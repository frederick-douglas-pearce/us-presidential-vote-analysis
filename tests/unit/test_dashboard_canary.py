"""The daily canary's plotly.js and origin-lock checks, run as written (#440).

``.github/workflows/api-canary.yml``'s "Check the public API" step asks the dashboard
for its bundled plotly.js and expects 404 (#430): a 200 means the running version
serves Dash's 4.8 MB copy again. The step collects failures (``fail()`` counts them, a
tally at the end decides the exit), and it switches off GitHub's ``bash -e`` with
``set +e`` so that one failing check cannot end the step before the rest report.

These tests pull blocks out of the step with the YAML parser, unchanged: the helpers
(everything before the first check), the whole dashboard block or the raw-origin block,
and the final tally. They run them under ``bash -e``, as GitHub does, with ``curl``
answering by URL and ``sleep`` stubbed. So they pin that the step reaches the plotly.js
check and that its exit code follows from it, not only the call's text. Offline: the
stubbed ``curl`` makes no request.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "api-canary.yml"
)
_STEP = "Check the public API"
#: The step's first check; everything before it is the helpers.
_FIRST_CHECK = 'echo "=== through Cloudflare'
_DASHBOARD_START = 'if [ -n "${EXPLORE_HOST}" ]; then'
_ORIGIN_START = 'if [ -n "${RAW_ORIGIN_URL}" ]; then'
_TALLY_START = 'if [ "$FAILURES" -ne 0 ]; then'
_PLOTLY_START = 'expect_status "dashboard plotly.js (#430)"'
_ORIGIN_CALL = 'expect_status "raw /v1 origin-lock" "${RAW_ORIGIN_URL}/v1/meta" 403'

_CF_HOST = "api.example.test"
_HOST = "explore.example.test"
_PLOTLY_URL = (
    f"https://{_HOST}/_dash-component-suites/plotly/package_data/plotly.min.js"
)
_ORIGIN = "https://origin.example.test"
_LABEL = "dashboard plotly.js (#430)"
_SNAPSHOT = "a" * 64

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

#: ``curl`` answers by URL (its last argument): the dashboard page shell with its
#: canonical link, the routing callback with a snapshot version, the plotly.js path with
#: ``$PLOTLY_CODE`` and the raw origin with ``$ORIGIN_CODE``. A code of ``fail`` is a
#: connection error (exit 7, ``%{http_code}`` = 000). Each call goes to ``$CURL_LOG`` as one
#: line, every argument ended by a unit separator (0x1f), so an empty argument shows as
#: one: joining them with spaces would hide it.
_STUBS = """\
sleep() { :; }
curl() {
  { printf '%s\\x1f' "$@"; printf '\\n'; } >> "$CURL_LOG"
  local url="${@: -1}" out="" hdr="" fmt="" code=200 body=""
  while [ $# -gt 0 ]; do
    case "$1" in -o) out="$2"; shift;; -D) hdr="$2"; shift;; -w) fmt="$2"; shift;; esac
    shift
  done
  case "$url" in
    "https://$EXPLORE_HOST/") body="<link rel=\\"canonical\\" href=\\"https://$EXPLORE_HOST/\\">";;
    */_dash-update-component) body="{\\"version\\": \\"$SNAPSHOT\\"}";;
    */plotly.min.js) code="$PLOTLY_CODE";;
    "$RAW_ORIGIN_URL/v1/meta") code="$ORIGIN_CODE";;
    *) code=599;;
  esac
  if [ "$code" = fail ]; then [ -n "$fmt" ] && printf 000; return 7; fi
  [ -n "$out" ] && printf '%s' "$body" > "$out"
  [ -n "$hdr" ] && printf 'HTTP/2 %s\\r\\n' "$code" > "$hdr"
  [ -n "$fmt" ] && printf '%s' "$code"
  return 0
}
"""


def _step_run() -> str:
    workflow = yaml.safe_load(_WORKFLOW.read_text())
    steps = [s for job in workflow["jobs"].values() for s in job["steps"]]
    (step,) = [s for s in steps if s.get("name") == _STEP]
    run: str = step["run"]
    return run


def _line_start(text: str, marker: str) -> int:
    return text.rindex("\n", 0, text.index(marker)) + 1


def _if_block(run: str, marker: str) -> str:
    """An ``if`` block, from the line holding ``marker`` to its own ``fi``."""
    lines = run[_line_start(run, marker) :].splitlines(keepends=True)
    indent = len(lines[0]) - len(lines[0].lstrip())
    end = next(
        i for i, line in enumerate(lines) if line.rstrip() == " " * indent + "fi"
    )
    return "".join(lines[: end + 1])


def _plotly_call(run: str) -> str:
    """The plotly.js call, from its first line to its last continuation line."""
    lines = run[_line_start(run, _PLOTLY_START) :].splitlines()
    end = next(i for i, line in enumerate(lines) if not line.rstrip().endswith("\\"))
    return "\n".join(lines[: end + 1])


def _run(
    tmp_path: Path, block: str, *, plotly: str = "404", origin: str = "403"
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    run = _step_run()
    helpers = run[: run.index(_FIRST_CHECK)]
    tally = run[_line_start(run, _TALLY_START) :]
    checks = _if_block(run, _DASHBOARD_START if block == "dashboard" else _ORIGIN_START)
    script = tmp_path / "canary.sh"
    script.write_text(f"{_STUBS}{helpers}{checks}{tally}", encoding="utf-8")
    log = tmp_path / "curl.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": "/usr/bin:/bin",
        "TMPDIR": str(tmp_path),
        "CURL_LOG": str(log),
        "PLOTLY_CODE": plotly,
        "ORIGIN_CODE": origin,
        "SNAPSHOT": _SNAPSHOT,
        "CF_HOST": _CF_HOST,
        "EXPLORE_HOST": _HOST,
        "EXPLORE_APP_HOST": "",
        "RAW_ORIGIN_URL": _ORIGIN,
    }
    result = subprocess.run(
        ["bash", "-e", str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    calls = [
        line.split("\x1f")[:-1] for line in log.read_text(encoding="utf-8").splitlines()
    ]
    return result, calls


def _calls_to(calls: list[list[str]], url: str) -> list[list[str]]:
    return [call for call in calls if call[-1] == url]


def _expect_status_args(call: list[str]) -> list[str]:
    """A call's arguments with the two temp-file paths masked."""
    assert call[1] == "-o" and call[3] == "-D", call
    return [call[0], "-o", "<body>", "-D", "<hdr>", *call[5:]]


def test_the_blocks_are_found_in_the_workflow() -> None:
    run = _step_run()
    helpers = run[: run.index(_FIRST_CHECK)]
    assert "set -uo pipefail\nset +e\n" in "\n".join(
        line.strip()
        for line in helpers.splitlines()
        if not line.strip().startswith("#")
    )
    assert _plotly_call(run).rstrip().endswith("404 --head")
    assert _plotly_call(run) in _if_block(run, _DASHBOARD_START)
    assert _ORIGIN_CALL in _if_block(run, _ORIGIN_START)
    assert (
        run[_line_start(run, _TALLY_START) :]
        .rstrip()
        .endswith('echo "API canary: all checks passed."')
    )


def test_a_404_passes(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "dashboard", plotly="404")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"✓ {_LABEL}: 404" in result.stdout
    assert "::error::" not in result.stdout
    assert "API canary: all checks passed." in result.stdout
    assert len(_calls_to(calls, _PLOTLY_URL)) == 1


@pytest.mark.parametrize(("code", "got"), [("200", "200"), ("fail", "000")])
def test_anything_but_404_fails_the_run_after_the_rest_report(
    tmp_path: Path, code: str, got: str
) -> None:
    """A 200 (the file served again) or no answer at all fails the check after three
    tries, the checks after it still run, and the tally fails the step."""
    result, calls = _run(tmp_path, "dashboard", plotly=code)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"::error::{_LABEL}: got {got}, want 404 — {_PLOTLY_URL}" in result.stdout
    assert f"::error::API canary: 1 check(s) failed against https://{_CF_HOST}" in (
        result.stdout
    )
    assert result.stdout.count("::error::") == 2
    # The content check comes after the plotly.js check in the step.
    assert "✓ dashboard content carries the live snapshot" in result.stdout
    assert len(_calls_to(calls, _PLOTLY_URL)) == 3


def test_the_check_is_a_head_request_for_the_exact_path(tmp_path: Path) -> None:
    _, calls = _run(tmp_path, "dashboard", plotly="404")
    (call,) = _calls_to(calls, _PLOTLY_URL)
    assert _expect_status_args(call) == [
        "-sS",
        "-o",
        "<body>",
        "-D",
        "<hdr>",
        "-w",
        "%{http_code}",
        "--max-time",
        "20",
        "--head",
        _PLOTLY_URL,
    ]


def test_a_failing_origin_lock_fails_the_run_without_ending_the_step(
    tmp_path: Path,
) -> None:
    """The raw origin answering 200 means the lock is open. Under ``bash -e`` the
    failure is counted and the step goes on to the tally (#440, owner decision)."""
    result, calls = _run(tmp_path, "origin", origin="200")
    assert result.returncode == 1, result.stdout + result.stderr
    assert (
        f"::error::raw /v1 origin-lock: got 200, want 403 — {_ORIGIN}/v1/meta"
        in result.stdout
    )
    assert f"::error::API canary: 1 check(s) failed against https://{_CF_HOST}" in (
        result.stdout
    )
    assert len(_calls_to(calls, f"{_ORIGIN}/v1/meta")) == 3


def test_a_closed_origin_lock_passes_and_sends_no_extra_option(tmp_path: Path) -> None:
    """A call with no extra curl options sends none: ``--head`` is the plotly.js
    check's alone."""
    result, calls = _run(tmp_path, "origin", origin="403")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "✓ raw /v1 origin-lock: 403" in result.stdout
    (call,) = _calls_to(calls, f"{_ORIGIN}/v1/meta")
    assert _expect_status_args(call) == [
        "-sS",
        "-o",
        "<body>",
        "-D",
        "<hdr>",
        "-w",
        "%{http_code}",
        "--max-time",
        "20",
        f"{_ORIGIN}/v1/meta",
    ]
