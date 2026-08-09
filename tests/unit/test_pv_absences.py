"""Unit tests for :mod:`usvote.pv.absences` — the in-repo PV absence catalog (#140).

Offline throughout. The EC spine arrives through the same DI seam every roster
derivation uses, from ``tests._helpers.ec_participation_frame`` (the committed
public-domain Archives roster snapshot), so these run in CI with no network, no DB, and
**no UCSB corpus**. That last one is the point of the issue: the classifications this
module ships must be provable without UCSB, and the structural half of that proof lives
in :mod:`tests.unit.test_layering`.

**What CI can and cannot prove here, stated plainly.** The 14 ``not_participating`` rows
are verifiable *in both directions* against the committed fixture — they must be exactly
the 1864/1868 zero-EV set, and the fixture carries that set — so those 14 are genuinely
proven. The 18 ``legislature_chosen`` rows are not: a legislature-appointed state cast
electoral votes like any other, so the spine cannot distinguish it from a state that held
a popular vote. They are pinned here as an explicit expected set with non-empty
citations, and independently checked against UCSB by
``test_ucsb_transform.TestRealCorpus``, which **skips in CI** (D022 — no UCSB bytes are
committed). Running that class locally with ``USVOTE_UCSB_HTML_DIR`` set is a merge
precondition, not a CI gate, and this docstring exists so nobody mistakes the green tick
for the stronger claim.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import ec_participation_frame
from usvote.pv import absences
from usvote.pv.absences import (
    CURATED_YEAR_COUNT,
    CURATED_YEARS,
    PV_ABSENCE_CATALOG,
    PVAbsence,
    PVAbsenceCatalogError,
    assert_catalog_matches_spine,
    build_curated_roster,
)
from usvote.pv.status import (
    PV_ABSENCE_STATUSES,
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
    ROSTER_COLUMNS,
    PVRosterError,
    assert_roster_shape,
    assert_unique_roster_grain,
    build_roster,
)

SOURCE = "TEST"

#: The 18 ``legislature_chosen`` rows, written out longhand rather than derived from the
#: catalog — a test that recomputes the constant it is checking proves nothing.
EXPECTED_LEGISLATURE_CHOSEN: frozenset[tuple[int, str]] = frozenset(
    {
        (1868, "Florida"),
        (1824, "Delaware"),
        (1824, "Georgia"),
        (1824, "Louisiana"),
        (1824, "New York"),
        (1824, "South Carolina"),
        (1824, "Vermont"),
        (1828, "Delaware"),
        (1828, "South Carolina"),
        (1832, "South Carolina"),
        (1836, "South Carolina"),
        (1840, "South Carolina"),
        (1844, "South Carolina"),
        (1848, "South Carolina"),
        (1852, "South Carolina"),
        (1856, "South Carolina"),
        (1860, "South Carolina"),
        (1876, "Colorado"),
    }
)

#: The 14 ``not_participating`` rows — the 11 Confederate states of 1864, plus the three
#: not yet readmitted in 1868 (admitted to scope by #143 with no new research: they were
#: catalogued out of scope in #140). Unlike the set above, this one is also checked
#: *against the EC spine* below, which is real proof.
EXPECTED_NOT_PARTICIPATING: frozenset[tuple[int, str]] = frozenset(
    {
        (1864, state)
        for state in (
            "Alabama",
            "Arkansas",
            "Florida",
            "Georgia",
            "Louisiana",
            "Mississippi",
            "North Carolina",
            "South Carolina",
            "Tennessee",
            "Texas",
            "Virginia",
        )
    }
    | {(1868, state) for state in ("Mississippi", "Texas", "Virginia")}
)


def curated(*years: int) -> pd.DataFrame:
    """The curated roster for ``years``, over the committed Archives fixture."""
    return build_curated_roster(
        ec_participation_frame(years), source=SOURCE, years=years
    )


def statuses(roster: pd.DataFrame) -> dict[tuple[int, str], str]:
    return {
        (int(year), state): status
        for year, state, status in zip(
            roster["year"], roster["state"], roster["pv_status"], strict=True
        )
    }


def keys_with(roster: pd.DataFrame, status: str) -> set[tuple[int, str]]:
    return {key for key, value in statuses(roster).items() if value == status}


# --- the general builder's new parameter ------------------------------------


class TestBuildRosterAbsenceMap:
    """``build_roster(absences=...)`` directly — the seam both callers go through.

    Tested here rather than only via ``build_curated_roster`` because the catalog can
    never produce a bad map: if the validation branch were inverted (``in`` for ``not
    in``), every catalog-driven test would still pass while every legitimate absence
    map raised.
    """

    def test_an_absence_map_is_layered_onto_the_residual(self) -> None:
        roster = build_roster(
            ec_participation_frame([2020]),
            source=SOURCE,
            years=[2020],
            absences={(2020, "Ohio"): PV_STATUS_LEGISLATURE_CHOSEN},
        )
        by_state = statuses(roster)
        assert by_state[(2020, "Ohio")] == PV_STATUS_LEGISLATURE_CHOSEN
        assert by_state[(2020, "Iowa")] == PV_STATUS_POPULAR_VOTE

    def test_no_absence_map_is_all_popular_vote(self) -> None:
        roster = build_roster(ec_participation_frame([2020]), source=SOURCE,
                              years=[2020])
        assert set(roster["pv_status"]) == {PV_STATUS_POPULAR_VOTE}

    @pytest.mark.parametrize(
        "status", [PV_STATUS_POPULAR_VOTE, "unknown", "legislature-chosen", ""]
    )
    def test_a_non_absence_status_in_the_map_raises(self, status: str) -> None:
        """``popular_vote`` included: mapping to the residual is a silent no-op."""
        with pytest.raises(PVRosterError, match="absence map"):
            build_roster(
                ec_participation_frame([2020]),
                source=SOURCE,
                years=[2020],
                absences={(2020, "Ohio"): status},
            )

    def test_a_key_matching_no_spine_row_is_simply_never_applied(self) -> None:
        """The general builder does not police keys — that is the catalog's job.

        Stated as a test so the division of labour is deliberate rather than assumed:
        ``assert_catalog_matches_spine`` is what turns an unmatched key into an error.
        """
        roster = build_roster(
            ec_participation_frame([2020]),
            source=SOURCE,
            years=[2020],
            absences={(2020, "Atlantis"): PV_STATUS_NOT_PARTICIPATING},
        )
        assert set(roster["pv_status"]) == {PV_STATUS_POPULAR_VOTE}


# --- catalog integrity ------------------------------------------------------


class TestCatalogIntegrity:
    """The catalog as a data structure, before any derivation runs over it."""

    def test_the_in_scope_catalog_is_exactly_32_rows_split_18_14(self) -> None:
        in_scope = {k: v for k, v in PV_ABSENCE_CATALOG.items() if k[0] in CURATED_YEARS}
        assert len(in_scope) == 32
        # Since #143 admitted 1868, *every* catalog row is in scope — there is no longer a
        # catalogued-but-unconsumed remainder.
        assert in_scope.keys() == PV_ABSENCE_CATALOG.keys()
        by_status: dict[str, set[tuple[int, str]]] = {}
        for key, entry in in_scope.items():
            by_status.setdefault(entry.pv_status, set()).add(key)
        assert by_status[PV_STATUS_LEGISLATURE_CHOSEN] == EXPECTED_LEGISLATURE_CHOSEN
        assert by_status[PV_STATUS_NOT_PARTICIPATING] == EXPECTED_NOT_PARTICIPATING

    def test_every_entry_carries_an_absence_status_and_a_citation(self) -> None:
        """``popular_vote`` is the residual and must never be catalogued."""
        for key, entry in PV_ABSENCE_CATALOG.items():
            assert isinstance(entry, PVAbsence), key
            assert entry.pv_status in PV_ABSENCE_STATUSES, key
            assert entry.citation.strip(), f"{key} has no citation"

    def test_curated_years_is_the_ec_ingest_span_and_excludes_1872(self) -> None:
        """The count pin. If the EC span moves, an unreviewed year becomes derivable.

        1868 joined the span in #143 — and the pin is exactly what forced that to be a
        deliberate act: lifting ``UNSUPPORTED_EC_YEARS`` raised at import until its four
        already-cited rows were confirmed in scope.
        """
        assert len(CURATED_YEARS) == CURATED_YEAR_COUNT == 50
        assert min(CURATED_YEARS) == 1824
        assert max(CURATED_YEARS) == 2024
        assert 1868 in CURATED_YEARS
        assert 1872 not in CURATED_YEARS

    def test_the_scope_pin_is_enforced_at_runtime_not_only_by_this_test(self) -> None:
        """Bumping ``LATEST_ELECTION_YEAR`` is a routine each-cycle edit.

        A test-only pin would let the span grow, ``build_curated_roster`` stop raising
        for the new year, and that year ship as an all-``popular_vote`` roster on no
        review — and #139 runs this derivation **in-process at snapshot build time**,
        where no test is watching. So the check runs where the code runs.
        """
        assert (
            "_assert_curated_scope_pinned" in dir(absences)
        ), "the runtime pin must exist, not just this assertion"
        with (
            pytest.MonkeyPatch.context() as mp,
            pytest.raises(PVAbsenceCatalogError, match="just became derivable"),
        ):
            mp.setattr(absences, "CURATED_YEARS", CURATED_YEARS | {2028})
            absences._assert_curated_scope_pinned()

    def test_no_catalog_row_is_left_outside_curated_years(self) -> None:
        """The catalogue-early payoff, asserted rather than assumed.

        1868's four rows were curated in #140 while the year was still gated, precisely so
        that admitting it (#143) needed no new research. Nothing is catalogued-but-unusable
        now; if a future year is pre-curated the same way, this test is where that shows.
        """
        uncurated = {k for k in PV_ABSENCE_CATALOG if k[0] not in CURATED_YEARS}
        assert not uncurated
        assert {k for k in PV_ABSENCE_CATALOG if k[0] == 1868} == {
            (1868, "Florida"),
            (1868, "Mississippi"),
            (1868, "Texas"),
            (1868, "Virginia"),
        }

    def test_no_catalog_key_falls_in_mit_s_span(self) -> None:
        """MIT's 1976-2024 precondition, held here rather than as a runtime assert.

        ``build_popular_vote_roster`` is the empty-map call, and MIT's path never imports
        this module — so if a modern absence were ever catalogued, MIT would keep marking
        the state ``popular_vote`` with nothing failing. This is what notices.
        """
        modern = sorted(k for k in PV_ABSENCE_CATALOG if 1976 <= k[0] <= 2024)
        assert not modern, (
            f"catalog keys {modern} fall in MIT's span, where "
            "build_popular_vote_roster assumes no absences exist"
        )


# --- the real-shape rosters -------------------------------------------------


class TestRealShapes:
    """The three years with structural content, plus a uniform modern control."""

    def test_1824_has_24_states_6_legislature_chosen_18_popular_vote(self) -> None:
        roster = curated(1824)
        assert len(roster) == 24
        assert keys_with(roster, PV_STATUS_LEGISLATURE_CHOSEN) == {
            k for k in EXPECTED_LEGISLATURE_CHOSEN if k[0] == 1824
        }
        assert len(keys_with(roster, PV_STATUS_POPULAR_VOTE)) == 18
        assert not keys_with(roster, PV_STATUS_NOT_PARTICIPATING)

    def test_not_participating_is_exactly_the_spine_s_zero_ev_set(self) -> None:
        """The 14 rows CI can genuinely prove — both directions, against the spine.

        Not "the catalog says so": the fixture independently records which states cast
        zero electoral votes, and the two sets must coincide exactly. Both absence years
        are checked together (1864's eleven Confederate states, 1868's three not yet
        readmitted), because the *cross-year* equality is what pins the claim — a
        1864-only check would pass while 1868 quietly acquired or lost a row.
        """
        years = [1864, 1868]
        frame = ec_participation_frame(years)
        zero_ev = {
            (int(year), state)
            for year, state, ev in zip(
                frame["year"], frame["state"], frame["total_electoral_votes"], strict=True
            )
            if state is not None and ev == 0
        }
        roster = curated(*years)
        assert keys_with(roster, PV_STATUS_NOT_PARTICIPATING) == zero_ev
        assert zero_ev == EXPECTED_NOT_PARTICIPATING

        # ...and per year, so a shortfall in one cannot be masked by the other.
        roster_1864 = curated(1864)
        assert len(roster_1864) == 36
        assert len(keys_with(roster_1864, PV_STATUS_NOT_PARTICIPATING)) == 11
        assert len(keys_with(roster_1864, PV_STATUS_POPULAR_VOTE)) == 25
        roster_1868 = curated(1868)
        assert len(roster_1868) == 37
        assert len(keys_with(roster_1868, PV_STATUS_NOT_PARTICIPATING)) == 3
        # Florida is legislature_chosen, not absent — it cast its three electoral votes.
        assert keys_with(roster_1868, PV_STATUS_LEGISLATURE_CHOSEN) == {(1868, "Florida")}
        assert len(keys_with(roster_1868, PV_STATUS_POPULAR_VOTE)) == 33

    def test_south_carolina_is_not_participating_in_1864_not_legislature_chosen(
        self,
    ) -> None:
        """The one state catalogued under both causes — so it pins the (year, state) key.

        A catalog keyed on state alone would have to pick one, and South Carolina's ten
        ``legislature_chosen`` years would swallow its single ``not_participating`` one.
        """
        assert statuses(curated(1864))[(1864, "South Carolina")] == (
            PV_STATUS_NOT_PARTICIPATING
        )
        assert statuses(curated(1860))[(1860, "South Carolina")] == (
            PV_STATUS_LEGISLATURE_CHOSEN
        )

    def test_1876_colorado_is_legislature_chosen_and_the_other_37_are_not(self) -> None:
        roster = curated(1876)
        assert len(roster) == 38
        assert keys_with(roster, PV_STATUS_LEGISLATURE_CHOSEN) == {(1876, "Colorado")}
        assert len(keys_with(roster, PV_STATUS_POPULAR_VOTE)) == 37
        assert not keys_with(roster, PV_STATUS_NOT_PARTICIPATING)

    def test_a_modern_year_is_uniformly_popular_vote(self) -> None:
        """The catalog contributes nothing after 1876 — the residual carries the year."""
        roster = curated(2020)
        assert len(roster) == 51
        assert set(roster["pv_status"]) == {PV_STATUS_POPULAR_VOTE}

    def test_the_whole_curated_span_yields_32_absences_and_nothing_else(self) -> None:
        roster = build_curated_roster(
            ec_participation_frame(CURATED_YEARS),
            source=SOURCE,
            years=CURATED_YEARS,
        )
        absent = {
            key
            for key, status in statuses(roster).items()
            if status in PV_ABSENCE_STATUSES
        }
        assert absent == EXPECTED_LEGISLATURE_CHOSEN | EXPECTED_NOT_PARTICIPATING
        assert len(absent) == 32


# --- the residual, and the shape contract -----------------------------------


class TestResidualAndShape:
    def test_popular_vote_is_the_residual_not_an_enumeration(self) -> None:
        """A state the catalog has never heard of becomes ``popular_vote`` on its own.

        This is what makes absence detectable (D024 §3) — and what makes the reverse
        cross-check in :func:`assert_catalog_matches_spine` load-bearing rather than
        belt-and-braces.
        """
        frame = pd.concat(
            [
                ec_participation_frame([1824]),
                pd.DataFrame(
                    [{
                        "year": 1824,
                        "state": "Atlantis",
                        "is_total": False,
                        "total_electoral_votes": 5,
                    }]
                ),
            ],
            ignore_index=True,
        )
        roster = build_curated_roster(frame, source=SOURCE, years=[1824])
        assert statuses(roster)[(1824, "Atlantis")] == PV_STATUS_POPULAR_VOTE

    def test_totals_rows_are_excluded(self) -> None:
        """``votes.state`` is NULL on them; a bare DISTINCT would emit a null roster row."""
        frame = ec_participation_frame([1824])
        assert frame["is_total"].any(), "fixture must carry a totals row to be a test"
        roster = curated(1824)
        assert roster["state"].notna().all()
        assert len(roster) == 24

    def test_the_output_satisfies_the_shared_roster_contract(self) -> None:
        roster = curated(1824, 1864, 1876)
        assert list(roster.columns) == list(ROSTER_COLUMNS)
        assert_roster_shape(roster)
        assert_unique_roster_grain(roster)

    def test_note_is_null_on_every_row_including_absences(self) -> None:
        """D024 §6: an absence's cause lives in its citation, never in the warehouse."""
        roster = curated(1824, 1864, 1876)
        assert roster["note"].isna().all()

    def test_source_is_required_and_has_no_default(self) -> None:
        with pytest.raises(TypeError):
            build_curated_roster(  # type: ignore[call-arg]
                ec_participation_frame([1824]), years=[1824]
            )


# --- the year gate ----------------------------------------------------------


class TestCuratedYearGate:
    """Silence about an unreviewed year must not read as "no absences"."""

    @pytest.mark.parametrize("year", [1872, 1800, 2028])
    def test_an_uncurated_year_raises_rather_than_deriving(self, year: int) -> None:
        frame = pd.DataFrame(
            [{
                "year": year,
                "state": "Delaware",
                "is_total": False,
                "total_electoral_votes": 5,
            }]
        )
        with pytest.raises(PVAbsenceCatalogError, match="outside CURATED_YEARS"):
            build_curated_roster(frame, source=SOURCE, years=[year])

    def test_a_mixed_request_raises_on_the_uncurated_year(self) -> None:
        """Partial derivation would be worse than refusal — some years unreviewed."""
        with pytest.raises(PVAbsenceCatalogError, match=r"\[1872\]"):
            build_curated_roster(
                ec_participation_frame([1864]), source=SOURCE, years=[1864, 1872]
            )

    def test_the_1868_catalog_rows_now_reach_the_roster(self) -> None:
        """The other side of the gate: 1868 derives, 1872 still does not.

        Was ``..._never_reach_a_roster`` while the year was gated. Inverting it (rather
        than deleting it) keeps the gate's *behaviour* pinned from both directions — a
        refactor that quietly stopped applying the catalog would pass a "1872 absent"
        assertion alone.
        """
        roster = build_curated_roster(
            ec_participation_frame(CURATED_YEARS),
            source=SOURCE,
            years=CURATED_YEARS,
        )
        assert 1868 in set(roster["year"])
        assert 1872 not in set(roster["year"])
        by_state = statuses(roster)
        assert by_state[(1868, "Florida")] == PV_STATUS_LEGISLATURE_CHOSEN
        assert by_state[(1868, "Texas")] == PV_STATUS_NOT_PARTICIPATING
        # ...and an ordinary 1868 state is still the residual, not swept up by the year.
        assert by_state[(1868, "Ohio")] == PV_STATUS_POPULAR_VOTE


# --- the spine cross-check --------------------------------------------------


class TestCatalogMatchesSpine:
    """The guard that makes the catalog falsifiable rather than merely asserted."""

    def test_it_passes_over_the_whole_real_span(self) -> None:
        assert_catalog_matches_spine(ec_participation_frame(CURATED_YEARS))

    def test_a_phantom_catalog_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A typo'd state name would otherwise never match and never be noticed."""
        catalog = dict(PV_ABSENCE_CATALOG)
        catalog[(1824, "Delware")] = PVAbsence(PV_STATUS_LEGISLATURE_CHOSEN, "typo")
        monkeypatch.setattr(absences, "PV_ABSENCE_CATALOG", catalog)
        with pytest.raises(PVAbsenceCatalogError, match="absent from the EC spine"):
            assert_catalog_matches_spine(ec_participation_frame([1824]), years=[1824])

    def test_a_not_participating_key_with_nonzero_ev_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        catalog = dict(PV_ABSENCE_CATALOG)
        catalog[(1824, "Delaware")] = PVAbsence(PV_STATUS_NOT_PARTICIPATING, "wrong")
        monkeypatch.setattr(absences, "PV_ABSENCE_CATALOG", catalog)
        with pytest.raises(PVAbsenceCatalogError, match="contradict the EC spine"):
            assert_catalog_matches_spine(ec_participation_frame([1824]), years=[1824])

    def test_a_legislature_chosen_key_with_zero_ev_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        catalog = dict(PV_ABSENCE_CATALOG)
        catalog[(1864, "Texas")] = PVAbsence(PV_STATUS_LEGISLATURE_CHOSEN, "wrong")
        monkeypatch.setattr(absences, "PV_ABSENCE_CATALOG", catalog)
        with pytest.raises(PVAbsenceCatalogError, match="contradict the EC spine"):
            assert_catalog_matches_spine(ec_participation_frame([1864]), years=[1864])

    def test_an_uncatalogued_zero_ev_state_raises(self) -> None:
        """The reverse direction — the half with teeth.

        Because ``popular_vote`` is the residual, a state that becomes zero-EV in the
        spine silently *becomes* ``popular_vote``. Nothing else in the derivation can
        see it: the catalog is unchanged, the roster is well-shaped, and the state looks
        like every other participant.
        """
        frame = ec_participation_frame([1876])
        frame.loc[frame["state"] == "Ohio", "total_electoral_votes"] = 0
        with pytest.raises(PVAbsenceCatalogError) as excinfo:
            assert_catalog_matches_spine(frame, years=[1876])
        message = str(excinfo.value)
        assert "not in the absence catalog" in message
        assert "Ohio" in message
        assert "usvote/parse.py" in message, "the message must name the likely culprit"

    def test_build_curated_roster_runs_the_cross_check_itself(self) -> None:
        """A guard the caller must remember to invoke is a guard that gets skipped."""
        frame = ec_participation_frame([1876])
        frame.loc[frame["state"] == "Ohio", "total_electoral_votes"] = 0
        with pytest.raises(PVAbsenceCatalogError, match="not in the absence catalog"):
            build_curated_roster(frame, source=SOURCE, years=[1876])

    def test_a_missing_electoral_vote_column_raises_rather_than_passing(self) -> None:
        """The cross-check needs the EV column; a silent skip would be the worst case."""
        frame = ec_participation_frame([1824]).drop(columns=["total_electoral_votes"])
        with pytest.raises(PVAbsenceCatalogError, match="total_electoral_votes"):
            assert_catalog_matches_spine(frame, years=[1824])

    def test_a_null_electoral_vote_raises_instead_of_exempting_the_state(self) -> None:
        """A null is worse than a wrong number, in both directions.

        ``int(nan)`` raises a bare ``ValueError`` naming no year or state; and — the
        silent half — ``nan == 0`` is False, so the uncatalogued-zero check would skip
        the state entirely and let the residual absorb it. That is the exact failure
        that check exists to catch, so a null must never reach it.
        """
        frame = ec_participation_frame([1864])
        frame.loc[frame["state"] == "Texas", "total_electoral_votes"] = float("nan")
        with pytest.raises(PVAbsenceCatalogError, match="null `total_electoral_votes`"):
            assert_catalog_matches_spine(frame, years=[1864])

    def test_duplicate_spine_rows_are_aggregated_not_last_wins(self) -> None:
        """``dwh.votes`` is per-candidate, so every state contributes several rows.

        ``read_ec_participation`` issues no ``ORDER BY``, so a last-wins lookup would
        make the whole cross-check depend on whichever candidate row the driver returned
        last. Both orderings must reach the same verdict.
        """
        base = ec_participation_frame([1876])
        colorado = base[base["state"] == "Colorado"].copy()
        stale = colorado.copy()
        stale["total_electoral_votes"] = 0
        for frame in (
            pd.concat([base, stale], ignore_index=True),
            pd.concat([stale, base], ignore_index=True),
        ):
            assert_catalog_matches_spine(frame, years=[1876])

    def test_string_years_are_coerced_rather_than_passing_vacuously(self) -> None:
        """``years=['1876']`` must not silently compare against nothing.

        Catalog keys are int-keyed and ``year`` is an int column, so an uncoerced string
        scope matches no catalog key *and* no spine row — every check then iterates an
        empty collection and the function reports agreement it never tested.
        """
        frame = ec_participation_frame([1876])
        frame.loc[frame["state"] == "Ohio", "total_electoral_votes"] = 0
        with pytest.raises(PVAbsenceCatalogError, match="not in the absence catalog"):
            assert_catalog_matches_spine(frame, years=["1876"])  # type: ignore[list-item]

    def test_a_non_boolean_is_total_raises_rather_than_yielding_nothing(self) -> None:
        frame = ec_participation_frame([1876])
        frame["is_total"] = frame["is_total"].map({False: "f", True: "t"})
        with pytest.raises(PVAbsenceCatalogError, match="non-boolean `is_total`"):
            assert_catalog_matches_spine(frame, years=[1876])


# --- the participation-frame guard, at the shared layer ----------------------


class TestParticipationShape:
    """A malformed spine frame must fail loudly, never yield an empty roster.

    These live here rather than only in ``test_pv_status.py`` because the curated path
    is the one with no PV facts downstream (#139 derives it in-process at snapshot build
    time), so ``assert_roster_covers_facts`` is not there to notice afterwards.
    """

    def test_string_is_total_yields_no_silent_empty_roster(self) -> None:
        """The dangerous case: every non-empty string is truthy under ``.astype(bool)``.

        Left unguarded, *no* row reads as data and the roster comes back empty with no
        error — indistinguishable downstream from "the EC spine was never loaded".
        """
        frame = ec_participation_frame([2020])
        frame["is_total"] = frame["is_total"].map({False: "f", True: "t"})
        with pytest.raises(PVAbsenceCatalogError, match="non-boolean `is_total`"):
            build_curated_roster(frame, source=SOURCE, years=[2020])

    @pytest.mark.parametrize("bad", [0, 1, "false"])
    def test_int_and_string_is_total_are_both_rejected(self, bad: object) -> None:
        frame = ec_participation_frame([2020])
        frame["is_total"] = bad
        with pytest.raises(PVAbsenceCatalogError, match="non-boolean `is_total`"):
            build_curated_roster(frame, source=SOURCE, years=[2020])

    def test_a_null_is_total_raises(self) -> None:
        frame = ec_participation_frame([2020])
        frame["is_total"] = frame["is_total"].astype("object")
        frame.loc[0, "is_total"] = None
        with pytest.raises(PVAbsenceCatalogError, match="null `is_total`"):
            build_curated_roster(frame, source=SOURCE, years=[2020])

    def test_a_year_with_no_spine_rows_raises_rather_than_truncating(self) -> None:
        """The converse of the phantom check, and it needs its own test.

        The phantom check only fires for years the catalog *mentions*, so a caller that
        reads the spine with the wrong ``years`` gets a silently truncated roster for
        every uncatalogued year — 2 of 3 requested elections here.
        """
        with pytest.raises(PVAbsenceCatalogError, match=r"\[1900, 1904\]"):
            build_curated_roster(
                ec_participation_frame([2020]),
                source=SOURCE,
                years=[1900, 1904, 2020],
            )

    def test_an_empty_year_set_raises(self) -> None:
        """Same "silence carries no information" failure as an uncurated year."""
        with pytest.raises(PVAbsenceCatalogError, match="no years at all"):
            build_curated_roster(
                ec_participation_frame([1824]), source=SOURCE, years=[]
            )

    def test_the_error_names_the_entry_point_the_caller_actually_called(self) -> None:
        """An operator greps the symbol in the message; it must be on their code path."""
        frame = ec_participation_frame([1824]).drop(columns=["is_total"])
        with pytest.raises(PVAbsenceCatalogError, match="build_curated_roster"):
            build_curated_roster(frame, source=SOURCE, years=[1824])
