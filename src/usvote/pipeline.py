"""Top-level orchestration — scrape -> parse -> transform -> load.

Wires the four stage modules into a single end-to-end Electoral College
ingestion entry point (:func:`run_ec_pipeline`), so the pipeline runs from the
package instead of by executing notebook cells top-to-bottom.

Assembled in E2-S5 (#28). Configuration (DB connection params, the TIGER
shapefile path) is externalized in E2-S6 (#31); until then the election-year
range is hardcoded here and the shapefile path is passed in by the caller.

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

# The most recent election year the pipeline ingests. The notebook (cell 7)
# hardcoded 2020; bumped to the actual latest election. Hardcoded until config
# externalization (#31).
LATEST_ELECTION_YEAR = 2024


def election_years(latest: int = LATEST_ELECTION_YEAR) -> set[int]:
    """Return the set of US presidential election years, 1789 through ``latest``.

    1789 is the lone off-cycle year (the first election); every election since has
    been held every four years from 1792. Ported from notebook cells 10/11; used
    to filter the scraped Archives links to real election years. ``latest + 1`` as
    the range bound includes ``latest`` when it is an election year without
    overshooting to the next cycle when it is not (e.g. ``election_years(2025)``
    stops at 2024, not 2028).
    """
    return {1789} | set(range(1792, latest + 1, 4))


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
    #31 externalizes) — then scrapes the Archives, parses each year's tables, builds
    the ``(candidates_df, state_df, votes_df)`` warehouse frames, and loads them into
    the ``dwh`` schema on ``dbc``.

    ``years`` is the set of election years to ingest; it defaults to
    :func:`election_years` (every real election through :data:`LATEST_ELECTION_YEAR`).
    Pass an explicit subset to ingest fewer years (e.g. ``{2016, 2020}`` to run only
    the years captured as fixtures). The scrape reads the full results index but
    fetches only the pages whose year is in ``years``.

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

    year_filter = election_years() if years is None else years
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
