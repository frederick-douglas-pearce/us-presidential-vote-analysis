"""D028 structural invariant: ``usvote/api/`` never imports the DB / build stack.

The API serves a read-only snapshot with **no live DB at serve time**. The plan makes
that structural, not incidental: nothing under ``usvote/api/`` may import
:mod:`usvote.db`, psycopg2, :mod:`usvote.snapshot` (the build module, which drags pandas
+ the DB stack), :mod:`usvote.hybrid` (E7's computation core — pandas again), or pandas
itself. This mirrors the project's other greppable layering guards
(``test_layering.test_no_pv_module_names_the_ec_votes_fact``;
``test_warehouse.test_no_pv_source_imports_the_warehouse_composition_root``) — a violation
fails this test, not review.

**Read the matcher before adding a module.** It greps each file's own text for a literal
module name; it does **not** follow transitive imports. So an allowed module that itself
pulls a forbidden one is invisible here — which is exactly why the D033 ``docker-build`` CI
job boots the slim image against a placeholder snapshot as the backstop. Every heavy module
reachable from ``usvote/api/`` must therefore be named in :data:`_FORBIDDEN` explicitly.
"""

from __future__ import annotations

import re
from pathlib import Path

import usvote.api as api

#: The forbidden imports under ``usvote/api/``. ``usvote.snapshot`` (build),
#: ``usvote.hybrid`` (E7's computation core) and pandas are forbidden alongside the obvious
#: DB modules because importing any of them would transitively pull the whole build/DB stack
#: across the serve-time boundary D028 draws — and the slim D033 container installs the
#: serve dependency group only, so such an import fails at *runtime*, not at test time.
_FORBIDDEN = ("usvote.db", "psycopg2", "usvote.snapshot", "usvote.hybrid", "pandas")


def test_api_imports_no_db_or_build_stack() -> None:
    pkg_root = Path(api.__file__).parent
    # Match `import <mod>` / `from <mod> import ...` for each forbidden module, being
    # careful that `usvote.snapshot` does NOT match the allowed `usvote.snapshot_schema`
    # (word boundary after the module name).
    patterns = [
        re.compile(rf"(^|\W)(import\s+{re.escape(m)}|from\s+{re.escape(m)})\b")
        for m in _FORBIDDEN
    ]
    offenders: list[str] = []
    for py in pkg_root.rglob("*.py"):
        text = py.read_text()
        for mod, pattern in zip(_FORBIDDEN, patterns, strict=True):
            if pattern.search(text):
                offenders.append(f"{py.relative_to(pkg_root).as_posix()} -> {mod}")
    assert not offenders, f"usvote/api must not import the DB/build stack: {offenders}"
