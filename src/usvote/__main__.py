"""Runnable entry point — ``python -m usvote`` runs the EC ingestion pipeline.

This is the piece that closes #31's "a fresh machine runs the pipeline by setting
config, not editing source": it resolves all configuration from the environment (see
:mod:`usvote.config`), prompts for the DB password if it is not already supplied via
``PGPASSWORD``, constructs the :class:`~usvote.db.DBC` connection, and calls
:func:`~usvote.pipeline.run_ec_pipeline`.

Deliberately thin — no pipeline logic lives here; it only wires environment ->
config -> connection -> the existing programmatic entry point.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from usvote import config
from usvote.db import DBC, DBConnectionError
from usvote.pipeline import run_ec_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m usvote",
        description="Scrape Electoral College results and load the dwh schema.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Drop and recreate the dwh schema before loading (destructive full "
        "rebuild). Omit to create-if-absent.",
    )
    args = parser.parse_args(argv)

    try:
        shapefile_path = config.shapefile_path_from_env()
        db_config = config.db_config_from_env()
    except config.ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    # Prompt only when the password was not supplied via PGPASSWORD, so a preset
    # secret is not re-requested and never has to be committed.
    if "password" not in db_config:
        db_config["password"] = getpass.getpass(
            f"Password for {db_config['user']}@{db_config['host']}: "
        )

    try:
        dbc = DBC(db_config)
    except DBConnectionError as e:
        print(e, file=sys.stderr)
        return 1

    run_ec_pipeline(dbc, shapefile_path, replace=args.replace, close=True)
    print("EC ingestion complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
