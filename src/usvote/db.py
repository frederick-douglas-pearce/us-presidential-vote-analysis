"""Database access — the ``DBC`` psycopg2 wrapper.

Thin wrapper around psycopg2 for schema/table create + drop, DataFrame inserts
(``execute_values``), and query-to-DataFrame reads. This is the one importable
module the whole pipeline loads through.

Ported from the top-level ``db_tools.py`` in E1-S3 (#21): type hints added and
SQL-string construction brought under unit test. Behavior matches the original
with one intentional change — a failed connection now raises
:class:`DBConnectionError` instead of calling ``sys.exit(1)``. Raising a typed
exception is both testable and friendlier inside the notebook (a clear
traceback rather than a killed kernel).

Original references:
- https://medium.com/analytics-vidhya/part-4-pandas-dataframe-to-postgresql-using-python-8ffdb0323c09
- https://github.com/Muhd-Shahid/Learn-Python-Data-Access/tree/main/PostgreSQL
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import pandas as pd
import psycopg2 as pg
from psycopg2.extras import execute_values


class DBConnectionError(RuntimeError):
    """Raised when :class:`DBC` cannot connect to the configured database.

    The original ``db_tools.DBC`` printed the error and called ``sys.exit(1)``.
    Raising a typed exception instead lets callers and tests handle the failure
    without terminating the process.
    """


class DBC:
    """Connect to a Postgres database and run schema/table/DML commands.

    ``db_config`` is passed straight through to :func:`psycopg2.connect`
    (e.g. ``host``, ``port``, ``dbname``, ``user``, ``password``). The
    ``connect`` callable can be overridden to substitute the connection factory
    — the unit tests use this to inject a fake connection and avoid a live
    database.
    """

    def __init__(
        self,
        db_config: dict[str, Any],
        *,
        connect: Callable[..., Any] = pg.connect,
    ) -> None:
        self.config = db_config
        try:
            self.conn = connect(**db_config)
        except pg.DatabaseError as e:
            raise DBConnectionError(f"Unable to connect to database:\n{e}") from e

    def close_connection(self) -> None:
        self.conn.close()

    def execute_query(self, query: str, close: bool = False) -> None:
        with self.conn as conn, conn.cursor() as curs:
            curs.execute(query)
        if close:
            self.close_connection()

    def delete_schema(
        self, schema: str, option: str = "Restrict", close: bool = False
    ) -> None:
        """Delete schema. Option can be "Cascade" or "Restrict" (default):
        https://www.postgresql.org/docs/14/sql-dropschema.html
        """
        self.execute_query(f"DROP SCHEMA IF EXISTS {schema} {option}", close=close)

    def create_schema(
        self, schema: str, replace: bool = False, close: bool = False
    ) -> None:
        """Create schema.
        https://www.postgresql.org/docs/14/sql-createschema.html
        """
        if replace:
            self.delete_schema(schema, option="Cascade")
        self.execute_query(f"CREATE SCHEMA IF NOT EXISTS {schema}", close=close)

    def delete_table(
        self,
        schema: str,
        table_name: str,
        option: str = "Restrict",
        close: bool = False,
    ) -> None:
        """Delete table in schema. Option can be "Cascade" or "Restrict" (default):
        https://www.postgresql.org/docs/14/sql-droptable.html
        """
        self.execute_query(
            f"DROP TABLE IF EXISTS {schema}.{table_name} {option}", close=close
        )

    def create_table(
        self,
        schema: str,
        table_name: str,
        table_columns: Iterable[tuple[str, str]],
        replace: bool = False,
        close: bool = False,
    ) -> None:
        """Create table. ``table_columns`` is a list of tuples, each tuple two
        strings: the first the column name, the second the column's type.
        https://www.postgresql.org/docs/14/sql-createtable.html
        """
        column_str = ", ".join(map(" ".join, table_columns))
        if replace:
            self.delete_table(schema, table_name, option="Cascade")
        self.execute_query(
            f"CREATE TABLE IF NOT EXISTS {schema}.{table_name} ({column_str})",
            close=close,
        )

    def copy_csv_to_table(
        self,
        schema: str,
        table_name: str,
        csv_path: str,
        header: bool = False,
        close: bool = False,
    ) -> None:
        """COPY a CSV file on the server into a table. ``header=True`` when the
        file's first line is a column header row (appends ``CSV HEADER``).

        Note: the original ``db_tools`` version was broken — its header logic was
        inverted and left ``header_str`` unbound when ``header=True`` (NameError).
        This port fixes it (the method was unused, so there was no working
        behavior to preserve); flagged in the #21 PR.
        """
        header_str = " CSV HEADER" if header else ""
        self.execute_query(
            f"COPY {schema}.{table_name} FROM '{csv_path}' DELIMITER ','{header_str}",
            close=close,
        )

    def insert_df_into_table(
        self,
        schema: str,
        table_name: str,
        df: pd.DataFrame,
        close: bool = False,
        **kwargs: Any,
    ) -> None:
        if len(df) > 0:
            columns = ",".join(list(df.columns))
            insert_stmt = f"INSERT INTO {schema}.{table_name} ({columns}) VALUES %s"
            with self.conn as conn, conn.cursor() as cur:
                execute_values(cur, insert_stmt, df.values, **kwargs)
        else:
            print("Input dataframe, df, is empty: No data was written to the database!")
        if close:
            self.close_connection()

    def select_query_to_df(self, query: str, close: bool = False) -> pd.DataFrame:
        """Execute ``query`` via :func:`pandas.read_sql` and return a DataFrame.

        Note: pandas warns when handed a raw psycopg2 connection rather than a
        SQLAlchemy connectable. Preserved from the original; a fix is out of
        scope for this port (#21).
        """
        df = pd.read_sql(query, self.conn)
        if close:
            self.close_connection()
        return df
