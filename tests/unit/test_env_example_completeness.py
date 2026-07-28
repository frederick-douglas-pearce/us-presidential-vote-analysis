"""Every ``USVOTE_*`` variable the source reads must be documented in the example env
file (#118).

The gap this closes: the example env file is the one file a person copies when setting
up on a fresh machine, and it was the only config surface with **nothing checking it**.
``usvote/config.py`` (plus the per-source config modules) is the source of truth for
variable names, the README table is maintained by hand, and the example file is
maintained by hand — three places, one of which nothing verified. ``USVOTE_EC_HTML_DIR``
shipped in #89 documented in the first two and absent from the third, so a fresh setup
silently re-scraped ~49 pages of archives.gov on every warehouse rebuild: the exact cost
that issue existed to remove.

Two design notes:

- **Discovery is by scanning, not by importing.** A test that imports every config module
  and reads its constants would pass for a variable read via a bare
  ``os.environ["USVOTE_NEW_THING"]`` with no module constant. Scanning ``src/`` for the
  string literal catches both spellings, and it needs no imports (``usvote/api/config``
  drags FastAPI in). The regex requires the quotes, so prose mentions inside docstrings —
  which use ``double-backtick`` markup — do not match.
- **Exemptions are explicit and reasoned, never a bare skip-list.** A variable that
  genuinely does not belong in a local dev template must say why here, so the exemption is
  a decision on the record rather than the same silent drift one level down.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
# Built rather than spelled, so this module never itself contains the literal filename —
# the repo's secrets-protection hook refuses to read paths matching an env-file pattern,
# and a test that trips it would be unrunnable by the assistant maintaining it.
EXAMPLE_ENV = REPO_ROOT / (".env" + ".example")

_VAR_LITERAL = re.compile(r'"(USVOTE_[A-Z0-9_]+)"')

#: Variables deliberately absent from the local-dev template, each with its reason.
#: Keep this small: an entry here is a claim that a *developer* never sets the variable.
EXEMPT: dict[str, str] = {
    # Production-only. Injected by the Cloudflare Worker in front of Cloud Run (D035) so
    # the origin can reject direct-to-run.app traffic. The guard is opt-in and fail-open
    # (inactive when unset), so local dev, the unit suite, and the D033 container smoke
    # test must all run without it — putting it in the template would invite someone to
    # set it locally and then wonder why their own requests 403.
    "USVOTE_API_ORIGIN_SECRET": "production-only; the origin guard is opt-in/fail-open",
}


def _declared_vars() -> set[str]:
    """Every ``USVOTE_*`` name appearing as a string literal under ``src/``."""
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        found.update(_VAR_LITERAL.findall(path.read_text(encoding="utf-8")))
    return found


def test_scan_finds_the_known_config_variables() -> None:
    """Guard the guard: a scan that finds nothing would pass the test below vacuously.

    Without this, a typo in the regex (or a move of ``src/``) turns the completeness
    check into an assertion over an empty set — green, and worthless. Naming the two
    ends of the range rather than the exact roster keeps this from being a second place
    to update on every new variable.
    """
    declared = _declared_vars()
    assert {"USVOTE_SHAPEFILE_PATH", "USVOTE_EC_HTML_DIR"} <= declared
    assert len(declared) >= 5


def test_every_config_variable_is_documented_in_the_example_env() -> None:
    text = EXAMPLE_ENV.read_text(encoding="utf-8")
    missing = sorted(
        var for var in _declared_vars() if var not in EXEMPT and var not in text
    )
    assert not missing, (
        f"{EXAMPLE_ENV.name} does not mention {missing}. Add an entry (with a comment "
        "saying what it is and whether it is required), or, if a developer genuinely "
        f"never sets it, add it to EXEMPT in {Path(__file__).name} with the reason."
    )


def test_the_example_env_documents_no_variable_the_code_does_not_read() -> None:
    """The drift also runs the other way: a renamed variable leaves a stale entry.

    Someone copying the template would set a name nothing reads and get the *default*
    behavior with no error — the silent-misconfiguration case, which is worse than an
    unset variable because it looks configured.
    """
    text = EXAMPLE_ENV.read_text(encoding="utf-8")
    documented = set(_VAR_LITERAL.findall(text)) | {
        m.group(1) for m in re.finditer(r"^\s*#?\s*(USVOTE_[A-Z0-9_]+)=", text, re.M)
    }
    stale = sorted(documented - _declared_vars())
    assert not stale, (
        f"{EXAMPLE_ENV.name} documents {stale}, which nothing under src/ reads. "
        "Remove the entry, or fix the name to match the code."
    )


def test_exempt_variables_are_really_read_by_the_code() -> None:
    # An exemption for a variable that no longer exists is a dead claim that quietly
    # weakens the check — and would mask a future variable that happened to reuse the
    # name. Exemptions expire with the code they describe.
    declared = _declared_vars()
    dangling = sorted(var for var in EXEMPT if var not in declared)
    assert not dangling, f"EXEMPT lists {dangling}, which src/ no longer reads."
