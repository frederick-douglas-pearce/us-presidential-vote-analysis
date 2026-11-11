"""The deploy smoke step's ``/v1/elections/summary`` check, run as written (#431).

``.github/workflows/deploy.yml``'s post-deploy smoke step requests the canonical
``/v1/elections/summary`` after the purge and checks the response with an inline shell
block and a Python heredoc. Nothing ran that block before a real deploy, and code review
found it ending the step before its error messages printed: the step runs under
``bash -e``, as GitHub runs every ``run:`` step.

These tests pull that block out of the workflow with the YAML parser, unchanged, and run
it under ``bash -e`` with ``curl``, ``python`` and ``sleep`` stubbed, so what they pin is
the shell the workflow will run, not a copy of it. ``safe()`` comes out of the same step.
Offline: the stubbed ``curl`` serves a local file.
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
_START = "sum_hdr=$(mktemp)"
_END = 'if [ "$sum_ok" -ne 1 ]; then'
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


def _summary_block() -> tuple[str, str]:
    """The step's ``safe()`` definition and its summary check, through its last ``fi``."""
    run = _smoke_script()
    safe_line = next(line for line in run.splitlines() if line.strip().startswith("safe()"))
    start = _line_start(run, _START)
    end = _line_start(run, _END)
    tail = run[end:].splitlines(keepends=True)[:4]  # the not-serving check: if/echo/exit/fi
    assert tail[-1].strip() == "fi", tail
    return safe_line.strip(), run[start:end] + "".join(tail)


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


def _run(
    tmp_path: Path, body: str, *, etag: str = _VERSION, code: str = "200"
) -> subprocess.CompletedProcess[str]:
    safe, block = _summary_block()
    script = tmp_path / "smoke.sh"
    script.write_text(
        f"{_STUBS}{safe}\nset -uo pipefail\n{block}echo 'END REACHED'\n",
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
    safe, block = _summary_block()
    assert safe.startswith("safe()")
    assert "/v1/elections/summary" in block
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
        "::error::/v1/elections/summary is inconsistent (rows, elections: '2 1')"
        in result.stdout
    )
    assert "END REACHED" not in result.stdout


def test_a_count_that_disagrees_with_data_is_inconsistent(tmp_path: Path) -> None:
    body = json.loads(_body([2016, 2020], [2016, 2020]))
    body["meta"]["count"] = 5
    result = _run(tmp_path, json.dumps(body))
    assert result.returncode == 1
    assert "is inconsistent (rows, elections: '2 2')" in result.stdout


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


def test_a_weak_etag_for_this_snapshot_passes(tmp_path: Path) -> None:
    """Cloudflare rewrites the strong tag to ``W/"…"``; the stub always serves it weak."""
    result = _run(tmp_path, _body([2016], [2016]), etag=_VERSION)
    assert result.returncode == 0, result.stdout + result.stderr
