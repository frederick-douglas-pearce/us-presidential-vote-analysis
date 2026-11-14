"""``scripts/check_dashboard_routing.sh`` (#526), run offline against a fake ``curl``.

The deploy workflow runs the script on a new version's own host before traffic moves, so
a failure rolls the deploy back. It checks that the path is decoded once, by the app
(D089), and that the app serves no local plotly.js (#430), first making sure the
instance's cache is filled so a cold cache is never read as a double decode.

These tests run the script itself, by its own ``#!`` line, with the shared fake ``curl``
and a no-op ``sleep`` first on ``PATH`` (``tests/workflow_steps.py``). Every test that
runs the script asserts the calls the fake received, so a fake that was bypassed fails the
test. The last tests pin the step in ``deploy-dashboard.yml`` that runs it: its position
inside the rollback window is what makes a failure roll back.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from subprocess import CompletedProcess

import pytest
import yaml

from tests.workflow_steps import Route, run_bash, write_stub_bin

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_dashboard_routing.sh"
WORKFLOW = REPO / ".github" / "workflows" / "deploy-dashboard.yml"

BASE = "https://v-x-dot-app.example"
CACHE = f"{BASE}/election/1825"
ESCAPED = f"{BASE}/election/%2531824"
CONTROL = f"{BASE}/election/%31824"
PLOTLY = f"{BASE}/_dash-component-suites/plotly/package_data/plotly.min.js"
NOT_FOUND = '<head><meta name="robots" content="noindex"></head>'
FOUND = '<head><link rel="canonical" href="https://explore.example/election/1824"></head>'

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _routes(**codes: str) -> list[Route]:
    """Every check answering as a serving, decoded-once version does, with the codes of
    the checks named (``cache``, ``escaped``, ``control``, ``plotly``) replaced."""
    want = {"cache": "404", "escaped": "404", "control": "200", "plotly": "404"}
    want.update(codes)
    return [
        Route(CACHE, want["cache"], NOT_FOUND),
        Route(ESCAPED, want["escaped"], NOT_FOUND),
        Route(CONTROL, want["control"], FOUND),
        Route(PLOTLY, want["plotly"]),
    ]


def _check(
    tmp_path: Path, routes: list[Route]
) -> tuple[CompletedProcess[str], list[list[str]]]:
    bin_dir = write_stub_bin(tmp_path)
    return run_bash([str(SCRIPT), BASE], tmp_path, routes, bin_dir=bin_dir)


def _urls(calls: list[list[str]]) -> list[str]:
    return [call[-1] for call in calls]


def _errors(result: CompletedProcess[str]) -> list[str]:
    return [line for line in result.stdout.splitlines() if line.startswith("::error::")]


def _failed(result: CompletedProcess[str]) -> str:
    """The checks the one ``::error::`` line names."""
    (error,) = _errors(result)
    prefix = f"::error::{BASE} failed the routing checks: "
    assert error.startswith(prefix), error
    return error[len(prefix) :]


def test_the_script_is_executable() -> None:
    """The workflow runs it by path, so a file without its exec bit fails the deploy."""
    assert os.access(SCRIPT, os.X_OK)
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\n")


def test_a_serving_decoded_once_version_passes(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes())
    assert result.returncode == 0, result.stdout + result.stderr
    assert _errors(result) == []
    assert f"  ✓ {BASE}: every routing check passed" in result.stdout
    for line in (
        "  ✓ cache filled: /election/1825 got 404, noindex: yes",
        "  ✓ decoded once: /election/%2531824 got 404, noindex: yes",
        "  ✓ decoded-once control: /election/%31824 got 200",
        "  ✓ no local plotly.js: got 404",
    ):
        assert line in result.stdout.splitlines()
    assert _urls(calls) == [CACHE, ESCAPED, CONTROL, PLOTLY]


def test_each_request_is_sent_exactly_as_written(tmp_path: Path) -> None:
    """The escaped paths reach curl byte for byte (curl sends them so), and only the
    plotly.js check is a HEAD."""
    _, calls = _check(tmp_path, _routes())
    for call in calls:
        assert call[:2] == ["-sS", "-o"], call
        assert call[3:7] == ["-w", "%{http_code}", "--max-time", "20"], call
    assert [call[7:] for call in calls] == [
        [CACHE],
        [ESCAPED],
        [CONTROL],
        ["--head", PLOTLY],
    ]
    assert ESCAPED.endswith("/election/%2531824")
    assert CONTROL.endswith("/election/%31824")


def test_a_double_decode_fails_and_is_not_retried(tmp_path: Path) -> None:
    """A 200 on %2531824: the path was decoded before the app read it."""
    result, calls = _check(tmp_path, _routes(escaped="200"))
    assert result.returncode == 1
    assert (
        "  ✗ decoded once: /election/%2531824 got 200, noindex: yes; want 404 with "
        "noindex" in result.stdout.splitlines()
    )
    assert _failed(result) == "decoded once"
    assert _urls(calls).count(ESCAPED) == 1


def test_a_404_without_noindex_fails(tmp_path: Path) -> None:
    """A 404 that is not the app's own came from something in front of it."""
    routes = _routes()
    routes[1] = Route(ESCAPED, "404", "<h1>Not Found</h1>")
    result, calls = _check(tmp_path, routes)
    assert result.returncode == 1
    assert (
        "  ✗ decoded once: /election/%2531824 got 404, noindex: no; want 404 with "
        "noindex" in result.stdout.splitlines()
    )
    assert _failed(result) == "decoded once"
    assert _urls(calls).count(ESCAPED) == 1


def test_a_failing_control_fails(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes(control="404"))
    assert result.returncode == 1
    assert "  ✗ decoded-once control: /election/%31824 got 404; want 200" in (
        result.stdout.splitlines()
    )
    assert _failed(result) == "decoded-once control"
    assert _urls(calls).count(CONTROL) == 1


def test_a_served_plotlyjs_fails(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes(plotly="200"))
    assert result.returncode == 1
    assert "  ✗ no local plotly.js: got 200; want 404" in result.stdout.splitlines()
    assert _failed(result) == "no local plotly.js"
    assert _urls(calls).count(PLOTLY) == 1


def test_a_request_with_no_answer_fails_after_three_tries(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes(control="fail"))
    assert result.returncode == 1
    assert "  ✗ decoded-once control: /election/%31824 got 000; want 200" in (
        result.stdout.splitlines()
    )
    assert _failed(result) == "decoded-once control"
    assert _urls(calls).count(CONTROL) == 3


def test_no_answer_on_the_escaped_path_reports_it_unfetched(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes(escaped="fail"))
    assert result.returncode == 1
    assert (
        "  ✗ decoded once: /election/%2531824 got 000, noindex: unfetched; want 404 "
        "with noindex" in result.stdout.splitlines()
    )
    assert _urls(calls).count(ESCAPED) == 3


def test_every_failing_check_is_reported(tmp_path: Path) -> None:
    """Each check is judged on its own, and the checks after a failure still run."""
    result, calls = _check(tmp_path, _routes(control="404", plotly="200"))
    assert result.returncode == 1
    assert _failed(result) == "decoded-once control; no local plotly.js"
    assert "  ✓ decoded once: /election/%2531824 got 404, noindex: yes" in (
        result.stdout.splitlines()
    )
    assert _urls(calls) == [CACHE, ESCAPED, CONTROL, PLOTLY]


def test_a_request_that_recovers_passes(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes(control="fail,200"))
    assert result.returncode == 0, result.stdout
    assert _urls(calls) == [CACHE, ESCAPED, CONTROL, CONTROL, PLOTLY]


def test_a_server_error_is_retried(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes(plotly="503,404"))
    assert result.returncode == 0, result.stdout
    assert _urls(calls).count(PLOTLY) == 2


def test_a_lasting_server_error_fails(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes(plotly="500"))
    assert result.returncode == 1
    assert "  ✗ no local plotly.js: got 500; want 404" in result.stdout.splitlines()
    assert _urls(calls).count(PLOTLY) == 3


def test_a_cold_cache_fails_and_the_escaped_path_is_not_judged(tmp_path: Path) -> None:
    """A cold index answers 200 for any year: the run fails naming the cache, and a 200
    on %2531824 is reported, never as a double decode."""
    result, calls = _check(tmp_path, _routes(cache="200", escaped="200"))
    assert result.returncode == 1
    assert _failed(result) == "cache filled"
    assert (
        "  ✗ cache filled: /election/1825 got 200, noindex: yes; want 404 with noindex"
        in result.stdout.splitlines()
    )
    assert (
        "  - decoded once: /election/%2531824 got 200, noindex: yes; not judged, the "
        "cache check did not pass" in result.stdout.splitlines()
    )
    assert _urls(calls) == [CACHE, CACHE, CACHE, ESCAPED, CONTROL, PLOTLY]


def test_a_cache_that_fills_on_a_retry_passes(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes(cache="200,404"))
    assert result.returncode == 0, result.stdout
    assert _urls(calls) == [CACHE, CACHE, ESCAPED, CONTROL, PLOTLY]


def test_no_answer_on_the_cache_path_is_retried(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes(cache="fail,404"))
    assert result.returncode == 0, result.stdout
    assert _urls(calls) == [CACHE, CACHE, ESCAPED, CONTROL, PLOTLY]


def test_no_answer_on_the_cache_path_fails_after_three_tries(tmp_path: Path) -> None:
    result, calls = _check(tmp_path, _routes(cache="fail"))
    assert result.returncode == 1
    assert _failed(result) == "cache filled"
    assert (
        "  ✗ cache filled: /election/1825 got 000, noindex: unfetched; want 404 with "
        "noindex" in result.stdout.splitlines()
    )
    assert _urls(calls) == [CACHE, CACHE, CACHE, ESCAPED, CONTROL, PLOTLY]


def test_response_bytes_never_reach_the_log(tmp_path: Path) -> None:
    """Only codes and noindex results (yes, no, unfetched) are printed, so a body cannot
    carry a workflow command."""
    routes = _routes(escaped="200")
    routes[1] = Route(ESCAPED, "200", "::error::planted ##[error]planted")
    result, calls = _check(tmp_path, routes)
    assert result.returncode == 1
    assert _urls(calls) == [CACHE, ESCAPED, CONTROL, PLOTLY]
    assert (
        "  ✗ decoded once: /election/%2531824 got 200, noindex: no; want 404 with "
        "noindex" in result.stdout.splitlines()
    )
    assert "planted" not in result.stdout + result.stderr


def test_a_404_without_noindex_on_the_cache_path_fails(tmp_path: Path) -> None:
    """A tagless 404 on /election/1825 is not the app's own: it is retried, then fails
    the cache check, and the escaped path is not judged."""
    routes = _routes()
    routes[0] = Route(CACHE, "404", "<h1>Not Found</h1>")
    result, calls = _check(tmp_path, routes)
    assert result.returncode == 1
    assert _failed(result) == "cache filled"
    assert (
        "  ✗ cache filled: /election/1825 got 404, noindex: no; want 404 with noindex"
        in result.stdout.splitlines()
    )
    assert (
        "  - decoded once: /election/%2531824 got 404, noindex: yes; not judged, the "
        "cache check did not pass" in result.stdout.splitlines()
    )
    assert _urls(calls) == [CACHE, CACHE, CACHE, ESCAPED, CONTROL, PLOTLY]


def test_a_check_never_reads_an_earlier_checks_body(tmp_path: Path) -> None:
    """If curl left the body file as it was after an answer arrived, the cache check's
    noindex body would make a tagless 404 on %2531824 pass; the script empties it first."""
    result, calls = _check(tmp_path, _routes(escaped="404@keep"))
    assert result.returncode == 1
    assert (
        "  ✗ decoded once: /election/%2531824 got 404, noindex: no; want 404 with "
        "noindex" in result.stdout.splitlines()
    )
    assert _failed(result) == "decoded once"
    assert _urls(calls) == [CACHE, ESCAPED, CONTROL, PLOTLY]


def test_a_curl_error_after_the_status_arrived_counts_as_no_answer(
    tmp_path: Path,
) -> None:
    """curl can print a real code and still exit nonzero (28: the transfer timed out
    after the status arrived). That is no answer: retried, and reported as 000."""
    result, calls = _check(tmp_path, _routes(control="200@28"))
    assert result.returncode == 1
    assert "  ✗ decoded-once control: /election/%31824 got 000; want 200" in (
        result.stdout.splitlines()
    )
    assert _failed(result) == "decoded-once control"
    assert _urls(calls).count(CONTROL) == 3


# --- The workflow step ------------------------------------------------------------

_RUN = 'scripts/check_dashboard_routing.sh "https://${VERSION}-dot-${APP_HOST}"'
_ROLLBACK_IF = (
    "${{ (failure() || cancelled()) && steps.before.outcome == 'success' && "
    "steps.probe_redirect.outcome != 'success' }}"
)


def _steps() -> list[dict[str, object]]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps: list[dict[str, object]] = workflow["jobs"]["deploy"]["steps"]
    return steps


def test_the_step_runs_between_the_version_probe_and_the_traffic_move() -> None:
    """Inside the rollback window: after the version-host probe has filled the cache,
    before any traffic moves (so before ``probe_redirect``, whose success closes it)."""
    ids = [step.get("id") for step in _steps()]
    at = ids.index("probe_routing")
    assert ids[at - 1 : at + 2] == ["probe_version", "probe_routing", "traffic"]
    assert ids.index("probe_redirect") > at


def test_the_step_runs_the_script_on_the_version_host_with_a_timeout() -> None:
    (step,) = [s for s in _steps() if s.get("id") == "probe_routing"]
    assert step["run"] == _RUN
    assert step["env"] == {
        "VERSION": "${{ steps.before.outputs.version }}",
        "APP_HOST": "${{ steps.before.outputs.app_host }}",
    }
    assert step["timeout-minutes"] == 6
    # Nothing that would let a failure pass, or the step run after a failure.
    assert not {"shell", "if", "continue-on-error"} & set(step)


def test_roll_back_still_runs_on_a_failure_before_the_redirect_probe() -> None:
    steps = _steps()
    (step,) = [s for s in steps if s.get("name") == "Roll back"]
    assert step["if"] == _ROLLBACK_IF
    # After the routing check, so a failure there reaches it.
    ids = [s.get("id") for s in steps]
    assert steps.index(step) > ids.index("probe_routing")
