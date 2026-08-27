"""Live-Postgres integration test for the snapshot build (#150).

Excluded from the default suite by the ``integration`` marker; run with
``pytest -m integration`` against a real database **and** the three local corpora.

**Why this exists.** The snapshot is the *public artifact* — what the Cloud Run image
bakes in and what ``api.us-presidential-election-center.org`` serves — and until this
test its entire build path was verified only offline, against hand-authored synthetic
frames. Three things were covered by a person remembering to run a manual build and by nothing
else: slug uniqueness over the real candidate set, the ``state_usps`` join resolving for
every state, and ``national_electoral_denominator`` matching the real appointed
allotments. A fourth — the catalog-vs-spine agreement across all 51 years — **is**
covered offline (``tests/unit/test_pv_absences.py::TestRealShapes::test_the_whole_curated_span_yields_32_absences_and_nothing_else``, which runs
``build_curated_roster`` over every year in ``CURATED_YEARS``), but against the
*committed roster fixture*; what this test adds there is the **live warehouse spine**,
so fixture-vs-pipeline drift has somewhere to fail.

**What this test covers, stated honestly.** It is **data-integrity** coverage, not
**mechanism** coverage, and the distinction is load-bearing:

- :func:`~usvote.pv.absences.assert_catalog_matches_spine` is a **no-op on correct
  data**, so disabling it entirely would not change a single number asserted below.
  Its *mechanism* is mutation-covered offline in
  ``tests/unit/test_pv_absences.py`` (``TestCatalogMatchesSpine``), which feeds
  phantom, miscast, uncatalogued and null-EV entries and asserts each raises.
- What this test adds instead is that every catalogued absence **reached a real fact
  row** and survived the roster merge onto the artifact as written.

**What the catalog comparison does and does not prove — stated precisely, because the
obvious reading is wrong.** ``absent_cells == expected`` compares the artifact's
non-``popular_vote`` cells against :data:`~usvote.pv.absences.PV_ABSENCE_CATALOG`, and
the artifact's ``pv_status`` is *itself* derived from that same catalog
(``derive_curated_pv_status_roster`` -> ``build_curated_roster``). **Both sides move
together**, so that equality cannot detect a wrong or deleted catalog entry. What it
does prove is real but narrower: every catalog key matched a ``(year, state)`` that
exists in the real spine and reached the artifact, and the ``m:1`` roster merge
preserved each value — a catalogued state that silently failed to join, or a status
mangled in transit, fails here.

**The spine-independent pins are the literals below it**, and each catches a different
edit — worth stating exactly, since mis-attributing a mechanism is the error that put
them here:

- **A deleted ``legislature_chosen`` entry** (EV > 0, e.g. Colorado 1876) fails
  :data:`ABSENCE_CELL_COUNT` (31 != 32): it reclassifies to the ``popular_vote``
  residual — ``assert_catalog_matches_spine``'s uncatalogued check fires only for
  zero-EV states — dropping the count before the ``PINNED_ABSENCES`` loop runs. A
  deleted ``not_participating`` entry (EV = 0) instead **raises** at build time via
  that same uncatalogued check, so no artifact exists to assert against.
- **A flipped status** raises in production before an artifact exists — the miscast
  check partitions the two statuses on ``total_electoral_votes == 0``, so the test
  errors rather than asserting.
- **A re-keyed entry** — ``(1876, "Colorado")`` becoming ``(1880, "Colorado")`` — is the
  pins' genuinely unique mutant: no phantom, no miscast, count unchanged, and the set
  equality moves with it. Only the ``KeyError`` in the pinned loop catches it.

**The residual, stated rather than implied:** a same-size **swap** — one entry deleted
and another added with electoral votes and a consistent status — keeps the count at 32
and moves both sides of the equality, so nothing here detects it. It is caught in CI by
the offline literal set in ``tests/unit/test_pv_absences.py::TestCatalogIntegrity::test_the_in_scope_catalog_is_exactly_32_rows_split_18_14``, which pins the
catalog's size and its 18/14 split directly.

**Three corpora, deliberately not four.** ``USVOTE_UCSB_HTML_DIR`` is **not** required
and must not become required. Since #139/D048 the build derives ``pv_status`` in-process
from :mod:`usvote.pv.absences` over the EC spine and **never** reads
``dwh.pv_state_status``, whose pre-1976 rows are UCSB-derived (D022/D030). A snapshot
test that needed the UCSB corpus would assert a dependency the licensing firewall says
does not exist. The catalog-vs-UCSB agreement is
``tests/unit/test_ucsb_transform.py::TestRealCorpus``'s job, and the
"no UCSB value on the redistributable surface" property is held by
``tests/unit/test_layering.py`` and by ``tests/integration/test_hybrid_views.py``'s own checks.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from usvote import hybrid
from usvote.db import DBC
from usvote.load import SCHEMA
from usvote.pv.absences import PV_ABSENCE_CATALOG
from usvote.pv.status import (
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
    PV_STATUS_VALUES,
)
from usvote.snapshot import build_snapshot_from_db
from usvote.snapshot_schema import (
    DATA_TABLE,
    HYBRID_SUMMARY_TABLE,
    META_TABLE,
    ROLLUP_TABLE,
    SNAPSHOT_SCHEMA_VERSION,
)

_EC_CORPUS = os.environ.get("USVOTE_EC_HTML_DIR", "")
_MIT_CSV = os.environ.get("USVOTE_MIT_CSV_PATH", "")
_SHAPEFILE = os.environ.get("USVOTE_SHAPEFILE_PATH", "")

#: The served window (D048) — every election the EC spine carries.
SERVED_YEARS = 51
SERVED_YEAR_MIN, SERVED_YEAR_MAX = 1824, 2024
#: The redistributable popular-vote sub-window — MIT's span, and only MIT's.
PV_YEAR_MIN, PV_YEAR_MAX = 1976, 2024
#: Distinct canonical candidate names 1824-2024. ``add_candidate_slug`` *raises* on a
#: true slug collision, so this equals the count of distinct names. Pinned rather than
#: bounded: a drift is a finding (lower => a name reconciliation merged two people;
#: higher => one person split across spellings), never a reason to relax the assertion.
CANDIDATE_COUNT = 96

#: 1872, the anomaly year #144 built the counted measure for. Grant's electors cast 300
#: votes; Congress counted 286, having rejected Arkansas's 6 and Louisiana's 8. The
#: appointed denominator is 366 — not the 352 the Archives page itself totals, because
#: AR/LA's allotments are restored (D046). This is the ladder appointed >= cast >=
#: counted, made observable on the public artifact.
GRANT_1872_CAST = 300
GRANT_1872_COUNTED = 286

#: Fact rows across the served span. Pinned rather than bounded for the same reason
#: :data:`CANDIDATE_COUNT` is: `> 0` cannot notice a build that keeps every year and
#: every candidate while dropping most *state* rows within them — a state-scoped source
#: extract, or an EC-left join regression leaving one row per year.
ROW_COUNT = 5623

#: Size of :data:`~usvote.pv.absences.PV_ABSENCE_CATALOG`, pinned as a literal so a
#: catalog entry added or deleted fails here. The set equality in the test cannot: the
#: artifact's ``pv_status`` derives from that same catalog, so both sides move together.
ABSENCE_CELL_COUNT = 32

#: Spine-independent classification pins — hardcoded expectations spanning both
#: non-``popular_vote`` statuses and several decades, so a single mis-set entry
#: cannot hide behind its neighbours.
PINNED_ABSENCES: dict[tuple[int, str], str] = {
    # McPherson v. Blacker: the legislature appointed electors.
    (1824, "South Carolina"): PV_STATUS_LEGISLATURE_CHOSEN,
    (1832, "South Carolina"): PV_STATUS_LEGISLATURE_CHOSEN,
    (1848, "South Carolina"): PV_STATUS_LEGISLATURE_CHOSEN,
    # H.R. 126: no returns from the seceded states.
    (1864, "Alabama"): PV_STATUS_NOT_PARTICIPATING,
    (1864, "Texas"): PV_STATUS_NOT_PARTICIPATING,
    # Colo. Const. of 1876, Schedule s 19: the first-year legislative appointment.
    (1876, "Colorado"): PV_STATUS_LEGISLATURE_CHOSEN,
}


def _corpus_fetch(html_dir: str) -> Any:
    """A ``Fetch`` replaying the local Archives corpus, verified complete first.

    Mirrors the helper in ``tests/integration/test_hybrid_views.py``; kept local rather than shared
    because the coupling cost of a shared private test helper exceeds four lines.
    ``assert_corpus_covers_years`` is the load-bearing call: a corpus short a year
    fails loud here instead of yielding a warehouse quietly missing an election.
    """
    from usvote import scrape

    scrape.assert_corpus_covers_years(html_dir)
    return scrape.fetch_from_corpus(html_dir)


@pytest.mark.integration
@pytest.mark.skipif(
    not (_EC_CORPUS and _MIT_CSV and _SHAPEFILE),
    reason=(
        "needs the local corpora: USVOTE_EC_HTML_DIR, USVOTE_MIT_CSV_PATH, "
        "USVOTE_SHAPEFILE_PATH (USVOTE_UCSB_HTML_DIR is deliberately NOT required)"
    ),
)
def test_snapshot_from_a_real_full_span_warehouse(
    integration_db_config: dict[str, Any], tmp_path: Path
) -> None:
    """Build a real 51-year EC+MIT warehouse, snapshot it, and read the artifact back.

    The warehouse half of AC-4's "corpus dir or warehouse" prerequisite is discharged by
    the ``integration_db_config`` fixture, which skips when ``USVOTE_TEST_DB_NAME`` is
    unset; this test builds its own warehouse with ``replace=True`` rather than
    inspecting a pre-existing one.
    """
    from usvote.warehouse import run_warehouse

    dbc = DBC(integration_db_config)
    try:
        result = run_warehouse(
            dbc,
            _SHAPEFILE,
            _MIT_CSV,
            replace=True,
            environ=dict(os.environ),
            fetch=_corpus_fetch(_EC_CORPUS),
        )
        assert result.views_built
        # Non-vacuity, and the D030 point in one assertion: a two-source build is what
        # the public artifact is built from. UCSB is skipped by ``run_warehouse``'s
        # ``if ucsb_html_dir is not None``, not merely absent from the environment.
        # (No line number: any edit above it in warehouse.py would silently repoint it.)
        assert result.sources_loaded == frozenset({"ec", "mit"})

        out = tmp_path / "snapshot.sqlite"
        # ``close=False``: the ``finally`` below owns the connection.
        meta = build_snapshot_from_db(dbc, str(out))

        # --- AC-1: the returned metadata --------------------------------------
        assert meta.schema_version == SNAPSHOT_SCHEMA_VERSION
        assert (meta.year_min, meta.year_max) == (SERVED_YEAR_MIN, SERVED_YEAR_MAX)
        assert (meta.pv_year_min, meta.pv_year_max) == (PV_YEAR_MIN, PV_YEAR_MAX)
        assert meta.candidate_count == CANDIDATE_COUNT, (
            f"expected {CANDIDATE_COUNT} distinct canonical candidates 1824-2024, got "
            f"{meta.candidate_count} — this is a FINDING, not a figure to retune: "
            "lower suggests a name reconciliation merged two people, higher suggests "
            "one person split across spellings"
        )
        assert meta.row_count == ROW_COUNT, (
            f"expected {ROW_COUNT} fact rows across the served span, got "
            f"{meta.row_count} — a bare `> 0` would not notice a build that dropped "
            "most state rows within years while keeping every year present"
        )

        conn = sqlite3.connect(str(out))
        try:

            def one(sql: str, *args: Any) -> Any:
                """First column of the single expected row, or fail naming the query.

                Without the guard a query that matches nothing dies with
                ``TypeError: 'NoneType' object is not subscriptable``, pointing at the
                subscript rather than at the missing row — and a missing row is the
                likely shape here, since a canonical name shift (``docs/corrections.md``
                records several) silently empties a ``WHERE candidate = ...``.
                """
                row = conn.execute(sql, args).fetchone()
                assert row is not None, f"query matched no row: {sql}"
                return row[0]

            # --- the artifact matches the metadata ------------------------------
            assert one(f"SELECT count(*) FROM {DATA_TABLE}") == meta.row_count
            assert one(f"SELECT count(*) FROM {META_TABLE}") == 1
            # Non-vacuity: every election in the served span is present, so a build
            # short a year cannot pass the window assertions above by accident.
            assert one(f"SELECT count(DISTINCT year) FROM {DATA_TABLE}") == SERVED_YEARS

            # --- AC-1: pv_status is non-null on every row -----------------------
            # Largely redundant with the ``NOT NULL`` column and ``add_pv_status``'s
            # anti-join; kept as cheap artifact-level confirmation. The assertion that
            # actually guards is the content check below, not this one.
            assert (
                one(f"SELECT count(*) FROM {DATA_TABLE} WHERE pv_status IS NULL") == 0
            )
            distinct_status = {
                r[0]
                for r in conn.execute(f"SELECT DISTINCT pv_status FROM {DATA_TABLE}")
            }
            assert distinct_status <= set(PV_STATUS_VALUES)

            # --- AC-2: the catalog agrees with the real spine, by CONTENT -------
            # The mutant this kills: a misclassification that leaves every count,
            # every window and every NOT NULL constraint satisfied.
            absent_cells = {
                (int(y), str(s)): str(status)
                for y, s, status in conn.execute(
                    f"SELECT DISTINCT year, state, pv_status FROM {DATA_TABLE} "
                    "WHERE pv_status != ?",
                    (PV_STATUS_POPULAR_VOTE,),
                )
            }
            expected = {
                key: entry.pv_status for key, entry in PV_ABSENCE_CATALOG.items()
            }
            assert absent_cells == expected, (
                "the artifact's non-popular-vote cells must be exactly the in-repo "
                "absence catalog — a difference is either a spine change the catalog "
                "has not caught up with, or a misclassification on the public surface"
            )
            assert len(absent_cells) == ABSENCE_CELL_COUNT, (
                f"expected {ABSENCE_CELL_COUNT} catalogued absences on the artifact, "
                f"got {len(absent_cells)} — an entry was added or deleted, which the "
                "set equality above cannot see (both sides derive from the catalog)"
            )
            for (year, state), expected_status in PINNED_ABSENCES.items():
                assert absent_cells[(year, state)] == expected_status, (
                    f"{year} {state} must ship as {expected_status!r}"
                )

            # --- AC-3, anomaly 1: 1872 Grant, cast vs counted vs appointed ------
            grant = conn.execute(
                f"SELECT national_electoral_votes, national_counted_electoral_votes "
                f"FROM {ROLLUP_TABLE} WHERE year = 1872 AND candidate LIKE '%Grant%'"
            ).fetchone()
            assert grant is not None, "no 1872 Grant row in the national rollup"
            cast, counted = grant
            appointed = one(
                f"SELECT national_electoral_denominator FROM {ROLLUP_TABLE} "
                "WHERE year = 1872 LIMIT 1"
            )
            assert (cast, counted, appointed) == (
                GRANT_1872_CAST,
                GRANT_1872_COUNTED,
                366,
            )

            # --- AC-3, anomaly 2: 1868 Georgia is disputed, on the right person -
            georgia = conn.execute(
                f"SELECT count_status, count_status_reason FROM {DATA_TABLE} "
                "WHERE year = 1868 AND state = 'Georgia' AND candidate = ?",
                ("Horatio Seymour",),
            ).fetchone()
            assert georgia is not None, (
                "no 1868 Georgia row for 'Horatio Seymour' — a canonical name shift "
                "would empty this filter silently"
            )
            status, reason = georgia
            assert status == "disputed"
            assert reason, "a disputed row must carry the Archives' own sentence"

            # --- a modern denominator too, so 1872 is not the only one pinned ---
            assert (
                one(
                    f"SELECT national_electoral_denominator FROM {ROLLUP_TABLE} "
                    "WHERE year = 2000 LIMIT 1"
                )
                == 538
            )
            assert (
                one(
                    f"SELECT national_counted_electoral_votes FROM {ROLLUP_TABLE} "
                    "WHERE year = 2000 AND candidate LIKE '%Bush%'"
                )
                == 271
            )

            # --- #102: the hybrid tables, and the ONE intended divergence -------
            # The snapshot derives the hybrid in-process from the CURATED roster
            # rather than reading `hybrid_redistributable`, so this is the only place
            # the two can be compared on real data. Everything except `pv_coverage`
            # must match the view exactly; `pv_coverage` must differ, and differ in a
            # specific direction. Without this, a future edit to the SQL builder that
            # misses the pandas oracle drifts the deployed view from the artifact
            # silently -- neither side's own tests would notice.
            assert (
                one(f"SELECT count(*) FROM {HYBRID_SUMMARY_TABLE}") == SERVED_YEARS
            ), "one hybrid_summary row per served election"

            for year in (2000, 2016):
                snap = conn.execute(
                    "SELECT ec_winner, pv_winner, hybrid_winner, pv_flip, "
                    f"hybrid_flip, ec_margin, pv_margin, hybrid_margin, pv_coverage "
                    f"FROM {HYBRID_SUMMARY_TABLE} WHERE year = ?",
                    (year,),
                ).fetchone()
                assert snap is not None, f"no hybrid_summary row for {year}"
                view = dbc.select_query_to_df(
                    "SELECT ec_winner, pv_winner, hybrid_winner, pv_flip, "
                    "hybrid_flip, ec_margin, pv_margin, hybrid_margin, pv_coverage "
                    f"FROM {SCHEMA}.{hybrid.HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW} "
                    f"WHERE year = {year}"
                )
                assert len(view) == 1
                row = view.iloc[0]
                assert snap[0] == row["ec_winner"]
                assert snap[1] == row["pv_winner"]
                assert snap[2] == row["hybrid_winner"]
                assert bool(snap[3]) is bool(row["pv_flip"])
                assert bool(snap[4]) is bool(row["hybrid_flip"])
                for i, col in enumerate(
                    ("ec_margin", "pv_margin", "hybrid_margin"), start=5
                ):
                    assert snap[i] == pytest.approx(float(row[col])), (
                        f"{year} {col} drifted between the snapshot and the view"
                    )
                # Inside the PV window the two rosters agree, so coverage matches too.
                assert snap[8] == pytest.approx(float(row["pv_coverage"]))

            # 2000 is the thesis year: the popular vote flips, the hybrid does not
            # (Nader's votes dilute Gore's PV share on the real national denominator).
            flip_2000 = conn.execute(
                f"SELECT pv_flip, hybrid_flip FROM {HYBRID_SUMMARY_TABLE} "
                "WHERE year = 2000"
            ).fetchone()
            assert bool(flip_2000[0]) is True, "2000 must flip on the popular vote"
            assert bool(flip_2000[1]) is False, (
                "2000 must NOT flip on the hybrid — asserted because the two-way unit "
                "fixture points the other way"
            )

            # The divergence itself, which is the whole of D048's action item for #102:
            # BEFORE the popular-vote window the view has no roster row and reads NULL,
            # while the snapshot reads the real catalog-derived figure.
            pre_window_view = dbc.select_query_to_df(
                "SELECT pv_coverage FROM "
                f"{SCHEMA}.{hybrid.HYBRID_SUMMARY_REDISTRIBUTABLE_VIEW} "
                "WHERE year = 1824"
            )
            assert pre_window_view["pv_coverage"].isna().all(), (
                "the warehouse view is expected to read NULL here — if this ever "
                "becomes non-null the divergence below is no longer the intended one"
            )
            coverage_1824 = one(
                f"SELECT pv_coverage FROM {HYBRID_SUMMARY_TABLE} WHERE year = 1824"
            )
            assert coverage_1824 is not None, (
                "the snapshot must carry a real 1824 coverage figure — this is the "
                "column #102 repointed at the in-repo catalog (D048)"
            )
            # 1824: six legislatures appointed electors holding 71 of 261 votes.
            assert float(coverage_1824) == pytest.approx(190 / 261, abs=1e-6)
        finally:
            conn.close()
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
