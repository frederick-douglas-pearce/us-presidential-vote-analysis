"""Election-year domain constants and the default EC ingest scope.

Extracted from :mod:`usvote.pipeline` (#36) so that a **pure, offline** module can
name the year scope without importing the orchestrator. ``usvote.pipeline`` imports
:mod:`usvote.load`, :mod:`usvote.scrape` and :class:`usvote.db.DBC`, so it pulls in
psycopg2 and the network stack; :mod:`usvote.ucsb.transform` needs only
:func:`ec_ingest_years`, and a leaf transform depending on the top-level orchestrator
is the shape that becomes a real import cycle the moment PV is wired into
``usvote.pipeline``.

Everything here is data and pure functions — **this module must stay dependency-free**
(no stage modules, no DB, no network), which is the property that makes it importable
from any source subpackage.

``usvote.pipeline`` re-exports all five names, so existing
``from usvote.pipeline import ec_ingest_years`` callers are unaffected.

**Why UCSB imports this (D006).** The EC spine is authoritative on participation, and
UCSB's ingest scope is *derived* from it — ``ec_ingest_years()`` minus the years UCSB
publishes no popular vote for (D024 §6, clarified 2026-07-18). The dependency direction
``ucsb -> years`` is acyclic and D006-correct; the literals ``1868``/``1872`` must never
be duplicated into ``usvote/ucsb/``, so that #57 lifting :data:`UNSUPPORTED_EC_YEARS`
admits both years to UCSB ingestion with no change there.
"""

from __future__ import annotations

# The most recent election year the pipeline ingests. A domain constant bumped
# each cycle (the notebook, cell 7, hardcoded 2020; this is the actual latest).
# Not deployment config: callers override per-run via ``election_years(latest=...)``
# or the ``years`` argument to :func:`usvote.pipeline.run_ec_pipeline`.
LATEST_ELECTION_YEAR = 2024

# The default EC ingestion floor (#32). The structurally-uniform post-12th-Amendment
# era begins in 1804, but the default spine starts at 1824 — the MVP popular-vote
# comparison floor (D009). 1804-1820 are post-12A yet below that floor and carry their
# own elector-shortfall notation in the totals cell ("176 (175)*" = appointed (cast));
# they are deferred, not required. 1789-1800 are pre-12th-Amendment (each elector cast
# two presidential votes) and out of scope entirely — a dedicated later epic (D010).
EC_SPINE_FLOOR = 1824

# Years the default ingest deliberately excludes because their Archives tables encode
# contested/uncounted electoral votes that need dedicated modeling, not the standard
# per-state candidate grain (#32, tracked in #57).
#
# **This set is now EMPTY, and that is the point.** Both Reconstruction years have been
# ingested and the EC spine is complete from 1824 to the latest election:
#   - **1868, lifted in #143.** Georgia's contested nine votes are carried as
#     ``count_status='disputed'`` on the fact (D043/D044) rather than resolved by
#     picking one of the page's two totals rows; Mississippi, Texas and Virginia
#     (not yet readmitted, no electors appointed) load as genuine 0-EV rows.
#   - **1872, lifted in #144.** Greeley died after the popular vote and his electoral
#     votes scattered across four recipients; the 17 votes Congress refused to count
#     (Georgia's 3 for Greeley, Arkansas's 6 and Louisiana's 8 for Grant) appear nowhere
#     in the Archives table and are synthesized from its own footnotes before being
#     flagged ``count_status='not_counted'`` (D045). Arkansas and Louisiana also recover
#     the allotments the table prints as "-", which is what makes the year's denominator
#     the 366 Congress announced rather than the 352 the page totals (D045).
#
# The constant is retained rather than deleted: it is the **single gate** on both
# sources (UCSB derives its scope from ``ec_ingest_years()``, D024 §6) and the
# documented seam for any future era — the pre-12th-Amendment epic (D010) is the next
# candidate — so a year can be excluded again without reinventing the mechanism.
# Emptying it likewise widened ``usvote.pv.absences.CURATED_YEARS`` to its full 51,
# whose import-time pin (``CURATED_YEAR_COUNT``) is what forces an un-reviewed year to
# be noticed.
UNSUPPORTED_EC_YEARS: frozenset[int] = frozenset()


def election_years(latest: int = LATEST_ELECTION_YEAR) -> set[int]:
    """Return the set of US presidential election years, 1789 through ``latest``.

    1789 is the lone off-cycle year (the first election); every election since has
    been held every four years from 1792. Ported from notebook cells 10/11; the
    full election calendar. :func:`ec_ingest_years` narrows this to the years the EC
    pipeline actually ingests by default. ``latest + 1`` as the range bound includes
    ``latest`` when it is an election year without overshooting to the next cycle when
    it is not (e.g. ``election_years(2025)`` stops at 2024, not 2028).
    """
    return {1789} | set(range(1792, latest + 1, 4))


def ec_ingest_years(latest: int = LATEST_ELECTION_YEAR) -> set[int]:
    """The default set of years the EC pipeline ingests.

    The full election calendar (:func:`election_years`) narrowed to the supported EC
    spine: from :data:`EC_SPINE_FLOOR` (1824, the D009 comparison floor) through
    ``latest``, minus :data:`UNSUPPORTED_EC_YEARS` — **which is now empty**, so this is
    currently every election year from 1824 on. See :data:`EC_SPINE_FLOOR` for why the
    pre-1824 years are out, and :data:`UNSUPPORTED_EC_YEARS` for the two Reconstruction
    years that were gated until #143 and #144 ingested them. This is the default
    ``years`` filter for :func:`usvote.pipeline.run_ec_pipeline`; pass an explicit
    ``years`` to override it.

    Also the base of the **UCSB** ingest scope — :func:`usvote.ucsb.transform.
    ucsb_ingest_years` subtracts the no-popular-vote years from this set (D024 §6).
    """
    return {
        y
        for y in election_years(latest)
        if y >= EC_SPINE_FLOOR and y not in UNSUPPORTED_EC_YEARS
    }
