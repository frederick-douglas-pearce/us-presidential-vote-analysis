# US Presidential Vote Analysis — Observability and Discoverability Backlog (E15)

> **Status: FILED (2026-11-13).** Epic **#500**, label `epic:observability`, `priority:high`.
> Scoped by the `pm` agent from the owner's decisions of 2026-11-13 and filed as #502–#513.
> **Each issue body is authoritative**; this file records the frame, the decisions and the
> order, and does not repeat the bodies. Decisions referenced as D0NN live in
> [`decisions.md`](decisions.md).

## Why

We do not know how much traffic the dashboard and API get, where it comes from, or which
pages are read. That gap affects design choices and budget. At filing: nothing documented how
to read traffic; request logs aged out of Cloud Logging's `_Default` bucket after its default
retention (30 days); and the dashboard had no analytics, and its `/robots.txt` and
`/sitemap.xml` answered 404.

What already existed, and stays: the daily public-surface canary (`api-canary.yml`) with its
healthchecks.io dead-man check (`docs/deploy-cloud-run.md`), the budget kill-switches on both
GCP projects (`deploy/killswitch/README.md`), post-deploy smoke checks, `gcloud logging read`
recipes in `docs/deploy-dashboard.md`, and the apex verified in Google Search Console as a
Domain property (`docs/deploy-dashboard.md` §8).

## Product frame (owner, 2026-11-13)

1. **Analytics: Umami Cloud,** on the account the blog already uses. The Hobby plan is $0
   with **one website**, 100K events/month and 6-month retention (umami.is/pricing, read
   2026-11-13), and the blog already uses that website, so the dashboard **shares it**,
   separated in reports by hostname. Each site's tag keeps its own `data-domains`. If the
   shared volume will not fit, the fallback is Cloudflare Web Analytics (#504).
2. **Pageviews plus a minimal closed event set** (#506); more events only in #513.
3. **The dashboard gets its own privacy page** (#505), with `ba` wording and the same
   contact email as the blog's privacy page, linked from every page, live before the tracker.
4. **API: index `/docs`, keep `/v1/*` out of the index.** The owner wants the architect's
   view on the design at the plan step (#509).
5. **Monitoring additions are `priority:low`** (#512): coverage already exists, and the
   analytics work may show how much more monitoring matters.
6. **Log retention is extended** within the $10/month budget, with a periodic size check
   and pruning of old logs (#502).
7. **The apex redirects to the dashboard,** a 302 that keeps the path (#510). The apex is
   meant to become a general project intro page later.
8. **UTM:** links from the blog's own posts into the dashboard use a new `utm_source` value,
   `blog`; the one live post that links to the dashboard is not retro-tagged (#507).

### Carry-forward constraints

- Cost: inside the $10/month budget.
- No visitor IP, raw user agent or other per-visitor record is committed to this public
  repo; aggregates only. Log exports are stored outside the repo.
- Reader-facing wording (privacy page, any dashboard or API text) is `ba`'s (root
  `CLAUDE.md`, "Who writes wording").
- Owner-run steps are marked in each issue; the loop prepares and records them.

## Stories and order

| Order | Issue | Story | Run | Depends on |
|---|---|---|---|---|
| 0 | #502 | Export the current log window, extend retention | **owner, this week** | — |
| 0 | #510 | Apex redirect (302, path kept) | owner, any time | — |
| 1 | #503 | Traffic inventory and runbook | loop | #502 |
| 2 | #504 | Confirm the shared Umami website fits | loop research, owner confirms | #503 |
| 3 | #505 | Privacy page | loop (`ba`) | #504 |
| 4 | #506 | Analytics on the dashboard (architect at plan) | loop, owner account steps | #504, #505 |
| 5 | #508 | robots.txt and sitemap.xml; Google and Bing submission | loop, owner submits | — |
| 6 | #507 | UTM conventions for links in | loop + Pages repo edit | #504 |
| 6 | #509 | API indexing (architect) | loop, owner edits Worker if chosen | — |
| 7 | #511 | API usage report | loop | #503 |
| 8 | #512 | Uptime and 5xx alerting (`priority:low`) | owner console, loop runbook | #503 |
| 8 | #513 | More analytics events (`priority:low`) | loop | #506 |

Across epics: E16's audit tool (#515) reads the sitemap from #508 and uses #506's analytics
opt-out, so #506 and #508 precede it.

## Facts that shape the stories (verified at scoping)

- Cloud Run sees **edge-cache misses only**: the Worker serves cached `GET /v1` 200s for
  30 days (`s-maxage=2592000`), so origin logs cannot measure API use (#503, #511).
- The e2e harness fails any browser request off the loopback host, so a tracker tag must be
  handled in the harness or omitted from the test server (#506).
- The dashboard's deploy-root allow-list (`_deploy_root_file_allowed`,
  `tests/unit/test_dashboard_guards.py`) admits only `.py` files plus `.css` under
  `explore/assets/`, so `robots.txt` and the sitemap are served by routes (#508).
- Tools that load production pages (the accessibility audit, the cold-start measurement
  script) would count as real traffic unless they opt out (#504, #506).
- The dashboard's server-side fetch User-Agent is `usvote-explore` (`explore/api.py`).

## Later / out of scope

- **The apex as a general project intro page.** Overlaps E9-S8's landing page
  (`backlog-dashboard.md`); shaping S8 decides whether the intro page is S8 or links to it.
- **A chatbot feature.** An idea only, with no issue.
- **A Content Security Policy.** None exists; #506 records what one would have to allow.
- **Self-hosted analytics,** unless #504 finds the shared website cannot work.
