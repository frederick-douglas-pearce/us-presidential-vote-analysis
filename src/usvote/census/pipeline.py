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

from usvote.census.load import load_census_population
from usvote.census.parse import parse_population_change, parse_resident_1790_1990
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
    one resident series, applies the Virginia boundary correction, and loads
    ``dwh.census_population``.

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

    with dbc.transaction():
        loaded = load_census_population(dbc, frame, replace=replace)
    if close:
        dbc.close_connection()
    return loaded
