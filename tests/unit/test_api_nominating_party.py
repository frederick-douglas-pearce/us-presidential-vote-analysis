"""The nominating party on the public API (#386, D077).

Three fields, ``nominating_party``, ``nominating_party_source`` and
``nominating_party_note``, on every state row (``/v1/elections/{year}``,
``/v1/states/{usps}``, ``/v1/candidates/{slug}``) and every national summary row
(``/v1/elections/{year}`` and ``/summary``), and nowhere else. A candidate-year the
dataset holds no party for is served ``null`` in all three, never ``no_nomination``.

Served from the shared synthetic snapshot (``tests/fixtures/api_snapshot.py``): 2016 and
2020 Cand A/B are Archives rows, 1860 John Bell is the curated row (the real catalog
entry, #387), and 1860 Cand D (8 votes cast) is not keyed — the pre-1976 case. The 1976-on
cases, faithless electors' choices, get their own small frame below
(:class:`TestFaithlessRecipient`), so the shared fixture's counts stay as the other API
tests pin them: an unkeyed one, served null, and 2016 Colin Powell, the real catalog's
``no_nomination`` row (#388), served with its value, source and note.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tests.fixtures.api_snapshot import (
    FIXTURE_CURATED_ROW,
    api_snapshot_row,
    synthetic_ec_pv_frame,
)
from usvote.party import NOTE_COLUMN, PARTY_COLUMN, SOURCE_COLUMN, SOURCE_CURATED
from usvote.party_catalog import CURATED_BY_KEY, WASHINGTON_2016_NOTE

#: The real catalog's 2016 Colin Powell row, a ``no_nomination`` row (#388).
_POWELL = CURATED_BY_KEY[(2016, "Colin Powell")]

_FIELDS = ("nominating_party", "nominating_party_source", "nominating_party_note")


def _by_candidate(rows: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    found = [row for row in rows if row["candidate"] == name]
    assert found, name
    return found


def _assert_party(
    row: dict[str, Any], value: str | None, note: str | None, source: str = "NARA"
) -> None:
    assert row["nominating_party"] == value, row
    assert row["nominating_party_source"] == (source if value else None), row
    assert row["nominating_party_note"] == note, row


class TestEveryRowEndpointServesIt:
    """AC1/AC2 on the synthetic snapshot: a keyed candidate-year carries its party on
    every endpoint that serves its rows; an unkeyed one carries null on each."""

    def test_the_year_endpoint_rows_and_summary(self, client: TestClient) -> None:
        body = client.get("/v1/elections/2016").json()
        for row in _by_candidate(body["data"], "Cand A"):
            _assert_party(row, "republican", None)
        for row in _by_candidate(body["summary"], "Cand B"):
            _assert_party(row, "democratic", None)

    def test_the_summary_endpoint(self, client: TestClient) -> None:
        rows = client.get("/v1/elections/2020/summary").json()["data"]
        _assert_party(_by_candidate(rows, "Cand A")[0], "republican", None)
        _assert_party(_by_candidate(rows, "Cand B")[0], "democratic", None)

    def test_the_state_endpoint(self, client: TestClient) -> None:
        rows = client.get("/v1/states/TX").json()["data"]
        for row in _by_candidate(rows, "Cand B"):
            _assert_party(row, "democratic", None)

    def test_the_candidate_endpoint(self, client: TestClient) -> None:
        rows = client.get("/v1/candidates/cand-a").json()["data"]
        assert {row["year"] for row in rows} == {2016, 2020}
        for row in rows:
            _assert_party(row, "republican", None)

    def test_a_curated_row_serves_its_value_note_and_source(
        self, client: TestClient
    ) -> None:
        """1860 John Bell: the catalog's value and note, with source ``USGOV`` (#387)."""
        rows = client.get("/v1/candidates/john-bell").json()["data"]
        assert rows
        for row in rows:
            _assert_party(row, "constitutional_union", FIXTURE_CURATED_ROW.note, "USGOV")
        assert FIXTURE_CURATED_ROW.note

    def test_a_pre_1976_candidate_with_no_party_row_is_null(
        self, client: TestClient
    ) -> None:
        """1860 Cand D: votes cast, no party row, so null on all four endpoints."""
        year = client.get("/v1/elections/1860").json()
        served = (
            _by_candidate(year["data"], "Cand D")
            + _by_candidate(year["summary"], "Cand D")
            + _by_candidate(
                client.get("/v1/elections/1860/summary").json()["data"], "Cand D"
            )
            + _by_candidate(client.get("/v1/states/CA").json()["data"], "Cand D")
            + client.get("/v1/candidates/cand-d").json()["data"]
        )
        for row in served:
            for field in _FIELDS:
                assert row[field] is None, (field, row)

    def test_null_never_stands_in_for_no_nomination(self, client: TestClient) -> None:
        values = {
            row["nominating_party"]
            for row in client.get("/v1/elections/1860").json()["data"]
        }
        assert values == {"constitutional_union", None}


class TestWhereItIsNotServed:
    def test_not_on_the_candidate_index(self, client: TestClient) -> None:
        for item in client.get("/v1/candidates").json()["data"]:
            assert not set(_FIELDS) & set(item), item

    def test_not_on_the_election_block(self, client: TestClient) -> None:
        election = client.get("/v1/elections/2016").json()["election"]
        assert not set(_FIELDS) & set(election), election


class TestTheCuratedProvenancePair:
    """``meta.provenance`` and ``/health`` name the curated pair (#386, D077), always,
    whether or not a curated row exists yet."""

    def test_on_meta_provenance(self, client: TestClient) -> None:
        prov = client.get("/v1/meta").json()["provenance"]
        assert prov["usgov_source"] == "USGOV"
        assert prov["usgov_source_name"] == "U.S. Government publications"
        assert prov["usgov_license"] == "US-PD"
        assert prov["usgov_license_url"] == "https://www.usa.gov/government-works"
        assert "`nominating_party_source` is `USGOV`" in prov["redistributable_note"]

    def test_on_every_data_response_too(self, client: TestClient) -> None:
        prov = client.get("/v1/elections/2016").json()["meta"]["provenance"]
        assert prov["usgov_source"] == "USGOV"

    def test_on_health(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert body["usgov_source"] == "USGOV"
        assert body["usgov_license"] == "US-PD"


def _faithless_frame() -> pd.DataFrame:
    """The shared frame plus two 2016 faithless electors' choices.

    Three Texas electors pledged to Cand A vote otherwise: one for ``Cand F``, two for
    ``Colin Powell``. So A's Texas votes drop 38 → 35 (national 38 → 35); F gets 1 and
    Powell 2 there, each 0 in California. Neither has a popular vote. Cand F has no
    party row, so it is served null. Colin Powell carries the real catalog's
    ``no_nomination`` row (#388): only his key, value, source and note are real; his
    states and votes are synthetic, as 1860 John Bell's are. The build's keyed catalog
    pin runs over him but cannot fail here, since his values are copied from the
    catalog: the test's own literals are what would catch a wrong value or note. Same ``(year, state)`` pairs as the shared frame, so its roster and
    per-capita companions still fit.
    """
    frame = synthetic_ec_pv_frame()
    a_2016 = (frame["year"] == 2016) & (frame["candidate"] == "Cand A")
    frame.loc[a_2016, "national_electoral_votes"] = 35
    frame.loc[a_2016, "national_counted_electoral_votes"] = 35
    a_tx = a_2016 & (frame["state"] == "Texas")
    counted = ["president_electoral_votes", "president_electoral_votes_counted"]
    frame.loc[a_tx, counted] = 35
    faithless = [
        api_snapshot_row(
            year=2016, state=state, candidate_id=cid, candidate=name,
            president_ev=ev if state == "Texas" else 0, national_ev=ev, rank=rank,
            took_office=False, candidate_votes=None, state_total=None, total_ev=total,
            source=None, party=None, reliability=None, redistributable=None,
        )
        for cid, name, ev, rank in ((9, "Cand F", 1, 4), (10, _POWELL.name, 2, 3))
        for state, total in (("Texas", 38), ("California", 55))
    ]
    out = pd.concat([frame, pd.DataFrame(faithless)], ignore_index=True)
    powell = out["candidate"] == _POWELL.name
    out.loc[powell, [PARTY_COLUMN, SOURCE_COLUMN, NOTE_COLUMN]] = [
        _POWELL.party, SOURCE_CURATED, _POWELL.note,
    ]
    return out


class TestFaithlessRecipient:
    """AC2's 1976-on case (#386): a faithless elector's choice with no party row is
    null. #388's AC3: a catalog ``no_nomination`` row serves that closed value, and it
    differs from the null on every field and endpoint."""

    @pytest.fixture
    def synthetic_frame(self) -> pd.DataFrame:
        return _faithless_frame()

    def test_null_on_every_endpoint(self, client: TestClient) -> None:
        year = client.get("/v1/elections/2016").json()
        served = (
            _by_candidate(year["data"], "Cand F")
            + _by_candidate(year["summary"], "Cand F")
            + _by_candidate(
                client.get("/v1/elections/2016/summary").json()["data"], "Cand F"
            )
            + _by_candidate(client.get("/v1/states/TX").json()["data"], "Cand F")
            + client.get("/v1/candidates/cand-f").json()["data"]
        )
        # Two state rows + two summaries + the Texas row + the two candidate rows.
        assert len(served) == 7
        for row in served:
            for field in _FIELDS:
                assert row[field] is None, (field, row)

    def test_a_no_nomination_row_serves_its_value_unlike_a_null(
        self, client: TestClient
    ) -> None:
        year = client.get("/v1/elections/2016").json()
        served = (
            _by_candidate(year["data"], "Colin Powell")
            + _by_candidate(year["summary"], "Colin Powell")
            + _by_candidate(
                client.get("/v1/elections/2016/summary").json()["data"], "Colin Powell"
            )
            + _by_candidate(client.get("/v1/states/TX").json()["data"], "Colin Powell")
            + client.get("/v1/candidates/colin-powell").json()["data"]
        )
        assert len(served) == 7
        for row in served:
            assert row["nominating_party"] == "no_nomination", row
            assert row["nominating_party_source"] == "USGOV", row
            assert row["nominating_party_note"] == WASHINGTON_2016_NOTE, row
        unkeyed = _by_candidate(year["data"], "Cand F")
        assert {r["nominating_party"] for r in unkeyed} == {None}

    def test_the_other_candidates_keep_theirs(self, client: TestClient) -> None:
        rows = client.get("/v1/elections/2016/summary").json()["data"]
        _assert_party(_by_candidate(rows, "Cand A")[0], "republican", None)
        _assert_party(_by_candidate(rows, "Cand B")[0], "democratic", None)
