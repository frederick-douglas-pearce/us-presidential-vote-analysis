# US Presidential Vote Analysis — Accessibility Backlog (E16)

> **Status: FILED (2026-11-13).** Epic **#501**, label `epic:accessibility`, `priority:high`.
> Scoped by the `pm` agent from the owner's decisions of 2026-11-13 and filed as #514–#520.
> **Each issue body is authoritative**; this file records the frame, the label policy and the
> order, and does not repeat the bodies.

## Why

The dashboard is public and aimed at non-technical readers, but it had never had an
accessibility audit. The code already applied some rules (aria work, WCAG 1.4.1 and 1.4.11
checks on charts, contrast tests on theme tokens), yet nothing confirmed it meets current
standards or guided design. The owner's page-by-page UX review, filed into E14 (#361) on a
rolling basis, needs a baseline to start from.

## Product frame (owner, 2026-11-13)

1. **Target: WCAG 2.2 Level AA.**
2. **The automated gate is on demand for the MVP,** following the Pages site's pattern
   (frederick-douglas-pearce.github.io: `bin/a11y-audit.js`, axe-core through Playwright over
   every sitemap URL in both themes; `doc/a11y-baseline.md`, where dark mode was 2.8× worse
   than light). CI integration is the follow-up #520.
3. **E16 owns measurement and conformance, never fixes.** See the label policy below.
4. The public statement claims no conformance beyond the evidence (#519).

## Label policy (owner, 2026-11-13)

- A fix lands in the epic that owns the code, by E14's routing test ("would the change look
  the same whatever the data?" → E14, else E9), and carries the `a11y` label.
- Cross-cutting presentation fixes (theme tokens, the site header and nav, focus ring,
  shared components such as the dropdown helper #475) go to **E14**, never E16.
- API `/docs` findings go to `epic:internal-api`.
- E16 owns the audit tool, the baseline, the manual-check protocol, the statement and the
  CI gate. Its tracker links the `a11y` label search, so open findings stay visible in one
  place.

E14's scope line names accessibility; it now reads as accessibility *fixes* to presentation
(`docs/ROADMAP.md`, `backlog-dashboard.md` §E14).

## Stories and order

| Order | Issue | Story | Run | Depends on |
|---|---|---|---|---|
| 1 | #514 | UX-review issue form with an accessibility checklist | loop | — (before the owner's review) |
| 2 | #515 | Audit tool: axe-core through Python Playwright, Light/Dark, 390/1280 px, open controls | loop | after #486; uses #506's opt-out and #508's sitemap once they exist |
| 3 | #516 | Baseline audit, recorded in `docs/a11y-baseline.md` | loop | #515 |
| 4 | #517 | Manual checks: keyboard, screen reader (Orca), open controls, chart alternatives | owner pass, loop records | #516 |
| 5 | #518 | File findings as root-cause issues in their owning epics | loop or `pm` | #516, #517 |
| 6 | #519 | Public accessibility statement (`ba`) | loop | #516, #517, #505 |
| 7 | #520 | CI gate on new serious or critical violations (`priority:low`) | loop | #515, #516, #486, #518 |

#444 (E14) was amended on filing: its automated-check criterion moved to #515 and #520, and
it keeps the radio/checkbox semantics fix.

## Notes for the stories

- axe cannot see collapsed content, so #515 scripts open-control states and #517 covers the
  rest by hand.
- Every chart already has a companion table, a table pointer and a drawing named by its
  title (`dashboard/CLAUDE.md`), so #517 checks chart alternatives rather than assuming they
  are missing.
- Tools that load production pages opt out of analytics (#504, #506).

## Out of scope

Fixing findings (they live in their owning epics). The Pages blog (its own repo and
baseline). Swagger UI's internal markup on the API's `/docs` (third party; findings are noted,
not fixed here).
