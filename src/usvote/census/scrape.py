"""Fetch/snapshot stage — download the published Census tables into a local corpus.

Named ``scrape.py`` for symmetry with the other sources' network stages, but it does not
scrape: it downloads a fixed, small set of **published files** by URL. There is no index
to walk and no markup to parse here, which is the whole reason S1 preferred this source
over the scanned Forstall volumes.

**The snapshot is mandatory, not a convenience** (S1 §10). The ``api.census.gov`` path
needs a key, and the static published files can be re-issued under the same URL with
different contents — so a corpus with recorded sha256s is the only way a rebuild is
reproducible. It mirrors ``USVOTE_EC_HTML_DIR`` (#89) and the UCSB corpus (D023), and
shares their manifest mechanics via :mod:`usvote.corpus`.

**The manifest is keyed by a logical source id, not by year.** EC and UCSB key by
election year because they snapshot one page per election; this corpus holds a handful
of named files spanning many censuses each, so ``resident_1790_1990`` is the natural
key. The per-*entry* shape is unchanged and is what the cross-corpus parity tests
compare. The keying is also what makes the corpus **extensible**: #183 adds the seats
sources (``seats_1789_2010``, ``seats_2020``) as new :data:`CENSUS_SOURCES` entries with
no change to the manifest shape, the guard, or the reader.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Any

import requests

from usvote import config, corpus
from usvote.census.config import CENSUS_CORPUS_DIR_VAR, census_corpus_dir_from_env
from usvote.census.sources import (
    CENSUS_SOURCES,
    RESIDENT_1790_1990,
    RESIDENT_1910_2020,
    RESIDENT_SOURCE_IDS,
    SourceFile,
)

# Re-exported so existing importers keep working and the catalog has ONE home: the
# definitions moved to usvote.census.sources in the #181 review (F10), because the pure
# transform needs the filename/vintage provenance and must not import this module's
# `requests` dependency to get it.
__all__ = [
    "CENSUS_SOURCES",
    "RESIDENT_1790_1990",
    "RESIDENT_1910_2020",
    "RESIDENT_SOURCE_IDS",
    "CensusScrapeError",
    "SourceFile",
    "assert_corpus_covers_sources",
    "describe_corpus",
    "fetch_file",
    "read_manifest",
    "read_snapshot_sources",
    "snapshot_census_sources",
    "write_manifest",
]

#: Identify truthfully, exactly as the EC and UCSB snapshots do (D015-legal: the shared
#: string lives in the source-neutral top-level config).
USER_AGENT = config.USER_AGENT

#: Seconds to wait on a fetch before giving up.
FETCH_TIMEOUT_SECONDS = 60

#: Seconds between fetches. census.gov publishes no ``Crawl-delay`` for ``*``, so this
#: is courtesy rather than compliance — and with only a couple of files in the corpus
#: the total cost is seconds, not the ~8.5 minutes the Archives crawl pays.
CRAWL_DELAY_SECONDS = 2


class CensusScrapeError(RuntimeError):
    """Raised when the corpus cannot be built or is incomplete."""


_MANIFEST_REMEDY = (
    "Delete it and re-run `python -m usvote.census snapshot` to rebuild the record "
    "from the saved files."
)


def _resolve_corpus_dir(
    corpus_dir: str | Path | None,
    environ: Mapping[str, str] | None,
    *,
    must_exist: bool,
) -> str | Path:
    """Return ``corpus_dir``, or resolve it from the environment when not given.

    One spelling for what the snapshot (write, ``must_exist=False``) and the read seam
    (``must_exist=True``) both need, with ``environ`` injectable for testing — UCSB's
    ``_resolve_html_dir`` shape.
    """
    if corpus_dir is not None:
        return corpus_dir
    if environ is not None:
        return census_corpus_dir_from_env(environ, must_exist=must_exist)
    return census_corpus_dir_from_env(must_exist=must_exist)


def fetch_file(url: str) -> tuple[int, bytes]:
    """Fetch ``url`` identifying truthfully; return ``(status_code, body)``.

    Surfaces the status rather than raising on it, so the driver can record the failure
    in the manifest before halting — the EC snapshot's posture, for the same reason:
    an error page saved as if it were data is far worse than a failed run.
    """
    try:
        response = requests.get(
            url, timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}
        )
    except requests.RequestException as exc:
        raise CensusScrapeError(
            f"Network error fetching {url}: {exc}. Files already saved are kept — "
            f"re-run `python -m usvote.census snapshot` to resume."
        ) from exc
    return response.status_code, response.content


def read_manifest(corpus_dir: str | Path) -> dict[str, Any]:
    """Read the corpus manifest, or return an empty dict when absent."""
    return corpus.read_manifest(
        corpus_dir, error_cls=CensusScrapeError, remedy=_MANIFEST_REMEDY
    )


def write_manifest(corpus_dir: str | Path, manifest: Mapping[str, Any]) -> None:
    """Write the corpus manifest sorted, indented and atomically."""
    corpus.write_manifest(corpus_dir, manifest)


def snapshot_census_sources(
    corpus_dir: str | Path | None = None,
    *,
    sources: Collection[SourceFile] = CENSUS_SOURCES,
    fetch: Callable[[str], tuple[int, bytes]] = fetch_file,
    sleep: Callable[[float], None] = time.sleep,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Download every source file not already present; return the manifest.

    Re-running is cheap and safe: a file already on disk **and** recorded at status 200
    is skipped, so an interrupted run resumes rather than re-downloading. Skipping
    requires both, so a corpus whose ``manifest.json`` was lost repairs itself on the
    next run instead of being permanently unrepairable — the guard keys on the manifest,
    and skipping on file-existence alone would let the two stores disagree with no way
    back.

    Halts on the first non-200 rather than saving an error page as data, recording the
    failure in the manifest first so the run is resumable and the reason is on disk.
    """
    directory = Path(_resolve_corpus_dir(corpus_dir, environ, must_exist=False))
    # parents=False deliberately, as in the EC snapshot: if the variable points into an
    # unmounted external volume, parents=True would silently build the tree on the root
    # filesystem and report success, leaving an invisible corpus under the mountpoint.
    # A missing *parent* is nearly always a wrong or unmounted path; a missing leaf is
    # the legitimate first-run case.
    try:
        directory.mkdir(exist_ok=True)
    except FileNotFoundError as exc:
        raise CensusScrapeError(
            f"Cannot create {directory}: its parent does not exist. Check "
            f"{CENSUS_CORPUS_DIR_VAR} — if it points into an external or network "
            f"volume, that volume may not be mounted."
        ) from exc

    manifest = read_manifest(directory)
    fetched_any = False
    for source in sources:
        recorded = manifest.get(source.source_id)
        has_record = isinstance(recorded, dict) and recorded.get("http_status") == 200
        if (directory / source.filename).exists() and has_record:
            print(f"{source.source_id}: skip (already have)")
            continue
        if fetched_any:
            sleep(CRAWL_DELAY_SECONDS)
        status, body = fetch(source.url)
        fetched_any = True
        if status != 200:
            manifest[source.source_id] = corpus.error_entry(
                url=source.url, status=status, error=f"HTTP {status}"
            )
            write_manifest(directory, manifest)
            raise CensusScrapeError(
                f"census.gov returned HTTP {status} for {source.url}; halting the "
                f"snapshot rather than saving an error response as data. The manifest "
                f"records the failure; re-run to resume once the site recovers."
            )
        corpus.atomic_write_bytes(directory / source.filename, body)
        manifest[source.source_id] = corpus.provenance_entry(
            url=source.url, file=source.filename, status=status, body=body
        )
        write_manifest(directory, manifest)
        print(f"{source.source_id}: 200 {len(body)}b saved as {source.filename}")

    assert_corpus_covers_sources(directory, [s.source_id for s in sources])
    return manifest


def assert_corpus_covers_sources(
    corpus_dir: str | Path, source_ids: Collection[str]
) -> None:
    """Raise unless every id in ``source_ids`` is recorded at 200 and present on disk.

    The counterpart of :func:`usvote.scrape.assert_corpus_covers_years`, and it exists
    for the same reason: a corpus that is missing a file must fail **loud** rather than
    silently building a warehouse short that data. Checks the manifest *and* the file,
    because either alone can be stale.
    """
    manifest = read_manifest(corpus_dir)
    missing: list[str] = []
    for source_id in sorted(source_ids):
        entry = manifest.get(source_id)
        if not isinstance(entry, dict) or entry.get("http_status") != 200:
            missing.append(f"{source_id} (no 200 manifest entry)")
            continue
        filename = entry.get("file")
        if not isinstance(filename, str) or not (Path(corpus_dir) / filename).exists():
            missing.append(f"{source_id} (recorded as {filename!r}, not on disk)")
    if missing:
        raise CensusScrapeError(
            f"The Census corpus at {corpus_dir} is incomplete: {', '.join(missing)}. "
            f"Run `python -m usvote.census snapshot` to complete it."
        )


def read_snapshot_sources(
    corpus_dir: str | Path | None = None,
    *,
    source_ids: Collection[str] = RESIDENT_SOURCE_IDS,
    environ: Mapping[str, str] | None = None,
) -> dict[str, bytes]:
    """Return ``{source_id: file bytes}`` for the corpus — the pipeline's read seam.

    Verifies completeness first, so a short corpus raises here rather than producing a
    frame that is quietly missing a century.
    """
    directory = Path(_resolve_corpus_dir(corpus_dir, environ, must_exist=True))
    assert_corpus_covers_sources(directory, source_ids)
    manifest = read_manifest(directory)
    return {
        source_id: (directory / manifest[source_id]["file"]).read_bytes()
        for source_id in sorted(source_ids)
    }


def describe_corpus(corpus_dir: str | Path) -> str:
    """Summarize the corpus for a rebuild banner: file count + fetch date range.

    The same cheap mitigation :func:`usvote.scrape.describe_corpus_age` provides for the
    Archives corpus. A stale corpus is otherwise indistinguishable from "nothing changed
    upstream" all the way through to whatever is built from it.
    """
    stamps = sorted(
        entry["timestamp"]
        for entry in read_manifest(corpus_dir).values()
        if isinstance(entry, dict) and "timestamp" in entry
    )
    if not stamps:
        return "no dated files"
    oldest, newest = stamps[0][:10], stamps[-1][:10]
    span = oldest if oldest == newest else f"{oldest} .. {newest}"
    return f"{len(stamps)} files, fetched {span}"
