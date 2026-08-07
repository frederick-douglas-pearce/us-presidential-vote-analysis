"""Runnable entry point — ``python -m usvote.mit`` loads the MIT popular-vote data.

Added in #84b to give MIT a symmetric ``__main__`` (before, ``run_mit_pipeline`` was
driven only by the integration test). A single subcommand, ``load``, is the default, so
bare ``python -m usvote.mit`` runs the pipeline:

- ``python -m usvote.mit`` / ``python -m usvote.mit load`` — read the MIT
  ``1976-2024-president.csv`` (``USVOTE_MIT_CSV_PATH``), transform + reconcile onto the
  canonical keys, and load **both** shared PV tables — ``dwh.pv_votes`` and, since #127,
  the ``dwh.pv_state_status`` roster (:func:`usvote.mit.pipeline.run_mit_pipeline`).

``--replace`` rebuilds **both** of those tables, and both are shared across sources — so
on a two-source warehouse it discards UCSB's rows as well, including the pre-1976
``legislature_chosen`` / ``not_participating`` roster that is the only record of which
states held no popular vote. Reload UCSB afterwards (or rebuild with
``python -m usvote all --replace``) rather than leaving the roster MIT-only.

Unlike UCSB there is no ``snapshot`` — MIT reads a single local CSV, so there is no
network stage to reproduce (the source asymmetry the package docs describe). ``load``
requires the EC spine to already be in ``dwh`` (its ``state`` FK targets ``dwh.state``);
run ``python -m usvote`` (or ``python -m usvote all``) first.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import Any

from usvote import config
from usvote.config import ConfigError
from usvote.db import DBC, DBConnectionError
from usvote.mit.config import mit_csv_path_from_env
from usvote.mit.pipeline import run_mit_pipeline


def _run_load(replace: bool) -> int:
    environ = os.environ
    try:
        csv_path = mit_csv_path_from_env(environ)
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

    loaded, roster = run_mit_pipeline(dbc, csv_path, replace=replace, close=True)
    print(
        f"MIT ingestion complete — {len(loaded)} dwh.pv_votes rows, "
        f"{len(roster)} dwh.pv_state_status roster rows."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m usvote.mit",
        description=(
            "Load the MIT Election Lab popular-vote data into dwh.pv_votes and its "
            "coverage roster into dwh.pv_state_status."
        ),
    )
    sub = parser.add_subparsers(dest="command")
    load_p = sub.add_parser(
        "load",
        help="Read the MIT CSV, reconcile, load dwh.pv_votes (the bare default).",
    )
    load_p.add_argument(
        "--replace",
        action="store_true",
        help="Rebuild both PV tables (pv_votes + pv_state_status) before loading. "
        "Table-level only — never touches the EC spine or the schema. WARNING: both "
        "tables are shared across sources, so this discards UCSB's rows too — "
        "including the pre-1976 legislature_chosen / not_participating roster, which "
        "only a UCSB reload restores.",
    )
    args = parser.parse_args(argv)

    # Bare (``command is None``) and explicit ``load`` both run the pipeline.
    replace = bool(getattr(args, "replace", False))
    return _run_load(replace)


if __name__ == "__main__":
    raise SystemExit(main())
