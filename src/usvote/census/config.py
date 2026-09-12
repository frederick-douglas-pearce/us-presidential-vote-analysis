"""Census-source configuration — resolve the local corpus directory from the env.

Per-source inputs live in the relevant subpackage's own config module, as
``USVOTE_MIT_CSV_PATH`` does in :mod:`usvote.mit.config`. Importing *up* from a source
subpackage into the source-agnostic top-level :mod:`usvote.config` is the D006-allowed
direction.

``must_exist`` mirrors :func:`usvote.config.ec_html_dir_from_env`, and for the same
reason: this directory is an **output** for ``python -m usvote.census snapshot`` (which
creates it) and an **input** for every load that replays it. Requiring it to pre-exist
on the write side would fail a fresh machine with advice to run the very command that
just failed.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from usvote.config import ConfigError, require_path_from_env

#: Environment variable holding the path to the local Census corpus directory.
#: Named to sit beside ``USVOTE_EC_HTML_DIR`` and ``USVOTE_UCSB_HTML_DIR``; ``CORPUS``
#: rather than ``HTML`` because what it holds is published spreadsheets, not markup.
CENSUS_CORPUS_DIR_VAR = "USVOTE_CENSUS_CORPUS_DIR"

_UNSET_HINT = (
    "Point it at a local Census corpus directory, then populate it with: "
    "python -m usvote.census snapshot"
)


def census_corpus_dir_from_env(
    environ: Mapping[str, str] = os.environ, *, must_exist: bool = True
) -> str:
    """Return the Census corpus directory from ``USVOTE_CENSUS_CORPUS_DIR``.

    Required when asked for, and deliberately with no default — there is no sensible
    default for a machine-local data directory, and defaulting would risk snapshotting
    into (or replaying from) the wrong place.

    Unlike the UCSB snapshot this corpus is public-domain data (17 U.S.C. §105, S1 §3),
    so nothing about it is licence-gated; what the variable buys is a load that costs
    zero network requests and a pinned, hash-recorded copy of files the Bureau can
    re-issue under the same URL. ``environ`` is injectable for testing.
    """
    if not must_exist:
        path = environ.get(CENSUS_CORPUS_DIR_VAR)
        if not path:
            raise ConfigError(f"{CENSUS_CORPUS_DIR_VAR} is not set. {_UNSET_HINT}")
        return path
    return require_path_from_env(
        CENSUS_CORPUS_DIR_VAR,
        environ,
        unset_hint=_UNSET_HINT,
        missing_hint="Populate it with: python -m usvote.census snapshot",
    )
