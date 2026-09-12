"""Shared on-disk corpus mechanics — manifest I/O and provenance entries.

Every local source snapshot in this project keeps the same two things on disk: the
fetched files themselves, and a ``manifest.json`` recording where each came from
(url, byte count, sha256, HTTP status, fetch timestamp). Three consumers now do it —
the Archives corpus (:mod:`usvote.scrape`, #89), the UCSB snapshot
(:mod:`usvote.ucsb.scrape`, D023) and the Census corpus (:mod:`usvote.census.scrape`,
#181) — and this module is the one implementation of the mechanical half.

**Why this module exists, and why it did not until now.** ``usvote/scrape.py`` carried
the reason verbatim: the EC corpus duplicated ~40 lines of UCSB's manifest helpers
rather than importing them, because importing :mod:`usvote.ucsb` from the spine would
invert D006/D015 (the spine must not depend on a source) — a direction
``test_no_top_level_module_imports_a_source_subpackage`` enforces. A source-neutral home
*would* have satisfied D015, and the comment closed with the standing instruction this
module discharges:

    "If a third consumer ever appears, extract rather than duplicate again."

Census is that third consumer. The dependency runs ``source -> shared`` and
``spine -> shared``, exactly as :mod:`usvote.years` and :mod:`usvote.pv.status` already
do, so no layering guard is disturbed: this is a top-level module, not a source
subpackage, so a top-level importer does not trip the guard above either.

**What stays with each source, deliberately.** Only the *mechanics* are shared. Each
corpus keeps its own:

* **key derivation** — EC and UCSB key the manifest by election year, Census by a
  logical source id (``resident_1790_1990``), since it snapshots a handful of named
  files rather than one page per year;
* **error type and remedy text** — a corrupt manifest should tell the reader which
  command rebuilds *that* corpus, so :func:`read_manifest` takes both;
* **politeness policy** — crawl delays, blocked-status handling and whether a non-200
  halts the run are per-source decisions about a per-source server.

This module is stdlib-only and does no network I/O, which keeps it importable from any
stage without dragging a dependency along.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

#: Provenance record for a corpus: per-file sha256 + byte count + fetch timestamp.
#: One spelling, so the three corpora stay diffable against each other on disk.
MANIFEST_FILENAME = "manifest.json"


class CorpusError(RuntimeError):
    """Raised for a corpus that cannot be read.

    The default for :func:`read_manifest`; each source passes its own error class so a
    failure surfaces as that source's typed error, which its CLI already handles.
    """


def utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp for manifest provenance."""
    return datetime.now(UTC).isoformat()


def atomic_write_bytes(path: Path, body: bytes) -> None:
    """Write ``body`` to ``path`` atomically (unique temp file, fsync, then replace).

    Used for **both** saved pages and the manifest. An earlier version of the EC corpus
    wrote pages with a plain ``write_bytes`` while going to real trouble for the
    manifest, which left the more valuable artifact less protected: two concurrent
    snapshot runs interleaved into one saved page, and the winner then recorded a
    sha256 of what it *sent* rather than what landed — a corrupt page that passes the
    completeness guard forever. A rebuild reading the directory mid-run could likewise
    see a half-written page.

    ``mkstemp`` gives a **unique** temp name, not a fixed ``<name>.tmp``: two concurrent
    runs sharing one temp path would interleave writes into it and then *atomically
    install* the corrupt result — atomicity that faithfully publishes garbage. Nothing
    tests that distinction (a fixed name behaves correctly single-threaded), so this
    note is the only thing standing between a future edit and the bug. The UCSB writer
    used the fixed-name spelling until it moved here; adopting the stricter one is part
    of what the extraction buys.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        Path(tmp_name).replace(path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def read_manifest(
    corpus_dir: str | Path,
    *,
    error_cls: type[Exception] = CorpusError,
    remedy: str = "",
) -> dict[str, Any]:
    """Read a corpus manifest, or return an empty dict when absent.

    An absent manifest is the expected first-run state, not an error. A manifest that
    exists but does not parse is recoverable and message-worthy rather than a stack
    trace, so it raises ``error_cls`` with ``remedy`` appended — each corpus points the
    reader at the command that rebuilds *it*.

    The object check is deliberate and is not merely defensive typing: a manifest that
    parsed as a list or a string would otherwise reach callers that do
    ``manifest.get(key)`` and fail much later, somewhere that cannot say what is wrong.
    """
    path = Path(corpus_dir) / MANIFEST_FILENAME
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise error_cls(f"{path} is not valid JSON ({exc}). {remedy}".strip()) from exc
    if not isinstance(loaded, dict):
        raise error_cls(
            f"{path} must contain a JSON object, got {type(loaded).__name__}."
        )
    manifest: dict[str, Any] = loaded
    return manifest


def write_manifest(corpus_dir: str | Path, manifest: Mapping[str, Any]) -> None:
    """Write ``manifest`` sorted, indented, and **atomically**.

    Sorted keys and indentation keep it diffable and human-readable — it is the
    corpus's provenance record, not an internal cache file.

    The atomicity is the point rather than a flourish: the manifest is rewritten after
    *every* file precisely so an interrupted run still leaves an accurate record, and a
    plain truncate-then-write would defeat that by leaving an unparseable half-file
    behind on a crash. The temp-file swap guarantees a reader sees either the old
    complete version or the new one, never a partial one.
    """
    path = Path(corpus_dir) / MANIFEST_FILENAME
    body = json.dumps(dict(manifest), indent=2, sort_keys=True)
    atomic_write_bytes(path, body.encode("utf-8"))


def provenance_entry(
    *, url: str, file: str, status: int, body: bytes
) -> dict[str, Any]:
    """Build the manifest entry for a file that was saved.

    The one definition of the per-entry field set the corpora share —
    ``{bytes, file, http_status, sha256, timestamp, url}``. It is asserted identical
    across corpora by the entry-shape parity tests, which previously had to drive two
    independent writers to compare them; now they guard one.

    The sha256 is taken over the bytes **as received**, which is the same object the
    caller writes to disk, so the record cannot describe a different payload than the
    one saved.
    """
    return {
        "bytes": len(body),
        "file": file,
        "http_status": status,
        "sha256": sha256(body).hexdigest(),
        "timestamp": utc_timestamp(),
        "url": url,
    }


def error_entry(*, url: str, status: int | None, error: str) -> dict[str, Any]:
    """Build the manifest entry for a file that was **not** saved.

    Deliberately a different shape from :func:`provenance_entry` — no ``file``,
    ``bytes`` or ``sha256``, because none exist — so a completeness guard keying on
    ``http_status == 200`` plus the file on disk cannot mistake a recorded failure for
    a saved page.
    """
    return {
        "url": url,
        "http_status": status,
        "timestamp": utc_timestamp(),
        "error": error,
    }
