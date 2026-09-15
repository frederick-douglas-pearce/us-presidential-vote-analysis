"""Unit tests for :mod:`usvote.census.reconcile` (#183).

Offline throughout. Two kinds of input, and the difference matters:

* **Synthetic frames**, built here, for the rule and the guards. Each guard protects
  against a plausible wrong number rather than a crash, so every test is written to fail
  on the wrong-but-passing input — an undeclared disagreement, a stale declaration, a
  cell missing from the curated series — rather than only on an obviously broken one.
* **Real allotments parsed from the committed Archives fixtures**
  (``TestRealAllotments``).
  This is the check with actual evidential weight: it runs the reconciliation against
  the electoral record as the National Archives published it, for eleven elections
  including the three hardest (1864, 1868 and 1872), with no database.

**Why deriving allotments from those fixtures is not a second source of EV truth.**
D024 §5 keeps electoral-vote counts out of ``ec_state_roster_by_year.json`` so that
fixture cannot become a rival authority, and ``ec_participation_frame`` therefore
synthesizes ``total_electoral_votes`` as 0-or-placeholder — which makes it unusable for
testing *values*. The Archives HTML fixtures are a different thing entirely: they are
the primary source itself, already committed, parsed by the repo's own parser. Reading
allotments out of them is not a second answer to "how many votes did this state have",
it is the only answer, reached offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from usvote.census.reconcile import (
    DC_ELECTORAL_VOTES,
    DC_FIRST_ELECTION,
    DC_STATE_NAME,
    KIND_ELECTORAL_VOTES_WITHHELD,
    KIND_RECORD_UNDERSTATES_ALLOTMENT,
    KIND_SEATS_NOT_APPORTIONED,
    SEAT_EXCEPTION_KINDS,
    SEAT_RECONCILIATION_EXCEPTIONS,
    SENATORIAL_ELECTORAL_VOTES,
    SeatException,
    SeatReconciliationError,
    assert_seats_reconcile,
    assert_seats_series_complete,
    build_seat_reconciliation,
    expected_electoral_votes,
)
from usvote.census.seats import SEATS_BY_CENSUS
from usvote.parse import parse_election_years
from usvote.transform import APPOINTED_ELECTORS_NOT_IN_TABLE

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

#: The election years whose Archives page is committed as a fixture.
#:
#: **1864 was added under review, and its absence is why this suite was green while the
#: real gate failed.** The first revision reconciled ten elections, none of them 1864 —
#: the year carrying twelve of the seventeen catalogued disagreements *and* the one
#: undeclared row (Nevada) that made ``assert_seats_reconcile`` raise on the full spine.
#: A proof over a convenient subset is not a proof; the full 51-election run lives in the
#: integration suite and could not be reached offline.
ARCHIVES_FIXTURE_YEARS: tuple[int, ...] = (
    1824,
    1832,
    1836,
    1856,
    1860,
    1864,
    1868,
    1872,
    2016,
    2020,
    2024,
)

#: Appointed electoral-vote totals for those years, **hand-written rather than summed
#: from the frame under test**. A total computed from the same rows the reconciliation
#: reads would pass under any consistent error; these are independent literals, pinned
#: so a parser change that shifted an allotment could not slide through. 1872's 366 and
#: 1868's 294 are the two the repo's own corrections catalog turns on (D045/D046).
EXPECTED_APPOINTED_TOTALS: dict[int, int] = {
    1824: 261,
    1832: 288,
    1836: 294,
    1856: 296,
    1860: 303,
    1864: 233,
    1868: 294,
    1872: 366,
    2016: 538,
    2020: 538,
    2024: 538,
}


def _participation(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build a ``dwh.votes``-shaped participation frame, totals row included."""
    years = sorted({row["year"] for row in rows})
    records = [dict(row, is_total=False) for row in rows]
    for year in years:
        records.append(
            {
                "year": year,
                "state": None,
                "is_total": True,
                "total_electoral_votes": sum(
                    row["total_electoral_votes"] for row in rows if row["year"] == year
                ),
            }
        )
    return pd.DataFrame.from_records(records)


def _row(year: int, state: str, votes: int) -> dict[str, Any]:
    return {"year": year, "state": state, "total_electoral_votes": votes}


def archives_allotments() -> pd.DataFrame:
    """Parse per-state appointed allotments out of the committed Archives fixtures.

    Applies :data:`usvote.transform.APPOINTED_ELECTORS_NOT_IN_TABLE`, so 1872 Arkansas
    and Louisiana carry the 6 and 8 they appointed rather than the ``-`` the page prints
    (D045) — without it the year's denominator reads 352 instead of the 366 Congress
    announced, and this whole reconciliation would be testing the wrong number.
    """
    state_names = set(SEATS_BY_CENSUS[2020])
    tables = {}
    for year in ARCHIVES_FIXTURE_YEARS:
        html = FIXTURES.joinpath(
            f"www_archives_gov_electoral_college_{year}.html"
        ).read_text(encoding="utf-8", errors="replace")
        tables[year] = BeautifulSoup(html, "html.parser").find_all("table")[:2]

    records: list[dict[str, Any]] = []
    for parsed in parse_election_years(tables, state_names):
        year = parsed["year"]
        for entry in parsed["t2"]["votes_by_state"]:
            state = str(entry["state"])
            is_total = state not in state_names
            votes = APPOINTED_ELECTORS_NOT_IN_TABLE.get(
                (int(year), state), int(entry["total_electoral_votes"])
            )
            records.append(
                {
                    "year": year,
                    "state": None if is_total else state,
                    "is_total": is_total,
                    "total_electoral_votes": votes,
                }
            )
    return pd.DataFrame.from_records(records)


class TestTheRule:
    """``seats + 2``, and the two things it is not."""

    def test_a_state_allotment_is_its_seats_plus_two_senators(self) -> None:
        # Texas under the 2010 apportionment: 36 seats, 38 electoral votes in 2016.
        assert SEATS_BY_CENSUS[2010]["Texas"] == 36
        assert expected_electoral_votes(2016, "Texas") == 38

    def test_the_senatorial_offset_is_two_not_folded_into_the_seat_count(self) -> None:
        """The wrong-easy-answer the acceptance criteria name.

        Reconciling raw seats would be off by exactly this constant for every state in
        every year, which looks like a data problem rather than an arithmetic one.
        """
        for state in ("California", "Wyoming", "Ohio"):
            seats = SEATS_BY_CENSUS[2010][state]
            expected = expected_electoral_votes(2016, state)
            assert seats is not None and expected is not None
            assert expected - seats == SENATORIAL_ELECTORAL_VOTES

    def test_dc_is_three_from_1964_and_is_not_census_apportioned(self) -> None:
        """DC's votes come from the 23rd Amendment, not from an apportionment."""
        assert SEATS_BY_CENSUS[1960][DC_STATE_NAME] is None
        assert expected_electoral_votes(DC_FIRST_ELECTION, DC_STATE_NAME) == (
            DC_ELECTORAL_VOTES
        )
        assert expected_electoral_votes(2024, DC_STATE_NAME) == DC_ELECTORAL_VOTES

    def test_dc_has_no_electoral_votes_before_1964(self) -> None:
        assert expected_electoral_votes(DC_FIRST_ELECTION - 4, DC_STATE_NAME) == 0

    def test_a_state_with_no_apportioned_seats_expects_none_not_two(self) -> None:
        """``(X)`` must not become ``0 + 2``.

        West Virginia is ``(X)`` in the 1860 column. Reading that as zero seats would
        silently expect 2 electoral votes and turn a real, catalogued discrepancy into a
        near-miss that looks like an off-by-three.
        """
        assert SEATS_BY_CENSUS[1860]["West Virginia"] is None
        assert expected_electoral_votes(1864, "West Virginia") is None


class TestCompleteness:
    """The three-state cell rule: a digit, an explicit ``(X)``, and an absent key."""

    def test_an_explicit_none_is_a_statement_and_passes_completeness(self) -> None:
        frame = _participation([_row(1864, "West Virginia", 5)])
        assert_seats_series_complete(
            frame.loc[~frame["is_total"]].rename(columns={"year": "election_year"})
        )

    def test_a_missing_key_fails_even_though_a_none_would_not(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The distinction the whole invariant exists for.

        A curation omission and the source's own ``(X)`` are indistinguishable
        downstream — both yield "no expected value" — so without this guard a forgotten
        cell needs only a plausible exception declaration to pass, and the acceptance
        criterion that an *unexplained* gap fails the build stops being true.
        """
        trimmed = {
            year: {
                state: seats
                for state, seats in by_state.items()
                if not (year == 2010 and state == "Texas")
            }
            for year, by_state in SEATS_BY_CENSUS.items()
        }
        monkeypatch.setattr(
            "usvote.census.reconcile.SEATS_BY_CENSUS", trimmed, raising=True
        )
        frame = _participation([_row(2016, "Texas", 38)])
        with pytest.raises(SeatReconciliationError, match="curation omission"):
            build_seat_reconciliation(frame)

    def test_the_error_names_the_regeneration_route_not_an_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing cell must not read as an invitation to declare an exception."""
        trimmed = {
            year: {s: v for s, v in by.items() if not (year == 2010 and s == "Ohio")}
            for year, by in SEATS_BY_CENSUS.items()
        }
        monkeypatch.setattr(
            "usvote.census.reconcile.SEATS_BY_CENSUS", trimmed, raising=True
        )
        frame = _participation([_row(2016, "Ohio", 18)])
        with pytest.raises(SeatReconciliationError) as excinfo:
            build_seat_reconciliation(frame)
        assert "scripts/extract_census_seats.py" in str(excinfo.value)


class TestUnexplainedDisagreements:
    """Direction 1 — every recorded allotment is explained, or the build fails."""

    def test_an_undeclared_disagreement_raises(self) -> None:
        frame = _participation([_row(2016, "Texas", 99)])
        with pytest.raises(SeatReconciliationError, match="does not explain"):
            assert_seats_reconcile(frame)

    def test_the_error_refuses_to_round_the_difference_away(self) -> None:
        frame = _participation([_row(2016, "Texas", 37)])
        with pytest.raises(SeatReconciliationError) as excinfo:
            assert_seats_reconcile(frame)
        assert "implies 38" in str(excinfo.value)
        assert "record says 37" in str(excinfo.value)

    def test_a_declared_exception_passes(self) -> None:
        frame = _participation([_row(1868, "Virginia", 0)])
        assert_seats_reconcile(frame)

    def test_an_exception_does_not_license_a_different_allotment(self) -> None:
        """The declaration pins the recorded value, so it is not a blanket waiver.

        1868 Virginia is declared against 0 electoral votes. If the fact ever said 7,
        the declaration must stop covering it rather than absorb a new number.
        """
        frame = _participation([_row(1868, "Virginia", 7)])
        with pytest.raises(SeatReconciliationError, match="does not explain"):
            assert_seats_reconcile(frame)


class TestStaleDeclarations:
    """The reciprocal — the direction with no other reader."""

    def test_an_exception_that_now_reconciles_raises(self) -> None:
        """Virginia 1868 with its full 13 votes would make the catalog entry a lie."""
        frame = _participation([_row(1868, "Virginia", 13)])
        with pytest.raises(SeatReconciliationError, match="now reconciles"):
            assert_seats_reconcile(frame)

    def test_a_year_absent_from_the_frame_is_not_stale(self) -> None:
        """A partial frame must not be able to condemn a declaration it never tested.

        Found by running the reconciliation over the ten committed Archives fixtures:
        1864 is not among them, and the guard reported all twelve 1864 declarations as
        stale. A frame that does not carry a year says nothing about that year.
        """
        frame = _participation([_row(2016, "Texas", 38)])
        assert_seats_reconcile(frame)

    def test_a_partial_frame_never_condemns_a_declaration_it_cannot_see(self) -> None:
        """Absence is ambiguous here, so this guard must not read it as staleness.

        A frame carrying only 1868 Ohio reaches none of that year's four declarations.
        Reading "not in this frame" as "did not participate" is what broke the earlier
        version; the membership claim is asserted against a complete spine instead —
        see :class:`TestTheRosterFixtureAgrees` and the integration suite.
        """
        assert_seats_reconcile(_participation([_row(1868, "Ohio", 21)]))


class TestTheCatalog:
    """Shape of :data:`SEAT_RECONCILIATION_EXCEPTIONS`."""

    def test_seventeen_entries_in_three_kinds(self) -> None:
        assert len(SEAT_RECONCILIATION_EXCEPTIONS) == 17
        withheld = [
            e
            for e in SEAT_RECONCILIATION_EXCEPTIONS
            if e.kind == KIND_ELECTORAL_VOTES_WITHHELD
        ]
        unapportioned = [
            e
            for e in SEAT_RECONCILIATION_EXCEPTIONS
            if e.kind == KIND_SEATS_NOT_APPORTIONED
        ]
        understated = [
            e
            for e in SEAT_RECONCILIATION_EXCEPTIONS
            if e.kind == KIND_RECORD_UNDERSTATES_ALLOTMENT
        ]
        assert len(withheld) == 14
        assert len(unapportioned) == 2
        assert len(understated) == 1

    def test_the_one_understated_row_is_nevada_1864_and_pins_the_cast_figure(
        self,
    ) -> None:
        """The row where the *record* is wrong, not the census.

        The declaration pins **2** — what the Archives prints — while the note states the
        appointed allotment is 3. Pinning the record's own value is what makes the entry
        self-cleaning: when the deferred spine correction restores 3, the row reconciles
        and the stale-declaration guard demands this entry's removal.
        """
        entry = next(
            e
            for e in SEAT_RECONCILIATION_EXCEPTIONS
            if e.kind == KIND_RECORD_UNDERSTATES_ALLOTMENT
        )
        assert (entry.election_year, entry.state) == (1864, "Nevada")
        assert entry.recorded_electoral_votes == 2
        assert expected_electoral_votes(1864, "Nevada") == 3
        assert "cast" in entry.note.lower()

    def test_the_withheld_rows_are_1864_and_1868_only(self) -> None:
        """Not 'every Reconstruction year' — 1872 has none, and that is a finding."""
        years = {
            e.election_year
            for e in SEAT_RECONCILIATION_EXCEPTIONS
            if e.kind == KIND_ELECTORAL_VOTES_WITHHELD
        }
        assert years == {1864, 1868}
        assert 1872 not in {e.election_year for e in SEAT_RECONCILIATION_EXCEPTIONS}

    def test_georgia_1868_is_not_declared(self) -> None:
        """Its nine votes were *disputed* (D044), not withheld; its allotment is intact.

        Whether votes counted and how many a state was allotted are different questions,
        and only the second is this module's business.
        """
        assert (1868, "Georgia") not in {
            (e.election_year, e.state) for e in SEAT_RECONCILIATION_EXCEPTIONS
        }

    def test_every_kind_is_in_the_closed_vocabulary(self) -> None:
        for exception in SEAT_RECONCILIATION_EXCEPTIONS:
            assert exception.kind in SEAT_EXCEPTION_KINDS

    def test_every_entry_carries_a_public_domain_statutory_citation(self) -> None:
        """A citation is the point of the record, exactly as in ``pv/absences``."""
        for exception in SEAT_RECONCILIATION_EXCEPTIONS:
            assert len(exception.citation) > 80
            assert "Stat." in exception.citation or "H.R." in exception.citation

    def test_a_duplicate_declaration_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        duplicate = (
            *SEAT_RECONCILIATION_EXCEPTIONS,
            SeatException(
                election_year=1868,
                state="Virginia",
                kind=KIND_ELECTORAL_VOTES_WITHHELD,
                recorded_electoral_votes=0,
                citation="x" * 100 + " Stat.",
                note="duplicate",
            ),
        )
        monkeypatch.setattr(
            "usvote.census.reconcile.SEAT_RECONCILIATION_EXCEPTIONS",
            duplicate,
            raising=True,
        )
        frame = _participation([_row(1868, "Virginia", 0)])
        with pytest.raises(SeatReconciliationError, match="twice"):
            assert_seats_reconcile(frame)


class TestRealAllotments:
    """The reconciliation against the electoral record as the Archives published it.

    Eleven elections, parsed offline from committed fixtures. This is the test that would
    fail if the curated seat series were wrong anywhere it is exercised, and it covers
    both Reconstruction years the epic was gated on.
    """

    def test_the_appointed_totals_match_independent_literals(self) -> None:
        frame = archives_allotments()
        states = frame.loc[~frame["is_total"]]
        totals = states.groupby("year")["total_electoral_votes"].sum().to_dict()
        assert {int(k): int(v) for k, v in totals.items()} == EXPECTED_APPOINTED_TOTALS

    def test_the_whole_series_reconciles(self) -> None:
        assert_seats_reconcile(archives_allotments())

    def test_the_disagreeing_rows_are_exactly_the_catalogued_ones(self) -> None:
        """The disagreements are not merely few — they are the *declared* ones.

        Pinning the whole set rather than a count is what makes a new undeclared row fail
        here. The first revision asserted four rows over a fixture set that excluded 1864,
        so thirteen real disagreements — including the undeclared Nevada one — were
        outside what this test could see.
        """
        built = build_seat_reconciliation(archives_allotments())
        disagreeing = {
            (int(row.election_year), str(row.state))
            for row in built.itertuples(index=False)
            if not row.reconciles
        }
        assert disagreeing == {
            (1864, "Alabama"),
            (1864, "Arkansas"),
            (1864, "Florida"),
            (1864, "Georgia"),
            (1864, "Louisiana"),
            (1864, "Mississippi"),
            (1864, "Nevada"),
            (1864, "North Carolina"),
            (1864, "South Carolina"),
            (1864, "Tennessee"),
            (1864, "Texas"),
            (1864, "Virginia"),
            (1864, "West Virginia"),
            (1868, "Mississippi"),
            (1868, "Texas"),
            (1868, "Virginia"),
            (1868, "West Virginia"),
        }

    def test_west_virginia_1868_is_the_votes_without_seats_case(self) -> None:
        """The case a one-sided 'missing state' guard passes in silence."""
        built = build_seat_reconciliation(archives_allotments())
        row = built[
            (built["election_year"] == 1868) & (built["state"] == "West Virginia")
        ].iloc[0]
        assert pd.isna(row["seats"])
        assert int(row["total_electoral_votes"]) == 5

    def test_1872_reconciles_on_the_restored_366_denominator(self) -> None:
        """AR and LA appointed full slates the page prints as ``-`` (D045/D046).

        The repo derives that denominator the same way this module does — 37 states x 2
        senators + 292 representatives = 366 — so this is the one year where the seat
        reconciliation and the electoral-vote corrections catalog meet.
        """
        built = build_seat_reconciliation(archives_allotments())
        year = built[built["election_year"] == 1872]
        assert bool(year["reconciles"].all())
        assert int(year["total_electoral_votes"].sum()) == 366
        for state, votes in (("Arkansas", 6), ("Louisiana", 8)):
            row = year[year["state"] == state].iloc[0]
            assert int(row["total_electoral_votes"]) == votes

    def test_a_single_corrupted_allotment_is_caught(self) -> None:
        """Negative control: the suite must be able to go red on real data."""
        frame = archives_allotments()
        mask = (frame["year"] == 2020) & (frame["state"] == "Texas")
        frame.loc[mask, "total_electoral_votes"] = 99
        with pytest.raises(SeatReconciliationError):
            assert_seats_reconcile(frame)

    def test_the_fixture_years_are_actually_all_read(self) -> None:
        """Guards the harness: a fixture that stopped parsing would go unnoticed."""
        frame = archives_allotments()
        assert set(frame["year"].unique()) == set(ARCHIVES_FIXTURE_YEARS)
        assert len(frame.loc[~frame["is_total"]]) == 401


class TestTheSeam:
    """Every guard the seam claims to run, actually runs.

    This exists because a guard call **was** silently droppable: the first revision wired
    three guards, one of which could not fire, and review demonstrated that deleting its
    call left all 1640 unit tests green. That is the shape this pins — not that the guards
    are correct, but that the seam has not quietly stopped calling one.
    """

    def test_the_seam_runs_every_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from usvote.census import reconcile as module

        called: list[str] = []
        for name in ("_assert_every_allotment_is_explained", "_assert_no_stale_exception"):
            monkeypatch.setattr(
                module,
                name,
                lambda *_a, _n=name, **_k: called.append(_n),
                raising=True,
            )
        module.assert_seats_reconcile(_participation([_row(2016, "Texas", 38)]))
        assert called == [
            "_assert_every_allotment_is_explained",
            "_assert_no_stale_exception",
        ]

    def test_the_recorder_would_catch_a_seam_that_dropped_a_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The twin, and it has to do real work to be worth anything.

        A recorder test passes just as well against a seam that calls everything as
        against one that calls nothing extra — what it must show is that it **fails** when
        a call goes missing. So this builds the exact defect under review (a seam wired
        with one guard dropped) and asserts the recorded list no longer matches. Without
        this, the test above is satisfied by any seam whose body happens to call both
        names, including by accident.
        """
        from usvote.census import reconcile as module

        called: list[str] = []
        for name in ("_assert_every_allotment_is_explained", "_assert_no_stale_exception"):
            monkeypatch.setattr(
                module,
                name,
                lambda *_a, _n=name, **_k: called.append(_n),
                raising=True,
            )

        def seam_missing_a_guard(ec_participation: pd.DataFrame) -> None:
            frame = module.build_seat_reconciliation(ec_participation)
            module._assert_every_allotment_is_explained(frame)

        seam_missing_a_guard(_participation([_row(2016, "Texas", 38)]))
        assert called == ["_assert_every_allotment_is_explained"]
        assert called != [
            "_assert_every_allotment_is_explained",
            "_assert_no_stale_exception",
        ]


class TestTheRosterFixtureAgrees:
    """Cross-check the catalog's membership against the committed EC roster.

    Independent of the Archives HTML path above: this reads the zero-EV roster, so the
    two would have to be wrong the same way to agree.
    """

    def test_the_withheld_states_are_exactly_the_fixtures_zero_ev_states(self) -> None:
        entries = json.loads(
            (FIXTURES / "ec_state_roster_by_year.json").read_text(encoding="utf-8")
        )["years"]
        for year in (1864, 1868):
            declared = {
                e.state
                for e in SEAT_RECONCILIATION_EXCEPTIONS
                if e.election_year == year and e.kind == KIND_ELECTORAL_VOTES_WITHHELD
            }
            assert declared == set(entries[str(year)]["zero_ev_states"])

    def test_1872_has_no_zero_ev_states_so_no_withheld_rows(self) -> None:
        entries = json.loads(
            (FIXTURES / "ec_state_roster_by_year.json").read_text(encoding="utf-8")
        )["years"]
        assert entries["1872"]["zero_ev_states"] == []
