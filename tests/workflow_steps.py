"""Run a workflow step's shell, or a deploy script, offline against a fake ``curl``.

Shared by the tests that run GitHub workflow shell as written (#526, from #440's review):
``tests/unit/test_dashboard_canary.py`` (``api-canary.yml``), ``test_deploy_summary_check.py``
(``deploy.yml``) and ``test_dashboard_routing_check.py`` (the script
``deploy-dashboard.yml`` runs).

- ``step_run`` pulls one step's ``run:`` text out of a workflow with the YAML parser,
  unchanged, and refuses a step that sets ``shell:``: the tests run the text under
  ``bash -e``, which is what GitHub runs a step with no ``shell:`` under.
- ``line_start`` and ``if_block`` cut a block out of that text by a marker.
- ``CURL_STUB`` is one fake ``curl`` (and a no-op ``sleep``), written in bash. It is used
  two ways: prepended to a step's text, where it defines shell functions, or written by
  ``write_stub_bin`` as executables first on ``PATH``, for a script that runs in a process
  of its own.
- ``run_bash`` runs either with ``TMPDIR`` set to the test's own directory, so no
  ``mktemp`` file lands in the system temp dir, and returns the calls the fake received.

The fake answers by URL (its last argument) from a routes file (``routes_file``). Each
route names an exact URL, or ``*`` for any URL no route names; a URL with no route
answers 599. A route's codes are a comma-separated list, the first for the first call to
that URL, the next for the second, the last repeating, so a test can make a request fail
and then recover. A code of ``fail`` is a connection error: exit 7, with
``%{http_code}`` written as 000 and no file touched. Otherwise the fake writes the route's
body to ``-o``, ``HTTP/2 <code>`` and the route's header lines to ``-D``, and the code to
``-w``. Every call goes to ``$CURL_LOG`` as one line, each argument ended by a unit
separator (0x1f), so an empty argument shows as one.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

import yaml

#: The fake ``curl`` and ``sleep``, as bash functions.
CURL_STUB = """\
sleep() { :; }
curl() {
  { printf '%s\\x1f' "$@"; printf '\\n'; } >> "$CURL_LOG"
  local url="${@: -1}" out="" hdr="" fmt="" codes="599" body="-" head="-"
  local r_url r_codes r_body r_head n code
  while [ $# -gt 0 ]; do
    case "$1" in -o) out="$2"; shift;; -D) hdr="$2"; shift;; -w) fmt="$2"; shift;; esac
    shift
  done
  while IFS=$'\\t' read -r r_url r_codes r_body r_head; do
    if [ "$r_url" = "$url" ]; then
      codes="$r_codes"; body="$r_body"; head="$r_head"; break
    fi
    if [ "$r_url" = "*" ]; then
      codes="$r_codes"; body="$r_body"; head="$r_head"
    fi
  done < "$STUB_ROUTES"
  n=$(awk -F '\\x1f' -v u="$url" '$(NF-1) == u' "$CURL_LOG" | wc -l)
  IFS=, read -r -a codes <<< "$codes"
  [ "$n" -gt "${#codes[@]}" ] && n=${#codes[@]}
  code="${codes[$((n - 1))]}"
  if [ "$code" = fail ]; then [ -n "$fmt" ] && printf 000; return 7; fi
  if [ -n "$out" ]; then
    if [ "$body" = - ]; then : > "$out"; else cat "$body" > "$out"; fi
  fi
  if [ -n "$hdr" ]; then
    { printf 'HTTP/2 %s\\r\\n' "$code"; [ "$head" = - ] || cat "$head"; } > "$hdr"
  fi
  [ -n "$fmt" ] && printf '%s' "$code"
  return 0
}
"""


class Route(NamedTuple):
    """One answer of the fake ``curl``: ``codes`` is ``"404"``, ``"fail,404"``, …"""

    url: str
    codes: str
    body: str | None = None
    headers: str | None = None


def routes_file(directory: Path, routes: Sequence[Route]) -> Path:
    """Write ``routes`` (and each body and header text) under ``directory``."""
    lines = []
    for i, route in enumerate(routes):
        assert "\t" not in route.url and "\n" not in route.url, route.url
        files = []
        for kind, text in (("body", route.body), ("headers", route.headers)):
            if text is None:
                files.append("-")
                continue
            path = directory / f"route-{i}.{kind}"
            path.write_text(text, encoding="utf-8")
            files.append(str(path))
        lines.append("\t".join([route.url, route.codes, *files]))
    path = directory / "routes.tsv"
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def write_stub_bin(directory: Path) -> Path:
    """``curl`` and ``sleep`` executables in ``directory/bin``, for a script's ``PATH``."""
    bin_dir = directory / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(f'#!/usr/bin/env bash\n{CURL_STUB}curl "$@"\n', encoding="utf-8")
    sleep = bin_dir / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for tool in (curl, sleep):
        tool.chmod(0o755)
    return bin_dir


def step_run(workflow: Path, name: str) -> str:
    """The ``run:`` text of the one step named ``name`` in ``workflow``."""
    parsed = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    steps = [s for job in parsed["jobs"].values() for s in job["steps"]]
    (step,) = [s for s in steps if s.get("name") == name]
    assert "shell" not in step, "the block is tested under bash -e, GitHub's default"
    run: str = step["run"]
    return run


def line_start(text: str, marker: str) -> int:
    """The offset of the start of the line holding ``marker``."""
    return text.rindex("\n", 0, text.index(marker)) + 1


def if_block(text: str, marker: str) -> str:
    """An ``if`` block, from the line holding ``marker`` to its own ``fi``."""
    lines = text[line_start(text, marker) :].splitlines(keepends=True)
    indent = len(lines[0]) - len(lines[0].lstrip())
    end = next(
        i for i, line in enumerate(lines) if line.rstrip() == " " * indent + "fi"
    )
    return "".join(lines[: end + 1])


def parse_call_log(log: Path) -> list[list[str]]:
    """Each call the fake ``curl`` received, as its argument list."""
    return [
        line.split("\x1f")[:-1] for line in log.read_text(encoding="utf-8").splitlines()
    ]


def run_bash(
    argv: Sequence[str],
    tmp_path: Path,
    routes: Sequence[Route],
    env: Mapping[str, str] | None = None,
    *,
    bin_dir: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    """Run ``argv`` with the fake's routes, ``TMPDIR`` in ``tmp_path`` and a plain
    ``PATH`` (``bin_dir`` first when given), returning the result and the calls."""
    log = tmp_path / "curl.log"
    log.write_text("", encoding="utf-8")
    path = "/usr/bin:/bin"
    if bin_dir is not None:
        path = f"{bin_dir}{os.pathsep}{path}"
    full_env = {
        "PATH": path,
        "HOME": str(tmp_path),
        "LC_ALL": "C.UTF-8",
        "TMPDIR": str(tmp_path),
        "CURL_LOG": str(log),
        "STUB_ROUTES": str(routes_file(tmp_path, routes)),
        **(env or {}),
    }
    result = subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=60,
        check=False,
    )
    return result, parse_call_log(log)
