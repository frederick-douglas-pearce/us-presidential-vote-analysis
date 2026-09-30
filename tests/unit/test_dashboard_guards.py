"""Structural guards for the dashboard: one source of truth (D070(b), #277).

These are the only acceptance guard for three promises the public dashboard makes:

1. **No ``usvote`` at runtime.** ``usvote`` is installed in the dev environment, so the
   guard cannot rely on an import failing. It runs the dashboard in a fresh interpreter
   whose ``usvote`` finder **records every attempt** and refuses it, drives the app's
   real request paths, and asserts there were no attempts at all. Recording the attempt
   is what catches ``try: import usvote / except ImportError`` and dynamic imports: a
   refused import never reaches ``sys.modules``, so checking that alone would not.
2. **One data input: HTTPS to one host.** The same interpreter installs an **audit hook**
   on the socket events (``connect``, ``getaddrinfo``, ``gethostbyname``, ``sendto``),
   which fire for C-level calls too, records each host and refuses it. The recorded
   hosts are compared with an **independent literal**, not with ``explore.config``, so
   repointing the config fails the test instead of moving it. Proxy variables are set in
   that interpreter before the app is imported, so an opener that honoured them would
   show the proxy's host.
3. **No data files and no ``run.app``** in the deploy root, plus the exact ``app.yaml``.

**What each layer is for, stated so it is not read as more.** The subprocess is the
behavioural check; it covers the paths it drives (warmup, the page shell, the page
render) with the API refused, which is every network path the skeleton has. A path that
runs only after a *successful* response (prefetching a second path, a fill on a miss) is
not reached, and #278's second registered path is where that coverage has to grow. One
limit of the audit hook itself: a raw ``connect`` to a *hostname* resolves the name
before the ``socket.connect`` event fires, so with the network cut it fails unrecorded;
the lint's ban on importing ``socket`` is what covers raw sockets. The
AST pass is a lint against *accidental* regressions: a second HTTP client, a file read,
a dynamic import. It is not a sandbox against code written to evade it (a name built at
runtime, say), and it does not claim to be.

Recorded API responses under ``tests/fixtures/dashboard/`` are test input only; a test
here asserts no runtime module can name them (the ``ec_state_roster_by_year.json``
precedent).
"""

from __future__ import annotations

import ast
import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

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

#: Set in the guard interpreter before the app is imported. An opener that honoured
#: proxy variables would resolve this host, and the host check would see it.
GUARD_PROXY = "http://proxy.guard.invalid:3128"

RUNTIME_MODULES = sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def _run(program: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().endswith("_PROXY")}
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        env[name] = GUARD_PROXY
    env["PYTHONPATH"] = str(DASHBOARD)
    return subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=DASHBOARD,
        env=env,
        timeout=120,
    )


#: Installed before anything else runs: every ``usvote`` import attempt recorded and
#: refused, and every socket host recorded and refused (so the program is offline).
_PRELUDE = """
import sys

ATTEMPTS = []
HOSTS = []


class _BlockUsvote:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "usvote" or fullname.startswith("usvote."):
            ATTEMPTS.append(fullname)
            raise ImportError(f"usvote is unimportable in this process: {fullname}")
        return None


sys.meta_path.insert(0, _BlockUsvote())


def _audit(event, args):
    if event in ("socket.getaddrinfo", "socket.gethostbyname"):
        host = args[0]
    elif event in ("socket.connect", "socket.sendto"):
        address = args[1]
        host = address[0] if isinstance(address, tuple) else address
    else:
        return
    HOSTS.append(host.decode() if isinstance(host, bytes) else str(host))
    raise OSError("network disabled by the guard")


sys.addaudithook(_audit)
"""

_RUNTIME_PROGRAM = (
    _PRELUDE
    + """
import threading
from pathlib import Path

BASELINE_THREADS = set(threading.enumerate())

import explore.app as appmod
from explore import api

assert set(threading.enumerate()) == BASELINE_THREADS, "a thread started at import"
assert api.CLIENT._thread is None, "the refresher started at import"
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

assert ATTEMPTS == [], f"the runtime tried to import usvote: {ATTEMPTS}"
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
    """Non-vacuity: each recorder sees what it exists to see."""
    program = (
        _PRELUDE
        + """
import importlib
import socket
import urllib.request

try:
    importlib.import_module("usvote")  # a dynamic import, swallowed
except ImportError:
    pass
try:  # C level, no helper. An IP literal: a hostname would be resolved before the
    # socket.connect audit event fires, so with the network cut it would fail unrecorded.
    socket.socket().connect(("203.0.113.7", 443))
except OSError:
    pass
try:  # urllib's default opener honours the proxy variables the guard sets
    urllib.request.build_opener().open("http://example.invalid/", timeout=5)
except OSError:
    pass
print("ATTEMPTS=" + ",".join(ATTEMPTS))
print("HOSTS=" + ",".join(HOSTS))
"""
    )
    result = _run(program)
    assert result.returncode == 0, result.stderr
    assert "ATTEMPTS=usvote" in result.stdout
    hosts_line = [ln for ln in result.stdout.splitlines() if ln.startswith("HOSTS=")][0]
    hosts = set(hosts_line.removeprefix("HOSTS=").split(","))
    assert "203.0.113.7" in hosts
    assert "proxy.guard.invalid" in hosts


# --- a lint over the runtime modules --------------------------------------------------

#: Modules no runtime module may import: each is a way to read data other than the
#: public API through ``explore.api.fetch``, or to reach one dynamically.
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
        "os",
        "pathlib",
        "importlib",
        "pkgutil",
        "glob",
        "shutil",
        "tempfile",
        "builtins",
    }
)

#: ``urllib.parse`` is pure string handling; the rest of ``urllib`` opens connections
#: and is allowed only in the chokepoint module.
CHOKEPOINT = PACKAGE / "api.py"
URLLIB_ANYWHERE = frozenset({"urllib.parse"})

#: Names that read files or open connections, flagged wherever they appear (as a name
#: or an attribute, called or not), so ``o = open; o(x)`` is caught too.
BANNED_NAMES = frozenset(
    {
        "open",
        "__import__",
        "urlopen",
        "urlretrieve",
        "read_text",
        "read_bytes",
        "get_data",
        "popen",
        "load",
    }
)


def _is_the_chokepoint_call(node: ast.AST, func: str | None, path: Path) -> bool:
    """``_OPENER.open`` inside ``fetch`` in ``api.py`` — the one allowed ``open``."""
    return (
        path == CHOKEPOINT
        and func == "fetch"
        and isinstance(node, ast.Attribute)
        and node.attr == "open"
        and isinstance(node.value, ast.Name)
        and node.value.id == "_OPENER"
    )


def _violations(tree: ast.AST, path: Path) -> list[str]:
    found: list[str] = []

    def check_import(name: str, line: int) -> None:
        top = name.split(".")[0]
        if top in BANNED_MODULES:
            found.append(f"line {line}: imports {name}")
        elif top == "urllib" and name not in URLLIB_ANYWHERE and path != CHOKEPOINT:
            found.append(f"line {line}: imports {name}; only api.py may")

    def visit(node: ast.AST, func: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            inner = (
                child.name
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                else func
            )
            line = getattr(child, "lineno", 0)
            if isinstance(child, ast.Import):
                for alias in child.names:
                    check_import(alias.name, line)
            elif isinstance(child, ast.ImportFrom) and child.module and child.level == 0:
                check_import(child.module, line)
                for alias in child.names:
                    if alias.name in BANNED_NAMES:
                        found.append(f"line {line}: imports {alias.name}")
            elif isinstance(child, ast.Name) and child.id in BANNED_NAMES:
                found.append(f"line {line}: {child.id}")
            elif (
                isinstance(child, ast.Attribute)
                and child.attr in BANNED_NAMES
                and not _is_the_chokepoint_call(child, func, path)
            ):
                found.append(f"line {line}: .{child.attr}")
            elif (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "getattr"
                and len(child.args) >= 2
                and isinstance(child.args[1], ast.Constant)
                and isinstance(child.args[1].value, str)
            ):
                found.append(f"line {line}: getattr(..., {child.args[1].value!r})")
            visit(child, inner)

    visit(tree, None)
    return found


@pytest.mark.parametrize("path", RUNTIME_MODULES, ids=lambda p: str(p.relative_to(REPO)))
def test_no_runtime_module_has_another_data_path(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert _violations(tree, path) == []


def test_the_runtime_modules_are_the_expected_ones() -> None:
    """The parametrized lint above cannot pass by finding nothing to check."""
    names = {str(p.relative_to(PACKAGE)) for p in RUNTIME_MODULES}
    assert {"api.py", "app.py", "config.py", "pages/home.py"} <= names


@pytest.mark.parametrize(
    ("source", "path", "flagged"),
    [
        ("import os\n", PACKAGE / "app.py", True),
        ("from importlib import import_module\n", PACKAGE / "app.py", True),
        ("o = open\n", PACKAGE / "pages" / "home.py", True),
        ("x = getattr(p, 'read_text')()\n", PACKAGE / "app.py", True),
        ("import urllib.request\n", PACKAGE / "app.py", True),
        ("from urllib.parse import quote\n", PACKAGE / "app.py", False),
        ("import urllib.request\n", CHOKEPOINT, False),
        ("def fetch():\n    return _OPENER.open(r)\n", CHOKEPOINT, False),
        ("def other():\n    return _OPENER.open(r)\n", CHOKEPOINT, True),
        ("def fetch():\n    return open('meta.json').read()\n", CHOKEPOINT, True),
        ("def fetch():\n    return urllib.request.urlopen(u)\n", CHOKEPOINT, True),
        ("import json\njson.load(f)\n", PACKAGE / "app.py", True),
        ("import json\njson.loads(s)\n", PACKAGE / "app.py", False),
    ],
)
def test_the_lint_rules_flag_what_they_should(
    source: str, path: Path, flagged: bool
) -> None:
    """Non-vacuity at the level of the rules, not of the tree walk."""
    assert bool(_violations(ast.parse(source), path)) is flagged


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


def _deploy_root_file_allowed(relative: Path) -> bool:
    """Where each kind of file may sit in the deploy root. A later story that needs
    another kind of file (a favicon, say) extends this, with a reason."""
    parts = relative.parts
    if len(parts) == 1:
        return relative.name in {"app.yaml", ".gcloudignore", "requirements.txt"}
    if parts[0] != "explore":
        return False
    if relative.suffix == ".py":
        return True
    return relative.suffix == ".css" and parts[1] == "assets"


def test_the_deploy_root_holds_no_data_files() -> None:
    offenders = [
        str(p.relative_to(REPO))
        for p in DASHBOARD.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and not _deploy_root_file_allowed(p.relative_to(DASHBOARD))
    ]
    assert offenders == []


@pytest.mark.parametrize(
    ("relative", "allowed"),
    [
        ("app.yaml", True),
        ("explore/results.yaml", False),
        ("explore/data.json", False),
        ("explore/assets/style.css", True),
        ("explore/pages/extra.css", False),
        ("explore/pages/home.py", True),
        ("snapshot.sqlite", False),
    ],
)
def test_the_deploy_root_allow_list(relative: str, allowed: bool) -> None:
    assert _deploy_root_file_allowed(Path(relative)) is allowed


@pytest.mark.parametrize("path", RUNTIME_MODULES, ids=lambda p: str(p.relative_to(REPO)))
def test_no_runtime_module_names_the_test_fixtures(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "fixtures" not in text
    assert "tests/" not in text


# --- deploy configuration ------------------------------------------------------------------


def test_app_yaml_is_exactly_the_pinned_configuration() -> None:
    """Every setting, including the whole entrypoint and the absence of env_variables.

    One F1, pinned (D071(b)); warmup; one gunicorn worker, so one process and one cache
    (D071(d)), with the thread count #277's load test measured; the least-privilege
    runtime account (#283). A change here is a change to what was measured and reviewed.
    """
    config = yaml.safe_load((DASHBOARD / "app.yaml").read_text(encoding="utf-8"))
    assert config == {
        "runtime": "python314",
        "instance_class": "F1",
        "service_account": "explore-run@uspv-explore.iam.gserviceaccount.com",
        "entrypoint": (
            "gunicorn -b :$PORT -w 1 --threads 8 --timeout 60 explore.app:server"
        ),
        "inbound_services": ["warmup"],
        "automatic_scaling": {"min_instances": 1, "max_instances": 1},
    }


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


#: The export the deploy workflow must run: the dashboard group only, without the
#: project itself (so the deployed runtime has no usvote to import).
EXPORT_ARGV = [
    "uv",
    "export",
    "--frozen",
    "--only-group",
    "dashboard",
    "--no-emit-project",
    "-o",
    "dashboard/requirements.txt",
]


def _workflow_export_argv() -> list[str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    commands = [
        step["run"]
        for step in workflow["jobs"]["deploy"]["steps"]
        if "uv export" in step.get("run", "")
    ]
    assert len(commands) == 1, "expected exactly one uv export in the deploy workflow"
    joined = commands[0].replace("\\\n", " ")
    line = next(ln for ln in joined.splitlines() if "uv export" in ln)
    return shlex.split(line)


def test_the_workflow_exports_exactly_the_dashboard_group() -> None:
    assert _workflow_export_argv() == EXPORT_ARGV


def test_the_dashboard_export_cannot_install_usvote(tmp_path: Path) -> None:
    """Runs the workflow's own export command (into a temp file) and reads the result."""
    argv = [*_workflow_export_argv()[:-1], str(tmp_path / "requirements.txt")]
    result = subprocess.run(argv, capture_output=True, text=True, cwd=REPO, timeout=120)
    assert result.returncode == 0, result.stderr
    requirements = [
        ln.strip()
        for ln in (tmp_path / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith(("#", "--hash"))
    ]
    names = {ln.split("==")[0].split(" ")[0].lower() for ln in requirements}
    assert {"dash", "flask-compress", "gunicorn"} <= names
    assert "usvote" not in names
    assert not {"pandas", "geopandas", "psycopg2-binary", "fastapi"} & names
    assert not [ln for ln in requirements if ln.startswith(("-e", "."))]
