"""Structural guards for the dashboard: one source of truth (D070(b), #277, #293).

These are the only acceptance guard for three promises the public dashboard makes:

1. **No ``usvote`` at runtime.** ``usvote`` is installed in the dev environment, so the
   guard cannot rely on an import failing. It runs the dashboard in a fresh interpreter
   whose ``usvote`` finder **records every attempt** and refuses it, drives the app's
   real request paths, and asserts there were no attempts at all. Recording the attempt
   is what catches ``try: import usvote / except ImportError`` and dynamic imports: a
   refused import never reaches ``sys.modules``, so checking that alone would not. The
   audit hook also records the ``import`` event for ``usvote``, a second recorder beside
   the finder. It complements the finder and cannot replace it:
   ``importlib.import_module`` raises no ``import`` event for its target (CPython 3.14),
   so only the finder sees that spelling.
2. **One data input: HTTPS to one host.** The same interpreter installs an **audit hook**
   on the socket events (``connect``, ``getaddrinfo``, ``gethostbyname``, ``sendto``),
   which fire for C-level calls too, records each host and refuses it. It also refuses
   ``socket.__new__`` and records the code that asked for the socket: a raw socket is
   created before its hostname is resolved, so this covers the raw connect to a
   *hostname* that the ``connect`` event alone would miss (urllib resolves first, so
   its requests still record their host). A socket created by anything but a named
   creator in :data:`ALLOWED_SOCKET_CREATORS` fails the test.
   The recorded hosts are compared with an **independent literal**, not with
   ``explore.config``, so repointing the config fails the test instead of moving it.
   Proxy variables are set in that interpreter before the app is imported, so an opener
   that honoured them would show the proxy's host.
3. **No data files.** The hook records every ``open`` event, and both runs fail on any
   file opened outside :data:`LIBRARY_ROOTS`, ``dashboard/explore/`` and the named
   files in :data:`ALLOWED_FILES`, and on any file under ``tests/`` whatever those
   lists allow. It also refuses ``sqlite3.connect``, which opens its file in C with no
   ``open`` event. Beside the behavioural check: no data files and no ``run.app`` in the
   deploy root, and the exact ``app.yaml``.

**Two runs, and what each covers.** The *refused* run drives warmup, the page shell and
every registered page with every connection refused. The *success* run replaces
``http.client.HTTPSConnection.connect`` with a fake transport that answers the API host
only, from recorded fixtures; ``fetch``, its proxy and redirect handling, the cache and
the renders all run as shipped on top of it. It registers at least two prefetch paths,
renders every registered page from a filled cache, and makes one fill on a miss. So the
code that runs only after a successful response is under the guard too.

**What the guard does not claim.** A file read that bypasses Python's ``open`` (C code
other than SQLite's) raises no event and is not seen. Pages other than ``/`` are pinned
in the success run only by the absence of the degraded message, so a page that skipped
its post-success code would still pass. A per-page success contract is deferred to #278,
as recorded in PR #304's review. The AST pass is a lint against *accidental*
regressions: a second HTTP client, a file read, a dynamic import. It is not a sandbox
against code written to evade it (a name built at runtime, say), and it does not claim
to be.

Recorded API responses under ``tests/fixtures/dashboard/`` are test input only. The
success run reads them in this process and embeds them in the guard program, so the
runtime under test never opens them, and the ``open`` check would fail if it did.
"""

from __future__ import annotations

import ast
import json
import mimetypes
import os
import shlex
import subprocess
import sys
import sysconfig
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DASHBOARD = REPO / "dashboard"
PACKAGE = DASHBOARD / "explore"
TESTS = REPO / "tests"
FIXTURES = TESTS / "fixtures" / "dashboard"
WORKFLOW = REPO / ".github" / "workflows" / "deploy-dashboard.yml"
PROBE = REPO / "scripts" / "probe_dashboard.sh"
#: Contributor guidance (#298), never uploaded: `.gcloudignore` is an allow-list that
#: does not name it, which `test_gcloudignore_uploads_only_the_runtime` pins. Its prose
#: says the runtime names no `run.app` URL, so the text scan below skips this one path.
GUIDANCE = DASHBOARD / "CLAUDE.md"

#: The public API host, written out here rather than imported from ``explore.config``:
#: a test that read the host from the module under test would move with it.
PUBLIC_API_HOST = "api.us-presidential-election-center.org"

#: Set in the guard interpreter before the app is imported. An opener that honoured
#: proxy variables would resolve this host, and the host check would see it.
GUARD_PROXY = "http://proxy.guard.invalid:3128"

RUNTIME_MODULES = sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)

#: The responses the success run's fake transport serves, by API path. A page that
#: registers a new prefetch path needs its fixture here, or the success run fails: the
#: transport answers 404, warmup's refresh fails, and the program stops at its
#: "warmup did not fill the cache" assertion.
FIXTURE_FILES = {
    "/v1/meta": "v1_meta.json",
    "/v1/elections": "v1_elections.json",
    "/v1/elections/1824": "v1_elections_1824.json",
}

#: Registered only while the pages register fewer than two prefetch paths, so the
#: prefetch loop runs past ``/v1/meta`` before #278's pages register real ones.
SYNTHETIC_PREFETCH = "/v1/elections"

#: Read by no page and prefetched by none: the success run's fill on a miss.
MISS_PATH = "/v1/elections/1824"


def _run(program: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().endswith("_PROXY")}
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        env[name] = GUARD_PROXY
    # On stdin, not ``-c``: the program embeds the fixtures, and one argument is
    # capped (128 KiB on Linux) well below what #278's fixtures will add up to. ``-I``
    # ignores every PYTHON* variable (a PYTHONPYCACHEPREFIX would move .pyc reads off
    # the allowed roots), so the app's directory goes on sys.path in the program.
    program = f"import sys\nsys.path.insert(0, {str(DASHBOARD)!r})\n" + program
    return subprocess.run(
        [sys.executable, "-I", "-"],
        input=program,
        capture_output=True,
        text=True,
        cwd=DASHBOARD,
        env=env,
        timeout=120,
    )


#: Installed before anything else runs. Every ``usvote`` import attempt is recorded and
#: refused; every socket host is recorded and refused, and so is creating a socket (so
#: no connection the hook sees can succeed); ``sqlite3.connect`` is recorded and
#: refused; ``open`` and ``import`` events are only recorded, since refusing them would
#: break imports. They are classified after the run, in this process.
_PRELUDE = """
import sys

ATTEMPTS = []
IMPORT_EVENTS = []
HOSTS = []
OPENS = []
SQLITE = []
SOCKETS = []
SERVED = []


class _BlockUsvote:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "usvote" or fullname.startswith("usvote."):
            ATTEMPTS.append(fullname)
            raise ImportError(f"usvote is unimportable in this process: {fullname}")
        return None


sys.meta_path.insert(0, _BlockUsvote())


def _audit(event, args):
    if event == "open":
        OPENS.append(args[0])
        return
    if event == "import":
        name = str(args[0])
        if name == "usvote" or name.startswith("usvote."):
            IMPORT_EVENTS.append(name)
        return
    if event == "sqlite3.connect":
        SQLITE.append(str(args[0]))
        raise OSError("sqlite disabled by the guard")
    if event == "socket.__new__":
        # Recorded by the code that asked for it, the first frame outside socket.py.
        frame = sys._getframe(1)
        while frame is not None and frame.f_code.co_filename.endswith("/socket.py"):
            frame = frame.f_back
        where = "?" if frame is None else frame.f_code.co_filename
        name = "?" if frame is None else frame.f_code.co_name
        SOCKETS.append(f"{where}:{name}")
        raise OSError("socket creation disabled by the guard")
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


def _transport(fixtures: dict[str, str], version: str) -> str:
    """The fake transport: ``HTTPSConnection.connect`` answering the API host only.

    Installed after the prelude and before ``explore`` is imported. Only the connection
    step is replaced, so the dashboard's real opener (no proxy, no redirects), real
    ``fetch`` and the stdlib's request and response handling all run on top of it. The
    socket is an in-memory buffer, never a real one: creating a socket is refused. Every
    200 response carries the meta fixture's snapshot version as its ``ETag``, since the
    cache compares only that; a 404 carries none.
    """
    return f"""
import http.client
import io

_FIXTURES = {ascii(fixtures)}
_VERSION = {version!r}
_API_HOST = {PUBLIC_API_HOST!r}


class _FixtureSocket:
    def __init__(self):
        self._sent = b""

    def sendall(self, data):
        self._sent += bytes(data)

    def makefile(self, mode, *args, **kwargs):
        target = self._sent.split(b" ", 2)[1].decode("ascii")
        body = _FIXTURES.get(target)
        if body is None:
            head = "HTTP/1.1 404 Not Found\\r\\n"
            payload = b'{{"error": "no fixture"}}'
        else:
            SERVED.append(target)
            head = f'HTTP/1.1 200 OK\\r\\nETag: "{{_VERSION}}"\\r\\n'
            payload = body.encode("utf-8")
        head += (
            "Content-Type: application/json\\r\\n"
            f"Content-Length: {{len(payload)}}\\r\\nConnection: close\\r\\n\\r\\n"
        )
        return io.BytesIO(head.encode("ascii") + payload)

    def close(self):
        pass


def _connect(self):
    HOSTS.append(self.host)
    if self.host != _API_HOST:
        raise OSError(f"the guard's transport answers {{_API_HOST}} only")
    self.sock = _FixtureSocket()


# The method, not the class: the stdlib's __init__ names the class through the module
# global, so rebinding that global would break every connection.
http.client.HTTPSConnection.connect = _connect
"""


def _fixture_transport() -> str:
    fixtures = {
        path: (FIXTURES / name).read_text(encoding="utf-8")
        for path, name in FIXTURE_FILES.items()
    }
    meta = json.loads(fixtures["/v1/meta"])
    return _transport(fixtures, meta["provenance"]["snapshot_version"])


#: Shared by both runtime runs: drives the routing callback for one page path.
_ROUTE = """
def route(client, path):
    body = {
        "output": ".._pages_content.children..._pages_store.data..",
        "outputs": [{"id": "_pages_content", "property": "children"},
                    {"id": "_pages_store", "property": "data"}],
        "inputs": [{"id": "_pages_location", "property": "pathname", "value": path},
                   {"id": "_pages_location", "property": "search", "value": ""}],
        "changedPropIds": ["_pages_location.pathname"],
        "state": [],
    }
    response = client.post("/_dash-update-component", json=body)
    assert response.status_code == 200, (path, response.status_code)
    return response.get_data(as_text=True)
"""

#: Every runtime module was actually loaded, so none escaped the checks.
_ALL_MODULES_LOADED = """
from pathlib import Path

loaded = {Path(m.__file__).resolve() for m in list(sys.modules.values())
          if getattr(m, "__file__", None)}
package = Path(api.__file__).resolve().parent
missing = sorted(str(p) for p in package.rglob("*.py")
                 if "__pycache__" not in p.parts and p.resolve() not in loaded)
assert not missing, f"runtime modules never imported: {missing}"
"""

#: The recorders' contents, as one line of JSON for this process to read.
_RESULT = """
import json as _json
import os as _os

_opened = sorted({_os.fsdecode(_os.fspath(p)) for p in list(OPENS)
                  if not isinstance(p, int)})
print("RESULT=" + _json.dumps({
    "attempts": ATTEMPTS,
    "import_events": IMPORT_EVENTS,
    "hosts": sorted(set(HOSTS)),
    "opens": _opened,
    "sqlite": SQLITE,
    "sockets": SOCKETS,
    "served": SERVED,
}))
"""

_REFUSED_PROGRAM = (
    _PRELUDE
    + _ROUTE
    + """
import threading

BASELINE_THREADS = set(threading.enumerate())

import dash
import explore.app as appmod
from explore import api

assert set(threading.enumerate()) == BASELINE_THREADS, "a thread started at import"
assert api.CLIENT._thread is None, "the refresher started at import"
assert HOSTS == [], f"importing the app made a network call: {HOSTS}"

client = appmod.server.test_client()
assert client.get("/_ah/warmup").status_code == 200
assert client.get("/").status_code == 200
paths = sorted(page["path"] for page in dash.page_registry.values())
assert "/" in paths, paths
for path in paths:
    assert "isn't responding" in route(client, path), path  # offline: degraded
"""
    + _ALL_MODULES_LOADED
    + _RESULT
)


def _success_program() -> str:
    return (
        _PRELUDE
        + _fixture_transport()
        + _ROUTE
        + f"""
import dash
import explore.app as appmod
from explore import api

registered = list(dict.fromkeys(api.registered_prefetch_paths()))
if len(registered) < 2:
    home = next(page for page in dash.page_registry.values() if page["path"] == "/")
    home["prefetch"] = (*home.get("prefetch", ()), {SYNTHETIC_PREFETCH!r})
    registered = list(dict.fromkeys(api.registered_prefetch_paths()))
assert len(registered) >= 2, registered
assert {MISS_PATH!r} not in registered, "the miss path must not be prefetched"
# Warmup's fills wait for tokens without limit: past the bucket's burst each one sleeps
# for real, and enough of them run into this subprocess's timeout. Fail fast instead.
planned = 1 + len([path for path in registered if path != api.META_PATH]) + 1
assert planned <= api.FILL_BURST, (
    f"{{planned}} planned fills exceed the bucket's burst of {{api.FILL_BURST}}: replace "
    "api.CLIENT's bucket here with a permissive one, e.g. TokenBucket(burst=inf)"
)

client = appmod.server.test_client()
assert client.get("/_ah/warmup").status_code == 200  # refresh: meta, then prefetch
assert api.CLIENT.snapshot is not None, "warmup did not fill the cache"
assert api.CLIENT.snapshot.version == _VERSION
assert client.get("/").status_code == 200
paths = sorted(page["path"] for page in dash.page_registry.values())
assert "/" in paths, paths
for path in paths:
    text = route(client, path)
    assert "isn't responding" not in text, path  # rendered from the filled cache
    if path == "/":
        assert _VERSION in text

api.CLIENT.get({MISS_PATH!r})  # a fill on a miss, through the real fetch
assert {MISS_PATH!r} in api.CLIENT.snapshot.responses, "the miss was not stored"

expected = [api.META_PATH]
expected += [path for path in registered if path != api.META_PATH]
expected += [{MISS_PATH!r}]
assert SERVED == expected, (SERVED, expected)
"""
        + _ALL_MODULES_LOADED
        + _RESULT
    )


def _result(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert completed.returncode == 0, completed.stderr[-3000:]
    lines = [ln for ln in completed.stdout.splitlines() if ln.startswith("RESULT=")]
    assert lines, completed.stdout[-3000:]
    result: dict[str, Any] = json.loads(lines[-1].removeprefix("RESULT="))
    return result


# --- which file opens are allowed ----------------------------------------------------

#: The interpreter's own library roots: the stdlib and the environment's site-packages,
#: each as configured and as resolved.
LIBRARY_ROOTS = tuple(
    dict.fromkeys(
        path
        for key in ("stdlib", "platstdlib", "purelib", "platlib")
        for path in (
            Path(os.path.abspath(sysconfig.get_paths()[key])),
            Path(os.path.realpath(sysconfig.get_paths()[key])),
        )
    )
)

#: Named files outside those roots that the runtime opens, each with its reason. A CI
#: environment that opens another one adds it here with a reason, never a directory.
ALLOWED_FILES = frozenset(
    Path(os.path.realpath(p))
    for p in (
        # Dash calls ``mimetypes.add_type`` at import, which reads the system's MIME
        # tables from the stdlib's own list of locations.
        *mimetypes.knownfiles,
        # The OS randomness source.
        "/dev/urandom",
        # The zipped stdlib's place on ``sys.path`` (its name varies with the
        # platform's libdir and a free-threaded build), which importlib.metadata
        # opens when it scans the path for distributions.
        *(entry for entry in sys.path if entry.endswith(".zip")),
    )
)


def _is_under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _open_violation(raw: str) -> bool:
    """Whether the runtime opening ``raw`` (as the audit event named it) is a violation.

    Relative names are read from the guard program's working directory. Every rule uses
    the resolved name, so ``../tests/x`` or a symlink cannot reach a file unnoticed,
    with one exception: a name written under :data:`LIBRARY_ROOTS` is accepted as
    written too, since an installer may make site-packages entries symlinks into a
    store (uv's symlink mode, Nix). ``tests/`` wins over every allow.
    """
    if raw.startswith("<") and raw.endswith(">"):
        return False  # a pseudo-filename (``<unknown>``), as linecache tries
    written = Path(os.path.abspath(os.path.join(DASHBOARD, raw)))
    resolved = Path(os.path.realpath(written))
    if _is_under(resolved, TESTS.resolve()):
        return True
    if resolved in ALLOWED_FILES or _is_under(resolved, PACKAGE.resolve()):
        return False
    return not any(
        _is_under(path, root) for root in LIBRARY_ROOTS for path in (written, resolved)
    )


#: Code allowed to create a socket, as (path suffix, function), each with its reason.
#: Creation is refused either way; these never connect.
ALLOWED_SOCKET_CREATORS = frozenset(
    {
        # urllib3 (imported by a dependency) probes for IPv6 at import by binding
        # ``::1``. Refused, it reads as no IPv6, which the dashboard never uses.
        ("/urllib3/util/connection.py", "_has_ipv6"),
    }
)


def _socket_violation(entry: str) -> bool:
    """Whether a socket created by ``entry`` (``path:function``) is a violation."""
    path, _, function = entry.rpartition(":")
    return not any(
        path.endswith(suffix) and function == name
        for suffix, name in ALLOWED_SOCKET_CREATORS
    )


def _assert_runtime_clean(result: dict[str, Any]) -> None:
    assert result["attempts"] == [], "the runtime tried to import usvote"
    assert result["import_events"] == [], "the runtime raised a usvote import event"
    assert result["sqlite"] == [], "the runtime opened a SQLite database"
    sockets = [entry for entry in result["sockets"] if _socket_violation(entry)]
    assert sockets == [], f"the runtime created sockets outside the allow-list: {sockets}"
    violations = [raw for raw in result["opens"] if _open_violation(raw)]
    assert violations == [], f"the runtime opened files outside the allow-list: {violations}"


def test_the_runtime_imports_no_usvote_and_reaches_only_the_public_api() -> None:
    """The refused run: every connection refused, every registered page driven."""
    result = _result(_run(_REFUSED_PROGRAM))
    _assert_runtime_clean(result)
    assert result["served"] == []
    # Non-empty: the paths above did try the API, so the host check is not vacuous.
    assert set(result["hosts"]) == {PUBLIC_API_HOST}


def test_the_success_path_reaches_only_the_public_api_and_reads_no_files() -> None:
    """The success run: the API answers, so prefetch, renders and a miss all execute."""
    result = _result(_run(_success_program()))
    _assert_runtime_clean(result)
    # The program asserted the order; this pins that the run reached all three stages.
    assert result["served"][0] == "/v1/meta"
    assert MISS_PATH in result["served"]
    assert len(result["served"]) >= 3
    assert set(result["hosts"]) == {PUBLIC_API_HOST}


def test_the_guard_program_can_fail(tmp_path: Path) -> None:
    """Non-vacuity: each recorder sees what it exists to see."""
    outside = tmp_path / "data.json"
    outside.write_text("{}", encoding="utf-8")
    fixture = FIXTURES / "v1_meta.json"
    program = (
        # Created before the prelude, so its connect reaches the connect event rather
        # than being refused at creation.
        "import socket\n_EARLY = socket.socket()\n"
        + _PRELUDE
        + f"""
import importlib
import sqlite3
import urllib.request

try:
    importlib.import_module("usvote")  # a dynamic import, swallowed: the finder
except ImportError:
    pass
try:
    import usvote  # the statement form: the import event (and the finder again)
except ImportError:
    pass
try:  # C level, no helper, to an IP literal: the connect event
    _EARLY.connect(("203.0.113.7", 443))
except OSError:
    pass
REFUSED = []
try:  # a raw socket to a hostname: refused at creation, before any lookup
    raw = socket.socket()
except OSError:
    REFUSED.append("socket")
else:
    raw.connect(("raw.guard.invalid", 443))
try:  # urllib's default opener honours the proxy variables the guard sets
    urllib.request.build_opener().open("http://example.invalid/", timeout=5)
except OSError:
    pass
try:
    sqlite3.connect(":memory:")
except OSError:
    REFUSED.append("sqlite")
assert REFUSED == ["socket", "sqlite"], REFUSED
for name in ({str(fixture)!r}, {str(outside)!r}):
    with open(name, encoding="utf-8") as handle:
        handle.read()
"""
        + _RESULT
    )
    result = _result(_run(program))
    assert result["attempts"] == ["usvote", "usvote"]
    # The statement form raises the event; whether import_module does is CPython's call.
    assert "usvote" in result["import_events"]
    hosts = set(result["hosts"])
    assert "203.0.113.7" in hosts
    assert any(_socket_violation(entry) for entry in result["sockets"])
    assert "proxy.guard.invalid" in hosts
    assert result["sqlite"] == [":memory:"]
    violations = {raw for raw in result["opens"] if _open_violation(raw)}
    assert {str(fixture), str(outside)} <= violations


def test_the_fake_transport_answers_the_api_host_only() -> None:
    """Non-vacuity for the success run's transport: it serves, and it refuses."""
    program = (
        _PRELUDE
        + _fixture_transport()
        + f"""
import json
import urllib.error
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({{}}))
with opener.open("https://{PUBLIC_API_HOST}/v1/meta", timeout=5) as response:
    assert response.status == 200
    assert response.headers["ETag"] == f'"{{_VERSION}}"'
    assert json.loads(response.read())["provenance"]["snapshot_version"] == _VERSION
try:
    opener.open("https://{PUBLIC_API_HOST}/v1/no-such-path", timeout=5)
except urllib.error.HTTPError as exc:
    assert exc.code == 404
else:
    raise AssertionError("an unrecorded path was answered")
try:
    opener.open("https://example.invalid/v1/meta", timeout=5)
except urllib.error.URLError:
    pass
else:
    raise AssertionError("another host was answered")
"""
        + _RESULT
    )
    result = _result(_run(program))
    assert result["served"] == ["/v1/meta"]
    assert set(result["hosts"]) == {PUBLIC_API_HOST, "example.invalid"}


@pytest.mark.parametrize(
    ("raw", "violation"),
    [
        (os.path.join(sysconfig.get_paths()["stdlib"], "json", "__init__.py"), False),
        (str(PACKAGE / "app.py"), False),
        ("explore/pages/home.py", False),  # relative to the program's directory
        (mimetypes.knownfiles[0], False),
        ("/dev/urandom", False),
        ("<unknown>", False),
        (str(FIXTURES / "v1_meta.json"), True),
        ("../tests/fixtures/dashboard/v1_meta.json", True),
        (str(DASHBOARD / "app.yaml"), True),
        (str(REPO / "src" / "usvote" / "__init__.py"), True),
        ("/etc/passwd", True),
        (os.path.join(sys.base_prefix, "share", "data.json"), True),
    ],
)
def test_the_open_rules_flag_what_they_should(raw: str, violation: bool) -> None:
    """Non-vacuity at the level of the rules."""
    assert _open_violation(raw) is violation


@pytest.mark.parametrize(
    ("entry", "violation"),
    [
        ("/venv/site-packages/urllib3/util/connection.py:_has_ipv6", False),
        ("/venv/site-packages/urllib3/util/connection.py:create_connection", True),
        ("/elsewhere/_has_ipv6.py:_has_ipv6", True),
        ("<stdin>:<module>", True),
        ("?:?", True),
    ],
)
def test_the_socket_rules_flag_what_they_should(entry: str, violation: bool) -> None:
    assert _socket_violation(entry) is violation


def test_tests_wins_over_every_allow_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ``tests/`` check is not merely the roots' fallback: it beats an allow."""
    fixture = FIXTURES / "v1_meta.json"
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "LIBRARY_ROOTS", (*LIBRARY_ROOTS, REPO.resolve()))
    monkeypatch.setattr(module, "ALLOWED_FILES", ALLOWED_FILES | {fixture.resolve()})
    assert _open_violation(str(REPO / "src" / "usvote" / "__init__.py")) is False
    assert _open_violation(str(fixture)) is True


def test_a_symlink_into_tests_is_a_violation(tmp_path: Path) -> None:
    """The ``tests/`` check uses the resolved name."""
    link = tmp_path / "innocent.json"
    link.symlink_to(FIXTURES / "v1_meta.json")
    assert _open_violation(str(link)) is True


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
        and p != GUIDANCE
        and "run.app" in p.read_text(encoding="utf-8", errors="replace")
    ]
    assert WORKFLOW.is_file() and PROBE.is_file()
    assert offenders == []


def _deploy_root_file_allowed(relative: Path) -> bool:
    """Where each kind of file may sit in the deploy root. A later story that needs
    another kind of file (a favicon, say) extends this, with a reason."""
    parts = relative.parts
    if len(parts) == 1:
        return relative.name in {
            "app.yaml",
            ".gcloudignore",
            "requirements.txt",
            "CLAUDE.md",  # GUIDANCE: the allow-list keeps it out of the upload
        }
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
        ("CLAUDE.md", True),
        ("explore/CLAUDE.md", False),  # explore/ uploads whole
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


def _link_out(tmp_path: Path, root: Path) -> Path:
    """A ``.py`` name inside ``root`` that is a symlink to a data file outside it."""
    target = tmp_path / "outside" / "data.json"
    target.parent.mkdir()
    target.write_text("{}", encoding="utf-8")
    root.mkdir()
    link = root / "pkg.py"
    link.symlink_to(target)
    return link


@pytest.mark.parametrize("key", ["stdlib", "platstdlib", "purelib", "platlib"])
def test_the_library_roots_carry_the_configured_form(key: str) -> None:
    """A root that itself sits behind a symlink matches the names imports write."""
    configured = sysconfig.get_paths()[key]
    assert Path(os.path.abspath(configured)) in LIBRARY_ROOTS
    assert Path(os.path.realpath(configured)) in LIBRARY_ROOTS


def test_a_symlink_under_a_library_root_is_accepted_as_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store-symlinked site-packages entry (uv's symlink mode, Nix) is allowed."""
    root = tmp_path / "site-packages"
    link = _link_out(tmp_path, root)
    monkeypatch.setattr(sys.modules[__name__], "LIBRARY_ROOTS", (*LIBRARY_ROOTS, root))
    assert _open_violation(str(link)) is False
    assert _open_violation(str(link.resolve())) is True  # the target itself is not


def test_a_symlink_out_of_the_package_is_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the library roots accept a name as written; ``explore/`` does not."""
    package = tmp_path / "explore"
    link = _link_out(tmp_path, package)
    monkeypatch.setattr(sys.modules[__name__], "PACKAGE", package)
    assert _open_violation(str(link)) is True
