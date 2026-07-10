# Decision Log

Append-only log of significant trade-off decisions made during US Presidential Vote
Analysis development. Format mirrors the sibling agentfluent project: each entry is
`## D0NN: <title>` with **Date**, **Context**, **Decision**, **Rationale**, and an
optional **Action required**.

---

## D001: Analytical guiding star — the EC-vs-PV-vs-hybrid what-if explorer

**Date:** 2026-07-05
**Context:** The project could aim first at a polished presentation surface (a Looker
prototype already exists) or at the analytical capability underneath it. We need a
single near-term star to sequence everything else against.
**Decision:** The first milestone to aim toward is an interactive "what-if" explorer
answering *"would this election have flipped under PV or the hybrid, and by how much?"*
with maps and narrative. The presentation platform / frontend host is **deferred** —
we do not design the frontend now, and the existing Looker prototype is not the
intended host.
**Rationale:**
- The differentiated value is the analysis and the cleanly joined dataset, not the
  chart-rendering layer, which is commodity and swappable.
- Committing to a frontend now would force premature hosting and UX decisions before
  the data model that feeds them is trustworthy.
- A crisp analytical question ("flip and by how much") gives every upstream epic a
  concrete target to conform to.

---

## D002: Public API is a first-class standalone deliverable

**Date:** 2026-07-05
**Context:** The joined EC+PV dataset is valuable in its own right — no equivalent
appears to exist publicly. The API could be treated as mere plumbing for our app, or
as a deliverable in its own right.
**Decision:** A public API over the joined dataset is a first-class standalone
deliverable. The **MVP bar is "the API powers our app."** A fully public /
third-party-developer API is a **stretch goal, gated on PV-data licensing** permitting
redistribution.
**Rationale:**
- The scarcity of a cleanly joined EC+PV dataset means exposing it has independent
  value to third-party developers and researchers.
- Setting the MVP bar at "powers our app" keeps the near-term scope bounded while
  building the API surface in a way that can graduate to public later.
- Third-party exposure hinges on redistribution rights we do not yet have (see D008),
  so it cannot be an MVP commitment.

---

## D003: Adopt a tested `src/` package + reproducible pipeline (retire the monolith)

**Date:** 2026-07-05
**Context:** The pipeline today is a single monolithic Jupyter notebook plus a thin
psycopg2 wrapper. That is fine for a seed but insufficient for numbers that must be
trustworthy and re-runnable every four years.
**Decision:** Adopt an `src/` Python package with a reproducible, tested pipeline,
mirroring the sibling agentfluent project's layout and conventions (uv, pytest, CI).
Replace the monolithic notebook **incrementally**. Target a 4-year ingestion cadence
(new data each presidential cycle).
**Rationale:**
- The thesis is only as credible as the pipeline underneath it; tests and
  reproducibility are the credibility.
- Mirroring agentfluent reuses proven conventions and lowers the cost of context-switching
  between the two repos.
- Incremental replacement preserves the notebook's dense inline validations and
  hardcoded historical corrections rather than discarding hard-won correctness.

**Action required:** M1 must decide the fate of the existing notebook (keep as research
artifact vs. fully migrate) as part of E1/E2 design — recorded as an open question, not
settled here.

---

## D004: Popular-vote ingestion is the critical-path linchpin

**Date:** 2026-07-05
**Context:** EC data is already loaded; PV data is not. The entire comparative thesis
(flips and margins under PV and the hybrid) is impossible without PV.
**Decision:** Treat PV ingestion as the critical-path linchpin. It is sequenced ahead
of the explorer and API, immediately after the `src/` backbone is in place.
**Rationale:**
- Nothing downstream — hybrid computation, flip detection, the explorer, the API — can
  begin producing thesis output until PV data exists and reconciles against EC.
- Naming it the linchpin makes the sequencing non-negotiable: backbone first, PV
  second, analysis third.

---

## D005: EC coverage expands to 1789–2024; PV gaps handled honestly

**Date:** 2026-07-05
**Context:** CLAUDE.md/README describe a 1892 EC floor. The National Archives now
publishes results back to 1789, and Fred has confirmed the Archives data is unrestricted.
PV, by contrast, is patchy or absent in the early republic.
**Decision:** Expand EC coverage to **1789–2024** — the old 1892 cutoff is obsolete.
Where PV is **unavailable**, handle it gracefully (no fabricated values); where PV is
**available-but-unreliable**, flag it explicitly with provenance. Authentic historical
representation is treated as a **product feature**, not an edge case.
**Rationale:**
- The Archives data being unrestricted removes the reason for the old floor.
- Surfacing PV gaps and reliability honestly is exactly the kind of provenance
  serious users (the NPVIC audience, researchers) need; hiding it would undermine trust.
- Provenance flags turn "missing data" from a defect into documented historical fact.

---

## D006: EC (National Archives) is the source of truth; canonical keys are the shared spine

**Date:** 2026-07-05
**Context:** Two datasets from two sources (Archives EC, TBD PV) must be joined.
Without a governing key and a designated authority, reconciliation conflicts have no
tiebreaker.
**Decision:** EC data from the National Archives is the **source of truth** for
reconciliation. A **canonical candidate key** and a **canonical state key** are the
shared spine that both datasets conform to.
**Rationale:**
- The Archives is the authoritative, unrestricted EC record; anchoring reconciliation
  to it gives every join a deterministic tiebreaker.
- Canonical keys absorb the messy real-world variance already seen in the EC data
  (name mismatches, split names, multi-party/multi-state candidates) into one spine
  the PV data must match, rather than reconciling ad hoc per join.
**Implemented by:** issue #30 — the EC-side keys are established, documented, and tested;
see [`docs/canonical-keys.md`](../../docs/canonical-keys.md) for the two-tier definition
(display PK vs. match target) and the `candidate_id`-is-not-canonical rule. The
cross-source join that consumes them is deferred to E6.

---

## D007: MVP candidate scope = candidates who received electoral votes

**Date:** 2026-07-05
**Context:** PV records include many minor candidates who never received an electoral
vote. Including all of them expands the candidate dimension and the reconciliation
burden substantially.
**Decision:** MVP candidate scope is **any candidate who received electoral votes**.
Minor PV-only candidates are tracked as **non-blocking nice-to-haves**. PV is provided
as **totals first**, with more granular detail added later by priority.
**Rationale:**
- Candidates with electoral votes are the ones that can change an EC/PV/hybrid outcome —
  the thesis-relevant set.
- Anchoring the candidate dimension to the EC-bearing set keeps it aligned with the
  source of truth (D006) and bounds reconciliation.
- PV totals are sufficient for flip-and-margin analysis; granularity is enrichment.

---

## D008: PV data source — pursue MIT Election Lab over UCSB / APP

**Date:** 2026-07-05
**Context:** Candidate PV sources include the MIT Election Data + Science Lab
(open-licensed state-level returns) and UCSB's American Presidency Project. Licensing
terms determine whether we can redistribute PV via a public API (see D002).
**Decision:** Pursue **MIT Election Lab** (open-licensed, state-level returns; Fred is
an MIT alum with a potential line to the lab director) over UCSB / American Presidency
Project, which has not replied on licensing and is deprioritized. The **final source
determination is its own research task** (epic E3), not settled by this decision.
**Rationale:**
- MIT's open licensing is the most promising path to the public-redistribution rights
  the stretch public API needs (D002).
- The alumni contact is a potential accelerant for licensing clarity.
- UCSB's licensing silence makes it a redistribution risk; deprioritize rather than block on it.

**Action required:** E3 (PV-source research) resolves the final source and confirms
whether its license permits public API redistribution. Open until then.

**Refined by:** D014 — the either/or framing here is superseded by a **dual-source** PV
strategy (MIT for the redistributable modern core + UCSB for historical breadth). D008
stands as the record of why MIT is the preferred *redistributable* source; see D014.

---

## D009: MVP comparison window starts at ~1824 (retained, mutually-agreed pending)

**Date:** 2026-07-05
**Context:** EC data extends to 1789 (D005), but the national popular vote is patchy in
the early republic. The choice was between anchoring the MVP comparison at ~1824 —
messy, but the first cycle with broad popular participation — versus starting at 1828,
which is cleaner (the first modern-style two-party popular election). 1824 itself is a
contingent election decided in the House, and six states still chose electors by
legislature that year.
**Decision:** **Retain ~1824 as the MVP comparison start** — do not push to 1828. EC
coverage still extends back to 1789 per D005; the *comparison* (flips/margins vs. PV
and hybrid) is what begins at ~1824. This is a **mutually-agreed pending** call — the
direction is set, but it is explicitly open to revisiting before implementation, since
serious data work (E3/E4) precedes any analysis and may surface reasons to adjust.
**Rationale:**
- 1824's messiness is a **narrative opportunity, not a defect.** The House contingent
  outcome and the legislature-chosen electors are exactly the phenomena the project
  exists to illuminate; starting at 1828 would silently bypass the very conditions that
  *made* 1828 cleaner and conformant to modern norms — dishonest, and a missed teaching
  moment.
- The provenance-first stance (D005) already commits us to representing unreliable or
  structurally-unusual data with flags rather than hiding it; 1824 is the flagship case
  for that stance, not an exception to it.
- Marking it pending keeps the decision cheap to revisit: the exact floor year is a
  one-parameter change to the comparison window, and the real data work in E3/E4 is the
  right point to confirm or adjust it.

---

## D010: Pre-12th-Amendment and contingent elections — structural nuances, mostly deferred

**Date:** 2026-07-05
**Context:** Elections of 1789–1800 predate the 12th Amendment: each elector cast two
votes for President and the runner-up became VP — structurally different from modern
tables. Separately, contingent elections decided in the House (1800, 1824) or Senate
(1836 VP) mean the EC plurality winner is not always who took office. The hybrid method
also raises a "no candidate reaches 270" legal ambiguity.
**Decision:**
- Pre-12th-Amendment elections (1789–1800) become their **own later epic**; the MVP
  leans on the structurally-uniform **post-1804** era.
- Contingent elections (1800/1824 House, 1836 Senate VP) are a **known data-modeling
  nuance to represent** — where the EC plurality winner differs from who took office.
- The hybrid "no candidate reaches 270" legal ambiguity is **parked for a later decision**.
**Rationale:**
- The two-votes-per-elector structure would distort the candidate/votes model if forced
  into the modern schema; isolating it protects MVP simplicity.
- Contingent elections are real historical outcomes the dataset must represent faithfully,
  but they are a modeling detail, not an MVP blocker.
- The no-270 hybrid question is a design question best answered alongside the detailed
  hybrid spec (D011), not now.

---

## D011: The hybrid method is settled in principle; its written spec is a future workstream

**Date:** 2026-07-05
**Context:** The hybrid (average of EC and PV) is Fred's original contribution and is
largely settled in his head, but no detailed written specification exists yet.
**Decision:** Treat the hybrid method as **largely settled in principle**. Its detailed
written spec — including the no-270 contingent-election treatment (D010) — is a **named
future workstream, not an MVP blocker**. MVP hybrid computation (E7) implements the
average / flip / margin logic; the formal spec follows.
**Rationale:**
- The core computation (average EC and PV, detect flips, compare margins) is clear
  enough to build the MVP explorer against.
- The edge cases requiring a formal spec (no-270, contingent elections) are rare and
  do not block the common-case analysis that delivers the MVP's value.

---

## D012: Process/tooling mirrors agentfluent conventions

**Date:** 2026-07-05
**Context:** Fred runs this project like the sibling agentfluent repo and wants
consistent PM and engineering conventions across both.
**Decision:** Mirror agentfluent's conventions: `.claude/specs/` for `prd-*`,
`backlog-*`, and `decisions.md`; `docs/ROADMAP.md`; GitHub-issue-driven epics/stories
with `epic:<slug>` and type/priority labels. The **pm agent owns PM artifacts**. Adopt
a `social/` placeholder folder *concept* for future blog/Medium content (not created now).
**Rationale:**
- Shared conventions lower the cost of context-switching between the two repos and let
  agentfluent's proven templates be reused directly.
- Naming the `social/` concept now reserves a home for future content marketing without
  incurring the cost of building it prematurely.

---

## D013: Package name — `usvote`

**Date:** 2026-07-05
**Context:** E1-S1 in the MVP backlog flagged the Python package name as an open
decision, defaulting to `usvote` with alternatives `uspv` and `elections`. The name is
referenced mechanically throughout the E1/E2 backlog as `src/usvote/`.
**Decision:** The package name is **`usvote`**. `src/usvote/` is the canonical package
root. Resolves the E1-S1 open decision.
**Rationale:**
- Fred approved `usvote`.
- Short and unambiguous; "pv" (popular vote) in the name signals the project's
  distinguishing analytical thesis, and it avoids the over-generic `elections` namespace
  that would collide conceptually with the existing `elections` Postgres database.
- Locking the name now removes the one blocker on E1-S1 and stabilizes every module path
  the rest of the backlog references.

---

## D014: Dual-source PV strategy — MIT (modern, API-eligible) + UCSB (historical, analysis-only)

**Date:** 2026-07-06
**Context:** Examination of the MIT Election Lab file Fred downloaded
(`1976-2024-president.csv`: 4,822 rows, **13 elections 1976→2024 only**, 51 jurisdictions,
one row per (year, state, candidate), with `candidatevotes` + state `totalvotes` and rich
columns — `state_po`, `state_fips`, `party_detailed`, `party_simplified`, `writein`,
`notes`) confirmed it is a clean, well-structured, state-level PV source that covers the
modern EC/PV splits (2000, 2016). But it only reaches **1976**, so it cannot satisfy the
~1824 MVP comparison window (D009) on its own. UCSB / American Presidency Project remains
the only source reaching ~1824 and is, per Fred, the most complete PV dataset available.
Its name format also differs from the Archives (`"BIDEN, JOSEPH R. JR"` vs `"Donald Trump"`),
so both sources reconcile via the canonical keys (D006 / issue #30).
**Decision:** Adopt **both** PV sources with distinct, non-overlapping roles:
- **MIT Election Lab (1976–2024)** — the clean, structured, **API-eligible modern core**;
  covers the 2000 & 2016 splits.
- **UCSB / American Presidency Project (~1824–1972)** — the **historical-breadth layer**,
  ingested for analysis and flagged **non-redistributable** pending a license answer.
- **Provenance and redistributability become first-class per-source data attributes**
  (every PV record carries `source` and a redistributable flag), extending D005.
**Refines D008.** D008 framed source selection as either/or (MIT over UCSB). D014
supersedes that framing: the two sources have non-overlapping jobs, so dual-source is a
**necessity, not redundancy**. D008 stands as the record of why MIT is the preferred
*redistributable* source; D014 adds UCSB as the required *historical-analysis* source.
**Rationale:**
- MIT's 1976 floor makes it insufficient for the historical thesis (the project needs
  ~1824 per D009); UCSB is the only path to that breadth.
- UCSB is needed for analysis even if it is never redistributable — analysis use and API
  redistribution are separable, which is exactly why redistributability must be a
  per-source attribute rather than an all-or-nothing project property.
- Splitting ingestion by source (clean MIT CSV vs. messy, era-drifting UCSB HTML) lets
  each be built at its own difficulty level instead of one over-general PV loader — hence
  UCSB gets its own epic, mirroring the EC ingestion architecture.
**Outreach path (deferred).** Two MIT-side contacts are the route to resolve MIT's license
terms and a possible pre-1976 coverage extension: **Zayne Sember**
(https://www.linkedin.com/in/zaynesember/ — published the 1976–2024 president file; lead
contact) and **Sean Greene** (https://www.linkedin.com/in/sean-greene-a467097/ —
additional contact). Outreach is **deferred until analysis back to 1976 is in hand**; its
exact mechanics remain open.
**Action required:** Backlog splits the former "E4 PV ingestion" into a scoped **UCSB
historical scrape + ingest** epic (E4, filed now, un-deferred) and a named-but-unscoped
**MIT PV ingestion** epic (E5). Roadmap epic numbering updated accordingly (join → E6,
hybrid → E7, internal API → E8, data mart → E9).

---

## D015: Source-namespacing convention — EC flat at the top level, each PV source its own subpackage

**Date:** 2026-07-06
**Context:** Defining the `src/usvote/` module skeleton (E1-S2 / issue #17, landed as
PR #40) created the Electoral College / National Archives pipeline modules flat at the
top level: `usvote/scrape.py`, `usvote/parse.py`, `usvote/transform.py`,
`usvote/load.py`, `usvote/db.py`, `usvote/pipeline.py`. The architect review of #17
flagged that D014 commits the project to two additional ingestion sources — UCSB (E4,
un-deferred) and MIT (E5) — each with its own full scrape→parse→transform→load pipeline.
E4-S1 already anticipates paths like `usvote/ucsb/scrape.py`. Without a stated
convention, those source modules would either collide with the flat EC module names (two
`scrape.py` files doing different jobs) or force an awkward retroactive move of the EC
modules into an `usvote/ec/` subpackage once E4 lands.
**Decision:** Adopt a **source-namespacing convention** for `src/usvote/` (D003):
- The **EC / National Archives pipeline stays flat** at the top level (`usvote/scrape.py`,
  `usvote/parse.py`, `usvote/transform.py`, `usvote/load.py`, `usvote/db.py`,
  `usvote/pipeline.py`).
- **Each popular-vote source lands as its own sibling subpackage** — `usvote/ucsb/` (E4)
  and `usvote/mit/` (E5) — each with its own scrape/parse/transform/load stages.
- The **EC-flat / PV-nested asymmetry is deliberate**, not an oversight. A future reader
  should not "fix" it by nesting EC under `usvote/ec/`.

This resolves the architecture point raised by issue #17 / the E1-S2 skeleton. The
convention is also carried as a working note ("Source-namespacing convention") in
CLAUDE.md, added in PR #40; **this entry is the authoritative decision record** that the
CLAUDE.md note reflects.
**Rationale:**
- EC (National Archives) is the source-of-truth spine that both PV sources reconcile
  against (D006); keeping it flat at the top level reflects its primary/anchor status.
- The two PV sources have materially different ingestion shapes (clean MIT CSV vs. messy,
  era-drifting UCSB HTML, per D014), so each warrants its own namespaced subpackage rather
  than being flattened into one shared PV loader or colliding with EC module names.
- Recording the convention now prevents a retroactive restructuring of the EC modules once
  E4 lands, and gives E4/E5 an unambiguous home.
