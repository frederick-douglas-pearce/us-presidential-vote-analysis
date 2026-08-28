# posts/

Version-controlled markdown sources for the **"Counted, Not Assumed"** blog series —
two centuries of US presidential elections read from what the record actually says.

Mirrors the layout of the [`claude-code-sessions`](https://github.com/frederick-douglas-pearce/claude-code-sessions)
repo, which runs the same publishing pattern: posts live here, get synced to a
Jekyll-based GitHub Pages site, and carry their OG share card as a tracked build
artifact under `social/images/`.

## What belongs here

**Published posts only.** Pre-publication drafts stay in `social/drafts/`, which is
gitignored on purpose: a half-finished post about a claim that turns out to be wrong
should not be in this repo's history. A post moves here when it ships.

Each post arrives with a rendered OG card already committed under
`social/images/<YYYY-MM-DD>-linkedin-<slug>/` — see [Share cards](#share-cards).

## Frontmatter convention

```yaml
---
layout: post
title: "Post title"
date: YYYY-MM-DD 00:00:00-0800
description: "One-sentence summary used for previews and SEO"
categories: ["us-presidential-vote"]
tags: ["electoral-college", "american-history", "data-quality", "us-presidential-vote-analysis"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/<slug>-og.png
og_card_source: social/images/<YYYY-MM-DD>-linkedin-<slug>/og-card.png
featured: false
---
```

`categories` names the **series**, not the subject. Every post here is
`["us-presidential-vote"]` and stays that way: the Pages site drives its blog filter
chips off categories (`display_categories`), and this repo shares that site's `_posts/`
namespace with [`claude-code-sessions`](https://github.com/frederick-douglas-pearce/claude-code-sessions),
so the category is what lets a reader see one series without the other. Subject stays on
the **tags** axis — `american-history`, `electoral-college`, `data-quality` — which is
where it already was.

`og_image` is the published URL on the Pages site; `og_card_source` is the
repo-root-relative path to the rendered card that gets copied there at publish time.
Keep the two slugs in agreement with the filename — a mismatch is the single easiest
thing to get wrong here.

**AI-assistance disclosure is required.** Every post ends with a horizontal rule and:

```markdown
_Drafted with Claude Code. The ideas, claims, and any errors are mine._
```

## Share cards

Every post needs an OG card before it can publish. Cards are built from a committable
TOML brief so they can be re-rendered without re-prompting:

```
uv run python tooling/render-og-card.py social/images/<slug>/og-card.toml
```

The series' visual system is deliberate: **every card shows a real fragment of the
actual record**, not an illustration of one. That follows from the series premise —
read from what the record actually says instead of the shorthand everyone repeats —
and it means the chassis (dimensions, palette, type scale, wordmark) stays fixed
while only the specimen changes from post to post. `social/images/og-card-template.svg`
is the chassis.

## Editorial guardrails

Two carry over from `social/README.md` and apply to anything published here:

- **Nothing critical of a data source is ever published.** The National Archives, MIT
  Election Lab, and UCSB American Presidency Project are the sources this project
  depends on. Findings about their data go to them privately via the `outreach` lane
  in the (untracked) candidate ledger — never into a post.
- **Every historical claim is checkable and gets checked before publishing.** The
  ledger records the provenance link so the check is cheap.

## Publishing

Ported from `claude-code-sessions` in
[#132](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/132).
Four pieces, with a deliberate split: **the Action owns auth and the push; the script
owns the transform, OG resolution, and the content-compare; two PR guards keep a post
from reaching `main` in a state the site will reject.**

| Piece                                                                     | What it does                                                                         | When it runs                                                                            |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| [`tooling/publish-to-pages.py`](../tooling/publish-to-pages.py)           | Transforms frontmatter to Pages conventions, resolves + copies each post's OG card   | Called by the Action; runnable locally                                                  |
| [`.github/workflows/pages-sync.yml`](../.github/workflows/pages-sync.yml) | Cross-repo auth + the reconcile-retry push to the Pages repo                         | Push to `main` touching `posts/**` or `social/images/**`; also `workflow_dispatch`      |
| [`tooling/check-og-cards.py`](../tooling/check-og-cards.py)               | PR guard — runs the publisher's _own_ validator, so a card-less post fails on the PR | [`og-card-guard.yml`](../.github/workflows/og-card-guard.yml), on PRs and `main` pushes |
| [`.github/workflows/prettier.yml`](../.github/workflows/prettier.yml)     | PR guard — `posts/` must be Prettier-clean in the site's own dialect                 | On PRs and `main` pushes                                                                |

**Shipping a post is a merge.** Move the finished draft from `social/drafts/` into
`posts/`, open a PR — the guards check the card resolves and the markdown is
Prettier-clean — and merge. The sync runs on `main` and pushes the post plus its card
to the Pages repo.

### Prettier, and why a post can turn the site red

The publisher copies each post's body through **byte-for-byte**, and the Pages site runs
`prettier . --check` on every push to its `main`. So a post that is valid markdown but
not _Prettier's_ markdown fails on the site rather than here — and keeps failing, because
the site's daily ESG cron re-runs the same check every morning on the same file.

That is not hypothetical. It bit a post in `claude-code-sessions` on 2026-06-08, which is
why that repo has this gate; #132 ported the publisher here without it, and post 1 did the
same thing to the site on 2026-08-12.

Run it before opening the PR — the gate does this in CI, but locally it is one command:

```
npm ci            # first time only
npm run format:check
npm run format:write   # fix
```

The trap that has now caused both incidents: **Prettier normalizes emphasis to
`_underscores_`**, and `*asterisks*` are not a configurable alternative. Tables get their
pipes padded, too.

Two scoping notes. The gate covers **`posts/` only** — `.prettierignore` ignores
everything and then unignores `posts/`, because the rest of the repo (`docs/`, `social/`,
`.claude/` specs, CLAUDE.md) is authored to other conventions. And the formatter is
pinned to the **exact** versions the Pages site pins, `prettier` 3.9.5 with
`@shopify/prettier-plugin-liquid` 1.11.0, installed via `npm ci` from the lockfile. Caret
ranges would let this gate drift a version away from the site's, which is the one way it
can pass here and still fail there.

Four properties are load-bearing; a change that keeps the code but loses one of these
produces something that looks the same and fails differently:

1. **OG resolution is fail-closed, never a glob.** A missing `og_card_source`, an
   absolute or repo-escaping path, a missing source file, a missing `og_image`, or two
   posts colliding on one target all abort with **zero writes**. A wrong image shipped
   under a green Action is the failure mode the design exists to prevent.
2. **Idempotency is content-compare, not push-diff.** Outputs are written only when
   their bytes differ, so a re-run makes no spurious changes and no empty commit.
3. **Atomicity is validate-all-then-write.** The full plan is built and validated before
   a single byte is written, so one bad post can't half-publish a batch.
4. **The guard reuses the publisher's `build_plan`** rather than re-deriving the rules,
   so it cannot drift. A future fail-closed condition is inherited for free.

### Previewing a publish locally

`--dry-run` resolves and compares but writes nothing. Point it at a real checkout of the
Pages repo:

```
uv run python tooling/publish-to-pages.py posts/YYYY-MM-DD-<slug>.md \
    --posts-dir  /path/to/frederick-douglas-pearce.github.io/_posts \
    --assets-dir /path/to/frederick-douglas-pearce.github.io/assets/img \
    --source-repo us-presidential-vote-analysis \
    --dry-run
```

The same preview is available in CI: **Actions → Pages sync → Run workflow → tick
`dry_run`**. That does a real Pages checkout with the real token and writes the planned
diff to the job summary, without committing.

That dispatch offers a branch picker, and **only `main` publishes**: a dispatch from any
other ref must have `dry_run` ticked or the run refuses, so an unreviewed draft on a
feature branch cannot reach the live site through the preview path.

To check the cards without a Pages repo at all (what CI does on every PR):

```
uv run python tooling/check-og-cards.py
```

### One-time owner setup

The sync cannot publish until this exists, and the ordering is deliberate: the workflow
checks for publishable posts **before** it requires the token. So while `posts/` holds
only this README the sync is genuinely inert — it exits green with "nothing to publish"
and never asks for a secret. The moment a dated post lands without the setup done, the
**preflight fails loud** rather than silently skipping. Both states are honest; neither
is a red `main` for a repo that has nothing to publish yet.

1. **Create a fine-grained PAT.** GitHub → Settings → Developer settings → Personal
   access tokens → Fine-grained tokens → _Generate new token_.
   - **Repository access:** _Only select repositories_ → **the Pages repo only**
     (`frederick-douglas-pearce.github.io`). It must not be able to write to this repo.
   - **Permissions → Repository permissions:** **Contents: Read and write**. Nothing else.
     (Metadata: Read-only is added automatically and is required.)
   - Name it for the source repo — `claude-code-sessions` needs its own separate token,
     and you want to tell them apart when revoking. GitHub caps the name length, so a
     shortened form is fine; the token's name is a display label and nothing reads it.
     (Ours is `pages-sync-from-us-presidential-vote`.)
2. **Create the environment.** This repo → Settings → Environments → _New environment_,
   named exactly **`pages-sync`** (the workflow's `environment:` key matches this string
   literally).
3. **Add the secret** inside that environment: name **`PAGES_SYNC_TOKEN`**, value the
   token, **with no trailing newline**. It must be an _environment_ secret, not a
   repository secret — scoping it there means only a job that opts into `pages-sync` can
   reach it.
4. **Verify** with the `dry_run` dispatch above before trusting the first real publish.

The default `GITHUB_TOKEN` cannot write to another repo, which is the whole reason for
the PAT. The workflow declares `permissions: contents: read` and needs nothing more from
this repo, and the token is never echoed — it lives only in `pages/.git/config` inside
the runner.

### Two things to know about the shared Pages site

That site also receives posts from `claude-code-sessions`, and the Pages repo has its own
daily ESG-feed cron. Two consequences:

- **Slugs share a namespace, and a clash now fails loud instead of overwriting.** The
  card target is derived as `assets/img/<basename of og_image>`, and `build_plan`'s
  collision check sees only _this_ repo's posts — so a clash with the other publisher
  enters neither repo's plan. Since #157 the publisher also refuses to overwrite a target
  it does not own: before any write, an existing target whose bytes differ must have been
  written last by a sync from **this** repo, per the Pages repo's own commit history.
  Otherwise the run aborts, having written nothing. Three things to know about it:

  - **It fires at publish, never on the PR.** `tooling/check-og-cards.py` runs the
    publisher's Phase-1 validator with no Pages checkout, so it cannot see the other
    repo's slugs. A colliding slug passes CI green and stops at the sync.
  - **It is one-sided until `claude-code-sessions` ports it.** This repo will not
    overwrite a card that repo owns; the reverse is not yet true. So the first symptom is
    likely to be **our** publish failing over an overwrite it did not cause — that is the
    intended trade (loud beats a wrong share image on a green run), not a bug.
  - **So keep the slug distinct across the two series anyway.** The guard turns a silent
    corruption into a stopped publish; it does not make the namespace safe to share.

- **Pushes race.** The Action reconciles rather than force-pushing: on rejection it
  fetches, resets to the moved tip, **re-transforms against it**, and retries (bounded,
  then fails loud). Nothing another writer put there is clobbered.
