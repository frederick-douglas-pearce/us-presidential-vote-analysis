"""Structural guards for the dashboard: one source of truth (D070(b), #277).

These are the only acceptance guard for three promises the public dashboard makes:

1. **No ``usvote`` at runtime.** ``usvote`` is installed in the dev environment, so the
   guard cannot rely on an import failing. It runs the dashboard in a fresh interpreter
   with ``usvote`` made unimportable, drives its real request paths, and then checks
   ``sys.modules`` — which also catches a ``try: import usvote / except ImportError``.
2. **One data input: HTTPS to one host.** The same interpreter records every host a
   socket is asked to reach, and the test compares them with an **independent literal**
   rather than with ``explore.config``, so repointing the config fails the test instead of
   moving it. An AST pass forbids every other way to read data (files, other HTTP
   clients) and confines the connection-opening call to ``explore.api.fetch``.
3. **No data files and no ``run.app``** in the deploy root, plus the ``app.yaml``
   settings D071 makes load-bearing.

Recorded API responses under ``tests/fixtures/dashboard/`` are test input only; a test
here asserts no runtime module can name them (the ``ec_state_roster_by_year.json``
precedent).
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DASHBOARD = REPO / "dashboard"
PACKAGE = DASHBOARD / "explore"
WORKFLOW = REPO / ".github" / "workflows" / "deploy-dashboard.yml"
PROBE = REPO / "scripts" / "probe_dashboard.sh"

#: The public API host, written out here rather than imported from ``explore.config``:
#: a test that read the host from the module under test would move with it.
PUBLIC_API_HOST = "api.us-presidential-election-center.org"

RUNTIME_MODULES = sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def _run(program: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().endswith("_PROXY")}
    env["PYTHONPATH"] = str(DASHBOARD)
    return subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=DASHBOARD,
        env=env,
        timeout=120,
    )


#: Installed before anything else runs: ``usvote`` unimportable, and every socket
#: connection and name lookup recorded and refused (so the program is also offline).
_PRELUDE = """
import socket
import sys


class _BlockUsvote:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "usvote" or fullname.startswith("usvote."):
            raise ImportError(f"usvote is unimportable in this process: {fullname}")
        return None


sys.meta_path.insert(0, _BlockUsvote())

HOSTS = []


def _record_connection(address, *args, **kwargs):
    HOSTS.append(address[0])
    raise OSError("network disabled by the guard")


def _record_lookup(host, *args, **kwargs):
    HOSTS.append(host)
    raise OSError("network disabled by the guard")


socket.create_connection = _record_connection
socket.getaddrinfo = _record_lookup
"""

_RUNTIME_PROGRAM = (
    _PRELUDE
    + """
import threading
from pathlib import Path

import explore.app as appmod
from explore import api

assert not any(t.name == "explore-refresher" for t in threading.enumerate()), (
    "the refresher started at import"
)
assert HOSTS == [], f"importing the app made a network call: {HOSTS}"

client = appmod.server.test_client()
routing = {
    "output": ".._pages_content.children..._pages_store.data..",
    "outputs": [{"id": "_pages_content", "property": "children"},
                {"id": "_pages_store", "property": "data"}],
    "inputs": [{"id": "_pages_location", "property": "pathname", "value": "/"},
               {"id": "_pages_location", "property": "search", "value": ""}],
    "changedPropIds": ["_pages_location.pathname"],
    "state": [],
}
assert client.get("/_ah/warmup").status_code == 200
assert client.get("/").status_code == 200
page = client.post("/_dash-update-component", json=routing)
assert page.status_code == 200, page.status_code
assert "isn't responding" in page.get_data(as_text=True)  # offline: the degraded state

# Every runtime module was actually loaded, so none escaped the checks above.
loaded = {Path(m.__file__).resolve() for m in list(sys.modules.values())
          if getattr(m, "__file__", None)}
package = Path(api.__file__).resolve().parent
missing = sorted(str(p) for p in package.rglob("*.py")
                 if "__pycache__" not in p.parts and p.resolve() not in loaded)
assert not missing, f"runtime modules never imported: {missing}"

leaked = sorted(m for m in sys.modules if m == "usvote" or m.startswith("usvote."))
assert not leaked, f"usvote reached the runtime: {leaked}"
print("HOSTS=" + ",".join(sorted(set(HOSTS))))
"""
)


def test_the_runtime_imports_no_usvote_and_reaches_only_the_public_api() -> None:
    result = _run(_RUNTIME_PROGRAM)
    assert result.returncode == 0, result.stderr[-3000:]
    hosts_line = [ln for ln in result.stdout.splitlines() if ln.startswith("HOSTS=")]
    assert hosts_line, result.stdout
    hosts = set(hosts_line[-1].removeprefix("HOSTS=").split(","))
    # Non-empty: the paths above did try the API, so the host check is not vacuous.
    assert hosts == {PUBLIC_API_HOST}


def test_the_guard_program_can_fail() -> None:
    """Non-vacuity: the blocker refuses ``usvote`` and the recorder sees any host."""
    program = (
        _PRELUDE
        + """
try:
    import usvote  # noqa: F401
except ImportError:
    print("BLOCKED")
try:
    socket.create_connection(("usvote-api-x.a.run.app", 443))
except OSError:
    pass
print("HOSTS=" + ",".join(HOSTS))
"""
    )
    result = _run(program)
    assert result.returncode == 0, result.stderr
    assert "BLOCKED" in result.stdout
    assert "HOSTS=usvote-api-x.a.run.app" in result.stdout


# --- static checks over the runtime modules -----------------------------------------------

#: No runtime module may import these: every one is a way to read data other than the
#: public API through ``explore.api.fetch``.
BANNED_MODULES = frozenset(
    {
        "usvote",
        "sqlite3",
        "pickle",
        "shelve",
        "csv",
        "socket",
        "http",
        "ssl",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "subprocess",
        "io",
        "pandas",
    }
)

#: ``urllib`` is allowed only in the one module that owns the chokepoint.
CHOKEPOINT = PACKAGE / "api.py"

#: Call names that read files, banned everywhere.
BANNED_CALLS = frozenset({"open", "read_text", "read_bytes", "load"})


def _imports(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def _calls(tree: ast.AST) -> list[tuple[str, str | None]]:
    """(callee name, enclosing function) for every call in the module."""
    found: list[tuple[str, str | None]] = []

    def visit(node: ast.AST, func: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                else func
            )
            if isinstance(child, ast.Call):
                callee = child.func
                if isinstance(callee, ast.Name):
                    found.append((callee.id, func))
                elif isinstance(callee, ast.Attribute):
                    found.append((callee.attr, func))
            visit(child, inner)

    visit(tree, None)
    return found


@pytest.mark.parametrize("path", RUNTIME_MODULES, ids=lambda p: str(p.relative_to(REPO)))
def test_no_runtime_module_imports_another_data_path(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for name in _imports(tree):
        top = name.split(".")[0]
        assert top not in BANNED_MODULES, f"{path.name} imports {name}"
        if top == "urllib":
            assert path == CHOKEPOINT, f"{path.name} imports {name}; only api.py may"


@pytest.mark.parametrize("path", RUNTIME_MODULES, ids=lambda p: str(p.relative_to(REPO)))
def test_no_runtime_module_reads_a_file_or_opens_a_connection(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for name, func in _calls(tree):
        if name == "open" and path == CHOKEPOINT and func == "fetch":
            continue  # the one chokepoint: _OPENER.open(...) inside api.fetch
        assert name not in BANNED_CALLS, f"{path.name}: {name}() in {func or 'module'}"


def test_the_ast_checks_can_fail() -> None:
    """Non-vacuity: the two checks above flag what they are meant to flag."""
    source = (
        "import sqlite3\n"
        "from urllib.request import urlopen\n"
        "def f():\n    return open('x').read()\n"
        "def fetch():\n    return OPENER.open('y')\n"
    )
    tree = ast.parse(source)
    assert {"sqlite3", "urllib.request"} <= set(_imports(tree))
    assert ("open", "f") in _calls(tree)
    assert ("open", "fetch") in _calls(tree)


def test_nothing_in_the_dashboard_or_its_deploy_names_run_app() -> None:
    offenders = [
        str(p.relative_to(REPO))
        for p in [*DASHBOARD.rglob("*"), WORKFLOW, PROBE]
        if p.is_file()
        and "__pycache__" not in p.parts
        and "run.app" in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert WORKFLOW.is_file() and PROBE.is_file()
    assert offenders == []


#: What the deploy root may contain. An allow-list, so a data file cannot arrive under a
#: new extension; a later story that needs another kind of file extends it here.
ALLOWED_SUFFIXES = frozenset({".py", ".css", ".yaml"})
ALLOWED_NAMES = frozenset({".gcloudignore", "requirements.txt"})


def test_the_deploy_root_holds_no_data_files() -> None:
    offenders = [
        str(p.relative_to(REPO))
        for p in DASHBOARD.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix not in ALLOWED_SUFFIXES
        and p.name not in ALLOWED_NAMES
    ]
    assert offenders == []


@pytest.mark.parametrize("path", RUNTIME_MODULES, ids=lambda p: str(p.relative_to(REPO)))
def test_no_runtime_module_names_the_test_fixtures(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "fixtures" not in text
    assert "tests/" not in text


# --- deploy configuration ------------------------------------------------------------------


def _app_yaml() -> dict[str, Any]:
    loaded = yaml.safe_load((DASHBOARD / "app.yaml").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_app_yaml_pins_one_warm_f1_instance() -> None:
    config = _app_yaml()
    assert config["runtime"] == "python314"
    assert config["instance_class"] == "F1"
    assert config["automatic_scaling"] == {"min_instances": 1, "max_instances": 1}
    assert config["inbound_services"] == ["warmup"]


def test_app_yaml_runs_one_process_as_the_least_privilege_account() -> None:
    config = _app_yaml()
    assert config["service_account"] == "explore-run@uspv-explore.iam.gserviceaccount.com"
    entry = config["entrypoint"].split()
    assert entry[0] == "gunicorn"
    assert entry[-1] == "explore.app:server"
    assert entry[entry.index("-w") + 1] == "1"  # one worker: one process, one cache


def test_app_yaml_carries_no_environment() -> None:
    """No env var can repoint the API base, set a proxy, or add a second input."""
    assert "env_variables" not in _app_yaml()


def test_gcloudignore_uploads_only_the_runtime() -> None:
    lines = [
        ln.strip()
        for ln in (DASHBOARD / ".gcloudignore").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    assert lines == [
        "/*",
        "!/app.yaml",
        "!/requirements.txt",
        "!/explore/",
        "/explore/**/__pycache__/",
    ]


def _groups() -> dict[str, list[str]]:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    groups = data["dependency-groups"]
    assert isinstance(groups, dict)
    return groups


def test_the_api_image_does_not_gain_dash() -> None:
    """D033: the serve group is the API container's whole closure."""
    serve = " ".join(_groups()["serve"]).lower()
    assert "dash" not in serve
    assert "gunicorn" not in serve


def test_the_dashboard_export_cannot_install_usvote() -> None:
    """What the deploy ships: the lock's dashboard group, without the project itself."""
    result = subprocess.run(
        [
            "uv",
            "export",
            "--frozen",
            "--only-group",
            "dashboard",
            "--no-emit-project",
            "--no-hashes",
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    requirements = [
        ln.strip()
        for ln in result.stdout.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    names = {ln.split("==")[0].split(" ")[0].lower() for ln in requirements}
    assert {"dash", "flask-compress", "gunicorn"} <= names
    assert "usvote" not in names
    assert not [ln for ln in requirements if ln.startswith(("-e", "."))]
