"""Runnable entry point — ``python -m usvote.census``.

Two subcommands, with ``load`` as the bare default (the D027 convention):

- ``python -m usvote.census`` / ``python -m usvote.census load`` — read the local
  corpus, parse both published workbooks, stitch and correct, load
  ``dwh.census_population`` **and** ``dwh.election_population``
  (:func:`usvote.census.pipeline.run_census_pipeline`), then rebuild the
  ``dwh.election_per_capita`` view over the second
  (:func:`usvote.census.per_capita.create_per_capita_view`). The view rebuild lives
  here rather than in the pipeline because this module is a composition root under
  D027, exactly as :mod:`usvote.warehouse` is — see ``_run_load``.
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
from usvote.census.per_capita import create_per_capita_view
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

    # The close is NOT delegated to the pipeline: this function owns it, in the
    # ``finally`` below.
    # ``run_census_pipeline`` has no ``try/finally`` of its own, so its ``close=True``
    # never fires on a raise — and a DB error this function does not *name* would then
    # leak the connection just as surely as one it fails to catch. One owner, one exit.
    try:
        loaded = run_census_pipeline(dbc, corpus_dir, replace=replace)
        # The view is rebuilt HERE, not inside the pipeline, and both halves of that
        # matter (#184 / D064(c-bis) — the record of this repair locus; D064(e) is
        # the separate skip-vs-raise ruling, which governs the closing line below).
        #
        # **Why it must happen at all.** `create_table(replace=True)` issues
        # `DROP TABLE ... CASCADE` (``usvote.db``), and ``dwh.election_per_capita``
        # depends on ``dwh.election_population`` — so a ``--replace`` refresh takes the
        # view with it and, without this call, leaves it dropped while exiting 0. On a
        # plain load it is the only thing that ever creates the view outside
        # ``python -m usvote all``. Reproduced against a live database during #184's
        # review, which is why it is a call rather than a caveat in the docstring.
        #
        # **Why here and not in ``run_census_pipeline``.** That pipeline is shared with
        # ``usvote.warehouse.run_warehouse``, whose ``rebuild_views`` is documented as
        # the one place the view ordering is expressed; putting view creation in the
        # shared stage would build it twice on an ``all`` build and split that knowledge
        # across two modules. A per-package ``__main__`` is a composition root under
        # D027, exactly as ``warehouse.py`` is, so this is the same architecture applied
        # to the other entry point: each composition layer owns view creation, and
        # ``run_census_pipeline`` stays view-free like its MIT and UCSB siblings.
        #
        # Safe unconditionally: it is `CREATE OR REPLACE` and skips when its input
        # table is absent (D064(e) — it returns False rather than raising).
        view_created = create_per_capita_view(dbc)
    except (CensusScrapeError, CensusTransformError, CensusParseError) as e:
        print(f"Census load failed: {e}", file=sys.stderr)
        print(
            "Nothing was loaded — the corpus, parse and jurisdiction guards all run "
            "before the transaction opens.",
            file=sys.stderr,
        )
        return 1
    except psycopg2.errors.UniqueViolation:
        # The one DB error with a *documented* meaning here: the table already holds
        # these rows, which is the non-destructive guard working as designed rather
        # than a failure. Deliberately narrow — an earlier version caught the whole
        # ``psycopg2.Error`` tree while printing advice that only fits this case, so a
        # ForeignKeyViolation or a dropped connection got told to pass ``--replace``.
        print(
            "Census load refused: dwh.census_population already holds these rows. "
            "That is the documented non-destructive guard, not a crash — pass "
            "--replace to rebuild the table.",
            file=sys.stderr,
        )
        return 1
    finally:
        dbc.close_connection()

    # The view half of this line reports what the call *returned* rather than
    # asserting the happy path. That skip branch is unreachable from here today —
    # the load above writes dwh.election_population, so the probe always finds it —
    # but the return value exists precisely to report a skip, and discarding it is
    # how a message that cannot be wrong today becomes one that lies after the next
    # change (#184 round-2 review).
    view_line = (
        "the dwh.election_per_capita view is rebuilt."
        if view_created
        else "the dwh.election_per_capita view was SKIPPED — its input table is "
        "absent."
    )
    print(
        f"Census ingestion complete — {len(loaded)} dwh.census_population rows, "
        f"{loaded['census_year'].min()}-{loaded['census_year'].max()}, "
        f"{loaded['state'].nunique()} jurisdictions. "
        f"dwh.election_population is rebuilt and {view_line}"
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
        help="Rebuild dwh.census_population and dwh.election_population before "
        "loading, then rebuild the dwh.election_per_capita view over the second. "
        "Table-level only — never touches the EC spine, the PV tables, or the schema.",
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
