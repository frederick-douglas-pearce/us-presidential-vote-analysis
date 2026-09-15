"""The source-namespacing layering invariants, as tests rather than conventions (D015).

``CLAUDE.md`` states the rule in both directions: EC is the source-of-truth spine (D006),
so a popular-vote source reading domain facts *from* the spine is expected, while the
reverse must never happen. Two greppable invariants express it:

- **No module under ``usvote/pv/`` names ``dwh.votes`` in code.** The shared PV contracts
  are source-neutral; EC-star-schema knowledge belongs to the top-level EC-domain modules
  (``spine.py``, ``years.py``, ``join.py``, ``snapshot.py``, ``hybrid.py``,
  ``warehouse.py``). A ``dwh.votes`` reference in a ``usvote/pv/`` **query** means EC
  knowledge has leaked into the shared layer.
- **Nothing under ``usvote/{mit,ucsb,pv,census}/`` imports a module that sits above it** — the
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
#:
#: **Every source subpackage must be listed here**, or the guards that scan it are
#: silently vacuous for it — this tuple is not derived from the filesystem, so a new
#: subpackage is unguarded until it is named. ``census`` joined in #181.
_LOWER_SUBPACKAGES = ("mit", "ucsb", "pv", "census")


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


@pytest.mark.parametrize("subpackage", ["pv", "census"])
def test_no_lower_subpackage_names_the_ec_votes_fact_in_code(subpackage: str) -> None:
    """D006/D015: EC-star-schema knowledge stays out of the shared and source layers.

    ``usvote/spine.py`` exists precisely so a stage can read EC facts across a DI seam
    without naming the fact table itself.

    **``census`` was added in #183 review.** Two census modules already asserted in their
    docstrings that "the greppable D015 invariant holds" (``conform.py`` since #182,
    ``reconcile.py`` since #183) while this scan covered ``pv`` only — so for that
    subpackage the invariant was convention claiming to be enforcement, which is the
    precise gap this file's own docstring says it exists to close.

    **``ucsb`` is deliberately absent and that is not an oversight**: two modules there
    name ``dwh.votes`` inside f-string error messages today, so adding it would fail. That
    is a pre-existing question about UCSB, deferred rather than silently widened into this
    guard.
    """
    modules = _modules_under(subpackage)
    assert modules, (
        f"found no modules under usvote/{subpackage}/ — the guard would pass vacuously"
    )
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


# --- usvote/apportionment.py: the dependency-free EC-domain family (#182) ---

#: What :mod:`usvote.apportionment` is allowed to import from inside the package.
#:
#: Exactly one module, and that is the point: its placement at the top level (architect
#: review C1) rests on it being pure election-domain, so the first import of a source
#: subpackage — or of the DB/pandas stack — would falsify the reason it lives there.
_APPORTIONMENT_ALLOWED_USVOTE_IMPORTS = frozenset({"usvote.years"})

#: Third-party names whose presence would make the module non-importable from a pure,
#: offline context. Deliberately the heavy stack rather than an allow-list: a new stdlib
#: import is fine and should not need this tuple edited.
_HEAVY_IMPORTS = ("pandas", "psycopg2", "requests", "geopandas", "bs4", "matplotlib")


def _imported_names(source: str) -> set[str]:
    """Every module name ``source`` imports, in any spelling."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_apportionment_module_is_dependency_free() -> None:
    """Its docstring claims stdlib + ``usvote.years`` only; this is what checks it.

    An unenforced claim about a module's dependencies is the defect class this repo keeps
    finding: the sentence stays true-looking while an import quietly makes it false, and
    the reader who trusts it stops looking. #183 and #184 will both import this module, so
    the property has to hold for them rather than only today.
    """
    source = (PKG_ROOT / "apportionment.py").read_text(encoding="utf-8")
    imported = _imported_names(source)
    usvote_imports = {name for name in imported if name.split(".")[0] == "usvote"}
    # `from usvote.years import ec_ingest_years` contributes both the module and the name.
    offenders = {
        name
        for name in usvote_imports
        if not any(
            name == allowed or name.startswith(f"{allowed}.")
            for allowed in _APPORTIONMENT_ALLOWED_USVOTE_IMPORTS
        )
    }
    assert not offenders, (
        f"usvote.apportionment must import only "
        f"{sorted(_APPORTIONMENT_ALLOWED_USVOTE_IMPORTS)} from the package; found "
        f"{sorted(offenders)}"
    )
    heavy = sorted(
        name
        for name in imported
        if name.split(".")[0] in _HEAVY_IMPORTS
    )
    assert not heavy, (
        f"usvote.apportionment must stay importable without the heavy stack; found "
        f"{heavy}"
    )


#: Makes the heavy stack unimportable, then imports the module and uses it.
#:
#: ``find_spec`` is the **only** working spelling: ``find_module`` was removed in Python
#: 3.12, so a blocker written that way is silently inert and the guard proves nothing. The
#: companion non-vacuity test below is what catches that, and it caught exactly this while
#: #182 was being written.
_HEAVY_BLOCK_PREAMBLE = """
import sys

_BLOCKED = {"pandas", "psycopg2", "requests", "geopandas", "matplotlib", "bs4"}


class _BlockHeavy:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in _BLOCKED:
            raise ImportError(f"{fullname} is unimportable in this process")
        return None


sys.meta_path.insert(0, _BlockHeavy())
"""

_APPORTIONMENT_PROGRAM = _HEAVY_BLOCK_PREAMBLE + """
from usvote.apportionment import GOVERNING_CENSUS_BY_ELECTION, governing_census_year

assert governing_census_year(1924) == 1910, "the 1920 gap is not applied"
assert len(GOVERNING_CENSUS_BY_ELECTION) == 51, len(GOVERNING_CENSUS_BY_ELECTION)
assert not _BLOCKED & set(sys.modules), sorted(_BLOCKED & set(sys.modules))
print("OK")
"""

# The non-vacuity twin: a module that genuinely needs pandas must FAIL under the same
# preamble. Without this, a blocker that stopped blocking would leave every assertion above
# passing by inspecting nothing.
_HEAVY_CONSUMER_PROGRAM = _HEAVY_BLOCK_PREAMBLE + """
import usvote.census.conform  # needs pandas
print("IMPORTED")
"""


def test_the_apportionment_module_imports_with_the_heavy_stack_blocked() -> None:
    """The structural proof, not a re-reading of the import list.

    A scan over import statements cannot see a **transitive** dependency, and
    ``usvote.years`` could grow one. Importing in a fresh interpreter with pandas, psycopg2
    and the rest made unimportable proves the property — the technique the D030 firewall
    guards above use for ``usvote.ucsb``.
    """
    result = subprocess.run(
        [sys.executable, "-c", _APPORTIONMENT_PROGRAM],
        capture_output=True,
        text=True,
        cwd=PKG_ROOT.parents[1],
    )
    assert result.returncode == 0, (
        f"usvote.apportionment could not be imported without the heavy stack.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout


def test_the_heavy_stack_blocker_is_not_inert() -> None:
    """Non-vacuity: the blocker must actually block.

    ``usvote.census.conform`` imports pandas, so under the same preamble it must fail. This
    exists because the first version of the guard above used ``find_module``, which Python
    3.12 removed — the subprocess happily imported pandas and the guard passed while
    proving nothing.
    """
    result = subprocess.run(
        [sys.executable, "-c", _HEAVY_CONSUMER_PROGRAM],
        capture_output=True,
        text=True,
        cwd=PKG_ROOT.parents[1],
    )
    assert result.returncode != 0, (
        "the import blocker is inert — a pandas-importing module loaded under it, so the "
        f"guard above proves nothing. stdout: {result.stdout}"
    )
    assert "unimportable in this process" in result.stderr


def test_the_apportionment_module_is_top_level_not_under_a_source_subpackage() -> None:
    """Architect review C1: it is election-domain, so it sits beside ``years.py``.

    Under ``usvote/census/`` the first non-census consumer — a warehouse query, or #183 as
    an EC-side reconciliation — would have to import *up* from a source subpackage, which
    is the D015 inversion.
    """
    assert (PKG_ROOT / "apportionment.py").is_file()
    for sub in _LOWER_SUBPACKAGES:
        assert not (PKG_ROOT / sub / "apportionment.py").exists(), (
            f"usvote/{sub}/apportionment.py would invert D015 — the module is "
            f"election-domain and belongs at the top level"
        )
