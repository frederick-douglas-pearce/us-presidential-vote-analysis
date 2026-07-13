"""Top-level orchestration — scrape -> parse -> transform -> load.

Wires the four stage modules into a single end-to-end Electoral College
ingestion entry point (:func:`run_ec_pipeline`), so the pipeline runs from the
package instead of by executing notebook cells top-to-bottom.

Assembled in E2-S5 (#28). Configuration (DB connection params, the TIGER
shapefile path) is externalized in :mod:`usvote.config` (E2-S6, #31): this module
takes the resolved shapefile path and the ``DBC`` connection by dependency
injection, and :mod:`usvote.__main__` resolves both from the environment when run
as ``python -m usvote``.

The entry point is named for the source (``run_ec_pipeline``, not a bare
``run_pipeline``): under the D006 source-namespacing convention the popular-vote
sources land as sibling ``usvote/ucsb`` and ``usvote/mit`` subpackages, each with
its own pipeline.
"""

from __future__ import annotations

from collections.abc import Callable, Container

import pandas as pd

from usvote import load, parse, scrape, transform
from usvote.db import DBC
from usvote.scrape import Fetch, fetch_url

# The most recent election year the pipeline ingests. A domain constant bumped
# each cycle (the notebook, cell 7, hardcoded 2020; this is the actual latest).
# Not deployment config: callers override per-run via ``election_years(latest=...)``
# or the ``years`` argument to :func:`run_ec_pipeline`.
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
# per-state candidate grain (#32; tracked for follow-up in #57):
#   - 1868: Georgia's 9 votes were contested (Congress could not agree whether to count
#     them), so the page carries dual "excluding/including Georgia" totals rows, and
#     Mississippi, Texas and Virginia did not participate (not yet readmitted).
#   - 1872: Horace Greeley died after the popular vote; his electoral votes scattered
#     across several candidates and Georgia's 3 Greeley votes were rejected by Congress.
# These are a default-scoping choice, not a hard block: an explicit ``years={1868}``
# still attempts them and fails loudly rather than being silently dropped.
UNSUPPORTED_EC_YEARS = frozenset({1868, 1872})


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
    ``latest``, excluding :data:`UNSUPPORTED_EC_YEARS` (the Reconstruction years whose
    contested/uncounted votes need dedicated modeling). See those constants for why the
    pre-1824 and 1868/1872 years are out of the default. This is the default ``years``
    filter for :func:`run_ec_pipeline`; pass an explicit ``years`` to override it.
    """
    return {
        y
        for y in election_years(latest)
        if y >= EC_SPINE_FLOOR and y not in UNSUPPORTED_EC_YEARS
    }


def run_ec_pipeline(
    dbc: DBC,
    shapefile_path: str,
    *,
    replace: bool = False,
    years: Container[int] | None = None,
    fetch: Fetch = fetch_url,
    load_geo: Callable[[str], pd.DataFrame] = transform.load_state_geo,
    close: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the end-to-end Electoral College ingestion and return the built frames.

    Reads the TIGER state geography once (via ``load_geo``), derives the valid
    state-name set from it — the same frame :func:`usvote.transform.build_state_dim`
    consumes, keeping the parse filter and the state dimension in lockstep (the SSOT
    is the shapefile) — then scrapes the Archives, parses each year's tables, builds
    the ``(candidates_df, state_df, votes_df)`` warehouse frames, and loads them into
    the ``dwh`` schema on ``dbc``.

    ``years`` is the set of election years to ingest; it defaults to
    :func:`ec_ingest_years` (the supported EC spine — 1824 through
    :data:`LATEST_ELECTION_YEAR`, excluding the Reconstruction-contested
    :data:`UNSUPPORTED_EC_YEARS`). Pass an explicit subset to ingest fewer years (e.g.
    ``{2016, 2020}`` to run only the years captured as fixtures). The scrape reads the
    full results index but fetches only the pages whose year is in ``years``.

    Seams mirror the stage modules' own: ``fetch`` (default live HTTP) lets the whole
    scrape replay from on-disk snapshots via :func:`usvote.scrape.fetch_from_dir`, and
    ``load_geo`` (default :func:`usvote.transform.load_state_geo`) lets a test inject a
    fake geo frame instead of the real shapefile. ``replace`` is forwarded to
    :func:`usvote.load.load_dataframes` — ``True`` for a destructive full rebuild,
    ``False`` (default) to create-if-absent. ``close`` is likewise forwarded; the
    caller owns ``dbc`` so it defaults to ``False``.

    Returns the three frames (candidates, state, votes) for inspection/validation.
    """
    state_geo = load_geo(shapefile_path)
    state_names = set(state_geo["NAME"])

    year_filter = ec_ingest_years() if years is None else years
    links = scrape.scrape_election_links(fetch=fetch)
    raw_tables = scrape.scrape_raw_election_tables(links, year_filter, fetch=fetch)
    parsed_years = parse.parse_election_years(raw_tables, state_names)

    candidates_df, state_df, votes_df = transform.transform_parsed_years(
        parsed_years, state_geo
    )
    load.load_dataframes(
        dbc,
        state_df=state_df,
        candidates_df=candidates_df,
        votes_df=votes_df,
        replace=replace,
        close=close,
    )
    return candidates_df, state_df, votes_df
