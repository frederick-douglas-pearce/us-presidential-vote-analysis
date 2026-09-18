"""Load stage — write the census frames into ``dwh.census_population`` and
``dwh.election_population``.

Mirrors :func:`usvote.pv.load.load_pv_records` exactly, including the one rule that is
easy to get wrong and expensive to get wrong: ``replace`` gates the **table**, never the
schema. Forwarding it to ``create_schema`` would cascade a drop of the whole ``dwh``
schema and take the EC spine with it.

The ``state`` foreign key targets ``{schema}.state``, so the EC pipeline must have run
first — which is also why :mod:`usvote.census.pipeline` reads the spine before it
writes.

**Two tables, one stage.** ``census_population`` is the ``(census_year, state)``
dimension #181 ingests; ``election_population`` is the ``(election_year, state)`` frame
#182 derives from it and #184 persists (D064). They are written in one transaction by
the pipeline, because the second is a function of the first plus the spine — a
warehouse holding one without the other is a state no consumer should have to reason
about.
"""

from __future__ import annotations

import pandas as pd

from usvote.census.conform import (
    ELECTION_POPULATION_NATURAL_KEY,
    ELECTION_POPULATION_TABLE,
    assert_election_population_shape,
    build_election_population_column_defs,
)
from usvote.census.schema import (
    CENSUS_NATURAL_KEY,
    CENSUS_SCHEMA,
    CENSUS_TABLE,
    assert_census_shape,
    build_census_column_defs,
)
from usvote.db import DBC


def load_census_population(
    dbc: DBC,
    df: pd.DataFrame,
    *,
    schema: str = CENSUS_SCHEMA,
    replace: bool = False,
    close: bool = False,
) -> pd.DataFrame:
    """Create ``schema.census_population`` if absent and insert ``df``.

    ``df`` must be on the census shape (:func:`assert_census_shape` guards this).
    Returns the frame as inserted — stable-sorted, and **without** ``population_id``,
    which is a ``GENERATED ALWAYS AS IDENTITY`` column the database fills from a
    persistent sequence so ids stay unique across separate loads.

    ``replace`` gates the **table-level** rebuild only: ``True`` drops and recreates the
    table; ``False`` (the default) creates it if absent and appends, so re-running
    against already-loaded rows raises a unique violation on the natural key — the
    intended non-destructive guard. The schema itself is **never** dropped here.

    ``close`` closes the connection when done; defaults to ``False`` because the caller
    owns the ``dbc`` it passed in.
    """
    assert_census_shape(df)

    ordered = df.sort_values(list(CENSUS_NATURAL_KEY), kind="stable").reset_index(
        drop=True
    )

    # NEVER forward ``replace`` to create_schema — that cascades a drop of the whole
    # ``dwh`` schema and wipes the EC spine. Create-if-absent only; ``replace`` is
    # gated at the table level below.
    dbc.create_schema(schema, replace=False)
    dbc.create_table(
        schema, CENSUS_TABLE, build_census_column_defs(schema), replace=replace
    )
    dbc.insert_df_into_table(schema, CENSUS_TABLE, ordered)
    if close:
        dbc.close_connection()
    return ordered


def load_election_population(
    dbc: DBC,
    df: pd.DataFrame,
    *,
    schema: str = CENSUS_SCHEMA,
    replace: bool = False,
    close: bool = False,
) -> pd.DataFrame:
    """Create ``schema.election_population`` if absent and insert ``df`` (#184 / D064).

    The second census table, and it holds the same two rules as the first: ``replace``
    gates the **table**, never the schema, and the ``state`` foreign key targets
    ``{schema}.state``, so the EC pipeline must have run first.

    ``df`` must be on the election-grain contract
    (:func:`~usvote.census.conform.assert_election_population_shape` guards it, and the
    caller has already run it as part of
    :func:`~usvote.census.conform.build_and_validate_election_population` — it is
    re-run here because this is the write boundary, and a write boundary that trusts
    its caller is a guard that stops running the day a second caller appears).

    Returns the frame as inserted — stable-sorted on the natural key, and **without**
    ``election_population_id``, which the database fills from its own sequence.
    """
    assert_election_population_shape(df)

    ordered = df.sort_values(
        list(ELECTION_POPULATION_NATURAL_KEY), kind="stable"
    ).reset_index(drop=True)

    # NEVER forward ``replace`` to create_schema -- see load_census_population above.
    dbc.create_schema(schema, replace=False)
    dbc.create_table(
        schema,
        ELECTION_POPULATION_TABLE,
        build_election_population_column_defs(schema),
        replace=replace,
    )
    dbc.insert_df_into_table(schema, ELECTION_POPULATION_TABLE, ordered)
    if close:
        dbc.close_connection()
    return ordered
