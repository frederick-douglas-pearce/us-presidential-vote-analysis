"""Unit tests for the local Archives HTML corpus (#89).

Offline throughout: the snapshot driver runs against a fake fetch, and the corpus
reader against a tmp_path directory. The one test that touches the *real* corpus is
:class:`TestRealCorpus`, which **skips when ``USVOTE_EC_HTML_DIR`` is unset** — the
same posture as UCSB's real-corpus test, since the corpus lives outside the repo and
CI has no copy of it.

The load-bearing case here is :func:`test_stale_corpus_missing_a_year_fails_loud`: a
corpus whose saved index predates a new election would otherwise build a warehouse
silently missing that year, and that warehouse feeds the public API snapshot (D034).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from usvote import scrape
from usvote.pipeline import PipelineError, _assert_years_scraped
from usvote.scrape import (
    EC_INDEX_FILENAME,
    MANIFEST_FILENAME,
    ScrapeError,
    assert_corpus_covers_years,
    corpus_filename,
    fetch_from_corpus,
    read_manifest,
    snapshot_election_years,
    write_manifest,
)

INDEX_URL = scrape.ARCHIVE_URL_DOMAIN + scrape.ARCHIVE_URL_BASE


class _AnyState:
    """A ``Container[str]`` accepting every label (see the real-corpus test)."""

    def __contains__(self, item: object) -> bool:
        return True


def _index_html(years: list[int]) -> bytes:
    links = "".join(
        f'<a href="/electoral-college/{y}">{y}</a>' for y in years
    )
    return f'<div id="main-col"><table>{links}</table></div>'.encode()


def _year_html(year: int) -> bytes:
    return f'<div id="main-col"><table><tr><td>{year}</td></tr></table></div>'.encode()


class _FakeFetch:
    """A snapshot fetch returning ``(status, body)``; records the URLs requested.

    A class rather than a closure with an attached attribute so ``seen`` is typed.
    """

    def __init__(self, years: list[int], *, status: int = 200) -> None:
        self.years = years
        self.status = status
        self.seen: list[str] = []

    def __call__(self, url: str) -> tuple[int, bytes]:
        self.seen.append(url)
        if url == INDEX_URL:
            return 200, _index_html(self.years)
        return self.status, _year_html(int(url.rstrip("/").rsplit("/", 1)[-1]))


def _fake_fetch(years: list[int], *, status: int = 200) -> _FakeFetch:
    return _FakeFetch(years, status=status)


# --- corpus_filename: the UCSB-mirrored naming -----------------------------


def test_year_url_maps_to_year_html() -> None:
    # The whole point of the layout mirror: browsable `1824.html`, matching ucsb_raw/,
    # NOT the fixtures' `www_archives_gov_electoral_college_1824.html`.
    assert corpus_filename("https://www.archives.gov/electoral-college/1824") == "1824.html"


def test_index_url_maps_to_the_index_file() -> None:
    assert corpus_filename(INDEX_URL) == EC_INDEX_FILENAME


def test_corpus_naming_differs_from_the_fixture_naming() -> None:
    # Pins that the two readers are genuinely distinct, so a future "simplification"
    # collapsing them fails here rather than breaking the committed fixture tests.
    url = "https://www.archives.gov/electoral-college/2020"
    assert corpus_filename(url) != scrape._snapshot_filename(url)


# --- snapshot driver -------------------------------------------------------


def test_snapshot_writes_index_year_pages_and_manifest(tmp_path: Path) -> None:
    manifest = snapshot_election_years(
        tmp_path, years={1824, 2020}, fetch=_fake_fetch([1824, 2020]), sleep=lambda s: None
    )
    assert (tmp_path / EC_INDEX_FILENAME).exists()
    assert (tmp_path / "1824.html").exists()
    assert (tmp_path / "2020.html").exists()
    assert set(manifest) == {"index", "1824", "2020"}


def test_manifest_entry_mirrors_the_ucsb_shape(tmp_path: Path) -> None:
    # The corpus is meant to be interchangeable-looking with ucsb_raw/; a reader who
    # knows one manifest must be able to read the other.
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    entry = read_manifest(tmp_path)["2020"]
    assert set(entry) == {"bytes", "file", "http_status", "sha256", "timestamp", "url"}
    assert entry["file"] == "2020.html"
    assert entry["http_status"] == 200
    assert entry["bytes"] == len(_year_html(2020))
    assert len(entry["sha256"]) == 64


def test_snapshot_skips_pages_already_on_disk(tmp_path: Path) -> None:
    fetch = _fake_fetch([1824, 2020])
    snapshot_election_years(tmp_path, years={1824, 2020}, fetch=fetch, sleep=lambda s: None)
    first = len(fetch.seen)

    again = _fake_fetch([1824, 2020])
    snapshot_election_years(tmp_path, years={1824, 2020}, fetch=again, sleep=lambda s: None)
    # Re-running is free: nothing re-fetched. This is what makes an interrupted
    # ~8.5-minute run resumable rather than restart-from-scratch.
    assert first > 0
    assert again.seen == []


def test_snapshot_waits_between_fetches_but_not_before_the_first(tmp_path: Path) -> None:
    waits: list[float] = []
    snapshot_election_years(
        tmp_path, years={1824, 2020}, fetch=_fake_fetch([1824, 2020]), sleep=waits.append
    )
    # 3 pages fetched (index + 2 years) -> 2 waits, each the robots.txt Crawl-delay.
    assert waits == [scrape.CRAWL_DELAY_SECONDS, scrape.CRAWL_DELAY_SECONDS]


def test_snapshot_halts_on_non_200_and_records_it(tmp_path: Path) -> None:
    # Never save an error page as if it were data (UCSB's posture).
    with pytest.raises(ScrapeError, match="HTTP 429"):
        snapshot_election_years(
            tmp_path,
            years={1824},
            fetch=_fake_fetch([1824], status=429),
            sleep=lambda s: None,
        )
    assert not (tmp_path / "1824.html").exists()
    # ...but the manifest still records the attempt, so the failure is auditable.
    assert read_manifest(tmp_path)["1824"]["http_status"] == 429


def test_manifest_write_is_atomic(tmp_path: Path) -> None:
    write_manifest(tmp_path, {"2020": {"file": "2020.html"}})
    assert not (tmp_path / f"{MANIFEST_FILENAME}.tmp").exists()
    assert json.loads((tmp_path / MANIFEST_FILENAME).read_text())["2020"]["file"] == (
        "2020.html"
    )


def test_read_manifest_of_an_empty_dir_is_not_an_error(tmp_path: Path) -> None:
    assert read_manifest(tmp_path) == {}


# --- corpus reader ---------------------------------------------------------


def test_fetch_from_corpus_replays_saved_bytes(tmp_path: Path) -> None:
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    fetch = fetch_from_corpus(tmp_path)
    assert fetch("https://www.archives.gov/electoral-college/2020") == _year_html(2020)
    assert fetch(INDEX_URL) == _index_html([2020])


def test_fetch_from_corpus_names_the_missing_page(tmp_path: Path) -> None:
    with pytest.raises(ScrapeError, match="python -m usvote snapshot"):
        fetch_from_corpus(tmp_path)("https://www.archives.gov/electoral-college/1888")


# --- completeness guards (the silent-partial-warehouse hazard) -------------


def test_stale_corpus_missing_a_year_fails_loud(tmp_path: Path) -> None:
    # THE case this guard exists for. A corpus snapshotted before a new election has
    # an index that never links the new year, so the rebuild would quietly produce a
    # warehouse short that year -- and that warehouse feeds the public API snapshot.
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    with pytest.raises(ScrapeError, match="incomplete"):
        assert_corpus_covers_years(tmp_path, {2020, 2024})


def test_complete_corpus_passes_the_guard(tmp_path: Path) -> None:
    snapshot_election_years(
        tmp_path, years={2016, 2020}, fetch=_fake_fetch([2016, 2020]), sleep=lambda s: None
    )
    assert_corpus_covers_years(tmp_path, {2016, 2020})  # does not raise


def test_guard_rejects_a_manifest_entry_whose_file_vanished(tmp_path: Path) -> None:
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    (tmp_path / "2020.html").unlink()
    with pytest.raises(ScrapeError, match="incomplete"):
        assert_corpus_covers_years(tmp_path, {2020})


def test_pipeline_guard_catches_a_year_the_scrape_never_returned() -> None:
    # The backstop covering the LIVE path too: archives.gov dropping a link from its
    # index is the same failure with a different cause.
    with pytest.raises(PipelineError, match=r"\[2024\]"):
        _assert_years_scraped({2016: [], 2020: []}, {2016, 2020, 2024})


def test_pipeline_guard_passes_when_every_requested_year_arrived() -> None:
    _assert_years_scraped({2016: [], 2020: []}, {2016, 2020})  # does not raise


# --- the real corpus (local only) ------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("USVOTE_EC_HTML_DIR"),
    reason="USVOTE_EC_HTML_DIR unset — the Archives corpus lives outside the repo",
)
class TestRealCorpus:
    """Replay the real corpus. Mirrors UCSB's ``TestRealCorpus`` posture (D022-style
    out-of-tree storage, though here by choice rather than by licence).

    This is the payoff of #89: 38 of the 49 in-scope years have no committed fixture,
    so before this ran, a ``parse.py`` refactor could break a 19th-century layout with
    nothing to catch it.
    """

    def test_every_in_scope_year_parses_from_the_corpus(self) -> None:
        from usvote import parse
        from usvote.years import ec_ingest_years

        html_dir = os.environ["USVOTE_EC_HTML_DIR"]
        assert_corpus_covers_years(html_dir)

        fetch = fetch_from_corpus(html_dir)
        years = ec_ingest_years()
        links = scrape.scrape_election_links(fetch=fetch)
        raw = scrape.scrape_raw_election_tables(links, years, fetch=fetch)
        _assert_years_scraped(raw, years)

        # Accept any state label: this test is about MARKUP coverage across 200 years
        # of layout drift, not geography, so it must not require the TIGER shapefile.
        parsed = parse.parse_election_years(raw, state_names=_AnyState())
        assert len(parsed) == len(years)
