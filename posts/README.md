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
categories: ["american-history"]
tags: ["electoral-college", "american-history", "data-quality", "us-presidential-vote-analysis"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/<slug>-og.png
og_card_source: social/images/<YYYY-MM-DD>-linkedin-<slug>/og-card.png
featured: false
---
```

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

## Not yet ported

The publish path from `claude-code-sessions` is **not** wired up here yet — tracked in
[#132](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/132),
which captures the port's design constraints and the required one-time PAT setup:

- `tooling/publish-to-pages.py` — resolves each post's `og_card_source`, copies the
  rendered card into the Pages repo, and fails closed if it can't.
- `.github/workflows/pages-sync.yml` — runs the publisher on push to `main`.
- `tooling/check-og-cards.py` — a PR guard that runs the publisher's *own* validator
  on PRs, so a post merged without its card fails on the PR rather than turning
  `main` red afterward. (That is not hypothetical; it happened in the source repo.)

Until those land, publishing is manual. Port them before the first post ships, or
accept that the card/URL wiring is checked by eye.
