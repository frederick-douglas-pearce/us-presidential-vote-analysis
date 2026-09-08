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
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "tooling" / "publish-to-pages.py"

#: The two publishers sharing one Pages namespace (#157). Spelled as the
#: hyphenated GitHub slugs, which is what the sync commit subject carries.
OUR_REPO = "us-presidential-vote-analysis"
THEIR_REPO = "claude-code-sessions"


def sync_subject(repo: str) -> str:
    """A Pages sync commit subject, exactly as the Action writes it."""
    return f"chore(sync): publish posts from {repo}@abc1234"


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
            POST_TEMPLATE.format(
                slug=slug, card_rel="" if card_rel is None else card_rel
            )
        )
        return src

    def publish(
        self,
        sources: list[Path],
        *,
        dry_run: bool = False,
        source_repo: str = OUR_REPO,
        # `object`, not `str | None`: the seam gained a third outcome in
        # #200 (`UNATTRIBUTED_SYNC`), and a fake returning it is exactly
        # what `test_an_unattributable_sync_refusal_never_says_rename`
        # injects.
        pages_owner: Callable[[Path], object] | None = None,
    ) -> None:
        """Publish through `run()`.

        `pages_owner` defaults to "every existing target is ours", which is the
        world every test written before #157 assumed. The cross-repo tests pass
        one to model the other publisher; the real git-backed implementation is
        exercised separately, against a throwaway repo.
        """
        owner = pages_owner or (lambda _dest: source_repo)
        self.ptp.run(
            sources,
            self.pages_posts,
            self.pages_assets,
            dry_run,
            source_repo,
            owner,
        )


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
        "retry",
        "social/images/2026-01-04-linkedin-retry/og-card.png",
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
        "ghost",
        "social/images/2026-01-05-linkedin-ghost/og-card.png",
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
        box.ptp.run([src], absent, box.pages_assets, False, OUR_REPO)
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
    assert not (box.pages_assets / "dry-og.png").exists(), (
        "dry-run must not write image"
    )


# --- og_image → target basename --------------------------------------------


def test_missing_og_image(box: Sandbox, ptp: ModuleType) -> None:
    with pytest.raises(ptp.PublishError, match="missing `og_image`"):
        ptp.og_target_name(None)


def test_og_target_name_from_url(ptp: ModuleType) -> None:
    url = "https://frederick-douglas-pearce.github.io/assets/img/222-votes-away-og.png"
    assert ptp.og_target_name(url) == "222-votes-away-og.png"


@pytest.mark.parametrize("quote", ['"', "'"])
def test_quoted_frontmatter_values_are_unquoted(
    box: Sandbox, ptp: ModuleType, quote: str
) -> None:
    """A quoted `og_image` must not put the quote character into the filename.

    This repo's frontmatter convention quotes `title` and `description`, so
    quoting `og_image` is a natural habit. Unstripped, the card lands at
    `x-og.png"` while the post points at `x-og.png` — a broken share image under
    a green Action and a green card guard, which is exactly what the fail-closed
    design is for.
    """
    src = box.add_post("quoted", "social/images/quoted/og-card.png")
    src.write_text(
        src.read_text().replace(
            "og_image: https://example.github.io/assets/img/quoted-og.png",
            f"og_image: {quote}https://example.github.io/assets/img/quoted-og.png{quote}",
        )
    )
    box.publish([src])
    assert (box.pages_assets / "quoted-og.png").is_file()
    assert not list(box.pages_assets.glob("*[\"']*")), "no quote may reach a filename"


def test_trailing_inline_comment_fails_closed(box: Sandbox) -> None:
    """`urlparse` reads a trailing `# …` as a fragment, leaving a padded name."""
    src = box.add_post("commented", "social/images/commented/og-card.png")
    src.write_text(src.read_text().replace("-og.png\n", "-og.png  # the card\n", 1))
    with pytest.raises(box.ptp.PublishError, match="is not a plain filename"):
        box.publish([src])
    assert not any(box.pages_assets.iterdir())


def test_non_ascii_body_round_trips(box: Sandbox) -> None:
    """Posts are full of em dashes; the write side is unconditionally UTF-8."""
    src = box.add_post("unicode", "social/images/unicode/og-card.png")
    src.write_text(
        src.read_text() + "\nAn em dash — and a curly quote’s tail.\n",
        encoding="utf-8",
    )
    box.publish([src])
    published = (box.pages_posts / src.name).read_text(encoding="utf-8")
    assert "em dash — and a curly quote’s tail." in published


# --- the shared-namespace provenance guard (#157) ---------------------------
#
# Two repos publish into ONE Pages namespace, and `build_plan`'s collision check
# sees only its own repo's posts — so a cross-repo collision enters neither
# publisher's plan and overwrites a card silently under two green Actions.
# `assert_no_foreign_overwrite` closes that by asking the Pages history which
# publisher owns the target.
#
# The tests below split deliberately: the POLICY is exercised with an injected
# `pages_owner` (fast, and it can model a sibling repo that isn't here), while
# the real git-backed reader gets its own tests against a throwaway repo. Those
# shell out, which the unit tier already does elsewhere — see
# `tests/unit/test_layering.py`, which runs its import-graph checks as
# subprocesses.


def _explode(dest: Path) -> str | None:
    """A `pages_owner` that fails the test if it is ever called.

    A spy, not a stub, and the distinction is the point: "an unchanged target
    doesn't consult git" is a claim about the MECHANISM, and a test that merely
    asserted the publish succeeded would stay green with the whole guard
    deleted.
    """
    raise AssertionError(f"pages_owner must not be consulted for {dest}")


class _NoSubprocess:
    """Stands in for the module's `subprocess`, failing on any use.

    Patched onto the module rather than onto `_git_run`, so what it enforces is
    "no git process started through this module's `subprocess`" rather than
    "one particular helper was not called" — a hand-rolled
    `subprocess.run(["git", ...])` resolves the same module global and is caught
    too, and renaming the helper cannot quietly make the spy inert. It is not a
    bound on process creation in general: `from subprocess import run` or
    `os.popen` would both escape it.
    """

    def run(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "build_plan must not shell out — check-og-cards.py calls it with "
            "no Pages checkout"
        )


def test_build_plan_never_shells_out_to_git(box: Sandbox) -> None:
    """`assert_no_foreign_overwrite` belongs to `run()`, never to `build_plan`.

    `tooling/check-og-cards.py` is the PR guard: it calls `build_plan` directly
    with inert `/__pages__/...` stand-in dirs and documents that it needs no
    Pages repo, checkout or PAT. Move the provenance check into `build_plan` and
    that stops being true — the guard acquires a git dependency and a
    Pages-checkout assumption on every PR.

    **The regression is silent, which is why this is a test and not a comment.**
    Nothing else goes red: the PR guard's stand-in targets never exist, so a
    check living in `build_plan` short-circuits on `not dest.exists()` before it
    ever reaches git.
    """
    # The precondition IS the test. git is reached only for a target that
    # exists with differing bytes, so without this setup the check would pass
    # vacuously against the very mutation it exists to catch — the short-circuit
    # would spare the misplaced guard rather than the guard being absent.
    src = box.add_post("nogit", "social/images/nogit/og-card.png", card_bytes=b"OURS")
    target = box.pages_assets / "nogit-og.png"
    target.write_bytes(b"THEIRS")
    assert target.exists() and target.read_bytes() != b"OURS"

    # Patching an absent attribute would create one and spy on nothing.
    assert hasattr(box.ptp, "subprocess")
    box.ptp.subprocess = _NoSubprocess()  # type: ignore[attr-defined]

    assert box.ptp.build_plan([src], box.pages_posts, box.pages_assets)


def test_a_card_owned_by_the_sibling_repo_is_not_overwritten(box: Sandbox) -> None:
    """The headline case: their card, our slug, differing bytes -> fail closed."""
    src = box.add_post("shared", "social/images/shared/og-card.png", card_bytes=b"OURS")
    (box.pages_assets / "shared-og.png").write_bytes(b"THEIRS")

    with pytest.raises(
        box.ptp.PublishError, match=r"last published by 'claude-code-sessions'"
    ):
        box.publish([src], pages_owner=lambda _d: THEIR_REPO)

    # Fail-closed means fail-BEFORE-writing, so their bytes must still be there.
    assert (box.pages_assets / "shared-og.png").read_bytes() == b"THEIRS"


def test_a_target_no_publisher_owns_is_refused_with_a_different_remedy(
    box: Sandbox,
) -> None:
    """A site-owned or hand-written target (the live `og_banner.png` is one).

    Refused like a sibling's card, but the advice must NOT be "rename your
    slug": there is no other series to disambiguate from, and renaming an
    already-published post moves a live permalink and share-card URL. Asserting
    the remedy, not just the refusal, is the point of this test.
    """
    src = box.add_post("banner", "social/images/banner/og-card.png", card_bytes=b"OURS")
    (box.pages_assets / "banner-og.png").write_bytes(b"SITE")

    with pytest.raises(
        box.ptp.PublishError, match=r"do NOT reflexively rename this post's slug"
    ):
        box.publish([src], pages_owner=lambda _d: None)


def test_post_targets_are_guarded_as_well_as_cards(box: Sandbox) -> None:
    """Both target kinds, not just the card.

    The card is the likelier collision; the post is the worse one. Guarding both
    is one uniform loop, and this pins that the post target is really in it — the
    card here is byte-identical, so ONLY the post can trip the guard.
    """
    src = box.add_post("dup", "social/images/dup/og-card.png", card_bytes=b"CARD")
    (box.pages_assets / "dup-og.png").write_bytes(b"CARD")  # identical: not the trigger
    (box.pages_posts / src.name).write_bytes(b"---\nlayout: post\n---\ntheirs\n")

    with pytest.raises(
        box.ptp.PublishError, match=r"\(post for .*\): it was last published by"
    ):
        box.publish([src], pages_owner=lambda _d: THEIR_REPO)


def test_our_own_target_is_overwritten_normally(box: Sandbox) -> None:
    """Provenance that matches us is not an obstacle — the guard is not a freeze."""
    src = box.add_post("ours", "social/images/ours/og-card.png", card_bytes=b"NEW")
    (box.pages_assets / "ours-og.png").write_bytes(b"OLD")

    box.publish([src], pages_owner=lambda _d: OUR_REPO)

    assert (box.pages_assets / "ours-og.png").read_bytes() == b"NEW"


def test_an_unchanged_target_never_consults_provenance(box: Sandbox) -> None:
    """Phase 2 won't write it, so there is nothing to arbitrate — and no git call.

    Load-bearing for the Action's reconcile-retry loop, which re-transforms
    against a moved tip on every attempt: the common case there is a target
    whose bytes already match.
    """
    src = box.add_post("idem", "social/images/idem/og-card.png")
    box.publish([src])  # first publish creates the targets

    box.publish([src], pages_owner=_explode)  # second must consult nothing


def test_an_absent_target_never_consults_provenance(box: Sandbox) -> None:
    """Nothing to overwrite — the first publish of a new card asks git nothing."""
    src = box.add_post("brandnew", "social/images/brandnew/og-card.png")

    box.publish([src], pages_owner=_explode)

    assert (box.pages_assets / "brandnew-og.png").is_file()


def test_a_foreign_overwrite_aborts_the_whole_batch_before_any_write(
    box: Sandbox,
) -> None:
    """Phase-1 discipline: one foreign target blocks the batch with zero writes."""
    clean = box.add_post("clean", "social/images/clean/og-card.png")
    dirty = box.add_post("dirty", "social/images/dirty/og-card.png", card_bytes=b"OURS")
    (box.pages_assets / "dirty-og.png").write_bytes(b"THEIRS")

    def owner(dest: Path) -> str | None:
        return THEIR_REPO if "dirty" in dest.name else OUR_REPO

    with pytest.raises(box.ptp.PublishError, match="refusing to overwrite"):
        box.publish([clean, dirty], pages_owner=owner)

    assert not (box.pages_posts / clean.name).exists()
    assert not (box.pages_assets / "clean-og.png").exists()


def test_dry_run_still_refuses_a_foreign_overwrite(box: Sandbox) -> None:
    """The operator dry-run is the pre-publish preview — it must surface this."""
    src = box.add_post(
        "preview", "social/images/preview/og-card.png", card_bytes=b"OURS"
    )
    (box.pages_assets / "preview-og.png").write_bytes(b"THEIRS")

    with pytest.raises(box.ptp.PublishError, match="refusing to overwrite"):
        box.publish([src], dry_run=True, pages_owner=lambda _d: THEIR_REPO)


def test_an_empty_source_repo_is_refused(box: Sandbox) -> None:
    """`required=True` accepts "", and an empty slug is only refused LATER.

    It would commit `... posts from @<sha>`, which the subject pattern can never
    parse. Since #200 that commit is also authored by `_SYNC_AUTHOR`, so every
    later update of that post reads as `UNATTRIBUTED_SYNC` rather than as owned
    by nobody — refused either way, but under a remedy naming the wrong cause.
    Kept in step with the same account in `main()`, which is the code this
    docstring describes.
    """
    src = box.add_post("empty", "social/images/empty/og-card.png")
    with pytest.raises(box.ptp.PublishError, match="must not be empty"):
        box.ptp.main(
            [
                str(src),
                "--posts-dir",
                str(box.pages_posts),
                "--assets-dir",
                str(box.pages_assets),
                "--source-repo",
                "  ",
            ]
        )


def test_a_padded_source_repo_is_trimmed_before_use(
    box: Sandbox, pages_repo: Path
) -> None:
    """Validated and used must be the SAME value.

    Trimming only for the emptiness check would let `--source-repo " ours"`
    pass validation and then match no owner — every one of our own targets
    refused, by a value the operator cannot see is padded. Run against real
    history so the comparison is the real one.
    """
    target = box.pages_assets / "padded-og.png"
    target.write_bytes(b"OLD")
    _git(pages_repo, "add", ".")
    _git(pages_repo, "commit", "-q", "-m", sync_subject(OUR_REPO))
    src = box.add_post("padded", "social/images/padded/og-card.png", card_bytes=b"NEW")

    box.ptp.main(
        [
            str(src),
            "--posts-dir",
            str(box.pages_posts),
            "--assets-dir",
            str(box.pages_assets),
            "--source-repo",
            f"  {OUR_REPO}  ",
        ]
    )

    assert target.read_bytes() == b"NEW"


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        (sync_subject(OUR_REPO), OUR_REPO),
        (sync_subject(THEIR_REPO), THEIR_REPO),
        ("chore(sync): publish posts from a.repo_x-1@deadbee", "a.repo_x-1"),
        # Everything a non-sync writer leaves behind reads as "not a sync".
        ("Add OG banner image and update config to use it", None),
        ("Update ESG news feed - 2026-08-28", None),
        ("chore(sync): publish posts from norepo", None),  # no @sha
        ("prefixed chore(sync): publish posts from x@1", None),  # must match at ^
        ("chore(sync): publish posts from @deadbee", None),  # the empty-slug commit
    ],
)
def test_sync_source_repo_parses_the_subject(
    ptp: ModuleType, subject: str, expected: str | None
) -> None:
    assert ptp.sync_source_repo(subject) == expected


# --- the real git-backed reader --------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    """Run git with an explicit identity — the runner may have no global config."""
    _git_as("t", cwd, *args)


def _git_as(name: str, cwd: Path, *args: str) -> None:
    """`_git`, with the commit identity as `name`.

    Provenance became a two-signal question in #200 — subject AND author — so a
    test that exercises the author leg has to be able to set it. `user.name`
    sets author and committer alike, which is what a direct-push sync produces
    in both publishers' Actions.
    """
    subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", f"user.name={name}", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _last_author(cwd: Path, path: Path) -> str:
    """Author of the newest commit touching `path` — read back, never assumed."""
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%an", "--", str(path)],
        cwd=cwd,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    return proc.stdout.strip()


def _last_subject(cwd: Path, path: Path) -> str:
    """Subject of the newest commit touching `path` — read back, never assumed.

    The twin of `_last_author`, and added for the same reason: #215's forgery is
    only a forgery if the separator SURVIVES the round-trip into git. Asserting
    the Python-side string would not show that.
    """
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%s", "--", str(path)],
        cwd=cwd,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    return proc.stdout.strip()


#: A sibling sync whose subject has drifted out of `_SYNC_SUBJECT`'s reach —
#: still a sync, still committed by the bot, no longer self-describing. The
#: precise shape does not matter; that it does not parse is the whole point.
DRIFTED_SUBJECT = "sync: publishing posts from claude-code-sessions (abc1234)"

#: The identity both publishers' Actions commit their syncs under.
SYNC_AUTHOR = "pages-sync[bot]"

#: The Pages repo's OTHER automated writer, verified over its full history on
#: 2026-09-07. It has never touched `_posts/` or `assets/img/`, but the guard
#: must not depend on that continuing to hold.
OTHER_BOT = "dependabot[bot]"


@pytest.fixture
def pages_repo(box: Sandbox, tmp_path: Path) -> Path:
    """The sandbox's Pages tree, made a real git repo."""
    pages = tmp_path / "pages"
    _git(pages, "init", "-q", ".")
    return pages


def test_a_real_sibling_sync_is_read_and_refused(
    box: Sandbox, pages_repo: Path
) -> None:
    """The whole path end-to-end on real history: read -> parse -> refuse.

    The foreign case specifically, because parse-then-refuse is the leg most
    likely to rot silently — a reader that returned the wrong thing on the
    "ours" case would merely publish, which is what it does anyway.
    """
    (box.pages_assets / "real-og.png").write_bytes(b"THEIRS")
    _git(pages_repo, "add", ".")
    _git(pages_repo, "commit", "-q", "-m", sync_subject(THEIR_REPO))

    src = box.add_post("real", "social/images/real/og-card.png", card_bytes=b"OURS")

    # No injected owner: this exercises ptp.git_pages_owner itself.
    with pytest.raises(
        box.ptp.PublishError, match=r"last published by 'claude-code-sessions'"
    ):
        box.ptp.run([src], box.pages_posts, box.pages_assets, False, OUR_REPO)

    assert (box.pages_assets / "real-og.png").read_bytes() == b"THEIRS"


def test_a_hand_edit_on_top_of_our_sync_does_not_brick_the_publish(
    box: Sandbox, pages_repo: Path
) -> None:
    """The most recent SYNC commit decides ownership — not the most recent commit.

    Someone fixing a typo on the Pages side, or a site-wide `prettier --write`,
    must not permanently reclassify our own post as foreign. It would: the
    Action re-publishes every dated post on every run and aborts the batch on
    the first refusal, so reading the latest commit of any kind would block ALL
    future publishing, on every retry, until the Pages repo was hand-edited.
    """
    target = box.pages_assets / "ours-og.png"
    target.write_bytes(b"V1")
    _git(pages_repo, "add", ".")
    _git(pages_repo, "commit", "-q", "-m", sync_subject(OUR_REPO))
    target.write_bytes(b"HAND-EDITED ON THE SITE")
    _git(pages_repo, "add", ".")
    _git(pages_repo, "commit", "-q", "-m", "Fix a typo in the card alt text")

    assert box.ptp.git_pages_owner(target) == OUR_REPO


def test_a_site_owned_target_has_no_pages_owner(box: Sandbox, pages_repo: Path) -> None:
    """Real history with no sync commit at all — the `og_banner.png` shape."""
    target = box.pages_assets / "og_banner.png"
    target.write_bytes(b"BANNER")
    _git(pages_repo, "add", ".")
    _git(pages_repo, "commit", "-q", "-m", "Add OG banner image and update config")

    assert box.ptp.git_pages_owner(target) is None


def test_a_path_with_no_history_has_no_pages_owner(
    box: Sandbox, pages_repo: Path
) -> None:
    """`git log` exits 0 with empty output here — "no history", not an error."""
    _git(pages_repo, "commit", "-q", "--allow-empty", "-m", "init")
    stray = box.pages_assets / "stray-og.png"
    stray.write_bytes(b"UNTRACKED")

    assert box.ptp.git_pages_owner(stray) is None


# --- #200: the second signal, when the sibling's subject drifts ------------
#
# Seven tests, and THREE of them fail against the pre-#200 code — the repro
# (which fails on behavior: the overwrite proceeds), plus the two that read
# symbols `main` does not define at all, `UNATTRIBUTED_SYNC` and `_SYNC_AUTHOR`.
#
# The other four pass before and after, deliberately, one role each: one pins
# the two-signal happy path (a parseable subject must still win over the author
# branch), one pins a property this change had to PRESERVE (the anti-bricking
# skip #157's review paid for, here on the site's most frequent writer), one
# pins the NARROWING (sync identity, not "any bot"), and one is the second drift
# tripwire on our own half of the contract, which passes on main because the
# subject it renders already parses.
#
# The other PRESERVE test, `test_a_hand_edit_on_top_of_our_sync_does_not_brick_
# the_publish`, is #157's and sits ABOVE this header — it is not one of the
# seven, and counting it here is the arithmetic slip this paragraph has now
# made twice.
#
# What each one is for is stated on it, so a later reader does not mistake
# "passes on main" for "proves nothing". Counts included on purpose: the header
# is the map, and a map that miscounts its own territory is worse than none.


def test_a_drifted_sibling_sync_is_refused_not_walked_past(
    box: Sandbox, pages_repo: Path
) -> None:
    """#200's repro, inverted. THE test for this change — it fails without it.

    History is our sync (older) then theirs (newer) with a subject
    `_SYNC_SUBJECT` cannot parse. Before #200 the drifted commit was not read as
    "theirs" — it was not read at all, so the walk continued to our older sync,
    the target resolved to US, and their card was silently overwritten under a
    green Action. Now the author stops the walk.

    Two details are load-bearing rather than incidental. The drifted commit must
    genuinely be authored by the sync bot, so the author is READ BACK rather than
    assumed — a helper that silently failed to set it would leave this test
    passing for the wrong reason, via the no-owner branch. And the match string
    is one only the new remedy carries: the no-owner refusal also talks about
    subjects this guard does not parse, so a looser match could not tell the two
    branches apart.
    """
    target = box.pages_assets / "drift-og.png"
    target.write_bytes(b"OURS-V1")
    _git(pages_repo, "add", ".")
    _git(pages_repo, "commit", "-q", "-m", sync_subject(OUR_REPO))

    target.write_bytes(b"THEIRS")
    _git_as(SYNC_AUTHOR, pages_repo, "add", ".")
    _git_as(SYNC_AUTHOR, pages_repo, "commit", "-q", "-m", DRIFTED_SUBJECT)
    assert _last_author(pages_repo, target) == SYNC_AUTHOR

    src = box.add_post(
        "drift", "social/images/drift/og-card.png", card_bytes=b"OURS-V2"
    )

    with pytest.raises(box.ptp.PublishError, match="realign the subject format"):
        box.ptp.run([src], box.pages_posts, box.pages_assets, False, OUR_REPO)

    assert target.read_bytes() == b"THEIRS"


def test_a_well_formed_sync_by_the_sync_bot_is_read_from_its_subject(
    box: Sandbox, pages_repo: Path
) -> None:
    """The two-signal happy path, with BOTH signals actually present.

    In every other owner test the commit whose SUBJECT decides the answer is
    authored by `t`, so until this one the subject leg was only ever exercised on
    commits the author leg would have ignored anyway. (Siblings do commit as
    `Fred Pearce`, `dependabot[bot]` and `pages-sync[bot]` — but never on the
    commit whose subject is the one that parses.) The
    real article carries both, and their order is what makes the whole design
    work: the subject is tried first, so a sibling sync the guard CAN parse is
    still attributed to the sibling rather than being swallowed by the
    author branch as merely "some publisher".

    Deleting the subject-parse leg turns this red — it would return
    UNATTRIBUTED_SYNC for a commit that says exactly whose it is.
    """
    target = box.pages_assets / "both-og.png"
    target.write_bytes(b"THEIRS")
    _git_as(SYNC_AUTHOR, pages_repo, "add", ".")
    _git_as(SYNC_AUTHOR, pages_repo, "commit", "-q", "-m", sync_subject(THEIR_REPO))
    assert _last_author(pages_repo, target) == SYNC_AUTHOR

    assert box.ptp.git_pages_owner(target) == THEIR_REPO


def test_the_esg_cron_on_top_of_our_sync_does_not_brick_the_publish(
    box: Sandbox, pages_repo: Path
) -> None:
    """The anti-bricking skip, on the Pages repo's most frequent writer.

    The daily ESG cron authors as a human (`Fred Pearce`, 388 commits over the
    full history), so it must keep falling through to the skip. The sibling test
    above stops the walk on an unparseable subject — this pins that it does so
    only for the SYNC identity, or the busiest writer on the site would refuse
    every one of our own republishes.

    Passes before #200 as well: preserving it is the point (see
    `test_a_hand_edit_on_top_of_our_sync_does_not_brick_the_publish`, the same
    property for a one-off hand edit).
    """
    target = box.pages_assets / "cron-og.png"
    target.write_bytes(b"V1")
    _git(pages_repo, "add", ".")
    _git(pages_repo, "commit", "-q", "-m", sync_subject(OUR_REPO))

    target.write_bytes(b"V1 + a site-wide reformat")
    _git_as("Fred Pearce", pages_repo, "add", ".")
    _git_as(
        "Fred Pearce",
        pages_repo,
        "commit",
        "-q",
        "-m",
        "Update ESG news feed - 2026-09-06",
    )

    assert box.ptp.git_pages_owner(target) == OUR_REPO


def test_a_non_sync_bot_is_skipped_not_read_as_an_unattributable_sync(
    box: Sandbox, pages_repo: Path
) -> None:
    """The decision-pin: the rule keys on the SYNC identity, never on "any bot".

    #200 proposed treating any bot-authored commit with an unparseable subject
    as foreign. This repo's guard narrows that to `_SYNC_AUTHOR`, because the
    Pages repo has a second bot — `dependabot[bot]` — and a suffix rule would
    refuse the day it, or any later image optimizer, touched `assets/img/`.

    Passes on main, and fails against an "any bot" implementation, which is what
    earns it a place: it is the only test that holds the narrowing in position.
    """
    target = box.pages_assets / "bot-og.png"
    target.write_bytes(b"V1")
    _git(pages_repo, "add", ".")
    _git(pages_repo, "commit", "-q", "-m", sync_subject(OUR_REPO))

    target.write_bytes(b"V1 + an automated tweak")
    _git_as(OTHER_BOT, pages_repo, "add", ".")
    _git_as(
        OTHER_BOT,
        pages_repo,
        "commit",
        "-q",
        "-m",
        "Bump the actions group across 1 directory",
    )
    assert _last_author(pages_repo, target) == OTHER_BOT

    assert box.ptp.git_pages_owner(target) == OUR_REPO


def test_an_unattributable_sync_refusal_never_says_rename(box: Sandbox) -> None:
    """The third remedy is a third remedy — not a copy of the other two.

    Renaming is right for a live slug collision with the sibling series and
    wrong here for its own reason: this is not a collision at all, so a rename
    would move a live permalink and a share-card URL and leave the actual
    defect — two publishers disagreeing about a subject format — untouched.

    Driven through the injected seam rather than through git, which is possible
    only because the reader RETURNS the third outcome instead of raising it: a
    raise would put this branch out of the seam's reach entirely.
    """
    (box.pages_assets / "seam-og.png").write_bytes(b"SOMEONE ELSE'S")
    src = box.add_post("seam", "social/images/seam/og-card.png", card_bytes=b"OURS")

    with pytest.raises(box.ptp.PublishError) as excinfo:
        box.publish([src], pages_owner=lambda _dest: box.ptp.UNATTRIBUTED_SYNC)

    msg = str(excinfo.value)
    assert "realign the subject format" in msg
    assert "Do NOT rename this post's slug" in msg
    # The foreign-owner remedy's instruction, which is the wrong advice here.
    assert "so its targets are unique" not in msg


def test_the_workflow_commits_under_the_identity_the_guard_keys_on(
    ptp: ModuleType,
) -> None:
    """Our half of the two-signal contract, tied to the workflow that sets it.

    `_SYNC_AUTHOR` is only provenance while `pages-sync.yml` actually commits
    under it. Nothing else notices if the workflow's identity is edited — the
    sync would keep working and the guard would quietly stop recognizing our own
    syncs.
    """
    workflow = (_REPO / ".github" / "workflows" / "pages-sync.yml").read_text()
    m = re.search(r'git config user\.name\s+"([^"]+)"', workflow)
    assert m is not None, "no `git config user.name` in pages-sync.yml"
    assert m.group(1) == ptp._SYNC_AUTHOR


def test_the_workflow_subject_template_still_parses(ptp: ModuleType) -> None:
    """The other half — and #200 is what makes this one urgent.

    BEFORE #200, drift in our OWN subject was a silent no-op: our newest sync
    stopped parsing, the walk fell back to an older parseable sync of ours, and
    publishing continued. AFTER it, that same commit is authored by the sync bot
    and unparseable, so it is refused — and since the Action republishes every
    dated post per run and aborts the batch on the first refusal, ALL publishing
    stops until someone fixes it.

    So the identity tie-test above is not sufficient: it says nothing about the
    subject, which is the string that actually drifts. Render the workflow's own
    template and put it through the parser.
    """
    workflow = (_REPO / ".github" / "workflows" / "pages-sync.yml").read_text()
    m = re.search(r'commit_msg="([^"]+)"', workflow)
    assert m is not None, "no `commit_msg=` template in pages-sync.yml"

    rendered = (
        m.group(1)
        .replace("${SOURCE_REPO}", OUR_REPO)
        .replace("${GITHUB_SHA:0:7}", "abc1234")
    )
    assert "$" not in rendered, (
        f"unsubstituted shell variable in {m.group(1)!r} — the workflow renamed "
        f"one of its variables, so update this test's substitution"
    )
    assert ptp.sync_source_repo(rendered) == OUR_REPO


# --- #215: the field order is a security property --------------------------
#
# Two tests, and BOTH fail against pre-#200 code — the behavioral one ON
# BEHAVIOR (that reader returns our slug for this forged history, which is the
# worked example in #215 itself), the structural one on a symbol `main` does not
# define. By the convention the #200 header sets above, both count.
#
# They are also NOT orthogonal to #200's author-as-second-signal property.
# Disable the author leg alone, keeping the shipped format, and the behavioral
# test goes red: the walk falls through the forged fragment to an older genuine
# sync of OURS and returns OUR_REPO. #200's second signal is load-bearing for
# this test's green result.
#
# An earlier draft of this header asserted the opposite on both counts. It was
# wrong, it was checkable, and it survived into a commit — in the file whose own
# #200 header says a map that miscounts its territory is worse than none.
#
# What these guard that #200's tests do not is the FIELD ORDER
# `_PROVENANCE_FORMAT` fixes — `%an` before `%s`, so the free-text field is the
# tail — held by a comment alone until #215. They sit in their own section so
# that adding them does not force a re-derivation of the #200 header's counts.


#: Line separators `str.splitlines()` folds and git's `%s` does not, so one
#: commit subject can arrive as several Python "lines".
#:
#: Two representatives of the set #215 names, chosen for different BYTE paths
#: through the real git write/read/decode round-trip: one single-byte ASCII
#: control, one 3-byte UTF-8. Branch coverage is identical either way — what the
#: second buys is a guard against a future encoding change in `_git_out`
#: handling one and not the other.
SPLIT_SEPARATORS = ("\v", "\u2028")


@pytest.mark.parametrize("separator", SPLIT_SEPARATORS, ids=("vt", "u2028"))
def test_a_split_forging_subject_cannot_forge_our_ownership(
    box: Sandbox, pages_repo: Path, separator: str
) -> None:
    """A forged sync hidden behind a `splitlines()` boundary must not read as ours.

    THE test for #215. It is load-bearing for the wiring in a way the structural
    test below is not: that one pins the constant's VALUE, while this one runs
    the real reader over real history. It is NOT the only test that would notice
    a desynced call site — review measured seven pre-existing tests reddening on
    one — so do not read exclusivity into it. Do still not delete it on the
    theory that the structural test covers the format; that theory is wrong for
    the reason above.

    The gap neither test closes, named rather than left to be discovered:
    replacing the call site with a stale LITERAL of the same value leaves the
    whole suite green. Nothing pins that git is handed the constant rather than
    something merely equal to it.

    The forgery is a commit the sync bot authored whose subject does not
    self-describe, with a well-formed sync naming US concealed behind a
    separator git stores verbatim and Python splits on. Reorder the format to
    `%s%x00%an` (unpacking coherently swapped) and the concealed fragment parses
    as ours, `git_pages_owner` returns OUR_REPO, and `assert_no_foreign_overwrite`
    permits the overwrite of a sibling-owned file.

    Under the shipped order the walk never examines that fragment at all: the
    FIRST entry is `pages-sync[bot]\x00typo fix`, whose subject does not parse
    and whose author is the sync bot, so it returns UNATTRIBUTED_SYNC there and
    stops. The general property — that a post-boundary fragment lands in the
    author slot with an empty subject — is what makes the concealed sync
    unreachable, but it is not the branch this history exercises.

    **The older sync at the top is not what makes this fail on a reordered
    format.** Under that mutation the concealed fragment parses as ours directly
    and returns before the walk ever reaches it — verified. It is here to
    reproduce #200's attack geometry faithfully, and to reinforce the
    `!= OUR_REPO` leg against a *walk-past*-class mutation, where a reader that
    returned nothing for the forged commit would resolve to this older sync of
    ours and go red. Not scaffolding, and not the primary guard either.

    The bot authorship is READ BACK rather than assumed, for the reason
    `test_a_drifted_sibling_sync_is_refused_not_walked_past` gives: a helper that
    silently failed to set it would leave this passing via the no-owner branch.
    """
    target = box.pages_assets / "forge-og.png"
    target.write_bytes(b"OURS-V1")
    _git(pages_repo, "add", ".")
    _git(pages_repo, "commit", "-q", "-m", sync_subject(OUR_REPO))

    target.write_bytes(b"THEIRS")
    forged = f"typo fix{separator}{sync_subject(OUR_REPO)}"
    _git_as(SYNC_AUTHOR, pages_repo, "add", ".")
    _git_as(SYNC_AUTHOR, pages_repo, "commit", "-q", "-m", forged)
    assert _last_author(pages_repo, target) == SYNC_AUTHOR

    # The entire security value of this test rests on the separator actually
    # producing a `splitlines()` boundary IN WHAT GIT STORED — an unasserted
    # property of SPLIT_SEPARATORS until the review that added this line. Two
    # ways it fails silently: a tuple someone edits to an ordinary character,
    # and a git that normalizes the separator away (a `commit.cleanup` setting,
    # a future version). Either leaves both assertions below passing trivially —
    # the subject stays one line, never parses as a sync, and the bot author
    # yields UNATTRIBUTED_SYNC for a reason with nothing to do with the forgery.
    # Both reviewers measured that vacuous green, one of them against the
    # REORDERED format this test exists to catch.
    stored = _last_subject(pages_repo, target)
    assert len(stored.splitlines()) == 2, (
        f"{separator!r} did not split the stored subject {stored!r} — the "
        f"forgery was never constructed and this test would be vacuous"
    )

    owner = box.ptp.git_pages_owner(target)

    # The security floor. `assert_no_foreign_overwrite` permits an overwrite ONLY
    # on `owner == source_repo`, so OUR_REPO is the one dangerous return and
    # everything else refuses. Compared with `!=`, never `is not`: the reader
    # returns a fresh `m.group(...)` string, so an identity test would pass while
    # holding the forged slug and assert nothing at all.
    assert owner != OUR_REPO, (
        f"a subject split on {separator!r} forged our ownership of a "
        f"sibling-authored target — the free-text field is no longer last in "
        f"_PROVENANCE_FORMAT"
    )
    # A D058 BEHAVIOR PIN, not the security property. A bot-authored commit with
    # an unparseable subject is definitionally an unattributable sync, so `None`
    # here would be D058-wrong while still being security-safe. If a future
    # refactor legitimately returns `None` for this case, re-judge it against
    # D058 — do not reflexively restore the sentinel to make this line green.
    assert owner is box.ptp.UNATTRIBUTED_SYNC


def test_the_provenance_format_puts_the_free_text_field_last(
    ptp: ModuleType,
) -> None:
    """The reason survives even for someone who reads only the test.

    Asserts the constant's VALUE. That is better than an `inspect.getsource`
    regex, which would keep passing if the live call changed and a stale literal
    stayed in a comment — but be precise about the limit: this lands on the
    constant, and nothing here ties the constant to the call site. The
    behavioral test above is what exercises that, and its docstring records the
    residue neither of them covers.

    Both of the sub-invariants the constant documents are pinned: the free-text
    field last (the #215 security property) and NUL as the separator, spelled
    `%x00` — git's escape for it — since an author name cannot contain a NUL, so
    the first one on an output line is unambiguously the field boundary.
    Pinning only the first would leave the second in exactly the comment-only
    state #215 exists to end.

    **What this does NOT guard**, named so the gap is known rather than assumed
    covered: `%an` → `%cn` (author-vs-committer — a different documented
    invariant, and one `_git_as` could not catch anyway since it sets both
    identities equal), and a NON-`%s` free-text field prepended before `%an`
    (`%b`, `%f`, ...). A prepended `%s` is caught, by the count assertion below —
    an earlier draft of this line claimed otherwise and was wrong three lines
    above the assertion that refutes it. Both remaining gaps are adjacent
    invariants, deliberately out of scope for #215.
    """
    fmt = ptp._PROVENANCE_FORMAT

    assert fmt.endswith("%s"), (
        f"{fmt!r} does not end with the free-text field — a subject carrying a "
        f"separator splitlines() folds can then parse as a sync on a fragment"
    )
    assert fmt.count("%s") == 1, f"{fmt!r} has more than one free-text field"
    # `%x00` is git's ESCAPE for a NUL byte — four literal characters here, not
    # a NUL. The format DECLARES the separator; only the output contains one.
    assert "%x00" in fmt, (
        f"{fmt!r} does not separate its fields with git's NUL escape (%x00) — "
        f"NUL is the one byte a commit author name cannot contain, which is "
        f"what makes the first separator on a line unambiguous"
    )
    # Presence, not position: `%x00%an %s` would satisfy this line. Position is
    # already carried by the two assertions above, which is why it is not
    # re-asserted here.


# --- #157: the bound on which repository's history gets consulted ----------
#
# Pre-#200 tests, and unchanged by it. They live below the sections above only
# because those were inserted here; the marker is what keeps them from reading
# as one.


def test_pages_dirs_inside_this_repo_are_refused(box: Sandbox) -> None:
    """The bound that actually holds — and the MECHANISM test for it.

    `REPO_ROOT` is derived from `__file__`, so this is a pure filesystem
    question with no git in it. Delete the check in `run()` and this test goes
    red, which is exactly what its predecessor could not do: that one asserted
    the not-a-checkout error, which the `toplevel is None` branch produces on
    its own, so it passed with the check deleted AND depended on where pytest
    happened to put `tmp_path`.

    What this catches is the realistic slip: pointing the Pages dirs at the
    source repo, whose targets would then be written into our own tree.
    """
    src = box.add_post("inside", "social/images/inside/og-card.png")
    inside = box.repo / "_posts"
    inside.mkdir()

    with pytest.raises(box.ptp.PublishError, match="is inside this repo"):
        box.ptp.run([src], inside, box.pages_assets, False, OUR_REPO)

    assert not (inside / src.name).exists()


def test_a_target_in_no_repository_at_all_is_refused(box: Sandbox) -> None:
    """The `toplevel is None` branch.

    Environment-dependent by nature — it needs `tmp_path` to sit outside every
    repository, which is ordinary but not guaranteed. Stated rather than
    disguised: the deterministic bound is the test above, and this one covers a
    different branch, not the same one twice.
    """
    with pytest.raises(box.ptp.PublishError, match="is not inside a git checkout"):
        box.ptp.git_pages_owner(box.pages_assets / "anything.png")
