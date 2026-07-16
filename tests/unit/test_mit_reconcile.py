"""Unit tests for :mod:`usvote.mit.reconcile` — MIT names -> canonical keys (#67).

Offline and data-free: reconcile operates on the D018 ``SHARED_PV_COLUMNS`` frame, so
these build small in-memory frames directly rather than reading a fixture. They lock
the curated candidate/state maps (RHS values pinned so drift from the EC spine is
caught), the 51-state coverage, the two-Bushes non-collision, and every
:class:`MITReconcileError` guard (unmapped value, grain collapse, shape).
"""

from __future__ import annotations

import pandas as pd
import pytest

from usvote.mit.reconcile import (
    MIT_CANDIDATE_RECONCILIATIONS,
    MIT_STATE_RECONCILIATIONS,
    MITReconcileError,
    reconcile_mit,
)
from usvote.mit.transform import SHARED_PV_COLUMNS


def make_frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    """Build a valid D018 ``SHARED_PV_COLUMNS`` frame from partial rows.

    Each row must carry ``year``/``state``/``candidate``; provenance and vote columns
    default to plausible constants (reconcile ignores everything but state/candidate,
    but the shape guard requires the full column set with no nulls).
    """
    filled = [
        {
            "source": "MIT",
            "year": r["year"],
            "state": r["state"],
            "candidate": r["candidate"],
            "party": r.get("party", "DEMOCRAT"),
            "candidate_votes": r.get("candidate_votes", 100),
            "state_total_votes": r.get("state_total_votes", 200),
            "reliability": "exact",
        }
        for r in rows
    ]
    return pd.DataFrame(filled)[list(SHARED_PV_COLUMNS)]


# The 18 distinct MIT D/R candidate strings transform_mit emits for 1976–2024, each
# paired with the EC canonical name (Archives Table 1 + the Dole correction). Pinned
# here so any drift between this map and the EC spine surfaces as a test failure.
EXPECTED_CANDIDATE_MAP = {
    "CARTER, JIMMY": "Jimmy Carter",
    "FORD, GERALD": "Gerald R. Ford",
    "REAGAN, RONALD": "Ronald Reagan",
    "MONDALE, WALTER": "Walter F. Mondale",
    "DUKAKIS, MICHAEL": "Michael S. Dukakis",
    "BUSH, GEORGE H.W.": "George Bush",
    "CLINTON, BILL": "William J. Clinton",
    "DOLE, ROBERT": "Robert Dole",
    "GORE, AL": "Albert Gore Jr.",
    "BUSH, GEORGE W.": "George W. Bush",
    "KERRY, JOHN": "John F. Kerry",
    "OBAMA, BARACK H.": "Barack Obama",
    "MCCAIN, JOHN": "John McCain",
    "ROMNEY, MITT": "Mitt Romney",
    "CLINTON, HILLARY": "Hillary Clinton",
    "TRUMP, DONALD J.": "Donald J. Trump",
    "BIDEN, JOSEPH R. JR": "Joseph R. Biden Jr.",
    "HARRIS, KAMALA D.": "Kamala D. Harris",
}


class TestCandidateMap:
    def test_map_matches_pinned_expectations(self) -> None:
        # Locks the RHS against the EC canonical names — the offline stand-in for
        # #69's live join guard (reciprocal check deferred to E6).
        assert MIT_CANDIDATE_RECONCILIATIONS == EXPECTED_CANDIDATE_MAP

    @pytest.mark.parametrize(
        ("mit_name", "canonical"),
        [
            ("CARTER, JIMMY", "Jimmy Carter"),        # early year
            ("FORD, GERALD", "Gerald R. Ford"),       # EC adds a middle initial
            ("OBAMA, BARACK H.", "Barack Obama"),     # MIT middle initial dropped
            ("CLINTON, BILL", "William J. Clinton"),  # given-name substitution
            ("GORE, AL", "Albert Gore Jr."),          # given name + suffix
            ("DOLE, ROBERT", "Robert Dole"),          # Bob->Robert EC correction
            ("HARRIS, KAMALA D.", "Kamala D. Harris"),  # most recent year
        ],
    )
    def test_representative_candidate_reconciliations(
        self, mit_name: str, canonical: str
    ) -> None:
        out = reconcile_mit(make_frame([{"year": 2000, "state": "OHIO", "candidate": mit_name}]))
        assert out.iloc[0]["candidate"] == canonical

    def test_two_bushes_map_to_distinct_names(self) -> None:
        # The same-name-collision hazard (docs/canonical-keys.md): a future edit must
        # not collapse the elder and younger Bush onto one canonical name.
        elder = MIT_CANDIDATE_RECONCILIATIONS["BUSH, GEORGE H.W."]
        younger = MIT_CANDIDATE_RECONCILIATIONS["BUSH, GEORGE W."]
        assert elder == "George Bush"
        assert younger == "George W. Bush"
        assert elder != younger

    def test_map_covers_exactly_18_nominees(self) -> None:
        assert len(MIT_CANDIDATE_RECONCILIATIONS) == 18


class TestStateMap:
    def test_covers_all_51_jurisdictions(self) -> None:
        assert len(MIT_STATE_RECONCILIATIONS) == 51

    def test_all_states_reconcile(self) -> None:
        rows = [
            {"year": 2020, "state": s, "candidate": "BIDEN, JOSEPH R. JR"}
            for s in MIT_STATE_RECONCILIATIONS
        ]
        out = reconcile_mit(make_frame(rows))
        assert set(out["state"]) == set(MIT_STATE_RECONCILIATIONS.values())

    def test_dc_lowercase_of_not_titlecase(self) -> None:
        # .title() would wrongly yield "District Of Columbia"; the map must not.
        out = reconcile_mit(
            make_frame([{"year": 2020, "state": "DISTRICT OF COLUMBIA",
                         "candidate": "BIDEN, JOSEPH R. JR"}])
        )
        assert out.iloc[0]["state"] == "District of Columbia"


class TestShapePreserved:
    def test_columns_grain_and_row_count_unchanged(self) -> None:
        frame = make_frame([
            {"year": 2016, "state": "MICHIGAN", "candidate": "TRUMP, DONALD J."},
            {"year": 2016, "state": "MICHIGAN", "candidate": "CLINTON, HILLARY"},
            {"year": 2020, "state": "GEORGIA", "candidate": "BIDEN, JOSEPH R. JR"},
        ])
        out = reconcile_mit(frame)
        assert list(out.columns) == list(SHARED_PV_COLUMNS)
        assert len(out) == 3
        # unchanged columns pass through verbatim
        assert list(out["candidate_votes"]) == list(frame["candidate_votes"])

    def test_many_to_one_alt_spelling_supported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Fred's Q1: two distinct MIT strings for one person → one canonical name is
        # fine (map values need not be unique). Simulate an alternate spelling for a
        # different election year; both must reconcile to the same canonical name and
        # the grain must hold (distinct year/state keeps them separate rows).
        patched = {**MIT_CANDIDATE_RECONCILIATIONS, "CLINTON, WILLIAM J.": "William J. Clinton"}
        monkeypatch.setattr(
            "usvote.mit.reconcile.MIT_CANDIDATE_RECONCILIATIONS", patched
        )
        out = reconcile_mit(make_frame([
            {"year": 1992, "state": "OHIO", "candidate": "CLINTON, BILL"},
            {"year": 1996, "state": "OHIO", "candidate": "CLINTON, WILLIAM J."},
        ]))
        assert list(out["candidate"]) == ["William J. Clinton", "William J. Clinton"]


class TestGuards:
    def test_unmapped_state_raises(self) -> None:
        with pytest.raises(MITReconcileError, match="PUERTO RICO"):
            reconcile_mit(
                make_frame([{"year": 2020, "state": "PUERTO RICO",
                             "candidate": "BIDEN, JOSEPH R. JR"}])
            )

    def test_unmapped_candidate_raises(self) -> None:
        with pytest.raises(MITReconcileError, match="NADER, RALPH"):
            reconcile_mit(
                make_frame([{"year": 2000, "state": "OHIO", "candidate": "NADER, RALPH"}])
            )

    def test_grain_collapse_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Two distinct MIT strings mapping to the SAME canonical name within one
        # (year, state) would double-count downstream — must raise, not silently pass.
        patched = {**MIT_CANDIDATE_RECONCILIATIONS, "BILL CLINTON": "William J. Clinton"}
        monkeypatch.setattr(
            "usvote.mit.reconcile.MIT_CANDIDATE_RECONCILIATIONS", patched
        )
        with pytest.raises(MITReconcileError, match="grain violated"):
            reconcile_mit(make_frame([
                {"year": 1992, "state": "OHIO", "candidate": "CLINTON, BILL"},
                {"year": 1992, "state": "OHIO", "candidate": "BILL CLINTON"},
            ]))
