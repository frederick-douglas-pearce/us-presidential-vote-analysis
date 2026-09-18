"""Wire the census stages: read corpus -> parse -> transform -> load.

Holds the same contract as :func:`usvote.mit.pipeline.run_mit_pipeline` and
:func:`usvote.ucsb.pipeline.run_ucsb_pipeline` — it owns **one** transaction, gates
``replace`` at the table level only, closes the connection only if asked, and returns
the frame as inserted. This is also the only module under ``usvote/census/`` that
touches ``dbc`` for a spine read; the transform takes the resulting frame by dependency
injection and stays pure and offline.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from usvote.census.conform import build_and_validate_election_population
from usvote.census.load import load_census_population, load_election_population
from usvote.census.parse import parse_population_change, parse_resident_1790_1990
from usvote.census.reconcile import assert_seats_reconcile
from usvote.census.scrape import (
    RESIDENT_1790_1990,
    RESIDENT_1910_2020,
    RESIDENT_SOURCE_IDS,
    read_snapshot_sources,
)
from usvote.census.transform import transform_census
from usvote.db import DBC
from usvote.spine import read_ec_participation

#: Which parser reads which source file. A dict rather than an ``if`` chain so that
#: adding #183's seats sources is a new entry rather than an edit to control flow.
_PARSERS = {
    RESIDENT_1790_1990.source_id: parse_resident_1790_1990,
    RESIDENT_1910_2020.source_id: parse_population_change,
}


def run_census_pipeline(
    dbc: DBC,
    corpus_dir: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    replace: bool = False,
    close: bool = False,
) -> pd.DataFrame:
    """Run the end-to-end census ingestion and return the loaded frame.

    Reads the local corpus (``corpus_dir`` explicit, or resolved from
    ``USVOTE_CENSUS_CORPUS_DIR``), parses both published workbooks, stitches them into
    one resident series, applies the Virginia boundary correction, **conforms the result
    to the EC participation roster** (#182) and loads ``dwh.census_population`` and
    ``dwh.election_population``.

    **The return value is the census dimension, not the election-grain frame.** Both are
    written; this returns the first because its row count is what
    :class:`~usvote.warehouse.WarehouseResult.census_rows` has always reported, and
    changing what that number counts would silently re-point every existing reader of
    the build receipt.

    The conformance step
    (:func:`usvote.census.conform.build_and_validate_election_population`) runs
    **before** the write and raises rather than warning: it crosses to ``(election_year,
    state)`` grain — the grain every E10 consumer joins on — and every failure it looks
    for produces a plausible wrong number instead of an error. A corpus short a state, a
    boundary restatement it cannot verify against its pin, or a synthesized
    between-census value all fail here with nothing written. Since #184 it also
    **returns** the frame it validated, which is then loaded, so the derivation the
    guards ran over and the rows that reach the database are the same object rather than
    two builds that happen to agree.

    **What it does NOT catch, stated because the obvious guess is wrong** (#182 review,
    GE-F3): a drifted ``election_year -> governing_census_year`` mapping passes every
    one of these guards. Each row is checked against *its own* governing census, so a
    wrongly mapped row is compared with the wrongly mapped census's published figure and
    matches. The mapping's own guards are ``TestTheFullSeries`` in
    ``tests/unit/test_apportionment.py`` (a hand-written 51-year oracle) and, against
    real allotments, ``test_the_allotment_change_years_match_this_mapping`` in
    ``tests/integration/test_census_conform.py``. Both sit outside this seam, and the
    second needs a corpus and a database.

    The **seat reconciliation** (:func:`usvote.census.reconcile.assert_seats_reconcile`)
    runs beside it, and also before the write, for the same reason. It reads no census
    *population* at all — only the injected spine and the curated seat series — so it is
    deliberately not folded into the conformance seam above: a population-side failure
    and a seat-side failure are different findings and must be able to fire
    independently.

    **It is also called from** :func:`usvote.warehouse.run_warehouse`, **and that call
    is the load-bearing one.** This one is reachable only on a build that has a census
    corpus, because the lines above it read that corpus first — so if this were the only
    call site, the gate would fire exactly when a corpus happened to be present. Since
    it needs neither, the composition root calls it unconditionally, and this call is
    the narrower belt-and-braces one for a direct ``python -m usvote.census`` load.

    **Zero network requests.** Everything comes from the snapshotted corpus, whose
    completeness is asserted before a byte is parsed — a corpus missing a file fails
    loudly rather than building a warehouse short that century. Populate it first with
    ``python -m usvote.census snapshot``.

    **The EC spine must already be loaded**, for two reasons that are easy to conflate:
    the ``state`` foreign key targets ``dwh.state``, and the jurisdiction guard checks
    the census file's area names against the spine's own state set. The spine read
    happens *outside* the transaction, exactly as the PV pipelines do it.

    Note there is deliberately **no** ``years`` parameter. Everywhere else in this
    package ``years`` means *election* years; census rows are keyed by *decennial*
    years, and one name meaning two domains is how #182's conformance work would come
    to conflate them. The full 1790-2020 series is always loaded — it is ~1,000 rows,
    so there is nothing to scope for.
    """
    sources = read_snapshot_sources(
        corpus_dir, source_ids=RESIDENT_SOURCE_IDS, environ=environ
    )
    rows_by_source = {
        source_id: _PARSERS[source_id](data, source_id=source_id)
        for source_id, data in sources.items()
    }
    ec_participation = read_ec_participation(dbc)
    frame = transform_census(rows_by_source, ec_participation)
    election_population = build_and_validate_election_population(
        frame, ec_participation
    )
    assert_seats_reconcile(ec_participation)

    with dbc.transaction():
        loaded = load_census_population(dbc, frame, replace=replace)
        load_election_population(dbc, election_population, replace=replace)
    if close:
        dbc.close_connection()
    return loaded
