"""The deploy smoke step's all-years route checks, run as written (#431, #428).

``.github/workflows/deploy.yml``'s post-deploy smoke step requests the canonical
``/v1/elections/summary`` (#431) and ``/v1/elections/states`` (#428, D098) after the purge.
One shell function, ``probe_json``, fetches each and runs a per-route Python checker
written to a file by a heredoc. Nothing ran the #431 block before a real deploy, and code
review found it ending the step before its error messages printed: the step runs under
``bash -e``, as GitHub runs every ``run:`` step.

These tests pull ``safe()``, ``probe_json`` and each route's section (its checker and its
call) out of the workflow with the YAML parser, unchanged, and run them under ``bash -e``
with ``curl``, ``python`` and ``sleep`` stubbed, so what they pin is the shell the
workflow will run, not a copy of it. Offline: the stubbed ``curl`` serves a local file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy.yml"
_FUNCTION_START = "probe_json() {"
#: Each route's section: its checker heredoc and its probe_json call, ending at the
#: call's ``|| exit 1``.
_SECTIONS = {
    "summary": "summary_check=$(mktemp)",
    "states": "states_check=$(mktemp)",
}
_VERSION = "abc123snapshot"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _smoke_script() -> str:
    workflow = yaml.safe_load(_WORKFLOW.read_text())
    steps = [s for job in workflow["jobs"].values() for s in job["steps"]]
    (step,) = [s for s in steps if s.get("name") == "Post-deploy smoke test"]
    assert "shell" not in step, "the block is tested under bash -e, GitHub's default"
    run: str = step["run"]
    return run


def _line_start(text: str, marker: str) -> int:
    return text.rindex("\n", 0, text.index(marker)) + 1


def _probe_block(route: str = "summary") -> tuple[str, str]:
    """The step's ``safe()`` line, and ``probe_json`` plus one route's section."""
    run = _smoke_script()
    safe_line = next(line for line in run.splitlines() if line.strip().startswith("safe()"))
    start = _line_start(run, _FUNCTION_START)
    lines = run[start:].splitlines(keepends=True)
    indent = len(lines[0]) - len(lines[0].lstrip())
    close = next(
        i for i, line in enumerate(lines) if i and line.rstrip() == " " * indent + "}"
    )
    function = "".join(lines[: close + 1])
    section_start = _line_start(run, _SECTIONS[route])
    section_lines = run[section_start:].splitlines(keepends=True)
    end = next(i for i, line in enumerate(section_lines) if "|| exit 1" in line)
    return safe_line.strip(), function + "".join(section_lines[: end + 1])


_STUBS = """\
python() { "$PY" "$@"; }
sleep() { :; }
curl() {
  local out="" hdr=""
  while [ $# -gt 0 ]; do
    case "$1" in -o) out="$2"; shift;; -D) hdr="$2"; shift;; esac
    shift
  done
  cp "$BODY" "$out"
  printf 'HTTP/2 %s\\r\\netag: W/"%s"\\r\\n' "$CODE" "$ETAG" > "$hdr"
  printf '%s' "$CODE"
}
"""


#: ``curl`` failing outright, as on a connection error: exit 7, ``%{http_code}`` = 000.
_FAILING_CURL = _STUBS.replace(
    "curl() {\n", 'curl() {\n  if [ "$CODE" = fail ]; then printf 000; return 7; fi\n'
)

#: The header name in HTTP/1.1 casing, which a fallback from HTTP/2 would send.
_TITLE_CASE_ETAG = _STUBS.replace("\\r\\netag:", "\\r\\nETag:")


def _run(
    tmp_path: Path,
    body: str,
    *,
    etag: str = _VERSION,
    code: str = "200",
    stubs: str = _STUBS,
    route: str = "summary",
) -> subprocess.CompletedProcess[str]:
    safe, block = _probe_block(route)
    script = tmp_path / "smoke.sh"
    script.write_text(
        f"{stubs}{safe}\nset -uo pipefail\n{block}echo 'END REACHED'\n",
        encoding="utf-8",
    )
    body_file = tmp_path / "body.json"
    body_file.write_text(body, encoding="utf-8")
    env = {
        "PATH": "/usr/bin:/bin",
        "PY": sys.executable,
        "BODY": str(body_file),
        "CODE": code,
        "ETAG": etag,
        "CF_HOST": "api.example.test",
        "SNAPSHOT_VERSION": _VERSION,
    }
    return subprocess.run(
        ["bash", "-e", str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def _body(years_in_data: list[int], years_in_elections: list[int]) -> str:
    data = [{"year": y, "candidate_slug": f"c-{i}"} for i, y in enumerate(years_in_data)]
    elections = [{"year": y} for y in years_in_elections]
    return json.dumps(
        {"data": data, "elections": elections, "meta": {"count": len(data)}}
    )


def test_the_block_is_found_in_the_workflow() -> None:
    for route, path in (
        ("summary", "/v1/elections/summary"),
        ("states", "/v1/elections/states"),
    ):
        safe, block = _probe_block(route)
        assert safe.startswith("safe()")
        assert block.lstrip().startswith("probe_json() {")
        assert f'probe_json "{path}"' in block
        assert "<<'PY'" in block


def test_a_consistent_body_passes(tmp_path: Path) -> None:
    result = _run(tmp_path, _body([2016, 2016, 2020], [2016, 2020]))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "✓ /v1/elections/summary: 200, this snapshot, 3 rows over 2 elections" in (
        result.stdout
    )
    assert "END REACHED" in result.stdout
    assert "::error::" not in result.stdout


def test_an_inconsistent_body_fails_with_its_own_message(tmp_path: Path) -> None:
    """Under ``bash -e`` the message must still print (#431 round 2)."""
    result = _run(tmp_path, _body([2016, 2020], [2016]))
    assert result.returncode == 1
    assert (
        "::error::/v1/elections/summary is inconsistent ('2 rows over 1 elections') — "
        "meta.count, data and elections disagree" in result.stdout
    )
    assert "END REACHED" not in result.stdout
    # It fails at once: a bad body is a real answer, never retried.
    assert "retrying" not in result.stdout
    assert result.stdout.count("::error::") == 1


def test_an_empty_body_is_inconsistent(tmp_path: Path) -> None:
    result = _run(tmp_path, _body([], []))
    assert result.returncode == 1
    assert "is inconsistent ('0 rows over 0 elections')" in result.stdout


def test_a_year_twice_in_elections_is_inconsistent(tmp_path: Path) -> None:
    result = _run(tmp_path, _body([2016], [2016, 2016]))
    assert result.returncode == 1
    assert "is inconsistent ('1 rows over 2 elections')" in result.stdout


def test_a_count_that_disagrees_with_data_is_inconsistent(tmp_path: Path) -> None:
    body = json.loads(_body([2016, 2020], [2016, 2020]))
    body["meta"]["count"] = 5
    result = _run(tmp_path, json.dumps(body))
    assert result.returncode == 1
    assert "is inconsistent ('2 rows over 2 elections')" in result.stdout


def test_a_hostile_body_is_unparseable_and_never_printed(tmp_path: Path) -> None:
    """A non-integer year carrying a workflow command fails without echoing the body."""
    body = json.loads(_body([2016], [2016]))
    body["data"][0]["year"] = "##[error]planted-by-the-edge"
    result = _run(tmp_path, json.dumps(body))
    assert result.returncode == 1
    assert "not the expected JSON shape (unparseable)" in result.stdout
    for stream in (result.stdout, result.stderr):
        assert "planted-by-the-edge" not in stream
        assert "##[" not in stream


def test_another_snapshots_etag_is_retried_then_refused(tmp_path: Path) -> None:
    """A weak ETag naming another snapshot never passes, whatever the body says."""
    result = _run(tmp_path, _body([2016], [2016]), etag="some-older-snapshot")
    assert result.returncode == 1
    assert result.stdout.count("retrying") == 5
    assert "is not serving this deploy's snapshot" in result.stdout


def test_a_hostile_etag_is_defused_in_every_message(tmp_path: Path) -> None:
    """An ETag carrying a workflow command reaches the log only through ``safe()``."""
    result = _run(tmp_path, _body([2016], [2016]), etag="##[error]planted")
    assert result.returncode == 1
    assert result.stdout.count("retrying") == 5
    assert "##[" not in result.stdout
    assert "# [error]planted" in result.stdout


def test_a_long_etag_is_cut_to_200_characters(tmp_path: Path) -> None:
    result = _run(tmp_path, _body([2016], [2016]), etag="x" * 400)
    assert result.returncode == 1
    assert "x" * 200 in result.stdout
    assert "x" * 201 not in result.stdout


def test_a_title_case_etag_header_is_read(tmp_path: Path) -> None:
    assert "ETag:" in _TITLE_CASE_ETAG
    result = _run(tmp_path, _body([2016], [2016]), stubs=_TITLE_CASE_ETAG)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_failing_curl_is_retried_not_fatal(tmp_path: Path) -> None:
    """Under ``bash -e``, a curl error must fall back to 000 and retry, never end the
    step silently."""
    result = _run(tmp_path, _body([2016], [2016]), code="fail", stubs=_FAILING_CURL)
    assert result.returncode == 1
    assert result.stdout.count("HTTP 000, ETag 'none', want 200") == 5
    assert result.stdout.count("retrying") == 5
    assert "is not serving this deploy's snapshot (last: HTTP 000" in result.stdout


def test_a_weak_etag_for_this_snapshot_passes(tmp_path: Path) -> None:
    """Cloudflare rewrites the strong tag to ``W/"…"``; the stub always serves it weak."""
    result = _run(tmp_path, _body([2016], [2016]), etag=_VERSION)
    assert result.returncode == 0, result.stdout + result.stderr


# --- /v1/elections/states (#428) ----------------------------------------------


def _states_body(keys: list[tuple[int, str]], count: int | None = None) -> str:
    data = [{"year": y, "state": st} for y, st in keys]
    return json.dumps(
        {"data": data, "meta": {"count": len(data) if count is None else count}}
    )


def test_a_consistent_states_body_passes(tmp_path: Path) -> None:
    body = _states_body([(2016, "Texas"), (2016, "Utah"), (2020, "Texas")])
    result = _run(tmp_path, body, route="states")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "✓ /v1/elections/states: 200, this snapshot, 3 rows over 2 elections" in (
        result.stdout
    )
    assert "END REACHED" in result.stdout


def test_a_repeated_state_is_inconsistent(tmp_path: Path) -> None:
    body = _states_body([(2020, "Texas"), (2020, "Texas")])
    result = _run(tmp_path, body, route="states")
    assert result.returncode == 1
    assert (
        "::error::/v1/elections/states is inconsistent ('2 rows over 1 elections') — "
        "meta.count and data disagree, or a (year, state) repeats" in result.stdout
    )
    assert "retrying" not in result.stdout
    assert "END REACHED" not in result.stdout


def test_a_states_count_that_disagrees_is_inconsistent(tmp_path: Path) -> None:
    result = _run(tmp_path, _states_body([(2020, "Texas")], count=2), route="states")
    assert result.returncode == 1
    assert "is inconsistent ('1 rows over 1 elections')" in result.stdout


def test_an_empty_states_body_is_inconsistent(tmp_path: Path) -> None:
    result = _run(tmp_path, _states_body([]), route="states")
    assert result.returncode == 1
    assert "is inconsistent ('0 rows over 0 elections')" in result.stdout


def test_a_hostile_states_body_is_unparseable_and_never_printed(tmp_path: Path) -> None:
    body = json.loads(_states_body([(2020, "Texas")]))
    body["data"][0]["year"] = "##[error]planted-by-the-edge"
    result = _run(tmp_path, json.dumps(body), route="states")
    assert result.returncode == 1
    assert "not the expected JSON shape (unparseable)" in result.stdout
    for stream in (result.stdout, result.stderr):
        assert "planted-by-the-edge" not in stream


def test_the_states_probe_refuses_another_snapshots_etag(tmp_path: Path) -> None:
    body = _states_body([(2020, "Texas")])
    result = _run(tmp_path, body, etag="older", route="states")
    assert result.returncode == 1
    assert result.stdout.count("retrying") == 5
    assert "/v1/elections/states is not serving this deploy's snapshot" in result.stdout
