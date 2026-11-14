"""The daily canary's plotly.js and origin-lock checks, run as written (#440).

``.github/workflows/api-canary.yml``'s "Check the public API" step asks the dashboard
for its bundled plotly.js and expects 404 (#430): a 200 means the running version
serves Dash's 4.8 MB copy again. The step collects failures rather than stopping at the
first, but GitHub runs it under ``bash -e``, so a failing ``expect_status`` outside an
``if`` would end the step before the checks after it report. The plotly.js check and the
raw-origin lock check are both such calls.

These tests pull the step's helpers (everything before its first check) and each of
those two checks out of the workflow with the YAML parser, unchanged, and run them under
``bash -e`` with ``curl`` and ``sleep`` stubbed, so what they pin is the shell the
workflow runs, not a copy of it. Offline: the stubbed ``curl`` makes no request.
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
_PLOTLY_START = 'expect_status "dashboard plotly.js (#430)"'
_ORIGIN_START = 'if [ -n "${RAW_ORIGIN_URL}" ]; then'
_HOST = "explore.example.test"
_PLOTLY_URL = (
    f"https://{_HOST}/_dash-component-suites/plotly/package_data/plotly.min.js"
)
_ORIGIN = "https://origin.example.test"
_LABEL = "dashboard plotly.js (#430)"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

#: ``curl`` answers ``$CODE``, or fails outright (exit 7, as on a connection error) when
#: ``$CODE`` is ``fail``. Each call's arguments go to ``$CURL_LOG``, one call per line.
_STUBS = """\
sleep() { :; }
curl() {
  printf '%s\\n' "$*" >> "$CURL_LOG"
  if [ "$CODE" = fail ]; then printf 000; return 7; fi
  local out="" hdr=""
  while [ $# -gt 0 ]; do
    case "$1" in -o) out="$2"; shift;; -D) hdr="$2"; shift;; esac
    shift
  done
  : > "$out"
  printf 'HTTP/2 %s\\r\\n' "$CODE" > "$hdr"
  printf '%s' "$CODE"
}
"""


def _step_run() -> str:
    workflow = yaml.safe_load(_WORKFLOW.read_text())
    steps = [s for job in workflow["jobs"].values() for s in job["steps"]]
    (step,) = [s for s in steps if s.get("name") == _STEP]
    assert "shell" not in step, "the step is tested under bash -e, GitHub's default"
    run: str = step["run"]
    return run


def _helpers(run: str) -> str:
    return run[: run.index(_FIRST_CHECK)]


def _plotly_check(run: str) -> str:
    """The plotly.js call, from its first line to the line ending ``|| true``."""
    lines = run[run.index(_PLOTLY_START) :].splitlines(keepends=True)
    end = next(i for i, line in enumerate(lines) if line.rstrip().endswith("|| true"))
    return "".join(lines[: end + 1])


def _origin_check(run: str) -> str:
    """The raw-origin block, from its ``if`` to its own ``fi``."""
    start = run.rindex("\n", 0, run.index(_ORIGIN_START)) + 1
    lines = run[start:].splitlines(keepends=True)
    indent = len(lines[0]) - len(lines[0].lstrip())
    end = next(
        i for i, line in enumerate(lines) if line.rstrip() == " " * indent + "fi"
    )
    return "".join(lines[: end + 1])


def _run(
    tmp_path: Path, check: str, code: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    run = _step_run()
    block = _plotly_check(run) if check == "plotly" else _origin_check(run)
    script = tmp_path / "canary.sh"
    script.write_text(
        f'{_STUBS}{_helpers(run)}{block}echo "END REACHED FAILURES=${{FAILURES}}"\n',
        encoding="utf-8",
    )
    log = tmp_path / "curl.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": "/usr/bin:/bin",
        "CODE": code,
        "CURL_LOG": str(log),
        "EXPLORE_HOST": _HOST,
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
    return result, log.read_text(encoding="utf-8").splitlines()


def test_the_checks_are_found_in_the_workflow() -> None:
    run = _step_run()
    assert "expect_status()" in _helpers(run)
    assert _plotly_check(run).rstrip().endswith("404 --head || true")
    assert _origin_check(run).lstrip().startswith(_ORIGIN_START)


def test_a_404_passes(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, "plotly", "404")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"✓ {_LABEL}: 404" in result.stdout
    assert "::error::" not in result.stdout
    assert "END REACHED FAILURES=0" in result.stdout
    assert len(calls) == 1


@pytest.mark.parametrize(("code", "got"), [("200", "200"), ("fail", "000")])
def test_anything_but_404_fails_and_the_step_goes_on(
    tmp_path: Path, code: str, got: str
) -> None:
    """A 200 (the file served again) or no answer at all fails the check after its
    retries, and under ``bash -e`` the step still reaches the checks after it."""
    result, calls = _run(tmp_path, "plotly", code)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"::error::{_LABEL}: got {got}, want 404 — {_PLOTLY_URL}" in result.stdout
    assert result.stdout.count("::error::") == 1
    assert "END REACHED FAILURES=1" in result.stdout
    assert len(calls) == 3


def test_the_check_is_a_head_request_for_the_exact_path(tmp_path: Path) -> None:
    _, calls = _run(tmp_path, "plotly", "404")
    (call,) = calls
    args = call.split()
    assert "--head" in args
    assert args[-1] == _PLOTLY_URL


def test_a_failing_origin_lock_does_not_end_the_step(tmp_path: Path) -> None:
    """The raw origin answering 200 means the lock is open; the failure is counted and
    the dashboard checks after it still run (#440, owner decision)."""
    result, calls = _run(tmp_path, "origin", "200")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        f"::error::raw /v1 origin-lock: got 200, want 403 — {_ORIGIN}/v1/meta"
        in result.stdout
    )
    assert "END REACHED FAILURES=1" in result.stdout
    assert len(calls) == 3


def test_a_closed_origin_lock_passes_and_sends_no_extra_option(tmp_path: Path) -> None:
    """A call with no extra curl options sends none: ``--head`` is the plotly.js
    check's alone."""
    result, calls = _run(tmp_path, "origin", "403")
    assert "✓ raw /v1 origin-lock: 403" in result.stdout
    assert "END REACHED FAILURES=0" in result.stdout
    (call,) = calls
    assert "--head" not in call.split()
    assert call.split()[-1] == f"{_ORIGIN}/v1/meta"
