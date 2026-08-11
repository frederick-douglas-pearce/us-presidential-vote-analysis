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

A third invariant joined them in #140, and it guards a different property — not layering
but **provenance**. ``usvote/pv/absences.py`` classifies pre-1976 popular-vote absences
from public-domain sources so the public snapshot needs no UCSB input (D022/D030), and
``tests/unit/test_ucsb_transform.py::TestRealCorpus`` uses UCSB as the *control* that
validates it. Both properties collapse if the two ever touch, in either direction: a
forward import would make the catalog UCSB-derived after all, and a **back**-import
(anything under ``usvote/ucsb/`` reaching for the catalog) would make the control test
circular — UCSB would be checking a number it had supplied. The back-direction is the one
with teeth, so it is enforced as its own test rather than folded into the sweep above.

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
import subprocess
import sys
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


def imports(source: str, module: str) -> bool:
    """Whether ``source`` imports ``module``, in **any** of the spellings Python allows.

    Naively matching only ``import usvote.hybrid`` / ``from usvote.hybrid`` misses
    ``from usvote import hybrid`` — which is the prevailing style in this repo, including
    inside the very subpackages being guarded (``usvote/mit/__main__.py``,
    ``usvote/ucsb/scrape.py``). A guard blind to the common spelling is worse than none,
    since it reads as enforcement. Parsed rather than grepped, so it also cannot
    false-positive on a docstring that quotes an import line.
    """
    package, _, name = module.rpartition(".")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(a.name == module or a.name.startswith(f"{module}.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == module or (node.module or "").startswith(f"{module}."):
                return True
            if node.module == package and any(a.name == name for a in node.names):
                return True
    return False


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
    modules = _modules_under(*_LOWER_SUBPACKAGES)
    assert modules, "found no lower-subpackage modules — the guard would pass vacuously"
    offenders = [
        py.relative_to(PKG_ROOT).as_posix()
        for py in modules
        if imports(py.read_text(), "usvote.hybrid")
    ]
    assert not offenders, f"these must not import usvote.hybrid: {offenders}"


@pytest.mark.parametrize(
    "line",
    [
        "import usvote.hybrid",
        "from usvote.hybrid import build_hybrid_frame",
        "from usvote import hybrid",
        "from usvote import config, hybrid",
        "import usvote.hybrid as h",
    ],
)
def test_the_import_guard_catches_every_spelling(line: str) -> None:
    """Including ``from usvote import hybrid`` — the spelling this repo prefers."""
    assert imports(line, "usvote.hybrid")


@pytest.mark.parametrize(
    "line",
    [
        "from usvote import config",
        "import usvote.join",
        "x = 'from usvote import hybrid'",
        '"""A docstring naming from usvote import hybrid."""',
    ],
)
def test_the_import_guard_does_not_over_match(line: str) -> None:
    """A near-miss import, or the words quoted in a string, is not a dependency."""
    assert not imports(line, "usvote.hybrid")


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


# --- the #140 provenance firewall -------------------------------------------


ABSENCES = PKG_ROOT / "pv" / "absences.py"


def test_the_absence_catalog_imports_nothing_from_ucsb() -> None:
    """The forward direction: the catalog must not be UCSB-derived (D022/D030)."""
    assert not imports(ABSENCES.read_text(), "usvote.ucsb")


def test_the_absence_catalog_reads_no_ucsb_artifact() -> None:
    """Not just imports — no corpus path, no env var, no ``ucsb`` literal in code.

    Over :func:`code_only`, so the module's docstring may explain the UCSB relationship
    (it must, in fact) without the guard punishing accurate documentation.
    """
    source = code_only(ABSENCES.read_text()).lower()
    for needle in ("ucsb", "usvote_ucsb_html_dir"):
        assert needle not in source, (
            f"usvote/pv/absences.py names {needle!r} in code. The catalog's whole value "
            "is that it reaches its classifications without UCSB; explain the "
            "relationship in the docstring instead."
        )


def test_nothing_under_ucsb_imports_the_absence_catalog() -> None:
    """The **back** direction — the one that protects something.

    ``TestRealCorpus`` checks the curated roster against UCSB's. If any ``usvote/ucsb/``
    module imported the catalog, UCSB's roster could inherit the very classifications it
    is supposed to be independently corroborating, and the control test would pass by
    construction while proving nothing.
    """
    modules = _modules_under("ucsb")
    assert modules, "found no modules under usvote/ucsb/ — the guard would pass vacuously"
    offenders = [
        py.relative_to(PKG_ROOT).as_posix()
        for py in modules
        if imports(py.read_text(), "usvote.pv.absences")
    ]
    assert not offenders, (
        "these must not import usvote.pv.absences — it would make the "
        f"TestRealCorpus cross-source control test circular: {offenders}"
    )


#: Derives the curated roster in a **fresh interpreter** with ``usvote.ucsb`` made
#: unimportable, then reports what it observed. Proving the property beats grepping for
#: it: a lazy in-function import, or a transitive one through ``usvote.pv.status``, would
#: survive both static checks above and die here. Run as a subprocess rather than by
#: deleting from ``sys.modules`` — that leaks into every test that follows.
_NO_UCSB_PROGRAM = """
import sys


class _BlockUCSB:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "usvote.ucsb" or fullname.startswith("usvote.ucsb."):
            raise ImportError(f"usvote.ucsb is unimportable in this process: {fullname}")
        return None


sys.meta_path.insert(0, _BlockUCSB())

import pandas as pd

from usvote.pv.absences import build_curated_roster
from usvote.pv.status import PV_STATUS_LEGISLATURE_CHOSEN, PV_STATUS_POPULAR_VOTE

LEGISLATURE = ["Delaware", "Georgia", "Louisiana", "New York", "South Carolina",
               "Vermont"]
frame = pd.DataFrame(
    [{"year": 1824, "state": s, "is_total": False, "total_electoral_votes": 5}
     for s in [*LEGISLATURE, "Pennsylvania"]]
    + [{"year": 1824, "state": None, "is_total": True, "total_electoral_votes": 99}]
)
roster = build_curated_roster(frame, source="PROOF", years=[1824])
by_state = dict(zip(roster["state"], roster["pv_status"]))

assert len(roster) == 7, roster
assert all(by_state[s] == PV_STATUS_LEGISLATURE_CHOSEN for s in LEGISLATURE), by_state
assert by_state["Pennsylvania"] == PV_STATUS_POPULAR_VOTE, by_state
assert "usvote.ucsb" not in sys.modules, sorted(sys.modules)
print("OK")
"""


def test_the_curated_roster_derives_with_ucsb_unimportable() -> None:
    """The strongest form of the firewall: prove it, don't grep it."""
    result = subprocess.run(
        [sys.executable, "-c", _NO_UCSB_PROGRAM],
        capture_output=True,
        text=True,
        cwd=PKG_ROOT.parents[1],
    )
    assert result.returncode == 0, (
        f"deriving the curated roster reached usvote.ucsb.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.stdout.strip().endswith("OK")


#: The same blocker, applied to the module that builds the **public artifact** (#139).
#: `build_curated_roster` proving itself UCSB-free is necessary but not sufficient: what
#: matters for D030 is that the whole snapshot build — imports and all — never reaches
#: UCSB, which is the claim D048 makes and the reason the pre-1976 `pv_status` may ship.
_NO_UCSB_SNAPSHOT_PROGRAM = """
import sys


class _BlockUCSB:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "usvote.ucsb" or fullname.startswith("usvote.ucsb."):
            raise ImportError(f"usvote.ucsb is unimportable in this process: {fullname}")
        return None


sys.meta_path.insert(0, _BlockUCSB())

import usvote.snapshot  # the public snapshot build, DB stack and all

assert hasattr(usvote.snapshot, "derive_curated_pv_status_roster")
assert "usvote.ucsb" not in sys.modules, sorted(sys.modules)
print("OK")
"""


def test_the_snapshot_build_imports_with_ucsb_unimportable() -> None:
    """The public snapshot build reaches no UCSB code, proven rather than asserted.

    D048's licensing claim rests on this: the pre-1976 ``pv_status`` values may ship
    because they come from the in-repo catalog over the EC spine, not from UCSB's
    roster. A stray import — added later for convenience, or arriving transitively —
    would quietly make the claim false while every other test stayed green.
    """
    result = subprocess.run(
        [sys.executable, "-c", _NO_UCSB_SNAPSHOT_PROGRAM],
        capture_output=True,
        text=True,
        cwd=PKG_ROOT.parents[1],
    )
    assert result.returncode == 0, (
        f"importing usvote.snapshot reached usvote.ucsb.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.stdout.strip().endswith("OK")


def test_the_ucsb_blocker_in_that_program_actually_blocks() -> None:
    """Non-vacuity: if the blocker were inert the proof above would prove nothing."""
    probe = _NO_UCSB_PROGRAM.replace(
        'print("OK")', 'import usvote.ucsb.transform\nprint("NOT BLOCKED")'
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=PKG_ROOT.parents[1],
    )
    assert result.returncode != 0
    assert "unimportable in this process" in result.stderr
