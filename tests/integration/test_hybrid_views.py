"""Live-Postgres integration tests for the materialized hybrid views (#124 / E7-S5).

Excluded from the default suite by the ``integration`` marker; run with
``pytest -m integration`` against a real database.

**Why these tests carry unusual weight.** ``usvote/hybrid.py`` now holds *two* expressions
of one derivation — the SQL builders that drive the live views, and the pandas builders
that were there first. Every view-creation precondition
(:func:`~usvote.hybrid.create_hybrid_views`) runs over the **pandas** side, so a drift
between the two passes all of them and leaves the view quietly wrong. Nothing offline can
catch that either: the unit tests assert the SQL's *shape* as a string. These are the only
checks that ever run the emitted SQL.

Two tests, split by what each needs:

- **``test_the_live_views_match_the_pandas_oracle``** — the crux, and deliberately **not**
  gated on any corpus, so it runs on any integration box. It seeds the real EC spine for
  2016+2020+2024 and a fabricated PV union over **real** canonical names, shaped so that
  the intricate NULL branches are actually exercised rather than assumed: a
  partial-coverage year, a year with a single scored candidate, and a year with no popular
  vote at all. Then it reads both grains back from all four views and compares them to the
  oracle over the same input. The counts are invented; only the names are real (D022
  forbids UCSB *bytes*, not the string ``'UCSB'``).

- **``test_hybrid_views_over_a_real_full_warehouse``** — the AC-6 acceptance test, gated on
  the three local corpora. It builds a real 51-year EC + MIT + UCSB warehouse and pins the
  2000/2016 flips against **real national figures** (which #123's hand-picked subsets could
  not), the twelve partial-coverage years and their EV-weighted values, and 1824 under both
  coverage policies.

Config + skip-if-unset come from the shared ``integration_db_config`` fixture.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import pytest

from tests._helpers import FIXTURES_DIR, fake_state_geo
from usvote import hybrid
from usvote.db import DBC
from usvote.join import (
    EC_PV_PREFERRED_VIEW,
    EC_PV_REDISTRIBUTABLE_VIEW,
    create_ec_pv_views,
)
from usvote.load import SCHEMA
from usvote.pv.load import build_pv_union, load_pv_records, load_pv_status
from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT, SOURCE_UCSB
from usvote.pv.status import (
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_POPULAR_VOTE,
    ROSTER_COLUMNS,
)

_EC_CORPUS = os.environ.get("USVOTE_EC_HTML_DIR", "")
_UCSB_CORPUS = os.environ.get("USVOTE_UCSB_HTML_DIR", "")
_MIT_CSV = os.environ.get("USVOTE_MIT_CSV_PATH", "")
_SHAPEFILE = os.environ.get("USVOTE_SHAPEFILE_PATH", "")

#: The verified twelve — years carrying at least one ``legislature_chosen`` state, so
#: ``pv_coverage < 1.0`` — with their EV-weighted values. Published in
#: ``docs/pv-coverage.md`` (#125 / #162) and carried onto #124 as an explicit acceptance
#: item; this is the code guarantee that doc's prose points at.
PARTIAL_COVERAGE_YEARS: dict[int, tuple[int, int]] = {
    1824: (190, 261),
    1828: (247, 261),
    1832: (277, 288),
    1836: (283, 294),
    1840: (283, 294),
    1844: (266, 275),
    1848: (281, 290),
    1852: (288, 296),
    1856: (288, 296),
    1860: (295, 303),
    1868: (291, 294),
    1876: (366, 369),
}


def _pv_row(
    source: str, year: int, state: str, candidate: str, votes: int, total: int
) -> dict[str, Any]:
    return {
        "source": source,
        "year": year,
        "state": state,
        "candidate": candidate,
        "party": "DEMOCRAT",
        "candidate_votes": votes,
        "state_total_votes": total,
        "reliability": "exact",
    }


def _top_two_getters(dbc: DBC, year: int) -> tuple[str, str]:
    """The two highest-EV getters that year (winner, runner-up) by canonical name."""
    got = dbc.select_query_to_df(
        f"SELECT c.name FROM {SCHEMA}.votes v "
        f"JOIN {SCHEMA}.candidate c ON v.candidate_id = c.candidate_id "
        f"WHERE v.is_total AND v.year = {year} "
        f"ORDER BY v.president_electoral_votes DESC LIMIT 2"
    )
    return got["name"].iloc[0], got["name"].iloc[1]


def _states(dbc: DBC, year: int) -> list[str]:
    got = dbc.select_query_to_df(
        f"SELECT DISTINCT state FROM {SCHEMA}.votes "
        f"WHERE year = {year} AND state IS NOT NULL ORDER BY state"
    )
    return [str(s) for s in got["state"]]


def _normalize_nulls(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse ``pd.NA`` / ``NaN`` / ``None`` to one sentinel in **object** columns.

    Narrowly scoped on purpose. The two expressions genuinely disagree on how they
    *spell* a null in an object column — psycopg2 hands back a Python ``None`` for a
    NULL boolean while :func:`usvote.hybrid._flip` returns ``pd.NA`` — and
    ``assert_frame_equal`` treats those as different values. They are the same value.

    **What this does not do is soften the comparison.** Null-vs-non-null stays exact, so
    a view that returned ``false`` where the oracle returns NULL — the precise defect
    :func:`usvote.hybrid._flip` exists to prevent — still fails. Only the choice of null
    object is normalized, and only where pandas has no typed null to begin with.
    """
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].where(out[col].notna(), None)
    return out


def _corpus_fetch(html_dir: str) -> Any:
    """A ``Fetch`` replaying the local Archives corpus, verified complete first."""
    from usvote import scrape

    scrape.assert_corpus_covers_years(html_dir)
    return scrape.fetch_from_corpus(html_dir)


def _same_frame(live: pd.DataFrame, oracle: pd.DataFrame, key: list[str]) -> None:
    """Assert two frames agree on every column, ignoring dtype and row order.

    Dtypes legitimately differ across the seam — Postgres hands back ``bigint`` where
    pandas held ``float64`` after a NULL-bearing sum — so comparing them would fail on a
    difference that is not a difference. Values, NULLs and column order are compared
    exactly (see :func:`_normalize_nulls` for the one narrow exception); floats within
    ``rtol``.
    """
    assert list(live.columns) == list(oracle.columns), "column contract drifted"
    left = _normalize_nulls(live.sort_values(key, kind="stable").reset_index(drop=True))
    right = _normalize_nulls(
        oracle.sort_values(key, kind="stable").reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(
        left, right, check_dtype=False, check_like=False, rtol=1e-9
    )


@pytest.mark.integration
def test_the_live_views_match_the_pandas_oracle(
    integration_db_config: dict[str, Any],
) -> None:
    """The differential test: the emitted SQL must *be* the pandas derivation.

    Shaped so the NULL branches are exercised, because those are where the two
    expressions most plausibly diverge and nothing else would notice:

    - **2016** — full PV for the top two getters, but one state marked
      ``legislature_chosen`` in the roster, so ``pv_coverage < 1.0`` (the coverage
      ``CASE``'s middle leg) and both margins are real.
    - **2020** — PV for the runner-up **only**: one scored candidate, so ``pv_margin`` and
      ``hybrid_margin`` must be NULL rather than ``top1 - 0``, while ``pv_flip`` is
      ``true``.
    - **2024** — no PV and no roster row at all: NULL winners, NULL margins, and a NULL
      ``pv_coverage`` via the roster-*absent* leg (which must not read as ``0.0``).
    """
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbc = DBC(integration_db_config)
    try:
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={2016, 2020, 2024},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )

        winner16, loser16 = _top_two_getters(dbc, 2016)
        _winner20, loser20 = _top_two_getters(dbc, 2020)
        assert winner16 != loser16

        states16 = _states(dbc, 2016)
        # The legislature-chosen state gets no PV row, which is what such a state means.
        chosen16 = states16[0]
        voting16 = states16[1:4]

        rows = [
            _pv_row(SOURCE_MIT, 2016, s, c, votes, 1_000_000)
            for s in voting16
            for c, votes in ((winner16, 600_000), (loser16, 400_000))
        ]
        # 2020: the runner-up alone carries a popular vote -> exactly one scored
        # candidate, so both PV-side margins must come back NULL.
        rows += [
            _pv_row(SOURCE_MIT, 2020, s, loser20, 500_000, 900_000)
            for s in _states(dbc, 2020)[:3]
        ]
        # A UCSB row on a 2016 state carrying NO MIT row, so the preferred and
        # redistributable surfaces genuinely differ and the public one is provably
        # computed off the public join view rather than filtered afterwards.
        #
        # The state must be MIT-free: ``pv_preferred`` resolves the 1976-2024 overlap to
        # MIT (D017), so a UCSB row on a key MIT already covers is superseded and both
        # surfaces would read identically -- which is the resolution working, not a leak.
        ucsb_state = states16[4]
        assert ucsb_state not in voting16 and ucsb_state != chosen16
        rows.append(
            _pv_row(SOURCE_UCSB, 2016, ucsb_state, winner16, 610_000, 1_010_000)
        )
        load_pv_records(
            dbc, pd.DataFrame(rows)[list(SHARED_PV_COLUMNS)], replace=False
        )

        roster = [
            {"source": SOURCE_MIT, "year": 2016, "state": s, "note": None,
             "pv_status": (
                 PV_STATUS_LEGISLATURE_CHOSEN if s == chosen16
                 else PV_STATUS_POPULAR_VOTE
             )}
            for s in states16
        ] + [
            {"source": SOURCE_MIT, "year": 2020, "state": s,
             "pv_status": PV_STATUS_POPULAR_VOTE, "note": None}
            for s in _states(dbc, 2020)
        ]
        # Deliberately NO 2024 roster row -- that is the roster-absent leg.
        load_pv_status(dbc, pd.DataFrame(roster)[list(ROSTER_COLUMNS)], replace=False)

        build_pv_union(dbc)
        create_ec_pv_views(dbc)
        hybrid.create_hybrid_views(dbc)

        for join_view, candidate_view, summary_view in hybrid.HYBRID_SURFACES:
            oracle_frame, oracle_summary = hybrid.build_hybrid_from_db(
                dbc, view=join_view
            )
            live_frame = dbc.select_query_to_df(
                f"SELECT * FROM {SCHEMA}.{candidate_view}"
            )
            live_summary = dbc.select_query_to_df(
                f"SELECT * FROM {SCHEMA}.{summary_view}"
            )
            _same_frame(
                live_frame, oracle_frame, list(hybrid.HYBRID_CANDIDATE_GRAIN)
            )
            _same_frame(
                live_summary, oracle_summary, list(hybrid.HYBRID_SUMMARY_GRAIN)
            )

        # --- the NULL branches, asserted directly on the LIVE view ------------
        # (the comparison above would pass if BOTH expressions were wrong the same way
        # for a structural reason; these pin the intended values independently)
        summary = dbc.select_query_to_df(
            f"SELECT * FROM {SCHEMA}.{hybrid.HYBRID_SUMMARY_PREFERRED_VIEW}"
        ).set_index("year")

        # 2016: partial coverage -- strictly between 0 and 1, not NULL and not 1.0.
        assert 0.0 < summary.loc[2016, "pv_coverage"] < 1.0
        assert summary.loc[2016, "pv_margin"] is not None
        assert float(summary.loc[2016, "pv_margin"]) > 0.0

        # 2020: one scored candidate -> NULL margins, but a real (flipped) PV winner.
        assert summary.loc[2020, "pv_winner"] == loser20
        assert pd.isna(summary.loc[2020, "pv_margin"]), "top1 - 0 is not a margin"
        assert pd.isna(summary.loc[2020, "hybrid_margin"])
        assert bool(summary.loc[2020, "pv_flip"]) is True
        assert summary.loc[2020, "pv_coverage"] == 1.0

        # 2024: no PV at all -> NULL winners/flips/margins, and coverage UNKNOWN (the
        # roster reaches no 2024 state), which must never read as a known 0.0.
        assert pd.isna(summary.loc[2024, "pv_winner"])
        assert pd.isna(summary.loc[2024, "hybrid_winner"])
        assert pd.isna(summary.loc[2024, "pv_flip"]), "no winner is NULL, never true"
        assert pd.isna(summary.loc[2024, "hybrid_flip"])
        assert pd.isna(summary.loc[2024, "pv_margin"])
        assert pd.isna(summary.loc[2024, "pv_coverage"])
        # The EC half is unaffected by the PV gap -- this is the D037/A split.
        assert summary.loc[2024, "ec_winner"] is not None
        assert summary.loc[2024, "ec_margin"] > 0.0

        # --- the numeric-cast check a string test cannot make -----------------
        # Without ``::double precision`` Postgres integer-divides and every share reads
        # 0. Assert a real fraction, not merely "a column exists".
        shares = dbc.select_query_to_df(
            f"SELECT ec_share_full FROM {SCHEMA}.{hybrid.HYBRID_PREFERRED_VIEW} "
            f"WHERE year = 2016 AND candidate = '{winner16}'"
        )
        assert 0.0 < float(shares["ec_share_full"].iloc[0]) < 1.0

        # --- the two surfaces really are different computations ---------------
        pref = dbc.select_query_to_df(
            f"SELECT national_pv_votes AS v FROM "
            f"{SCHEMA}.{hybrid.HYBRID_PREFERRED_VIEW} "
            f"WHERE year = 2016 AND candidate = '{winner16}'"
        )["v"].iloc[0]
        pub = dbc.select_query_to_df(
            f"SELECT national_pv_votes AS v FROM "
            f"{SCHEMA}.{hybrid.HYBRID_REDISTRIBUTABLE_VIEW} "
            f"WHERE year = 2016 AND candidate = '{winner16}'"
        )["v"].iloc[0]
        assert pref > pub, (
            "the UCSB row must reach the preferred surface and never the public one"
        )

        # Idempotent: a second create over an existing warehouse is a no-op, which is
        # what ``rebuild_views`` relies on after every load (AC-1).
        hybrid.create_hybrid_views(dbc)
        again = dbc.select_query_to_df(
            f"SELECT * FROM {SCHEMA}.{hybrid.HYBRID_SUMMARY_PREFERRED_VIEW}"
        ).set_index("year")
        assert len(again) == len(summary)
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()


@pytest.mark.integration
@pytest.mark.skipif(
    not (_EC_CORPUS and _UCSB_CORPUS and _MIT_CSV and _SHAPEFILE),
    reason=(
        "needs the full local corpora: USVOTE_EC_HTML_DIR, USVOTE_UCSB_HTML_DIR, "
        "USVOTE_MIT_CSV_PATH, USVOTE_SHAPEFILE_PATH"
    ),
)
def test_hybrid_views_over_a_real_full_warehouse(
    integration_db_config: dict[str, Any],
) -> None:
    """AC-6: both grains end-to-end over a real 51-year EC + MIT + UCSB warehouse.

    This is the only place the derivation meets **real national figures**, which is
    exactly the gap #123's acceptance gate left open: its 2000 and 2016 fixtures are
    hand-picked four- and six-state subsets, and its verdict was that *"no test would
    catch a pipeline that got 2000 or 2016 wrong on real data."*

    **2000's hybrid answer is expected to differ from #123's unit fixture, and that is
    the point of this test rather than a regression.** #123's fixture uses two-way state
    totals (third parties omitted); on the real national figures Nader's votes sit in the
    denominator and dilute Gore's popular-vote share, so the hybrid does **not** go to
    Gore (Bush 0.4908 to Gore 0.4887) even though the popular vote does.
    """
    from usvote.warehouse import run_warehouse

    dbc = DBC(integration_db_config)
    try:
        result = run_warehouse(
            dbc,
            _SHAPEFILE,
            _MIT_CSV,
            ucsb_html_dir=_UCSB_CORPUS,
            replace=True,
            environ=dict(os.environ),
            # The local Archives corpus (#89), not ``fetch_from_dir`` — the corpus has
            # its own ``<year>.html`` + ``_index_results.html`` layout, and
            # ``assert_corpus_covers_years`` fails loud on a corpus missing a year
            # rather than quietly building a warehouse short that year.
            fetch=_corpus_fetch(_EC_CORPUS),
        )
        assert result.views_built
        # Non-vacuity: the coverage assertions below are roster-driven, and only UCSB
        # supplies pre-1976 roster rows -- a two-source build would leave them NULL and
        # the set-equality would fail for the wrong reason.
        assert result.sources_loaded == frozenset({"ec", "mit", "ucsb"})
        assert result.ucsb_roster_rows and result.ucsb_roster_rows > 0

        summary = dbc.select_query_to_df(
            f"SELECT * FROM {SCHEMA}.{hybrid.HYBRID_SUMMARY_PREFERRED_VIEW}"
        ).set_index("year")
        candidates = dbc.select_query_to_df(
            f"SELECT * FROM {SCHEMA}.{hybrid.HYBRID_PREFERRED_VIEW}"
        )

        # --- both grains are populated and unique -----------------------------
        assert len(summary) == 51, "the full EC span must be present"
        hybrid.assert_no_fan_out(candidates, hybrid.HYBRID_CANDIDATE_GRAIN)
        hybrid.assert_no_fan_out(
            summary.reset_index(), hybrid.HYBRID_SUMMARY_GRAIN
        )

        # --- C1: the 2000 and 2016 flips, on REAL national figures ------------
        assert bool(summary.loc[2016, "pv_flip"]) is True
        assert summary.loc[2016, "ec_winner"] != summary.loc[2016, "pv_winner"]
        assert bool(summary.loc[2000, "pv_flip"]) is True
        assert summary.loc[2000, "pv_winner"] != summary.loc[2000, "ec_winner"]
        # The trap #123 documented and deliberately did not assert: on the real
        # national denominators the hybrid does NOT follow the popular vote in 2000.
        assert bool(summary.loc[2000, "hybrid_flip"]) is False, (
            "Nader's votes dilute Gore's PV share on the real national denominator — "
            "the two-way unit fixture points the other way, which is why this test "
            "exists"
        )

        # --- C3: the twelve partial-coverage years, exactly ------------------
        below_one = set(
            summary.index[summary["pv_coverage"].astype("Float64") < 1.0].tolist()
        )
        assert below_one == set(PARTIAL_COVERAGE_YEARS), (
            "the set of partial-coverage years drifted from docs/pv-coverage.md"
        )
        for year, (covered, appointed) in PARTIAL_COVERAGE_YEARS.items():
            assert float(summary.loc[year, "pv_coverage"]) == pytest.approx(
                covered / appointed, abs=1e-6
            ), f"{year} coverage"
            assert int(summary.loc[year, "ec_denominator"]) == appointed

        # Every other year is exactly 1.0 -- without this, a year *leaving* the set
        # would pass the set-equality above unnoticed.
        others = summary.drop(index=list(PARTIAL_COVERAGE_YEARS))
        assert len(others) == 39
        assert (others["pv_coverage"].astype("Float64") == 1.0).all()

        # 1864 reads 1.0, NOT below it: its eleven not_participating states carry 0
        # electoral votes, so they contribute to neither side of the ratio. The one
        # case where an intuition-driven assert goes the wrong way (#125's first draft
        # did exactly that, caught at the architect gate).
        assert float(summary.loc[1864, "pv_coverage"]) == 1.0

        # --- C2: 1824 under BOTH coverage policies ---------------------------
        # The views materialize (b) only; (c) is reachable from Python alone, which is
        # what keeps the public surface's treatment fixed (D038/D049). So the (c) leg
        # is asserted through the builder over the same live warehouse.
        ec_pv = hybrid.read_ec_pv_join(dbc, view=EC_PV_PREFERRED_VIEW)
        roster = hybrid.read_pv_status_roster(
            dbc, sources=set(ec_pv["source"].dropna().unique())
        )
        for policy in hybrid.COVERAGE_POLICIES:
            frame = hybrid.build_hybrid_frame(ec_pv, roster, policy=policy)
            row = hybrid.build_hybrid_summary(frame).set_index("year").loc[1824]
            assert row["hybrid_winner"] == "Andrew Jackson", (
                f"1824's hybrid winner must be invariant under policy {policy}"
            )
            assert row["ec_winner"] == "Andrew Jackson"
            # The House installed Adams; the EC leader was Jackson. Both are correct,
            # and ec_determinative is what says the EC did not settle it.
            assert bool(row["ec_determinative"]) is False
            assert row["hybrid_margin"] is not None

        # --- the public surface carries no UCSB-derived number ---------------
        leak = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{EC_PV_REDISTRIBUTABLE_VIEW} "
            f"WHERE source = '{SOURCE_UCSB}' OR redistributable = false"
        )
        assert leak["n"].iloc[0] == 0
        hybrid.assert_redistributable_only_source(
            hybrid.read_ec_pv_join(dbc, view=EC_PV_REDISTRIBUTABLE_VIEW)
        )
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
