# US Presidential Vote Analysis — Roadmap

> **Status: the plan held; most of it is built.** This document is kept as the
> *planning* record — milestone themes, epic boundaries, and the reasoning behind them.
> E1–E6 and E8 have since landed, E7 is partly landed, and E9 has not started; see
> [Where it stands](#where-it-stands-2026-08-19) immediately below for the delivery
> status, which is the section to trust when the two disagree. Decisions referenced as
> D0NN live in [`../.claude/specs/decisions.md`](../.claude/specs/decisions.md).

This document frames the thesis, then lays out a milestone plan from the current
"seed" repo through an MVP and into stretch scope. Per-milestone entries cover the
**theme** and headline scope. A first-cut **epic outline** (E# handles) at the
bottom is what the backlog expands into GitHub issues and stories.

## Where it stands (2026-08-19)

| Epic | Status |
|---|---|
| **E1** `src/` package scaffolding | **Done** (#11) — `uv` + pytest + mypy + ruff, enforced in CI |
| **E2** EC ingestion refactor + extension | **Done** (#12) — the notebook's scrape/transform/load runs as `usvote`, and EC coverage is **complete for 1824–2024**; `UNSUPPORTED_EC_YEARS` is empty. The two contested Reconstruction elections closed it out (1868 in #143, 1872 in #144), adding a `count_status` fact column and a **counted** electoral-vote measure beside the **cast** one |
| **E3** PV-source research | **Done** (#13) — settled the dual-source approach (D014) |
| **E4** UCSB historical PV ingest | **Done** (#33) — parses six header eras across ~1824–1972; non-redistributable, so no UCSB bytes are committed and its acceptance corpus lives outside the repo (D022/D023) |
| **E5** MIT PV ingestion | **Done** (#62) — the CC0 1976–2024 core |
| **E6** Canonical key + cross-source join | **Done** (#63) — `ec_pv_preferred` (analysis) and `ec_pv_redistributable` (public), joined EC-left on the canonical `(year, state, candidate)` grain |
| **E7** Hybrid computation | **Done** (#120) — the three-method computation core is built (`usvote/hybrid.py`, #121/#122): EC share, PV share, the hybrid average, `ec_determinative`, and EV-weighted coverage. **Done** — flip detection and three-method margins (#123), the four materialized views (#124), the partial-coverage note (#125) and the D017 layer-3 overlap gate (#167) all landed |
| **E8** Internal API | **Done, and past its MVP bar** (#94) — a read-only SQLite snapshot served by FastAPI with no live DB (D028), publicly deployed to Cloud Run behind Cloudflare and **live at `https://api.us-presidential-election-center.org`** (#101, D034/D035). The served window was widened from the MIT-only 1976–2024 back to the full **1824–2024** EC span in #139. **Open:** hybrid/flip/margin fields (#102) — E7 has landed, so this is no longer gated |
| **E9** Analytical explorer data mart | **Not started** |
| **E10** Census / apportionment analysis | **Not started** (#129) — added after this outline was written |
| *(unnumbered)* Publishing | **Done and in use** — see below |

Two workstreams sit outside the original E1–E9 outline:

- **Publishing** (`epic:publishing`) — anticipated only as a one-line `social/`
  placeholder under Stretch, now a real workstream: the **"Counted, Not Assumed"** blog
  series, live at <https://frederick-douglas-pearce.github.io/blog/>, with a fail-closed
  publish path to a Jekyll Pages site plus two PR guards (#132, #152, #156, #158). Two
  posts are published as of this revision.
- **E10, the census epic** (#129), which is where the deferred per-capita apportionment
  analysis would live.

The **critical-path bet stated below held**: E6 unblocked the E8 API MVP directly, and
the API shipped and deployed without waiting on E7.

## The thesis (the "why")

Analyze historical US presidential elections to compare three ways of determining
the winner: (a) the **Electoral College** (EC), (b) the national **Popular Vote**
(PV), and (c) a novel **hybrid** — the average of the EC and PV outcomes (Fred's
original contribution). The core questions: **how many elections would have flipped**
under PV or the hybrid, and **how would the margins differ?**

**Current-events relevance.** The National Popular Vote Interstate Compact
([written explanation](https://www.nationalpopularvote.com/written-explanation))
currently holds 222 of the 270 electoral votes needed to activate. It cites exactly
the statistics this pipeline would produce — 5 of 47 presidents took office without
the popular-vote lead; battleground concentration; 2024's ~240k national PV margin
decided by a few thousand swing-state votes. A cleanly joined EC+PV dataset on a
shared state/candidate model does not appear to exist publicly anywhere. That
scarcity is itself a motivation: the dataset is a deliverable, not just an input.

## Guiding stars

- **Near-term analytical star:** an interactive EC-vs-PV-vs-hybrid "what-if"
  explorer answering *"would this election have flipped, and by how much?"* with
  maps and narrative (D001). The presentation platform/frontend is **deferred** —
  do not design it yet.
- **Infrastructure backbone:** graduate from the monolithic notebook to a tested,
  reproducible `src/` package so the numbers are trustworthy; new data ingested
  every 4 years (D003).
- **Standalone deliverable:** a **public API** over the joined dataset. MVP bar is
  "the API powers our app"; a fully public/third-party API is a stretch goal gated
  on PV-data licensing (D002).

**Status legend (as originally written):** "done" = present in the seed repo; "draft" =
scoped here but not committed; "later" = explicitly deferred. Delivery status since then
is in [Where it stands](#where-it-stands-2026-08-19), not in these labels.

---

## Seed (the starting point, since superseded)

**This describes the repo as it was when the roadmap was written, not as it is now** —
kept because the milestones below are written against it. The repository then: one
monolithic Jupyter notebook
(`step1_electoral_college_data.ipynb`) that scrapes EC results from the National
Archives and loads a Postgres star schema (`dwh`: `state` dim, `candidate` dim,
`votes` fact), plus `db_tools.py` (a thin psycopg2 wrapper, `DBC`), README, LICENSE,
and CLAUDE.md. EC data is loaded and row-validated; a Looker prototype exists but is
**not** the intended host. Popular-vote ingestion and the analysis layer are unbuilt.

---

## M1 — "Trustworthy Backbone" (draft)

**Theme:** make the numbers reproducible and testable before building analysis on
top of them. Graduate the notebook into an `src/` package mirroring the agentfluent
layout (uv, pytest, CI), and refactor EC ingestion into that package while extending
coverage. The thesis is only as credible as the pipeline underneath it.

- `src/` package scaffolding — tested, reproducible pipeline (**E1**).
- EC ingestion refactored out of the notebook into `src/`, coverage extended from
  the current 1892 floor toward 1789, with the structurally-uniform post-1804 era as
  the MVP spine and contingent elections (1800/1824 House, 1836 Senate VP) represented
  as a modeling nuance (**E2**; D005, D010). *Landed as 1824–2024 complete — 1824's
  House contingency is modeled via `took_office`, and 1789–1820 stays its own deferred
  epic as planned.*
- The existing notebook's inline validations and hardcoded historical corrections are
  preserved as tests/fixtures, not lost in the migration.
- **Runs in parallel:** the PV-source research spike (**E3**) starts here so MIT PV
  ingestion is unblocked when M2 opens (the UCSB historical ingest is un-deferred and
  can begin once the `src/` backbone lands — see M2).

---

## M2 — "The Popular-Vote Linchpin" (draft)

**Theme:** ingest PV from two complementary sources and join it to EC on a shared
spine. This is the critical path — the entire thesis is blocked until PV data lands and
reconciles against EC (D004). Per **D014**, PV is a **dual-source** effort: **MIT
Election Lab (1976–2024)** is the clean, structured, **API-eligible modern core**
covering the 2000/2016 splits, and **UCSB / American Presidency Project (~1824–1972)**
is the **historical-breadth layer**, ingested for analysis and flagged
**non-redistributable** pending a license answer. Provenance and redistributability are
first-class per-source data attributes (D005, D014).

- **UCSB historical PV scrape + ingest** (**E4**; D005, D014) — scrape/snapshot the
  messy, era-drifting UCSB HTML, parse across eras, transform/validate into state-level
  PV records tagged `source=UCSB`, `redistributable=false`, with provenance/reliability
  flags. **Un-deferred and high-priority** — UCSB is the only source reaching ~1824, so
  its necessity does not depend on E3's licensing outcome. Scoped in the backlog and
  filed as issues. It mirrors the EC ingestion architecture (E2), because raw UCSB HTML
  is substantially harder than the clean MIT CSV.
- **MIT PV ingestion** (**E5**; D008, D014) — load the clean MIT 1976–2024 CSV as the
  API-eligible modern core, tagged `source=MIT`. Named but not yet scoped; the
  redistribution question is gated on E3's MIT licensing finding.
- **Canonical candidate/state key + cross-source join** (**E6**; D006) — conform both PV
  sources onto the EC spine (E2-S9), with EC (National Archives) as the source of truth.
  MIT and UCSB name formats both differ from the Archives and reconcile via the canonical
  keys.
- **MVP comparison window** may start ~1824 (D009): MIT covers the modern splits, UCSB
  supplies the pre-1976 breadth.
- **MIT outreach (deferred):** two MIT-side contacts — **Zayne Sember**
  ([LinkedIn](https://www.linkedin.com/in/zaynesember/); published the 1976–2024 file;
  lead) and **Sean Greene** ([LinkedIn](https://www.linkedin.com/in/sean-greene-a467097/);
  additional contact) — are the path to resolve MIT's license terms and a possible
  pre-1976 coverage extension. Outreach waits until analysis back to 1976 is in hand;
  mechanics TBD (D014).

---

## M3 — "The What-If Explorer" (draft — MVP target)

**Theme:** deliver the analytical guiding star. Compute the three outcomes, detect
flips and margins, and expose them through an internal API that powers our app.

- Hybrid computation — average of EC and PV, flip detection, margin comparison across
  all three methods (**E7**; D011). The detailed hybrid written spec (including the
  no-270 contingent-election treatment) is a named future workstream, not an M3 blocker.
- Analytical explorer data mart — the query surface behind flips/margins/maps/narrative
  (**E9**).
- Internal API — exposes the joined dataset; **MVP bar = it powers our app** (**E8**;
  D002). Excludes `redistributable=false` rows from any public-facing surface (D014).
  Frontend/presentation platform remains out of scope.

---

## Stretch / Later

- ~~**Public / third-party API**~~ — **SHIPPED** (E8-S6/S7, #100/#101; D032–D035). The
  internal API graduated to a public surface, live at
  `https://api.us-presidential-election-center.org`, and the licensing gate was met by
  serving only the redistributable subset: MIT (CC0) for the popular vote and the
  public-domain National Archives for the electoral college. UCSB remains analysis-only
  and never reaches the public surface (D030), enforced structurally rather than by
  convention.
- **Pre-12th-Amendment epic** — model the 1789–1800 elections, where each elector cast
  two presidential votes and the runner-up became VP; structurally distinct from modern
  tables, so its own epic (D010).
- **Granular PV detail** — county-level or by-source PV enrichment beyond MVP totals (D007).
- **Minor PV-only candidates** — candidates who received popular votes but no electoral
  votes; non-blocking nice-to-have (D007).
- **Hybrid no-270 legal treatment** — the "no candidate reaches 270" ambiguity relevant
  to the hybrid method; parked for a later decision (D010).
- **Presentation platform** — the actual frontend/dashboard host; deferred (D001).
- ~~**`social/` content**~~ — **REAL, and in use** (D012). Became the **"Counted, Not
  Assumed"** blog series (<https://frederick-douglas-pearce.github.io/blog/>) plus the
  fail-closed publish path and PR guards described in the README. `social/` itself stays
  git-ignored working state; published post sources live in `posts/`.

---

## First-cut epic outline

Handles are tentative; the backlog expands each into a GitHub epic issue with child
stories (agentfluent `E#` / `E#-S#` convention, `epic:<slug>` labels). All nine were
subsequently filed, and E10 (census) was added later. The **Milestone** column below is
the original plan; the **Status** column is where each one actually got to.

| Handle | Epic | One-line scope | Milestone (planned) | Status |
|--------|------|----------------|---------------------|--------|
| **E1** | `src/` package scaffolding | uv + pytest + CI; reproducible tested pipeline layout mirroring agentfluent | M1 (filed) | **Done** (#11) |
| **E2** | EC ingestion refactor + extension | move Archives scrape/transform/load into `src/`; extend toward 1789; represent contingent elections | M1 (filed) | **Done** (#12) — 1824–2024 complete |
| **E3** | PV-source research | characterize MIT vs. UCSB; MIT licensing finding for the public-API gate | M1 (spike, filed) → gates E5 | **Done** (#13) |
| **E4** | UCSB historical PV scrape + ingest | scrape/parse/transform/load messy UCSB HTML → state-level PV; `source=UCSB`, `redistributable=false`; ~1824–1972 breadth | M2 (scoped + filed; un-deferred) | **Done** (#33) |
| **E5** | MIT PV ingestion | load clean MIT 1976–2024 CSV; API-eligible modern core (covers 2000/2016 splits); `source=MIT` | M2 (named) | **Done** (#62) |
| **E6** | Canonical key + cross-source join | shared candidate/state spine; conform MIT + UCSB onto EC as source of truth | M2 (named) | **Done** (#63) |
| **E7** | Hybrid computation | EC/PV average; flip detection; three-method margin comparison | M3 (named) | **Done** (#120) |
| **E8** | Internal API | FastAPI/REST over `ec_pv_redistributable` via a read-only embedded snapshot (no live DB); redistributable-only; MVP bar = powers our app; **depends only on E6, not E7** (D028–D032) | M3 (scoped + filed, #94) | **Done + publicly deployed**; #102 open |
| **E9** | Analytical explorer data mart | query surface for flips/margins/maps/narrative | M3 (named) | Not started |
| **E10** | Census / apportionment analysis | state population + apportionment; the per-capita elector-weight drift question | *(added later)* | Not started (#129) |

**Critical path:** E1 → E2 (backbone) with E3 running in parallel. PV is dual-source
(D014): **E4 (UCSB historical, un-deferred, high-priority)** and E5 (MIT modern) feed E6
(canonical join). **E6 then unblocks the E8 API MVP directly** — the API serves
`ec_pv_redistributable` and does **not** wait on E7 (D029). E7 + E9 → the explorer, and
E7 later feeds E8's hybrid/flip/margin fields (E8-S8, gated on E7). PV ingestion and the
`src/` backbone precede the explorer and API by design.

---

## Open Questions / Risks

These are **not fully decided** — they are surfaced for Fred, and most become their own
decision or research task later.

1. **PV licensing + coverage (highest risk).** Direction is set per D014: dual-source —
   MIT (1976–2024, API-eligible) + UCSB (~1824–1972, analysis-only, non-redistributable
   pending a license answer). The open risk is MIT's exact license terms for public API
   redistribution and whether MIT coverage can be extended pre-1976 — both pursued via
   named MIT-side contacts (Zayne Sember, Sean Greene), with outreach deferred until
   analysis back to 1976 is in hand (E3, D008, D014).
2. **Fate of the existing notebook.** Keep it as a research artifact vs. fully migrate
   into `src/` — an architecture decision, deferred to E1/E2 design.
3. **API + DB hosting.** **API-hosting half RESOLVED (D032/D034/D035)** — the API deploys
   to Cloud Run behind Cloudflare (free), keyless via WIF (E8-S7, #101), and has since gone
   live at `https://api.us-presidential-election-center.org`. The **DB-hosting**
   half remains open: the warehouse is still local Postgres, read only at snapshot-build
   time (D028), so no live DB is hosted; whether/where to host Postgres is still undecided.
4. **Detailed hybrid-method spec.** Including the no-270 contingent-election legal
   treatment. Largely settled in Fred's head but unwritten; a named future workstream,
   not an MVP blocker (D010, D011).
5. **PV data quality pre-1824.** How far back a *meaningful* comparison is honest, given
   states that chose electors by legislature. MVP may start the comparison at 1824 (D009).
   **Partly answered (D024, #139/#140).** The comparison window does start at 1824, and the
   "chose electors by legislature" case is no longer a caveat in prose — it is a modeled
   value. Every `(year, state)` back to 1824 carries a `pv_status` of `popular_vote`,
   `legislature_chosen`, or `not_participating`, so a null popular vote always says *which
   kind* of null it is, and coverage is reported as an EV-weighted number rather than
   inferred from missing rows. The 32 pre-1976 absences are curated in
   `usvote/pv/absences.py` from **public-domain** citations, deliberately not from UCSB, so
   the classification can ship publicly. What remains open is the analytical judgment the
   question actually asks: how much pre-1976 coverage is *enough* for a given election's
   comparison to be worth publishing (#125).
6. ~~**Shared PV record schema.**~~ **RESOLVED (D018/D021)** — and resolved with its premise
   reversed. This question assumed E4 (UCSB) would define a minimal schema MIT could conform to.
   In the event **MIT landed first**: D018 settled the shared PV record shape and D021 finalized
   and shipped the `dwh.pv_votes` DDL, with `candidate_votes`/`state_total_votes` **NOT NULL**
   enforced for every source at the shared write boundary. **UCSB conforms to that table
   as-shipped and does not redefine it.** UCSB's one genuinely un-shared need — popular-vote
   *absence*, which has no MIT analogue post-1976 — is met by a **sibling** table
   (`dwh.pv_state_status`) rather than by amending the shared fact, per **D024**.
