"""Live-Postgres integration test for the snapshot build (#150).

Excluded from the default suite by the ``integration`` marker; run with
``pytest -m integration`` against a real database **and** the three local corpora.

**Why this exists.** The snapshot is the *public artifact* — what the Cloud Run image
bakes in and what ``api.us-presidential-election-center.org`` serves — and until this
test its entire build path was verified only offline, against hand-authored synthetic
frames. Four things were covered by a person remembering to run a manual build and by
nothing else: the catalog-vs-spine agreement across all 51 years, slug uniqueness over
the real candidate set, the ``state_usps`` join resolving for every state, and
``national_electoral_denominator`` matching the real appointed allotments.

**What this test covers, stated honestly.** It is **data-integrity** coverage, not
**mechanism** coverage, and the distinction is load-bearing:

- :func:`~usvote.pv.absences.assert_catalog_matches_spine` is a **no-op on correct
  data**, so disabling it entirely would not change a single number asserted below.
  Its *mechanism* is mutation-covered offline in
  ``tests/unit/test_pv_absences.py`` (``TestAssertCatalogMatchesSpine``), which feeds
  phantom, miscast, uncatalogued and null-EV entries and asserts each raises.
- What this test adds instead is that the **real** ``dwh.votes`` frame agrees with the
  in-repo catalog end-to-end, on the artifact as written. That is why
  :func:`test_snapshot_from_a_real_full_span_warehouse` asserts the *content* of
  ``pv_status`` against :data:`~usvote.pv.absences.PV_ABSENCE_CATALOG` rather than only
  its non-nullness: a misclassification — 1824 South Carolina shipping as
  ``popular_vote`` instead of ``legislature_chosen`` — passes ``NOT NULL``, passes a
  distinct-values-in-enum check, passes the modern-years guard and passes every count.
  Nothing but a positive content assertion catches it.

**Three corpora, deliberately not four.** ``USVOTE_UCSB_HTML_DIR`` is **not** required
and must not become required. Since #139/D048 the build derives ``pv_status`` in-process
from :mod:`usvote.pv.absences` over the EC spine and **never** reads
``dwh.pv_state_status``, whose pre-1976 rows are UCSB-derived (D022/D030). A snapshot
test that needed the UCSB corpus would assert a dependency the licensing firewall says
does not exist. The catalog-vs-UCSB agreement is ``TestRealCorpus``'s job, and the
"no UCSB value on the redistributable surface" property is held by
``tests/unit/test_layering.py`` and by ``test_hybrid_views.py``'s own checks.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

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


def _corpus_fetch(html_dir: str) -> Any:
    """A ``Fetch`` replaying the local Archives corpus, verified complete first.

    Mirrors the helper in ``test_hybrid_views.py``; kept local rather than shared
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
        # the public artifact is built from. UCSB is skipped at warehouse.py:265
        # (``if ucsb_html_dir is not None``), not merely absent from the environment.
        assert result.sources_loaded == frozenset({"ec", "mit"})

        out = tmp_path / "snapshot.sqlite"
        # ``close=False``: the ``finally`` below owns the connection.
        meta = build_snapshot_from_db(dbc, str(out))

        # --- AC-1: the returned metadata --------------------------------------
        # NOTE: ``schema_version == SNAPSHOT_SCHEMA_VERSION`` pins the symbol to itself
        # and would silently follow a hand-bump. It is kept because a *shape* change
        # trips the column-set assertion below; when #102 (E8-S8) bumps 2 -> 3 by hand,
        # the shape guard that makes the D034 cutover contract enforceable belongs here.
        assert meta.schema_version == SNAPSHOT_SCHEMA_VERSION
        assert (meta.year_min, meta.year_max) == (SERVED_YEAR_MIN, SERVED_YEAR_MAX)
        assert (meta.pv_year_min, meta.pv_year_max) == (PV_YEAR_MIN, PV_YEAR_MAX)
        assert meta.candidate_count == CANDIDATE_COUNT, (
            f"expected {CANDIDATE_COUNT} distinct canonical candidates 1824-2024, got "
            f"{meta.candidate_count} — this is a FINDING, not a figure to retune: "
            "lower suggests a name reconciliation merged two people, higher suggests "
            "one person split across spellings"
        )
        assert meta.row_count > 0

        conn = sqlite3.connect(str(out))
        try:
            def one(sql: str, *args: Any) -> Any:
                return conn.execute(sql, args).fetchone()[0]

            # --- the artifact matches the metadata ------------------------------
            assert one(f"SELECT count(*) FROM {DATA_TABLE}") == meta.row_count
            assert (
                one(f"SELECT count(DISTINCT candidate_slug) FROM {DATA_TABLE}")
                == meta.candidate_count
            )
            assert one(f"SELECT count(*) FROM {META_TABLE}") == 1
            # Non-vacuity: every election in the served span is present, so a build
            # short a year cannot pass the window assertions above by accident.
            assert one(f"SELECT count(DISTINCT year) FROM {DATA_TABLE}") == SERVED_YEARS

            # --- AC-1: pv_status is non-null on every row -----------------------
            # Largely redundant with the ``NOT NULL`` column and ``add_pv_status``'s
            # anti-join; kept as cheap artifact-level confirmation. The assertion that
            # actually guards is the content check below, not this one.
            assert one(
                f"SELECT count(*) FROM {DATA_TABLE} WHERE pv_status IS NULL"
            ) == 0
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
            # Two named cells, so a wholesale swap of the comparison cannot pass.
            assert absent_cells[(1824, "South Carolina")] == (
                PV_STATUS_LEGISLATURE_CHOSEN
            )
            assert absent_cells[(1864, "Alabama")] == PV_STATUS_NOT_PARTICIPATING

            # --- AC-3, anomaly 1: 1872 Grant, cast vs counted vs appointed ------
            cast, counted = conn.execute(
                f"SELECT national_electoral_votes, national_counted_electoral_votes "
                f"FROM {ROLLUP_TABLE} WHERE year = 1872 AND candidate LIKE '%Grant%'"
            ).fetchone()
            appointed = one(
                f"SELECT national_electoral_denominator FROM {ROLLUP_TABLE} "
                "WHERE year = 1872 LIMIT 1"
            )
            assert (cast, counted, appointed) == (GRANT_1872_CAST, GRANT_1872_COUNTED, 366)

            # --- AC-3, anomaly 2: 1868 Georgia is disputed, on the right person -
            status, reason = conn.execute(
                f"SELECT count_status, count_status_reason FROM {DATA_TABLE} "
                "WHERE year = 1868 AND state = 'Georgia' AND candidate = ?",
                ("Horatio Seymour",),
            ).fetchone()
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
        finally:
            conn.close()
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
