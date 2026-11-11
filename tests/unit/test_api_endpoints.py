"""Unit tests for the ``/v1`` data endpoints (``usvote.api.routes``, E8-S3 #97).

All offline, **no live DB** (D028): the shared synthetic ``ec_pv_redistributable``-shaped
frame (``tests/fixtures/api_snapshot.py``) is materialized into a real SQLite snapshot via
:func:`usvote.snapshot.build_snapshot`, and the app serves that file. The
``snapshot_path`` / ``settings`` / ``client`` fixtures come from ``tests/unit/conftest.py``
(#99). Covers each endpoint's happy path, the ``state`` / ``candidate`` / ``year_from`` /
``year_to`` filters, 404 (unknown / out-of-window identifier) vs. 200-empty (empty filter),
422 (bad / inverted params), the ETag / 304 freshness — including the architect's
*404-not-304* case — the server-side cap failing loud, and the D006 / D030 guards (no
``candidate_id``, no non-MIT row reachable).

The shared 2020 rows match this story's original fixture, so the value-specific rollup
assertions below are unchanged; 2016 is the shared flip year (structural assertions only
here — the flip itself is asserted in ``test_api_e2e``).
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from usvote.api import create_app
from usvote.api.config import ApiSettings
from usvote.api.repository import SnapshotError, SnapshotRepository

# --- list years -------------------------------------------------------------


def test_list_elections_returns_years_with_counts(client: TestClient) -> None:
    body = client.get("/v1/elections").json()
    assert [item["year"] for item in body["data"]] == [1860, 2016, 2020]
    assert all(item["candidate_count"] == 2 for item in body["data"])
    assert body["meta"]["count"] == 3
    # has_popular_vote answers "which years can I compare PV for" from the index
    # itself, without fetching each year and inspecting its nulls (#139).
    assert {i["year"]: i["has_popular_vote"] for i in body["data"]} == {
        1860: False,
        2016: True,
        2020: True,
    }
    prov = body["meta"]["provenance"]
    assert prov["source"] == "MIT"
    assert prov["source_name"] == "MIT Election Lab"
    assert prov["license"] == "CC0-1.0"
    assert prov["license_url"]
    assert "UCSB" in prov["redistributable_note"]
    assert prov["coverage"] == {
        "year_min": 1860,
        "year_max": 2020,
        "pv_year_min": 2016,
        "pv_year_max": 2020,
    }
    assert prov["snapshot_version"]


def test_list_elections_year_filter(client: TestClient) -> None:
    body = client.get("/v1/elections", params={"year_from": 2020}).json()
    assert [item["year"] for item in body["data"]] == [2020]
    assert body["meta"]["count"] == 1


# --- one election -----------------------------------------------------------


def test_get_election_returns_rows_and_summary(client: TestClient) -> None:
    body = client.get("/v1/elections/2020").json()
    assert body["meta"]["count"] == 4  # 2 states x 2 candidates; summary not counted
    assert len(body["data"]) == 4
    assert len(body["summary"]) == 2
    row = body["data"][0]
    # Public field names, not the internal snapshot columns.
    assert "electoral_votes" in row
    assert "popular_votes" in row
    assert "state_popular_total" in row
    assert "state_electoral_votes" in row
    assert "president_electoral_votes" not in row
    assert "candidate_id" not in row


def test_get_election_state_filter(client: TestClient) -> None:
    body = client.get("/v1/elections/2020", params={"state": "TX"}).json()
    assert len(body["data"]) == 2
    assert {r["state_usps"] for r in body["data"]} == {"TX"}


def test_get_election_candidate_filter(client: TestClient) -> None:
    body = client.get("/v1/elections/2020", params={"candidate": "cand-b"}).json()
    assert len(body["data"]) == 2
    assert {r["candidate_slug"] for r in body["data"]} == {"cand-b"}


def test_get_election_empty_filter_is_200(client: TestClient) -> None:
    """A filter that matches nothing on a known year is a 200 empty, not a 404."""
    resp = client.get("/v1/elections/2020", params={"state": "FL"})
    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["meta"]["count"] == 0


def test_get_election_unknown_year_404(client: TestClient) -> None:
    resp = client.get("/v1/elections/1800")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "year_not_found"
    assert "1800" in body["error"]["message"]
    assert resp.headers["cache-control"] == "no-store"
    assert "etag" not in resp.headers


# --- national summary -------------------------------------------------------


def test_get_election_summary_reads_rollup(client: TestClient) -> None:
    body = client.get("/v1/elections/2020/summary").json()
    assert body["meta"]["count"] == 2
    by_slug = {r["candidate_slug"]: r for r in body["data"]}
    winner = by_slug["cand-b"]
    assert winner["national_electoral_votes"] == 55
    assert winner["took_office"] is True
    assert winner["national_pv_votes"] == 6_000_000 + 11_000_000
    assert winner["national_pv_denominator"] == 11_000_000 + 17_000_000
    # No hybrid / flip / margin fields (E8-S8).
    assert "margin" not in winner
    assert "hybrid" not in winner


def test_get_summary_unknown_year_404(client: TestClient) -> None:
    resp = client.get("/v1/elections/1900/summary")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "year_not_found"


def test_summary_ignores_row_filters_on_the_year_endpoint(client: TestClient) -> None:
    """The national ``summary`` is not narrowed by a ``data`` filter (documented)."""
    body = client.get("/v1/elections/2020", params={"candidate": "cand-b"}).json()
    assert {r["candidate_slug"] for r in body["data"]} == {"cand-b"}
    # summary still lists every candidate — it's the national roll-up for the year.
    assert {r["candidate_slug"] for r in body["summary"]} == {"cand-a", "cand-b"}


# --- every election's national summary (#431) -------------------------------

#: The order ``/v1/elections/summary`` must serve, written out by hand from
#: ``tests/fixtures/api_snapshot.py`` (year, then rank, then slug) rather than read back
#: from the snapshot, so a defect both routes share cannot pass by agreeing with itself.
_EXPECTED_SUMMARY_ORDER = [
    (1860, "john-bell"),
    (1860, "cand-d"),
    (2016, "cand-b"),
    (2016, "cand-a"),
    (2020, "cand-b"),
    (2020, "cand-a"),
]
_EXPECTED_SUMMARY_YEARS = [1860, 2016, 2020]


def _assert_summary_grain(body: dict) -> None:
    """One row per ``(year, candidate_slug)``; one ``elections`` item per year in ``data``.

    The unscoped route's fan-out guard (D094): a read that multiplied rows would repeat
    a key here before it came anywhere near ``MAX_ROWS``.
    """
    keys = [(r["year"], r["candidate_slug"]) for r in body["data"]]
    assert len(keys) == len(set(keys)), f"duplicate (year, candidate) rows: {keys}"
    election_years = [e["year"] for e in body["elections"]]
    assert len(election_years) == len(set(election_years)), election_years
    assert set(election_years) == {r["year"] for r in body["data"]}


def test_all_summaries_serve_the_expected_rows_in_order(client: TestClient) -> None:
    body = client.get("/v1/elections/summary").json()
    assert [(r["year"], r["candidate_slug"]) for r in body["data"]] == (
        _EXPECTED_SUMMARY_ORDER
    )
    assert [e["year"] for e in body["elections"]] == _EXPECTED_SUMMARY_YEARS
    assert body["meta"]["count"] == len(body["data"])
    assert body["meta"]["provenance"]["snapshot_version"]
    _assert_summary_grain(body)


def test_the_summary_fixture_is_not_vacuous() -> None:
    """The per-year loops below need several years, and a year with several candidates."""
    years = {y for y, _ in _EXPECTED_SUMMARY_ORDER}
    assert len(years) >= 2
    assert max(sum(1 for y, _ in _EXPECTED_SUMMARY_ORDER if y == yr) for yr in years) >= 2


def test_all_summaries_match_each_per_year_summary(client: TestClient) -> None:
    """For every served year, the rows and the block equal the per-year route's (AC2)."""
    body = client.get("/v1/elections/summary").json()
    years = [item["year"] for item in client.get("/v1/elections").json()["data"]]
    assert years == _EXPECTED_SUMMARY_YEARS
    elections = {e["year"]: e for e in body["elections"]}
    for year in years:
        per_year = client.get(f"/v1/elections/{year}/summary").json()
        assert [r for r in body["data"] if r["year"] == year] == per_year["data"], year
        assert elections[year] == per_year["election"], year


def test_all_summaries_cover_exactly_the_listed_years(client: TestClient) -> None:
    body = client.get("/v1/elections/summary").json()
    listed = {item["year"] for item in client.get("/v1/elections").json()["data"]}
    assert {e["year"] for e in body["elections"]} == listed
    assert {r["year"] for r in body["data"]} == listed


def test_all_summaries_carry_the_snapshot_etag(client: TestClient) -> None:
    resp = client.get("/v1/elections/summary")
    assert resp.status_code == 200
    reference = client.get("/v1/elections/2020/summary")
    assert resp.headers["etag"] == reference.headers["etag"]
    assert resp.headers["cache-control"] == reference.headers["cache-control"]
    again = client.get(
        "/v1/elections/summary", headers={"If-None-Match": resp.headers["etag"]}
    )
    assert again.status_code == 304
    assert again.content == b""


def test_all_summaries_ignore_an_unknown_query_parameter(client: TestClient) -> None:
    """No query parameters: an unknown one is ignored (200, same body), as elsewhere."""
    plain = client.get("/v1/elections/summary")
    odd = client.get("/v1/elections/summary", params={"year": 2020})
    assert odd.status_code == 200
    assert odd.json() == plain.json()


def test_the_all_years_path_does_not_shadow_or_get_shadowed_by_the_year_path(
    client: TestClient,
) -> None:
    """``/elections/summary`` is declared before ``/elections/{year}`` (D094)."""
    assert client.get("/v1/elections/summary").status_code == 200
    assert client.get("/v1/elections/2020").status_code == 200
    assert client.get("/v1/elections/2020/summary").status_code == 200
    assert client.get("/v1/elections/abc").status_code == 422


def test_the_summary_grain_check_fires_on_a_duplicated_row(
    snapshot_path: str, settings: ApiSettings
) -> None:
    """The twin that proves ``_assert_summary_grain`` can fail.

    The build keys ``national_rollup`` by ``(year, candidate_slug)``, so a duplicate
    needs a doctored table without that key.
    """
    _doctor(
        snapshot_path,
        "CREATE TABLE nr_nokey AS SELECT * FROM national_rollup",
        "DROP TABLE national_rollup",
        "ALTER TABLE nr_nokey RENAME TO national_rollup",
        "INSERT INTO national_rollup SELECT * FROM national_rollup "
        "WHERE year = 2020 AND candidate_slug = 'cand-b'",
    )
    with TestClient(create_app(settings)) as c:
        body = c.get("/v1/elections/summary").json()
    with pytest.raises(AssertionError, match="duplicate"):
        _assert_summary_grain(body)


@pytest.mark.parametrize("storage", ["ASC", "DESC"])
def test_tied_ranks_are_ordered_by_slug_on_both_summary_routes(
    snapshot_path: str, settings: ApiSettings, storage: str
) -> None:
    """A dense rank can tie (real 2016 has four candidates at rank 4); slug breaks it.

    The table is rebuilt without its key and filled in each slug order in turn, so an
    order that leaned on storage, whichever way SQLite's sort then returns ties, fails
    one of the two cases.
    """
    _doctor(
        snapshot_path,
        "UPDATE national_rollup SET president_electoral_rank = 1 WHERE year = 2020",
        "CREATE TABLE nr_copy AS SELECT * FROM national_rollup "
        f"ORDER BY year, candidate_slug {storage}",
        "DROP TABLE national_rollup",
        "ALTER TABLE nr_copy RENAME TO national_rollup",
    )
    with TestClient(create_app(settings)) as c:
        per_year = c.get("/v1/elections/2020/summary").json()["data"]
        every = c.get("/v1/elections/summary").json()["data"]
    assert [r["candidate_slug"] for r in per_year] == ["cand-a", "cand-b"]
    assert [r["candidate_slug"] for r in every if r["year"] == 2020] == [
        "cand-a",
        "cand-b",
    ]


def test_the_elections_list_is_oldest_first_whatever_the_storage_order(
    snapshot_path: str, settings: ApiSettings
) -> None:
    """``elections`` is ordered by the query, not by the table's key (#431).

    ``hybrid_summary`` is keyed by ``year``, so a plain scan already returns years in
    order; the copy here has no key and stores them newest first.
    """
    _doctor(
        snapshot_path,
        "CREATE TABLE hs_rev AS SELECT * FROM hybrid_summary ORDER BY year DESC",
        "DROP TABLE hybrid_summary",
        "ALTER TABLE hs_rev RENAME TO hybrid_summary",
    )
    with TestClient(create_app(settings)) as c:
        body = c.get("/v1/elections/summary").json()
    assert [e["year"] for e in body["elections"]] == _EXPECTED_SUMMARY_YEARS


def test_all_summaries_fail_loud_on_a_year_without_its_comparison(
    snapshot_path: str, settings: ApiSettings
) -> None:
    """A roll-up year with no hybrid row is a 500 here, while the per-year route stays
    200 with ``election: null`` (the deliberate divergence, D094)."""
    _doctor(snapshot_path, "DELETE FROM hybrid_summary WHERE year = 2016")
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        assert c.get("/v1/elections/summary").status_code == 500
        per_year = c.get("/v1/elections/2016/summary")
        assert per_year.status_code == 200
        assert per_year.json()["election"] is None


def test_all_summaries_fail_loud_on_a_comparison_without_its_year(
    snapshot_path: str, settings: ApiSettings
) -> None:
    """The other direction: a hybrid year with no roll-up rows is a 500 too."""
    _doctor(snapshot_path, "DELETE FROM national_rollup WHERE year = 2016")
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        assert c.get("/v1/elections/summary").status_code == 500


def test_the_repository_names_both_directions_of_a_year_mismatch(
    snapshot_path: str,
) -> None:
    repo = _doctor(snapshot_path, "DELETE FROM hybrid_summary WHERE year = 2016")
    with pytest.raises(SnapshotError, match=r"roll-up only \[2016\], summary only \[\]"):
        repo.national_summary_all()


def test_all_summaries_read_under_the_row_cap(
    settings: ApiSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unscoped read goes through the capped select: a cap below 6 rows is a 500."""
    monkeypatch.setattr("usvote.api.repository.MAX_ROWS", 5, raising=True)
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        assert c.get("/v1/elections/summary").status_code == 500
        assert c.get("/v1/elections/2020/summary").status_code == 200


# --- one state --------------------------------------------------------------


def test_get_state_across_years(client: TestClient) -> None:
    body = client.get("/v1/states/CA").json()
    assert {r["state_usps"] for r in body["data"]} == {"CA"}
    assert {r["year"] for r in body["data"]} == {1860, 2016, 2020}
    assert body["meta"]["count"] == 6


def test_get_state_is_case_insensitive(client: TestClient) -> None:
    assert client.get("/v1/states/ca").json()["meta"]["count"] == 6


def test_get_state_year_window(client: TestClient) -> None:
    body = client.get("/v1/states/CA", params={"year_from": 2020}).json()
    assert {r["year"] for r in body["data"]} == {2020}


def test_get_state_unknown_404(client: TestClient) -> None:
    resp = client.get("/v1/states/ZZ")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "state_not_found"


# --- one candidate ----------------------------------------------------------


def test_get_candidate_across_years(client: TestClient) -> None:
    body = client.get("/v1/candidates/cand-b").json()
    assert {r["candidate_slug"] for r in body["data"]} == {"cand-b"}
    assert body["meta"]["count"] == 4


def test_get_candidate_unknown_404(client: TestClient) -> None:
    resp = client.get("/v1/candidates/nobody")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "candidate_not_found"


# --- candidate index (#330) -------------------------------------------------

#: The index the fixture frame must produce, written out by hand from
#: ``tests/fixtures/api_snapshot.py`` rather than re-queried from the snapshot: a test
#: that recomputed it from ``ec_pv`` would re-encode the code under test and agree with
#: it when both drifted. ``cand-d`` 1860 is 8 votes cast and 0 counted (the 1872
#: Greeley shape), so the cast basis of ``years`` is exercised.
_EXPECTED_CANDIDATE_INDEX = [
    {"candidate_slug": "cand-a", "candidate": "Cand A", "years": [2016, 2020]},
    {"candidate_slug": "cand-b", "candidate": "Cand B", "years": [2016, 2020]},
    {"candidate_slug": "cand-d", "candidate": "Cand D", "years": [1860]},
    {"candidate_slug": "john-bell", "candidate": "John Bell", "years": [1860]},
]


def test_candidate_index_lists_every_candidate_once(client: TestClient) -> None:
    """Slug order, oldest year first, one item per candidate, exactly three fields."""
    body = client.get("/v1/candidates").json()
    assert body["data"] == _EXPECTED_CANDIDATE_INDEX
    assert body["meta"]["count"] == len(body["data"])


def test_candidate_index_matches_the_by_slug_route_both_ways(client: TestClient) -> None:
    """AC4: the listed slugs are exactly those ``/v1/candidates/{slug}`` answers 200 for.

    "Exactly" holds over canonical lowercase slugs: the by-slug route lowercases its
    input, so ``CAND-A`` answers 200 without being listed (asserted below). One
    direction: the listed slugs equal the hand-written oracle's, and each answers 200.
    The other: a well-formed slug that is not a candidate answers 404.
    """
    listed = [item["candidate_slug"] for item in client.get("/v1/candidates").json()["data"]]
    assert listed == [item["candidate_slug"] for item in _EXPECTED_CANDIDATE_INDEX]
    for slug in listed:
        assert client.get(f"/v1/candidates/{slug}").status_code == 200, slug
    assert "cand-e" not in listed
    assert client.get("/v1/candidates/cand-e").status_code == 404
    assert "CAND-A" not in listed
    upper = client.get("/v1/candidates/CAND-A")
    assert upper.status_code == 200
    # Same rows, not merely a 200: the published text says the route ignores case.
    lower_rows = client.get("/v1/candidates/cand-a").json()["data"]
    assert lower_rows
    assert upper.json()["data"] == lower_rows


def test_candidate_index_years_are_the_by_slug_years(client: TestClient) -> None:
    """Each item's years are exactly the years the by-slug route returns rows for.

    Read off the by-slug route, a different query from the index's. The cast-vote
    loop is a sanity check on the fixture, not on ``list_candidates``, which applies
    no cast filter: it confirms the test data holds no candidate-year with zero votes
    cast. The cast basis of ``years`` is pinned by ``cand-d`` 1860 (8 cast, 0 counted)
    in ``_EXPECTED_CANDIDATE_INDEX``; in production the "at least one electoral vote
    cast" wording rests on the EC-spine invariant that #373 will guard at build time.
    """
    for item in client.get("/v1/candidates").json()["data"]:
        rows = client.get(f"/v1/candidates/{item['candidate_slug']}").json()["data"]
        assert item["years"] == sorted({r["year"] for r in rows})
        for year in item["years"]:
            cast = sum(r["electoral_votes"] for r in rows if r["year"] == year)
            assert cast > 0, (item["candidate_slug"], year)


def test_candidate_index_agrees_with_the_build_time_counts(client: TestClient) -> None:
    """Cross-table checks that do not go through the index's own SQL.

    ``/v1/meta``'s ``candidate_count`` is counted when the snapshot is built, and
    ``/v1/elections`` counts candidates per year from the national roll-up table.
    """
    index = client.get("/v1/candidates").json()
    meta = client.get("/v1/meta").json()
    assert index["meta"]["count"] == meta["candidate_count"]
    per_year = client.get("/v1/elections").json()["data"]
    assert sum(len(i["years"]) for i in index["data"]) == sum(
        y["candidate_count"] for y in per_year
    )


def test_candidate_index_carries_the_snapshot_etag(client: TestClient) -> None:
    resp = client.get("/v1/candidates")
    assert resp.headers["cache-control"].startswith("public, max-age=3600")
    assert resp.headers["etag"] == client.get("/v1/elections").headers["etag"]
    again = client.get("/v1/candidates", headers={"If-None-Match": resp.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""


def _doctor(snapshot_path: str, *statements: str) -> SnapshotRepository:
    """Edit a built fixture snapshot, then open it.

    The build refuses a slug carrying two names, derives every slug from its name, and
    writes rows in year order, so it cannot produce the shapes these tests need (one
    slug with two names; a name its slug is not derived from; rows stored out of year
    order). The file is edited after the build to reach them.
    """
    conn = sqlite3.connect(snapshot_path)
    try:
        with conn:
            for statement in statements:
                conn.execute(statement)
    finally:
        conn.close()
    return SnapshotRepository.open(snapshot_path)


def test_candidate_index_fails_loud_on_a_slug_with_two_names(snapshot_path: str) -> None:
    """One slug carrying two display names raises, never a duplicate or a silent pick.

    The build refuses such a frame (``add_candidate_slug``). The edit touches ``ec_pv``
    only, so this is also the test that fails if ``list_candidates`` were moved to read
    ``national_rollup``: listing and existence must share ``ec_pv``.
    """
    repo = _doctor(
        snapshot_path,
        "UPDATE ec_pv SET candidate = 'Cand A Renamed' "
        "WHERE candidate_slug = 'cand-a' AND year = 2020",
    )
    with pytest.raises(SnapshotError, match="cand-a"):
        repo.list_candidates()


def test_candidate_index_is_ordered_by_slug_not_name(snapshot_path: str) -> None:
    """Items follow slug order even where display names sort differently.

    The fixture's names sort like their slugs, so ordering by name would pass every
    other test. Renaming every ``cand-a`` row to one name that sorts last separates
    the two orders without tripping the two-name guard.
    """
    repo = _doctor(
        snapshot_path, "UPDATE ec_pv SET candidate = 'Zed A' WHERE candidate_slug = 'cand-a'"
    )
    items = repo.list_candidates()
    assert [i["candidate_slug"] for i in items] == [
        "cand-a",
        "cand-b",
        "cand-d",
        "john-bell",
    ]
    assert items[0]["candidate"] == "Zed A"


def test_candidate_index_years_are_oldest_first_whatever_the_row_order(
    snapshot_path: str,
) -> None:
    """``years`` is sorted by the query, not by the order rows were written.

    The build writes rows in year order, so an index read with no year ordering could
    still return years ascending. Rewriting ``cand-a``'s 2016 rows after its 2020 rows
    reverses the storage order; the published "oldest first" must still hold.
    """
    repo = _doctor(
        snapshot_path,
        "CREATE TEMP TABLE moved AS "
        "SELECT * FROM ec_pv WHERE candidate_slug = 'cand-a' AND year = 2016",
        "DELETE FROM ec_pv WHERE candidate_slug = 'cand-a' AND year = 2016",
        "INSERT INTO ec_pv SELECT * FROM moved",
    )
    by_slug = {i["candidate_slug"]: i["years"] for i in repo.list_candidates()}
    assert by_slug["cand-a"] == [2016, 2020]


# --- validation (422) -------------------------------------------------------


def test_inverted_year_window_is_422(client: TestClient) -> None:
    resp = client.get("/v1/states/CA", params={"year_from": 2020, "year_to": 2016})
    assert resp.status_code == 422


def test_non_integer_year_path_is_422(client: TestClient) -> None:
    assert client.get("/v1/elections/notayear").status_code == 422


def test_non_integer_query_param_is_422(client: TestClient) -> None:
    resp = client.get("/v1/states/CA", params={"year_from": "abc"})
    assert resp.status_code == 422


# --- freshness / caching ----------------------------------------------------


def test_data_endpoint_carries_etag_and_cache_control(client: TestClient) -> None:
    resp = client.get("/v1/elections/2020")
    assert resp.headers["cache-control"].startswith("public, max-age=3600")
    assert resp.headers["etag"]


def test_conditional_get_304_on_existing_resource(client: TestClient) -> None:
    etag = client.get("/v1/elections/2020").headers["etag"]
    resp = client.get("/v1/elections/2020", headers={"If-None-Match": etag})
    assert resp.status_code == 304
    assert resp.content == b""


def test_conditional_get_unknown_year_is_404_not_304(client: TestClient) -> None:
    """A conditional GET to an unknown resource must 404, never 304 (architect note)."""
    etag = client.get("/v1/elections/2020").headers["etag"]
    resp = client.get("/v1/elections/1800", headers={"If-None-Match": etag})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "year_not_found"
    assert resp.headers["cache-control"] == "no-store"


# --- D006 / D030 guards -----------------------------------------------------


def test_no_endpoint_exposes_candidate_id(client: TestClient) -> None:
    for path in (
        "/v1/elections",
        "/v1/elections/2020",
        "/v1/elections/2020/summary",
        "/v1/elections/summary",
        "/v1/states/CA",
        "/v1/candidates",
        "/v1/candidates/cand-a",
    ):
        assert "candidate_id" not in client.get(path).text, path


# The "no served row is non-MIT" sweep now lives in test_api_redistributable_guard.py
# (full year/state/candidate sweep), superseding the old three-path spot-check here.


# --- server-side cap fails loud, never truncates ----------------------------


def test_row_cap_fails_loud(settings: ApiSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exceeding MAX_ROWS raises (500), never silently truncates."""
    monkeypatch.setattr("usvote.api.repository.MAX_ROWS", 1, raising=True)
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        resp = c.get("/v1/states/CA")  # 4 rows > cap of 1
        assert resp.status_code == 500


# --- per capita (#245) ------------------------------------------------------


def test_election_per_capita_returns_one_row_per_state(client: TestClient) -> None:
    body = client.get("/v1/elections/2020/per-capita").json()
    assert [r["state_usps"] for r in body["data"]] == ["CA", "TX"]  # ordered by state
    assert body["meta"]["count"] == 2
    ca = body["data"][0]
    # The fixture's 2020 California: 37,000,000 residents over 55 electoral votes, and
    # the allotment arrives under the same public name the election rows use.
    assert ca["state_electoral_votes"] == 55
    assert ca["population"] == 37_000_000
    assert ca["persons_per_electoral_vote"] == pytest.approx(37_000_000 / 55)
    assert ca["coverage"] == "covered"
    assert "total_electoral_votes" not in ca
    assert body["meta"]["provenance"]["census_source"] == "USCB"


def test_election_per_capita_nulls_are_explained_by_the_row(client: TestClient) -> None:
    """Neither NULL ratio is bare: each carries the operand that explains it."""
    rows = {
        r["state_usps"]: r
        for r in client.get("/v1/elections/1860/per-capita").json()["data"]
    }
    assert rows["NV"]["persons_per_electoral_vote"] is None
    assert rows["NV"]["state_electoral_votes"] == 0
    assert rows["VT"]["persons_per_electoral_vote"] is None
    assert rows["VT"]["population"] is None
    assert rows["VT"]["population_series"] is None
    assert rows["VT"]["coverage"] == "no_governing_figure"


def test_election_per_capita_state_filter(client: TestClient) -> None:
    body = client.get("/v1/elections/2020/per-capita", params={"state": "tx"}).json()
    assert [r["state_usps"] for r in body["data"]] == ["TX"]


def test_election_per_capita_empty_filter_is_200(client: TestClient) -> None:
    resp = client.get("/v1/elections/2020/per-capita", params={"state": "VT"})
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_election_per_capita_unknown_year_404(client: TestClient) -> None:
    resp = client.get("/v1/elections/1800/per-capita")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "year_not_found"
    assert "etag" not in resp.headers


def test_state_per_capita_across_years(client: TestClient) -> None:
    body = client.get("/v1/states/ca/per-capita").json()
    assert [r["year"] for r in body["data"]] == [1860, 2016, 2020]  # ordered by year
    assert {r["state_usps"] for r in body["data"]} == {"CA"}


def test_state_per_capita_year_window(client: TestClient) -> None:
    body = client.get("/v1/states/CA/per-capita", params={"year_to": 2016}).json()
    assert [r["year"] for r in body["data"]] == [1860, 2016]


def test_state_per_capita_unknown_404(client: TestClient) -> None:
    resp = client.get("/v1/states/ZZ/per-capita")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "state_not_found"


def test_state_per_capita_inverted_window_is_422(client: TestClient) -> None:
    resp = client.get(
        "/v1/states/CA/per-capita", params={"year_from": 2020, "year_to": 2016}
    )
    assert resp.status_code == 422


def test_per_capita_carries_the_snapshot_etag(client: TestClient) -> None:
    resp = client.get("/v1/elections/2020/per-capita")
    etag = resp.headers["etag"]
    assert etag == f'"{resp.json()["meta"]["provenance"]["snapshot_version"]}"'
    again = client.get("/v1/elections/2020/per-capita", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_per_capita_reads_order_explicitly(
    settings: ApiSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two per-capita reads carry their own ORDER BY.

    The ordering asserts above cannot show it: the build writes the table already
    sorted and the ``(year, state)`` primary key walks in that order, so a read with no
    ORDER BY returns the same rows in the same order today. Pinning the clause is what
    keeps the response order a contract rather than a property of the file.
    """
    from usvote.api.repository import SnapshotRepository

    seen: list[str] = []
    original = SnapshotRepository._select

    def spy(
        self: SnapshotRepository, sql: str, params: tuple[object, ...]
    ) -> list[dict[str, object]]:
        seen.append(sql)
        return original(self, sql, params)

    monkeypatch.setattr(SnapshotRepository, "_select", spy)
    repo = SnapshotRepository.open(str(settings.snapshot_path))
    repo.per_capita_by_year(2020)
    repo.per_capita_by_state("CA")
    assert seen[0].rstrip().endswith("ORDER BY state")
    assert seen[1].rstrip().endswith("ORDER BY year")
