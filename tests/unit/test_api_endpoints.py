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
    {"candidate_slug": "cand-c", "candidate": "Cand C", "years": [1860]},
    {"candidate_slug": "cand-d", "candidate": "Cand D", "years": [1860]},
]


def test_candidate_index_lists_every_candidate_once(client: TestClient) -> None:
    """Slug order, oldest year first, one item per candidate, exactly three fields."""
    body = client.get("/v1/candidates").json()
    assert body["data"] == _EXPECTED_CANDIDATE_INDEX
    assert body["meta"]["count"] == len(body["data"])


def test_candidate_index_matches_the_by_slug_route_both_ways(client: TestClient) -> None:
    """AC4: the listed slugs are exactly those ``/v1/candidates/{slug}`` answers 200 for.

    "Exactly" holds over canonical lowercase slugs: the by-slug route lowercases its
    input, so ``CAND-A`` also answers 200 without being listed. One direction: every
    listed slug answers 200. The other: every candidate in the fixture frame (the
    hand-written oracle, not the served index) answers 200 and is listed, and a
    well-formed slug that is not a candidate answers 404.
    """
    listed = [item["candidate_slug"] for item in client.get("/v1/candidates").json()["data"]]
    for slug in listed:
        assert client.get(f"/v1/candidates/{slug}").status_code == 200, slug
    expected = [item["candidate_slug"] for item in _EXPECTED_CANDIDATE_INDEX]
    for slug in expected:
        assert client.get(f"/v1/candidates/{slug}").status_code == 200, slug
    assert listed == expected
    assert "cand-e" not in listed
    assert client.get("/v1/candidates/cand-e").status_code == 404


def test_candidate_index_years_are_the_by_slug_years_with_votes_cast(
    client: TestClient,
) -> None:
    """Each listed year is a year the by-slug route returns rows for, with votes cast.

    Holds the published wording true: "the years `/v1/candidates/{slug}` returns rows
    for" and "at least one electoral vote cast" — read off the by-slug route, a
    different query from the index's.
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
        "/v1/states/CA",
        "/v1/candidates",
        "/v1/candidates/cand-a",
    ):
        assert "candidate_id" not in client.get(path).text, path


# The "no served row is non-MIT" sweep now lives in test_api_redistributable_guard.py
# (full year/state/candidate sweep), superseding the old three-path spot-check here.


# --- server-side cap fails loud, never truncates ----------------------------


def test_candidate_index_fails_loud_on_a_slug_with_two_names(snapshot_path: str) -> None:
    """One slug carrying two display names raises, never a duplicate or a silent pick.

    The build refuses such a frame (``add_candidate_slug``), so the file is doctored
    after the build to reach the repository's own failure branch.
    """
    conn = sqlite3.connect(snapshot_path)
    try:
        with conn:
            conn.execute(
                "UPDATE ec_pv SET candidate = 'Cand A Renamed' "
                "WHERE candidate_slug = 'cand-a' AND year = 2020"
            )
    finally:
        conn.close()
    repo = SnapshotRepository.open(snapshot_path)
    with pytest.raises(SnapshotError, match="cand-a"):
        repo.list_candidates()


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
