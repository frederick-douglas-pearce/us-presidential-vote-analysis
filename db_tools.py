#!/usr/bin/env python
# See https://medium.com/analytics-vidhya/part-4-pandas-dataframe-to-postgresql-using-python-8ffdb0323c09
# https://github.com/Muhd-Shahid/Learn-Python-Data-Access/tree/main/PostgreSQL

import pandas as pd
import psycopg2 as pg
from psycopg2.extras import execute_values
import sys

# DBC Class connects to postgres database with methods for executing different sql commands
class DBC:
    def __init__(self, db_config):
        self.config = db_config
        try:
            self.conn = pg.connect(**db_config)
        except pg.DatabaseError as e:
            print(f"Unable to connect to database:\n{e}")
            sys.exit(1)
            
    def close_connection(self):
        self.conn.close()

    def execute_query(self, query, close=False):    
        with self.conn as conn, conn.cursor() as curs:
            curs.execute(query)
        if close:
            self.close_connection()      
            
    def delete_schema(self, schema, option="Restrict", close=False):
        """Delete schema. Option can be "Cascade" or "Restrict" (default):
        https://www.postgresql.org/docs/14/sql-dropschema.html
        """
        self.execute_query(f"DROP SCHEMA IF EXISTS {schema} {option}", close=close)
        
    def create_schema(self, schema, replace=False, close=False):
        """Create schema.
        https://www.postgresql.org/docs/14/sql-createschema.html
        """
        if replace:
            self.delete_schema(schema, option="Cascade")
        self.execute_query(f"CREATE SCHEMA IF NOT EXISTS {schema}", close=close)
    
    def delete_table(self, schema, table_name, option="Restrict", close=False):
        """Delete table in schema. Option can be "Cascade" or "Restrict" (default):
        https://www.postgresql.org/docs/14/sql-droptable.html
        """
        self.execute_query(f"DROP TABLE IF EXISTS {schema}.{table_name} {option}", close=close)

    def create_table(self, schema, table_name, table_columns, replace=False, close=False):
        """Create schema. table columns is a list of tuples, with each tuple containing
        two strings: the first defines the column name and the second the column's type
        https://www.postgresql.org/docs/14/sql-createtable.html
        """
        column_str = ", ".join(map(" ".join, table_columns))
        if replace:
            self.delete_table(schema, table_name, option="Cascade")
        self.execute_query(f"CREATE TABLE IF NOT EXISTS {schema}.{table_name} ({column_str})", close=close)
        
    def copy_csv_to_table(self, schema, table_name, csv_path, header=False, close=False):
        if not header:
            header_str = " CSV HEADER"
        self.execute_query(f"COPY {schema}.{table_name} FROM '{csv_path}' DELIMITER ','{header_str}", close=close)
        
    def insert_df_into_table(self, schema, table_name, df, close=False, **kwargs):
        if len(df) > 0:
            columns = ",".join(list(df.columns))
            insert_stmt = f"INSERT INTO {schema}.{table_name} ({columns}) VALUES %s"
            with self.conn as conn, conn.cursor() as cur:
                execute_values(cur, insert_stmt, df.values, **kwargs)
        else:
            print("Input dataframe, df, is empty: No data was written to the database!")
        if close:
            self.close_connection()   
        
    def select_query_to_df(self, query, close=False):
        """Execute input SQL query using pandas.read_sql and return resulting table as a dataframe.
        """
        df = pd.read_sql(query, self.conn)
        if close:
            self.close_connection()         
        return df
