"""Load stage — write the census frame into ``dwh.census_population``.

Mirrors :func:`usvote.pv.load.load_pv_records` exactly, including the one rule that is
easy to get wrong and expensive to get wrong: ``replace`` gates the **table**, never the
schema. Forwarding it to ``create_schema`` would cascade a drop of the whole ``dwh``
schema and take the EC spine with it.

The ``state`` foreign key targets ``{schema}.state``, so the EC pipeline must have run
first — which is also why :mod:`usvote.census.pipeline` reads the spine before it
writes.
"""

from __future__ import annotations

import pandas as pd

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
