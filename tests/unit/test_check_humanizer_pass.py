"""`tooling/check-humanizer-pass.py` fails CI on any post that has not recorded
a humanizer pass in its frontmatter (#258).

Ported from the `claude-code-sessions` repo's
`tooling/tests/test_check_humanizer_pass.py` (unittest → pytest). The guard
checks that a post RECORDS a pass, never that its prose is clean (#258, D-1), so
these tests pin the recording contract: a missing, empty, or non-version value
fails; `none` passes and is counted; every failing post is reported, not just
the first.

Added on the port: `predates` is a **closed set** (AC3). The source guard accepts
`predates` on any post; here only the four posts published before the
convention may carry it, and the set is pinned to a literal so it cannot grow.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[2]
_GUARD = _REPO / "tooling" / "check-humanizer-pass.py"

POST_TEMPLATE = """\
---
layout: post
title: "Test post"
date: 2026-01-01 00:00:00-0800
{field_line}featured: false
---

Body line.
"""

#: The four posts live before the convention landed, as the issue lists them.
#: Written out independently of the guard's constant so the pin below is not
#: circular.
PUBLISHED_BEFORE_CONVENTION = frozenset(
    {
        "2026-08-06-222-votes-away.md",
        "2026-08-18-presidential-elections-are-messy.md",
        "2026-08-25-it-takes-270-but-270-of-what.md",
        "2026-09-03-how-did-we-get-to-538-electors.md",
    }
)


def _load_guard() -> ModuleType:
    """Import the hyphenated script by path (it is not an importable module name)."""
    spec = importlib.util.spec_from_file_location("check_humanizer_pass", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def chp() -> ModuleType:
    """A fresh guard per test — tests repoint the publisher module's `REPO_ROOT`."""
    return _load_guard()


class Repo:
    """A throwaway repo with a `posts/` dir, `REPO_ROOT` pointed at it."""

    def __init__(self, chp: ModuleType, tmp_path: Path) -> None:
        self.chp = chp
        self.root = tmp_path / "repo"
        self.posts = self.root / "posts"
        self.posts.mkdir(parents=True)
        chp.ptp.REPO_ROOT = self.root

    def add_post(
        self,
        slug: str,
        value: str | None = "v3.0.0",
        *,
        filename: str | None = None,
    ) -> Path:
        """Write a dated post. `value=None` leaves the field out entirely."""
        field_line = "" if value is None else f"humanizer_pass: {value}\n"
        src = self.posts / (filename or f"2026-01-01-{slug}.md")
        src.write_text(POST_TEMPLATE.format(field_line=field_line), encoding="utf-8")
        return src

    def run(
        self, capsys: pytest.CaptureFixture[str], argv: list[str] | None = None
    ) -> tuple[int, str]:
        """Run the guard; return (exit code, stdout + stderr)."""
        code = self.chp.main([] if argv is None else argv)
        out = capsys.readouterr()
        return code, out.out + out.err


@pytest.fixture
def repo(chp: ModuleType, tmp_path: Path) -> Repo:
    return Repo(chp, tmp_path)


# --- happy path --------------------------------------------------------------


@pytest.mark.parametrize("value", ["v3.0.0", "3.0.0", '"v3.0.0"', "v3.1"])
def test_recorded_version_passes(
    repo: Repo, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    repo.add_post("anatomy", value)
    code, text = repo.run(capsys)
    assert code == 0, text
    assert "All 1 post(s) record a humanizer pass." in text


def test_inline_yaml_comment_is_accepted(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """Recording the date beside the version is natural; a comment is not part
    of the value."""
    repo.add_post("anatomy", "v3.0.0  # ran 2026-09-08")
    code, text = repo.run(capsys)
    assert code == 0, text


# --- the two non-version values ---------------------------------------------


def test_none_passes_and_is_counted(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """`none` is a deliberate record of no pass (D-5), not an absence."""
    repo.add_post("anatomy", "none")
    repo.add_post("retry", "v3.0.0")
    code, text = repo.run(capsys)
    assert code == 0, text
    assert "1 declined a pass" in text
    assert "0 predate the convention" in text
    assert "deliberately declined" in text


def test_predates_and_none_are_counted_separately(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """Collapsing `predates` into `none` would bury the one number worth acting
    on under an archive that can never change."""
    listed = sorted(PUBLISHED_BEFORE_CONVENTION)
    repo.add_post("a", "predates", filename=listed[0])
    repo.add_post("b", "predates", filename=listed[1])
    repo.add_post("retry", "none")
    repo.add_post("subagent", "v3.0.0")
    code, text = repo.run(capsys)
    assert code == 0, text
    assert "2 predate the convention" in text
    assert "1 declined a pass" in text
    assert "published before the convention" in text


def test_declined_with_stray_space_is_still_counted(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """The check and the count must normalize identically, or `"none "` passes
    without being counted as declined."""
    repo.add_post("anatomy", '"none "')
    code, text = repo.run(capsys)
    assert code == 0, text
    assert "1 declined a pass" in text


# --- predates is a closed set (AC3) -----------------------------------------


def test_predates_on_a_new_post_fails(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole point of the closed set: a new post cannot reach for it."""
    repo.add_post("next-post", "predates", filename="2026-10-01-next-post.md")
    code, text = repo.run(capsys)
    assert code == 1, text
    assert "[FAIL] 2026-10-01-next-post.md" in text
    assert "is reserved for the posts published before" in text


@pytest.mark.parametrize("filename", sorted(PUBLISHED_BEFORE_CONVENTION))
def test_predates_on_each_listed_post_passes(
    repo: Repo, capsys: pytest.CaptureFixture[str], filename: str
) -> None:
    repo.add_post("x", "predates", filename=filename)
    code, text = repo.run(capsys)
    assert code == 0, text
    assert "1 predate the convention" in text


def test_a_listed_post_may_record_a_real_pass(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """Listed posts are *allowed* `predates`, not required to keep it."""
    repo.add_post("x", "v3.0.0", filename=sorted(PUBLISHED_BEFORE_CONVENTION)[0])
    code, text = repo.run(capsys)
    assert code == 0, text


def test_the_closed_set_is_pinned_to_the_four_published_posts(
    chp: ModuleType,
) -> None:
    """Compared against an independent literal, so growing the set — the one
    change that would reopen `predates` to new posts — turns this red."""
    assert chp.PREDATES_POSTS == PUBLISHED_BEFORE_CONVENTION


# --- failures -----------------------------------------------------------------


def test_missing_field_fails(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.add_post("anatomy", None)
    code, text = repo.run(capsys)
    assert code == 1, text
    assert "no `humanizer_pass` in frontmatter" in text


def test_empty_field_fails(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.add_post("anatomy", "")
    code, text = repo.run(capsys)
    assert code == 1, text
    assert "is empty" in text


def test_boolean_value_fails(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    """A bare `true` names no version, so it cannot identify which pattern list
    ran (D-2). Rejected on purpose."""
    repo.add_post("anatomy", "true")
    code, text = repo.run(capsys)
    assert code == 1, text
    assert "is not a skill version" in text


def test_missing_frontmatter_fails(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo.posts / "2026-01-01-broken.md").write_text("no frontmatter here\n")
    code, text = repo.run(capsys)
    assert code == 1, text
    assert "[FAIL] 2026-01-01-broken.md: no frontmatter block found" in text


def test_the_read_does_not_depend_on_the_default_encoding(
    repo: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Posts are full of em dashes. On a UTF-8 runner a bare `read_text()` reads
    them fine, so writing one and running the guard proves nothing. Instead force
    reads with no named encoding to ASCII, a stand-in for a non-UTF-8 locale
    default, so only an explicit UTF-8 read passes."""
    src = repo.add_post("anatomy", "v3.0.0")
    src.write_bytes(src.read_bytes().replace(b"Body line.", "Body \u2014 line.".encode()))
    real_read_text = Path.read_text

    def ascii_by_default(
        self: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        return real_read_text(self, encoding=encoding or "ascii", errors=errors)

    monkeypatch.setattr(Path, "read_text", ascii_by_default)
    code, text = repo.run(capsys)
    assert code == 0, text


def test_an_undecodable_post_is_reported_not_raised(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """A UnicodeDecodeError is a ValueError, not an OSError, so an OSError-only
    handler would let it escape as a traceback and cut the report short. The
    post after it must still be reported."""
    (repo.posts / "2026-01-01-latin1.md").write_bytes(
        b"---\nhumanizer_pass: v3.0.0\n---\n\xff\xfe body\n"
    )
    repo.add_post("zz-after", None)
    code, text = repo.run(capsys)
    assert code == 1, text
    assert "[FAIL] 2026-01-01-latin1.md: cannot read 2026-01-01-latin1.md:" in text
    assert "[FAIL] 2026-01-01-zz-after.md" in text


def test_unreadable_path_is_reported_not_raised(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bad explicit path belongs in the report, not in a traceback."""
    code, text = repo.run(capsys, [str(repo.posts / "2026-01-01-nope.md")])
    assert code == 1, text
    assert "cannot read 2026-01-01-nope.md" in text
    assert str(repo.root) not in text


def test_reports_every_failing_post(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """One CI run should surface the whole backlog, not stop at the first — one
    post wrong in each way the guard rejects."""
    repo.add_post("missing", None)
    repo.add_post("empty", "")
    repo.add_post("boolean", "true")
    repo.add_post("reserved", "predates")
    repo.add_post("good", "v3.0.0")
    code, text = repo.run(capsys)
    assert code == 1, text
    for slug in ("missing", "empty", "boolean", "reserved"):
        assert f"[FAIL] 2026-01-01-{slug}.md" in text
    assert "[ok]   2026-01-01-good.md" in text
    assert "4 post(s) with no valid recorded humanizer pass" in text


def test_a_failing_run_still_reports_both_counts(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `none` count is the actionable one (D-5), and a failing run is when the
    author is reading the log, so the counts print on the failure path too. The
    two counts differ so a swapped or merged counter cannot pass."""
    listed = sorted(PUBLISHED_BEFORE_CONVENTION)
    repo.add_post("a", "predates", filename=listed[0])
    repo.add_post("b", "none")
    repo.add_post("c", "none")
    repo.add_post("bad", None)
    code, text = repo.run(capsys)
    assert code == 1, text
    assert "1 predate the convention. 2 declined a pass." in text


# --- selection ----------------------------------------------------------------


def test_explicit_paths_override_the_glob(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    good = repo.add_post("good", "v3.0.0")
    bad = repo.add_post("bad", None)
    assert repo.run(capsys, [str(good)])[0] == 0
    assert repo.run(capsys, [str(bad)])[0] == 1


def test_readme_is_not_checked(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    """The glob is dated posts only, matching the publisher's own selection."""
    (repo.posts / "README.md").write_text("# Posts\n\nNo frontmatter.\n")
    repo.add_post("anatomy", "v3.0.0")
    code, text = repo.run(capsys)
    assert code == 0, text
    assert "README" not in text


def test_empty_glob_fails_rather_than_reporting_green(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every post must carry the field, so a guard that checked zero posts has
    proved nothing."""
    code, text = repo.run(capsys)
    assert code == 1, text
    assert "no dated posts found" in text


# --- value checking, directly ------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "ok"),
    [
        ("v3.0.0", True),
        ("3.0.0", True),
        ("v3.1", True),
        ("  v3.0.0  ", True),
        ("'v3.0.0'", True),
        # Space inside the quotes: only the strip after unquoting removes it.
        ("' none '", True),
        ('" v3.0.0 "', True),
        ("none", True),
        (None, False),
        ("", False),
        ("   ", False),
        ("true", False),
        ("yes", False),
        ("done", False),
        ("v3", False),
        ("v3.0.0 (partial)", False),
        ("predates", False),  # on a post outside the closed set
        ("  predates  ", False),
    ],
)
def test_check_value_matrix(chp: ModuleType, raw: str | None, ok: bool) -> None:
    assert (chp.check_value(raw, "2026-10-01-new.md") is None) is ok


# --- the real posts/ ------------------------------------------------------------


def test_the_real_posts_pass_with_every_listed_post_backfilled(
    chp: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """Runs the guard over this repo's actual `posts/`, as the workflow does, and
    then reads the four backfilled posts by name: the guard alone would stay
    green if one of them were switched to a version or `none`, but the backfill
    (AC6) says each carries `predates`."""
    code = chp.main([])
    text = capsys.readouterr()
    assert code == 0, text.out + text.err
    for name in PUBLISHED_BEFORE_CONVENTION:
        assert chp.read_pass(_REPO / "posts" / name) == "predates", name


# --- the workflow (AC4) ---------------------------------------------------------

_WORKFLOW = _REPO / ".github" / "workflows" / "humanizer-guard.yml"
_GUARDED_PATHS = {
    "posts/**",
    "tooling/check-humanizer-pass.py",
    "tooling/publish-to-pages.py",
    ".github/workflows/humanizer-guard.yml",
}


def _trigger_block(workflow: str, trigger: str) -> str:
    """The lines under `on:`'s `<trigger>:` key, up to the next sibling key."""
    m = re.search(rf"^  {trigger}:\n((?:    .*\n|\s*\n)*)", workflow, re.MULTILINE)
    assert m is not None, f"no `{trigger}:` trigger in {_WORKFLOW.name}"
    return m.group(1)


def _paths(block: str) -> set[str]:
    m = re.search(r"^    paths:\n((?:      - .*\n)+)", block, re.MULTILINE)
    assert m is not None, "trigger has no `paths:` list"
    return set(re.findall(r'^      - "([^"]+)"', m.group(1), re.MULTILINE))


def test_the_workflow_runs_on_prs_and_main_pushes_scoped_to_its_paths() -> None:
    """AC4, read off the workflow text (PyYAML is not a declared dependency):
    both triggers exist, `push` is limited to `main`, and each trigger's path
    filter is exactly the guarded set, so dropping `posts/**` — after which the
    guard would never run on a post-only PR — turns this red."""
    workflow = _WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"^on:\n", workflow, re.MULTILINE)

    pull_request = _trigger_block(workflow, "pull_request")
    push = _trigger_block(workflow, "push")
    assert re.search(r"^    branches: \[main\]$", push, re.MULTILINE), push
    # No branch filter on pull_request: one would silently switch the guard off
    # for PRs into any branch it does not name, main included.
    assert not re.search(r"^    branches", pull_request, re.MULTILINE), pull_request
    assert _paths(pull_request) == _GUARDED_PATHS
    assert _paths(push) == _GUARDED_PATHS


def test_the_workflow_runs_the_guard_over_every_post() -> None:
    """The job must invoke the guard with no path arguments, so it checks the
    default full glob rather than a named subset."""
    workflow = _WORKFLOW.read_text(encoding="utf-8")
    runs = re.findall(r"^\s*- run: (.+)$", workflow, re.MULTILINE)
    assert runs == ["python3 tooling/check-humanizer-pass.py"], runs
