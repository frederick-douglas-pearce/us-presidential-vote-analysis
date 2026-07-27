"""Scrape stage — walk the National Archives site and fetch raw HTML.

Maps to notebook Section 2 (the network-facing half). This module is the *only*
place live network access belongs: it fetches the Archives results index and the
two HTML tables published per election year, so every downstream stage (parse,
transform, load) can run offline against saved HTML.

Ported from ``step1_electoral_college_data.ipynb`` in E2-S1 (#23). The three
notebook functions land here unchanged in behavior — ``get_html_tables``,
``scrape_election_links``, ``scrape_raw_election_tables`` — with two additions:

- a **fetch seam** (:data:`Fetch`, defaulting to :func:`fetch_url`). Live network
  access is confined to :func:`fetch_url`; inject an alternative fetch to run the
  same parsing against saved HTML. This is how parse/transform tests stay offline.
- a **snapshot seam** (:func:`snapshot_page` / :func:`fetch_from_dir`) that lets a
  developer save Archives pages into ``tests/fixtures/`` and replay them.

One intentional behavior change from the notebook (mirroring the ``db.py`` port's
typed-exception choice): a missing ``<div>``/``<table>`` now raises
:class:`ScrapeError` rather than surfacing as a bare ``AttributeError``.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Collection, Container, Iterable, Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, overload

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from usvote import config
from usvote.years import ec_ingest_years

# Archives site parameters (notebook Section 1.3). Exposed as defaults so callers
# and tests need not repeat them.
ARCHIVE_URL_DOMAIN = "https://www.archives.gov"
ARCHIVE_URL_BASE = "/electoral-college/results"

# Seconds to wait on the live network fetch before giving up. Bounded so a
# stalled server can't wedge a ~60-URL scrape indefinitely.
FETCH_TIMEOUT_SECONDS = 30

# A Fetch maps a URL to that page's raw markup (bytes). The default hits the
# network; tests and snapshot replay inject one that reads saved HTML instead.
#
# NOTE: this seam stays EC-local, and both PV sources have now settled the
# question of whether it should be shared. An earlier note here anticipated
# extracting it into a usvote/_fetch.py once usvote/ucsb/ (E4) and usvote/mit/
# (E5) landed, on the premise they would want the same machinery. They did not:
# MIT ships a local CSV and needs no fetch seam at all (usvote/mit/read.py),
# and UCSB's seam is a different shape -- it must surface HTTP status (its
# 403/429 halt reads it) and keep the body on an error status, encoding
# presidency.ucsb.edu's robots policy rather than plain "fetch a URL"
# (usvote/ucsb/scrape.py). With no duplicated knowledge to factor out, the
# extraction would buy indirection only. D006's actual constraint -- that a PV
# source must not import *from* this EC spine -- holds either way, and does.
# EC parse/transform tests (#25/#26) may reuse this
# seam (fetch_from_dir + get_html_tables) to replay a saved Archives page into
# <table> elements offline -- that is the tested snapshot->table path, so
# re-deriving fixture file paths in those tests would only duplicate it. (This
# in-spine reuse is fine; it is the future ucsb/mit sources reaching *into* the
# EC spine that D006 forbids.)
Fetch = Callable[[str], bytes]


class ScrapeError(RuntimeError):
    """Raised when an Archives page lacks the expected ``<div>``/``<table>``.

    The notebook read the structure directly and would surface a missing element
    as an ``AttributeError`` (``None.find_all(...)``). Raising a typed, message-
    carrying exception instead names the URL and the element that was missing.
    """


def fetch_url(url: str) -> bytes:
    """Fetch ``url`` over HTTP and return the raw response body.

    The package's single point of live network access. Every scrape function
    takes a ``fetch`` seam defaulting here; inject :func:`fetch_from_dir` (or any
    :data:`Fetch`) to run the identical parsing against saved HTML.
    """
    return requests.get(url, timeout=FETCH_TIMEOUT_SECONDS).content


@overload
def get_html_tables(
    url: str,
    div_id: str = ...,
    *,
    find_all: Literal[False] = ...,
    fetch: Fetch = ...,
) -> Tag: ...


@overload
def get_html_tables(
    url: str,
    div_id: str = ...,
    *,
    find_all: Literal[True],
    fetch: Fetch = ...,
) -> list[Tag]: ...


def get_html_tables(
    url: str,
    div_id: str = "main-col",
    *,
    find_all: bool = False,
    fetch: Fetch = fetch_url,
) -> Tag | list[Tag]:
    """Fetch ``url`` and return the ``<table>`` element(s) under ``<div id=...>``.

    With ``find_all=False`` (default) returns the first table; with
    ``find_all=True`` returns every table in the div. Raises :class:`ScrapeError`
    if the div — or, for the single-table case, its table — is absent. Note that
    ``find_all=True`` returns an empty list (not an error) for a div with no
    tables, matching the notebook; the parse stage (#25) is the first to depend
    on two tables being present.
    """
    soup = BeautifulSoup(fetch(url), "html.parser")
    div = soup.find("div", id=div_id)
    if not isinstance(div, Tag):
        raise ScrapeError(f"No <div id={div_id!r}> found at {url}")
    if find_all:
        return div.find_all("table")
    table = div.find("table")
    if not isinstance(table, Tag):
        raise ScrapeError(f"No <table> under <div id={div_id!r}> at {url}")
    return table


def scrape_election_links(
    archive_url_domain: str = ARCHIVE_URL_DOMAIN,
    archive_url_base: str = ARCHIVE_URL_BASE,
    *,
    fetch: Fetch = fetch_url,
) -> list[str]:
    """Return the absolute per-year Archives links from the results index."""
    link_table = get_html_tables(archive_url_domain + archive_url_base, fetch=fetch)
    return [archive_url_domain + _href(a) for a in link_table.find_all("a")]


def scrape_raw_election_tables(
    election_links: Iterable[str],
    us_election_years: Container[int],
    *,
    fetch: Fetch = fetch_url,
) -> dict[int, list[Tag]]:
    """Fetch the raw HTML tables for each election-year link.

    Keyed by year; a link whose trailing year is not a recognized US election
    year is reported (matching the notebook) and skipped.
    """
    raw_election_tables: dict[int, list[Tag]] = {}
    for link in election_links:
        segment = _year_segment(link)
        if not segment.isdigit():
            # Matches the snapshot driver's tolerance (#89). Without this, a non-year
            # link the driver skipped and saved into the corpus index would crash every
            # later rebuild with a bare ValueError and no remedy text. Skipping is safe
            # because a genuinely missing year still fails loudly in
            # usvote.pipeline._assert_years_scraped.
            print(f"Skipping non-year link in the Archives index: {link}")
            continue
        link_year = int(segment)
        if link_year in us_election_years:
            raw_election_tables[link_year] = get_html_tables(
                link, find_all=True, fetch=fetch
            )
        else:
            print(
                f"Error: The link year, {link_year}, parsed from the following "
                f"link does not match a US election year: \n{link}"
            )
    return raw_election_tables


# --- snapshot seam ---------------------------------------------------------
# Save Archives pages to disk once, then replay them offline. snapshot_page and
# fetch_from_dir share _snapshot_filename so a page saved under one name is found
# again by the other — a thin file cache keyed by URL.


def _href(anchor: Tag) -> str:
    """Return an anchor's ``href`` as a string (bs4 may type it as a list)."""
    href = anchor["href"]
    return href if isinstance(href, str) else href[0]


def _snapshot_filename(url: str) -> str:
    """Derive a stable ``.html`` filename from a URL (scheme stripped, slugged)."""
    slug = re.sub(r"[^0-9A-Za-z]+", "_", url.split("://", 1)[-1]).strip("_")
    return f"{slug}.html"


def snapshot_page(url: str, dest_dir: str | Path, *, fetch: Fetch = fetch_url) -> Path:
    """Fetch ``url`` and save its markup under ``dest_dir``; return the path.

    The developer seam for capturing Archives pages into ``tests/fixtures/``.
    Pair with :func:`fetch_from_dir` to replay the saved page offline.
    """
    dest = Path(dest_dir) / _snapshot_filename(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(fetch(url))
    return dest


def fetch_from_dir(source_dir: str | Path) -> Fetch:
    """Build a :data:`Fetch` that reads saved pages from ``source_dir``.

    Resolves each URL to the filename :func:`snapshot_page` would have written,
    so scrape functions run fully offline against snapshotted HTML.
    """
    base = Path(source_dir)

    def _fetch(url: str) -> bytes:
        return (base / _snapshot_filename(url)).read_bytes()

    return _fetch


# --- local Archives corpus (#89) -------------------------------------------
# A second, *complete* on-disk copy of the Archives pages, distinct from the
# curated tests/fixtures/ set above. Where snapshot_page/fetch_from_dir are a
# URL-keyed file cache for a handful of fixture pages, this is a whole-span
# corpus that a warehouse rebuild can run from with zero network requests --
# the path that feeds the public API snapshot (D034), which previously cost a
# full re-scrape of ~49 pages every time it was refreshed.
#
# Layout deliberately MIRRORS the UCSB corpus (usvote/ucsb/scrape.py): one
# ``<year>.html`` per election, the results index under EC_INDEX_FILENAME, and a
# ``manifest.json`` whose per-year entries carry the same keys. That is why this
# cannot reuse _snapshot_filename, which spells the same page
# ``www_archives_gov_electoral_college_1824.html``: fixtures keep that naming
# (their committed files and tests depend on it), the corpus uses UCSB's. The two
# readers coexist exactly as they do on the UCSB side.
#
# The manifest helpers below duplicate ~40 lines of usvote/ucsb/scrape.py rather than
# importing them. Importing usvote.ucsb here would invert D006/D015 (the spine must not
# depend on a source), which a test enforces. A source-neutral third home (usvote/pv/,
# or a new shared module) WOULD satisfy D015 and was available; ~40 lines of JSON
# read/write did not seem worth a new shared module, so the cost is paid instead by
# test_ec_and_ucsb_manifest_entries_have_the_same_shape, which drives both writers and
# compares the results. If a third consumer ever appears, extract rather than duplicate
# again.

#: Identify truthfully, as the UCSB scraper does — one shared string (D015-legal:
#: ``source -> shared``). archives.gov's robots.txt sets ``Crawl-delay: 10`` for
#: ``User-agent: *`` and does not disallow ``/electoral-college/``; the snapshot driver
#: honors both.
USER_AGENT = config.USER_AGENT

#: Seconds between snapshot fetches, from archives.gov/robots.txt (``Crawl-delay: 10``).
#: A full ~50-page run therefore takes ~8.5 minutes. That cost is paid **once**; every
#: subsequent warehouse rebuild replays the corpus for free. NOTE: the live
#: :func:`fetch_url` path does *not* yet honor this — see the follow-up issue.
CRAWL_DELAY_SECONDS = 10

#: The saved results index, named with a leading underscore so it sorts away from the
#: ``<year>.html`` pages (UCSB's ``_index_elections.html`` convention).
EC_INDEX_FILENAME = "_index_results.html"

#: Provenance record for the corpus: per-year sha256 + byte count + fetch timestamp.
MANIFEST_FILENAME = "manifest.json"


def corpus_filename(url: str) -> str:
    """Return the corpus filename for ``url`` — ``<year>.html``, or the index.

    The corpus counterpart of :func:`_snapshot_filename`. Year pages are keyed by the
    trailing path segment (``.../electoral-college/2020`` -> ``2020.html``), which is
    what makes the directory human-browsable and diffable against ``ucsb_raw/``.
    """
    if url.rstrip("/") == (ARCHIVE_URL_DOMAIN + ARCHIVE_URL_BASE).rstrip("/"):
        return EC_INDEX_FILENAME
    return f"{_year_segment(url)}.html"


def _year_segment(url: str) -> str:
    """Return a URL's trailing path segment — the year, for an Archives year page.

    One spelling for what was three (here, the snapshot loop, and
    :func:`scrape_raw_election_tables`), which disagreed on trailing slashes: a
    ``.../1824/`` href produced ``1824`` in one and ``""`` in another, so the snapshot
    would succeed and the pipeline then die on ``int("")``.
    """
    return url.rstrip("/").rsplit("/", 1)[-1]


def read_manifest(html_dir: str | Path) -> dict[str, Any]:
    """Read the corpus manifest, or return an empty dict when absent.

    An absent manifest is the expected first-run state, not an error.
    """
    path = Path(html_dir) / MANIFEST_FILENAME
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # Recoverable and message-worthy, not a stack trace (UCSB's wording).
        raise ScrapeError(
            f"{path} is not valid JSON ({exc}). Delete it and re-run "
            f"`python -m usvote corpus` to rebuild the record from the saved pages."
        ) from exc
    if not isinstance(loaded, dict):
        raise ScrapeError(
            f"{path} must contain a JSON object, got {type(loaded).__name__}."
        )
    return loaded


def _atomic_write_bytes(path: Path, body: bytes) -> None:
    """Write ``body`` to ``path`` atomically (temp file in the same dir, then replace).

    Used for **both** the pages and the manifest. An earlier version wrote pages with a
    plain ``write_bytes`` while going to real trouble for the manifest, which left the
    more valuable artifact less protected: two concurrent ``corpus`` runs interleaved
    into one ``<year>.html``, and the winner then recorded a sha256 of what it *sent*
    rather than what landed — a corrupt page that passes the completeness guard forever.
    A rebuild reading the directory mid-run could likewise see a half-written page.
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


def write_manifest(html_dir: str | Path, manifest: Mapping[str, Any]) -> None:
    """Write ``manifest`` sorted, indented, and **atomically**.

    Mirrors :func:`usvote.ucsb.scrape.write_manifest`, including the reason for the
    atomicity: the manifest is rewritten after *every* page precisely so an interrupted
    run still leaves an accurate record, and a plain truncate-then-write would defeat
    that by leaving an unparseable half-file behind on a crash. The temp-file swap
    guarantees readers see either the old complete version or the new one.
    """
    directory = Path(html_dir)
    path = directory / MANIFEST_FILENAME
    # A unique temp name, not a fixed one: two concurrent runs sharing
    # ``manifest.json.tmp`` would interleave writes into it and then *atomically
    # install* the corrupt result.
    fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=MANIFEST_FILENAME, suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(dict(manifest), fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        Path(tmp_name).replace(path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def fetch_page_with_status(url: str) -> tuple[int, bytes]:
    """Fetch ``url`` identifying truthfully; return ``(status_code, body)``.

    The snapshot driver's fetch seam, kept separate from :func:`fetch_url` for two
    reasons. It must surface the **status** (the driver halts the whole run on a
    non-200 rather than saving an error page as if it were data — UCSB's posture), and
    it sends :data:`USER_AGENT`, which the live path does not yet do. Bringing the live
    path up to the same politeness is deliberately a separate change: it would add
    :data:`CRAWL_DELAY_SECONDS` between every page of a cold ``--replace``.
    """
    try:
        response = requests.get(
            url, timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}
        )
    except requests.RequestException as exc:
        # A ~50-request crawl spread over ~8.5 minutes will eventually meet a blip.
        # Surface it as the typed error the CLI already handles, not a traceback; saved
        # pages persist, so the documented remedy (re-run, it resumes) is accurate.
        raise ScrapeError(
            f"Network error fetching {url}: {exc}. Pages already saved are kept — "
            f"re-run `python -m usvote corpus` to resume."
        ) from exc
    if response.history:
        # A retired page 302'd to the index would otherwise be saved under the year's
        # name, at status 200, and pass every check the guard makes — silently feeding
        # the wrong markup to every future offline rebuild.
        raise ScrapeError(
            f"{url} redirected to {response.url}; refusing to save the response under "
            f"the requested year's name. The Archives layout may have changed."
        )
    return response.status_code, response.content


def snapshot_election_years(
    html_dir: str | Path | None = None,
    *,
    years: Collection[int] | None = None,
    fetch: Callable[[str], tuple[int, bytes]] = fetch_page_with_status,
    sleep: Callable[[float], None] = time.sleep,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Snapshot the Archives index + every in-scope year page; return the manifest.

    The EC counterpart of :func:`usvote.ucsb.scrape.snapshot_elections`, with the same
    contract: wait :data:`CRAWL_DELAY_SECONDS` between fetches (never before the first,
    and never for a page already on disk), record each page's sha256, rewrite the
    manifest after every page so an interrupt leaves an accurate record, and **stop the
    run entirely** the first time the server answers non-200 rather than saving error
    pages as data.

    When ``html_dir`` is ``None`` it resolves from ``USVOTE_EC_HTML_DIR``. ``years``
    defaults to :func:`usvote.years.ec_ingest_years`. Re-running is cheap and safe: a
    page already present is skipped, so an interrupted run resumes where it stopped
    rather than restarting the ~8.5-minute crawl.
    """
    directory = Path(
        html_dir
        if html_dir is not None
        else config.ec_html_dir_from_env(os.environ if environ is None else environ)
    )
    # parents=False on purpose: if USVOTE_EC_HTML_DIR points into an unmounted external
    # volume, parents=True would silently build the whole tree on the root filesystem,
    # crawl for ~8.5 minutes, report success, and leave an invisible corpus under the
    # mountpoint. A missing *parent* is nearly always a wrong or unmounted path; a
    # missing leaf is the legitimate first-run case.
    try:
        directory.mkdir(exist_ok=True)
    except FileNotFoundError as exc:
        raise ScrapeError(
            f"Cannot create {directory}: its parent does not exist. Check "
            f"{config.EC_HTML_DIR_VAR} — if it points into an external or network "
            f"volume, that volume may not be mounted."
        ) from exc
    wanted = ec_ingest_years() if years is None else years
    manifest = read_manifest(directory)
    fetched_any = False

    def capture(url: str, *, force: bool = False) -> None:
        """Fetch, record, and save one page — the single write path.

        Every page including the index goes through here, so the manifest is a
        complete provenance record. An earlier draft let the index be written
        separately while enumerating years, which silently left the index with no
        manifest entry — exactly the page whose staleness the guard needs to audit.

        ``force`` re-fetches even when the page is on disk; the index always sets it
        (see the call site). Skipping requires **both** the file and a 200 manifest
        entry, so a corpus whose ``manifest.json`` was lost or never copied repairs
        itself on the next run instead of being permanently unrepairable: the guard
        keys on the manifest, and skipping on file-existence alone let the two stores
        disagree with no way back.
        """
        name = corpus_filename(url)
        key = "index" if name == EC_INDEX_FILENAME else name.removesuffix(".html")
        recorded = manifest.get(key)
        has_record = isinstance(recorded, dict) and recorded.get("http_status") == 200
        if not force and (directory / name).exists() and has_record:
            return
        nonlocal fetched_any
        if fetched_any:
            sleep(CRAWL_DELAY_SECONDS)
        status, body = fetch(url)
        fetched_any = True
        manifest[key] = {
            "bytes": len(body),
            "file": name,
            "http_status": status,
            "sha256": sha256(body).hexdigest(),
            "timestamp": datetime.now(UTC).isoformat(),
            "url": url,
        }
        if status != 200:
            write_manifest(directory, manifest)
            raise ScrapeError(
                f"Archives returned HTTP {status} for {url}; halting the snapshot "
                f"rather than saving an error page as data. The manifest records the "
                f"failure; re-run to resume once the site recovers."
            )
        _atomic_write_bytes(directory / name, body)
        write_manifest(directory, manifest)

    # The index first: year URLs are enumerated *from it*, so it must be on disk before
    # the corpus reader can walk it — and it is re-fetched **every run** (``force``).
    # Skipping it would make a stale corpus permanently unrepairable: the year list
    # comes from the saved index, so a corpus snapshotted before a new election could
    # never discover that election, and the completeness guard would fail forever while
    # prescribing this very command as the remedy. One extra request per run is the
    # whole cost; the index is the one page that must be current.
    capture(ARCHIVE_URL_DOMAIN + ARCHIVE_URL_BASE, force=True)
    for url in scrape_election_links(fetch=fetch_from_corpus(directory)):
        segment = _year_segment(url)
        if not segment.isdigit():
            # "The Archives restructured the index" is exactly what the corpus exists to
            # survive; a non-year link must not abort a crawl minutes deep.
            print(f"Skipping non-year link in the Archives index: {url}")
            continue
        if int(segment) in wanted:
            capture(url)

    # The on-disk manifest is authoritative here: write_manifest flushed after every
    # capture, and on a fully-cached run it is the prior run's record that matters.
    assert_corpus_covers_years(directory, wanted)
    return manifest


def describe_corpus_age(html_dir: str | Path) -> str:
    """Summarize the corpus for the rebuild banner: page count + fetch date range.

    The cheapest mitigation for the D036 content-divergence residual. The manifest has
    recorded a per-page ``timestamp`` all along and nothing read it, so "how old is the
    data this warehouse was built from?" was unanswerable from the output — and a stale
    corpus is indistinguishable from "nothing changed upstream" all the way through to
    the deployed snapshot hash. Printing the range converts an invisible condition into
    a date the operator can judge.

    The ``index`` entry is excluded deliberately: it is re-fetched every run, so it
    would always read as today and would mask genuinely old year pages.
    """
    stamps = sorted(
        entry["timestamp"]
        for key, entry in read_manifest(html_dir).items()
        if key != "index" and isinstance(entry, dict) and "timestamp" in entry
    )
    if not stamps:
        return "no dated pages"
    oldest, newest = stamps[0][:10], stamps[-1][:10]
    span = oldest if oldest == newest else f"{oldest} .. {newest}"
    return f"{len(stamps)} year pages, fetched {span}"


def fetch_from_corpus(html_dir: str | Path) -> Fetch:
    """Build a :data:`Fetch` reading the local corpus — the offline rebuild seam.

    Resolves each URL through :func:`corpus_filename`, so the whole EC pipeline
    (:func:`usvote.pipeline.run_ec_pipeline`, which already accepts a ``fetch`` seam)
    runs against saved bytes with zero requests. Distinct from :func:`fetch_from_dir`,
    which serves the differently-named ``tests/fixtures/`` pages.
    """
    base = Path(html_dir)

    def _fetch(url: str) -> bytes:
        path = base / corpus_filename(url)
        if not path.exists():
            raise ScrapeError(
                f"{path} is missing from the Archives corpus. Populate it with "
                f"`python -m usvote corpus`, or pass --no-corpus to scrape live."
            )
        return path.read_bytes()

    return _fetch


def assert_corpus_covers_years(
    html_dir: str | Path, years: Collection[int] | None = None
) -> None:
    """Raise unless every requested year is present, 200, and on disk.

    **The corpus completeness guard**, run before an offline rebuild so a stale corpus
    fails here by name rather than surfacing later as a mysteriously short warehouse.

    Without it a stale corpus fails *silently*: :func:`scrape_raw_election_tables`
    iterates the links found in the *index* and only warns about years it does not
    recognize, so a year that is requested but simply absent from a stale index is
    never fetched and never reported — the build exits 0 having ingested a year less,
    and that partial warehouse feeds the public API snapshot (D034). Nothing downstream
    catches it either: :func:`usvote.transform.assert_state_count_by_year` iterates the
    years that *are* present, so a wholly-missing year is invisible to it. This is the
    same silent-drop hazard the roster assert (D024) closes on the PV side.

    Reached by construction on the next-cycle path: when ``LATEST_ELECTION_YEAR`` moves
    to 2028, a corpus snapshotted today is missing 2028 and every rebuild would quietly
    produce a 2028-less warehouse.
    """
    directory = Path(html_dir)
    manifest = read_manifest(directory)
    # No intersection with ec_ingest_years(): an explicitly requested out-of-scope year
    # (years={1868}) must still be checked, or the guard passes vacuously on an empty
    # corpus — contradicting usvote.years' contract that an explicit year "fails loudly
    # rather than being silently dropped".
    wanted = set(ec_ingest_years() if years is None else years)
    if not (directory / EC_INDEX_FILENAME).exists():
        raise ScrapeError(
            f"Archives corpus at {directory} has no {EC_INDEX_FILENAME}. The year list "
            f"is enumerated from it, so the corpus is unusable. Build it with "
            f"`python -m usvote corpus`."
        )
    missing = sorted(
        y
        for y in wanted
        if str(y) not in manifest
        or not isinstance(manifest[str(y)], dict)
        or manifest[str(y)].get("http_status") != 200
        or not (directory / f"{y}.html").exists()
    )
    if missing:
        raise ScrapeError(
            f"Archives corpus at {directory} is incomplete — missing or non-200 for "
            f"{len(missing)} year(s): {missing}. Refresh it with "
            f"`python -m usvote corpus` before rebuilding from the corpus; a partial "
            f"corpus would silently build a warehouse missing those years."
        )
