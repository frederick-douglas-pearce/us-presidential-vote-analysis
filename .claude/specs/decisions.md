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
  finalized at the first load story, consistent with this shape. **Finalized in #66 — see D021.**

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

---

## D020: MIT name reconciliation — curated maps producing canonical *values*, in a separate offline stage

**Date:** 2026-07-15
**Context:** E5-S4 (#67) reconciles MIT's native `state`/`candidate` strings (left MIT-native by
#65, D018) onto the canonical keys the EC spine defines (D006, #30) — the MIT analogue of the
UCSB reconciliation (#38). Three mechanism choices were open and settled with the user +
architect review before coding: (a) how candidate names map, (b) what the reconciliation targets,
(c) where the stage runs. MIT prints `"LAST, FIRST M. SUFFIX"`; the EC canonical `name` is not a
mechanical transform of it — across 1976–2024 the reconciliation *drops* MIT's middle initial for
some nominees (`OBAMA, BARACK H.` → `Barack Obama`; `BUSH, GEORGE H.W.` → `George Bush`) and
*adds* one for others (`FORD, GERALD` → `Gerald R. Ford`; `MONDALE, WALTER` → `Walter F. Mondale`),
plus given-name substitutions (`CLINTON, BILL` → `William J. Clinton`; `GORE, AL` →
`Albert Gore Jr.`). RHS names were derived from the National Archives Table 1 per year (+ the
`Bob Dole` → `Robert Dole` EC correction), LHS from the distinct `candidate` values `transform_mit`
emits on the real file — both enumerated, not guessed.

**Decision:** Reconcile via **curated, provenance-carrying lookup maps** in a **separate offline
reconcile stage** (`src/usvote/mit/reconcile.py`, `reconcile_mit`) that produces the canonical
**values** directly:
1. **Curated maps, not a parser.** `MIT_STATE_RECONCILIATIONS` (51 jurisdictions) and
   `MIT_CANDIDATE_RECONCILIATIONS` (18 D/R nominees, bounded by D019). Each value is the whole
   canonical string — no token-level nickname/middle-initial logic — mirroring the EC
   `CANDIDATE_NAME_FIXES` catalog. The map is keyed on the MIT string and is **many-to-one safe**
   (multiple MIT spellings of one person → the same canonical name); the inverse (one MIT string →
   two people) does not occur and is assumed not to (per D006 each EC candidate has a single
   canonical name across all years; a violation would be an upstream EC-transform bug).
2. **Static canonical values, not a live join.** Reconcile emits only the **display keys**
   (`name`, full `state` name) deterministically; it does **not** join against the live EC dims,
   so the stage is pure/offline (no DB, shapefile, network). The EC "match target" columns
   (name-parts, `state_usps`) exist to absorb *format* variance the maps have already removed, so
   E6/#69 joins on the display key directly. **#69 owns the reciprocal guard** — that every
   reconciled MIT name/state is present in the EC dims (the offline map only pins RHS in a test).
3. **State map on the ALLCAPS name, not `state_po`.** D018's shape drops `state_po`, and the full
   state name is documented stable/unambiguous, so the map keys the ALLCAPS name (the AC also
   names `state_po`; we deviate deliberately, documented in `reconcile.py`). `.title()` is *not*
   used — DC's lowercase "of" needs the explicit entry.
4. **Separate stage, not folded into `transform_mit`.** `transform_mit` validates MIT-internal
   correctness (totals, scope); reconcile validates cross-source conformance to the EC spine — a
   different concern with a different authority (SRP; matches the per-source read/transform seams,
   D015).

**Validation (each raises `MITReconcileError`):** full state + candidate coverage (unmapped value
→ raise, the inner-join silent-drop guard); unique `(year, state, candidate)` grain re-asserted
*after* the rewrite (catches two MIT strings collapsing onto one canonical name); D018 shape +
row-count preserved. The two-Bushes non-collision (`George Bush` ≠ `George W. Bush`) and the pinned
RHS values are locked by tests in `tests/unit/test_mit_reconcile.py`.

**Rationale:**
- The reconciliation is genuinely non-mechanical (middles dropped *and* added, given-name
  substitutions), so a parser would need per-name overrides for most nominees anyway — a curated
  map is simpler and fully auditable at this scale (18 nominees, 51 states).
- Emitting canonical *values* offline keeps #67 free of the DB/shapefile/network that a live join
  would drag in, and keeps the D002/D016 licensing boundary and the join itself as #69's concern.
- **Supersedes D019's proxy question narrowly:** the D019 `{DEMOCRAT, REPUBLICAN}` scope already
  yields exactly the 18 EC-getter nominees for 1976–2024, so #67 confirms rather than replaces the
  proxy; no faithless-elector recipient appears in MIT's D/R-scoped PV rows, so that D019 deferral
  is discharged as "out of scope for MIT PV" rather than acted on.

**Action required:**
- #69 (E6 join) must carry the reciprocal guard: assert every reconciled MIT `name`/`state` is
  present in the EC candidate/state dims (fail loud, not an inner-join silent drop).
- The EC transform has no *general* guard against a future un-`FIXED` cross-year name split (one
  person printed two ways in different years → two silent candidate rows); the known case (Trump)
  is handled by `CANDIDATE_NAME_FIXES` and tested. A general invariant check belongs with the EC
  coverage-extension work (#32), not #67 — flagged here so it is not lost.

---

## D021: Shared PV target table DDL finalized — `dwh.pv_votes` (state-FK-only, no candidate FK)

**Date:** 2026-07-16
**Context:** D018 fixed the shared PV *record shape* and left one action open: "DDL is finalized
at the first load story." MIT is the first PV source to load (it is the canonical/preferred source
per D016/D017), so **#66 (E5-S3, PR #75)** is that story — it created the shared, source-neutral
PV fact table and loaded MIT into it. This entry records the DDL that shipped, so a future reader
knows the concrete table — its name, exact column order, types, and constraints — without
reverse-engineering it from the loader. Architect-reviewed before merge.

**Decision:** The shared, source-neutral PV fact table is **`dwh.pv_votes`** — named to parallel
the EC `votes` fact, and kept deliberately distinct from D017's resolved-series **view** names
(`pv_preferred` / `pv_redistributable` / `pv_ucsb`) and the `pv_source` reference table. Columns,
in DDL order:

| # | Column | Type | Constraint |
|---|---|---|---|
| 1 | `pv_id` | integer | surrogate **PK**, assigned at load |
| 2 | `source` | varchar | NOT NULL |
| 3 | `year` | smallint | NOT NULL |
| 4 | `state` | varchar | `REFERENCES dwh.state` (state-FK) |
| 5 | `candidate` | varchar | **no FK** |
| 6 | `party` | varchar | nullable |
| 7 | `candidate_votes` | integer | NOT NULL |
| 8 | `state_total_votes` | integer | NOT NULL |
| 9 | `reliability` | varchar | `CHECK (reliability IN ('exact','estimated','unreliable'))`, nullable |

Table constraint: **`UNIQUE (source, year, state, candidate)`** — the D018 natural key.

**Key design calls (architect-reviewed):**
- **State-FK-only, no candidate FK.** The EC `candidate` PK is `candidate_id`, not the `name`
  string this shape carries — so a PV→EC candidate FK cannot target this column, and a PV FK onto
  the EC candidate dim would **invert the D006 spine dependency** (EC is the source of truth PV
  joins *onto*, not the reverse). Candidate referential integrity is instead guarded **offline at
  reconcile (#67)** and **at the EC↔PV join seam (#69)** — not by a DDL constraint.
- **`state`/`candidate`/`party`/`reliability` left nullable in the DDL** for UCSB forward-compat;
  the shared loader's `assert_pv_shape` enforces NON-NULL on the natural-key + vote columns for the
  frame actually being loaded. Nullable-in-DDL + asserted-at-load lets one physical table serve
  both MIT's strict rows and UCSB's looser rows without an ALTER later.
- **No `redistributable` column** — it is per-*source* (license), so it lives once in the
  `pv_source` reference table (D017) and is surfaced by join, never duplicated per fact row. #66
  deferred `pv_source` itself to **E6 / #68** (per D017); `dwh.pv_votes` carries `source` only.

**Rationale:**
- Recording the concrete DDL closes D018's "finalized at the first load story" action and gives
  #37 (UCSB) an exact conformance target rather than a shape description.
- The nullable-DDL + `assert_pv_shape` split is what lets a single table serve both sources; the
  no-candidate-FK call is what keeps D006's spine direction structural rather than incidental.

**Action required:**
- **#37 (UCSB load) conforms to `dwh.pv_votes` as-shipped** — same columns/types/constraints,
  populating `source="UCSB"` and real `reliability` values; it does **not** redefine the table.
- **#68 (E6)** adds the `pv_source` reference table + the three D017 views over `dwh.pv_votes`;
  `redistributable` (incl. MIT's `redistributable=true`) is surfaced there by join, not on the fact.

---

## D022: UCSB parser fixtures are synthetic, not real snapshots — amends E4-S1 (#34) AC3

**Date:** 2026-07-17
**Context:** E4-S1 (#34) carries an acceptance criterion — written 2026-07-06, before the
D014/D016 licensing posture hardened — requiring that "at least a few representative year
snapshots (spanning different eras) are saved into `tests/fixtures/`" to seed the UCSB parser
tests (E4-S2 / #35). That AC is now in **direct conflict with D014/D016**: this repository is
**public**, and UCSB / American Presidency Project content is `redistributable=false` (UCSB Terms
of Use grant no reuse; redistribution requires explicit permission via `policy@ucsb.edu` —
research-pv-source.md §3). **Committing UCSB HTML to a public repo *is* redistribution**, and the
act is effectively **irreversible** — once pushed, the bytes persist in forks, clones, git
history, and third-party caches beyond our control. The AC and the licensing decision cannot both
be honored as written.

The raw snapshot itself already exists in full — **all 60 elections 1789–2024, every one HTTP
200**, fetched 2026-07-06 — at `~/Documents/Projects/data/presidential_vote_analysis/ucsb_raw/`,
**outside the repo and untracked by git** (research-pv-source.md §5). So the question at issue is
only **what ships into `tests/fixtures/`**, never whether the parser has real data to be
developed against.

**Decision:** UCSB parser fixtures are **hand-written synthetic HTML** that mimics the real UCSB
table structure with **fabricated vote numbers**. **No UCSB-sourced bytes are committed to this
repository.** The real snapshot stays where it is — external, untracked, analysis-only — and
remains the artifact each fixture is *derived from* by close reading, never by copy.

Each synthetic fixture is **annotated with the real source year it mimics** (e.g. "structure
mimics 1824; vote values are fabricated") so the derivation stays auditable. Between them the
fixtures must pin every structural case #35 must handle (research-pv-source.md §5):
- **Wide-not-long layout** — candidates in columns; the melt to per-(year, state, candidate) records.
- **`colspan`/`rowspan` multi-row headers**, with the **candidate-group count drifting by era**
  (2 groups in 1876, 4 in 1824) — forcing generic header parsing, never fixed column indices.
- **Legislature-chosen-elector states with no PV** (1824: Delaware, Georgia, Louisiana, New York,
  South Carolina, Vermont) — which must be **flagged with provenance, never coerced to zero** (D005).
- **Footnote/annotation rows at table bottom** (e.g. 1824's "elected by the House of
  Representatives") — which must not be mistaken for data rows.

**This decision amends E4-S1's AC3** (issue #34 and its `backlog-mvp.md` entry): "representative
year snapshots saved into `tests/fixtures/`" is **replaced by** "synthetic era-spanning fixtures
saved into `tests/fixtures/`." The original AC is recorded as **amended, not silently dropped** —
as written it would have required shipping non-redistributable content.

**Options weighed:**
1. **Commit small excerpts of the real HTML** — reduces the *volume* redistributed but not the
   *fact* of it; the licensing question is unchanged by size. **Rejected.**
2. **Hand-written synthetic fixtures** — no UCSB content ships; parser tests still pin every
   structural case; runs in CI. **Chosen.**
3. **Keep fixtures external + env-var-gate the parser tests** — uses real data, but the parser
   tests cannot then run in CI, which is most of the point of having them. **Rejected.**

**Rationale:**
- **The parser cares about structural shape, not vote values.** #35's job is to survive
  `colspan`/`rowspan` header drift, melt a wide table, and distinguish footnote rows and no-PV
  states from data. Every one of those cases is expressible with fabricated numbers, so real UCSB
  values buy the tests nothing they cannot get synthetically.
- **Keeps the parser tests in CI** — unlike option 3, which would leave CI blind to exactly the
  era-drift regressions that make #35 the highest-risk story in the epic.
- **Keeps the public repo free of non-redistributable content** — unlike options 1 and 3, which
  either ship UCSB bytes or accept a blind CI. Since pushing is irreversible, the conservative
  option is the only reversible one.
- Consistent with D014/D016 treating redistributability as a **first-class per-source attribute**:
  UCSB is usable for analysis *and* undistributable, and those are separable — the fixtures are
  where that separation becomes structural rather than incidental.

**Known tradeoff (and its mitigation):** synthetic fixtures can **drift from real UCSB quirks** —
a structure we invent may be subtly cleaner than the one the site actually serves, so a green test
suite could coexist with a parser that fails on the real snapshot. Mitigations: (a) derive each
fixture from **close reading of the real snapshot**, not from imagination; (b) **annotate the real
source year** each fixture mimics, so the derivation is re-checkable; (c) treat a parse run over
the **full external 60-year snapshot** as an acceptance check for #35 that the fixtures alone
cannot provide.

**Action required:**
- **#34** — AC3 amended per this entry; the remaining fixture work is *synthetic* era-spanning
  fixtures, not real snapshots. The `backlog-mvp.md` E4-S1 entry is updated to match.
- **#35 (UCSB parse)** — its "one page per distinct era format, against saved fixtures" AC reads
  as *synthetic* fixtures; the real 60-year external snapshot remains the development corpus and
  acceptance check.
- **No UCSB HTML is ever committed** to this repository while `redistributable=false` stands.
  Should UCSB ever grant permission (D017 notes this is a one-row `pv_source` edit for *data*),
  this fixture decision may be revisited — though the synthetic fixtures would remain adequate
  regardless.

---

## D023: Port the UCSB snapshot script into the package — code comes in, data stays out

**Date:** 2026-07-17
**Context:** The UCSB HTML snapshot E4-S1 (#34) asks for **already exists in full** — all 60
elections 1789–2024, every one HTTP 200, fetched 2026-07-06 — produced by a self-contained,
stdlib-only script, `_snapshot_ucsb.py`, whose own docstring names "backlog #34 (E4-S1)". Both
the snapshot **and the script** live at
`~/Documents/Projects/data/presidential_vote_analysis/ucsb_raw/` — **outside the repo and
untracked by git**. D022 settled what ships into `tests/fixtures/` (synthetic HTML, no UCSB
bytes) but not what happens to the **scrape code**: `src/usvote/ucsb/` does not exist, and the
script is neither importable as `usvote.*` nor under version control. The port rationale existed
only in #34's Implementation Notes; this entry promotes it to a decision of record.

**Decision:** **Port `_snapshot_ucsb.py` into the package** at `src/usvote/ucsb/scrape.py`, per
D015's sibling-subpackage namespacing (each PV source is its own subpackage; EC stays flat).

**Port, don't rewrite.** The script's robots-compliant behavior is preserved **exactly**, not
reimplemented:
- honors the site's **`Crawl-delay: 10`**
- identifies truthfully as **`us-presidential-vote-analysis-research/0.1 (personal academic
  research)`** — matching `User-agent: *`, explicitly **not** ClaudeBot
- enumerates year URLs by **regexing the already-saved index** (no extra network hit)
- **skip-if-already-have**
- **halts immediately on 403/429**
- writes the per-year **sha256 `manifest.json`**

These politeness behaviors are precisely what a from-scratch reimplementation would lose, and
their loss is **invisible until the site blocks us** — by which point the damage (to the
project's access and to a public archive's goodwill) is already done. A rewrite would be judged
green by any test that only checks "did we get the HTML."

**The snapshot DATA stays outside the repo.** Only the *code* comes in. UCSB is
`redistributable=false` (D014/D016) and this repo is public, so committing the HTML is
redistribution (D022's reasoning applies unchanged to the snapshot itself, not just to fixtures).
The resulting **asymmetry is deliberate and worth naming**: the data is knowingly left
**un-backed-up by git**, and it is safely re-fetchable **precisely because the script is in git**.
The script in version control is what makes the data's absence from version control an acceptable
risk rather than a single point of failure.

**The snapshot directory path is resolved from the env var `USVOTE_UCSB_HTML_DIR`** rather than
the script's hard-coded `os.path.expanduser(...)`. The name follows the established sibling
config convention — `USVOTE_MIT_CSV_PATH` and `USVOTE_SHAPEFILE_PATH` both name **format + role**,
so `USVOTE_UCSB_HTML_DIR` is exactly parallel; a `..._SNAPSHOT_DIR` variant would name role only
and break the pattern. Unset / empty / nonexistent raises the typed `ConfigError`, as the sibling
config modules do.

**Rationale:**
- **Reproducibility is the D003 star.** The 2028 refresh must regenerate the snapshot by running
  a versioned, tested module — not by hunting for a loose script on one machine. A pipeline whose
  ingestion step exists only as untracked local code is not reproducible in any meaningful sense.
- **The means to re-fetch was as fragile as the data.** The snapshot has no backup and exists on
  exactly one disk; before this port, so did the *only* copy of the fetch logic. Porting the code
  removes the worse half of that risk — losing the data costs a polite re-scrape, whereas losing
  the script costs re-deriving the URL enumeration, the politeness rules, and the manifest format
  from scratch.
- **It creates the `usvote/ucsb/` namespace that #35–#38 all need**, so it is the natural first
  story of the epic regardless of the snapshot's existence.

**Counter-argument (recorded honestly):** the snapshot is **one-and-done for historical data** —
1789–2024 does not change — so a re-scraper earns its keep only about **every four years**. That
is a real argument against porting. It loses anyway because the cost is **~70 lines of
already-written code** (a port, not a build), while the downside case — losing the only copy of
the fetch logic — is **silent until it matters**, and matters at exactly the moment (a refresh
deadline) when re-deriving it is most expensive.

**Related:** **D022** (its sibling — that entry governs *fixtures*, this one governs *code*; both
land on "no UCSB bytes in the repo"); **D015** (the `usvote/ucsb/` namespacing this port obeys);
**D003** (the reproducibility star it serves); **D014**/**D016** (why the data stays out).

**Action required:**
- **#34** — the port is scoped as remaining-work item (a), with the robots-compliant behaviors
  enumerated as ACs so a reviewer can check each one survived the port; env var is
  `USVOTE_UCSB_HTML_DIR`; unit tests cover URL enumeration, manifest shape + sha256,
  skip-if-already-have, the 403/429 halt, and config resolution — **against injected fakes, no
  live network in CI** (a test run must never re-fetch the snapshot).
- **No UCSB HTML is committed** by this port (D022) — only the code that can re-fetch it.

---

## D024: PV absence is modeled at its own grain — a `pv_state_status` roster, never a null vote

**Date:** 2026-07-18
**Context:** A survey of all 60 real UCSB year pages (see
[`docs/ucsb-html-formats.md`](../../docs/ucsb-html-formats.md)) established that **no year fails
to parse**. E4-S2's acceptance criterion "era-specific format variations are handled (or
explicitly flagged where a year cannot be parsed cleanly)" was written expecting year-level parse
failures; there are none. What actually needs flagging is **popular-vote absence at the record
level**, in four structurally distinct cases:

1. **State chose electors by legislature** — no popular vote was ever held. 18 rows across 12
   years (1824 DE/GA/LA/NY/SC/VT; 1828 DE/SC; 1832–1860 SC each cycle; 1868 FL; 1876 CO). Markup
   is a 2-cell row whose second cell has `colspan = width-1`, carrying verbatim prose such as
   *"3 electors chosen by state legislature and awarded to Rutherford B. Hayes"* or, for 1824
   New York, *"…: 2 for Crawford; 1 for Adams"* — i.e. the prose sometimes records a **split
   elector allocation**.
2. **State did not participate at all** — the row is simply **absent, with no markup whatsoever**.
   1864 (11 Confederate states), 1868 (3 states). Only a prose footnote elsewhere on the page
   attests to it.
3. **Candidate not on that state's ballot, pre-1852** — the Votes cell is a lone `U+00A0`.
4. **Candidate not on that state's ballot, 1852+** — the Votes cell is `--`.

Crucially: **a literal `0` never appears in a state-row vote column anywhere in the corpus.**
"Zero popular votes" is never encoded, so absence must never be modeled as zero.

Two prior decisions constrain the answer. **D021** shipped `dwh.pv_votes` with
`candidate_votes`/`state_total_votes` **NOT NULL**, enforced for *every* source by
`usvote.pv.schema.REQUIRED_NON_NULL`; and its action item states that UCSB (#37) **conforms to the
table as-shipped and does not redefine it**. **D018** already settled that a source lacking a
(year, state, candidate) value yields an **absent row, never a zero-filled placeholder**.

**Decision:** Model PV absence **at the grain at which each case actually occurs**, adding a
sibling table rather than amending the shared PV fact.

1. **`dwh.pv_votes` is untouched.** No `ALTER`, no nullable `candidate_votes`, no weakened
   `assert_pv_shape`. The "null vote + reason enum" design is **rejected**: it would relax a
   shipped constraint for both sources to describe a UCSB-only phenomenon, and it denormalizes a
   (year, state) fact onto N candidate rows with nothing keeping the copies consistent.
2. **Cases 3–4 produce no row**, per D018's existing absent-row policy. Both the pre-1852 `U+00A0`
   and the 1852+ `--` normalize to one internal parser sentinel — the era difference is a parsing
   detail, not a data attribute.
3. **Cases 1–2 land in a new sibling table `dwh.pv_state_status`**, grain `(source, year, state)`,
   with columns `pv_status` (CHECK-constrained), `note` (nullable text), and `source`. It is a
   **complete roster — one row per state in that year's election, including ordinary ones** — not
   an exceptions table. This is what makes absence detectable at all: an exceptions-only table
   cannot distinguish "no exception" from "we never looked."
4. **`pv_status` has exactly three values:** **`popular_vote`** (held and recorded in `pv_votes`),
   **`legislature_chosen`** (case 1), **`not_participating`** (case 2). Deliberately absent: any
   value for cases 3–4 (they are one fact, not two); a secession/unreconstructed split (the enum
   encodes the data-modeling consequence, not the historical cause — cause goes in `note`); and
   any `unknown`/`unparsed` bucket — **anything the parser cannot classify raises**, because an
   `unknown` slot is where parse failures go to die quietly.
5. **The verbatim legislature prose is preserved unparsed** in `note`. Elector counts and the 1824
   NY split allocation are **not** extracted into structured columns: doing so would create a
   **second source of electoral-vote truth**, contrary to D006 — the same ruling D018 made for
   `party` ("must not become a second source of party truth"). Nothing is lost, because the EC
   `votes` fact already carries per-state per-candidate electoral votes from the authoritative
   source. Only the **structural** cross-check is automated (every `legislature_chosen`
   (year, state) has ≥1 EC `votes` row); textual name-matching against the prose is a one-time
   manual audit recorded in `docs/`, not a test.
6. **The roster is assembled from the EC spine plus a named constant — never from UCSB markup.**
   The participating-state roster for year Y is the distinct states in the EC `votes` fact (D006
   makes EC authoritative on participation; costs no new reference data). Case 2 comes from
   `UCSB_NONPARTICIPATING_STATES` in `usvote/ucsb/transform.py` — 14 entries, each with its cause
   — following the established anomaly pattern (constant + test + `docs/corrections.md` row). A
   general statehood-admission roster is **rejected**: it needs reference data the repo lacks (the
   `state` dim is TIGER geography, no admission dates) for a set that is **historically closed**
   and can never grow.
   - *Clarified 2026-07-18 during the #36 architect review (scope refinement; no part of this
     decision reverses).* §6 assumed the EC spine covers every year UCSB publishes PV for. It does
     not: `UNSUPPORTED_EC_YEARS` (`pipeline.py:53`) gates 1868 and 1872, for which UCSB *does*
     publish PV. **UCSB ingestion is therefore scoped to the EC spine** — `ec_ingest_years()` minus
     `NO_POPULAR_VOTE_YEARS` — **derived at runtime, never duplicated as a literal year set in
     `usvote/ucsb/`**, so #57 lifting the gate admits both years to E4 with no change in
     `usvote/ucsb/`. A roster that comes back empty for an in-scope year **raises**. Rationale:
     `pv_coverage` (§8) is EV-weighted and therefore uncomputable without an EC spine for the year,
     so ingesting 1868/1872 would create exactly the partial-coverage years D009 mandates a caveat
     for, with no means to quantify one. This **defers, not hides**: the gating is expected to be
     temporary (#57 is tracked, deprioritized behind bulk-ingest and the API, and non-trivial),
     `UCSB_NONPARTICIPATING_STATES` retains all 14 entries including 1868's three, and
     `docs/corrections.md` records that the 1868 rows are catalogued but not yet ingested.
   - *Also clarified:* the participating-state roster derives from `dwh.votes` **with totals rows
     excluded** (`is_total = false` / `state IS NOT NULL`) — `votes.state` is NULL on totals rows,
     so a naive `SELECT DISTINCT year, state` yields a NULL roster entry per year. The same filter
     applies to E6's MIT roster backfill, which §Rationale describes as a mechanical
     `INSERT … SELECT DISTINCT`.
   - *Clarified 2026-07-19 during #36 implementation (the design is unchanged; its stated
     justification was wrong).* §6 above says the roster is the EC spine "**plus**"
     `UCSB_NONPARTICIPATING_STATES`, implying a non-participating state is *missing* from the spine
     and the constant supplies its row. Measured against the real spine, it is not: the Archives
     Table 2 carries rows for non-participating states with **`total_electoral_votes = 0`**, so
     `dwh.votes` already yields the *complete* roster (1864: 36 states, against UCSB's 25 popular-
     vote rows). **The constant therefore supplies the `pv_status`, not the roster row**, and the
     union is retained as belt-and-braces rather than as the mechanism. This matters because a
     future reader who measures the same thing has a live incentive to delete the constant from
     roster assembly as dead code — which would silently lose the status assignment, leaving 1864's
     eleven states classified `popular_vote` with zero facts.
   - *Consequently, a structural cross-check is available and is now enforced* (§7-adjacent, the
     generalization of §5's "every `legislature_chosen` (year, state) has ≥1 EC `votes` row"):
     **(a)** every in-scope `UCSB_NONPARTICIPATING_STATES` entry must have
     `total_electoral_votes = 0` in the spine, validating the constant against the authority; and
     **(b)** no zero-EV roster state may be classified `popular_vote`. Verified exact corpus-wide —
     the zero-EV roster states are precisely 1864's eleven, in every in-scope year, with no false
     positives. (b) deliberately couples E4 to the Archives' rendering: a silent change in how
     non-participating states are rendered would corrupt the roster invisibly, and surfacing that is
     the roster's entire purpose, so its error message says plainly that the cause is an EC-spine
     change rather than a UCSB one. **Do not "optimize" the roster by filtering to
     `total_electoral_votes > 0`** — that drops exactly the states this design exists to represent.
     For **#57**: whatever spine it builds for 1868 must render that year's three non-participating
     states as zero-EV rows, or check (a) will fire.
   - *Clarified 2026-08-07 during #140 (no part of this decision reverses; §6's wording is now
     out of date in two ways).* §6 says the roster is "the EC spine plus a named constant",
     singular and UCSB-scoped. Both halves of that have moved:
     **(i) There are now two absence constants, not one.** `usvote/pv/absences.py` holds
     `PV_ABSENCE_CATALOG` — the same 28 in-scope `(year, state)` pairs, classified from
     **public-domain** sources with a citation per row — alongside UCSB's existing
     `UCSB_NONPARTICIPATING_STATES`, which stays because UCSB's own transform still needs it.
     The reason for a second constant is licensing, not disagreement: the pre-1976 classifications
     had exactly one machine origin (parsing UCSB markup), UCSB grants no reuse rights (D022), and
     the snapshot is redistributable-only *at the source* (D030) — so #139's public `pv_status`
     back to 1824 cannot be built on UCSB-derived rows. The `pv_status` enum being "a bare
     historical fact" (see the Licensing consequence below) is what makes an independent
     compilation possible at all; what is *not* redistributable is UCSB's expression of it,
     including their selection.
     **(ii) UCSB's role changes from source to control.** `TestRealCorpus` now asserts the two
     rosters agree exactly on `(year, state, pv_status)` over all 49 in-scope years, with the
     dependency **inverted**, the same posture D016 takes for the PV facts. State precisely what
     that corroborates: the two rosters take their `(year, state)` **membership** from the same EC
     spine because §6 requires both to, so the shared 2,130-row count is the *design* and asserting
     it would assert a tautology. What is independent is the `pv_status` on each row — UCSB's
     parsed from their markup, ours curated with its own citations — so the test checks the 28
     absences first and on their own, that being the entire claim, with full triple-equality
     following as "nothing else diverges either". Anything downstream that cites "2,130 rows" as
     agreement must carry the same qualifier. That
     inversion is only meaningful if the two cannot touch, so `tests/unit/test_layering.py`
     enforces both directions: the catalog imports and reads nothing UCSB (proved in a subprocess
     with `usvote.ucsb` made unimportable, not grepped), and **nothing under `usvote/ucsb/` may
     import the catalog** — a back-import would let UCSB inherit the classifications it is meant to
     corroborate, and the control test would pass by construction.
     Three consequences worth recording, because each was a live design choice:
     **(a) The derivation is single-sourced, in the direction that keeps the contract clean.**
     `usvote/pv/status.py` gained `build_roster(..., absences=...)` with `popular_vote` as the
     **residual**; `build_popular_vote_roster` is the empty-map call and `build_curated_roster` is
     the catalog-bound one. The dependency runs `absences -> status`, so `status.py` keeps
     importing nothing from `usvote` and stays underneath every source *and* the catalog.
     **(b) Scope is explicit — `CURATED_YEARS`, with a count pin.** An exceptions catalog's
     *silence* about an un-reviewed year is indistinguishable from a reviewed "no absences here":
     §3's own failure mode, one level up. `build_curated_roster` therefore **raises** outside
     `frozenset(ec_ingest_years())` rather than returning an all-`popular_vote` roster. 1868's four
     rows are catalogued but never consumed, mirroring how `UCSB_NONPARTICIPATING_STATES` retains
     its 1868 trio. (Note for #57: 1868 Florida has **no** in-repo constant behind it today — it is
     parser-derived from UCSB markup — so it needed its own independent citation here.)
     **(c) `note` stays null on curated rows, and that is structural rather than tidy.** The moment
     the catalog's own prose could reach `note`, "no `note` reaches the public snapshot" stops being
     a property of the column's provenance and becomes a reviewed invariant. An absence's cause
     lives in its citation, in code.
     Scope: #140 ships the derivation and its proof only. **No DB write, no new `source` value in
     `dwh.pv_state_status`, no warehouse change** — wiring it into the snapshot build is #139's,
     and the recommendation there is to call the derivation **in-process** at build time rather than
     load a `CURATED` source (a vote-less source never appears in the join view's PV rows, so
     loading it would not have bought a live cross-check anyway).
     **On provenance, stated precisely, because the honest version is narrower than the tempting
     one:** the firewall is over *machine* provenance. The curator did cross-check against UCSB's
     count while scoping the work. Every row is independently attested and independently cited, and
     the exact coincidence with UCSB's set is **corroboration** — nothing here should be read, or
     restated downstream, as "we never looked."
     **CI proves 11 of the 28, and the docs say so.** The `not_participating` rows are verifiable
     both directions against the committed public-domain EC roster fixture (they must be exactly
     1864's zero-EV set). The 17 `legislature_chosen` rows are not — a legislature-appointed state
     cast electoral votes like any other, so the spine cannot distinguish it from a popular-vote
     state — and `TestRealCorpus` **skips in CI** (D022). They are pinned as an explicit expected
     set with non-empty citations, and running that class locally with `USVOTE_UCSB_HTML_DIR` set is
     a **merge precondition** for anything touching the catalog. A UCSB-derived roster fixture must
     **never** be committed to close that gap: committing UCSB's *selection* of absence pairs is
     precisely the compilation question #140 exists to answer.
     One check was attempted and **failed**: the public-domain Archives year pages would have been a
     committable, CI-runnable witness for the 17, but neither the 1824 nor the 1876 page's Notes
     attests how electors were appointed (fetched 2026-08-07). Recorded so it is not re-attempted.
7. **The silent-drop guard is a two-way tested assert**, and is the roster's primary purpose:
   every `popular_vote` roster state has **≥1** `pv_votes` row; every absence-status state has
   **exactly 0**; and every `pv_votes` (year, state) is **in** the roster. The third check is what
   catches a phantom or dropped state that a sum validator cannot see. A **within-page** guard
   complements it: per (year, state), `numeric_cells + not_on_ballot_cells ==
   candidate_column_count` with **no residual**.
8. **`pv_coverage`** — the share of a year's **electoral votes** cast by `popular_vote` states —
   is the honest qualifier on partial-coverage years (see the D009 note below). Weighted by
   electoral votes, not state count, because EV is the analytically relevant weight and is already
   loaded.

**Licensing consequence (extends D022/D016):** the `note` column holds **verbatim UCSB text** and
is therefore `redistributable=false` content — it must be excluded from any public API surface and
must never appear in a committed fixture. The `pv_status` enum is a bare historical fact and
carries no such restriction. Same distinction D022 drew for fixtures, surfacing in a new place.

**Consequence for D009 (strengthens, does not change):** the ~1824 comparison start **stands**. For
a legislature-chosen state the national PV is **not an incomplete measurement of the national
electorate — it is a complete measurement of a smaller one**; those voters never voted, so there
is no missing value to impute and any "adjusted" national PV would be fabrication (D005).
Partial-coverage years therefore remain usable in an EC-vs-PV comparison, reported as *"PV among
states that held one"*, with `pv_coverage` surfaced and a **mandatory caveat wherever a year with
`pv_coverage < 100%` is displayed**. **No exclusion threshold** is set — an arbitrary cutoff would
hide exactly the years the project exists to illuminate. This is grounds to move D009 from
"mutually-agreed pending" toward settled: D009 named E3/E4's data work as the confirmation point,
and that work has now confirmed it *with a mechanism attached*.

**Rationale:**
- **Grain drives structure.** Cases 1–2 assert "this election had no popular-vote event in this
  state" — true independent of any candidate. Expressing it as a candidate-level null is a
  category error that happens to fit in the column.
- **Absence never enters the fact table**, so the corpus finding that `0` is never encoded is
  honored structurally: there is no cell that could be mistakenly zero-filled.
- **A complete roster is the only shape that makes case 2 representable at all** (it has no
  markup) and simultaneously supplies the expected-state roster the silent-drop guard needs — one
  mechanism, two jobs.
- **MIT is not taxed.** Cases 1–2 cannot occur in 1976–2024, and the design imposes no
  shared-shape change; MIT's roster rows are a mechanical `INSERT … SELECT DISTINCT` over
  already-loaded rows.

**Known trade-off (recorded):** modeling cases 3–4 as no-row loses the distinction between
"attested not on ballot" and "absent from our data." Accepted because D007 scopes candidates to
EC-getters, for whom "no row" and "zero votes" are arithmetically identical in every flip and
margin computation. **Revisit trigger:** if the explorer wants "appeared on the ballot in N
states" as a narrative statistic, cases 3–4 need their own table.

**Related:** **D021** (the shipped `dwh.pv_votes` DDL this conforms to rather than amends);
**D018** (absent-row-not-zero-fill, and the "no second source of truth" ruling reapplied here);
**D006** (EC as the source of truth for electoral votes and participation); **D005** (no
fabricated values); **D009** (the ~1824 window, strengthened via `pv_coverage`); **D022**/**D016**
(the redistributability line the `note` column falls on).

**Action required:**
- **#35 (E4-S2)** — parser emits, per (year, state), a classified status + the verbatim note, and
  **raises** on any unclassifiable cell; the no-residual cell-count assert is a tested function.
  - *Clarified 2026-07-18 during the #35 architect review (story boundary only — no part of this
    decision changes).* The parser emits **only `legislature_chosen`**, the sole status readable
    from markup (§4 case 1). `not_participating` has no markup at all (§4 case 2) and
    `popular_vote` is the roster's residual, so **both are assigned in #36**, which per §6 owns the
    only legitimate roster inputs — the EC spine and `UCSB_NONPARTICIPATING_STATES`. §6 forbids
    deriving participation from UCSB markup, so #35's original three-status AC was unsatisfiable as
    written. The parser retains the §7 **within-page** no-residual guard and §4's raise-on-
    unclassifiable rule; the cross-page two-way roster assert stays in #36 per §7.
- **#36 (E4-S3)** — builds the roster from the EC spine + `UCSB_NONPARTICIPATING_STATES`; the
  two-way roster/fact assert is a tested function, scoped by source and in-scope year set;
  `docs/corrections.md` gains the case-2 rows. Per the §6 clarification, UCSB's year scope is
  derived from `ec_ingest_years()`, and **state-name** canonicalization moves here from #38 (the
  roster is keyed on `dwh.state`'s canonical PK, so it must precede the assert); #38 keeps
  **candidate**-name reconciliation.
- **#57** — lifting 1868/1872 from `UNSUPPORTED_EC_YEARS` also admits them to UCSB ingestion; its
  test updates must cover the UCSB roster path (18-vs-17 legislature-chosen count, and
  `UCSB_NONPARTICIPATING_STATES` going from 11 consumed entries to 14).
- **#37 (E4-S4)** — creates `dwh.pv_state_status` and loads UCSB rows; `dwh.pv_votes` is used
  as-shipped (D021).
- **E6** — a small MIT roster-backfill story (derived, not a reopening of #65/#66); `pv_coverage`
  is defined alongside the D017 views; the `note` column is excluded from the public surface.
- **ROADMAP Open Question 6 ("Shared PV record schema") is closed** — resolved by D018/D021, which
  reversed its premise: MIT landed first and defined the shape; UCSB conforms.

---

## D025: UCSB candidate reconciliation scopes to EC-getters via a reciprocal completeness guard

**Date:** 2026-07-20
**Context:** E4-S4 (#38) reconciles UCSB **candidate** names onto the canonical EC candidate
key (D006) *and* applies the D007 candidate scope (MVP = candidates who received electoral
votes). MIT (#67) could require **full coverage** — every native name mapped, else raise —
because D019 had already pre-scoped it to `party_simplified ∈ {DEMOCRAT, REPUBLICAN}`. UCSB
has no party proxy: it prints the top 2–4 candidates each year (majors *and* notable minors
like Debs 1912, Perot 1992/1996, Nader 2000), so scoping to EC-getters *is* a name match, and
telling a legitimately dropped minor from a **forgotten major** needs the EC-getter authority.
The #38 architect review weighed two designs: **Fork 1** — enumerate every UCSB column,
minors included, with an explicit DROP sentinel (full coverage like MIT); **Fork 2** — map
EC-getters only and guard completeness reciprocally.

**Decision:** **Fork 2.** In `usvote/ucsb/reconcile.py`:

1. `UCSB_CANDIDATE_RECONCILIATIONS` maps only EC-getter columns, keyed `(year,
   ucsb_native_name)` → canonical `name` (111 entries; keyed by year because 49 elections reuse
   surnames across different people and drift one person's spelling across years). The 8
   popular-vote-only minors are enumerated in `UCSB_NON_GETTER_COLUMNS` and dropped under D007.
   `_assert_native_coverage` requires **every** UCSB column to be in one bucket or the other —
   an unclassified column raises rather than being silently dropped.
2. Dropping-by-omission is made safe not by enumerating minors (Fork 1's open-ended,
   burden-heavy catalog that D007 exists to avoid) but by a **reciprocal completeness guard**:
   every EC-getter that held a popular vote must survive into the reconciled facts. The getter
   set arrives as an injected `ec_getters` frame (dependency injection, the pattern
   `transform_ucsb` already uses for `ec_participation`), so reconcile stays pure/offline.
3. `EC_GETTERS_WITHOUT_POPULAR_VOTE` (13 entries) exempts EC-getters who by design have no
   popular-vote row — faithless/unpledged electors (1960 Byrd, the 2016 faithless five, 2004
   Edwards, …) and legislature-chosen awards (1832 Floyd, 1836 Mangum). It is historically
   closed. Without it the guard would false-positive on exactly these.
4. This guard is **distinct from and additional to** E6/#69's join-side guard. The #36 two-way
   roster assert operates at `(year, state)` grain and *cannot* catch a forgotten major (its
   states stay non-empty via the other majors), and #69 only ever sees surviving rows — so an
   **ingest-side, candidate-grain** guard here is the only thing that can catch it. #69 still
   owns the reciprocal join-side check that every reconciled name is present in the EC dim.
5. A prerequisite **EC-side** correction strips the 1944 footnote asterisk from the canonical
   name (`Franklin D. Roosevelt*` → `Franklin D. Roosevelt`, via
   `usvote.transform.strip_name_footnote_markers`), so FDR is one cross-year-consistent
   canonical key and UCSB maps 1944 to the clean name.

**Rationale:**
- D007 exists to *bound* the reconciliation burden to the thesis-relevant (EC-getter) set;
  Fork 1's minor catalog is exactly the open-ended list it rejects, and drop-by-omission already
  has precedent (D019 drops non-{D,R} without cataloguing minors).
- The completeness guard, injected offline, gives the anti-silent-drop guarantee that full
  enumeration would — without the catalog — and catches the one failure (a forgotten major in a
  multi-major state) that no later stage can.
- Keying on `(year, name)` resolves recurring surnames and *is* the per-year D007 decision
  (Van Buren won EVs in 1836, ran Free-Soil with none in 1848).

**Action items:**
- **#38 (E4-S4)** — `reconcile_ucsb(pv_votes, roster, ec_getters, *, years)`; the three curated
  constants; `docs/corrections.md` gains the candidate-reconciliation and 1944-asterisk rows;
  `docs/canonical-keys.md`'s UCSB line describes the shipped map. Committed test-input-only
  witness `ec_getters_by_year.json` (names only, D024 §5) drives the offline 49-year guard run.
- **#37 (E4-S5)** — resolves `ec_getters` from `dwh.votes` joined to `dwh.candidate`
  (`president_electoral_votes > 0`, totals rows excluded) and runs reconcile before the load.
- **#69 (E6)** — carries the reciprocal join-side guard that every reconciled UCSB/MIT name is
  present in the EC `candidate` dim.

---

## D026: The EC↔PV join is an EC-left join over the *dense* EC votes fact (year, state, candidate)

**Date:** 2026-07-21 (corrected 2026-07-22 — see "Correction")
**Context:** E6-S2 (#69) joins the resolved PV series onto the EC spine — `pv_preferred` for the
analysis path (E7), `pv_redistributable` for the API path (E8) — reading a **resolved view, never
the raw `dwh.pv_votes` union** (D017; joining the union fans the 1976–2024 overlap out 2× and
double-counts every downstream sum/margin). D017 framed the join as "EC on the left, PV attaches,
missing PV surfaces as an explicit gap," a natural reading of D006 (EC is the source of truth PV
joins *onto*). The project's primary thesis (D001) is a per-state and national **margin** question
— "where does a candidate lose the EC but win the PV, and by how much" — which needs *both* majors'
per-state popular votes, i.e. a losing candidate's per-state row must survive the join.

**Correction (2026-07-22): the premise that drove the first design was empirically false.** The
first draft of #69 adopted a **FULL OUTER "participant" view** on the belief that the EC `votes`
fact is **sparse** — that `build_votes_fact`'s `.dropna(subset=["president_electoral_votes"])`
drops any candidate/state cell with no electoral votes, so a loser (Biden in Texas 2020) has *no EC
row* and an EC-left join would drop them. **That is wrong.** The Archives Table 2 prints `-` for
"won no electoral votes here", and `parse_t2_votes_by_state` reads `-` as **0** (`parse.py:385`),
so `.dropna()` (which only removes the ragged cross-year NaNs of the multi-year `json_normalize`)
drops **no** losers. The CI integration test caught it — `(2016, Texas, Clinton)` came back as a
real EC row with `president_electoral_votes = 0`, not a missing one. Verified across the **entire**
dataset by rebuilding the fact for all years: **49/49 years are rectangular** (`rows == states ×
getters`), and **~59% of state rows (3,162 / 5,327) are explicit 0-EV loser rows**. The EC fact is
**dense**, not sparse.

Consequences: an **EC-left** join already keeps every loser's per-state row (they are 0-EV rows,
with the national rank/`took_office` already broadcast onto them by the transform), so it satisfies
the thesis directly. And because PV is scoped to EC-getters (D007) in participating states (D024),
**every PV key matches a dense EC row** — so the full-outer's PV-only arm was *provably dead*
(`has_ec_state_row` always true, its fill CASE never fired). The full-outer was correct-but-over-
justified machinery resting on a false premise; EC-left is simpler and honest.

**Decision:** Join the EC state-level `votes` rows to the resolved PV view with an **EC-LEFT JOIN**
on `(year, state, candidate)` — `dwh.votes v (WHERE state IS NOT NULL) JOIN dwh.candidate c LEFT
JOIN <pv_view> p ON (v.year, v.state, c.name) LEFT JOIN dwh.pv_source s`. Subordinate to D006 (EC
governs the candidate universe and is the join's left/authoritative side) and D017 (resolved view,
not the union).

1. **Two views, one parameterized builder.** `ec_pv_preferred` (over `pv_preferred`, for E7) and
   `ec_pv_redistributable` (over `pv_redistributable`, for E8) are the same join over a different
   resolved PV view. **Views, not materialized tables** (D017's default).
2. **Three row types the grain expresses:**
   - **winner+PV** — EC actual (electoral votes > 0), PV actual.
   - **loser+PV** — a real EC **0-EV row** (dense fact — *not* a filled/fabricated value), PV
     actual. The rows the thesis is *about*; an EC-left join keeps them because they exist.
   - **getter-without-PV** — EC actual, PV **NULL**. Pre-1976 getters, or faithless getters with no
     popular vote — an honest D005 gap, never a fabricated PV.
3. **Scope is per-year EC-getters, for free.** `pv_preferred` is already D007/D019-scoped to per-year
   EC-getters (D025), and `dwh.votes` only holds getters, so no popular-vote-only minor leaks in.
4. **The dense fact is guarded, not assumed.** Density is what makes EC-left preserve losers, so it
   is asserted rather than left emergent: `assert_rectangular_state_grain` in `build_votes_fact`
   fails loud if any year's state fact is not rectangular (`rows == states × getters`). This closes
   a real seam — `assert_state_count_by_year` only checks the rank-1 winner per state, and
   `assert_totals_equal_state_sum` is blind to a dropped 0-row — before coverage extends below 1892
   (#32) and some early table breaks it silently. **No EC-0 is ever fabricated:** every electoral
   value comes straight from `dwh.votes`; a getter with no PV keeps NULL PV (D005).
5. **National context via a window SUM.** `national_electoral_votes` is
   `SUM(president_electoral_votes) OVER (PARTITION BY year, candidate_id)` — exact because the fact
   is dense and the state-sum equals the published national total (`assert_totals_equal_state_sum`),
   so it needs no join to the `is_total` rows; `president_electoral_rank`/`took_office` are already
   broadcast onto the state rows by the transform. Flip detection reads off this one view.
6. **This module is EC-domain.** `src/usvote/join.py`, a **sibling to `usvote/spine.py`** (not under
   `usvote/pv/`), because it names `dwh.votes`/`dwh.candidate` — the greppable invariant "**nothing
   under `usvote/pv/` names `dwh.votes`**" forbids a `pv/` home.
7. **The reciprocal guard is a fact-level anti-join, and load-bearing.** Under an EC-left join a PV
   row matching **no** EC votes row is *silently dropped* (the project's documented inner-join
   footgun). So the guard #69 owns (`docs/canonical-keys.md`) is stronger than dim-membership: a
   `NOT EXISTS` anti-join asserts every resolved PV `(year, state, candidate)` matches an EC state
   row `(year, state, name)`, failing loud with the offending keys as a **view-creation
   precondition**. It also catches a D007 getter-scope violation, or a name/state that exists in the
   dims but not for that election. Supporting the `c.name` join, **`UNIQUE(name)` is added to
   `dwh.candidate`** (D021's table carried `candidate_id` PK, `name` unconstrained).
8. **Winner-has-PV coverage guard (EC→PV direction).** Complementing the anti-join, an EC **winner**
   (`president_electoral_votes > 0`) inside the PV window with no PV is a reconciliation miss and
   fails loud — keyed on `> 0`, **not** every EC row, because a *loser*'s 0-EV row may legitimately
   lack PV (a regional candidate like Thurmond 1948 on the ballot in only some states). Exemptions
   are the getters that legitimately held no popular vote (`EC_GETTERS_WITHOUT_POPULAR_VOTE`,
   promoted to the dependency-free `usvote/getters.py`). It returns its inspected-winner count so a
   caller asserts a vacuity floor. Wired live in the gated real-corpus integration test over
   `ec_pv_preferred`.
9. **Honest consumer split.** E7 reads `ec_pv_preferred`; E8 reads `ec_pv_redistributable`, which
   **never surfaces a `redistributable=false` (UCSB) row** — inherited from `pv_redistributable`'s
   independent `WHERE redistributable` (D017/D002/D014/D016), not re-derived at the join.

**Rationale:**
- **Match the data, not an assumption.** EC-left is the simplest join that satisfies the thesis
  *given the dense fact*; the full-outer's PV-only arm and 0-fill were solving a non-problem. When a
  premise turns out false, the honest fix is to remove the machinery it justified, not keep it.
- **Density is now guarded, not lucky.** The rectangularity assert makes the property the whole
  simplification rests on a checked invariant — so a future ragged early table (below 1892, #32)
  fails at the transform, not as a silently-dropped loser downstream.
- **Fail-loud over silent surfacing.** EC-left's one risk (a dropped unmatched PV row) is caught by
  the anti-join precondition — a loud failure with keys beats a full-outer's silently-visible row.
- **Forward-compatible.** A third PV source drops in via #68's data-driven precedence with no change
  to the join, which reads whatever `pv_preferred`/`pv_redistributable` resolve to.

**Related:** **D017** (resolved views not the raw union); **D006** (EC as source of truth — the
join's left/authoritative side); **D005** (no fabricated PV — NULL-not-zero on the PV side);
**D007**/**D024** (getter + participating-state scope that makes PV ⊆ the dense EC rows);
**D021** (the `dwh.candidate` DDL this adds `UNIQUE(name)` to); **D002**/**D014**/**D016** (the
`redistributable=false` boundary `ec_pv_redistributable` must not cross); **D020**/**D025** (#69
carries the reciprocal name-in-dim guard those defer to it, now fact-level); **#89** (the missing EC
HTML snapshot that made verifying density require a full live re-scrape).

**Action required:**
- **#69 (E6-S2)** — implement `usvote/join.py`: the parameterized EC-left builder, the two views
  (`ec_pv_preferred`, `ec_pv_redistributable`), the national-EV window sum, the fact-level anti-join
  precondition, and the winner-has-PV coverage guard.
- Add **`assert_rectangular_state_grain` to `build_votes_fact`** (guards the dense-fact premise).
- Add **`UNIQUE(name)` to the `dwh.candidate` DDL** (supports the `c.name` join).
- Promote **`EC_GETTERS_WITHOUT_POPULAR_VOTE` to `usvote/getters.py`** (a second cross-boundary
  consumer — the winner-has-PV guard — makes it an EC-domain fact, not a UCSB one).
- **Automated tests:** no-fan-out; the anti-join guard (a PV row matching no EC row fails loud);
  rectangularity (a dropped loser row fails at the transform); a **split-vote state** (ME/NE — each
  getter keeps its real EC count); winner-has-PV over the real corpus with the exemption set + a
  vacuity floor; and the `ec_pv_redistributable` leak-guard.

## D027: Package entry points are subcommand-based, with a top-level `warehouse.py` composition root

**Date:** 2026-07-22
**Context:** #84b, split out of #84 (84a landed the `DBC.transaction()` primitive + the uniform
per-pipeline ownership rule). Before this, the three ingest entry points disagreed on what
`python -m X` meant: `python -m usvote` ran the whole EC pipeline, `python -m usvote.ucsb`
*snapshotted* raw HTML (not a pipeline run), and `usvote.mit` had no `__main__` at all. The same
spelling meant "run the pipeline" for EC and "fetch raw data" for UCSB. E6 also needs a single
one-command build of the entire warehouse (EC spine + both PV sources + the E6-S2 join views), which
no entry point provided.

**Decision (five parts):**

1. **All package `__main__`s are subcommand-based, but every bare invocation keeps its historical
   meaning as a *named default subcommand*.** `python -m usvote` → EC (subcommands `ec`, `all`);
   `python -m usvote.ucsb` → snapshot (subcommands `snapshot`, `load`); `python -m usvote.mit` → load
   (single `load` subcommand). The issue framed the wart as "same spelling, different meaning"; this
   **reduces it to a documented default, not eliminates it** — `python -m usvote` loads and
   `python -m usvote.ucsb` snapshots still differ, but each is now a discoverable default, and the
   asymmetry is principled (only UCSB has a network stage to snapshot; MIT reads a local CSV).

2. **Bare `python -m usvote` stays EC — it is *not* re-pointed at `all`.** `all` additionally requires
   `USVOTE_MIT_CSV_PATH` (and the UCSB snapshot for the full set), so making bare mean `all` would
   *raise* the config bar on the single most common command and break a CLAUDE.md-documented
   invocation. Backward compatibility (including bare `--replace`) is preserved; the whole-warehouse
   build is the explicit `all` subcommand.

3. **The whole-warehouse orchestrator lives in a new top-level `usvote/warehouse.py`
   (`run_warehouse`), a composition root — NOT inside `usvote/pipeline.py`.** `warehouse.py` imports
   *from* every source (EC + `usvote/mit` + `usvote/ucsb`). Putting that wiring in `pipeline.py` (an
   EC-spine module) would make the EC spine import the PV sources — the exact D015 source-to-source
   inversion. A composition root sits **above** both EC and PV, like `usvote/__main__`, so it is
   exempt from the prohibition for the same reason `__main__` is. The exemption is kept honest by the
   reverse invariant — **nothing under `usvote/{mit,ucsb,pv}/` imports `usvote.warehouse`** — enforced
   by a test mirroring the greppable `dwh.votes` guard (a back-import would invert D015 into a cycle).

4. **The build is per-source atomic, not globally atomic; recovery is `--replace`, not a bare
   re-run.** `run_warehouse` opens **no** transaction of its own — each pipeline already owns its
   DB-write transaction (84a's uniform rule), and `DBC.transaction()` raises on a nested open, so the
   orchestrator sequences them and never wraps them. Consequence: a mid-build failure leaves the
   already-committed sources in place and later ones absent. Because the PV/EC loaders are
   create-if-absent/append, a bare re-run raises a unique/PK violation on the first already-loaded
   source before it reaches the missing one, so the honest recovery path is
   `run_warehouse(..., replace=True)` (a clean full rebuild). Network/scrape stays outside every
   transaction, so no build holds one open across HTTP.

5. **`--replace` maps EC-destructive + PV-additive, and the join views are always rebuilt.** For `all`,
   `--replace` forwards to `run_ec_pipeline(replace=True)` (which does `DROP SCHEMA dwh CASCADE`,
   taking the PV tables *and* the E6-S2 views with it) while the PV sources load `replace=False` onto
   the fresh schema — the only sane mapping, and exactly the integration-test order. The resolved-PV +
   EC↔PV join views are therefore **always rebuilt as the final step** (`build_pv_union` +
   `create_ec_pv_views`, both idempotent, both transaction-free): without that rebuild a `--replace`
   build would leave the warehouse with fact tables but no `ec_pv_preferred`/`ec_pv_redistributable`
   for E7/E8 to read. For a single-source subcommand (`usvote.mit load --replace`,
   `usvote.ucsb load --replace`) `--replace` is instead *table-level* (rebuild that source's PV
   table(s), never the schema) — one flag, two scopes, spelled out in `--help`.

**Alternatives rejected:** bare `python -m usvote` → `all` (raises the config bar, breaks a documented
command — part 2); orchestrator inside `pipeline.py` (D015 inversion — part 3); a global transaction
across the whole build (would hold one open across HTTP scrapes, and 84a's raise-on-nest forbids it —
part 4); a per-source `--replace` matrix (overkill — part 5); env-magic UCSB gating inside
`run_warehouse` (the programmatic seam takes an explicit `ucsb_html_dir=None` to skip; only the CLI
auto-detects `USVOTE_UCSB_HTML_DIR`, and only *loudly* with a printed notice + `--require-ucsb`, so a
warehouse silently missing the UCSB analysis-only control can never happen — D024/D017).

**Related:** **#84a** (the `DBC.transaction()` primitive + uniform per-pipeline ownership this builds
on); **D015** (source-namespacing / no source-to-source imports — the composition-root carve-out
here); **D023** (the UCSB snapshot, why `python -m usvote.ucsb` defaults to `snapshot`); **D024**/
**D017** (missing data modeled explicitly, never silent — the loud UCSB gating and the structured
`WarehouseResult`); **D016** (EC + MIT = the redistributable public core, UCSB = the analysis-only
control — why a fresh public clone builds EC + MIT and skips UCSB); **D026** (the join views
`run_warehouse` rebuilds); **E7/E8** (the `ec_pv_preferred`/`ec_pv_redistributable` consumers the
always-rebuild step and the `WarehouseResult` receipt are designed for).

**Action required:**
- Add `usvote/warehouse.py` (`run_warehouse`, `rebuild_views`, `WarehouseResult`) — done.
- Rewrite `usvote/__main__.py` (subcommands `ec`/`all`, bare = EC), add `usvote/mit/__main__.py`
  (`load`), rewrite `usvote/ucsb/__main__.py` (subcommands `snapshot`/`load`, bare = snapshot) — done.
- Add the reverse-import guard test (nothing under `usvote/{mit,ucsb,pv}/` imports `usvote.warehouse`)
  and CLI/orchestrator unit tests; point the live-DB integration test at `run_warehouse` (the shipped
  path) — done.
- A future `views` subcommand (rebuild views without re-scraping) is a thin wrapper over
  `rebuild_views`; the dispatch is left open for it (#84 follow-up).

---

## D028: The E8 API serves a read-only embedded snapshot, not a live database

**Date:** 2026-07-23
**Context:** E8 (#94) exposes `ec_pv_redistributable` over HTTP. The obvious design points the
API at the warehouse Postgres, but that makes Postgres a production runtime dependency — the one
component that will not scale to zero (a managed instance carries a monthly floor even at zero
traffic) and the one most likely to fail a request. The redistributable dataset is tiny and
read-mostly (~a dozen elections × ~51 jurisdictions × the D/R nominees, refreshed on a ~4-year
cadence + occasional corrections), so a live query engine is disproportionate to the workload.

**Decision:** The API reads a **read-only embedded snapshot** materialized from
`ec_pv_redistributable`, with **no live DB at serve time**. Postgres stays the *local* warehouse /
source of truth. Refined per the E8 architect review (three parts):

1. **The snapshot store is SQLite** (stdlib `sqlite3` driver — zero runtime deps, indexed
   by-year/by-state/by-candidate filtering, a `meta` table for provenance), not static JSON. The CDN
   caches API *responses*, not the store, so JSON buys no caching edge; SQLite ages better as
   coverage widens (S8 hybrid columns, a possible pre-1976 extension).
2. **"No live DB at serve time" is a structural import-graph invariant, not a runtime property.**
   The snapshot *build* reads Postgres, so it lives in a new top-level `usvote/snapshot.py` (an
   EC-domain consumer of `ec_pv_redistributable`, in the `spine.py`/`join.py`/`warehouse.py` family,
   composition-root-exempt from D015 per D027) — **not** inside `usvote/api/`. `usvote/api/` imports
   only the snapshot artifact + a thin `SnapshotRepository`, and a unit test asserts nothing under
   `usvote/api/` imports `usvote.db` or psycopg2 — mirroring the project's existing greppable layering
   guards (`dwh.votes` not named under `pv/`; `usvote.warehouse` not imported under the sources).
3. **The snapshot version is a content hash, not a build timestamp.** `snapshot_version` = a hash of
   the data rows extracted with a deterministic `ORDER BY (year, state, candidate)` (+ a schema
   version); the build timestamp is informational metadata only, excluded from the version and the
   ETag. A timestamp would break both the byte-reproducibility AC and cache correctness (identical
   data must yield an identical ETag).

**Rationale:**
- Cost/reliability/ease all point the same way: a scale-to-zero container serving an immutable
  SQLite file has no DB to provision, connection to drop, or floor to pay, and runs standalone in
  local dev with Postgres stopped.
- Making the DB-free property *structural* means a future change can't quietly reintroduce a live
  query path without failing a test — the same discipline the rest of the package already relies on.
- A content-derived version is the single value that reconciles reproducibility with the freshness
  contract (D-below) and lets a second consumer cache honestly.

**Related:** **#94/#95/#96** (E8 epic + the snapshot-build and app-skeleton stories); **D026**
(`ec_pv_redistributable`, the view the snapshot reads); **D027** (composition-root exemption reused by
`usvote/snapshot.py`); **D017** (redistributable surface); **[[nan-none-db-boundary]]**-style single
write chokepoint, applied here to the single *read/materialize* chokepoint.

**Action required:**
- Add `usvote/snapshot.py` (materialize `ec_pv_redistributable` → SQLite; content-hash version;
  national roll-up table; drop `candidate_id`, mint the public slug — see D-slug below) and its build
  entry point.
- Add the `usvote/api/`-imports-no-DB guard test.

---

## D029: E8's API MVP is decoupled from E7 — it depends only on E6's join view

**Date:** 2026-07-23
**Context:** The ROADMAP's original critical path read `E7 (hybrid) + E9 (mart) → E8 (API)`. But E6
landed `ec_pv_redistributable`, and the API MVP (redistributable EC+PV at the canonical grain) needs
nothing from the hybrid computation to be useful and to power our app.

**Decision:** The **E8 API MVP depends only on E6** (`ec_pv_redistributable`), not on E7 or E9. Hybrid
/ flip / margin fields are added to the API as a **later story (E8-S8, #102), gated on E7** — arriving
as new *optional* response fields under the same `/v1` (additive, non-breaking) and flowing through
the same snapshot materialization seam (no second extract path). The ROADMAP critical-path note is
updated to match; E9 (mart) may later become an additional read source behind the same
`SnapshotRepository` seam but is not an MVP dependency.

**Rationale:**
- Shipping the foundation now (a robust, public-graduation-ready surface over data that already
  exists) beats waiting on hybrid work for a first release, and matches the "running quickly on a
  robust foundation" goal.
- Because hybrid is only defined on the redistributable window, S8 stays automatically D030-consistent
  and additive — so decoupling costs no rework, it only reorders.

**Related:** **#94/#102** (epic + the E7-gated hybrid story); **D011** (hybrid computation, E7);
**D026** (the E6 view); ROADMAP "First-cut epic outline" critical path (edited alongside this entry).

**Action required:** Edit `docs/ROADMAP.md` so the critical path reflects E6 → E8 (MVP) directly,
with E7 + E9 → the explorer and E8's later hybrid fields — done alongside this entry.

---

## D030: The API surface is redistributable-only from day one

**Date:** 2026-07-23
**Context:** E8 will eventually graduate to a public/third-party API (D002), gated on PV licensing
(D008/D014). UCSB PV is `redistributable=false`; MIT is the redistributable modern core (D016). The
question was whether the *internal* MVP could serve everything and filter later, or exclude
non-redistributable rows from the start.

**Decision:** The API serves **only redistributable rows from the first release** — it reads
`ec_pv_redistributable`, which wraps `pv_redistributable`, defined *independently* as
`WHERE redistributable` (D017). No preference-resolution or later feature change can leak a UCSB row
onto the API surface. Defense-in-depth: the redistributable-only guarantee is re-asserted at the
snapshot source (E8-S1), the endpoints (E8-S3), and a regression test (E8-S5).

**Rationale:**
- Building the internal MVP on exactly the surface the public API will use means **zero rework at
  graduation** — the licensing boundary is structural (an invalid state is unrepresentable), not a
  filter someone must remember to apply.
- The CC0/UCSB stakes justify the triple guard as proportionate, not gold-plating.

**Related:** **#94** (epic); **D002** (public-API deliverable + gate); **D008/D014** (PV licensing);
**D016** (EC + MIT = redistributable core, UCSB = analysis-only); **D017** (`pv_redistributable`
defined independently as `WHERE redistributable`); **[[inner-join-silent-drop]]** (why the guard is
tested, not assumed).

---

## D031: The API is FastAPI/REST with `/v1` and OpenAPI-as-a-deliverable, not GraphQL

**Date:** 2026-07-23
**Context:** The stack choice was FastAPI/REST vs. GraphQL (both viable in Python). The dataset is
small and tabular with a few obvious query patterns (by year / state / candidate + a national
summary), and a near-term goal is advertising the API to the MIT Election Lab.

**Decision:** **FastAPI (REST)**, versioned `/v1` from day one, with the **auto-generated
OpenAPI/Swagger docs treated as a first-class deliverable** (its own story, E8-S4) — the
self-documenting surface *is* half the pitch to external consumers. No pagination for the MVP (every
endpoint is already scoped by year/state/candidate; the whole corpus is low-thousands of rows), but
`meta.count` is retained and a server-side cap prevents any unbounded path, so pagination stays an
additive change. Freshness contract: a **content-hash ETag** (per D028) plus
`Cache-Control: public, max-age=3600, stale-while-revalidate=...`, emitted from the app locally so the
CDN step (E8-S7) is config, not code. CORS via a `USVOTE_API_CORS_ORIGINS` env allow-list (localhost
default, never a silent `*`).

**Rationale:**
- GraphQL's flexibility buys little for a handful of fixed query shapes and costs a learning curve,
  harder CDN caching (POST queries don't cache as cleanly as REST GETs), and more surface area.
- REST GETs + OpenAPI are the more discoverable, cacheable, standard choice for a public reference-data
  API; a GraphQL layer can be added later if a real consumer demands it.
- `/v1` and cache headers on day one are near-free hedges that make the public/Cloud-Run graduation a
  config step rather than a rewrite.

**Related:** **#94/#96/#97/#98** (epic + skeleton/endpoints/docs stories); **D002** (public-API
graduation the OpenAPI asset serves).

---

## D032: The API ships as a cloud-agnostic container with the snapshot baked in; Cloud Run is the post-MVP target

**Date:** 2026-07-23
**Context:** Hosting was Open Question #3 (undecided infra). Priorities: cost > reliability > ease,
with initial traffic tiny (our own dashboard) and a likely later pivot to a cloud provider once the
API is advertised. Candidates considered: Cloud Run, Fly.io, Render/Railway, Vercel.

**Decision:** The MVP **runs locally** and ships as a **cloud-agnostic container** (no
provider-specific coupling), with the **snapshot baked into the image** (snapshot-version ==
image-version, so no runtime mount and no artifact/code version skew). The **eventual cloud target is
Google Cloud Run** — scale-to-zero, pay-per-request, portable container, generous free tier — but the
actual deploy (+ CDN, custom domain, auth/rate-limiting posture) is a **later/stretch story
(E8-S7, #101)**, not an MVP commitment. Vercel is rejected as a Python-second-class frontend platform;
Fly.io/Render remain fallbacks if Cloud Run's cost profile changes.

**Rationale:**
- A baked-in immutable snapshot on a scale-to-zero container is the cheapest and most reliable option
  at our volume, and the refresh path (rebuild-and-redeploy) is fine precisely because data changes
  every ~4 years.
- Keeping the container provider-agnostic means the hosting decision can be deferred/changed without
  touching application code — cost is the top priority and the market moves.

**Related:** **#94/#100/#101** (epic + Dockerfile + Cloud-Run-deploy stories); **D028** (the baked-in
snapshot); ROADMAP Open Question #3 (this decision resolves the API-hosting half).

## D033: The API container installs a slim serve-only dependency closure, not the full package deps

**Date:** 2026-07-24
**Context:** E8-S6 (#100) containerizes the API (D032: cloud-agnostic image, snapshot
baked in). A full package install drags the warehouse/analysis stack — pandas, geopandas,
GDAL, psycopg2, matplotlib — into the image (hundreds of MB, slow cold start), failing the
AC that the image be "reasonably small and starts fast (scale-to-zero friendly)." But the
API serve path never uses that stack: `usvote/api/` imports only fastapi/starlette/pydantic
+ `usvote.snapshot_schema`/`usvote.config` (both stdlib-only) + stdlib — the D028
import-graph invariant.

**Decision:** The container installs the `usvote` package with `--no-deps` and adds only the
serve-time closure (fastapi, uvicorn, pydantic), whose versions are resolved from `uv.lock`
via a dedicated `serve` dependency-group (never hand-pinned literals in the Dockerfile, which
would fork the version truth from the lock). The container's runtime dependency closure thus
**intentionally diverges** from the package's declared base dependencies — the D028
import-graph invariant is what makes that divergence safe, and this decision elevates that
invariant from a code-layering guard to a load-bearing deployment guarantee. An `api` *extra*
is explicitly **not** the mechanism: extras are additive and cannot subtract the heavy base
deps; the size lever comes from `--no-deps` + the lock-derived serve group.

**Rationale:**
- Slim is required to meet the scale-to-zero AC; the import graph is already test-enforced,
  so the closure divergence rests on an existing invariant, not a new hope.
- Sourcing serve versions from `uv.lock` keeps a single version source of truth; CI and the
  container resolve the same fastapi/uvicorn/pydantic.
- The divergence introduces a silent-drift failure mode (an allowed-but-unpackaged import
  added to `usvote/api/` — e.g. httpx — passes the denylist import-graph test but breaks the
  slim image at `docker run`). This is guarded by the CI docker job running the built image
  and hitting `/health` (a container smoke test), not by a bespoke positive-allowlist test.

**Related:** **D028** (import-graph invariant this exploits), **D032** (the container/hosting
decision this refines), **#100** (E8-S6), `tests/unit/test_api_import_graph.py`.

## D034: Deploy the API to Cloud Run behind Cloudflare (free), keyless via WIF, with a GCS-sourced CI-built image and version-based edge caching

**Date:** 2026-07-24
**Context:** E8-S7 (#101) graduates the D032 cloud-agnostic container to a public host. Roadmap Open Question #3's hosting half. Priorities (owner, 2026-07-24): cost first (scale-to-zero, single instance), then request throttling/anti-bot, then reliability. Locked human decisions: Cloudflare **free** plan in front (not a GCP HTTPS LB, whose ~$18–25/mo fixed cost fights scale-to-zero); deploy via **GitHub Actions + Workload Identity Federation** (keyless). Provisioning is owner-run (owner's GCP + Cloudflare creds); the repo ships deploy glue + runbooks + the app changes.

**Decision:**
1. **Host:** Cloud Run, `--min-instances=0 --max-instances=1`, request-based CPU, single region, `--allow-unauthenticated --ingress=all`, fronted by Cloudflare (proxied DNS on an owner-supplied custom domain) for CDN + rate limiting + Bot Fight Mode. A GCP Billing Budget → Pub/Sub kill-switch sets `max-instances=0` on spend threshold (Cloud Run has no native hard cost cap).
2. **Snapshot → image:** the snapshot is a **data input** to a **CI-built** image, not a locally-built image. It lives in a private, object-versioned **GCS bucket**; the deploy workflow pulls it into the build context, builds in Actions, pushes to **Artifact Registry**, deploys. The image is tagged with the `snapshot_version` content hash. Refresh (AC4): rebuild snapshot locally from the warehouse → upload to the bucket → run the deploy workflow. Rejected: local build+push (laptop-tied, fails AC3); Actions/release artifacts (expiry / support-commitment overhead).
3. **Origin lock-down:** a stdlib-only app middleware requires a shared-secret header (injected by a Cloudflare Transform Rule) on `/v1` — **only when `USVOTE_API_ORIGIN_SECRET` is set** (fail-open for local dev/tests/smoke), `/health` always exempt (Cloud Run probes and the D033 smoke test don't traverse Cloudflare). Chosen over Cloud Run ingress/IAM/mTLS, all of which the no-LB decision or Cloud Run's TLS model rule out. Fail-open is made safe by (a) surfacing enforcement state in `/health` + a startup log line and (b) a post-deploy workflow assertion that raw `run.app` `/v1` returns 403 and the Cloudflare hostname returns 200.
4. **Caching:** version-based, not TTL. The response header stays moderate and honest to all caches — `public, max-age=3600, stale-while-revalidate=86400, stale-if-error=86400` + the strong `snapshot_version` ETag. The *long* hold lives in a Cloudflare **Cache Rule Edge Cache TTL** (purge-reachable), and the deploy workflow **purges the Cloudflare cache after the new revision is serving traffic**. This keeps true scale-to-zero (edge absorbs reads; browser revalidations terminate at the warm edge and never wake the origin) while a bug-fix deploy reflects promptly (new ETag + moderate browser max-age + edge purge).
5. **Deploy auth/secrets:** WIF provider attribute-locked to this repo; two least-privilege service accounts (deploy vs runtime); Cloudflare purge token (cache-purge, single zone) in GitHub Actions secrets; `USVOTE_API_ORIGIN_SECRET` in GCP Secret Manager bound to the service. Deploy trigger is `workflow_dispatch` (+ optional tag), never `pull_request`.

**Rationale:**
- Cloudflare-free + scale-to-zero + single instance is the cheapest posture that still gets CDN + rate limiting; a GCP LB's fixed floor contradicts the top priority.
- A CI-built image over a GCS-sourced snapshot satisfies "reproducible, not laptop-tied" while respecting that the snapshot itself can only be produced from the local warehouse.
- The version-based cache model exploits the ~4-yearly data cadence: reads never wake the origin between versions, and invalidation is an explicit purge keyed to the content hash rather than a TTL guess.
- The origin secret is the only lock-down layer available once a GCP LB is off the table; making its enforcement observable + post-deploy-asserted converts a fail-open footgun into a verified control.

**Related:** **#101** (this story); **D028** (DB-free snapshot + content-hash ETag the cache/purge model rests on); **D030** (redistributable-only, reconfirmed in the hosted context); **D031** (`/v1` + the `Cache-Control`/ETag contract emitted locally so the CDN step is config); **D032** (cloud-agnostic image + Cloud Run target this realizes); **D033** (slim image + import-graph invariant the middleware must not break); ROADMAP Open Question #3 (hosting half).

## D035: The Cloudflare front is a Worker, not Origin/Transform/Cache Rules (free-plan reality)

**Date:** 2026-07-25
**Context:** D034 specified the Cloudflare front as zone Rules — an **Origin Rule "Host Header Override"** (so Cloud Run's Host-routed `run.app` front end accepts the request), a **Transform Rule** to inject the origin secret, and a **Cache Rule** for the edge TTL. During provisioning (#101) the free Cloudflare plan turned out to **paywall Origin Rules "Host Header Override"** — and without it a proxied `CNAME api → run.app` returns a **Google 404**, because Cloud Run's front end routes by the HTTP `Host` header, which Cloudflare forwards as `api.<domain>` (unknown to Cloud Run).

**Decision:** Front Cloud Run with a **Cloudflare Worker** (`usvote-api-proxy`, bound as a Custom Domain on `api.<domain>`) instead of zone Rules. The Worker: (1) rebuilds the request against the `run.app` URL so the outbound Host is `run.app` (fixes the 404); (2) injects the `X-Usvote-Origin-Secret` header from a Worker **secret binding** (replaces the Transform Rule); (3) caches `GET /v1` 200s via the **Cache API** with a long `s-maxage` edge hold + moderate browser `max-age` (replaces the Cache Rule). Rate limiting + Bot Fight Mode stay zone-level WAF features (the Worker does not rate-limit). This **supersedes D034's Cloudflare *mechanism* only** — D034's *intent* is unchanged and fully preserved: origin-locked (`run.app/v1` → 403, Cloudflare → 200), version-based edge caching, purge-on-deploy (`purge_everything` clears the Worker's `caches.default`), scale-to-zero. The deploy workflow (`deploy.yml`) is unaffected — its post-deploy 403/200 smoke and cache purge work identically against the Worker.

**Also recorded here:** the origin secret must be stored **without a trailing newline**. `openssl rand -hex 32 | gcloud secrets versions add` stores the `\n`, which Cloud Run injects, so the lock 403s (the Worker's clean header value ≠ stored `value + \n`). Use `printf '%s' "$(openssl rand -hex 32)"`.

**Related:** **D034** (the deploy decision whose Cloudflare mechanism this revises), **#101**, `docs/deploy-cloud-run.md` (§4 + §7 updated), `.github/workflows/deploy.yml` (unchanged). Live at `https://api.us-presidential-election-center.org`.

---

## D036: The Archives HTML corpus lives outside the tree, mirrors the UCSB corpus, and is guarded for completeness

**Date:** 2026-07-26 (#89)

**Context:** Refreshing the SQLite snapshot that serves the public API (D034) meant rebuilding the
warehouse, and rebuilding the warehouse re-scraped ~49 archives.gov pages every time. The
capability to avoid that already existed but was unreachable: `run_ec_pipeline` and
`run_warehouse` both accept a `fetch` seam, and `__main__` never passed one. Unlike UCSB, Archives
data is **public domain**, so D022's licensing prohibition does not apply and committing the
corpus into the repo was genuinely available.

**Decision:**

1. **Stored outside the tree** (owner's call, 2026-07-26), at `USVOTE_EC_HTML_DIR`, alongside
   `ucsb_raw/` — *not* committed. The reason differs from UCSB's: UCSB is **forced** out of the
   tree by D022 licensing; EC is a **deliberate choice** for public-domain data. The benefit is a
   uniform rule ("raw source HTML lives outside the tree, full stop") with no per-source exception
   to remember. The accepted cost is that the network-free-CI benefit #89 originally claimed is
   **unreachable, not deferred** — CI has no corpus, so the all-years parser regression is a
   local-only test that skips when the variable is unset, exactly like UCSB's `TestRealCorpus`.
2. **Layout mirrors the UCSB corpus exactly** — `<year>.html`, `_index_results.html`, and a
   `manifest.json` whose per-entry keys are `bytes`/`file`/`http_status`/`sha256`/`timestamp`/`url`.
   This required a **second reader**: `fetch_from_dir` resolves URLs through `_snapshot_filename`
   to `www_archives_gov_electoral_college_1824.html`, the naming the committed `tests/fixtures/`
   pages use and must keep. The two readers coexist as they already do on the UCSB side.
3. **The corpus is optional and auto-detected, but verified before use.** Skipping UCSB merely
   builds without an optional control; swapping the EC fetch source changes where the *spine's*
   data comes from, so a detected corpus is checked complete first. A **set-but-broken**
   `USVOTE_EC_HTML_DIR` is an error, never a silent fallback to live scraping — the whole point is
   that an operator who asked for an offline rebuild does not silently get 50 live requests.
4. **The index is re-fetched every run.** Year URLs are enumerated *from* the saved index, so
   skipping it made a stale corpus permanently unrepairable: it could never discover a
   newly-published election, and the completeness guard failed forever while prescribing the very
   command that did nothing. Skipping a *year page* additionally requires a matching 200 manifest
   entry, so a corpus copied without its manifest repairs itself instead of bricking.
5. **Two completeness guards, because a frozen corpus makes an existing silent-drop hazard
   likelier.** `scrape_raw_election_tables` iterates the links found in the index and only warns
   about years it does not *recognize* — so a year that is requested but absent from a stale index
   was never fetched and never reported, the build exited 0 one year short, and
   `assert_state_count_by_year` could not see it (it iterates the years that *are* present). That
   partial warehouse feeds the public API snapshot. `scrape.assert_corpus_covers_years` is the
   corpus-side precondition; `pipeline._assert_years_scraped` is the backstop covering the **live**
   path too. Neither intersects with `ec_ingest_years()`, so an explicitly requested out-of-scope
   year still fails loudly (the `usvote.years` contract).

**Rationale:** The corpus is a *cache of immutable historical fact*, not a source of truth — the
warehouse remains that. What makes it safe to build on is that every way it can be wrong (stale,
partial, manifest-less, redirected, corrupt JSON) fails loudly at a named boundary rather than
silently producing a short warehouse.

**Action required:** The **live** scrape path (`fetch_url`) still sends no User-Agent and no crawl
delay, while `archives.gov/robots.txt` asks for `Crawl-delay: 10` and the new snapshot driver
honors both. Bringing the live path up to the same posture would make a cold `--replace` ~8.5
minutes for anyone without a corpus — a real behavior change, so it is tracked as its own issue
rather than smuggled into #89.

**Acknowledged residual (added after the post-implementation architect pass, 2026-07-26):**
The guards close **presence** divergence — a year missing from the corpus, the index, or the
manifest fails loudly. They do **not** close **content** divergence:

- an Archives **in-place correction** to a page that is present and 200 is never noticed, because
  a year page on disk is not re-fetched; the old bytes are replayed forever, and
- a year file corrupted **after** it was saved passes the presence guard, because the `sha256` the
  manifest records is written but never read back.

Both are low-likelihood and cheap to close (a `--refresh` flag that re-fetches all and diffs the
recorded hashes; verify-on-read in `fetch_from_corpus`), and both are filed as follow-ups rather
than fixed here. Until then, "a corpus-backed rebuild equals a live-scraped one, or fails loudly"
holds for *presence* only — which is the property the silent-partial-warehouse hazard needed, but
it is not the whole claim, and this paragraph exists so the gap is not mistaken for coverage.

---

## D037: The hybrid is the average of a candidate's EC-vote share and PV share; highest average wins

**Date:** 2026-07-28

**Context:** E7 (Milestone 3) must compute the project's third method of determining a winner — the
**hybrid**, Fred's original contribution — but the roadmap named it in one line and never scoped the
formula, the computation's home, or how one computation serves both the analysis surface and the
public (redistributable) surface. E6's EC↔PV join views (`ec_pv_preferred`, `ec_pv_redistributable`,
D026) have shipped and are the substrate E7 reads.

**Decision:** `hybrid_score = (ec_share_hybrid + pv_share) / 2` — for each candidate in an election,
average their share of the electoral votes with their share of the national popular vote; the highest
average wins. The EC share is deliberately **split in two**: `ec_share_full` (policy-invariant, the
**only** input to `ec_determinative`) and `ec_share_hybrid` (policy-selected, feeds `hybrid_score`
only) — so no coverage policy can ever manufacture or destroy an EC majority. The computation lands as
**`src/usvote/hybrid.py`**, a top-level EC-domain module (sibling of `join.py`, D015/D027), a **pure
computation parameterized by which resolved join view it reads** ("two views, one builder", D026): over
`ec_pv_preferred` it emits `hybrid_preferred` (analysis, full history); over `ec_pv_redistributable`
it emits `hybrid_redistributable` (API, MIT-only). Margins are **percentage-point** top-2 gaps only.
The deliverable is computed data + validated logic, not charts (D001/D011). **Roll-up ownership (OQ4,
resolved by the architect):** the shared national-aggregation derivation is single-sourced **now** —
the primitive is extracted into `usvote/hybrid.py` and `snapshot.build_national_rollup`
(`snapshot.py:203`) calls it, touching neither the snapshot's source view, public columns, nor
`SNAPSHOT_SCHEMA_VERSION`; the two roll-up **tables** stay separate for MVP (D029).

**Rationale:**
- Splitting the EC share is the load-bearing safety property: a coverage-restricted share must never
  be able to push a candidate over 0.5 and assert a constitutional majority that never existed (the
  1824 hazard). Keeping `ec_share_full` policy-invariant makes that structurally impossible.
- Parameterizing one builder by view reuses the exact shape `join.py` already proves, and guarantees
  the public surface is computed by the same code as the analysis surface — no divergence.
- Single-sourcing the national roll-up now (not "reconcile later") prevents two hand-written copies of
  a subtle dedup (per-state max-then-sum, `min_count=1`) from drifting once #102 puts both under one
  public artifact.

**Intent (Fred — drives the design, not over-formalized per D011):** the hybrid exists to circumvent
the House choosing the President when no candidate wins an EC majority — "let the people decide when
the EC is very close." So "no EC majority" is a first-class expected outcome (`ec_determinative =
false`), not an error; and a hybrid is computed for **every** in-scope year (D038), never withheld on
partial PV coverage.

---

## D038: The hybrid is computed for every in-scope year and flagged with `pv_coverage`; denominator policy (b) is settled

**Date:** 2026-07-28

**Context:** The hybrid needs a *national* PV total, which is only strictly apples-to-apples where
every state that cast electoral votes also held a popular vote. For partial-PV years — those with a
`legislature_chosen` state that cast EC votes but never held a popular vote (D024) — the EC and PV
shares are computed over different-sized electorates. Three treatments were on the table: **(a)**
withhold the hybrid for such years; **(b)** compute with the mismatched denominators and flag via
`pv_coverage`; **(c)** restrict both shares to the popular-vote-holding states so the denominators
match.

**Decision:** Rule (a) is **rejected** — it would suppress the House-contingent, no-EC-majority
elections (including 1824) the hybrid exists to speak to. E7 **always computes a hybrid** and flags
coverage via `pv_coverage` (D024 §8, the EV-weighted share of the year's electoral votes cast by
`popular_vote` states). The denominator policy is **settled: (b)** (Fred, 2026-07-28) — compute with
the mismatched denominators (EC over all EC-casting states, PV over the PV states), flagged by
`pv_coverage < 1.0`. Rule (c) is **not shipped**; the `apply_coverage_policy` seam keeps it a
swappable one-line policy at zero cost, but (b) is the only configured rule and applies globally to
every affected year. An explanatory note (E7-S6) ships with any surface exposing a partial-coverage
hybrid.

**Rationale:**
- Fred's words: *"I vote for b. Simpler and sticks more closely to the historical record for ec, so
  as not to cause as much confusion, just needs an explanatory footnote or similar."* (b) reports the
  national picture as it existed with an honest coverage caveat, rather than silently re-scoping the
  EC electorate.
- Keeping the policy factored (even though only (b) ships) costs nothing and leaves (c) available if
  the future explorer wants a same-electorate view.
- **1824 rationale (verified):** Jackson led both the EC (99 of 261 cast, 131 needed) and the PV
  (~151k vs ~113k) with a majority of neither; the House elected Adams (`took_office = Adams`,
  `president_electoral_rank == 1 = Jackson`). The hybrid returns **Jackson** under both (b) and (c),
  so the pick moves the **margin, not the winner** — a calibration question, not a correctness one
  (1824 → Jackson is pinned as a test fixture). `ec_determinative` and `pv_coverage` are **orthogonal**
  (both populated for 1824).

Extends D005/D024.

---

## D039: The #102 read seam is `hybrid_redistributable` (+ `hybrid_summary`), materialized by `usvote/snapshot.py`

**Date:** 2026-07-28

**Context:** #102 (E8-S8) adds the hybrid/flip/margin fields to the public API but was filed before E7
was scoped; its implementation note said only "reads E7's output wherever E7 materializes it;
coordinate the read seam." E7 must decide that seam.

**Decision:** E7 exposes **`hybrid_redistributable`** (+ its per-election `hybrid_summary`) — resolved
warehouse views alongside the join views, rebuilt by `warehouse.rebuild_views`. #102 materializes them
into the SQLite snapshot in `usvote/snapshot.py` (the same module that already materializes
`ec_pv_redistributable`), minting the public `candidate_slug` and dropping `candidate_id` there (D006),
exactly as it does for `ec_pv` today. The redistributable hybrid views wrap the **independently
defined** redistributable join view (`WHERE redistributable`, D017), so **no UCSB-derived number can
structurally reach the public surface** (extends D030). Because that surface is MIT-only 1976–2024
where every state holds a popular vote, `apply_coverage_policy` **degrades to identity** on it
(`ec_share_hybrid == ec_share_full`, `pv_coverage == 1.0`), so `hybrid_redistributable` is **provably
policy-invariant** and #102 is unblocked regardless of the D038 machinery. **#102 must bump
`SNAPSHOT_SCHEMA_VERSION`** (`snapshot_schema.py:21`): the content hash covers only the `ec_pv` data
rows, so a roll-up/shape change is invisible to it and the version must be moved manually or consumers
will not see the new shape. Per the resolved OQ4, #102's `build_national_rollup` becomes a **reader**
of E7's single-sourced national derivation (D037), not a parallel one.

**Rationale:**
- Reusing the existing snapshot materialization path keeps E7's views warehouse-internal (carrying the
  internal `candidate_id`, no public-id leak) and makes the hybrid fields a straight materialization
  onto the existing `national_rollup` table (or a sibling `hybrid_rollup` — architect's call).
- The structural redistributable-only property (independent view definition) is stronger than a data
  filter and matches D030's day-one guarantee.
- The schema-version bump is easy to miss precisely because the hash does not cover roll-up shape;
  recording it here makes the obligation explicit.

The E9 mart may later slot in behind the same seam but is not a dependency.

---

## D040: #70 is folded into E7 and re-labeled in place (`epic:hybrid`), not re-filed

**Date:** 2026-07-28

**Context:** #70 ("Quantify MIT vs. UCSB PV discrepancies across the 1976–2024 overlap") was filed
2026-07-13 under `epic:pv-join` (#63), before the E6 join views existed; its body refers to them
speculatively. It is E7's empirical trust prerequisite (the benign-seam evidence behind cross-1976
margin/flip trends). It is referenced by number in D017's action items and calibrates D017 layer 3.

**Decision:** **Re-label #70 in place** — retitle unchanged, swap `epic:pv-join` → `epic:hybrid`, keep
`research` + `priority:medium`, keep the issue number and its existing AC, repoint the body's
`**Epic:** #63` line to the E7 epic (#120). **Do not close-and-refile.** Amend its AC to reflect that
E6 has shipped: compute the MIT−UCSB delta directly off the shipped `dwh.pv_votes` union / `pv_ucsb` /
`pv_redistributable` views (not a throwaway re-extract), and flow the finding into **D017 layer 3 +
E7's margin/flip benign-seam caveat** (not "the E6 join design", now shipped). It is distinct from
E7-S6 (the coverage/denominator explanatory artifact) and must not be merged with it.

**Rationale:** A relabel preserves the reference graph (D017's action items, the issue's history) at
zero cost; a fresh number would orphan those references. The AC amendments only update stale
forward-references now that the relations #70 measures have shipped — the **finding** remains the
deliverable.

---

## D041: The EC is determinative only on a strict majority of the appointed electoral allotment (`ec_share_full > 0.5`)

**Date:** 2026-07-28

**Context:** The hybrid's flip logic needs a precise rule for when the EC "determines" an election.
Fred's principle: use the most historically accurate vote that actually elected the president, "not a
simplification on our part," and the EC is determinative only if the leader has "50% or more" of the
electoral votes. A prior architect pass raised a "cast vs appointed" concern — claiming the formula's
denominator was cast-basis while the 12th Amendment's bar is "appointed" — and proposed treating the
divergence as a documented simplification.

**Decision:** Implement a **strict majority: `ec_determinative = true` iff `ec_share_full(ec_winner) >
0.5`**; otherwise `false` (no EC majority — the hybrid's motivating case). An exact 50/50 tie is
treated as the **same branch** as no-majority (not a tie to break), because "≥ 50%" names two winners
at the boundary and is ill-defined there. `ec_determinative` reads **only** `ec_share_full`
(policy-invariant, D037). **The majority basis is the appointed allotment — settled and
constitutionally correct.** `ec_denominator` = Σ `total_electoral_votes` (each state counted once) is
the **appointed** electoral total, exactly the 12th Amendment's "majority of the whole number of
Electors **appointed**," while the numerator (`president_electoral_votes`) is the electoral votes
actually **cast**. The earlier "cast vs appointed" concern was a **misreading** of
`total_electoral_votes` and is resolved, not carried as open.

**Rationale:**
- Verified in code: `total_electoral_votes` is each state's **allotment**, not votes cast.
  `docs/corrections.md` is explicit for the 2000 DC abstention — the allotment
  (`total_electoral_votes=3`) is preserved, with the 1-vote gap tracked separately in
  `ELECTORAL_VOTE_SHORTFALLS` / `_expected_shortfall`, and `assert_row_votes_sum_to_total` checking
  candidate votes == total − shortfall. So `ec_denominator` is an **appointed** denominator and the
  numerator is **cast** — precisely the 12th Amendment's formulation. 2000 is Bush **271 of 538
  appointed**, clearing an appointed-basis threshold of **270** — not the **269** a cast-basis
  threshold (537 ÷ 2, rounded up) would have set. The contrast is between the two *thresholds*, not
  between two tallies of Bush's votes: Bush cast 271 either way (271 + Gore's 266 = 537 cast, of 538
  appointed). Matches the historical record Fred asked for.
- **Derived requirement:** because shortfalls are real, Σ `president_electoral_votes` can be **less**
  than `ec_denominator`, so candidate EC shares in such a year sum to slightly **under** 1.0. That is
  correct, not a bug — validation must assert shares sum to **≤ 1.0**, never == 1.0, with 2000 (537
  cast of 538 appointed) pinned as the fixture.
- A strict `> 0.5` resolves the boundary cleanly; treating an exact tie as "the EC did not settle it"
  is exactly the condition the hybrid exists to address.

`ec_determinative` is a first-class, populated output; contingent / no-majority elections (1824) are
**flagged and computed**, with the who-takes-office legal treatment left to the D010/D011 future
workstream.

---

## D042: D039's "policy-invariant redistributable surface" premise is false; #102 is unblocked by configuration, not by invariance

**Date:** 2026-07-31

**Context:** D039 (2026-07-28) settled #102's read seam and justified it, in part, with this claim:

> Because that surface is MIT-only 1976–2024 where every state holds a popular vote,
> `apply_coverage_policy` **degrades to identity** on it (`ec_share_hybrid == ec_share_full`,
> `pv_coverage == 1.0`), so `hybrid_redistributable` is **provably policy-invariant** and #102 is
> unblocked regardless of the D038 machinery.

#122 (E7-S3) built the (c) branch that premise was about, and found it does not hold. Raised by the
`/code-review` gate on PR #128: the correction had landed only in a module docstring and a test
docstring, so a reader planning #102/#124 off the decision record would still get the falsified claim.

**Decision:** The **conclusion stands — #102 is unblocked — but the mechanism is different**, and the
D039 sentence above is superseded by this entry (the log is append-only; D039 is not edited).

1. **The premise is false in two independent ways.** (i) `dwh.pv_state_status` carries **no MIT rows
   at all** — only UCSB calls `load_pv_status` — so `build_hybrid_from_db`, which correctly scopes the
   roster read to the sources present in the chosen view (#126), scopes `ec_pv_redistributable` to
   `{"MIT"}` and matches nothing. `pv_coverage` is therefore **NULL for every year** on that surface,
   1976–2024 included, not `1.0`. That gap is now **#127**. (ii) Even setting the roster aside, "the
   two policies agree" would not follow from an empty restricted set: (b) keeps the full EC share
   while (c) restricts to nothing and returns NULL, so today the two policies **diverge** on the
   public surface rather than coincide.
2. **What actually unblocks #102** is that **(b) is the only configured rule**. `policy` defaults to
   (b) everywhere, and no production call site passes one — enforced by an AST-matching test
   (`test_nothing_configures_a_policy_other_than_b`) that flags a `COVERAGE_POLICY_*` reference, an
   aliased import of one, or a `policy=` keyword on any of the three functions that take one. The
   guarantee is *configuration*, checkable and enforced, rather than a *numerical identity* that
   happened not to be true.
3. **The invariance claim is still true where it was really about the policy function**: (b) and (c)
   coincide **exactly on any full-coverage year**, on any surface. That is surface-independent and is
   pinned by `test_a_full_coverage_year_makes_the_two_policies_identical`. Once #127 lands, 1976+ on
   the redistributable surface becomes fully covered and D039's original sentence becomes true for
   the reason it stated — at which point it is a fact about the data, not a structural guarantee.
4. **Consequence for #124:** materialize `hybrid_redistributable` from the default policy and do not
   thread a policy argument into `warehouse.py`. **#127 blocks #124's public surface** — without it
   the materialized `pv_coverage` column ships all-NULL.

**Rationale:**
- A decision record whose stated justification is known-false is worse than one that is silent: the
  next reader plans against it. Recording the correction as its own entry keeps the append-only
  guarantee (C1) while making the superseding relationship explicit at both ends.
- Preferring an enforced configuration invariant over a numerical coincidence is the more durable
  guarantee anyway — it survives #127 changing the data underneath it, and it fails loud in CI.
- The general lesson is the one #121's `took_office` fixture and this story's fabricated `source="mit"`
  roster row both taught: a claim about live warehouse shape needs checking **against the warehouse**,
  not against a fixture that models what we assumed it contains.

---

## D043: 1868/1872 counting anomalies are a per-`(year, state, candidate)` `count_status` on `dwh.votes`, not a choice between totals rows

**Date:** 2026-08-06

**Context:** #57 (ingest the gated Reconstruction years) named its own blocker as a modeling
question: *"decide how the model represents the contested/uncounted Georgia votes and the dual
'excluding/including' totals — likely a small modeling decision (which total is authoritative for
the votes fact)."* Drafting blog post 3 forced it, because the post cannot describe how the record
handles 1868 without the record having decided.

The source shapes, from the committed fixtures:

- **1868** (`www_archives_gov_electoral_college_1868.html`) ends with **two totals rows** —
  `Totals (excluding Georgia's votes) 285` and `Totals (including Georgia's votes) 294` — and marks
  neither authoritative. The note: *"The electoral votes of Georgia were contested and the Senate and
  the House of Representatives could not agree whether to accept – and count – them or not."*
  Georgia's 9 appear parenthesized, `(9)`, in Seymour's column. Mississippi, Texas, and Virginia
  carry a dash in the allotment column itself — not readmitted, no electors appointed.
- **1872** (`..._1872.html`) totals **352**, with Grant 286 + Others 63 = **349** counted for
  president. Note 1: Greeley's 3 votes *"were not counted"* by House resolution. Note 3: *"Arkansas
  and Louisiana were unable to certify their election results and did not submit any electoral votes
  to be counted"* — 6 and 8 respectively, so 352 + 14 = the 366 electors the states were entitled to.

**Decision:** Model the *count* as a status carried by the vote rows. Do **not** resolve 1868 by
picking a totals row.

1. **The appointed denominator is never an editorial choice.** The 12th Amendment's denominator is
   "the whole number of Electors **appointed**" (D041/D037/A). 1868 Georgia's nine electors *were*
   appointed — undisputed; the open question was only whether their **votes counted**. So 1868's
   `ec_denominator` is **294**, and that follows from the existing rule rather than from taking a
   side in the congressional dispute. The 285-vs-294 question is not a denominator question at all.
2. **1872's denominator is 366, not the Archives' printed 352.** Arkansas and Louisiana appointed
   electors; their returns were never accepted into the count. That is materially different from
   1868's Mississippi/Texas/Virginia, which appointed **none** (no readmitted government to do it)
   and therefore genuinely contribute 0. Keeping those two situations distinct requires AR/LA in the
   appointed total, flagged at the count. This **diverges from the Archives' own totals row** and so
   ships as a documented correction (constant + test + `docs/corrections.md` row), like every other
   spine anomaly.
3. **`count_status` is a three-value enum on `dwh.votes`, plus a free-text reason** in the source's
   own words: `counted` (default) / `not_counted` (settled — Congress decided *no*) / `disputed`
   (unresolved — Congress decided *nothing*). This mirrors `pv_status` + `note` and its
   CHECK-built-from-a-value-tuple pattern (`usvote/pv/status.py`, D024 §4) so the enum has one
   definition. Assignments: 1868 Georgia → `disputed`; 1872 Georgia's 3 Greeley votes,
   1872 Arkansas, 1872 Louisiana → `not_counted`.
4. **The grain is `(year, state, candidate)` — a column on the fact, not a sibling roster.** 1872
   Georgia is the proof: of its 11 votes, Greeley's 3 were rejected while B. Gratz Brown's 6 and
   Jenkins's 2 were counted. Status varies *within* a state, so the `pv_state_status` shape (a
   `(year, state)` roster) cannot express it. Because `dwh.votes` is already dense and rectangular
   (`assert_rectangular_state_grain`), "complete rather than exceptions-only" (D024 §3) comes free —
   every row carries a status and there is no second table to keep in sync.
5. **`disputed` is not the `unknown` bucket D024 §4 forbids.** `unknown` means *we do not know what
   happened*; `disputed` means *we know exactly what happened — the Senate and House deadlocked and
   never resolved it*. That is a recorded fact about the world, not a gap in our knowledge, and every
   such row carries the Archives' sentence saying so. The no-`unknown` prohibition stands unamended.
6. **Two mechanisms stay separate because they encode two different failures.**
   `ELECTORAL_VOTE_SHORTFALLS` means *votes never cast* (appointed > cast: 1832 Maryland's two
   electors in ill health, 2000 DC's protest abstention). `count_status` means *cast, then not
   counted* (cast > counted: 1868, 1872). Consequently `assert_row_votes_sum_to_total` is
   **unchanged** and passes for 1872 Georgia — 6 + 2 + 3 = 11 = the allotment — because rejected
   votes remain *rows*, merely flagged. No Reconstruction entries leak into the shortfall constant.
7. **Nothing downstream flips.** Grant is 214/294 = 0.728 in 1868 and 286/366 = 0.781 in 1872, so
   `ec_determinative` is `true` under every reading of either year; no outcome depends on this
   choice. Both years are pre-1976, so the D028 snapshot and the public API are unaffected.
   Surfacing `count_status` through `EC_PV_COLUMNS`/the snapshot is **deferred** until a public
   surface actually covers these years.

**Rationale:**
- The series' thesis (post 2, D024) is that a record must hold *why* a number is absent, and that the
  failure mode is a structure forced to answer a question its source left open. 1868 is that case in
  its purest form: the official record prints two totals and declines to choose. A schema that
  collapses them answers Congress's question by accident, in whichever direction the parser leaned.
- Splitting "appointed" from "counted" costs nothing here and is the same two-numbers-kept-apart move
  that already earned its keep in D041 (appointed denominator vs cast numerator). 1872 simply shows
  the ladder has a third rung: **366 appointed → 352 submitted → 349 counted**.
- A boolean `contested` was the first proposal and is not enough: it cannot distinguish *Congress
  decided no* (1872) from *Congress never decided* (1868), which is precisely the distinction the
  years exist to teach.
- Choosing 366 over the Archives' 352 accepts a documented divergence from the source in exchange for
  keeping "appointed no electors" and "appointed electors whose votes were not counted" as separate
  facts. Collapsing them would reintroduce the missing-vs-zero conflation at the state level.

**Action required:**
- #57: implement `count_status` + reason, the 366/294 denominators, and the four flagged rows; add
  the 1872 AR/LA denominator divergence to `docs/corrections.md`; drop 1868/1872 from
  `UNSUPPORTED_EC_YEARS` and update the gate test. Downstream UCSB roster effects are already
  enumerated in #57 and unchanged by this entry.
- Blog post 3 states this handling as shipped-by-decision; if #57 lands differently, the post is the
  thing that has to change.

## D044: 1868's two totals rows are resolved by the source's own allotment sum, not a curated literal

**Date:** 2026-08-09

**Context:** #143 (the first of #57's two per-year slices) ingests 1868 and carries the shared
`count_status` DDL. D043 settled the *modeling* — a three-value status on the fact — but left three
implementation questions the code had to answer, and one of them is a place where a parser can
silently take a side in a constitutional dispute.

The 1868 Archives page (`tests/fixtures/www_archives_gov_electoral_college_1868.html`) ends with
**two** totals rows — `Totals (excluding Georgia's votes) 285 / 214 / 71` and `Totals (including
Georgia's votes) 294 / 214 / 80` — and marks neither authoritative. Everything downstream of the
parser treats `state == "Totals"` as one row per year (`_add_electoral_rank` ranks off it,
`assert_totals_equal_state_sum` compares against it, `assert_state_count_by_year` counts it), so
both cannot survive. The parser's exact `{"Total", "Totals"}` match recognised *neither*, which
would have loaded the year with no totals row at all.

**Decision:**

1. **The surviving totals row is the one whose `total_electoral_votes` equals the sum of that
   page's own per-state allotments** — a rule *derived from the source*, not a curated per-year
   literal, and not an editorial choice between two readings. Verified against the fixture's own
   tokens: its 37 state rows sum to **294 / Grant 214 / Seymour 80**, matching the *including*
   row exactly, while the *excluding* row disagrees with the very state rows printed above it and
   would fail `assert_totals_equal_state_sum`. This re-derives D043 §1's 294 from the data rather
   than inheriting it from D043's prose, which is what AC 4 of #143 demanded (D043 §6 had already
   been found wrong once). The rule compares **allotments** on both sides, never the per-candidate
   vote columns: 1832's totals row carries 288 *appointed* while only 286 were *cast*, and the
   allotment comparison is what keeps `ELECTORAL_VOTE_SHORTFALLS` years unaffected. Zero or several
   reconciling rows **raise** — the parser never guesses, because guessing wrong answers Congress's
   question by accident. Totals-label matching becomes a **prefix** match to recognise qualified
   labels; no US state name begins with "Total".
2. **The enum lives in a new stdlib-only top-level module, `usvote/count_status.py`.** It has two
   callers that must not depend on each other — `usvote/transform.py` *assigns* the values,
   `usvote/load.py` builds the `CHECK` from them. Putting the tuple in `transform` would point the
   DDL builder at the pandas transform module; putting it in `load` would drag psycopg2 into the
   transform import chain. This is the shape `usvote/years.py` and `usvote/pv/status.py` already
   have, so `count_status.py` joins the `years.py` family of pure EC-domain top-level modules
   (D027's taxonomy) rather than being an ad-hoc placement.
3. **The columns are `count_status` + `count_status_reason`**, not `pv_status`'s `note` spelling.
   A deliberate, minor divergence from D043 §3's phrasing-by-analogy: `note` on a wide fact table
   does not say what it is a note *about*. Unlike `pv_state_status.note` (verbatim UCSB prose,
   `redistributable=false`), this column holds the **Archives' own sentence** — a US Government
   work, so it carries no redistribution restriction. `count_status` is `NOT NULL` with **no
   `DEFAULT`**: the transform supplies a value on every row, so the column is complete rather than
   exceptions-only (D024 §3 applied to the fact) and a null can never stand in for "presumably
   fine". A biconditional assert (`assert_count_status_reasons`) requires a reason on every flagged
   row and forbids one on a `counted` row.
4. **Aggregate (`is_total`) rows are never flagged.** 1868 Seymour's national 80 includes Georgia's
   disputed 9, and one enum value cannot say "80, of which 9 disputed". D043 §4 fixes the grain at
   `(year, state, candidate)`; the state rows carry the truth and the aggregate's disputed-ness is
   derivable from them. Asserted by a test rather than left emergent, because propagating `disputed`
   upward is a defensible-looking change that would quietly over-claim.
5. **No migration story.** The `dwh` schema is only ever created fresh (`create_table` /
   `--replace`), so adding two columns needs a rebuild, not an `ALTER`.
6. **The `(N)` relaxation carries a reciprocal guard.** Reading a parenthesized cell as a
   number is a *global* loosening — before this, every `(N)` raised `ParseError` — so the
   parser now **reports** each parenthesized cell (`ParsedTable2.contested_cells`) and
   `transform.assert_contested_cells_catalogued` requires every one to have a
   `COUNT_STATUS_OVERRIDES` entry. Without it, a parenthesized cell in a year with no
   catalog entry would load as an ordinary `counted` vote with every sum validator
   passing, and 41 of the 50 in-scope years have no committed fixture, so a re-scrape or
   an Archives edit is a live path. `_add_count_status`'s own guard runs catalog → data;
   this is data → catalog, and it is modelled on `apply_other_candidates`, which raises
   the same way for an unregistered "Other(s)" column. (Found by the `/code-review` gate,
   not by the plan.)

**Rationale:**
- D043's own argument is that a structure must not answer a question its source left open. A parser
  that picked a totals row by position — or by a literal someone typed once — would do exactly that,
  in whichever direction it leaned. Deriving the choice from the allotment sum means the source
  answers it, and means the rule degrades to a **loud error** rather than to a stale constant when a
  future page does something new.
- The allotment basis is not a new principle: it is D041's "whole number of Electors **appointed**",
  already load-bearing for `ec_denominator`. 1868's nine Georgia electors were appointed beyond
  dispute — only whether their votes *counted* was open — so 294 follows from the existing rule and
  the 285-vs-294 question was never a denominator question at all (D043 §1).
- Catalogue-early paid off. The four 1868 `PV_ABSENCE_CATALOG` rows were curated in #140 while the
  year was still gated, with public-domain citations; admitting them here required **no new
  research**, only lifting `UNSUPPORTED_EC_YEARS` and bumping `CURATED_YEAR_COUNT` 49 → 50. The
  import-time scope pin is what forced that to be a deliberate act instead of an accident.
- Nothing under `usvote/ucsb/` changed. Its scope derives from `ec_ingest_years()` (D024 §6), so
  lifting the gate moved its consumed `UCSB_NONPARTICIPATING_STATES` from 11 to 14 and its roster's
  `legislature_chosen` from 17 to 18 with no edit in that package — the self-healing property the
  derivation was built for, now observed rather than promised.

**Action required:**
- **#144 (1872)** rebases on this. It ships the second and third `count_status` values in anger
  (`not_counted` for Georgia's 3 Greeley votes and for Arkansas/Louisiana), the 366 denominator, and
  the correction to D043 §6's worked arithmetic — which is wrong against the 1872 fixture: the
  rejected Greeley votes are **not rows in the table at all** (Greeley's column reads `-`, the
  president-side Others cell reads 8), so they must be *synthesized* before they can be flagged.
  That correction is #144's to append, not this entry's.
- **#139** should note a coupling the plan initially mis-stated: the API snapshot is unaffected by
  1868 because `snapshot._covered_years` is the MIT window, **not** because the year is excluded —
  1868 rows *do* enter `ec_pv_redistributable`. #139 is the story that widens the covered window, so
  it is the one that must decide what `count_status` does on a public surface (D043 §7 defers the
  surfacing until then, and that deferral now expires in #139).

## D045: 1872's 17 rejected electoral votes are synthesized from prose; the denominator is 366, not the Archives' 352

**Date:** 2026-08-10
**Issue:** #144 (split from #57) · **Corrects:** D043 §6 · **Builds on:** D043, D044

**Context:**

D043 §6 asserted that `assert_row_votes_sum_to_total` was "**unchanged** and passes for 1872 Georgia
— 6 + 2 + 3 = 11 = the allotment — because rejected votes remain *rows*, merely flagged."

Verified against `tests/fixtures/www_archives_gov_electoral_college_1872.html` at plan time, **that
is wrong**. Georgia's row reads `['Georgia 4', '11', '-', '-', '8', '-', '5', '6']`: Greeley's
president column is `-` and the president-side Others cell is 8 (Brown 6 + Jenkins 2). The three
rejected Greeley votes **are not in the table at all** — they exist only in Table 2's note 4. The
president side therefore sums to 8 against an allotment of 11, and D043 §6's arithmetic holds only
*after* a synthesis step D043 did not anticipate.

Re-verifying the rest of D043's prose, as that issue instructed, found the same pattern twice more:

- **The 366 denominator is right, and its basis was under-stated.** The Archives totals row prints
  352, which is the sum of the *submitting* states' allotments. Arkansas (6) and Louisiana (8)
  appointed their full complement and print `-` only because their returns were refused.
- **D043 §3's "Arkansas and Louisiana get `not_counted`" is right for a reason D043 did not give.**
  The Archives note says only that the two states "did not submit any electoral votes to be
  counted", which reads as an allotment-only gap with no recipient — and modelling it that way would
  have kept Grant's national row at the familiar 286. The primary record says otherwise: both
  states' electors met and cast **for Grant**, and the *returns* were rejected.

**Decision:**

1. **Three new correction mechanisms in `usvote/transform.py`**, each provenance-carrying, applied
   inside `_votes_matrix` before `assert_row_votes_sum_to_total` so the source's own arithmetic is
   what checks them:
   - `UNPRINTED_ELECTORAL_VOTES` — votes the source documents in prose but omits from its table.
     Keyed `(year, state, canonical candidate name)`, the **`COUNT_STATUS_OVERRIDES` grain (D043
     §4)**, deliberately *not* the parsed `col_ind`: the Others pass renumbers those columns, so a
     positional key would drift while its twin count_status entry — addressing the same cell — stayed
     correct, and the two would disagree with the row still reading as ordinary. The column index is
     resolved from the name at application time, so a name matching no column raises.
   - `APPOINTED_ELECTORS_NOT_IN_TABLE` — allotments the source prints as `-` for a state that did
     appoint electors. It moves the **denominator**, not a candidate's votes, which is why it is a
     separate constant.
   - `OTHER_CANDIDATES_1872` / `OTHER_VOTES_1872` — no new mechanism, the existing aggregate-column
     split, but the widest instance in the corpus: four recipients (Brown 18, Hendricks 42, Jenkins
     2, Davis 1).
2. **The totals row is recomputed from its state rows** for every column and for the allotment, so
   366 is derived rather than entered — D044 §2's discipline, extended to the denominator.
3. **`UNSUPPORTED_EC_YEARS` becomes empty.** The EC spine is complete, 1824–2024. The constant is
   **retained, not deleted**: it is the single gate on both sources (D024 §6) and the documented seam
   for the deferred pre-12th-Amendment era (D010).
4. **1872 is reviewed for popular-vote absences and has none**, which is a finding rather than a
   silence. `CURATED_YEAR_COUNT` 50 → 51. **What corroborates that is the UCSB cross-source control
   test, not the EC spine** (corrected at code review, before merge): `assert_catalog_matches_spine`
   only forces an entry for a state that appointed *no* electors, and restoring AR/LA's allotments
   leaves 1872 with no such state — so that check inspects nothing there and passes trivially. It is
   blind to `legislature_chosen` absences in any case, since those states appointed electors (18 of
   the catalog's 32 entries). The real check skips in CI (D022) and is a local merge precondition.

**Sources (all public domain; the citation discipline `usvote/pv/absences.py` established):**
- **CRS Report RL30769**, *Electoral Vote Counts in Congress: Survey of Certain Congressional
  Practices* (Maskell, Halstead, Welborn & Burkes, 2000-12-13) — a US Government work. Records the
  announced **whole number of 366** electors with **349 counted**, and 17 rejected: Georgia 3
  (Greeley, who had died), Arkansas 6 (the certified persons "were not the persons elected as
  electors"; returns "not certified according to law"), Louisiana 8 (no lawful canvass).
- **H. Misc. Doc. No. 13, 44th Cong., 2d Sess. (1877)**, *Counting Electoral Votes: Proceedings and
  Debates of Congress Relating to Counting the Electoral Votes for President and Vice-President of
  the United States*, printed by order of the House — for the AR/LA **recipient**, which the
  Archives page does not name: "the votes of Arkansas, 6, and Louisiana, 8, cast for U. S. Grant".
- **Apportionment Act of 1872**, 17 Stat. 28 — the independent structural check: 37 states × 2
  senators + 292 representatives = 366; Arkansas 4 + 2 = 6; Louisiana 6 + 2 = 8.
- The per-state Others split and Georgia's recipients come from the **Archives page's own** Table 2
  notes 1 and 4–10; every figure reproduces the parsed Others column per state and each recipient's
  national total. No external source is needed for that half.

**Rationale:**
- The issue instructed that D043's worked numbers be treated as claims to re-verify rather than
  settled inputs, because one of them had already proved wrong. Doing so found a second loose clause
  (§3's AR/LA reasoning) that a narrower reading would have missed — and reversed a design that was
  about to record a defensible-but-false model of what happened in those two states.
- Keeping `APPOINTED_ELECTORS_NOT_IN_TABLE` separate from `UNPRINTED_ELECTORAL_VOTES` despite their
  numbers coinciding (6 and 8 in both) avoids baking a **coincidence** into the schema: the identity
  holds only because every appointed elector in those states cast for one candidate and all were
  rejected. It is also cross-checked for free — `assert_row_votes_sum_to_total` requires each row's
  cast votes to equal its allotment, so an appointed 6 against an unprinted 5 raises.
- `ELECTORAL_VOTE_SHORTFALLS` is **untouched**. Its meaning is votes *never cast*; 1872's were cast
  and then refused. The two mechanisms stay disjoint exactly as `usvote/count_status.py` claims, and
  1872 acquires no shortfall entry.
- 1868 and 1872 must not be conflated even though both print `-` allotments. 1868's
  Mississippi/Texas/Virginia had no readmitted government and appointed nobody — genuine zeros
  (D043 §2). A test asserts the two behave differently.

**Action required:**
- Nothing outstanding for this entry. The `count_status` **public surfacing** decision is D046/D047.

## D046: `dwh.votes` carries both a cast and a counted electoral-vote measure, and counted decides who won

**Date:** 2026-08-10
**Issue:** #144 · **Builds on:** D041, D043, D044, D045 · **Decided by:** Fred, at the #144 plan gate

**Context:**

Synthesizing 1872's 17 rejected votes (D045) forced a question #143 had left implicit. With the
rejected votes present as rows, Grant's national `president_electoral_votes` reads **300**, not the
familiar 286 — because the fact records what electors *cast*, and `assert_totals_equal_state_sum`
requires the totals row to equal the sum of the state rows.

Checking rather than assuming showed the warehouse had **no counted-only total anywhere**:
`national_electoral_votes` is an unfiltered window `SUM` (`join.py`), and `count_status` is absent
from `EC_PV_COLUMNS`, so the join views, `usvote/hybrid.py` and the API could not express "counted
only" at all. #143 had therefore already shipped 1868 with Seymour at **80**, nine of which were
never counted, and nothing downstream could say so.

1872 makes three different totals all true at once, and one measure cannot carry them:

| | appointed | cast | counted |
|---|---|---|---|
| **1872 national** | 366 | 366 | 349 |
| Grant | — | 300 | 286 |
| Greeley | — | 3 | 0 |
| **1868 national** | 294 | 294 | 285 |
| Seymour | — | 80 | **71** |

**Decision:**

1. **`dwh.votes` carries both measures.** `president_electoral_votes` is unchanged and means **cast**;
   `president_electoral_votes_counted` is new and means **entered the final national count**. The
   column name lives in the stdlib-only `usvote/count_status.py` for the same reason the enum does
   (D044): `transform` derives it, `load` builds its DDL, `join` sums it, and none may depend on the
   others.
2. **The counted rule is strict:** `disputed` is excluded alongside `not_counted`, because Georgia's
   nine votes in 1868 were never counted by anyone — the two chambers deadlocked. A pleasing
   consequence: **both** of the Archives' printed 1868 totals rows are now reproducible, 294 as cast
   and 285 as counted, where D044 could only select one.
3. **The measure is derived by two rules, and that is deliberate.** State rows take the row rule
   (cast when `counted`, else 0). `is_total` rows take the **sum over their year's state rows** — the
   row rule is *wrong* for them, since aggregates are never flagged (D044) and would hand back the
   cast value. This is exactly the fact D044 recorded that one enum value could not express.
4. **Counted decides who won.** `president_electoral_rank` (and the `took_office` derived from it)
   and `hybrid.ec_share_full` / `ec_determinative` all move to the counted basis. The denominator
   stays the **appointed** allotment (D041), so `ec_share_full` is now literally the 12th Amendment's
   test — votes *counted* over electors *appointed*. 1872 reads Grant at 286/366 = 0.781 against the
   184-of-366 threshold Congress actually announced.
5. **Three measures, one ladder: appointed ≥ cast ≥ counted**, with a documented gap at each step —
   `ELECTORAL_VOTE_SHORTFALLS` opens the first (appointed, never cast) and `count_status` the second
   (cast, never counted).

**Rationale:**
- The alternative — keep the fact at what Congress counted and correct only the denominator — would
  have kept Grant at the familiar 286 but left the 17 cast votes and their recipients out of the
  warehouse entirely, needing a new 17-vote row-sum exemption and leaving `not_counted` with **zero
  instances** in the corpus. That is the mechanism D043 built, unexercised.
- Storing rather than deriving-at-the-view is what the two-rule derivation buys: on a state row the
  value is redundant, but on an `is_total` row it is the only place the counted total exists.
- **Rank and `ec_share_full` had to switch together.** `assert_ec_winner_matches_rank` compares
  `argmax(ec_share_full)` against `president_electoral_rank == 1`; had only one moved, 1872 alone
  would have fired it. The co-switch is mandatory, not incidental.
- **No outcome changes, and that is provable without running anything** (architect, #144): only 1868
  and 1872 have `counted ≠ cast`, and in both the EC winner is Grant, **whose votes were entirely
  counted** — so the winner's `ec_share_full` is identical on either basis and the argmax cannot
  reorder. What *does* change is 1868 Seymour's `ec_share_full` (80/294 = 0.272 → 71/294 = 0.241).
  His `hybrid_score` does **not** move: 1868 is pre-1976, so `pv_share` and the hybrid are NULL.
- Because `counted ≤ cast ≤ appointed`, `assert_ec_shares_le_one` is **strictly safer** under the new
  basis: a smaller numerator can only shrink a share, never manufacture a majority. D041's safety
  property is strengthened rather than threatened.
- Policy (c)'s `_restricted_ec_numerator` moved to the counted measure too. A coverage policy chooses
  which *states* count toward a share, never which *basis*; leaving it on cast would have made (b)
  and (c) disagree in 1872 for a reason unrelated to coverage. Numerically immaterial today — both
  anomaly years have full popular-vote coverage — but the inconsistency would have been invisible.

**Action required:**
- **#139** owns the public surfacing (D047).

## D047: `count_status` and the counted measure will be surfaced publicly; the API plumbing is #139's

**Date:** 2026-08-10
**Issue:** #144 · **Supersedes:** D043 §7 · **Builds on:** D028, D030, D046

**Context:**

D043 §7 deferred the question of whether `count_status` should reach a public surface "until a public
surface actually covers these years". #139 is that surface — it widens the API's covered window back
to 1824 — so the deferral has expired and #144 is where the call is recorded.

**Decision:**

1. **Yes, both `count_status` and `president_electoral_votes_counted` are surfaced publicly.** An API
   that reports Grant at 300 electoral votes in 1872 with no way to see that 14 were refused is worse
   than one that omits the year: the number looks ordinary and contradicts every reference the reader
   can check.
2. **The plumbing is #139's, not #144's.** `usvote/join.py` gains **two** columns in `EC_PV_COLUMNS`
   here — the per-row `president_electoral_votes_counted` and the national
   `national_counted_electoral_votes` — because the analysis surface needs both for D046: coverage
   policy (c) re-sums the measure over a *restricted* state set, which a national total cannot give
   it. `snapshot_schema.DATA_COLUMNS` and the API models are untouched.
   **Both are appended, never inserted**, and that is a hard rule rather than a style note:
   PostgreSQL's `CREATE OR REPLACE VIEW` can only add trailing columns, so a mid-list insert makes
   `rebuild_views` fail against every warehouse whose views already exist. #144 shipped exactly that
   bug into review — it passed all 987 offline tests, because the pandas oracle builds any order —
   and it is now pinned by a test.
3. **Leaving them out of `DATA_COLUMNS` is safe, and was verified rather than assumed.**
   `DATA_COLUMNS` is an **independent explicit tuple** that `snapshot.py` projects with
   `[list(DATA_COLUMNS)]`; the only test coupling the two runs `DATA_COLUMNS → API model`, never
   `EC_PV_COLUMNS → DATA_COLUMNS`. So an added join-view column does not propagate to the snapshot,
   the content hash, or the served payload.

**Rationale:**
- Splitting the decision from its plumbing keeps #144 to one coherent slice (ingest 1872 + model the
  two measures) while giving #139 a settled answer to build against instead of a re-litigation.
- The containment property is what makes the split honest. Had `DATA_COLUMNS` been derived from
  `EC_PV_COLUMNS`, adding a column here would have silently changed the public payload and the
  snapshot version — a D028/D030 surprise. It is not, and a test proves the direction.

**Action required:**
- **#139** threads both columns through `snapshot.py` → the API models, and decides their public
  field names. One thing it should not re-derive: `national_counted_electoral_votes` is **never
  NULL** (an int at state grain, unlike PV), so it needs none of the `_INTEGER_COLUMNS`/`_to_int64`
  NULL handling the PV columns require.
- **Blog Post 3** (`social/drafts/2026-08-05-it-takes-270-but-270-of-what.md`) describes this model in
  the present tense and cites #57 as the record. Per D043's action item it is **the post that
  changes** where it diverges from shipped behaviour — in particular it must not describe 1872's
  electoral totals without saying which basis it means.

## D048: the public surface widens to 1824, and it carries a second provenance

**Date:** 2026-08-10
**Issue:** #139 (E8-S9) · **Implements:** #134 option 2 · **Builds on:** D024, D028, D030,
D041, D046 · **Discharges:** D047's action item

**Context:**

The public API covered **13 of 51** in-scope elections. `ec_pv_redistributable` is EC-left and
already carried every EC state row from 1824 on; `snapshot.build_snapshot` filtered the rows
without popular votes away. So 38 elections — including every year the blog series' historical
posts turn on — were unreachable on the artifact those posts point readers at, and 1824 or 1872
returned a **404**: a coverage gap rendered as a nonexistence, which is the missing-vs-zero
error the series exists to describe, committed by the series' own evidence.

**Decision:**

1. **The served window is the full EC span, 1824–2024**; the redistributable popular vote keeps
   its own narrower window. `SnapshotMeta` carries **both** (`year_min`/`year_max` and
   `pv_year_min`/`pv_year_max`), so coverage is *stated* rather than inferred from a field of
   nulls. 1,734 rows / 25 candidates → **5,623 rows / 96 candidates**.
2. **Every fact row carries a `pv_status`, `NOT NULL`.** Widening without it would have shipped
   ~3,900 bare NULL popular votes, conflating "no popular vote was ever held here" with "no
   source reaches this far back" — the exact error this project describes. 1860 South Carolina
   (`legislature_chosen`) and 1860 New York (`popular_vote`) both show a null popular vote, and
   the two nulls now mean different things.
3. **The classifications are derived from the in-repo catalog, never from `dwh.pv_state_status`**
   (#134 option (C), built in #140). Membership comes from the EC spine; the 32 catalogued
   absences supply the two absence statuses; `popular_vote` is the residual. **The warehouse
   roster is not read at all**, so no UCSB-provenanced value is on the public path and D030 stays
   structural rather than becoming an authorized editorial crossing. UCSB's roster is the
   cross-source *control* that validates ours — never an input to it — and the property is
   **proved, not grepped**: `usvote.snapshot` imports cleanly in a subprocess where
   `usvote.ucsb` is unimportable.
4. **`count_status` and both counted measures are surfaced** (D047's plumbing). Without them the
   API would report Grant at 300 in 1872 with no way to see that 14 votes were refused — a
   number contradicting every reference a reader can check. `count_status_reason` is the one
   free-text column that ships, and it ships **because it is Archives prose** (a U.S. Government
   work, 17 U.S.C. § 105) where `pv_state_status.note` is UCSB's. The build pins every served
   reason to the sentences in `COUNT_STATUS_OVERRIDES` — but that is a **containment** check,
   not a provenance one, and the distinction matters: it catches a reason arriving from anywhere
   other than the curated map (a hand-edited warehouse, a migration, a future second writer),
   while the map itself is exactly where a new correction is added. So unlike `pv_status` —
   whose enum is closed in a module no correction workflow touches — the thing keeping
   non-public-domain text off this column is **review of the catalog**, where each entry carries
   its Archives URL in a comment. A first draft of this entry claimed the guard made the
   provenance structural; it does not, and the honest close is to make the citation
   machine-checkable in `usvote/transform.py` (a per-entry source field asserted to be an
   `archives.gov` URL). Recorded as a known residual rather than asserted away.
5. **`national_rollup` gains the appointed denominator.** A counted total is not checkable
   without one: 1872 is Grant **286 of 366**, and 1824 is the **261** the contingent election
   turns on. Delegated to `hybrid.ec_denominator_by_year`, because the obvious re-derivation
   multiplies each state's allotment by the candidate count.
6. **Provenance is heterogeneous.** `snapshot_meta` gains `ec_source` / `ec_license` (NARA /
   US-PD) beside the PV pair, which keep their unprefixed names for compatibility. Recorded in
   the *artifact*, not hardcoded in the serving layer, so the advertised source cannot drift from
   the one that was built. `redistributable_note` names both sources with their windows, and
   OpenAPI's single `info.license` slot now advertises the **EC** license — it covers every row,
   where CC0 covers only the popular-vote window.
7. **A scoped warehouse can no longer build a snapshot.** The roster derives over the full
   `ec_ingest_years()` span and raises if the warehouse is short a year. This **retires the
   scoped-subset promise** `SnapshotMeta`'s docstring made, deliberately and in the same change.
8. **`SNAPSHOT_SCHEMA_VERSION` 1 → 2.** The content hash covers only `ec_pv` data rows, so a
   shape or roll-up-derivation change is invisible to it; the version must move by hand.

**Rationale:**
- The widening is *one deleted filter* at the fact level. Almost all the work is the honesty
  scaffolding around it — which is the right ratio for a public artifact whose selling point is
  "check the claim yourself".
- **Catalogue-early paid off twice.** #140 curated the absences while 1868 was still gated; #144
  settled the surfacing question. This issue therefore needed no new historical research and no
  re-litigation, only plumbing.
- The rights argument is now *demonstrated* rather than asserted. Fred's own test — "could this
  value have been obtained from a different source?" — is answered by 32 cited rows that are that
  other source.
- Two guards look redundant and are not. The pre-window PV guard's unique catch is a **fabricated
  zero** (a `min_count=1` regression turning an all-null year into `0`), not laundered UCSB —
  `assert_redistributable_only` already fires on that. And its floor is a **constant**: the
  obvious "lowest year with any PV" spelling is vacuous under exactly the failure it exists to
  catch, since repointing the build at `ec_pv_preferred` slides the observed floor down with the
  bad rows.
- No outcome changes for 1976–2024. 2000 still reads Bush 271 / rank 1 / took office against
  Gore's larger popular vote — the thesis year is untouched.

**Action required:**
- **The deploy is sequenced, not done.** The widened snapshot must reach production by the D034/
  D035 path (rebuild → GCS → hash-tagged image → Cloudflare purge), and the schema bump means the
  **image and snapshot cut over together**. #139 stays open with that as its sole remaining item.
- The **local Archives corpus does not exist on this machine**, so the D034 zero-network build
  path is unavailable; run `python -m usvote corpus` before the deploy rebuild.
- **#102 / E8-S8** inherits `MIT_PV_YEAR_MIN` and the pre-window guard for `pv_share` /
  `hybrid_score`. It should also resolve `pv_coverage` to **the in-repo catalog**, which is now
  the public roster of record — `usvote.hybrid` still reads the UCSB-inclusive
  `dwh.pv_state_status`, and publishing a coverage figure derived from data D030 excludes would
  undo point 3.
- **#130 guardrail G5** ("reproducible from the public API") becomes keepable pre-1976; amend it.
- The **2028 `LATEST_ELECTION_YEAR` bump will fail the snapshot build** until the new year is
  reviewed and added to the absence catalog. That is the designed behaviour, recorded here so it
  is recognized as the feature it is rather than treated as a regression.
