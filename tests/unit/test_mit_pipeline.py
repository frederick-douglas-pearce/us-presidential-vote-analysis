"""Unit tests for the MIT pipeline wiring (``usvote.mit.pipeline``).

Drives read -> transform -> reconcile -> load over the offline fusion fixture against
the recording fake connection (no live Postgres), asserting the four stages compose:
the raw CSV becomes reconciled, canonical-key PV rows loaded into ``dwh.pv_votes``,
correctly scoped by ``years`` and stamped with MIT provenance. The load into a real
database lives in ``tests/integration/test_pv_load.py``.

Since #127 the pipeline also derives and loads its D024 roster from the **EC spine**,
so these tests stub :func:`usvote.spine.read_ec_participation` on the pipeline module
(the pattern ``test_ucsb_pipeline.py`` already uses) — the fake connection cannot serve
a real participation frame, and stubbing it lets each test state exactly which states
the spine believes participated.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import (
    MIT_FUSION_SAMPLE_CSV,
    RecordingConnection,
    make_dbc,
    record_inserts,
)
from usvote.mit import pipeline as mit_pipeline
from usvote.mit.pipeline import MITRosterError, run_mit_pipeline
from usvote.pv.schema import PV_SCHEMA, PV_TABLE, SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT
from usvote.pv.status import (
    PV_STATUS_POPULAR_VOTE,
    ROSTER_COLUMNS,
    ROSTER_SCHEMA,
    ROSTER_TABLE,
)

#: The states the fusion fixture's two years actually carry, as the EC spine would
#: report them: 2000 Florida and 2016 New York, plus each year's totals row (``state``
#: NULL / ``is_total`` true) so the exclusion is exercised on every run.
_SPINE_ROWS = [
    {"year": 2000, "state": "Florida", "is_total": False},
    {"year": 2000, "state": None, "is_total": True},
    {"year": 2016, "state": "New York", "is_total": False},
    {"year": 2016, "state": None, "is_total": True},
]


def _stub_spine(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, object]] | None = None
) -> dict[str, object]:
    """Stub ``read_ec_participation`` on the pipeline module; record the years it got."""
    seen: dict[str, object] = {}
    frame = pd.DataFrame(_SPINE_ROWS if rows is None else rows)

    def participation(dbc: object, *, years: object = None) -> pd.DataFrame:
        seen["years"] = years
        return frame.copy()

    monkeypatch.setattr(mit_pipeline, "read_ec_participation", participation)
    return seen


def test_pipeline_scopes_to_years_and_reconciles(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    _stub_spine(monkeypatch)
    # Scoped to 2016 → the fusion fixture's New York rows only. After the D019
    # {DEMOCRAT, REPUBLICAN} scope + fusion aggregation that is exactly Clinton and
    # Trump, reconciled onto the canonical EC names.
    loaded, roster = run_mit_pipeline(
        make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV, years={2016}
    )

    assert loaded["year"].unique().tolist() == [2016]
    assert set(loaded["candidate"]) == {"Hillary Clinton", "Donald J. Trump"}
    assert set(loaded["state"]) == {"New York"}
    # Provenance stamped; every row exact (MIT).
    assert set(loaded["source"]) == {"MIT"}
    assert set(loaded["reliability"]) == {"exact"}
    # Clinton's fusion lines summed into her main total (4379789 + 140041 + 36294).
    clinton = loaded.loc[loaded["candidate"] == "Hillary Clinton", "candidate_votes"]
    assert clinton.iloc[0] == 4556124
    # #127: the roster is the mechanical SELECT DISTINCT over the EC spine's
    # participating (year, state) keys — one all-``popular_vote`` row for the single
    # state this scope covers, with the year's totals row correctly excluded.
    assert list(roster.columns) == list(ROSTER_COLUMNS)
    assert roster[["year", "state", "pv_status"]].values.tolist() == [
        [2016, "New York", PV_STATUS_POPULAR_VOTE]
    ]
    assert set(roster["source"]) == {SOURCE_MIT}
    assert roster["note"].isna().all()


def test_pipeline_creates_pv_table_and_inserts(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    inserts = record_inserts(monkeypatch)
    _stub_spine(monkeypatch)
    run_mit_pipeline(make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV, years={2016})

    assert any(
        q.startswith(f"CREATE TABLE IF NOT EXISTS {PV_SCHEMA}.{PV_TABLE}")
        for q in recording_conn.executed
    )
    assert any(
        q.startswith(f"CREATE TABLE IF NOT EXISTS {ROSTER_SCHEMA}.{ROSTER_TABLE}")
        for q in recording_conn.executed
    )
    # #127: both PV tables are written, roster first — the same order (and the same
    # single ``replace`` flag) run_ucsb_pipeline uses, so its state FK to dwh.state is
    # resolved before the fact rows land.
    assert [sql.split()[2] for sql, _ in inserts] == [
        f"{ROSTER_SCHEMA}.{ROSTER_TABLE}",
        f"{PV_SCHEMA}.{PV_TABLE}",
    ]


def test_pipeline_loads_in_one_transaction(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every pipeline owns its DB-write transaction (#84a), so the #84b orchestrator can
    # sequence them without nesting. Since #127 MIT's load is create-schema +
    # create-table + insert for BOTH shared PV tables; wrapped, that is exactly ONE
    # commit, so the D024 two-way roster/fact invariant can never be left half-written
    # (the property run_ucsb_pipeline already had). Removing the ``with
    # dbc.transaction():`` would make each statement commit on its own and push this
    # above 1.
    record_inserts(monkeypatch)
    _stub_spine(monkeypatch)
    run_mit_pipeline(make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV, years={2016})

    assert recording_conn.commits == 1
    assert recording_conn.rollbacks == 0


def test_pipeline_without_year_filter_loads_all_years(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    _stub_spine(monkeypatch)
    loaded, roster = run_mit_pipeline(
        make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV
    )

    # The fixture covers 2000 FL (Bush, Gore) + 2016 NY (Clinton, Trump) — four D/R
    # rows after scoping, spanning both years. The returned frame is the shared shape
    # (pv_id is DB-assigned, so it is not a column here).
    assert set(loaded["year"]) == {2000, 2016}
    assert list(loaded.columns) == list(SHARED_PV_COLUMNS)
    assert len(loaded) == 4
    # One roster row per distinct (year, state): 2000 Florida + 2016 New York.
    assert roster[["year", "state"]].values.tolist() == [
        [2000, "Florida"],
        [2016, "New York"],
    ]
    assert set(roster["pv_status"]) == {PV_STATUS_POPULAR_VOTE}


def test_years_is_a_filter_not_a_demand(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A requested year the CSV lacks is absent, not a failure — and must stay so.

    ``run_warehouse`` threads **one** year set to every source, but MIT's CSV covers a
    different span than the EC spine, so a year present for EC and absent for MIT is
    routine (``tests/integration/test_ec_pv_join.py`` depends on exactly this:
    ``years={2016, 2020}`` against a sample holding no 2020). The D024 assert therefore
    takes its in-scope set from the **loaded frame**; scoping it to the *requested*
    years instead turns this documented filter into a hard failure on the shipped
    warehouse path — which is precisely what the integration suite caught.
    """
    record_inserts(monkeypatch)
    _stub_spine(monkeypatch)
    loaded, roster = run_mit_pipeline(
        make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV, years={2016, 1900}
    )

    assert set(loaded["year"]) == {2016}
    assert set(roster["year"]) == {2016}


def test_pipeline_raises_clearly_when_no_rows_for_requested_years(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A years set disjoint from the file must fail with a clear, actionable message
    # naming the covered years — not an opaque MITTransformError deep in transform.
    record_inserts(monkeypatch)
    _stub_spine(monkeypatch)
    with pytest.raises(ValueError, match=r"no MIT rows for requested years.*covers"):
        run_mit_pipeline(
            make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV, years={1900}
        )


def test_a_state_the_spine_has_but_mit_lost_fails_the_load(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The payoff of deriving the roster from the spine** (D024 §7, decisions.md).

    The spine says Ohio participated in 2016; MIT's fixture has no Ohio rows, standing
    in for a state lost during transform (``_drop_unattributable_rows``, the D019 party
    filter, a join that dropped it). Because the roster comes from the spine and not
    from MIT's own facts, Ohio lands as a ``popular_vote`` roster state with no vote
    rows and the load fails loudly.

    Derived from MIT's own facts the roster would have lost Ohio too, both sides would
    have agreed, and 2016 would silently report ``pv_coverage`` below ``1.0`` on the
    public surface. No sum validator can see that (the total went missing with the
    state), and #69's join-side guard cannot either — it is a PV→EC anti-join, so it
    finds phantom rows, not missing ones.
    """
    record_inserts(monkeypatch)
    _stub_spine(
        monkeypatch,
        [
            {"year": 2016, "state": "New York", "is_total": False},
            {"year": 2016, "state": "Ohio", "is_total": False},  # MIT never loads it
        ],
    )

    with pytest.raises(MITRosterError, match=r"have no vote rows.*Ohio"):
        run_mit_pipeline(
            make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV, years={2016}
        )
    # And nothing was written: the guard runs before the transaction opens.
    assert recording_conn.commits == 0


def test_the_spine_read_is_scoped_to_the_years_mit_actually_loaded(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scoped, so a whole-warehouse spine is not dragged in for a one-year MIT load."""
    record_inserts(monkeypatch)
    seen = _stub_spine(monkeypatch)
    run_mit_pipeline(make_dbc(recording_conn), path=MIT_FUSION_SAMPLE_CSV, years={2016})

    assert seen["years"] == frozenset({2016})
