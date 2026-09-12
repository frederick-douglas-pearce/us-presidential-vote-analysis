"""Runnable entry point — ``python -m usvote.census``.

Two subcommands, with ``load`` as the bare default (the D027 convention):

- ``python -m usvote.census`` / ``python -m usvote.census load`` — read the local
  corpus, parse both published workbooks, stitch and correct, and load
  ``dwh.census_population`` (:func:`usvote.census.pipeline.run_census_pipeline`).
- ``python -m usvote.census snapshot`` — download the published source files into
  ``USVOTE_CENSUS_CORPUS_DIR`` and record their sha256s
  (:func:`usvote.census.scrape.snapshot_census_sources`). Run this once before the
  first load; it is the only command here that touches the network.

**Why ``load`` is the default when UCSB's is ``snapshot``.** UCSB's bare command meant
"snapshot" before it had subcommands at all, so its default is backward compatibility
rather than a principle. Census is new and inherits no history, so it takes the same
default as :mod:`usvote.mit` and the bare top-level — leaving UCSB the one documented
exception rather than making it a pattern.

``load`` requires the EC spine to already be in ``dwh``: the ``state`` FK targets
``dwh.state``, and the jurisdiction guard checks the census file's area names against
the spine's own state set. Run ``python -m usvote`` (or ``python -m usvote all``) first.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import Any

import psycopg2

from usvote import config
from usvote.census.config import census_corpus_dir_from_env
from usvote.census.parse import CensusParseError
from usvote.census.pipeline import run_census_pipeline
from usvote.census.scrape import (
    CensusScrapeError,
    describe_corpus,
    snapshot_census_sources,
)
from usvote.census.transform import CensusTransformError
from usvote.config import ConfigError
from usvote.db import DBC, DBConnectionError


def _run_snapshot() -> int:
    try:
        corpus_dir = census_corpus_dir_from_env(os.environ, must_exist=False)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    try:
        snapshot_census_sources(corpus_dir)
    except CensusScrapeError as e:
        print(f"Snapshot failed: {e}", file=sys.stderr)
        return 1
    print(f"Census corpus at {corpus_dir}: {describe_corpus(corpus_dir)}")
    return 0


def _run_load(replace: bool) -> int:
    environ = os.environ
    try:
        corpus_dir = census_corpus_dir_from_env(environ)
        db_config: dict[str, Any] = config.db_config_from_env(environ)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    if "password" not in db_config:
        db_config["password"] = getpass.getpass(
            f"Password for {db_config['user']}@{db_config['host']}: "
        )
    try:
        dbc = DBC(db_config)
    except DBConnectionError as e:
        print(e, file=sys.stderr)
        return 1

    try:
        loaded = run_census_pipeline(dbc, corpus_dir, replace=replace, close=True)
    except (
        CensusScrapeError,
        CensusTransformError,
        CensusParseError,
        psycopg2.Error,
    ) as e:
        # ``run_census_pipeline`` has no try/finally, so its ``close=True`` never fires
        # on a raise — close here rather than leaking the connection. Nothing was
        # written: both guards run before the transaction opens.
        print(f"Census load failed: {e}", file=sys.stderr)
        print(
            "The corpus, parse and jurisdiction guards all run before any write, so a "
            "failure from one of those loaded nothing. A UniqueViolation instead means "
            "the table already holds these rows — that is the documented "
            "non-destructive guard; pass --replace to rebuild.",
            file=sys.stderr,
        )
        dbc.close_connection()
        return 1
    print(
        f"Census ingestion complete — {len(loaded)} dwh.census_population rows, "
        f"{loaded['census_year'].min()}-{loaded['census_year'].max()}, "
        f"{loaded['state'].nunique()} jurisdictions."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m usvote.census",
        description=(
            "Snapshot the published Census population tables and load them into "
            "dwh.census_population."
        ),
    )
    sub = parser.add_subparsers(dest="command")
    load_p = sub.add_parser(
        "load",
        help="Parse the local corpus and load dwh.census_population (bare default).",
    )
    load_p.add_argument(
        "--replace",
        action="store_true",
        help="Rebuild dwh.census_population before loading. Table-level only — never "
        "touches the EC spine, the PV tables, or the schema.",
    )
    sub.add_parser(
        "snapshot",
        help="Download the published source files into USVOTE_CENSUS_CORPUS_DIR.",
    )
    args = parser.parse_args(argv)

    if args.command == "snapshot":
        return _run_snapshot()
    # Bare (``command is None``) and explicit ``load`` both run the pipeline.
    return _run_load(bool(getattr(args, "replace", False)))


if __name__ == "__main__":
    raise SystemExit(main())
