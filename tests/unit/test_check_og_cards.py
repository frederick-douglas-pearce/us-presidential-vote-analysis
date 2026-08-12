"""`tooling/check-og-cards.py` is the pre-merge gate that keeps a card-less post
off `main`.

Ported with the guard itself in #132, from the `claude-code-sessions` repo's
`tooling/tests/test_check_og_cards.py` (unittest → pytest). The guard reuses the
publisher's `build_plan`, so the fail-closed *resolution* is pinned in
`test_publish_to_pages.py`; these tests pin the guard's own behaviour — it reports
EVERY failing post rather than stopping at the first, it catches the cross-post
image collision a per-post pass cannot see, and it exits non-zero.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[2]
_GUARD = _REPO / "tooling" / "check-og-cards.py"

POST_TEMPLATE = """\
---
layout: post
title: "Test post"
date: 2026-01-01 00:00:00-0800
og_image: https://example.github.io/assets/img/{og_basename}
og_card_source: {card_rel}
featured: false
---

Body line.
"""


def _load_guard() -> ModuleType:
    """Import the hyphenated script by path (it is not an importable module name)."""
    spec = importlib.util.spec_from_file_location("check_og_cards", _GUARD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cog() -> ModuleType:
    """A fresh guard per test — it mutates the publisher module's `REPO_ROOT`."""
    return _load_guard()


class Sandbox:
    """A throwaway repo, with the publisher's `REPO_ROOT` pointed at it.

    The guard resolves via `cog.ptp`, and its default glob reads
    `cog.ptp.REPO_ROOT`, so repointing that one global covers both.
    """

    def __init__(self, cog: ModuleType, tmp_path: Path) -> None:
        self.cog = cog
        self.repo = tmp_path / "repo"
        self.posts = self.repo / "posts"
        self.posts.mkdir(parents=True, exist_ok=True)
        cog.ptp.REPO_ROOT = self.repo

    def add_post(
        self,
        slug: str,
        card_rel: str | None,
        *,
        write_card: bool = True,
        og_basename: str | None = None,
    ) -> Path:
        """Write a dated post named to match the publisher glob.

        `card_rel` is the `og_card_source` value (None -> empty field); the card
        file is rendered unless `write_card` is False. `og_basename` overrides the
        `og_image` basename so two posts can be made to collide on one target.
        """
        if card_rel and write_card:
            card = self.repo / card_rel
            card.parent.mkdir(parents=True, exist_ok=True)
            card.write_bytes(b"PNGDATA")
        src = self.posts / f"2026-01-01-{slug}.md"
        src.write_text(
            POST_TEMPLATE.format(
                og_basename=og_basename or f"{slug}-og.png",
                card_rel="" if card_rel is None else card_rel,
            )
        )
        return src

    def run(
        self, capsys: pytest.CaptureFixture[str], argv: list[str] | None = None
    ) -> tuple[int, str]:
        """Run the guard; return (exit code, combined stdout+stderr)."""
        code: int = self.cog.main([] if argv is None else argv)
        captured = capsys.readouterr()
        return code, captured.out + captured.err


@pytest.fixture
def box(cog: ModuleType, tmp_path: Path) -> Sandbox:
    return Sandbox(cog, tmp_path)


# --- happy path ------------------------------------------------------------


def test_all_cards_present_passes(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    box.add_post("anatomy", "social/images/2026-01-03-linkedin-anatomy/og-card.png")
    box.add_post("retry", "social/images/2026-01-04-linkedin-retry/og-card.png")
    code, text = box.run(capsys)
    assert code == 0, text
    assert "resolvable OG card" in text


def test_default_glob_skips_readme(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-dated .md (posts/README.md) has no frontmatter and must not be checked."""
    box.add_post("anatomy", "social/images/2026-01-03-linkedin-anatomy/og-card.png")
    (box.posts / "README.md").write_text("# posts/\n\nNot a post.\n")
    code, text = box.run(capsys)
    assert code == 0, text
    assert "README.md" not in text


def test_no_posts_is_not_a_failure(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty posts/ is the repo's state until post 1 ships — green, not red."""
    code, text = box.run(capsys)
    assert code == 0, text
    assert "no posts found" in text


# --- fail-closed conditions ------------------------------------------------


def test_missing_card_file_fails(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    box.add_post(
        "ghost", "social/images/2026-01-05-linkedin-ghost/og-card.png", write_card=False
    )
    code, text = box.run(capsys)
    assert code == 1, text
    assert "og card source not found" in text
    assert "2026-01-01-ghost.md" in text


def test_missing_field_fails(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC5: the deliberately-broken post — `og_card_source` present but empty."""
    box.add_post("nofield", None)
    code, text = box.run(capsys)
    assert code == 1, text
    assert "missing `og_card_source`" in text
    assert "[FAIL] 2026-01-01-nofield.md" in text, "the report must name the post"


def test_reports_every_failing_post(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard must not stop at the first failure — that is why it runs per-post."""
    box.add_post("ghost", "social/images/x/og-card.png", write_card=False)
    box.add_post("nofield", None)
    box.add_post("good", "social/images/2026-01-06-linkedin-good/og-card.png")
    code, text = box.run(capsys)
    assert code == 1, text
    assert "2026-01-01-ghost.md" in text
    assert "2026-01-01-nofield.md" in text
    assert "[ok] 2026-01-01-good.md" in text
    assert "2 OG-card problem(s)" in text


def test_cross_post_image_collision_fails(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two valid posts colliding on one og_image target — only a batch pass sees it."""
    box.add_post(
        "a", "social/images/2026-01-07-linkedin-a/og-card.png", og_basename="dup-og.png"
    )
    box.add_post(
        "b", "social/images/2026-01-08-linkedin-b/og-card.png", og_basename="dup-og.png"
    )
    code, text = box.run(capsys)
    assert code == 1, text
    assert "collision" in text.lower()


# --- explicit-path mode ----------------------------------------------------


def test_explicit_paths_argument(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    good = box.add_post("good", "social/images/2026-01-09-linkedin-good/og-card.png")
    bad = box.add_post("bad", "social/images/none/og-card.png", write_card=False)
    assert box.run(capsys, [str(good)])[0] == 0
    assert box.run(capsys, [str(bad)])[0] == 1


# --- drift guard -----------------------------------------------------------


def test_guard_reuses_the_publishers_validator(cog: ModuleType) -> None:
    """The whole point of the guard: it calls `build_plan`, it does not reimplement it.

    If someone re-derives the rules here, the guard can pass while publish fails.
    """
    publisher = _REPO / "tooling" / "publish-to-pages.py"
    assert cog.ptp.__file__ == str(publisher)
    assert cog.ptp.build_plan is not None
    source = _GUARD.read_text()
    assert "ptp.build_plan(" in source, "the guard must call the publisher's validator"
    assert "def build_plan" not in source, "...not define its own"
