"""Unit tests for :mod:`usvote.census.scrape` (#181) — the D023 corpus stage.

Never touches the network: every test injects a fake ``fetch``. The completeness guard
gets the most attention, because its failure mode is the one this corpus exists to
prevent — a warehouse built quietly short a century.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from usvote import corpus
from usvote import scrape as ec_scrape
from usvote.census import scrape
from usvote.census.scrape import (
    CENSUS_SOURCES,
    RESIDENT_SOURCE_IDS,
    CensusScrapeError,
    SourceFile,
    assert_corpus_covers_sources,
    describe_corpus,
    read_snapshot_sources,
    snapshot_census_sources,
)

_A = SourceFile(
    source_id="alpha",
    url="https://example.test/alpha.xlsx",
    filename="alpha.xlsx",
    span="1790-1990",
    description="alpha",
)
_B = SourceFile(
    source_id="beta",
    url="https://example.test/beta.xlsx",
    filename="beta.xlsx",
    span="2000-2020",
    description="beta",
)


def _fetch(bodies: dict[str, bytes], status: int = 200) -> Any:
    def fetch(url: str) -> tuple[int, bytes]:
        return status, bodies.get(url, b"")

    return fetch


class TestSnapshot:
    def test_it_saves_each_file_and_records_provenance(self, tmp_path: Path) -> None:
        manifest = snapshot_census_sources(
            tmp_path,
            sources=(_A, _B),
            fetch=_fetch({_A.url: b"aaa", _B.url: b"bbbb"}),
            sleep=lambda _s: None,
        )
        assert (tmp_path / "alpha.xlsx").read_bytes() == b"aaa"
        assert manifest["alpha"]["bytes"] == 3
        assert manifest["beta"]["file"] == "beta.xlsx"
        assert manifest["alpha"]["http_status"] == 200

    def test_a_second_run_re_downloads_nothing(self, tmp_path: Path) -> None:
        calls: list[str] = []

        def counting(url: str) -> tuple[int, bytes]:
            calls.append(url)
            return 200, b"x"

        for _ in range(2):
            snapshot_census_sources(
                tmp_path, sources=(_A,), fetch=counting, sleep=lambda _s: None
            )
        assert calls == [_A.url], "the second run re-fetched an already-saved file"

    def test_a_lost_manifest_repairs_itself_rather_than_staying_broken(
        self, tmp_path: Path
    ) -> None:
        """Skipping requires the file **and** a 200 record, not just the file.

        The completeness guard keys on the manifest, so if skipping keyed on
        file-existence alone a corpus whose manifest was lost or never copied could
        never be repaired: every run would skip the download and every guard would then
        fail, with the remedy being the command that just skipped.
        """
        snapshot_census_sources(
            tmp_path, sources=(_A,), fetch=_fetch({_A.url: b"x"}), sleep=lambda _s: None
        )
        (tmp_path / corpus.MANIFEST_FILENAME).unlink()
        snapshot_census_sources(
            tmp_path, sources=(_A,), fetch=_fetch({_A.url: b"x"}), sleep=lambda _s: None
        )
        assert_corpus_covers_sources(tmp_path, ["alpha"])  # must not raise

    def test_a_non_200_halts_the_run_and_records_the_failure(
        self, tmp_path: Path
    ) -> None:
        # Saving an error page as if it were data is far worse than a failed run: it
        # passes every later completeness check while carrying HTML where a spreadsheet
        # should be.
        with pytest.raises(CensusScrapeError, match="HTTP 503"):
            snapshot_census_sources(
                tmp_path,
                sources=(_A,),
                fetch=_fetch({_A.url: b"<html>oops</html>"}, status=503),
                sleep=lambda _s: None,
            )
        assert not (tmp_path / "alpha.xlsx").exists()
        assert scrape.read_manifest(tmp_path)["alpha"]["http_status"] == 503

    def test_it_waits_between_fetches_but_not_before_the_first(
        self, tmp_path: Path
    ) -> None:
        waits: list[float] = []
        snapshot_census_sources(
            tmp_path,
            sources=(_A, _B),
            fetch=_fetch({_A.url: b"a", _B.url: b"b"}),
            sleep=waits.append,
        )
        assert waits == [scrape.CRAWL_DELAY_SECONDS]

    def test_a_missing_parent_directory_is_refused(self, tmp_path: Path) -> None:
        # An unmounted external volume would otherwise have the corpus silently built on
        # the root filesystem and reported as success.
        with pytest.raises(CensusScrapeError, match="parent does not exist"):
            snapshot_census_sources(
                tmp_path / "not-mounted" / "corpus",
                sources=(_A,),
                fetch=_fetch({_A.url: b"a"}),
                sleep=lambda _s: None,
            )


class TestCompletenessGuard:
    def test_a_complete_corpus_passes(self, tmp_path: Path) -> None:
        snapshot_census_sources(
            tmp_path,
            sources=(_A, _B),
            fetch=_fetch({_A.url: b"a", _B.url: b"b"}),
            sleep=lambda _s: None,
        )
        assert_corpus_covers_sources(tmp_path, ["alpha", "beta"])

    def test_a_missing_source_raises_and_names_it(self, tmp_path: Path) -> None:
        snapshot_census_sources(
            tmp_path, sources=(_A,), fetch=_fetch({_A.url: b"a"}), sleep=lambda _s: None
        )
        with pytest.raises(CensusScrapeError, match="beta"):
            assert_corpus_covers_sources(tmp_path, ["alpha", "beta"])

    def test_a_manifest_entry_whose_file_is_gone_is_caught(
        self, tmp_path: Path
    ) -> None:
        """The manifest and the disk can disagree, so both are checked.

        Checking only the manifest passes a corpus whose files were deleted; checking
        only the disk passes one whose provenance was lost. Either alone lets a rebuild
        proceed on something it cannot vouch for.
        """
        snapshot_census_sources(
            tmp_path, sources=(_A,), fetch=_fetch({_A.url: b"a"}), sleep=lambda _s: None
        )
        (tmp_path / "alpha.xlsx").unlink()
        with pytest.raises(CensusScrapeError, match="not on disk"):
            assert_corpus_covers_sources(tmp_path, ["alpha"])

    def test_the_read_seam_verifies_before_returning_bytes(
        self, tmp_path: Path
    ) -> None:
        # The guard runs *inside* the reader, so a short corpus fails before a byte is
        # parsed rather than producing a frame quietly missing a century.
        with pytest.raises(CensusScrapeError):
            read_snapshot_sources(tmp_path, source_ids=["alpha"])

    def test_the_read_seam_returns_the_saved_bytes_keyed_by_source_id(
        self, tmp_path: Path
    ) -> None:
        snapshot_census_sources(
            tmp_path,
            sources=(_A, _B),
            fetch=_fetch({_A.url: b"aaa", _B.url: b"bb"}),
            sleep=lambda _s: None,
        )
        assert read_snapshot_sources(tmp_path, source_ids=["alpha", "beta"]) == {
            "alpha": b"aaa",
            "beta": b"bb",
        }


class TestCorpusShapeAndExtensibility:
    def test_the_shipped_sources_cover_the_resident_series(self) -> None:
        assert set(RESIDENT_SOURCE_IDS) <= {s.source_id for s in CENSUS_SOURCES}

    def test_source_ids_and_filenames_are_unique(self) -> None:
        # Two sources sharing a manifest key would silently overwrite each other's
        # provenance; two sharing a filename would overwrite the file itself.
        assert len({s.source_id for s in CENSUS_SOURCES}) == len(CENSUS_SOURCES)
        assert len({s.filename for s in CENSUS_SOURCES}) == len(CENSUS_SOURCES)

    def test_a_new_source_needs_no_change_to_the_manifest_or_the_guard(
        self, tmp_path: Path
    ) -> None:
        """#183 adds the seats files to this same corpus; this is that rehearsal.

        The keying is by logical source id rather than by year precisely so a file
        covering a different thing entirely drops in as a new entry. If this test ever
        needs editing to admit a new source, the extensibility claim was false.
        """
        seats = SourceFile(
            source_id="seats_1789_2010",
            url="https://example.test/seats.pdf",
            filename="seats.pdf",
            span="1789-2010",
            description="seats per state",
        )
        snapshot_census_sources(
            tmp_path,
            sources=(_A, seats),
            fetch=_fetch({_A.url: b"a", seats.url: b"%PDF-"}),
            sleep=lambda _s: None,
        )
        assert_corpus_covers_sources(tmp_path, ["alpha", "seats_1789_2010"])
        assert read_snapshot_sources(tmp_path, source_ids=["seats_1789_2010"]) == {
            "seats_1789_2010": b"%PDF-"
        }

    def test_the_entry_shape_matches_the_ec_corpus_entry_shape(
        self, tmp_path: Path
    ) -> None:
        """The cross-corpus parity check, now that all three share one writer.

        ``test_ec_and_ucsb_manifest_entries_have_the_same_shape`` compared two
        independent implementations; since the extraction there is one, so this asserts
        the census corpus really does go through it rather than having quietly grown its
        own entry shape.
        """
        snapshot_census_sources(
            tmp_path, sources=(_A,), fetch=_fetch({_A.url: b"a"}), sleep=lambda _s: None
        )
        census_entry = scrape.read_manifest(tmp_path)["alpha"]

        ec_dir = tmp_path / "ec"
        ec_dir.mkdir()
        ec_scrape.write_manifest(
            ec_dir,
            {
                "2020": corpus.provenance_entry(
                    url="https://www.archives.gov/electoral-college/2020",
                    file="2020.html",
                    status=200,
                    body=b"<html/>",
                )
            },
        )
        assert set(census_entry) == set(ec_scrape.read_manifest(ec_dir)["2020"])


class TestDescribeCorpus:
    def test_it_reports_the_file_count_and_fetch_date(self, tmp_path: Path) -> None:
        snapshot_census_sources(
            tmp_path,
            sources=(_A, _B),
            fetch=_fetch({_A.url: b"a", _B.url: b"b"}),
            sleep=lambda _s: None,
        )
        assert describe_corpus(tmp_path).startswith("2 files, fetched ")

    def test_an_empty_corpus_says_so(self, tmp_path: Path) -> None:
        assert describe_corpus(tmp_path) == "no dated files"
