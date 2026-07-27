"""Runnable entry point — ``python -m usvote`` runs an ingestion build.

Subcommand-based (#84b), but **bare ``python -m usvote`` still runs the EC pipeline**
for backward compatibility (it is the most common command and the only one needing just
``USVOTE_SHAPEFILE_PATH`` + DB):

- ``python -m usvote`` / ``python -m usvote ec`` — scrape + load the EC spine into
  ``dwh`` (the historical default; ``--replace`` still works bare, before or without
  the subcommand).
- ``python -m usvote all`` — build the **whole** warehouse: EC spine, MIT PV,
  optionally UCSB PV, then the resolved-PV + EC<->PV join views
  (:func:`usvote.warehouse.run_warehouse`).

Bare is kept on EC rather than re-pointed at ``all`` deliberately: ``all`` additionally
requires ``USVOTE_MIT_CSV_PATH`` (and the UCSB snapshot for the full set), so silently
making the default command need more config would break a documented invocation (D027).

**``--replace`` has two scopes.** For ``ec`` / bare it drops and recreates the whole
``dwh`` schema (the destructive EC rebuild). For ``all`` it forwards to the EC step the
same way — which *cascades* the PV tables and views away — while the PV sources
always load ``replace=False`` (append onto the fresh schema) and the views are rebuilt
(:func:`usvote.warehouse.run_warehouse`). A re-run **without** ``--replace`` over an
already-built warehouse fails loud on a unique/PK violation (the intended
non-destructive guard), not silently; recover a partial build with ``--replace``.

**UCSB gating for ``all`` is explicit and loud.** UCSB content is non-redistributable
and lives outside the repo (D016/D022), so a fresh public clone builds EC + MIT (the
redistributable core) and skips UCSB (the analysis-only control) unless the private
snapshot is present. By default ``all`` auto-detects ``USVOTE_UCSB_HTML_DIR`` and, when
it is absent, builds **without** UCSB after printing a prominent notice.
``--require-ucsb`` turns an absent snapshot into a hard failure (for an analysis
workflow that must have the control); ``--no-ucsb`` skips it unconditionally.

Deliberately thin — no pipeline logic lives here; it resolves environment -> config ->
connection and calls the programmatic entry points.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Mapping
from typing import Any

from usvote import config, scrape
from usvote.db import DBC, DBConnectionError
from usvote.mit.config import mit_csv_path_from_env
from usvote.pipeline import run_ec_pipeline
from usvote.ucsb.config import ucsb_html_dir_from_env
from usvote.warehouse import SOURCE_UCSB, run_warehouse

_NO_CORPUS_HELP = (
    "Scrape archives.gov live even when USVOTE_EC_HTML_DIR points at a local corpus. "
    "By default a complete corpus is used, which makes the rebuild network-free."
)

_REPLACE_HELP = (
    "Drop and recreate the dwh schema before loading (destructive full rebuild). "
    "Omit to create-if-absent; a create-if-absent re-run over already-loaded data "
    "fails loud on a unique/PK violation."
)


def _connect(db_config: dict[str, Any]) -> DBC | None:
    """Prompt for the password if needed and connect; return ``None`` on failure."""
    # Prompt only when the password was not supplied via PGPASSWORD, so a preset secret
    # is not re-requested and never has to be committed.
    if "password" not in db_config:
        db_config["password"] = getpass.getpass(
            f"Password for {db_config['user']}@{db_config['host']}: "
        )
    try:
        return DBC(db_config)
    except DBConnectionError as e:
        print(e, file=sys.stderr)
        return None


def _resolve_ucsb_dir(
    args: argparse.Namespace, environ: Mapping[str, str]
) -> str | None:
    """Resolve the UCSB snapshot dir for ``all``, honoring the gating flags.

    ``--no-ucsb`` -> always ``None`` (skip). ``--require-ucsb`` -> resolve or raise
    :class:`~usvote.config.ConfigError` (an absent snapshot is a hard failure). Default
    -> auto-detect: the resolved dir if ``USVOTE_UCSB_HTML_DIR`` is set and exists, else
    ``None`` (skip). Returning ``None`` means "build without UCSB", surfaced loudly by
    the caller.
    """
    if args.no_ucsb:
        return None
    try:
        return ucsb_html_dir_from_env(environ)
    except config.ConfigError:
        # Absent snapshot: a hard failure only under --require-ucsb; otherwise skip.
        if args.require_ucsb:
            raise
        return None


def _resolve_ec_fetch(
    args: argparse.Namespace, environ: Mapping[str, str]
) -> scrape.Fetch:
    """Resolve the EC fetch seam: the local Archives corpus, or the live network.

    Mirrors :func:`_resolve_ucsb_dir`'s posture — auto-detect, but **loudly** — with
    one deliberate difference in strictness. Skipping UCSB merely builds without an
    optional control; swapping the EC fetch source changes where the *spine's* data
    comes from, so a detected corpus is verified complete
    (:func:`usvote.scrape.assert_corpus_covers_years`) before it is used. A stale
    corpus fails here, by name, instead of silently building a warehouse short a year.

    ``--no-corpus`` forces the live scrape. When ``USVOTE_EC_HTML_DIR`` is unset we
    scrape live, as before — the corpus is an optimization, never a requirement.
    """
    if getattr(args, "no_corpus", False):
        return scrape.fetch_url
    if not environ.get(config.EC_HTML_DIR_VAR):
        # Genuinely unconfigured: scrape live, as before. Distinguished from a
        # configured-but-broken corpus below, which must NOT silently hit the network —
        # an unmounted volume would otherwise fire ~50 live requests at a user who asked
        # for an offline rebuild. Announced because a *misspelled* variable name is
        # indistinguishable from an unset one, and the two differ by ~50 requests.
        print(
            f"{config.EC_HTML_DIR_VAR} is not set — scraping archives.gov live. "
            f"Build a local corpus with `python -m usvote corpus` to rebuild offline."
        )
        return scrape.fetch_url
    html_dir = config.ec_html_dir_from_env(environ)
    scrape.assert_corpus_covers_years(html_dir)
    print(f"Using the local Archives corpus at {html_dir} (no network requests).")
    return scrape.fetch_from_corpus(html_dir)


def _run_corpus(args: argparse.Namespace) -> int:
    """Fetch the Archives corpus to ``USVOTE_EC_HTML_DIR``. No DB involved.

    Resolves with ``must_exist=False``: this is the one command for which the
    directory is an *output*, so requiring it to pre-exist would make the first run on
    a fresh machine fail with advice to run this very command.
    """
    try:
        html_dir = config.ec_html_dir_from_env(os.environ, must_exist=False)
    except config.ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    print(
        f"Snapshotting the Archives into {html_dir}. Pages already present are "
        f"skipped; new ones are fetched {scrape.CRAWL_DELAY_SECONDS}s apart to honor "
        f"archives.gov/robots.txt, so a full first run takes several minutes."
    )
    try:
        manifest = scrape.snapshot_election_years(html_dir)
    except scrape.ScrapeError as e:
        print(f"Corpus fetch failed: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Cannot write the corpus to {html_dir}: {e}", file=sys.stderr)
        return 1
    # Count files on disk, not manifest keys: a stale key (an out-of-scope year, or a
    # recorded non-200 attempt) would otherwise inflate the reported page count.
    pages = sum(
        1
        for k, v in manifest.items()
        if k != "index" and v.get("http_status") == 200
    )
    print(f"Archives corpus complete: {pages} year page(s) + the index in {html_dir}.")
    return 0


def _run_ec(replace: bool, fetch: scrape.Fetch = scrape.fetch_url) -> int:
    try:
        shapefile_path = config.shapefile_path_from_env()
        db_config = config.db_config_from_env()
    except config.ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    dbc = _connect(db_config)
    if dbc is None:
        return 1

    run_ec_pipeline(dbc, shapefile_path, replace=replace, fetch=fetch, close=True)
    print("EC ingestion complete.")
    return 0


def _run_all(args: argparse.Namespace) -> int:
    environ = os.environ
    try:
        shapefile_path = config.shapefile_path_from_env(environ)
        mit_csv_path = mit_csv_path_from_env(environ)
        ucsb_html_dir = _resolve_ucsb_dir(args, environ)
        db_config = config.db_config_from_env(environ)
        # Resolved BEFORE _connect: a stale corpus must not abort after the user has
        # typed a DB password, leaving an open connection that close=True never reaches.
        ec_fetch = _resolve_ec_fetch(args, environ)
    except config.ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    except scrape.ScrapeError as e:
        print(f"Archives corpus error: {e}", file=sys.stderr)
        return 2

    if ucsb_html_dir is None:
        # D024/D016: a build missing UCSB is never silent — loud either way. UCSB is the
        # analysis-only consistency control; a hybrid/analysis run over a warehouse that
        # quietly lacks it would produce subtly wrong numbers with no signal. The remedy
        # differs by cause: --no-ucsb is a deliberate choice (nothing to fix), whereas
        # an auto-skip means the snapshot was simply not found (point to the fix).
        remedy = (
            "This was requested with --no-ucsb."
            if args.no_ucsb
            else (
                "Pass --require-ucsb to demand the full set, or set "
                "USVOTE_UCSB_HTML_DIR to the snapshot directory to include it."
            )
        )
        print(
            "NOTICE: building WITHOUT UCSB — the warehouse will hold only the "
            "redistributable EC + MIT core, and any hybrid analysis will lack the UCSB "
            f"consistency control. {remedy}",
            file=sys.stderr,
        )

    dbc = _connect(db_config)
    if dbc is None:
        return 1

    result = run_warehouse(
        dbc,
        shapefile_path,
        mit_csv_path,
        ucsb_html_dir=ucsb_html_dir,
        replace=args.replace,
        fetch=ec_fetch,
        environ=environ,
        close=True,
    )
    sources = ", ".join(sorted(result.sources_loaded))
    ucsb_note = (
        f", UCSB {result.ucsb_pv_rows} PV / {result.ucsb_roster_rows} roster rows"
        if SOURCE_UCSB in result.sources_loaded
        else ""
    )
    print(
        f"Warehouse build complete — sources: {sources}; "
        f"EC {result.ec_rows} rows, MIT {result.mit_rows} rows"
        f"{ucsb_note}; join views rebuilt."
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m usvote",
        description="Scrape and load US presidential vote data into the dwh schema.",
    )
    # Kept at the top level too, so bare ``python -m usvote --replace`` (the historical
    # spelling, no subcommand) still works and maps to the EC rebuild.
    parser.add_argument("--replace", action="store_true", help=_REPLACE_HELP)
    parser.add_argument("--no-corpus", action="store_true", help=_NO_CORPUS_HELP)
    sub = parser.add_subparsers(dest="command")

    ec_p = sub.add_parser(
        "ec", help="Scrape and load the Electoral College spine (the bare default)."
    )
    # SUPPRESS default: when ``--replace`` is not given on the subcommand, do not add
    # the attribute, so the top-level ``--replace`` value survives (avoids the argparse
    # subparser-default-clobber gotcha).
    ec_p.add_argument(
        "--replace", action="store_true", default=argparse.SUPPRESS, help=_REPLACE_HELP
    )
    # SUPPRESS for the same reason as --replace above: without it the subparser's
    # False default clobbers a top-level ``--no-corpus ec``, silently ignoring the flag.
    ec_p.add_argument(
        "--no-corpus",
        action="store_true",
        default=argparse.SUPPRESS,
        help=_NO_CORPUS_HELP,
    )

    # Named ``corpus``, not ``snapshot``: ``python -m usvote.snapshot`` already builds
    # the API SQLite artifact, and a ``python -m usvote snapshot`` one character away
    # meaning "fetch Archives HTML" is exactly the same-spelling-different-meaning
    # collision D027/#84b exists to avoid. Every other name in this feature already
    # says corpus (corpus_filename, fetch_from_corpus, assert_corpus_covers_years).
    sub.add_parser(
        "corpus",
        help="Fetch the Archives HTML corpus to USVOTE_EC_HTML_DIR (no DB needed).",
    )

    all_p = sub.add_parser(
        "all",
        help="Build the whole warehouse: EC + MIT + (optional) UCSB + join views.",
    )
    all_p.add_argument(
        "--replace", action="store_true", default=argparse.SUPPRESS, help=_REPLACE_HELP
    )
    ucsb_group = all_p.add_mutually_exclusive_group()
    ucsb_group.add_argument(
        "--require-ucsb",
        action="store_true",
        help="Fail if the UCSB snapshot (USVOTE_UCSB_HTML_DIR) is absent, instead of "
        "building without it.",
    )
    ucsb_group.add_argument(
        "--no-ucsb",
        action="store_true",
        help="Skip UCSB unconditionally (build only the EC + MIT core).",
    )
    all_p.add_argument(
        "--no-corpus",
        action="store_true",
        default=argparse.SUPPRESS,
        help=_NO_CORPUS_HELP,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "corpus":
        return _run_corpus(args)
    if args.command == "all":
        return _run_all(args)
    # Bare (``command is None``) and explicit ``ec`` both run the EC pipeline. argparse
    # leaves ``replace`` set by the top-level parser (default False) unless the ``ec``
    # subcommand overrode it.
    try:
        fetch = _resolve_ec_fetch(args, os.environ)
    except (config.ConfigError, scrape.ScrapeError) as e:
        print(f"Archives corpus error: {e}", file=sys.stderr)
        return 2
    return _run_ec(getattr(args, "replace", False), fetch)


if __name__ == "__main__":
    raise SystemExit(main())
