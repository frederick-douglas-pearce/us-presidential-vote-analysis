"""Unit tests for :mod:`usvote.corpus` — the shared corpus mechanics (#181).

These cover the module the EC corpus (#89) and the UCSB snapshot (D023) were factored
into when Census became the third consumer. Two of them pin properties that previously
existed only as prose in a comment: that the manifest write routes through the atomic
writer, and that the atomic writer takes a **unique** temp name rather than a fixed
``<name>.tmp``. Both are mechanism tests on purpose — the outcome-only versions of each
pass a plain ``write_bytes``/fixed-name implementation identically, which is how the
non-atomic write survived an earlier round of review on the EC side.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from usvote import corpus


class _CallerError(RuntimeError):
    """Stand-in for a source's own typed error (``ScrapeError``, ``UCSBScrapeError``)."""


class TestReadManifest:
    def test_an_absent_manifest_is_the_first_run_state_not_an_error(
        self, tmp_path: Path
    ) -> None:
        assert corpus.read_manifest(tmp_path) == {}

    def test_it_raises_the_callers_error_class_carrying_the_callers_remedy(
        self, tmp_path: Path
    ) -> None:
        # The whole reason read_manifest takes these two arguments: a corrupt manifest
        # must tell the reader which command rebuilds *that* corpus, and must surface
        # as the typed error that corpus's CLI already handles.
        (tmp_path / corpus.MANIFEST_FILENAME).write_text('{"1824": {"http_stat')
        with pytest.raises(_CallerError, match="not valid JSON") as excinfo:
            corpus.read_manifest(
                tmp_path, error_cls=_CallerError, remedy="Re-run `the fix command`."
            )
        assert "Re-run `the fix command`." in str(excinfo.value)

    def test_a_valid_json_document_of_the_wrong_shape_is_rejected_by_name(
        self, tmp_path: Path
    ) -> None:
        # Valid JSON, wrong shape: every later `.get("http_status")` would raise
        # AttributeError deep inside a completeness guard instead of naming the file.
        (tmp_path / corpus.MANIFEST_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(_CallerError, match="must contain a JSON object"):
            corpus.read_manifest(tmp_path, error_cls=_CallerError)

    def test_the_default_error_class_is_used_when_a_caller_passes_none(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / corpus.MANIFEST_FILENAME).write_text("nope", encoding="utf-8")
        with pytest.raises(corpus.CorpusError):
            corpus.read_manifest(tmp_path)


class TestWriteManifest:
    def test_it_round_trips_and_leaves_no_temp_file(self, tmp_path: Path) -> None:
        manifest = {"1824": {"http_status": 200}, "index": {"http_status": 200}}
        corpus.write_manifest(tmp_path, manifest)
        assert corpus.read_manifest(tmp_path) == manifest
        assert [p.name for p in tmp_path.iterdir()] == [corpus.MANIFEST_FILENAME]

    def test_it_is_written_sorted_and_indented_to_stay_diffable(
        self, tmp_path: Path
    ) -> None:
        # It is the corpus's provenance record, read by humans in a diff, not an
        # internal cache file — so key order must not depend on insertion order.
        corpus.write_manifest(tmp_path, {"1876": {}, "1824": {}})
        body = (tmp_path / corpus.MANIFEST_FILENAME).read_text(encoding="utf-8")
        assert body.index('"1824"') < body.index('"1876"')
        assert "\n  " in body

    def test_the_write_routes_through_the_atomic_writer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mechanism, not outcome.

        "No stray .tmp, content correct" is satisfied exactly by a plain
        ``write_text``, so an outcome-only test cannot tell the atomic write from the
        truncate-then-write it replaced. The manifest is rewritten after *every* file
        precisely so an interrupt leaves a parseable record; observing which writer
        runs is the only check that catches losing that.
        """
        routed: list[Path] = []
        real = corpus.atomic_write_bytes

        def recording_write(path: Path, body: bytes) -> None:
            routed.append(path)
            real(path, body)

        monkeypatch.setattr(corpus, "atomic_write_bytes", recording_write)
        corpus.write_manifest(tmp_path, {"1824": {"http_status": 200}})
        assert routed == [tmp_path / corpus.MANIFEST_FILENAME]


class TestAtomicWriteBytes:
    def test_a_failed_write_leaves_the_destination_absent_not_partial(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The property that matters: a crash mid-write leaves the destination absent or
        # whole, never partial. A plain write_bytes leaves a truncated file that then
        # passes a completeness guard forever.
        def boom(_fd: int) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(corpus.os, "fsync", boom)
        with pytest.raises(OSError):
            corpus.atomic_write_bytes(tmp_path / "page.html", b"partial")
        assert not (tmp_path / "page.html").exists()
        assert list(tmp_path.glob("*.tmp")) == []

    def test_the_temp_name_is_unique_per_call_not_a_fixed_suffix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pin the property the docstring could previously only assert in prose.

        A fixed ``<name>.tmp`` behaves correctly single-threaded, so every
        outcome-based test passes with it. The hazard it hides is two concurrent runs
        interleaving writes into one shared temp path and then *atomically installing*
        the corrupt result — atomicity that faithfully publishes garbage. Observing
        that the unique-name allocator is what supplies the path is what stops a future
        edit quietly swapping it for a fixed one.
        """
        names: list[str] = []
        real_mkstemp = tempfile.mkstemp

        def recording_mkstemp(**kwargs: Any) -> tuple[int, str]:
            fd, name = real_mkstemp(**kwargs)
            names.append(name)
            return fd, name

        monkeypatch.setattr(corpus.tempfile, "mkstemp", recording_mkstemp)
        corpus.atomic_write_bytes(tmp_path / "page.html", b"one")
        corpus.atomic_write_bytes(tmp_path / "page.html", b"two")

        assert len(names) == 2, "the allocator was bypassed"
        assert names[0] != names[1], "a fixed temp name would collide under concurrency"
        assert (tmp_path / "page.html").read_bytes() == b"two"


class TestEntryShapes:
    def test_a_saved_entry_carries_the_shared_field_set(self) -> None:
        entry = corpus.provenance_entry(
            url="https://example.test/1824", file="1824.html", status=200, body=b"abc"
        )
        assert set(entry) == {
            "bytes",
            "file",
            "http_status",
            "sha256",
            "timestamp",
            "url",
        }
        assert entry["bytes"] == 3
        assert entry["http_status"] == 200

    def test_the_digest_is_taken_over_the_bytes_as_received(self) -> None:
        # The record must describe the payload the caller then writes to disk — the EC
        # corpus's recorded failure mode was a sha256 of what was *sent* rather than
        # what landed, which passes a completeness guard forever.
        import hashlib

        body = b"the page as received"
        entry = corpus.provenance_entry(
            url="https://example.test/x", file="x.html", status=200, body=body
        )
        assert entry["sha256"] == hashlib.sha256(body).hexdigest()

    def test_a_failed_entry_is_a_different_shape_so_it_cannot_read_as_saved(
        self,
    ) -> None:
        # A completeness guard keys on http_status == 200 plus the file on disk. The
        # failure entry carries no file/bytes/sha256 at all, so a recorded failure
        # cannot be mistaken for a saved page even before the guard looks at the status.
        entry = corpus.error_entry(
            url="https://example.test/2028", status=429, error="blocked"
        )
        assert set(entry) == {"url", "http_status", "timestamp", "error"}
        assert not {"file", "bytes", "sha256"} & set(entry)

    def test_a_transport_failure_records_a_null_status(self) -> None:
        entry = corpus.error_entry(
            url="https://example.test/x", status=None, error="dns"
        )
        assert entry["http_status"] is None

    def test_both_entry_shapes_survive_a_manifest_round_trip(
        self, tmp_path: Path
    ) -> None:
        # The entries are only useful if they are JSON-serializable as written; a
        # timestamp left as a datetime would round-trip through str() and quietly
        # change type between write and read.
        manifest = {
            "1824": corpus.provenance_entry(
                url="https://example.test/1824",
                file="1824.html",
                status=200,
                body=b"x",
            ),
            "2028": corpus.error_entry(
                url="https://example.test/2028", status=429, error="blocked"
            ),
        }
        corpus.write_manifest(tmp_path, manifest)
        assert corpus.read_manifest(tmp_path) == json.loads(json.dumps(manifest))
