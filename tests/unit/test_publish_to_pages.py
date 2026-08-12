"""`tooling/publish-to-pages.py` decides which bytes reach a public website.

Ported with the publisher itself in #132, from the `claude-code-sessions` repo's
`tooling/tests/test_publish_to_pages.py` (unittest → pytest, to match this repo's
suite). The focus is the **fail-closed contract** and **content-compare
idempotency** — the silent-wrong-image and partial-deploy failure modes the design
exists to prevent. A green sync that ships the wrong bytes is the nightmare case,
so those are the paths worth pinning.

Every test gets a freshly-loaded copy of the module and a throwaway repo + Pages
tree, with `REPO_ROOT` repointed at the throwaway, so nothing here touches the
real checkout or the real Pages site.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "tooling" / "publish-to-pages.py"

POST_TEMPLATE = """\
---
layout: post
title: "A title"
date: 2026-01-01 00:00:00-0800
description: "desc"
categories: ["american-history"]
tags: ["electoral-college"]
og_image: https://example.github.io/assets/img/{slug}-og.png
og_card_source: {card_rel}
featured: false
---

Body line one.
Body line two.
"""


def _load_publisher() -> ModuleType:
    """Import the hyphenated script by path (it is not an importable module name)."""
    spec = importlib.util.spec_from_file_location("publish_to_pages", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ptp() -> ModuleType:
    """A fresh module per test — `REPO_ROOT` is mutated, so it must not be shared."""
    return _load_publisher()


class Sandbox:
    """A throwaway source repo + Pages tree, with `REPO_ROOT` pointed at it."""

    def __init__(self, ptp: ModuleType, tmp_path: Path) -> None:
        self.ptp = ptp
        self.repo = tmp_path / "repo"
        self.posts_src = self.repo / "posts"
        self.pages_posts = tmp_path / "pages" / "_posts"
        self.pages_assets = tmp_path / "pages" / "assets" / "img"
        for d in (self.posts_src, self.pages_posts, self.pages_assets):
            d.mkdir(parents=True, exist_ok=True)
        # resolve_og_source reads this global at call time. The ignore is
        # unavoidable: a path-loaded module is a bare ModuleType to mypy, so
        # it has no attributes to assign to.
        ptp.REPO_ROOT = self.repo  # type: ignore[attr-defined]

    def add_post(
        self,
        slug: str,
        card_rel: str | None,
        *,
        write_card: bool = True,
        card_bytes: bytes = b"PNGDATA",
        filename: str | None = None,
    ) -> Path:
        """Write a post with `og_card_source = card_rel` (None -> empty field).

        Also renders the card file, unless `write_card` is False — the "field
        points at a card that was never generated" case.
        """
        if card_rel is not None and write_card:
            card = self.repo / card_rel
            card.parent.mkdir(parents=True, exist_ok=True)
            card.write_bytes(card_bytes)
        src = self.posts_src / (filename or f"2026-01-01-{slug}.md")
        src.write_text(
            POST_TEMPLATE.format(slug=slug, card_rel="" if card_rel is None else card_rel)
        )
        return src

    def publish(self, sources: list[Path], *, dry_run: bool = False) -> None:
        self.ptp.run(sources, self.pages_posts, self.pages_assets, dry_run)


@pytest.fixture
def box(ptp: ModuleType, tmp_path: Path) -> Sandbox:
    return Sandbox(ptp, tmp_path)


# --- the transform ---------------------------------------------------------


def test_happy_path_strips_only_og_card_source(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    src = box.add_post(
        "anatomy",
        "social/images/2026-01-03-linkedin-anatomy/og-card.png",
        card_bytes=b"CARD-A",
    )
    box.publish([src])

    published = (box.pages_posts / src.name).read_text()
    assert "og_card_source" not in published, "og_card_source must be stripped"
    assert "og_image:" in published, "og_image must be preserved"
    assert "featured: false" in published, "every other field passes through"
    assert "Body line one." in published
    assert published.endswith("\n")
    assert (box.pages_assets / "anatomy-og.png").read_bytes() == b"CARD-A", (
        "OG card must be copied to <assets>/<og_image basename>"
    )


def test_body_is_byte_for_byte(box: Sandbox) -> None:
    """The transform touches frontmatter only — never the prose."""
    src = box.add_post("body", "social/images/x/og-card.png")
    original = src.read_text().split("---\n", 2)[2]
    box.publish([src])
    published = (box.pages_posts / src.name).read_text().split("---\n", 2)[2]
    assert published == original


# --- idempotency -----------------------------------------------------------


def test_idempotent_rerun_writes_nothing(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    src = box.add_post(
        "retry", "social/images/2026-01-04-linkedin-retry/og-card.png",
        card_bytes=b"CARD-R",
    )
    box.publish([src])
    capsys.readouterr()
    box.publish([src])  # second run, nothing changed upstream
    out = capsys.readouterr().out
    assert "0 change(s)" in out, f"re-run should write nothing, got:\n{out}"
    assert "CHANGED" not in out


def test_changed_card_is_republished(box: Sandbox) -> None:
    """Content-compare must not mistake 'target exists' for 'target current'."""
    src = box.add_post("edit", "social/images/edit/og-card.png", card_bytes=b"V1")
    box.publish([src])
    (box.repo / "social/images/edit/og-card.png").write_bytes(b"V2")
    box.publish([src])
    assert (box.pages_assets / "edit-og.png").read_bytes() == b"V2"


# --- fail-closed conditions ------------------------------------------------


def test_missing_og_card_source(box: Sandbox) -> None:
    src = box.add_post("nocard", None)  # field present but empty
    with pytest.raises(box.ptp.PublishError, match="missing `og_card_source`"):
        box.publish([src])


def test_escaping_og_card_source(box: Sandbox) -> None:
    src = box.add_post("escape", "../../../etc/passwd", write_card=False)
    with pytest.raises(box.ptp.PublishError, match="escapes the repo root"):
        box.publish([src])


def test_absolute_og_card_source(box: Sandbox) -> None:
    src = box.add_post("abs", "/etc/passwd", write_card=False)
    with pytest.raises(box.ptp.PublishError, match="must be repo-root-relative"):
        box.publish([src])


def test_missing_card_file(box: Sandbox) -> None:
    src = box.add_post(
        "ghost", "social/images/2026-01-05-linkedin-ghost/og-card.png",
        write_card=False,
    )
    with pytest.raises(box.ptp.PublishError, match="og card source not found"):
        box.publish([src])


def test_missing_source_file(box: Sandbox) -> None:
    ghost = box.posts_src / "2026-01-01-does-not-exist.md"
    with pytest.raises(box.ptp.PublishError, match="source not found"):
        box.publish([ghost])


def test_no_frontmatter(box: Sandbox) -> None:
    bare = box.posts_src / "2026-01-01-bare.md"
    bare.write_text("# Just a heading\n\nNo frontmatter here.\n")
    with pytest.raises(box.ptp.PublishError, match="no frontmatter block found"):
        box.publish([bare])


def test_missing_pages_dir_fails_loud(box: Sandbox, tmp_path: Path) -> None:
    """A missing Pages dir means the worktree isn't checked out — never mkdir it."""
    src = box.add_post("nodir", "social/images/nodir/og-card.png")
    absent = tmp_path / "pages" / "nope"
    with pytest.raises(box.ptp.PublishError, match="is the Pages worktree checked out"):
        box.ptp.run([src], absent, box.pages_assets, False)
    assert not absent.exists()


# --- atomicity -------------------------------------------------------------


def test_target_collision_aborts_before_any_write(box: Sandbox) -> None:
    """Two posts colliding on one image target: fail with ZERO writes."""
    a = box.add_post(
        "dup", "social/images/2026-01-07-linkedin-a/og-card.png", card_bytes=b"A"
    )
    # A different post filename (so the post targets differ) but the same slug,
    # hence the same og_image basename.
    b = box.add_post(
        "dup",
        "social/images/2026-01-08-linkedin-b/og-card.png",
        card_bytes=b"B",
        filename="2026-01-02-dup.md",
    )
    with pytest.raises(box.ptp.PublishError, match="target collision"):
        box.publish([a, b])
    assert not any(box.pages_assets.iterdir()), "collision must abort before any write"
    assert not any(box.pages_posts.iterdir()), "collision must abort before any write"


def test_one_bad_post_blocks_the_whole_batch(box: Sandbox) -> None:
    """Validate-all-then-write: a good post must not half-publish beside a bad one."""
    good = box.add_post("good", "social/images/good/og-card.png")
    bad = box.add_post("bad", "social/images/bad/og-card.png", write_card=False)
    with pytest.raises(box.ptp.PublishError, match="2026-01-01-bad.md"):
        box.publish([good, bad])
    assert not any(box.pages_posts.iterdir())
    assert not any(box.pages_assets.iterdir())


# --- dry run ---------------------------------------------------------------


def test_dry_run_writes_nothing(
    box: Sandbox, capsys: pytest.CaptureFixture[str]
) -> None:
    src = box.add_post(
        "dry", "social/images/2026-01-06-linkedin-dry/og-card.png", card_bytes=b"CARD-D"
    )
    box.publish([src], dry_run=True)
    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert not (box.pages_posts / src.name).exists(), "dry-run must not write the post"
    assert not (box.pages_assets / "dry-og.png").exists(), "dry-run must not write image"


# --- og_image → target basename --------------------------------------------


def test_missing_og_image(box: Sandbox, ptp: ModuleType) -> None:
    with pytest.raises(ptp.PublishError, match="missing `og_image`"):
        ptp.og_target_name(None)


def test_og_target_name_from_url(ptp: ModuleType) -> None:
    url = "https://frederick-douglas-pearce.github.io/assets/img/222-votes-away-og.png"
    assert ptp.og_target_name(url) == "222-votes-away-og.png"
