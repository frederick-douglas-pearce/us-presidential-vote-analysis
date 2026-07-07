"""Load stage — write the three DataFrames into the Postgres ``dwh`` schema.

Maps to notebook Section 4. Orchestrates DataFrame -> Postgres via the ``DBC``
wrapper in :mod:`usvote.db`, creating the loose star schema (``state`` and
``candidate`` dimensions, ``votes`` fact) in FK-dependency order
(state -> candidate -> votes) and inserting the rows.

Ported from ``step1_electoral_college_data.ipynb`` in E2-S5 (#28). The
orchestrator to land here is ``create_tables_from_dfs``. The notebook's
``replace=True`` behavior cascades a drop/recreate of the whole ``dwh`` schema on
every full run; the package version must make that destructive write **opt-in and
guarded**, not default-on-import.

Connection params and the shapefile path are hardcoded in the notebook today;
externalizing them is E2-S6 (#31), not this module's concern yet.
"""
