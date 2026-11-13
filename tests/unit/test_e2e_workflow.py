"""Structural guard for the dashboard's e2e workflow's browser install (#486, D082).

``e2e.yml`` installs the headless shell from a cache keyed on the locked Playwright
version and the runner image, and Chromium's system libraries in a step of their own,
with a time cap on every step from the cache restore on. Each property below fails
silently if it regresses: the run stays green while the cache never fills or never hits,
or a hung package mirror goes back to canceling the whole job instead of failing the step
that hung. So each is checked here, and every negative case shows that its own check, and
only that check, catches its mutation.

Checked: the permissions of the workflow and of every job; no ``--with-deps``; the step
order; a cap on every step from the restore on, and those caps plus
:data:`SETUP_MARGIN_MINUTES` under the job's cap; no ``continue-on-error``; the install
and test steps unconditional; the download and save skipped exactly on a cache hit of the
restore step; the version step writing the version it reads and the runner image; the
key reading both, with no literal version; the save reusing the restore's resolved key;
the cache path. Not checked: step names and the exact cap values, which would only
restate the YAML; and the setup steps before the restore (checkout, uv, Python,
``uv sync``, the version read), which carry no cap of their own.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "e2e.yml"
JOB = "e2e"

#: Minutes the job's cap leaves, over the capped steps' caps, for the uncapped steps: the
#: setup steps before the restore (about 10 s on a healthy run) and the post steps
#: (setup-uv's cache save, checkout's cleanup). The capped steps must fire before the job's
#: cap, or a hang in one of them ends as a canceled job rather than a failed step.
SETUP_MARGIN_MINUTES = 4

#: Playwright's default browser directory on Linux, which the download fills.
CACHE_PATH = "~/.cache/ms-playwright"

RESTORE_ACTION = "actions/cache/restore@"
SAVE_ACTION = "actions/cache/save@"
#: ``actions/cache`` saves in a post step that runs only when the whole job succeeds, so
#: a failed or canceled test run would never fill the cache.
COMBINED_CACHE_ACTION = "actions/cache@"

_STEP_OUTPUT = re.compile(r"steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)")
_EXPRESSION = re.compile(r"\$\{\{.*?\}\}")
_LITERAL_VERSION = re.compile(r"\d+\.\d+")
_VERSION_READ = re.compile(r"(\w+)=\$\(uv run python -c [^\n]*version\(\"playwright\"\)")
_IMAGE_WRITE = re.compile(r'echo "image=\$\{ImageOS(:\?)?\}" >> "\$GITHUB_OUTPUT"')


def _load() -> dict[str, Any]:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _run(step: dict[str, Any]) -> str:
    return str(step.get("run", ""))


def _uses(step: dict[str, Any], action: str) -> bool:
    return str(step.get("uses", "")).startswith(action)


def _norm(expression: object) -> str:
    """An expression without its ``${{ }}`` wrapper and with single spaces."""
    text = str(expression).strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2]
    return " ".join(text.split())


def _cap(step: dict[str, Any]) -> int | None:
    value = step.get("timeout-minutes")
    return value if isinstance(value, int) and value > 0 else None


def _is_version_step(step: dict[str, Any]) -> bool:
    return 'version("playwright")' in _run(step)


def _is_download_step(step: dict[str, Any]) -> bool:
    run = _run(step)
    return "playwright install" in run and "install-deps" not in run


def _is_deps_step(step: dict[str, Any]) -> bool:
    return "playwright install-deps" in _run(step)


def _is_tests_step(step: dict[str, Any]) -> bool:
    return "pytest -m e2e" in _run(step)


KINDS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "version": _is_version_step,
    "restore": lambda s: _uses(s, RESTORE_ACTION),
    "download": _is_download_step,
    "save": lambda s: _uses(s, SAVE_ACTION),
    "install-deps": _is_deps_step,
    "tests": _is_tests_step,
}


def workflow_problems(workflow: dict[str, Any]) -> list[str]:
    """Every way the install's guarantees are broken in ``workflow``; empty when none."""
    problems: list[str] = []
    jobs: dict[str, Any] = workflow["jobs"]
    job = jobs[JOB]
    steps: list[dict[str, Any]] = job["steps"]

    # AC3: the workflow stays read-only, and no job widens it.
    if workflow.get("permissions") != {"contents": "read"}:
        problems.append(f"workflow permissions are {workflow.get('permissions')!r}")
    for name, other in jobs.items():
        if "permissions" in other:
            problems.append(f"job {name} sets permissions: {other['permissions']!r}")

    for step in steps:
        if "--with-deps" in _run(step):
            problems.append(f"a step passes --with-deps: {_run(step)!r}")
        if _uses(step, COMBINED_CACHE_ACTION):
            problems.append("actions/cache saves only on job success; use restore + save")
        if step.get("continue-on-error"):
            problems.append(f"continue-on-error on {step.get('name')!r}")
    for scope in (workflow, job, *steps):
        if "PLAYWRIGHT_BROWSERS_PATH" in (scope.get("env") or {}):
            problems.append("PLAYWRIGHT_BROWSERS_PATH moves the browser off the cache path")

    at: dict[str, int] = {}
    for kind, matches in KINDS.items():
        found = [i for i, s in enumerate(steps) if matches(s)]
        if len(found) != 1:
            problems.append(f"{len(found)} {kind} steps, not 1")
        else:
            at[kind] = found[0]
    if len(at) != len(KINDS):
        return problems
    version, restore, download, save, deps, tests = (
        steps[at[kind]] for kind in KINDS
    )

    if not at["version"] < at["restore"] < at["download"] < at["save"] < at["tests"]:
        problems.append("order: version, restore, download, save, tests")
    if not at["download"] < at["install-deps"] < at["tests"]:
        problems.append("order: download, install-deps, tests")

    # A cap on every step from the restore on, and the caps fire before the job's.
    for step in steps[at["restore"] :]:
        if _cap(step) is None:
            problems.append(f"no timeout-minutes on {step.get('name')!r}")
    job_cap = job.get("timeout-minutes")
    total = sum(_cap(s) or 0 for s in steps) + SETUP_MARGIN_MINUTES
    if not isinstance(job_cap, int) or total >= job_cap:
        problems.append(
            f"step caps plus a {SETUP_MARGIN_MINUTES}-minute margin ({total}) "
            f"reach the job cap ({job_cap!r})"
        )

    for step in (deps, tests):
        if "if" in step:
            problems.append(f"{step.get('name')!r} has an if: {step['if']!r}")

    # Download and save run exactly on a miss of the one restore step.
    skip_on_hit = f"steps.{restore.get('id')}.outputs.cache-hit != 'true'"
    for step in (download, save):
        if _norm(step.get("if", "")) != skip_on_hit:
            problems.append(
                f"{step.get('name')!r} does not skip on a cache hit: {step.get('if')!r}"
            )

    # The version step writes the version it reads, and the runner image.
    run = _run(version)
    read = _VERSION_READ.search(run)
    if read is None or not re.search(
        rf'echo "version=\$\{{{read.group(1)}(:\?)?\}}" >> "\$GITHUB_OUTPUT"', run
    ):
        problems.append("the version step does not write the version it reads")
    if not _IMAGE_WRITE.search(run):
        problems.append("the version step does not write the runner image")

    # The key reads both outputs and the runner, never a literal version.
    restore_with = restore.get("with") or {}
    key = str(restore_with.get("key", ""))
    refs = set(_STEP_OUTPUT.findall(key))
    for output in ("version", "image"):
        if (version.get("id"), output) not in refs:
            problems.append(f"the cache key does not read the version step's {output}")
    for part in ("runner.os", "runner.arch"):
        if part not in key:
            problems.append(f"the cache key does not read {part}")
    if _LITERAL_VERSION.search(_EXPRESSION.sub("", key)):
        problems.append(f"the cache key holds a literal version: {key!r}")

    # The save writes the key the restore resolved, at the browser's path.
    save_with = save.get("with") or {}
    primary = f"steps.{restore.get('id')}.outputs.cache-primary-key"
    if _norm(save_with.get("key", "")) != primary:
        problems.append(f"the save key is not the restore's {primary}")
    for name, with_ in (("restore", restore_with), ("save", save_with)):
        if with_.get("path") != CACHE_PATH:
            problems.append(f"the {name} path is {with_.get('path')!r}")

    return problems


def test_the_workflow_keeps_the_install_guarantees() -> None:
    assert workflow_problems(_load()) == []


# --- negative cases: each mutation trips its own check and nothing else -------------


def _steps(w: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = w["jobs"][JOB]["steps"]
    return steps


def _step(w: dict[str, Any], kind: str) -> dict[str, Any]:
    matches = [s for s in _steps(w) if KINDS[kind](s)]
    assert len(matches) == 1
    return matches[0]


def _move(w: dict[str, Any], kind: str, before: str | None) -> None:
    """Move the ``kind`` step to just before the ``before`` step (or to the end)."""
    steps = _steps(w)
    step = _step(w, kind)
    steps.remove(step)
    index = len(steps) if before is None else steps.index(_step(w, before))
    steps.insert(index, step)


def _widen_workflow_permissions(w: dict[str, Any]) -> None:
    w["permissions"]["actions"] = "write"


def _second_job_writes(w: dict[str, Any]) -> None:
    w["jobs"]["other"] = {"permissions": {"contents": "write"}, "steps": []}


def _with_deps(w: dict[str, Any]) -> None:
    step = _step(w, "download")
    step["run"] = step["run"].replace("install ", "install --with-deps ", 1)


def _combined_cache_step(w: dict[str, Any]) -> None:
    _steps(w).append({"uses": "actions/cache@v4", "timeout-minutes": 1})


def _continue_on_error(w: dict[str, Any]) -> None:
    _step(w, "install-deps")["continue-on-error"] = True


def _browsers_path(w: dict[str, Any]) -> None:
    w["jobs"][JOB]["env"] = {"PLAYWRIGHT_BROWSERS_PATH": "/opt/browsers"}


def _restore_after_download(w: dict[str, Any]) -> None:
    _move(w, "restore", "save")


def _save_after_tests(w: dict[str, Any]) -> None:
    _move(w, "save", None)


def _version_after_restore(w: dict[str, Any]) -> None:
    _move(w, "version", "download")


def _deps_before_download(w: dict[str, Any]) -> None:
    _move(w, "install-deps", "download")


def _uncap_restore(w: dict[str, Any]) -> None:
    del _step(w, "restore")["timeout-minutes"]


def _uncap_deps(w: dict[str, Any]) -> None:
    del _step(w, "install-deps")["timeout-minutes"]


def _caps_reach_the_job_cap(w: dict[str, Any]) -> None:
    job = w["jobs"][JOB]
    job["timeout-minutes"] = sum(_cap(s) or 0 for s in job["steps"]) + (
        SETUP_MARGIN_MINUTES
    )


def _deps_conditional(w: dict[str, Any]) -> None:
    _step(w, "install-deps")["if"] = "false"


def _save_on_hit(w: dict[str, Any]) -> None:
    step = _step(w, "save")
    step["if"] = step["if"].replace("!=", "==")


def _download_ref_less(w: dict[str, Any]) -> None:
    _step(w, "download")["if"] = "cache-hit != 'true'"


def _download_unconditional(w: dict[str, Any]) -> None:
    del _step(w, "download")["if"]


def _rename_restore(w: dict[str, Any]) -> None:
    _step(w, "restore")["id"] = "renamed"


def _version_written_literally(w: dict[str, Any]) -> None:
    step = _step(w, "version")
    step["run"] = re.sub(r'echo "version=[^"]*"', 'echo "version=1.64.1"', step["run"])


def _version_output_renamed(w: dict[str, Any]) -> None:
    step = _step(w, "version")
    step["run"] = step["run"].replace('echo "version=', 'echo "pw_version=')


def _image_not_written(w: dict[str, Any]) -> None:
    step = _step(w, "version")
    step["run"] = "\n".join(
        line for line in step["run"].splitlines() if "image=" not in line
    )


def _image_dropped_from_key(w: dict[str, Any]) -> None:
    with_ = _step(w, "restore")["with"]
    with_["key"] = with_["key"].replace("${{ steps.playwright.outputs.image }}-", "")


def _literal_version_in_key(w: dict[str, Any]) -> None:
    _step(w, "restore")["with"]["key"] += "-1.49"


def _save_key_copied(w: dict[str, Any]) -> None:
    _step(w, "save")["with"]["key"] = _step(w, "restore")["with"]["key"]


def _path_moved(w: dict[str, Any]) -> None:
    for kind in ("restore", "save"):
        _step(w, kind)["with"]["path"] = "~/.cache/elsewhere"


MUTATIONS: list[tuple[Callable[[dict[str, Any]], None], tuple[str, ...]]] = [
    (_widen_workflow_permissions, ("workflow permissions",)),
    (_second_job_writes, ("job other sets permissions",)),
    (_with_deps, ("--with-deps",)),
    (_combined_cache_step, ("saves only on job success",)),
    (_continue_on_error, ("continue-on-error",)),
    (_browsers_path, ("PLAYWRIGHT_BROWSERS_PATH",)),
    (_restore_after_download, ("order: version, restore",)),
    (_save_after_tests, ("order: version, restore",)),
    # Also lands the uncapped version step inside the capped run of steps.
    (_version_after_restore, ("no timeout-minutes", "order: version, restore")),
    (_deps_before_download, ("order: download, install-deps",)),
    (_uncap_restore, ("no timeout-minutes",)),
    (_uncap_deps, ("no timeout-minutes",)),
    (_caps_reach_the_job_cap, ("reach the job cap",)),
    (_deps_conditional, ("has an if",)),
    (_save_on_hit, ("does not skip on a cache hit",)),
    (_download_ref_less, ("does not skip on a cache hit",)),
    (_download_unconditional, ("does not skip on a cache hit",)),
    (
        _rename_restore,
        ("does not skip on a cache hit", "does not skip on a cache hit", "save key"),
    ),
    (_version_written_literally, ("does not write the version it reads",)),
    (_version_output_renamed, ("does not write the version it reads",)),
    (_image_not_written, ("does not write the runner image",)),
    (_image_dropped_from_key, ("does not read the version step's image",)),
    (_literal_version_in_key, ("literal version",)),
    (_save_key_copied, ("save key",)),
    (_path_moved, ("restore path", "save path")),
]


@pytest.mark.parametrize(
    ("mutate", "expected"), MUTATIONS, ids=[m.__name__ for m, _ in MUTATIONS]
)
def test_each_check_catches_its_own_mutation(
    mutate: Callable[[dict[str, Any]], None], expected: tuple[str, ...]
) -> None:
    workflow = copy.deepcopy(_load())
    mutate(workflow)
    problems = workflow_problems(workflow)
    assert len(problems) == len(expected), problems
    for problem, fragment in zip(sorted(problems), sorted(expected), strict=True):
        assert fragment in problem, problems
