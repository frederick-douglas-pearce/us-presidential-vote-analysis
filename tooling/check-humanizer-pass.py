#!/usr/bin/env python3
"""Pre-merge guard: every post under posts/ records a humanizer pass.

The humanizer skill (https://github.com/blader/humanizer) strips structural
AI-writing tells from a draft: not-X-but-Y staging, one-line closers, staged
run-ups, forced triads, dashes used as a universal connector, inflated
significance. It is a manual, judgment-heavy step, and nothing about a finished
draft reveals whether it ran. This guard makes the omission visible before merge
rather than after publication.

**It checks that the pass was recorded, not that the prose is clean** (#258, D-1).
The skill carries a "When not to act" section because these calls need judgment
that a pattern-matching lint cannot make: a numeric-range dash is not a
connector, and a "not X" scope correction is often exactly what the reader
needs. A lint that wrong trains the writer to write around it, which is worse
than no lint. So the `humanizer_pass` frontmatter field is an attestation, and
the guard only enforces that one was made.

The recorded value is the skill version that ran (D-2), so that a later change
to the skill's pattern list shows which posts predate it. A bare `true` names no
version and is rejected. Two non-version values are valid (D-5):

- `none` records a pass deliberately declined for that post. Open-ended, and the
  only value that is actionable debt.
- `predates` marks a post published before this convention landed. It is a
  CLOSED set, enforced here: only the filenames in `PREDATES_POSTS` may carry it,
  so a new post cannot reach for it.

The guard counts the two separately so the actionable `none` number is not
buried under a permanent archive.

Ported from the `claude-code-sessions` repo's guard (#223 there, commit
`913507e`). The closed-set enforcement is an addition: the source guard calls
`predates` closed but accepts it on any post.

Frontmatter parsing is reused verbatim from publish-to-pages.py, so the guard
sees exactly the fields the publisher sees and cannot drift from it.

Usage:
    python3 tooling/check-humanizer-pass.py [posts/NNNN-*.md ...]

Defaults to every dated post (`posts/[0-9][0-9][0-9][0-9]-*.md`), matching the
publisher's own selection so the two see the same file set (and the guard skips
`posts/README.md`). Exit 0 if all record a pass, 1 with a per-post report
otherwise.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

# Reuse publish-to-pages.py verbatim so the guard can't drift from the
# publisher's view of frontmatter. The script's filename is hyphenated (not
# importable by name), so we load it the same way check-og-cards.py does.
_SCRIPT = Path(__file__).resolve().parent / "publish-to-pages.py"


def _load_publisher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("publish_to_pages", _SCRIPT)
    assert spec is not None and spec.loader is not None, f"cannot load {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ptp = _load_publisher()

FIELD = "humanizer_pass"

# Two non-version values, kept distinct on purpose (D-5). Both mean "no pass was
# run", but they are different facts and only one is a choice. Collapsing them
# would make every future `none` ambiguous and hide the one signal worth acting
# on behind an archive that can never change.
PREDATES = "predates"
DECLINED = "none"

# The closed set of posts allowed `predates`: the four published before this
# convention landed (#258). Nothing may join it. A listed post is *allowed*
# `predates`, not required to keep it — a real pass run over one later is still
# a valid record.
PREDATES_POSTS: frozenset[str] = frozenset(
    {
        "2026-08-06-222-votes-away.md",
        "2026-08-18-presidential-elections-are-messy.md",
        "2026-08-25-it-takes-270-but-270-of-what.md",
        "2026-09-03-how-did-we-get-to-538-electors.md",
    }
)

# A recorded pass names the skill version that ran (D-2). The leading `v` is
# optional because the skill's manifest and SKILL.md report "3.0.0" while its
# release tag is "v3.0.0"; both are accepted, neither is rewritten.
_VERSION_RE = re.compile(r"^v?\d+\.\d+(\.\d+)?$")

# ` # ...` after a value is a YAML comment, not part of it. Recording the date
# beside the version is a natural thing to write, so accept it.
_INLINE_COMMENT_RE = re.compile(r"\s+#.*$")


def _normalize(raw: str | None) -> str:
    """The comparable value: inline comment dropped, quotes and space stripped.

    One implementation on purpose: `check_value` and the counts must agree, or a
    value like `"none "` passes the check without being counted as declined."""
    if raw is None:
        return ""
    return _INLINE_COMMENT_RE.sub("", raw.strip()).strip().strip("\"'").strip()


def check_value(raw: str | None, post_name: str) -> str | None:
    """None if the recorded value is acceptable for this post, else the reason."""
    if raw is None:
        return f"no `{FIELD}` in frontmatter"
    value = _normalize(raw)
    if not value:
        return f"`{FIELD}` is empty"
    if value == PREDATES:
        if post_name in PREDATES_POSTS:
            return None
        return (
            f"`{FIELD}: {PREDATES}` is reserved for the posts published before "
            f"this convention landed; record a skill version, or `{DECLINED}`"
        )
    if value == DECLINED:
        return None
    if not _VERSION_RE.match(value):
        return (
            f"`{FIELD}: {value}` is not a skill version "
            f"(expected e.g. `v3.0.0`, or `{DECLINED}`)"
        )
    return None


def read_pass(src: Path) -> str | None:
    """The post's recorded `humanizer_pass`, or None if absent.

    Raises PublishError for an unreadable file or a missing frontmatter block, so
    a bad path lands in the per-post report like every other failure instead of
    as a traceback."""
    try:
        # Posts are UTF-8 and full of em dashes; without an explicit encoding a
        # runner with a non-UTF-8 locale decodes as ASCII and dies. And a
        # UnicodeDecodeError is a ValueError, so an OSError-only handler misses it.
        text = src.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        reason = getattr(e, "strerror", None) or e
        raise ptp.PublishError(f"cannot read {src.name}: {reason}") from e
    fm_block, _ = ptp.split_frontmatter(text)
    value: str | None = ptp.read_field(fm_block, FIELD)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Guard: every post under posts/ records a humanizer pass "
        "(the pass itself is manual; this checks it was recorded).",
    )
    ap.add_argument(
        "posts",
        nargs="*",
        type=Path,
        help="posts to check (default: every posts/[0-9][0-9][0-9][0-9]-*.md)",
    )
    args = ap.parse_args(argv)

    posts: list[Path] = list(args.posts) or sorted(
        (ptp.REPO_ROOT / "posts").glob("[0-9][0-9][0-9][0-9]-*.md")
    )
    if not posts:
        # Unlike check-og-cards.py, zero posts is a failure: every post must carry
        # the field, so a guard that checked nothing has proved nothing.
        print(
            f"no dated posts found under {ptp.REPO_ROOT / 'posts'}. Expected "
            "posts/[0-9][0-9][0-9][0-9]-*.md; has the directory moved?",
            file=sys.stderr,
        )
        return 1

    # Per-post, collecting EVERY failure rather than stopping at the first, so one
    # CI run reports the whole backlog (the check-og-cards.py behavior).
    results: list[tuple[str, str | None, str | None]] = []
    for src in posts:
        try:
            raw = read_pass(src)
        except ptp.PublishError as e:
            results.append((src.name, str(e), None))
            continue
        results.append((src.name, check_value(raw, src.name), raw))

    for name, err, raw in results:
        if err:
            print(f"  [FAIL] {name}: {err}")
        elif _normalize(raw) == PREDATES:
            print(f"  [ok]   {name}: {PREDATES} (published before the convention)")
        elif _normalize(raw) == DECLINED:
            print(f"  [ok]   {name}: {DECLINED} (pass deliberately declined)")
        else:
            print(f"  [ok]   {name}: {_normalize(raw)}")

    passed = [_normalize(raw) for _, err, raw in results if not err]
    n_predates = passed.count(PREDATES)
    n_declined = passed.count(DECLINED)
    n_fail = len(results) - len(passed)
    # Printed on both paths: the `none` count is the actionable one (D-5), and a
    # failing run is exactly when the author is reading this log.
    counts = (
        f"{n_predates} predate the convention. "
        # The actionable number: posts that could have had a pass and did not.
        f"{n_declined} declined a pass."
    )

    if n_fail:
        print(f"\n{counts}")
        sys.stdout.flush()  # keep the per-post report ahead of the stderr summary
        print(
            f"\n{n_fail} post(s) with no valid recorded humanizer pass. Run the "
            f"humanizer skill\nover the draft, then set `{FIELD}: v<version>` in "
            f"its frontmatter. If the pass was\ndeliberately skipped, set "
            f"`{FIELD}: {DECLINED}` to record that instead.\n(`{PREDATES}` is "
            "reserved for the posts published before this convention landed.)",
            file=sys.stderr,
        )
        return 1

    print(f"\nAll {len(posts)} post(s) record a humanizer pass. {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
