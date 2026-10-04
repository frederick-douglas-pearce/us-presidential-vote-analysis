"""``scripts/probe_dashboard.sh`` (#277), run offline against a fake ``curl`` (#294).

The deploy workflow trusts this script to tell a serving dashboard from a broken one, and
the rollback drill in #294 showed that its log said "page carries the API's snapshot: no"
when the check that failed was the canonical link. These tests put a fake ``curl`` (and
a no-op ``sleep``) first on ``PATH`` and pin which responses pass and what each failing
try reports.

The fake answers each kind of request (the API's ``/v1/meta``, the page shell, the
routing callback) from a per-kind list, by call number, repeating the last entry, so a
test can vary responses across tries. It logs every call, and every test asserts the
calls it expected, so a fake that was bypassed fails the test instead of letting it pass
on the exit status alone. The script runs with only ``PATH`` and ``HOME`` from the
developer's environment: a ``BASH_ENV`` that reset ``PATH`` would otherwise send these
requests to the real API.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROBE = REPO / "scripts" / "probe_dashboard.sh"

CANONICAL = "explore.us-presidential-election-center.org"
SNAPSHOT = "71b777de23181c224d80207fb756a9a4541fe18ce70cced28dd8de9d666c20a0"
NEWER = "0f3e5d2c1b0a99887766554433221100ffeeddccbbaa00998877665544332211"
GOOD_SHELL = f'<link rel="canonical" href="https://{CANONICAL}/">'
DRILL_SHELL = '<link rel="canonical" href="https://drill-294.invalid/">'
GOOD_PAGE = f'{{"response": {{"_pages_content": "snapshot {SNAPSHOT}"}}}}'
NO_VERSION_PAGE = '{"response": "no version here"}'

# A shell code of "000", or a page of null, is a request that failed: curl exits 7 and,
# like the real one, leaves its -o file untouched.
FAKE_CURL = """\
import json, os, sys
args = sys.argv[1:]
plan = json.loads(os.environ["FAKE_PLAN"])
state = os.environ["FAKE_STATE"]
if any("/v1/meta" in a for a in args):
    kind = "meta"
elif "--data" in args:
    kind = "page"
else:
    kind = "shell"
counter = os.path.join(state, kind)
n = int(open(counter).read()) if os.path.exists(counter) else 0
with open(counter, "w") as f:
    f.write(str(n + 1))
with open(os.path.join(state, "calls.log"), "a") as f:
    f.write(kind + "\\n")
def pick(key):
    values = plan[key]
    return values[min(n, len(values) - 1)]
if kind == "meta":
    sys.stdout.write('HTTP/2 200\\r\\netag: W/"' + pick("etags") + '"\\r\\n\\r\\n')
elif kind == "page":
    page = pick("pages")
    if page is None:
        sys.exit(7)
    sys.stdout.write(page)
else:
    code = pick("codes")
    if code == "000":
        sys.stdout.write("000")
        sys.exit(7)
    with open(args[args.index("-o") + 1], "w") as f:
        f.write(pick("shells"))
    sys.stdout.write(code)
"""


@dataclass(frozen=True)
class Run:
    result: subprocess.CompletedProcess[str]
    calls: Counter[str]

    @property
    def returncode(self) -> int:
        return self.result.returncode

    @property
    def stdout(self) -> str:
        return self.result.stdout

    def try_lines(self, expected: int) -> list[str]:
        """The failing tries' lines, asserting how many tries ran and the fake served."""
        lines = [line for line in self.stdout.splitlines() if "(try " in line]
        assert len(lines) == expected, self.stdout
        assert self.calls == Counter(
            meta=1 + expected, shell=expected, page=expected
        ), self.calls
        return lines

    def error(self) -> str:
        errors = [line for line in self.stdout.splitlines() if line.startswith("::error::")]
        assert len(errors) == 1, self.stdout
        return errors[0]


@pytest.fixture
def fake_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = tmp_path / "fake_curl.py"
    script.write_text(FAKE_CURL)
    # A /bin/sh wrapper rather than a #! line naming the interpreter, which the kernel
    # splits at a space and truncates past its length limit.
    curl = bin_dir / "curl"
    curl.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} "$@"\n'
    )
    sleep = bin_dir / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    for tool in (curl, sleep):
        tool.chmod(0o755)
    return bin_dir


def probe(
    fake_bin: Path,
    *,
    etags: Sequence[str] = (SNAPSHOT,),
    codes: Sequence[str] = ("200",),
    shells: Sequence[str] = (GOOD_SHELL,),
    pages: Sequence[str | None] = (GOOD_PAGE,),
    tries: int = 2,
) -> Run:
    state = fake_bin.parent / "state"
    state.mkdir()
    plan = {
        "etags": list(etags),
        "codes": list(codes),
        "shells": list(shells),
        "pages": list(pages),
    }
    env = {
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(fake_bin.parent),
        "LC_ALL": "C.UTF-8",
        "FAKE_PLAN": json.dumps(plan),
        "FAKE_STATE": str(state),
    }
    result = subprocess.run(
        ["bash", str(PROBE), "https://v-x-dot-app.example", CANONICAL, str(tries)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    log = state / "calls.log"
    calls = Counter(log.read_text().split()) if log.exists() else Counter()
    return Run(result, calls)


def test_a_serving_dashboard_passes(fake_bin: Path) -> None:
    run = probe(fake_bin)
    assert run.returncode == 0, run.stdout
    assert f"serves snapshot {SNAPSHOT[:12]}… (try 1)" in run.stdout
    assert run.calls == Counter(meta=2, shell=1, page=1)


def test_a_page_carrying_only_the_newer_snapshot_passes(fake_bin: Path) -> None:
    # The API cut over mid-run: the first /v1/meta read names SNAPSHOT, the next NEWER.
    run = probe(fake_bin, etags=(SNAPSHOT, NEWER), pages=(f"snapshot {NEWER}",))
    assert run.returncode == 0, run.stdout
    assert f"serves snapshot {NEWER[:12]}… (try 1)" in run.stdout
    assert run.calls == Counter(meta=2, shell=1, page=1)


def test_a_wrong_canonical_link_is_reported(fake_bin: Path) -> None:
    # Drill 1's shape: shell 200, page carries the snapshot, canonical names another host.
    run = probe(fake_bin, shells=(DRILL_SHELL,))
    assert run.returncode == 1
    for line in run.try_lines(2):
        assert "shell HTTP 200" in line
        assert f"canonical link names {CANONICAL}: no" in line
        assert "page carries the API's snapshot: yes" in line


def test_a_missing_snapshot_is_reported(fake_bin: Path) -> None:
    run = probe(fake_bin, pages=(NO_VERSION_PAGE,))
    assert run.returncode == 1
    for line in run.try_lines(2):
        assert f"canonical link names {CANONICAL}: yes" in line
        assert "page carries the API's snapshot: no" in line


def test_the_degraded_page_fails_even_carrying_the_snapshot(fake_bin: Path) -> None:
    run = probe(fake_bin, pages=(f"{GOOD_PAGE} The API isn't responding",))
    assert run.returncode == 1
    for line in run.try_lines(2):
        assert "page carries the API's snapshot: degraded" in line


def test_a_non_200_shell_fails(fake_bin: Path) -> None:
    run = probe(fake_bin, codes=("503",))
    assert run.returncode == 1
    for line in run.try_lines(2):
        assert "shell HTTP 503" in line


def test_a_failed_shell_request_does_not_report_the_last_trys_shell(fake_bin: Path) -> None:
    # Try 1 fetches a good shell with a 503; try 2's request fails, leaving curl's -o
    # file untouched. Try 2 must not read try 1's shell as its own.
    run = probe(fake_bin, codes=("503", "000"))
    assert run.returncode == 1
    first, second = run.try_lines(2)
    assert f"canonical link names {CANONICAL}: yes" in first
    assert "shell HTTP 000" in second
    assert f"canonical link names {CANONICAL}: unfetched" in second


def test_a_failed_page_request_is_not_a_page_without_the_snapshot(fake_bin: Path) -> None:
    # Try 1's page carries the snapshot but its shell is a 503; try 2's shell is good and
    # its page request fails. Try 2 must not pass on try 1's page.
    run = probe(fake_bin, codes=("503", "200"), pages=(GOOD_PAGE, None))
    assert run.returncode == 1, run.stdout
    first, second = run.try_lines(2)
    assert "page carries the API's snapshot: yes" in first
    assert "page carries the API's snapshot: unfetched" in second


def test_the_final_error_names_the_last_try(fake_bin: Path) -> None:
    run = probe(
        fake_bin, shells=(DRILL_SHELL, GOOD_SHELL), pages=(GOOD_PAGE, NO_VERSION_PAGE)
    )
    assert run.returncode == 1
    run.try_lines(2)
    error = run.error()
    assert "failed the probe in 2 tries" in error
    assert f"canonical link names {CANONICAL}: yes" in error
    assert "page carries the API's snapshot: no" in error
    assert SNAPSHOT[:12] in error
