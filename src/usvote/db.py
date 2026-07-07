"""Database access — the ``DBC`` psycopg2 wrapper.

Thin wrapper around psycopg2 for schema/table create + drop, DataFrame inserts
(``execute_values``), and query-to-DataFrame reads. This is the one importable
module the whole pipeline loads through.

Placeholder in #17 (structure only). The existing top-level ``db_tools.py`` is
ported here — with type hints and unit tests covering SQL-string construction —
in E1-S3 (#21).
"""
