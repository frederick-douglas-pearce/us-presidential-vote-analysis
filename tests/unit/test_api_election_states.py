"""Unit tests for ``/v1/elections/states`` (#428, D098): every (year, state) in one response.

All offline, **no live DB** (D028): the shared synthetic frame is built into a real SQLite
snapshot (``tests/unit/conftest.py``), and a few tests edit the built file to reach
shapes the build refuses (``_doctor``). The route reads ``per_capita`` whole and
``ec_pv`` grouped to ``(year, state)`` (``SnapshotRepository.state_rows_all``), so the
checks here are of three kinds:

- **consistency with the per-year routes** — the shared fields equal
  ``/v1/elections/{year}/per-capita`` (AC2), and the two added fields equal the state's
  values on ``/v1/elections/{year}``;
- **independent reconciliation** — each year's electoral votes sum to the
  ``electoral_denominator`` of ``hybrid_summary`` and the in-window totals to the
  roll-up's ``national_pv_denominator`` (AC5), both computed by the build from ``ec_pv``
  by other code;
- **fail-loud twins** — two totals or two statuses in a state, and key sets that differ
  either way, are 500s while the per-year routes keep answering (D094(iii)).
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tests.fixtures.api_snapshot import api_snapshot_row, synthetic_ec_pv_frame
from usvote.api import create_app
from usvote.api.config import ApiSettings
from usvote.api.repository import SnapshotError, SnapshotRepository

_PATH = "/v1/elections/states"

#: The fixture's (year, state) keys in the served order, written by hand: year, then
#: state **name**. The fixture's four states sort the same by name and by USPS code, so
#: :func:`test_items_are_ordered_by_state_name_not_code` separates the two.
_EXPECTED_ORDER = [
    (1860, "California"),
    (1860, "Nevada"),
    (1860, "Texas"),
    (1860, "Vermont"),
    (2016, "California"),
    (2016, "Texas"),
    (2020, "California"),
    (2020, "Texas"),
]

#: The ``PerCapitaRow`` fields, which must equal the per-year per-capita route's.
_PER_CAPITA_FIELDS = (
    "year",
    "state",
    "state_usps",
    "governing_census_year",
    "state_electoral_votes",
    "population",
    "population_series",
    "boundary_basis",
    "coverage",
    "persons_per_electoral_vote",
)


def _doctor(snapshot_path: str, *statements: str) -> SnapshotRepository:
    """Edit a built fixture snapshot, then open it (the build refuses these shapes)."""
    conn = sqlite3.connect(snapshot_path)
    try:
        with conn:
            for statement in statements:
                conn.execute(statement)
    finally:
        conn.close()
    return SnapshotRepository.open(snapshot_path)


def _assert_state_grain(body: dict) -> None:
    """Exactly one item per ``(year, state)`` — the unscoped route's fan-out guard (D094)."""
    keys = [(r["year"], r["state"]) for r in body["data"]]
    assert len(keys) == len(set(keys)), f"duplicate (year, state) items: {keys}"


def _window(body: dict) -> tuple[int, int]:
    coverage = body["meta"]["provenance"]["coverage"]
    return coverage["pv_year_min"], coverage["pv_year_max"]


# --- shape, order, grain ----------------------------------------------------


def test_items_are_the_expected_keys_in_order(client: TestClient) -> None:
    body = client.get(_PATH).json()
    assert [(r["year"], r["state"]) for r in body["data"]] == _EXPECTED_ORDER
    assert body["meta"]["count"] == len(body["data"])
    assert body["meta"]["provenance"]["snapshot_version"]
    _assert_state_grain(body)


def test_the_envelope_names_all_three_sources(client: TestClient) -> None:
    """AC6: the Census Bureau (population), the Archives (electors) and MIT Election Lab
    (popular-vote fields), on the shared envelope, as the other data routes carry them."""
    body = client.get(_PATH).json()
    provenance = body["meta"]["provenance"]
    assert provenance["census_source"] == "USCB"
    assert provenance["ec_source"] == "NARA"
    assert provenance["source"] == "MIT"
    reference = client.get("/v1/elections/2020/per-capita").json()["meta"]["provenance"]
    assert provenance == reference


def test_the_state_grain_check_fires_on_a_duplicated_row(
    snapshot_path: str, settings: ApiSettings
) -> None:
    """The twin that proves ``_assert_state_grain`` can fail.

    ``per_capita`` is keyed by ``(year, state)``, so a duplicate needs a copy without the
    key. The repository's key-set check compares sets, so a duplicate passes it and only
    the grain check can see it.
    """
    _doctor(
        snapshot_path,
        "CREATE TABLE pc_nokey AS SELECT * FROM per_capita",
        "DROP TABLE per_capita",
        "ALTER TABLE pc_nokey RENAME TO per_capita",
        "INSERT INTO per_capita SELECT * FROM per_capita "
        "WHERE year = 2020 AND state = 'Texas'",
    )
    with TestClient(create_app(settings)) as c:
        body = c.get(_PATH).json()
    with pytest.raises(AssertionError, match="duplicate"):
        _assert_state_grain(body)


def test_items_are_ordered_by_state_name_not_code(
    snapshot_path: str, settings: ApiSettings
) -> None:
    """Within a year, items follow ``state`` (the name), as the per-capita route does.

    California's code is moved to sort last, in both tables, so an order by code would
    put it after Texas; the published order, and the per-year identity, must still hold.
    """
    _doctor(
        snapshot_path,
        "UPDATE per_capita SET state_usps = 'ZZ' WHERE state = 'California'",
        "UPDATE ec_pv SET state_usps = 'ZZ' WHERE state = 'California'",
    )
    with TestClient(create_app(settings)) as c:
        body = c.get(_PATH).json()
        per_year = c.get("/v1/elections/2020/per-capita").json()["data"]
    in_2020 = [r for r in body["data"] if r["year"] == 2020]
    assert [r["state"] for r in in_2020] == ["California", "Texas"]
    assert in_2020[0]["state_usps"] == "ZZ"
    assert [{k: r[k] for k in _PER_CAPITA_FIELDS} for r in in_2020] == per_year


def test_items_cover_exactly_the_listed_years(client: TestClient) -> None:
    body = client.get(_PATH).json()
    listed = {item["year"] for item in client.get("/v1/elections").json()["data"]}
    assert {r["year"] for r in body["data"]} == listed


def test_the_fixture_is_not_vacuous(client: TestClient) -> None:
    """The loops below need several years, one outside the window, and every status."""
    body = client.get(_PATH).json()
    lo, hi = _window(body)
    years = {r["year"] for r in body["data"]}
    assert len(years) >= 2
    assert any(lo <= y <= hi for y in years)
    assert any(not lo <= y <= hi for y in years)
    assert {r["pv_status"] for r in body["data"]} == {
        "popular_vote",
        "legislature_chosen",
        "not_participating",
    }


def test_a_state_that_took_no_part_has_an_item(client: TestClient) -> None:
    """The docstring's claim: a ``not_participating`` state is an item (1860 Nevada)."""
    by_key = {(r["year"], r["state"]): r for r in client.get(_PATH).json()["data"]}
    nevada = by_key[(1860, "Nevada")]
    assert nevada["pv_status"] == "not_participating"
    assert nevada["state_electoral_votes"] == 0
    assert by_key[(1860, "Vermont")]["pv_status"] == "legislature_chosen"


# --- consistency with the per-year routes -----------------------------------


def test_the_per_capita_fields_equal_each_per_year_route(client: TestClient) -> None:
    """For every served year, the shared fields equal ``/per-capita``'s, in order (AC2)."""
    body = client.get(_PATH).json()
    years = [item["year"] for item in client.get("/v1/elections").json()["data"]]
    assert years
    for year in years:
        per_year = client.get(f"/v1/elections/{year}/per-capita").json()["data"]
        mine = [r for r in body["data"] if r["year"] == year]
        assert [{k: r[k] for k in _PER_CAPITA_FIELDS} for r in mine] == per_year, year


def test_the_popular_vote_fields_equal_the_state_rows_of_each_year(
    client: TestClient,
) -> None:
    """Each item's total is its state's one non-null total on ``/v1/elections/{year}``,
    or null where there is none; its status is the status on every one of those rows."""
    for item in client.get(_PATH).json()["data"]:
        rows = client.get(
            f"/v1/elections/{item['year']}", params={"state": item["state_usps"]}
        ).json()["data"]
        assert rows, item
        totals = {r["state_popular_total"] for r in rows} - {None}
        assert totals == (
            set() if item["state_popular_total"] is None else {item["state_popular_total"]}
        ), item
        assert {r["pv_status"] for r in rows} == {item["pv_status"]}, item


def test_popular_votes_are_null_exactly_where_the_state_total_is(
    client: TestClient,
) -> None:
    """The field description's claim about ``/v1/elections/{year}`` rows (ba claim 8):
    the total is null on a candidate row exactly when that row has no popular votes."""
    for year in (1860, 2016, 2020):
        for row in client.get(f"/v1/elections/{year}").json()["data"]:
            assert (row["popular_votes"] is None) == (
                row["state_popular_total"] is None
            ), row


def test_candidates_popular_votes_never_exceed_the_state_total(
    client: TestClient,
) -> None:
    for item in client.get(_PATH).json()["data"]:
        if item["state_popular_total"] is None:
            continue
        rows = client.get(
            f"/v1/elections/{item['year']}", params={"state": item["state_usps"]}
        ).json()["data"]
        votes = sum(r["popular_votes"] or 0 for r in rows)
        assert votes <= item["state_popular_total"], item


# --- reconciliation against independently built figures (AC5) ----------------


def test_each_years_electoral_votes_sum_to_its_denominator(client: TestClient) -> None:
    body = client.get(_PATH).json()
    for year in sorted({r["year"] for r in body["data"]}):
        expected = client.get(f"/v1/elections/{year}/summary").json()["election"][
            "electoral_denominator"
        ]
        got = sum(r["state_electoral_votes"] for r in body["data"] if r["year"] == year)
        assert got == expected, year


def test_in_window_totals_sum_to_the_national_denominator(client: TestClient) -> None:
    body = client.get(_PATH).json()
    lo, hi = _window(body)
    checked = 0
    for year in sorted({r["year"] for r in body["data"]}):
        if not lo <= year <= hi:
            continue
        rows = client.get(f"/v1/elections/{year}/summary").json()["data"]
        expected = {r["national_pv_denominator"] for r in rows}
        assert len(expected) == 1, year
        got = sum(r["state_popular_total"] for r in body["data"] if r["year"] == year)
        assert {got} == expected, year
        checked += 1
    assert checked >= 2


def test_every_item_outside_the_window_has_a_null_total(client: TestClient) -> None:
    body = client.get(_PATH).json()
    lo, hi = _window(body)
    outside = [r for r in body["data"] if not lo <= r["year"] <= hi]
    assert outside
    assert all(r["state_popular_total"] is None for r in outside)


# --- caching, parameters, routing -------------------------------------------


def test_the_route_carries_the_snapshot_etag(client: TestClient) -> None:
    resp = client.get(_PATH)
    assert resp.status_code == 200
    reference = client.get("/v1/elections/2020/per-capita")
    assert resp.headers["etag"] == reference.headers["etag"]
    assert resp.headers["cache-control"] == reference.headers["cache-control"]
    again = client.get(_PATH, headers={"If-None-Match": resp.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""


def test_an_unknown_query_parameter_is_ignored(client: TestClient) -> None:
    plain = client.get(_PATH)
    odd = client.get(_PATH, params={"state": "TX", "year": 2020})
    assert odd.status_code == 200
    assert odd.json() == plain.json()


def test_the_literal_path_does_not_shadow_or_get_shadowed_by_the_year_path(
    client: TestClient,
) -> None:
    """``/elections/states`` is declared before ``/elections/{year}`` (D094(ii), D098)."""
    assert client.get(_PATH).status_code == 200
    assert client.get("/v1/elections/2020").status_code == 200
    assert client.get("/v1/elections/2020/per-capita").status_code == 200
    assert client.get("/v1/elections/summary").status_code == 200
    assert client.get("/v1/elections/abc").status_code == 422


def test_the_route_is_a_500_over_the_row_cap(
    settings: ApiSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Over the cap the route fails loud (a 500), and the per-year route still answers."""
    monkeypatch.setattr("usvote.api.repository.MAX_ROWS", 7, raising=True)
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        assert c.get(_PATH).status_code == 500
        assert c.get("/v1/elections/2020/per-capita").status_code == 200


def test_the_per_capita_read_goes_through_the_row_cap(
    snapshot_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``per_capita``'s 8 rows trip a cap of 7 in its own read, the first of the two."""
    repo = SnapshotRepository.open(snapshot_path)
    monkeypatch.setattr("usvote.api.repository.MAX_ROWS", 7, raising=True)
    with pytest.raises(SnapshotError, match=r"7-row cap.*FROM per_capita"):
        repo.state_rows_all()


def test_the_grouped_ec_pv_read_goes_through_the_row_cap(
    snapshot_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second read is capped too, not only the first.

    With one ``per_capita`` row removed that read returns 7 and passes a cap of 7, so
    the read that trips it is ``ec_pv`` grouped to its 8 ``(year, state)`` keys, before
    the key-set check would have refused the mismatch.
    """
    repo = _doctor(
        snapshot_path, "DELETE FROM per_capita WHERE year = 2020 AND state = 'Texas'"
    )
    monkeypatch.setattr("usvote.api.repository.MAX_ROWS", 7, raising=True)
    with pytest.raises(SnapshotError, match=r"7-row cap.*FROM ec_pv"):
        repo.state_rows_all()


# --- fail loud: one total and one status per state ---------------------------


def test_two_totals_in_one_state_are_a_500(
    snapshot_path: str, settings: ApiSettings
) -> None:
    repo = _doctor(
        snapshot_path,
        "UPDATE ec_pv SET state_total_votes = 1 "
        "WHERE year = 2020 AND state = 'Texas' AND candidate_slug = 'cand-a'",
    )
    with pytest.raises(SnapshotError, match=r"2 popular-vote totals .*2020, 'Texas'"):
        repo.state_rows_all()
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        assert c.get(_PATH).status_code == 500
        assert c.get("/v1/elections/2020/per-capita").status_code == 200


def test_two_statuses_in_one_state_are_a_500(
    snapshot_path: str, settings: ApiSettings
) -> None:
    repo = _doctor(
        snapshot_path,
        "UPDATE ec_pv SET pv_status = 'legislature_chosen' "
        "WHERE year = 1860 AND state = 'Texas' AND candidate_slug = 'cand-d'",
    )
    with pytest.raises(SnapshotError, match=r"2 popular-vote statuses .*1860, 'Texas'"):
        repo.state_rows_all()
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        assert c.get(_PATH).status_code == 500
        assert c.get("/v1/elections/1860").status_code == 200


def test_a_per_capita_key_missing_from_ec_pv_is_a_500(
    snapshot_path: str, settings: ApiSettings
) -> None:
    """A ``per_capita`` row with no ``ec_pv`` state: 500 here, the per-year routes 200."""
    repo = _doctor(
        snapshot_path,
        "INSERT INTO per_capita SELECT year, 'Utah', 'UT', governing_census_year, "
        "total_electoral_votes, population, population_series, boundary_basis, "
        "coverage, persons_per_electoral_vote FROM per_capita "
        "WHERE year = 2020 AND state = 'Texas'",
    )
    with pytest.raises(SnapshotError, match=r"per_capita only \[\(2020, 'Utah'\)\]"):
        repo.state_rows_all()
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        assert c.get(_PATH).status_code == 500
        assert c.get("/v1/elections/2020/per-capita").status_code == 200
        assert c.get("/v1/elections/2020").status_code == 200


def test_key_sets_of_equal_size_that_differ_are_a_500(
    snapshot_path: str, settings: ApiSettings
) -> None:
    """The check compares the keys, not how many there are.

    Relabeling ``per_capita``'s 2020 Texas row as Utah keeps both tables at 8 keys, so a
    count check would pass it; each table now holds one key the other lacks.
    """
    repo = _doctor(
        snapshot_path,
        "UPDATE per_capita SET state = 'Utah', state_usps = 'UT' "
        "WHERE year = 2020 AND state = 'Texas'",
    )
    with pytest.raises(
        SnapshotError,
        match=r"per_capita only \[\(2020, 'Utah'\)\], ec_pv only \[\(2020, 'Texas'\)\]",
    ):
        repo.state_rows_all()
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        assert c.get(_PATH).status_code == 500
        assert c.get("/v1/elections/2020").status_code == 200


def test_an_ec_pv_key_missing_from_per_capita_is_a_500(
    snapshot_path: str, settings: ApiSettings
) -> None:
    """The other direction: an ``ec_pv`` state with no ``per_capita`` row."""
    repo = _doctor(
        snapshot_path, "DELETE FROM per_capita WHERE year = 2020 AND state = 'Texas'"
    )
    with pytest.raises(SnapshotError, match=r"ec_pv only \[\(2020, 'Texas'\)\]"):
        repo.state_rows_all()
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        assert c.get(_PATH).status_code == 500
        assert c.get("/v1/elections/2020/per-capita").status_code == 200
        assert c.get("/v1/elections/2020").status_code == 200


# --- a candidate with no popular-vote figure (the faithless-elector shape) ----


def _with_a_faithless_getter() -> pd.DataFrame:
    """The canonical frame with one 2016 Texas elector moved from Cand A to Cand F.

    Cand F has no popular-vote figure, so the EC-left join gives it a dense row in both
    2016 states with NULL ``candidate_votes`` and NULL ``state_total_votes``, beside each
    state's real total — the shape every state has in 1976, 1988, 2004 and 2016 on the
    real snapshot (D098(b)). Local to this module: the canonical fixture feeds ordering,
    count and ETag assertions elsewhere.
    """
    frame = synthetic_ec_pv_frame()
    cand_a_2016 = (frame["year"] == 2016) & (frame["candidate"] == "Cand A")
    frame.loc[cand_a_2016, ["national_electoral_votes"]] = 37
    frame.loc[cand_a_2016, ["national_counted_electoral_votes"]] = 37
    texas_a = cand_a_2016 & (frame["state"] == "Texas")
    frame.loc[texas_a, ["president_electoral_votes"]] = 37
    frame.loc[texas_a, ["president_electoral_votes_counted"]] = 37
    getter = [
        api_snapshot_row(
            year=2016, state=state, candidate_id=9, candidate="Cand F",
            president_ev=ev, national_ev=1, rank=3, took_office=False,
            candidate_votes=None, state_total=None, total_ev=total_ev,
            source=None, reliability=None,
        )
        for state, ev, total_ev in (("Texas", 1, 38), ("California", 0, 55))
    ]  # fmt: skip
    return pd.concat([frame, pd.DataFrame(getter)], ignore_index=True)


class TestAFaithlessGetter:
    @pytest.fixture
    def synthetic_frame(self) -> pd.DataFrame:
        return _with_a_faithless_getter()

    def test_the_fixture_has_the_null_total_shape(self, client: TestClient) -> None:
        rows = client.get("/v1/elections/2016", params={"state": "TX"}).json()["data"]
        totals = [r["state_popular_total"] for r in rows]
        assert None in totals
        assert 14_000_000 in totals

    def test_the_state_total_is_the_one_non_null_value(self, client: TestClient) -> None:
        by_key = {(r["year"], r["state"]): r for r in client.get(_PATH).json()["data"]}
        assert by_key[(2016, "Texas")]["state_popular_total"] == 14_000_000
        assert by_key[(2016, "California")]["state_popular_total"] == 17_000_000
        assert by_key[(2016, "Texas")]["pv_status"] == "popular_vote"

    def test_the_sums_still_reconcile(self, client: TestClient) -> None:
        body = client.get(_PATH).json()
        summary = client.get("/v1/elections/2016/summary").json()
        in_2016 = [r for r in body["data"] if r["year"] == 2016]
        assert sum(r["state_electoral_votes"] for r in in_2016) == summary["election"][
            "electoral_denominator"
        ]
        assert {sum(r["state_popular_total"] for r in in_2016)} == {
            r["national_pv_denominator"] for r in summary["data"]
        }

    def test_popular_votes_are_null_exactly_where_the_state_total_is(
        self, client: TestClient
    ) -> None:
        rows = client.get("/v1/elections/2016").json()["data"]
        assert any(r["popular_votes"] is None for r in rows)
        for row in rows:
            assert (row["popular_votes"] is None) == (
                row["state_popular_total"] is None
            ), row
