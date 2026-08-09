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

import hashlib
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


def _real_state_names() -> set[str]:
    """Every state name the EC spine has ever carried, from the committed roster.

    The real-corpus test needs a *real* state-name set, not a permissive one. An
    earlier draft passed a container accepting every label, to avoid depending on the
    TIGER shapefile — which silently broke the test on every real Archives page:
    Table 2 carries footnote/notes rows that are filtered out **precisely because**
    their text is not a state name, so accepting everything makes them parse as state
    rows and raise. Sourcing the names from ``ec_state_roster_by_year.json`` (real,
    committed, public-domain Archives data — test input only, D006) keeps the test
    offline without disabling the filter.
    """
    roster = json.loads(
        (Path(__file__).parent.parent / "fixtures" / "ec_state_roster_by_year.json")
        .read_text(encoding="utf-8")
    )
    return {s for year in roster["years"].values() for s in year["states"]}


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
    # Re-running re-fetches ONLY the index; the year pages are skipped. That is what
    # makes an interrupted ~8.5-minute run resumable, while still letting a stale
    # corpus discover years added upstream (see the refresh test below).
    assert first == 3  # index + 2 years
    assert again.seen == [INDEX_URL]


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


def test_manifest_write_leaves_no_temp_file(tmp_path: Path) -> None:
    # Globbed, not a fixed name: write_manifest uses tempfile.mkstemp, so the literal
    # "manifest.json.tmp" this once asserted against is a path EC can never produce —
    # the assertion was vacuous and a non-atomic writer passed it.
    write_manifest(tmp_path, {"2020": {"file": "2020.html"}})
    assert list(tmp_path.glob("*.tmp")) == []
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
    with pytest.raises(ScrapeError, match="python -m usvote corpus"):
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

    This is the payoff of #89: 41 of the 50 in-scope years have no committed fixture,
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

        # Real state names, from the committed roster — not a permissive container.
        # See _real_state_names for why the permissive version silently broke this.
        parsed = parse.parse_election_years(raw, state_names=_real_state_names())
        assert len(parsed) == len(years)


# --- refresh / recovery (defects found in review) ---------------------------


def test_snapshot_repairs_a_corpus_whose_index_predates_a_new_election(
    tmp_path: Path,
) -> None:
    # THE deadlock this feature shipped with in review: the index was skipped as
    # "already on disk", so the year list could never grow, and the completeness guard
    # failed forever while prescribing this very command as the remedy.
    snapshot_election_years(
        tmp_path, years={2016, 2020}, fetch=_fake_fetch([2016, 2020]), sleep=lambda s: None
    )
    upstream = _fake_fetch([2016, 2020, 2024])  # a new election is now published
    snapshot_election_years(
        tmp_path, years={2016, 2020, 2024}, fetch=upstream, sleep=lambda s: None
    )
    assert (tmp_path / "2024.html").exists()
    assert_corpus_covers_years(tmp_path, {2016, 2020, 2024})  # does not raise


def test_snapshot_repairs_a_corpus_whose_manifest_was_lost(tmp_path: Path) -> None:
    # Skipping on file-existence alone let the manifest and the files disagree with no
    # way back: the guard keys on the manifest, so a corpus copied without its
    # manifest.json was permanently unrepairable.
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    (tmp_path / MANIFEST_FILENAME).unlink()
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    assert_corpus_covers_years(tmp_path, {2020})  # does not raise


def test_snapshot_repairs_a_corpus_whose_year_page_was_lost(tmp_path: Path) -> None:
    # The mirror of the manifest-lost case, and the other half of the two-part skip
    # predicate. Only the manifest half was tested, so dropping the file-exists half
    # survived the suite — and its consequence is the same deadlock: a corpus that loses
    # a page but keeps its manifest would skip the re-fetch and then fail the guard,
    # prescribing the command that just declined to do anything.
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    (tmp_path / "2020.html").unlink()
    again = _fake_fetch([2020])
    snapshot_election_years(tmp_path, years={2020}, fetch=again, sleep=lambda s: None)
    assert (tmp_path / "2020.html").exists()
    assert any(u.endswith("/2020") for u in again.seen)
    assert_corpus_covers_years(tmp_path, {2020})  # does not raise


def test_guard_requires_the_index(tmp_path: Path) -> None:
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    (tmp_path / EC_INDEX_FILENAME).unlink()
    # Without it the year list cannot be enumerated at all, so the corpus is unusable
    # even though every year page is present.
    with pytest.raises(ScrapeError, match="no _index_results.html"):
        assert_corpus_covers_years(tmp_path, {2020})


def test_guard_checks_an_explicitly_requested_out_of_scope_year(tmp_path: Path) -> None:
    # The guard used to intersect with ec_ingest_years(), so a deliberate
    # years={1868} passed vacuously on an empty corpus — contradicting usvote.years'
    # contract that an explicit year fails loudly rather than being silently dropped.
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    with pytest.raises(ScrapeError, match="1868"):
        assert_corpus_covers_years(tmp_path, {1868})


def test_pipeline_guard_checks_an_explicitly_requested_out_of_scope_year() -> None:
    # The pipeline-side twin of the test above. Its comment states "NOT intersected with
    # ec_ingest_years() ... This is why the parameter is a Collection" — but only the
    # scrape-side guard had a test for it, so adding the intersection back here passed.
    # Vacuous-pass is the failure mode: years={1868} over an empty scrape must RAISE.
    with pytest.raises(PipelineError, match="1868"):
        _assert_years_scraped({}, {1868})


def test_non_year_link_in_the_index_is_skipped_not_fatal(tmp_path: Path) -> None:
    # "The Archives restructured the index" is what the corpus exists to survive; a
    # non-year link must not abort a crawl minutes deep with a bare ValueError.
    class WithJunkLink(_FakeFetch):
        def __call__(self, url: str) -> tuple[int, bytes]:
            if url == INDEX_URL:
                self.seen.append(url)
                return 200, (
                    b'<div id="main-col"><table>'
                    b'<a href="/electoral-college/about">about</a>'
                    b'<a href="/electoral-college/2020">2020</a>'
                    b"</table></div>"
                )
            return super().__call__(url)

    snapshot_election_years(
        tmp_path, years={2020}, fetch=WithJunkLink([2020]), sleep=lambda s: None
    )
    assert (tmp_path / "2020.html").exists()


def test_corrupt_manifest_raises_a_typed_error(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(ScrapeError, match="not valid JSON"):
        read_manifest(tmp_path)


def test_network_error_becomes_a_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # A ~50-request crawl will meet a blip; it must not end in a raw traceback.
    import requests

    def boom(*a: object, **k: object) -> object:
        raise requests.ConnectionError("connection reset")

    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(ScrapeError, match="Network error"):
        scrape.fetch_page_with_status("https://www.archives.gov/electoral-college/2020")


def test_redirect_is_refused_rather_than_saved_under_the_wrong_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A retired year page 302'ing to the index would otherwise be saved as <year>.html
    # at status 200 and pass every check the guard makes.
    class Resp:
        status_code = 200
        content = b"<html>index</html>"
        url = "https://www.archives.gov/electoral-college/results"
        history = ["302"]

    monkeypatch.setattr("requests.get", lambda *a, **k: Resp())
    with pytest.raises(ScrapeError, match="redirected"):
        scrape.fetch_page_with_status("https://www.archives.gov/electoral-college/2020")


def test_fetch_page_sends_the_truthful_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    # The one behavior whose loss is silent and whose cost lands on archives.gov.
    captured: dict[str, object] = {}

    class Resp:
        status_code = 200
        content = b"ok"
        history: list[str] = []

    def fake_get(url: str, **kwargs: object) -> Resp:
        captured.update(kwargs)
        return Resp()

    monkeypatch.setattr("requests.get", fake_get)
    scrape.fetch_page_with_status("https://www.archives.gov/electoral-college/2020")
    assert captured["headers"] == {"User-Agent": scrape.USER_AGENT}


# --- structural guards for the duplication this design rests on -------------


def test_ec_and_ucsb_manifest_entries_have_the_same_shape(tmp_path: Path) -> None:
    """Pin the EC/UCSB manifest parity the duplication in ``scrape.py`` claims.

    The manifest helpers are duplicated rather than imported because a top-level EC
    module importing from a PV subpackage would invert the D006/D015 dependency
    direction. Duplication is only safe if something holds the two shapes together —
    this drives **both** writers and compares the resulting keys, rather than asserting
    EC against a hand-copied literal (which would pin EC to itself and notice nothing).
    """
    from usvote.ucsb import scrape as ucsb_scrape

    ec_dir, ucsb_dir = tmp_path / "ec", tmp_path / "ucsb"
    ec_dir.mkdir()
    ucsb_dir.mkdir()

    snapshot_election_years(
        ec_dir, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    ec_entry = read_manifest(ec_dir)["2020"]

    # Drive UCSB's REAL entry construction (snapshot_elections), not a hand-written
    # dict round-tripped through its writer — that would return whatever it was given
    # and pin nothing, which is exactly the failure mode this test exists to avoid.
    (ucsb_dir / ucsb_scrape.INDEX_FILENAME).write_text(
        '<a href="/statistics/elections/2020">2020</a>', encoding="utf-8"
    )
    ucsb_scrape.snapshot_elections(
        ucsb_dir,
        fetch=lambda url: ucsb_scrape.FetchResult(200, b"<html>ucsb</html>", None),
        sleep=lambda s: None,
    )
    ucsb_manifest = ucsb_scrape.read_manifest(ucsb_dir)
    ucsb_entry = ucsb_manifest[next(k for k in ucsb_manifest if k != "index")]
    assert set(ec_entry) == set(ucsb_entry), (
        f"EC manifest entry {sorted(ec_entry)} has drifted from UCSB's "
        f"{sorted(ucsb_entry)} — the duplication in usvote/scrape.py is only safe "
        f"while these agree."
    )


def test_no_top_level_module_imports_a_source_subpackage() -> None:
    """The EC spine must never import from a PV source subpackage (D006/D015).

    The greppable invariant that makes the duplicated manifest helpers *deliberate*
    rather than an oversight: without it, the obvious "simplification" is to import
    ``usvote.ucsb.scrape.write_manifest`` into ``usvote/scrape.py``, inverting the
    dependency direction with a green suite. Mirrors the existing warehouse and
    api-import-graph guards.

    Scoped to the **source** subpackages only. ``usvote/pv/`` is the shared,
    source-neutral contract, and top-level EC-domain modules import it by design
    (``join.py`` reads the resolved PV views, ``snapshot.py`` reads ``pv_source``) — an
    earlier draft of this test forbade it and correctly failed.
    """
    import usvote

    package_root = Path(usvote.__file__).parent
    exempt = {"warehouse.py", "__main__.py"}  # composition roots sit ABOVE both (D027)
    offenders = []
    for module in sorted(package_root.glob("*.py")):
        if module.name in exempt:
            continue
        source = module.read_text(encoding="utf-8")
        for pv in ("usvote.mit", "usvote.ucsb"):
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")) and pv in stripped:
                    offenders.append(f"{module.name}: {stripped}")
    assert not offenders, (
        "top-level EC modules must not import PV source subpackages "
        f"(D006/D015): {offenders}"
    )


# --- behaviors added by the production-readiness pass (#89) -----------------
# That commit added ~120 production lines with no tests; all of it survived mutation.


def test_describe_corpus_age_reports_count_and_date_range(tmp_path: Path) -> None:
    snapshot_election_years(
        tmp_path, years={2016, 2020}, fetch=_fake_fetch([2016, 2020]), sleep=lambda s: None
    )
    described = scrape.describe_corpus_age(tmp_path)
    assert described.startswith("2 year pages, fetched ")


def test_describe_corpus_age_excludes_the_always_refetched_index(tmp_path: Path) -> None:
    # The index is force-refetched every run, so including it would always read as
    # "today" and mask genuinely old year pages — the exact staleness this reports on.
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    manifest = read_manifest(tmp_path)
    manifest["2020"]["timestamp"] = "1999-01-01T00:00:00+00:00"
    write_manifest(tmp_path, manifest)
    described = scrape.describe_corpus_age(tmp_path)
    assert "1999-01-01" in described
    assert "1 year pages" in described


def test_describe_corpus_age_handles_an_empty_corpus(tmp_path: Path) -> None:
    assert scrape.describe_corpus_age(tmp_path) == "no dated pages"


def test_snapshot_writes_pages_through_the_atomic_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin the call site, not just the outcome.

    An earlier version of this test asserted "no .tmp left behind, content matches" —
    which a plain ``write_bytes`` satisfies too, so reverting to the non-atomic write
    survived it. Observing *which* writer is used is the only thing that catches that.
    """
    routed: list[Path] = []
    real = scrape._atomic_write_bytes

    def recording_write(path: Path, body: bytes) -> None:
        routed.append(path)
        real(path, body)

    monkeypatch.setattr(scrape, "_atomic_write_bytes", recording_write)
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    assert (tmp_path / "2020.html") in routed


def test_atomic_write_leaves_no_partial_file_when_the_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The property that matters: a crash mid-write must leave the destination absent or
    # whole, never partial. A plain write_bytes leaves a truncated page that then passes
    # the completeness guard forever.
    def boom(_fd: int) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(scrape.os, "fsync", boom)
    with pytest.raises(OSError):
        scrape._atomic_write_bytes(tmp_path / "2020.html", b"partial")
    assert not (tmp_path / "2020.html").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_snapshot_refuses_a_directory_whose_parent_is_missing(tmp_path: Path) -> None:
    # An unmounted external volume would otherwise have the whole tree silently built
    # on the root filesystem, crawled for ~8.5 minutes, and reported as success.
    missing_parent = tmp_path / "not-mounted" / "corpus"
    with pytest.raises(ScrapeError, match="parent does not exist"):
        snapshot_election_years(
            missing_parent, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
        )


def test_scrape_raw_election_tables_skips_a_non_year_link(tmp_path: Path) -> None:
    # The snapshot driver was taught to skip these, but the pipeline's own scraper still
    # crashed on them with a bare ValueError — so a non-year link saved into the corpus
    # index would poison every later rebuild with no remedy text.
    links = [
        "https://www.archives.gov/electoral-college/about",
        "https://www.archives.gov/electoral-college/2020",
    ]
    tables = scrape.scrape_raw_election_tables(
        links, {2020}, fetch=lambda url: _year_html(2020)
    )
    assert sorted(tables) == [2020]


def test_scrape_raw_election_tables_tolerates_a_trailing_slash(tmp_path: Path) -> None:
    # The three spellings of "the year is the last URL segment" disagreed here: one
    # yielded "1824" and another "", so a snapshot succeeded and the pipeline then died
    # on int("").
    tables = scrape.scrape_raw_election_tables(
        ["https://www.archives.gov/electoral-college/2020/"],
        {2020},
        fetch=lambda url: _year_html(2020),
    )
    assert sorted(tables) == [2020]


def test_snapshot_verifies_itself_before_reporting_success(tmp_path: Path) -> None:
    """The final self-check must fire when nothing else has already raised.

    An earlier version used a 404, which halts inside ``capture`` *before* the final
    guard — so it passed for the wrong reason and removing the guard survived it. The
    honest scenario is an index that simply does not link a requested year: every fetch
    succeeds, nothing errors, and only the closing self-check notices the corpus is
    short. Without it, `usvote corpus` reports "complete" for an incomplete corpus.
    """
    with pytest.raises(ScrapeError, match="incomplete"):
        snapshot_election_years(
            tmp_path,
            years={2020, 2024},
            fetch=_fake_fetch([2020]),  # index links 2020 only
            sleep=lambda s: None,
        )


def test_guard_rejects_a_year_recorded_as_non_200(tmp_path: Path) -> None:
    # Reachable: manifest lost, refresh 503s, the stale <year>.html from an earlier run
    # is still on disk — so the file-exists clause passes and only the status clause
    # stops the rebuild replaying stale bytes.
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    manifest = read_manifest(tmp_path)
    manifest["2020"]["http_status"] = 503
    write_manifest(tmp_path, manifest)
    with pytest.raises(ScrapeError, match="incomplete"):
        assert_corpus_covers_years(tmp_path, {2020})


# --- code-review round 3 findings (#89) -------------------------------------


def _redirecting_response(final_url: str) -> type:
    class Resp:
        status_code = 200
        content = b"<html>ok</html>"
        url = final_url
        history = ["302"]

    return Resp


@pytest.mark.parametrize(
    "requested,final",
    [
        # Canonical trailing slash on the index — the case that would have broken the
        # corpus on its very FIRST request the day archives.gov adds one, while the live
        # scrape (which follows redirects silently) kept working.
        (
            "https://www.archives.gov/electoral-college/results",
            "https://www.archives.gov/electoral-college/results/",
        ),
        # http -> https, a year page. Same corpus name, so nothing can be mis-saved.
        (
            "http://www.archives.gov/electoral-college/2020",
            "https://www.archives.gov/electoral-college/2020",
        ),
    ],
)
def test_a_redirect_landing_on_the_same_corpus_name_is_allowed(
    monkeypatch: pytest.MonkeyPatch, requested: str, final: str
) -> None:
    """The refusal is about the NAME, not about redirects as such.

    The hazard is answering for one page under another page's name. A redirect that
    resolves to the same corpus filename cannot do that, so refusing it has no upside —
    and the index in particular has no year name to be mis-saved under at all.
    """
    monkeypatch.setattr("requests.get", lambda *a, **k: _redirecting_response(final)())
    status, body = scrape.fetch_page_with_status(requested)
    assert (status, body) == (200, b"<html>ok</html>")


def test_a_redirect_to_a_different_year_is_still_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The narrowing must not reopen the hole it narrowed: a year->year redirect saves
    # one year's markup under another year's name, silently, at status 200.
    monkeypatch.setattr(
        "requests.get",
        lambda *a, **k: _redirecting_response(
            "https://www.archives.gov/electoral-college/2016"
        )(),
    )
    with pytest.raises(ScrapeError, match="redirected"):
        scrape.fetch_page_with_status("https://www.archives.gov/electoral-college/2020")


def test_snapshot_resolves_a_not_yet_created_dir_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The env-resolving branch is the WRITE side: the directory is an output.

    Resolving it with the read-side default (``must_exist=True``) failed a fresh machine
    with "does not exist. Populate it with: python -m usvote corpus" — advice to run the
    command that just failed — and contradicted the mkdir five lines below. The shipped
    CLI always passes ``html_dir`` explicitly, so only a library caller reached it.
    """
    target = tmp_path / "not-yet"
    monkeypatch.setenv(scrape.config.EC_HTML_DIR_VAR, str(target))
    snapshot_election_years(
        years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    assert (target / "2020.html").exists()


# --- AC-verify round 5: the manifest's VALUES, and the remaining seams ------
# The manifest's key *set* was pinned; its values were not, so the corpus's provenance
# record could lie while every test stayed green.


def test_manifest_records_the_hash_of_the_bytes_actually_saved(tmp_path: Path) -> None:
    # D036 names this hash as the integrity mechanism. Only its LENGTH was asserted, so
    # hashing the wrong bytes survived — a corpus that certifies content it does not
    # hold, which is worse than no hash at all.
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    entry = read_manifest(tmp_path)["2020"]
    on_disk = (tmp_path / "2020.html").read_bytes()
    assert entry["sha256"] == hashlib.sha256(on_disk).hexdigest()
    assert entry["bytes"] == len(on_disk)


def test_manifest_records_the_url_fetched(tmp_path: Path) -> None:
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    manifest = read_manifest(tmp_path)
    assert manifest["2020"]["url"] == "https://www.archives.gov/electoral-college/2020"
    assert manifest["index"]["url"] == INDEX_URL


def test_manifest_timestamps_advance_between_runs(tmp_path: Path) -> None:
    # describe_corpus_age — the D036 staleness mitigation, and the only signal an
    # operator gets that a corpus predates an election — reads this field. Frozen to a
    # constant it would report a confidently false age, and only key-presence was pinned.
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    first = read_manifest(tmp_path)["index"]["timestamp"]
    snapshot_election_years(
        tmp_path, years={2020}, fetch=_fake_fetch([2020]), sleep=lambda s: None
    )
    # The index is force-refetched every run, so its stamp must move.
    assert read_manifest(tmp_path)["index"]["timestamp"] > first


def test_manifest_is_written_through_the_atomic_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mechanism, not outcome — the page writer's test, now for the manifest.

    ``test_manifest_write_leaves_no_temp_file`` asserts "no stray .tmp, content correct",
    which a plain ``write_text`` satisfies exactly, so swapping the atomic write out
    survived it. The manifest is rewritten after *every* page precisely so an interrupt
    leaves a parseable record; a truncate-then-write defeats that and looks identical
    afterwards. ``write_manifest`` now delegates to the one atomic writer, so observing
    that call is the check.
    """
    routed: list[Path] = []
    real = scrape._atomic_write_bytes

    def recording_write(path: Path, body: bytes) -> None:
        routed.append(path)
        real(path, body)

    monkeypatch.setattr(scrape, "_atomic_write_bytes", recording_write)
    write_manifest(tmp_path, {"2020": {"http_status": 200}})
    assert routed == [tmp_path / MANIFEST_FILENAME]


def test_read_manifest_rejects_a_non_object_document(tmp_path: Path) -> None:
    # Valid JSON, wrong shape: every later `.get("http_status")` would raise
    # AttributeError deep inside the guard instead of naming the file.
    (tmp_path / MANIFEST_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ScrapeError, match="must contain a JSON object"):
        read_manifest(tmp_path)


def test_snapshot_reads_the_injected_environ_not_the_process_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The `environ` DI seam had no test at all: ignoring it and always reading
    # os.environ left the suite green, which would make every injected-config caller
    # silently resolve the ambient corpus instead of the one it asked for.
    monkeypatch.setenv(scrape.config.EC_HTML_DIR_VAR, str(tmp_path / "ambient"))
    wanted = tmp_path / "injected"
    snapshot_election_years(
        years={2020},
        fetch=_fake_fetch([2020]),
        sleep=lambda s: None,
        environ={scrape.config.EC_HTML_DIR_VAR: str(wanted)},
    )
    assert (wanted / "2020.html").exists()
    assert not (tmp_path / "ambient").exists()


def test_manifest_is_written_sorted_and_indented(tmp_path: Path) -> None:
    # write_manifest's docstring promises "sorted, indented", and the corpus is meant to
    # be human-browsable and diffable against ucsb_raw/ — unsorted or unindented, every
    # rewrite (one per page) churns the whole file and the diff stops being readable.
    # Dropping either flag survived AC-verify round 6; the JSON stays valid, so only an
    # explicit assertion catches it.
    # Insertion order must DIFFER from sorted order, or sort_keys is unobservable: a
    # first draft passed {"2020": ..., "index": ...}, which is already sorted, so
    # dropping the flag produced byte-identical output and survived.
    write_manifest(tmp_path, {"index": {"bytes": 1}, "2020": {"http_status": 200}})
    text = (tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8")
    assert text.index('"2020"') < text.index('"index"')
    assert text == json.dumps(
        {"2020": {"http_status": 200}, "index": {"bytes": 1}}, indent=2, sort_keys=True
    )
