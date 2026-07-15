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

---

## D016: PV source determination finalized — MIT is CC0 (public-API-eligible); UCSB analysis-only

**Date:** 2026-07-13
**Context:** E3 (PV-source research, epic #13) was the task D008 named to resolve the final
PV source and confirm whether its license permits public-API redistribution — the gate
D002 leaves open. E3-S1 (#15) characterized MIT, E3-S2 (#16) UCSB / American Presidency
Project, and E3-S3 (#20) consolidated them into
[`research-pv-source.md`](research-pv-source.md). During consolidation the MIT license was
verified against the upstream Harvard Dataverse record (dataset `doi:10.7910/DVN/42MVDX`,
the source of Fred's `1976-2024-president.csv`): its license object is **CC0 1.0**
(`http://creativecommons.org/publicdomain/zero/1.0`) with **no custom terms of use
attached**. D008 had described MIT only as "open-licensed" and D014 still carried the
license question as an open, outreach-gated item.
**Decision:** Treat the PV source determination as **settled**:
- **MIT Election Lab (1976–2024) is licensed CC0 1.0** — a public-domain dedication.
  Redistribution, commercial use, and derivatives are permitted with no attribution or
  permission required, so the modern core is **cleared for public-API redistribution**.
  MIT rows carry `source=MIT`, `redistributable=true`.
- **UCSB / American Presidency Project remains analysis-only** — no data-specific reuse
  grant (UCSB Terms of Use prohibit redistribution without explicit permission via
  `policy@ucsb.edu`). UCSB rows carry `source=UCSB`, `redistributable=false` and are
  excluded from any public API surface.
- The **D002 public-API stretch goal is un-gated for 1976–2024** on the licensing axis; no
  outreach is required to ship the modern core publicly.
**Resolves D008's open action and closes the licensing question D014 deferred.** D014's
dual-source split stands unchanged; this entry records that the split's licensing basis is
now confirmed rather than pending. D008 remains the record of *why* MIT was preferred; D016
records that the preference is now backed by a verified CC0 license.
**Rationale:**
- CC0 is unambiguous and verified at the authoritative upstream (Dataverse license object),
  so the redistribution gate is settled on evidence, not on a hoped-for outreach reply.
- Keeping UCSB analysis-only is the safe, defensible default (its Terms of Use grant no
  reuse), and per-source `redistributable` flags (D014) already let the public surface
  filter cleanly to CC0 MIT rows.
**Action required:** None to unblock the API. MIT outreach is now **optional**, narrowed to
a single nice-to-have question — a possible **pre-1976 coverage extension** (which would let
more of the historical window ride on the redistributable source). Per epic #13 this stays
deferred until analysis back to at least 1976 is in hand.

---

## D017: PV source-overlap policy — MIT-preferred canonical series, UCSB the consistency control, both stored

**Date:** 2026-07-13
**Context:** MIT (1976–2024, CC0, redistributable — D016) and UCSB (physically 1789–2024,
analysis-only) both cover **1976–2024**, so the warehouse holds two PV values for the same
(year, state, candidate) across that overlap. D014 settled that both sources are stored and
tagged, but not which is authoritative where both exist — a question parked as an acceptance
criterion on the E6 union story (#68). The thesis is a **per-election** what-if (would this
election have flipped under PV/hybrid, and by how much), computed from each election's own
PV+EC; its headline outputs are normalized (flip booleans, margin percentages). The human's
steer: MIT is the definitive reference *where available* (it is the only API-exposed source,
for licensing reasons), but a **single-source UCSB series across all elections** should stay
available so a longitudinal comparison can be internally consistent. Reviewed with the
architect (see #68 comment) before recording.
**Decision:** Adopt a layered source-overlap policy. **This is subordinate to D006** — "MIT-
preferred" is a preference *among PV sources only*; the EC/National-Archives spine remains
the source of truth, and PV is joined onto it (EC on the left; missing PV surfaces as an
explicit gap, never a fabricated value — D005).

1. **Storage (unchanged from D014):** both sources' PV rows are stored and tagged `source`
   + `redistributable`; **the union keeps both rows always** (no dedup at load/union time —
   precedence is a read-time view concern, resolved in #68).
2. **Canonical/default analysis series — `pv_preferred`:** MIT wins wherever it exists
   (1976–2024); UCSB supplies everything earlier. Exactly one preferred PV value per
   (year, state, candidate), resolved by a documented precedence rank (`DISTINCT ON key
   ORDER BY precedence_rank`).
3. **Overlap (1976–2024) is a validation gate, not dual-truth:** where both sources exist,
   compare them. Close agreement is the **empirical justification that the pre-1976 UCSB
   methodology is comparable to MIT** — i.e. that the source seam at 1976 does not introduce
   a step. Disagreements beyond a tolerance are flagged with provenance (D005 reliability),
   not silently resolved. The magnitude of these discrepancies is measured by a dedicated
   research task (filed as #70) whose finding calibrates the tolerance and confirms or
   challenges the benign-seam assumption below.
4. **Public API surface — `pv_redistributable`:** exposes only `redistributable=true` rows →
   MIT → 1976–2024; pre-1976 PV is honestly absent from the public surface. This series is
   defined **independently** (`WHERE redistributable`), not as a filter over `pv_preferred`,
   so no future change to canonical resolution can leak a non-redistributable UCSB row onto
   the public API. It coincides with `pv_preferred` across the overlap by construction.
5. **UCSB single-source control — `pv_ucsb`:** the whole-span UCSB-only series stays fully
   queryable as the internally-consistent longitudinal lens. It is the **control** that lets
   us measure whether the 1976 seam matters — so the human's two desires (MIT-definitive
   *and* a consistent all-elections series) are served by one mechanism, not traded off.

**Benign-seam scope boundary (a load-bearing caveat, per the architect):** MIT-precedence is
safe for the analysis because a source change at 1976 does not bias the **normalized
per-election metrics** (flip booleans and margin %, where ratios cancel the source). It is
**not** automatically safe for (a) a raw national-PV-*count* series read across the seam, or
(b) a margin *trend* line, if the two sources differ in "other/write-in" handling or in the
total-votes denominator. Two mitigations are part of this decision: state the caveat
wherever a cross-seam longitudinal view is presented, and **pin the margin denominator to
each source's own provided state-total column** rather than re-summing candidate rows (which
would make margins sensitive to each source's minor-candidate coverage — D007 scopes
candidates to EC-getters, so re-summing would systematically differ between sources).

**Encoding (how this is materialized):** a small **`pv_source` reference table** carries
`source`, `precedence_rank`, `redistributable`, and license as the single source of truth for
these attributes (data, not code). Three **thin views** — `pv_preferred`, `pv_redistributable`,
`pv_ucsb` — express the three series over one union of the raw per-source rows. **No
materialized canonical table**; at this scale (low thousands of rows) plain views resolve in
milliseconds, and `CREATE MATERIALIZED VIEW` remains a one-line escape hatch if ever needed.
**Consequence for E6:** #68 (union) stacks-and-tags and keeps both rows; #69 joins the EC
spine to the **resolved single-row `pv_preferred`** (or `pv_redistributable` for the API path),
**not** the raw union — joining the raw union would fan the 1976–2024 overlap out 2× and
double-count downstream sums/margins. "Unified PV" is therefore two distinct objects (raw
tagged union vs. resolved preferred series); they are named apart to prevent that mistake.
**Rationale:**
- Precedence-as-data + a resolve-once view (options a+b combined) keeps the pick in exactly
  one place and avoids the drift of maintaining two materialized artifacts.
- A materialized "canonical PV" table was **rejected**: the API cannot read a canonical that
  mixes in pre-1976 UCSB rows, so it would force two materialized artifacts with duplicated,
  drift-prone resolution logic — all cost, no benefit at this scale.
- Defining `pv_redistributable` independently (not as a filter of `pv_preferred`) is the
  guardrail that keeps the D002/D016 licensing boundary structural rather than incidental.
- **Forward-compatible:** a UCSB redistribution grant becomes a one-row edit
  (`redistributable=true`) that auto-widens the public series; the ICPSR fallback (or any
  future source) drops in as one additional ranked row in `pv_source` without touching any
  view or join.
**Action required:**
- E6 #68 — resolve its parked AC to "keep both rows; add the `pv_source` reference table and
  the three views"; E6 #69 — join EC to `pv_preferred`/`pv_redistributable`, not the raw union.
- File the MIT-vs-UCSB overlap discrepancy research task (**#70**) that empirically tests the
  benign-seam assumption and calibrates the overlap tolerance (layer 3). It depends on E4
  (UCSB parsed to the overlap years) and E5 (MIT read) landing.

---

## D018: Shared PV record shape — the one schema both MIT and UCSB conform to

**Date:** 2026-07-15
**Context:** E5-S2 (#65) transforms MIT PV into "the shared PV record shape" — but that
shape is nominally owned by E4-S3 (#36, UCSB), and UCSB is unstarted (`src/usvote/ucsb/`
does not exist). The backlog anticipated this race (E4-S4 note, backlog-mvp.md:1025): whichever
PV source lands first **defines a minimal shared PV schema the other conforms to, flagged as a
shared-schema decision**. MIT is landing first, and MIT is the canonical/preferred PV source
(D016/D017) at the (year, state, candidate) fact grain already — so MIT is the right source to
*establish* the shape rather than retrofit onto a UCSB-first design. This decision fixes that
shape so #65 has a concrete target and #36/#38 (UCSB) later conform to it, not the reverse.

**Decision:** Adopt one **state-level, long-format PV record shape** — one row per
`(source, year, state, candidate)` — as the shared output contract of every PV source's
transform stage and the column contract of the shared PV target table. MIT (#65) and UCSB
(#36) both emit exactly these logical columns; sources differ only in *how* they populate
them, never in the shape.

**Logical columns (transform output):**

| Column | Type | MIT mapping | Notes |
|---|---|---|---|
| `year` | int | `year` | |
| `state` | str (canonical) | `state` (full name) | Canonical **state key** (full name, → EC `state` dim, D006). Populated MIT-native at #65; reconciled onto the canonical key at #67 (UCSB: #38). See FK-ordering note below. |
| `candidate` | str (canonical) | `candidate` | Canonical **candidate key**. Same reconcile-later contract as `state` (#67/#38). |
| `party` | str | `party_simplified` (main line) | **Descriptive-only, not the key.** For an aggregated fusion candidate (see grain note) the party is the **plurality line** — the `party_simplified` of the constituent row with the most `candidatevotes`. Party *authority* lives in the EC candidate dim (D006); this column is for validation/display and must not become a second source of party truth. `party_detailed` is MIT-only and **not** carried into the shape. |
| `candidate_votes` | int | `candidatevotes` | Popular votes for this candidate in this state, **summed across fusion lines** (see grain note). |
| `state_total_votes` | int | `totalvotes` | The **source's own** state-total denominator, carried verbatim. Pinning to the provided total (not re-summing candidate rows) is required by D017's benign-seam caveat — re-summing would make margins sensitive to each source's minor-candidate coverage, which D007 scopes differently. |
| `source` | str | literal `"MIT"` | Provenance (D014). `"MIT"` / `"UCSB"`. **The only provenance column stored in the fact** — `redistributable`/`precedence_rank`/license are derived by join to the `pv_source` reference table (D017), never stored per-row. |
| `reliability` | enum \| null | literal `"exact"` | D005/D014 reliability flag, constrained to `{exact, estimated, unreliable}` (CHECK / lookup, not a free string). Genuinely **per-row** — UCSB varies it by year/state — so it stays in the fact (unlike `redistributable`, which is per-source). MIT is a clean modern release → `"exact"`. Column exists in the shape **now** so UCSB needs no ALTER later. |

**Grain & natural key:** exactly one row per `(source, year, state, candidate)`. `source` is
part of the key because the union deliberately keeps both sources' rows (D017 — no dedup at
load); precedence between sources is a read-time view concern (`pv_preferred` etc., D017), never
a transform/load-time drop. Grain uniqueness is a tested validation (mirroring the EC transform
intent, E2-S3).

**Fusion-line aggregation (load-bearing — the raw MIT CSV is *not* at this grain).** MIT lists a
candidate on multiple party lines in fusion-voting states as **separate rows** (e.g. 2016 NY:
three `CLINTON, HILLARY` rows across Democratic / Working Families / Women's Equality; two
`TRUMP, DONALD J.` rows), while other year/states are pre-aggregated (2020 NY Biden is one row).
D007's EC-getter filter does **not** collapse these — the fusion cases *are* the major
candidates. Transform therefore **sums `candidatevotes` to one row per (year, state, candidate)
before** the grain assertion, taking `party` from the plurality line and `state_total_votes`
verbatim (it is already the all-lines state total). Skipping this makes the grain assertion fail
and, worse, silently corrupts D017's `pv_preferred` `DISTINCT ON (year,state,candidate)` —
which would keep one fusion line and **undercount a major candidate**. This is a tested
validation, not a comment.

**What is deliberately *not* in the shape:**
- **No stored `redistributable` column.** It is per-*source* (license), so it lives once in the
  `pv_source` reference table (D017) and is surfaced by join — never duplicated per fact row. This
  is what keeps "a UCSB redistribution grant is a one-row edit" true (D017). The transform frame
  *may* carry a literal `redistributable` for self-documentation, but the persistent target table
  does not store it.
- **No surrogate `pv_id` and no FK enforcement at transform** — those are added at the load seam
  (#66/#37), not by transform, exactly as EC assigns `votes_id` at load. Transform emits a logical
  frame. **FK ordering:** because #65 emits MIT-native `state`/`candidate` strings that do not yet
  match the EC dims, FK enforcement to `state`/`candidate` must **follow** reconciliation (#67) —
  or the first load lands FK-deferred. Adding FKs before #67 would reject or silently drop every
  unreconciled row (the inner-join silent-drop hazard).
- **No aggregate/total rows.** Unlike the EC `votes` table's `is_total` rows, PV state totals ride
  as the `state_total_votes` *column*; national totals are derived downstream, not stored.
- **No `writein` column.** D007 scopes candidates to EC-getters, which drops MIT's write-in long
  tail (up to 167 names in 2024) at transform; the survivors are non-write-in, so the flag is
  vacuous. (The filter itself is applied and tested in #65 via `writein` + `party_simplified`.)
- **No fabricated gap rows.** Where a source lacks a (year, state, candidate) value it is an
  **absent row**, never a zero-filled placeholder (D005).

**Rationale:**
- **Long format, not wide** mirrors the EC `votes` fact (melted, one row per candidate/state) so
  PV joins onto the EC spine at a matching grain (D006) with no reshape at join time.
- **`source` in the key** is what makes D017's "keep both rows, resolve at read-time" policy
  expressible — a shape keyed only on (year, state, candidate) could not hold the 1976–2024
  MIT/UCSB overlap without a lossy dedup the union explicitly forbids.
- **`reliability` present from day one** avoids an ALTER/backfill when UCSB lands; MIT simply
  pins it to `"exact"`. Same forward-compat logic as the source-derived `redistributable`.
- **Canonical keys are the target, reconciliation is a later story** — #65 legitimately emits
  MIT-native `state`/`candidate` strings and #67 maps them, so this decision names the *columns*
  as canonical without forcing #65 to also own reconciliation (keeps the stories separable, as
  the backlog sequences them).
- **Transform emits a logical frame; load owns keys/FKs/NaN→None** keeps the single write
  chokepoint (`usvote.db.insert_df_into_table`) authoritative and matches how EC is layered.

**Action required:**
- #65 (MIT transform) targets this exact column set; **fusion-line aggregation runs before** the
  grain assertion; grain + totals-reconciliation validations become tested functions; 2000 & 2016
  covered.
- **Totals reconciliation is `<=`, not `==`, post-filter.** After the D007 EC-getter filter,
  `sum(candidate_votes) <= state_total_votes` is expected (the dropped minor candidates are the
  residual); equality would spuriously fail. Best practice: assert *full* reconciliation on the
  **pre-filter** frame (catches read/parse regressions), then `<=` on the filtered frame.
- #36/#38 (UCSB) **conform** to this shape when E4 is scoped — populating `source="UCSB"` and real
  `reliability` values — rather than defining a rival shape. `redistributable=false` for UCSB is a
  `pv_source` row, not a fact column.
- The shared PV **target table** (#66/#37) is these columns (`source` + `reliability`, **not**
  `redistributable`) + a surrogate PK; FKs to the EC `state`/`candidate` dims are added only once
  reconciliation (#67) lands (or the load is FK-deferred until then). `redistributable`,
  `precedence_rank`, and license come from the `pv_source` reference table by join (D017). DDL is
  finalized at the first load story, consistent with this shape.

---

## D019: MIT D007 candidate-scope proxy — `party_simplified ∈ {DEMOCRAT, REPUBLICAN}`

**Date:** 2026-07-15
**Context:** D007 scopes the MVP to "candidates who received electoral votes," and D018 fixed the
*mechanism* of the MIT filter (`writein` + `party_simplified`) but left the *value set* open. MIT
carries **no electoral-vote data**, so the true EC-getter set is not computable inside the pure
MIT transform (#65). A value set must be chosen without coupling MIT transform to the EC spine.
**Context surfaced by architect review of the #65 implementation plan.**
**Decision:** The MIT transform (#65) keeps rows where `writein == False` **and** the candidate's
(fusion-aggregated) `party_simplified` is in **`{DEMOCRAT, REPUBLICAN}`**. This is a deliberate
*proxy* for D007's "received electoral votes," valid because across 1976–2024 **every electoral
vote went to a Democratic or Republican nominee**, so the two-value party filter is effectively
exact for this window — offline, with zero maintenance. Two known, deliberate deviations:
- **Libertarian/Green PV candidates are excluded.** None received an electoral vote in 1976–2024,
  so including them would both violate D007 and manufacture PV rows with no EC counterpart that
  #67/E6's inner-join would drop silently (the inner-join silent-drop hazard).
- **Faithless-elector EC recipients are deferred to #67** (e.g. 2016 Powell / Faith Spotted Eagle
  / Kasich / Paul / Sanders; 1988 Bentsen; 2004 Edwards). They are immaterial to state
  sums/margins, and the *exact* EC-getter set becomes joinable at reconciliation (#67 / D006)
  where canonical keys exist.
**Rationale:**
- `{DEMOCRAT, REPUBLICAN}` dominates a hand-curated per-year allow-list (exact but maintained for
  no MVP gain) and injecting the EC-getter set from the spine (correct, but that coupling is the
  #67 answer, not #65's). D018 already defers candidate *identity* to #67; this keeps #65's scope
  to "select + type + filter + validate."
- The filter runs on the **fusion-aggregated** frame (party = the plurality line), so a fusion
  candidate is judged by their main party, never a secondary `OTHER`-coded line — see D018's
  fusion-aggregation note.
- Encoded as a named, provenance-carrying constant in `usvote/mit/transform.py`, mirroring the EC
  correction-constant pattern, and locked by a test.
**Action required:**
- #65 implements the `{DEMOCRAT, REPUBLICAN}` constant + filter; #67 supersedes the proxy with the
  exact EC-getter set once canonical keys land, at which point the faithless-elector deferral is
  revisited.
