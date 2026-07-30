"""The source-namespacing layering invariants, as tests rather than conventions (D015).

``CLAUDE.md`` states the rule in both directions: EC is the source-of-truth spine (D006),
so a popular-vote source reading domain facts *from* the spine is expected, while the
reverse must never happen. Two greppable invariants express it:

- **No module under ``usvote/pv/`` names ``dwh.votes`` in code.** The shared PV contracts
  are source-neutral; EC-star-schema knowledge belongs to the top-level EC-domain modules
  (``spine.py``, ``years.py``, ``join.py``, ``snapshot.py``, ``hybrid.py``,
  ``warehouse.py``). A ``dwh.votes`` reference in a ``usvote/pv/`` **query** means EC
  knowledge has leaked into the shared layer.
- **Nothing under ``usvote/{mit,ucsb,pv}/`` imports a module that sits above it** — the
  ``warehouse.py`` composition root, or ``hybrid.py``. A back-import inverts D015 into a
  cycle.

**Why this file exists.** Both rules were cited as "the greppable ``dwh.votes`` guard" in
several docstrings (``join.py``, ``warehouse.py``, ``test_api_import_graph.py``) and by the
``warehouse`` back-import test, which says it "mirrors" it. It turned out only the
``warehouse`` half was ever enforced: the ``dwh.votes`` rule was a human-greppable
convention, so nothing failed if it regressed. Found while adding ``usvote/hybrid.py``
(#121), whose structural protection rests on the same rule.

**Code, not prose** — and that distinction is load-bearing rather than a convenience.
Enforcing this over raw file text immediately flagged ``pv/load.py``, whose docstring
explains that ``usvote.spine.read_ec_participation`` has *already* read ``dwh.votes`` by
the time the roster loads. That prose is correct and is exactly the kind of cross-layer
reasoning the docs should record; banning the literal would make the guard punish accurate
documentation. So :func:`code_only` drops docstrings and comments and keeps **every other
string literal** — SQL lives in f-strings, and SQL is precisely where a real violation
would hide.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import usvote

PKG_ROOT = Path(usvote.__file__).parent

#: The subpackages that sit *below* the EC-domain top-level modules.
_LOWER_SUBPACKAGES = ("mit", "ucsb", "pv")


def code_only(source: str) -> str:
    """Return ``source`` with docstrings and comments removed, other strings intact.

    ``ast.unparse`` drops comments for free; docstrings are blanked node-by-node. What
    survives is the code — including the string literals that carry SQL, which is the thing
    the layering guard actually cares about.
    """
    tree = ast.parse(source)
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            first.value.value = ""
    return ast.unparse(tree)


def _modules_under(*subpackages: str) -> list[Path]:
    return [py for sub in subpackages for py in sorted((PKG_ROOT / sub).rglob("*.py"))]


# --- the scan mechanism itself ----------------------------------------------


PROSE_AND_SQL = '''
"""A module docstring that mentions dwh.votes for explanatory reasons."""

def f(schema: str) -> str:
    """Another docstring naming dwh.votes."""
    # A comment naming dwh.votes.
    return f"SELECT * FROM {schema}.votes"

def g() -> str:
    return "SELECT * FROM dwh.votes"
'''


def test_the_scan_ignores_prose() -> None:
    """A docstring or comment naming the fact is documentation, not a dependency."""
    stripped = code_only(PROSE_AND_SQL)
    assert "explanatory reasons" not in stripped
    assert "A comment naming" not in stripped


def test_the_scan_still_sees_sql_in_a_string_literal() -> None:
    """The non-vacuity proof: stripping prose must not strip the queries.

    Without this, ``code_only`` could return an empty string and every layering assertion
    below would pass by inspecting nothing.
    """
    stripped = code_only(PROSE_AND_SQL)
    assert "dwh.votes" in stripped  # from g()'s literal
    assert "{schema}.votes" in stripped  # and the f-string survives as an f-string


# --- the invariants ---------------------------------------------------------


def test_no_pv_module_names_the_ec_votes_fact_in_code() -> None:
    """D006/D015: EC-star-schema knowledge stays out of the shared PV layer.

    ``usvote/spine.py`` exists precisely so a PV stage can read EC facts across a DI seam
    without naming the fact table itself.
    """
    modules = _modules_under("pv")
    assert modules, "found no modules under usvote/pv/ — the guard would pass vacuously"
    offenders = [
        py.relative_to(PKG_ROOT).as_posix()
        for py in modules
        if "dwh.votes" in code_only(py.read_text())
    ]
    assert not offenders, (
        "these must not name dwh.votes in code — read EC facts through usvote.spine "
        f"instead: {offenders}"
    )


def test_no_lower_subpackage_imports_the_hybrid_computation() -> None:
    """D015: ``usvote/hybrid.py`` is EC-domain and sits **above** every PV source.

    It reads the resolved EC<->PV join view and the shared roster; a PV source importing it
    would invert the dependency exactly as a ``usvote.warehouse`` back-import would (the
    sibling guard in ``test_warehouse.py``).
    """
    pattern = re.compile(r"(^|\W)(import\s+usvote\.hybrid|from\s+usvote\.hybrid)")
    modules = _modules_under(*_LOWER_SUBPACKAGES)
    assert modules, "found no lower-subpackage modules — the guard would pass vacuously"
    offenders = [
        py.relative_to(PKG_ROOT).as_posix()
        for py in modules
        if pattern.search(py.read_text())
    ]
    assert not offenders, f"these must not import usvote.hybrid: {offenders}"


def test_hybrid_is_a_top_level_ec_domain_module() -> None:
    """It belongs beside ``join.py``/``spine.py``, never under a PV subpackage."""
    assert (PKG_ROOT / "hybrid.py").is_file()
    for sub in _LOWER_SUBPACKAGES:
        assert not (PKG_ROOT / sub / "hybrid.py").exists()


@pytest.mark.parametrize("module", ["usvote.hybrid", "usvote.warehouse"])
def test_the_ec_domain_modules_are_importable_without_a_pv_source_importing_back(
    module: str,
) -> None:
    """Import them standalone — a cycle would surface here as an ImportError."""
    __import__(module)
