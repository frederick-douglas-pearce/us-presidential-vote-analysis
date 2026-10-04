"""``scripts/probe_dashboard.sh`` (#277), run offline against a fake ``curl`` (#294).

The deploy workflow trusts this script to tell a serving dashboard from a broken one, and
the rollback drill in #294 showed that its log said "page carries the API's snapshot: no"
when the check that failed was the canonical link. These tests put a fake ``curl`` (and
a no-op ``sleep``) first on ``PATH``, so the script runs with no network, and pin both
halves: which responses pass, and which condition each failing line names.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROBE = REPO / "scripts" / "probe_dashboard.sh"

CANONICAL = "explore.us-presidential-election-center.org"
SNAPSHOT = "71b777de23181c224d80207fb756a9a4541fe18ce70cced28dd8de9d666c20a0"
GOOD_SHELL = f'<link rel="canonical" href="https://{CANONICAL}/">'
GOOD_PAGE = f'{{"response": {{"_pages_content": "snapshot {SNAPSHOT}"}}}}'

# Answers the script's three kinds of request from FAKE_* variables: the API's
# /v1/meta headers (-D -), the routing callback (--data), and the page shell (-o).
FAKE_CURL = """\
import os, sys
args = sys.argv[1:]
if any("/v1/meta" in a for a in args):
    sys.stdout.write('HTTP/2 200\\r\\netag: W/"' + os.environ["FAKE_ETAG"] + '"\\r\\n\\r\\n')
elif "--data" in args:
    sys.stdout.write(os.environ["FAKE_PAGE"])
else:
    with open(args[args.index("-o") + 1], "w") as f:
        f.write(os.environ["FAKE_SHELL"])
    sys.stdout.write(os.environ["FAKE_CODE"])
"""


@pytest.fixture
def fake_bin(tmp_path: Path) -> Path:
    curl = tmp_path / "curl"
    curl.write_text(f"#!{sys.executable}\n{FAKE_CURL}")
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    for tool in (curl, sleep):
        tool.chmod(0o755)
    return tmp_path


def probe(
    fake_bin: Path,
    *,
    code: str = "200",
    shell: str = GOOD_SHELL,
    page: str = GOOD_PAGE,
    tries: int = 2,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "FAKE_ETAG": SNAPSHOT,
        "FAKE_CODE": code,
        "FAKE_SHELL": shell,
        "FAKE_PAGE": page,
    }
    return subprocess.run(
        ["bash", str(PROBE), "https://v-x-dot-app.example", CANONICAL, str(tries)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def try_lines(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in result.stdout.splitlines() if "(try " in line]


def test_a_serving_dashboard_passes(fake_bin: Path) -> None:
    result = probe(fake_bin)
    assert result.returncode == 0, result.stdout
    assert f"serves snapshot {SNAPSHOT[:12]}" in result.stdout


def test_a_wrong_canonical_link_is_named_as_the_failure(fake_bin: Path) -> None:
    # Drill 1's shape: shell 200, page carries the snapshot, canonical names another host.
    result = probe(fake_bin, shell='<link rel="canonical" href="https://drill-294.invalid/">')
    assert result.returncode == 1
    lines = try_lines(result)
    assert len(lines) == 2
    for line in lines:
        assert "shell HTTP 200" in line
        assert f"canonical link names {CANONICAL}: no" in line
        assert "page carries the API's snapshot: yes" in line


def test_a_missing_snapshot_is_named_as_the_failure(fake_bin: Path) -> None:
    result = probe(fake_bin, page='{"response": "no version here"}')
    assert result.returncode == 1
    for line in try_lines(result):
        assert f"canonical link names {CANONICAL}: yes" in line
        assert "page carries the API's snapshot: no" in line


def test_the_degraded_page_fails_even_carrying_the_snapshot(fake_bin: Path) -> None:
    result = probe(fake_bin, page=f"{GOOD_PAGE} The API isn't responding")
    assert result.returncode == 1
    for line in try_lines(result):
        assert "page carries the API's snapshot: degraded" in line


def test_a_non_200_shell_fails(fake_bin: Path) -> None:
    result = probe(fake_bin, code="503")
    assert result.returncode == 1
    for line in try_lines(result):
        assert "shell HTTP 503" in line


def test_the_final_error_names_the_last_try(fake_bin: Path) -> None:
    result = probe(fake_bin, shell="<html></html>", tries=1)
    assert result.returncode == 1
    error = [line for line in result.stdout.splitlines() if line.startswith("::error::")]
    assert len(error) == 1
    assert "failed the probe in 1 tries" in error[0]
    assert f"canonical link names {CANONICAL}: no" in error[0]
    assert SNAPSHOT[:12] in error[0]
