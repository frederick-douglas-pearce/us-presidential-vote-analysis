"""Live-Postgres integration tests for the EC-left EC<->PV join (#69 / D026).

Excluded from the default suite by the ``integration`` marker; run with
``pytest -m integration`` against a real database. The join uses a window SUM and a
LEFT JOIN over a resolved view, so the live view is where the emitted SQL is proven to
behave like the pure oracle in ``tests/unit/test_join.py``.

Two tests, split by what each needs:

- **``test_join_resolves_a_synthetic_participant_set``** — the crux, **not** gated on the
  UCSB corpus. It seeds the real EC spine for 2016+2020, then loads a small **fabricated**
  PV union that reuses **real** canonical candidate/state names (so the D026 reciprocal
  anti-join precondition passes) — a winner+PV, a loser (a real 0-EV EC row) with PV, and
  a UCSB analysis-only row — and asserts the live
  ``ec_pv_preferred``/``ec_pv_redistributable`` views resolve exactly as D026 requires
  (no fan-out; loser EC 0 with PV; the UCSB row never on the redistributable surface).
  The counts are invented; only the names are real (D022 forbids UCSB *bytes*, not the
  string ``'UCSB'``).

- **``test_join_over_a_real_two_source_load``** — end-to-end, doubly gated
  (``integration`` + ``USVOTE_UCSB_HTML_DIR``): real MIT + UCSB for 2016+2020, then the
  join views, asserting no fan-out and the redistributable leak-guard over reconciled data.

Config + skip-if-unset come from the shared ``integration_db_config`` fixture.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import pytest

from tests._helpers import FIXTURES_DIR, MIT_FUSION_SAMPLE_CSV, fake_state_geo
from usvote.db import DBC
from usvote.getters import EC_GETTERS_WITHOUT_POPULAR_VOTE
from usvote.join import (
    EC_PV_PREFERRED_VIEW,
    EC_PV_REDISTRIBUTABLE_VIEW,
    JoinError,
    assert_db_pv_matches_ec,
    assert_winners_have_pv,
    create_ec_pv_views,
)
from usvote.load import SCHEMA
from usvote.pv.load import build_pv_union, load_pv_records
from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT, SOURCE_UCSB
from usvote.pv.views import PV_PREFERRED_VIEW

_CORPUS = os.environ.get("USVOTE_UCSB_HTML_DIR", "")


def _top_two_getters(dbc: DBC, year: int) -> tuple[str, str]:
    """The two highest-EV getters that year (winner, runner-up) by canonical name.

    Used to build a fabricated PV over *real* names: the runner-up is a getter who won
    no EC votes in some state the winner took (a loser-in-state), so a PV row for them
    there exercises the guarded EC-0 fill on live data.
    """
    got = dbc.select_query_to_df(
        f"SELECT c.name FROM {SCHEMA}.votes v "
        f"JOIN {SCHEMA}.candidate c ON v.candidate_id = c.candidate_id "
        f"WHERE v.is_total AND v.year = {year} "
        f"ORDER BY v.president_electoral_votes DESC LIMIT 2"
    )
    return got["name"].iloc[0], got["name"].iloc[1]


def _pv_row(
    source: str, year: int, state: str, candidate: str, votes: int
) -> dict[str, Any]:
    return {
        "source": source, "year": year, "state": state, "candidate": candidate,
        "party": "DEMOCRAT", "candidate_votes": votes,
        "state_total_votes": votes * 2, "reliability": "exact",
    }


@pytest.mark.integration
def test_join_resolves_a_synthetic_participant_set(
    integration_db_config: dict[str, Any],
) -> None:
    """Seed the EC spine, load a fabricated PV over real names, assert the live views."""
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbc = DBC(integration_db_config)
    try:
        # 1. Seed the real EC spine for 2016+2020.
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={2016, 2020},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )

        winner16, loser16 = _top_two_getters(dbc, 2016)   # Trump won Texas; runner-up did not
        _winner20, loser20 = _top_two_getters(dbc, 2020)  # Biden won California; runner-up did not

        # 2. Fabricated PV over REAL names: a winner+PV and a loser (a real 0-EV EC row,
        #    2016 Texas), plus a UCSB analysis-only loser (2020 California).
        union = pd.DataFrame([
            _pv_row(SOURCE_MIT, 2016, "Texas", winner16, 4_500_000),   # winner + PV
            _pv_row(SOURCE_MIT, 2016, "Texas", loser16, 3_800_000),    # loser, EC 0-row
            _pv_row(SOURCE_UCSB, 2020, "California", loser20, 6_000_000),  # UCSB analysis-only
        ])[list(SHARED_PV_COLUMNS)]
        load_pv_records(dbc, union, replace=False)
        build_pv_union(dbc)
        create_ec_pv_views(dbc)

        # No fan-out: one row per (year, state, candidate) in both views.
        for view in (EC_PV_PREFERRED_VIEW, EC_PV_REDISTRIBUTABLE_VIEW):
            dupes = dbc.select_query_to_df(
                f"SELECT year, state, candidate FROM {SCHEMA}.{view} "
                f"GROUP BY year, state, candidate HAVING count(*) > 1"
            )
            assert dupes.empty, f"{view} fanned out"

        # Loser: the 2016 Texas runner-up has a real EC 0-row (dense fact), PV attached —
        # exactly the row an EC-left join keeps (and the sparse-premise draft mis-handled).
        loser = dbc.select_query_to_df(
            f"SELECT president_electoral_votes AS ev, candidate_votes AS cv, source "
            f"FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW} "
            f"WHERE year = 2016 AND state = 'Texas' AND candidate = '{loser16}'"
        )
        assert loser["ev"].iloc[0] == 0
        assert loser["cv"].iloc[0] == 3_800_000
        assert loser["source"].iloc[0] == SOURCE_MIT

        # Winner+PV: the 2016 Texas winner has EC votes (EV > 0) and the PV attached.
        winner = dbc.select_query_to_df(
            f"SELECT president_electoral_votes AS ev, candidate_votes AS cv "
            f"FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW} "
            f"WHERE year = 2016 AND state = 'Texas' AND candidate = '{winner16}'"
        )
        assert winner["ev"].iloc[0] > 0
        assert winner["cv"].iloc[0] == 4_500_000

        # The UCSB analysis-only row IS in the preferred series (as UCSB), tagged
        # redistributable = false — a loser with EC 0.
        ucsb_pref = dbc.select_query_to_df(
            f"SELECT president_electoral_votes AS ev, source, redistributable "
            f"FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW} "
            f"WHERE year = 2020 AND state = 'California' AND candidate = '{loser20}'"
        )
        assert ucsb_pref["ev"].iloc[0] == 0
        assert ucsb_pref["source"].iloc[0] == SOURCE_UCSB
        assert not bool(ucsb_pref["redistributable"].iloc[0])

        # The public surface: NO UCSB row, and NO redistributable = false row ever.
        leak = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{EC_PV_REDISTRIBUTABLE_VIEW} "
            f"WHERE source = '{SOURCE_UCSB}' OR redistributable = false"
        )
        assert leak["n"].iloc[0] == 0
        # The EC row (2020, CA, loser20) still appears on the public surface — EC-left keeps
        # every EC state row — but the UCSB PV must NOT attach: its candidate_votes/source
        # stay NULL (pv_redistributable excludes UCSB), so the 6M UCSB votes never leak.
        pub = dbc.select_query_to_df(
            f"SELECT candidate_votes AS cv, source FROM "
            f"{SCHEMA}.{EC_PV_REDISTRIBUTABLE_VIEW} "
            f"WHERE year = 2020 AND state = 'California' AND candidate = '{loser20}'"
        )
        assert len(pub) == 1
        assert pd.isna(pub["cv"].iloc[0])
        assert pd.isna(pub["source"].iloc[0])

        # Reciprocal anti-join precondition: a PV row matching no EC votes row (an orphan
        # candidate) must fail loud — the EC-left join would otherwise silently drop it
        # (the guard the join owns, docs/canonical-keys.md). Inject one and confirm the
        # live guard raises.
        orphan = pd.DataFrame([
            _pv_row(SOURCE_MIT, 2016, "Texas", "Nonexistent Q. Candidate", 1),
        ])[list(SHARED_PV_COLUMNS)]
        load_pv_records(dbc, orphan, replace=False)
        with pytest.raises(JoinError, match="match no EC votes row"):
            assert_db_pv_matches_ec(dbc, PV_PREFERRED_VIEW)
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()


@pytest.mark.integration
@pytest.mark.skipif(
    not _CORPUS,
    reason="USVOTE_UCSB_HTML_DIR unset; the UCSB snapshot lives outside the repo (D022)",
)
def test_join_over_a_real_two_source_load(
    integration_db_config: dict[str, Any],
) -> None:
    """End-to-end: real MIT + real UCSB for 2016+2020, then the D026 join views.

    The only check that resolves the join over genuinely reconciled two-source data.
    Doubly gated so CI never touches the UCSB snapshot (D022).
    """
    from usvote.mit.pipeline import run_mit_pipeline
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir
    from usvote.ucsb.pipeline import run_ucsb_pipeline

    years = {2016, 2020}
    dbc = DBC(integration_db_config)
    try:
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years=years,
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )
        run_mit_pipeline(dbc, path=MIT_FUSION_SAMPLE_CSV, years={2016}, replace=False)
        run_ucsb_pipeline(dbc, _CORPUS, years=years, replace=False)
        build_pv_union(dbc)
        create_ec_pv_views(dbc)  # its reciprocal anti-join precondition runs here

        # No fan-out over real reconciled data (the raw-union double-count guard, live).
        for view in (EC_PV_PREFERRED_VIEW, EC_PV_REDISTRIBUTABLE_VIEW):
            dupes = dbc.select_query_to_df(
                f"SELECT year, state, candidate FROM {SCHEMA}.{view} "
                f"GROUP BY year, state, candidate HAVING count(*) > 1"
            )
            assert dupes.empty, f"{view} fanned out"

        # Losers are kept: a getter who won no EC votes in a state they contested is a real
        # 0-EV EC row with PV attached — the dense-fact rows the EC-left join preserves.
        losers = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW} "
            f"WHERE candidate_votes IS NOT NULL AND president_electoral_votes = 0"
        )
        assert losers["n"].iloc[0] > 0

        # The public surface never carries a non-redistributable row, over real data.
        leak = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{EC_PV_REDISTRIBUTABLE_VIEW} "
            f"WHERE source = '{SOURCE_UCSB}' OR redistributable = false"
        )
        assert leak["n"].iloc[0] == 0

        # Winner-has-PV coverage over the ANALYSIS series (the D026 crux guard, on real
        # reconciled data — the one path that catches a name-reconciliation miss where an
        # EC winner silently fails to match PV). Run on ec_pv_preferred only: UCSB is dense
        # across both corpus years, so the check is non-vacuous; ec_pv_redistributable
        # (MIT = the NY-only fusion sample here) would need a huge exemption set and is
        # deferred to E8 when the full MIT load lands. Exempt only the getters that
        # legitimately held no popular vote (the 2016 faithless set for this corpus).
        preferred = dbc.select_query_to_df(
            f"SELECT * FROM {SCHEMA}.{EC_PV_PREFERRED_VIEW}"
        )
        # Scope guard: the exemption set is curated for the 2016/2020 corpus, so fail loud
        # if a future corpus widening slips a year past it (rather than exempting silently).
        assert {int(y) for y in preferred["year"]} <= years, (
            "ec_pv_preferred carries a year outside the loaded corpus; widen the "
            "winner-has-PV exemption scope deliberately (EC_GETTERS_WITHOUT_POPULAR_VOTE)"
        )
        # A first real run may flag a genuine UCSB coverage gap — treat a modern flag as a
        # reconciliation miss to FIX, not an exemption to add (per the architect).
        inspected = assert_winners_have_pv(
            preferred, exemptions=EC_GETTERS_WITHOUT_POPULAR_VOTE
        )
        # Vacuity floor: 2016+2020 have ~100+ EC-winner state rows; a guard that inspected
        # near-zero would pass vacuously (mirrors this file's ``assert not both.empty``).
        assert inspected >= 50, f"winner-has-PV inspected only {inspected} rows (vacuous?)"
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
