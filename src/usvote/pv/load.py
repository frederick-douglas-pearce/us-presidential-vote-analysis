"""Load stage — write the shared-shape PV frames into their ``dwh`` tables.

The source-neutral PV analogue of the EC :func:`usvote.load.load_dataframes`. Every
PV source (MIT #66, later UCSB #37) loads through this one seam: hand it a frame on
the D018 shared shape (:data:`usvote.pv.schema.SHARED_PV_COLUMNS`, already reconciled
onto the canonical keys) and it assigns the surrogate ``pv_id``, creates the shared
table if absent, and inserts — tagged by whatever ``source`` value the frame carries.

Two loaders live here, one per shared PV table, and they are deliberately parallel:
:func:`load_pv_records` writes the ``dwh.pv_votes`` fact, and :func:`load_pv_status`
writes the D024 ``dwh.pv_state_status`` roster (the second frame a source's transform
emits). Both are source-neutral — UCSB (#37) is the first caller of the roster loader,
but E6's MIT roster backfill is the second, so neither can live under a source
subpackage. A source that loads both (UCSB) applies **one** ``replace`` flag to both
calls; the two writes are not one transaction (``DBC`` commits per statement), so a
failure between them can leave the roster/fact pair inconsistent in the DB — see
:func:`usvote.ucsb.pipeline.run_ucsb_pipeline` for the load order that minimizes the
blast radius and follow-up #84, which would make it atomic.

**Two invariants this module exists to protect:**

- **Never a schema-level ``replace``.** The EC loader's ``replace=True`` cascades a
  drop of the *entire* ``dwh`` schema (``create_schema(replace=True)`` ->
  ``DROP SCHEMA ... CASCADE``). The PV table shares ``dwh`` with the EC spine, so
  doing that here would wipe ``state``/``candidate``/``votes`` on every PV reload.
  :func:`load_pv_records` therefore calls ``create_schema(replace=False)``
  *unconditionally* and gates ``replace`` only at the **table** level — a PV reload
  drops at most ``dwh.pv_votes``, never the schema. A unit test asserts no
  schema-level drop is ever issued.
- **The database owns the surrogate key; the DB boundary owns NaN -> None.**
  ``pv_id`` is a ``GENERATED ALWAYS AS IDENTITY`` column (see
  :func:`usvote.pv.schema.build_pv_column_defs`), so Postgres assigns it from a
  persistent sequence on insert and the loader **never supplies it**. This is the fix
  for the multi-source-coexistence hazard: a per-call pandas ``range(1, n+1)`` would
  restart at 1 on every load and collide on the ``pv_id`` PK the moment a second
  source (UCSB #37) or a second year-batch is appended — the exact "keep both rows"
  case D017 requires. Deferring the id to the DB sequence keeps ids unique across all
  loads. (The EC ``votes`` fact assigns ``votes_id`` in pandas instead, but EC always
  rebuilds the whole schema in one shot, so it never appends; PV is append-shaped.)
  NaN/NA -> SQL NULL and numpy unboxing stay owned by
  ``usvote.db.insert_df_into_table`` — this module adds no upstream ``.map`` pass
  (which would silently no-op on ``StringDtype``; CLAUDE.md).
"""

from __future__ import annotations

import pandas as pd

from usvote.db import DBC
from usvote.pv.schema import (
    NATURAL_KEY,
    PV_SCHEMA,
    PV_TABLE,
    assert_pv_shape,
    build_pv_column_defs,
)
from usvote.pv.status import (
    ROSTER_NATURAL_KEY,
    ROSTER_SCHEMA,
    ROSTER_TABLE,
    assert_roster_shape,
    assert_unique_roster_grain,
    build_status_column_defs,
)


def load_pv_records(
    dbc: DBC,
    df: pd.DataFrame,
    *,
    schema: str = PV_SCHEMA,
    replace: bool = False,
    close: bool = False,
) -> pd.DataFrame:
    """Assign ``pv_id``, create ``schema.pv_votes`` if absent, and insert ``df``.

    ``df`` must be on the D018 shared shape (:func:`assert_pv_shape` guards this) with
    ``state``/``candidate`` already reconciled onto the canonical keys — the ``state``
    FK to ``dwh.state`` requires the EC spine to be loaded first, so a PV load always
    runs *after* the EC pipeline. Returns the shared-shape frame as inserted (sorted;
    **without** ``pv_id`` — that is DB-assigned) for inspection/validation.

    Rows are inserted in a stable sort on the
    :data:`~usvote.pv.schema.NATURAL_KEY` ``(source, year, state, candidate)`` for a
    deterministic insert/output order. ``pv_id`` itself is **not** assigned here — it
    is a ``GENERATED ALWAYS AS IDENTITY`` column the database fills from a persistent
    sequence, so ids stay unique across separate loads (the loader omits the column
    from the INSERT).

    ``replace`` gates the **table-level** destructive rebuild only: ``True`` drops and
    recreates ``schema.pv_votes`` (discarding existing PV rows for *all* sources);
    ``False`` (the default) creates it if absent and appends. The schema itself is
    **never** dropped here — the EC spine sharing ``dwh`` must survive a PV reload.
    Re-running with ``replace=False`` against already-loaded rows raises a
    primary-key/unique violation on insert (the intended non-destructive guard).

    ``close`` closes the connection when done; defaults to ``False`` because the
    caller owns the ``dbc`` it passed in.
    """
    assert_pv_shape(df)

    # Stable-sort for a deterministic insert/output order. pv_id is NOT assigned here —
    # it is a GENERATED ALWAYS AS IDENTITY column the DB fills, so it must be absent
    # from the inserted frame (a per-call range(1, n+1) would collide across loads).
    ordered = df.sort_values(list(NATURAL_KEY), kind="stable").reset_index(drop=True)

    # NEVER forward ``replace`` to create_schema — that cascades a drop of the whole
    # ``dwh`` schema and wipes the EC spine. Create-if-absent only; ``replace`` is
    # gated at the table level below.
    dbc.create_schema(schema, replace=False)
    dbc.create_table(schema, PV_TABLE, build_pv_column_defs(schema), replace=replace)
    dbc.insert_df_into_table(schema, PV_TABLE, ordered)
    if close:
        dbc.close_connection()
    return ordered


def load_pv_status(
    dbc: DBC,
    roster: pd.DataFrame,
    *,
    schema: str = ROSTER_SCHEMA,
    replace: bool = False,
    close: bool = False,
) -> pd.DataFrame:
    """Create ``schema.pv_state_status`` if absent and insert the D024 roster frame.

    The roster-table sibling of :func:`load_pv_records`, and source-neutral for the
    same reason its shape contract is (``usvote.pv.status``): E6's MIT roster backfill
    loads through this seam too, so it must not live under a source subpackage.
    ``roster`` is the second frame :func:`usvote.ucsb.transform.transform_ucsb` returns,
    on :data:`~usvote.pv.status.ROSTER_COLUMNS`; its ``state`` FK targets ``dwh.state``,
    so the EC spine must be loaded first.

    Mirrors :func:`load_pv_records` exactly:

    - the frame is shape/grain-guarded (:func:`assert_roster_shape`,
      :func:`assert_unique_roster_grain`) before any DDL, so a malformed roster fails
      loudly here rather than mid-insert;
    - it is stable-sorted on :data:`~usvote.pv.status.ROSTER_NATURAL_KEY` for a
      deterministic insert/output order;
    - ``status_id`` is a ``GENERATED ALWAYS AS IDENTITY`` column the DB fills, so it is
      **never** supplied in the frame (a per-call ``range`` would collide across a
      second source's append, the same hazard ``pv_id`` avoids);
    - ``create_schema`` is called ``replace=False`` **unconditionally** — the EC spine
      sharing ``dwh`` must survive — and ``replace`` gates only the table-level rebuild.

    Returns the sorted roster frame as inserted (without ``status_id``).
    """
    assert_roster_shape(roster)
    assert_unique_roster_grain(roster)

    ordered = roster.sort_values(
        list(ROSTER_NATURAL_KEY), kind="stable"
    ).reset_index(drop=True)

    # As in load_pv_records: NEVER forward ``replace`` to create_schema (it would
    # cascade a drop of the whole dwh schema and wipe the EC spine). Create-if-absent
    # only; ``replace`` is gated at the table level.
    dbc.create_schema(schema, replace=False)
    dbc.create_table(
        schema, ROSTER_TABLE, build_status_column_defs(schema), replace=replace
    )
    dbc.insert_df_into_table(schema, ROSTER_TABLE, ordered)
    if close:
        dbc.close_connection()
    return ordered
