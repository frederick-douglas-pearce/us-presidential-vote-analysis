"""Structural guard for the dashboard's e2e workflow's browser install (#486, D082).

``e2e.yml`` installs the headless shell from a cache keyed on the locked Playwright
version, and Chromium's system libraries in a step of their own with its own time cap.
Every property below fails silently if it regresses: the run stays green while the cache
never hits, or a hung package mirror goes back to cancelling the whole job instead of
failing the step that hung. So each one is checked here, and the negative cases show the
check can fail. What is not asserted, on purpose: step names, paths, the exact caps and
the cache key's literal text, which would only restate the YAML.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "e2e.yml"
JOB = "e2e"

#: Minutes left for the uncapped setup steps (checkout, uv, Python, ``uv sync``; about
#: 10 s on a healthy run) once every capped step has used its whole cap. The capped steps
#: must fire before the job's own cap, or a hang ends as a cancellation of the job.
SETUP_MARGIN_MINUTES = 3

RESTORE_ACTION = "actions/cache/restore@"
SAVE_ACTION = "actions/cache/save@"
#: ``actions/cache`` saves in a post step that runs only when the whole job succeeds, so
#: a failed or cancelled test run would never fill the cache.
COMBINED_CACHE_ACTION = "actions/cache@"

_STEP_OUTPUT = re.compile(r"steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)")
_LITERAL_VERSION = re.compile(r"\d+\.\d+")


def _load() -> dict[str, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _run(step: dict[str, Any]) -> str:
    return str(step.get("run", ""))


def _uses(step: dict[str, Any], action: str) -> bool:
    return str(step.get("uses", "")).startswith(action)


def _is_browser_step(step: dict[str, Any]) -> bool:
    """A step that runs ``playwright install`` or ``playwright install-deps``."""
    return "playwright install" in _run(step)


def _is_download_step(step: dict[str, Any]) -> bool:
    return _is_browser_step(step) and "install-deps" not in _run(step)


def _is_tests_step(step: dict[str, Any]) -> bool:
    return "pytest -m e2e" in _run(step)


def _cap(step: dict[str, Any]) -> int | None:
    value = step.get("timeout-minutes")
    return value if isinstance(value, int) and value > 0 else None


def workflow_problems(workflow: dict[str, Any]) -> list[str]:
    """Every way the install's guarantees are broken in ``workflow``; empty when none."""
    problems: list[str] = []
    job = workflow["jobs"][JOB]
    steps: list[dict[str, Any]] = job["steps"]

    # (a) AC3: the workflow stays read-only, and no job widens it.
    if workflow.get("permissions") != {"contents": "read"}:
        problems.append(f"workflow permissions are {workflow.get('permissions')!r}")
    if "permissions" in job:
        problems.append(f"job permissions are set: {job['permissions']!r}")

    # (b) The system libraries are never installed inside the browser download again.
    for step in steps:
        if "--with-deps" in _run(step):
            problems.append(f"a step passes --with-deps: {_run(step)!r}")

    # (c) Every browser step and the tests step carries its own cap.
    capped = [s for s in steps if _is_browser_step(s) or _is_tests_step(s)]
    if not any(_is_download_step(s) for s in steps):
        problems.append("no step downloads the browser")
    if not any("install-deps" in _run(s) for s in steps):
        problems.append("no step installs the system libraries")
    if not any(_is_tests_step(s) for s in steps):
        problems.append("no step runs the e2e tests")
    for step in capped:
        if _cap(step) is None:
            problems.append(f"no timeout-minutes on: {_run(step)!r}")

    # (d) The step caps fire before the job's, so a hang fails its own step.
    job_cap = job.get("timeout-minutes")
    total = sum(_cap(s) or 0 for s in steps) + SETUP_MARGIN_MINUTES
    if not isinstance(job_cap, int):
        problems.append(f"job timeout-minutes is {job_cap!r}")
    elif total >= job_cap:
        problems.append(
            f"step caps plus a {SETUP_MARGIN_MINUTES}-minute setup margin ({total}) "
            f"reach the job cap ({job_cap})"
        )

    # (e) The cache is restored and saved by the split actions, and every cache-hit
    # condition names the restore step, so a renamed id cannot silently read as a miss.
    restores = [s for s in steps if _uses(s, RESTORE_ACTION)]
    saves = [s for s in steps if _uses(s, SAVE_ACTION)]
    for step in steps:
        if _uses(step, COMBINED_CACHE_ACTION):
            problems.append("actions/cache saves only on job success; use restore + save")
    if len(restores) != 1 or len(saves) != 1:
        problems.append(f"{len(restores)} restore and {len(saves)} save steps, not 1 and 1")
        return problems
    restore, save = restores[0], saves[0]
    restore_id = restore.get("id")
    for step in [*(s for s in steps if _is_download_step(s)), save]:
        condition = str(step.get("if", ""))
        refs = _STEP_OUTPUT.findall(condition)
        if ("cache-hit" not in condition) or any(
            ref != (restore_id, "cache-hit") for ref in refs
        ):
            problems.append(f"{condition!r} does not test the restore step's cache-hit")

    # The save writes exactly what the restore reads.
    for field in ("key", "path"):
        if save.get("with", {}).get(field) != restore.get("with", {}).get(field):
            problems.append(f"save and restore differ in {field}")

    # (f) The key follows the installed Playwright version, never a literal one.
    key = str(restore.get("with", {}).get("key", ""))
    writers = {
        s.get("id")
        for s in steps
        if 'version("playwright")' in _run(s) and "GITHUB_OUTPUT" in _run(s)
    }
    if not any(ref in {(w, "version") for w in writers} for ref in _STEP_OUTPUT.findall(key)):
        problems.append(f"cache key {key!r} does not read the Playwright version step")
    if _LITERAL_VERSION.search(_STEP_OUTPUT.sub("", key)):
        problems.append(f"cache key {key!r} holds a literal version")

    return problems


def test_the_workflow_keeps_the_install_guarantees() -> None:
    assert workflow_problems(_load()) == []


def _step(workflow: dict[str, Any], predicate: Any) -> dict[str, Any]:
    steps: list[dict[str, Any]] = workflow["jobs"][JOB]["steps"]
    matches = [s for s in steps if predicate(s)]
    assert len(matches) == 1
    return matches[0]


def _widen_permissions(w: dict[str, Any]) -> None:
    w["permissions"]["actions"] = "write"


def _restore_with_deps(w: dict[str, Any]) -> None:
    step = _step(w, _is_download_step)
    step["run"] = step["run"].replace("install ", "install --with-deps ", 1)


def _uncap_system_libraries(w: dict[str, Any]) -> None:
    del _step(w, lambda s: "install-deps" in _run(s))["timeout-minutes"]


def _uncap_tests(w: dict[str, Any]) -> None:
    del _step(w, _is_tests_step)["timeout-minutes"]


def _caps_reach_the_job_cap(w: dict[str, Any]) -> None:
    w["jobs"][JOB]["timeout-minutes"] = sum(
        _cap(s) or 0 for s in w["jobs"][JOB]["steps"]
    )


def _rename_the_restore_step(w: dict[str, Any]) -> None:
    _step(w, lambda s: _uses(s, RESTORE_ACTION))["id"] = "renamed"


def _combined_cache_action(w: dict[str, Any]) -> None:
    _step(w, lambda s: _uses(s, RESTORE_ACTION))["uses"] = "actions/cache@v4"


def _save_key_differs(w: dict[str, Any]) -> None:
    save = _step(w, lambda s: _uses(s, SAVE_ACTION))
    save["with"]["key"] = save["with"]["key"] + "-x"


def _literal_version_in_key(w: dict[str, Any]) -> None:
    for step in w["jobs"][JOB]["steps"]:
        if _uses(step, RESTORE_ACTION) or _uses(step, SAVE_ACTION):
            step["with"]["key"] = _STEP_OUTPUT.sub("1.64.1", step["with"]["key"])


def _download_unconditional(w: dict[str, Any]) -> None:
    del _step(w, _is_download_step)["if"]


@pytest.mark.parametrize(
    "mutate",
    [
        _widen_permissions,
        _restore_with_deps,
        _uncap_system_libraries,
        _uncap_tests,
        _caps_reach_the_job_cap,
        _rename_the_restore_step,
        _combined_cache_action,
        _save_key_differs,
        _literal_version_in_key,
        _download_unconditional,
    ],
)
def test_the_guard_can_fail(mutate: Any) -> None:
    workflow = copy.deepcopy(_load())
    mutate(workflow)
    assert workflow_problems(workflow) != []
