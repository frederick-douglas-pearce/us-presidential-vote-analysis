"""The daily canary's plotly.js, origin-lock and JSON-body checks, run as written.

``.github/workflows/api-canary.yml``'s "Check the public API" step asks the dashboard
for its bundled plotly.js and expects 404 (#430): a 200 means the running version
serves Dash's 4.8 MB copy again. The step collects failures (``fail()`` counts them, a
tally at the end decides the exit), and it switches off GitHub's ``bash -e`` with
``set +e`` so that one failing check cannot end the step before the rest report.

Since #526 the ``/health`` and ``/v1/meta`` checks read their fields only from a body
that is a JSON object; any other 200 (a Cloudflare challenge page, say) fails once, with a
message that says so, rather than through field checks that would name a wrong cause.

These tests pull blocks out of the step with the YAML parser, unchanged
(``tests/workflow_steps.py``): the helpers (everything before the first check), the whole
dashboard block, the raw-origin block or the ``/health`` and ``/v1/meta`` blocks, and the
final tally. They run them under ``bash -e``, as GitHub does, with ``curl``
answering by URL and ``sleep`` stubbed. So they pin that the step reaches the plotly.js
check and that its exit code follows from it, not only the call's text. Offline: the
stubbed ``curl`` makes no request.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tests.workflow_steps import (
    CURL_STUB,
    Route,
    if_block,
    line_start,
    run_bash,
    step_run,
)

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
_HEALTH_START = 'if expect_status "/health"'
_META_START = 'if expect_status "/v1/meta"'
_JSON_GATE = "if ! jq -e 'type == \"object\"' \"$BODY\" >/dev/null 2>&1; then"

_CF_HOST = "api.example.test"
_HOST = "explore.example.test"
_PLOTLY_URL = (
    f"https://{_HOST}/_dash-component-suites/plotly/package_data/plotly.min.js"
)
_ORIGIN = "https://origin.example.test"
_LABEL = "dashboard plotly.js (#430)"
_SNAPSHOT = "a" * 64

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _step_run() -> str:
    return step_run(_WORKFLOW, _STEP)


def _plotly_call(run: str) -> str:
    """The plotly.js call, from its first line to its last continuation line."""
    lines = run[line_start(run, _PLOTLY_START) :].splitlines()
    end = next(i for i, line in enumerate(lines) if not line.rstrip().endswith("\\"))
    return "\n".join(lines[: end + 1])


def _dashboard_routes(plotly: str, origin: str) -> list[Route]:
    """The dashboard's page shell with its canonical link, the routing callback with a
    snapshot version, the plotly.js path and the raw origin."""
    return [
        Route(
            f"https://{_HOST}/",
            "200",
            f'<link rel="canonical" href="https://{_HOST}/">',
        ),
        Route(
            f"https://{_HOST}/_dash-update-component",
            "200",
            f'{{"version": "{_SNAPSHOT}"}}',
        ),
        Route(_PLOTLY_URL, plotly),
        Route(f"{_ORIGIN}/v1/meta", origin),
    ]


def _run_blocks(
    tmp_path: Path, checks: str, routes: list[Route]
) -> tuple[CompletedProcess[str], list[list[str]]]:
    """The step's helpers, then ``checks``, then the tally, under ``bash -e``."""
    run = _step_run()
    helpers = run[: run.index(_FIRST_CHECK)]
    tally = run[line_start(run, _TALLY_START) :]
    script = tmp_path / "canary.sh"
    script.write_text(f"{CURL_STUB}{helpers}{checks}{tally}", encoding="utf-8")
    env = {
        "CF_HOST": _CF_HOST,
        "EXPLORE_HOST": _HOST,
        "EXPLORE_APP_HOST": "",
        "RAW_ORIGIN_URL": _ORIGIN,
    }
    return run_bash(["bash", "-e", str(script)], tmp_path, routes, env)


def _run(
    tmp_path: Path, block: str, *, plotly: str = "404", origin: str = "403"
) -> tuple[CompletedProcess[str], list[list[str]]]:
    run = _step_run()
    checks = if_block(run, _DASHBOARD_START if block == "dashboard" else _ORIGIN_START)
    return _run_blocks(tmp_path, checks, _dashboard_routes(plotly, origin))


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
    assert _plotly_call(run) in if_block(run, _DASHBOARD_START)
    assert _ORIGIN_CALL in if_block(run, _ORIGIN_START)
    for start in (_HEALTH_START, _META_START):
        assert _JSON_GATE in if_block(run, start)
    assert (
        run[line_start(run, _TALLY_START) :]
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


# --- /health and /v1/meta: a 200 that is not a JSON object (#526) --------------------

_HEALTH_URL = f"https://{_CF_HOST}/health"
_META_URL = f"https://{_CF_HOST}/v1/meta"
_HEALTH_BODY = (
    f'{{"origin_guard": "enforced", "snapshot_loaded": true, '
    f'"snapshot_version": "{_SNAPSHOT}"}}'
)
_META_BODY = '{"row_count": 5}'
#: A body a Cloudflare challenge could serve with a 200, and JSON that is no object.
_NOT_OBJECTS = ["<!DOCTYPE html><title>Just a moment...</title>", "[1]", "null", ""]
_FIELD_MESSAGES = ("origin_guard is", "snapshot_loaded=", "row_count=", "stale edge")


def _meta_headers(etag: str) -> str:
    return f'server: cloudflare\r\netag: W/"{etag}"\r\n'


def _run_json(
    tmp_path: Path,
    *,
    health: str = _HEALTH_BODY,
    meta: str = _META_BODY,
    etag: str = _SNAPSHOT,
) -> CompletedProcess[str]:
    run = _step_run()
    checks = if_block(run, _HEALTH_START) + if_block(run, _META_START)
    routes = [
        Route(_HEALTH_URL, "200", health),
        Route(_META_URL, "200", meta, _meta_headers(etag)),
    ]
    result, calls = _run_blocks(tmp_path, checks, routes)
    assert [call[-1] for call in calls] == [_HEALTH_URL, _META_URL]
    return result


def _error_lines(result: CompletedProcess[str]) -> list[str]:
    """The lines the runner reads as error commands: ``::error::`` after leading
    whitespace, which it trims."""
    return [
        line.lstrip()
        for line in result.stdout.splitlines()
        if line.lstrip().startswith("::error::")
    ]


def test_json_objects_pass(tmp_path: Path) -> None:
    result = _run_json(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _error_lines(result) == []
    assert "API canary: all checks passed." in result.stdout


def test_the_field_checks_still_fail_on_a_json_object(tmp_path: Path) -> None:
    """The gate passes an object through to the checks it guards."""
    result = _run_json(
        tmp_path, health='{"origin_guard": "off", "snapshot_loaded": true}'
    )
    assert result.returncode == 1
    assert (
        "::error::origin_guard is 'off', want 'enforced' — the /v1 origin lock is open"
        in result.stdout
    )


@pytest.mark.parametrize("body", _NOT_OBJECTS)
def test_a_health_body_that_is_not_an_object_fails_once(
    tmp_path: Path, body: str
) -> None:
    result = _run_json(tmp_path, health=body)
    assert result.returncode == 1, result.stdout + result.stderr
    assert _error_lines(result) == [
        "::error::/health answered 200 but the body is not a JSON object",
        f"::error::API canary: 1 check(s) failed against https://{_CF_HOST}",
    ]
    for message in _FIELD_MESSAGES:
        assert message not in result.stdout


@pytest.mark.parametrize("body", _NOT_OBJECTS)
def test_a_meta_body_that_is_not_an_object_fails_once(
    tmp_path: Path, body: str
) -> None:
    """The edge/origin comparison sits with the field checks: a challenge page's ETag
    names no snapshot, which would otherwise read as a stale edge cache."""
    result = _run_json(tmp_path, meta=body, etag="not-a-snapshot")
    assert result.returncode == 1, result.stdout + result.stderr
    assert _error_lines(result) == [
        "::error::/v1/meta answered 200 but the body is not a JSON object",
        f"::error::API canary: 1 check(s) failed against https://{_CF_HOST}",
    ]
    for message in _FIELD_MESSAGES:
        assert message not in result.stdout


def test_a_body_that_is_not_an_object_is_dumped_defused(tmp_path: Path) -> None:
    """The body's first bytes reach the log, but never as a workflow command."""
    result = _run_json(tmp_path, health="::error::x ##[error]y")
    assert result.returncode == 1
    assert "    | ::error::x # [error]y" in result.stdout.splitlines()
    assert "##[" not in result.stdout
    commands = [
        line for line in result.stdout.splitlines() if line.lstrip().startswith("::")
    ]
    assert commands == [
        "::error::/health answered 200 but the body is not a JSON object",
        f"::error::API canary: 1 check(s) failed against https://{_CF_HOST}",
    ]


@pytest.mark.parametrize(
    ("health", "meta", "etag", "message"),
    [
        (
            _HEALTH_BODY.replace('"snapshot_loaded": true', '"snapshot_loaded": false'),
            _META_BODY,
            _SNAPSHOT,
            "::error::snapshot_loaded=false — the service is up but holds no data",
        ),
        (
            _HEALTH_BODY,
            '{"row_count": 0}',
            _SNAPSHOT,
            "::error::row_count=0 — the served snapshot is empty",
        ),
        (
            _HEALTH_BODY,
            _META_BODY,
            "b" * 64,
            f"::error::the edge is serving snapshot '{'b' * 64}' but the origin has "
            f"'{_SNAPSHOT}' — stale edge cache",
        ),
    ],
    ids=["snapshot-not-loaded", "empty-snapshot", "stale-edge"],
)
def test_the_field_checks_run_on_a_json_object(
    tmp_path: Path, health: str, meta: str, etag: str, message: str
) -> None:
    """Behind the gate, each field check still runs: the stale-edge case also shows the
    origin's version is still read from /health."""
    result = _run_json(tmp_path, health=health, meta=meta, etag=etag)
    assert result.returncode == 1, result.stdout + result.stderr
    assert _error_lines(result) == [
        message,
        f"::error::API canary: 1 check(s) failed against https://{_CF_HOST}",
    ]
