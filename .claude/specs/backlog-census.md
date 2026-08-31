# US Presidential Vote Analysis — Census / Apportionment Backlog (E10)

> **Status: PARTIALLY REVIEWED (2026-08-31) — E10 IS THE ACTIVE EPIC.** **OQ5 and OQ6 are
> answered** (see [#129's review comment](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/129#issuecomment-5475654446)):
> E10 is **pulled forward as the dev loop's active epic** — #180 raised to `priority:high`,
> #181/#182/#184 to `priority:medium`, #129 itself to `priority:medium` — and the 1868/1872
> Reconstruction correction is **confirmed**, so the census work covers those two years like
> any other. **OQ1, OQ2, OQ3 and OQ4 remain open by design**: they are what S1 (#180) exists to
> answer, and settling them before the finding lands would be guessing. **S2–S5 (#181–#184) are
> therefore still not final** — their shape is visible, not settled, and S1's verdict may re-cut
> S2 and S5 in particular. Each of #181–#184 carries a banner saying so.
>
> **Decision numbering drifted:** the candidate decisions below were written as **D053–D057**
> and all five slots are now taken. They record as **D058–D062** (+5) — see the renumber note in
> [Proposed decisions](#proposed-decisions-candidates-for-fred--architect--not-yet-in-decisionsmd).
>
> **Prior status: FILED, REVIEW STILL PENDING (2026-08-25).**  This backlog sharpens **E10
> (Census / apportionment analysis)** — epic **#129** — into stories, and Fred authorized
> filing them **ahead of** the review so the epic is visible to the dev loop: **#180** (S1),
> **#181** (S2), **#182** (S3), **#183** (S4), **#184** (S5). Filing is **not** approval of
> the design — **Open questions 1, 4 and 5 are unanswered**, and OQ1 (coverage floor) and OQ4
> (the redistributable branch plan) decide the shape of S2 and S5. Each of #181–#184 carries a
> banner saying so and pointing at S1. The proposed decisions below (**D053–D057**) are
> **candidates**, not recorded — `decisions.md` is append-only and the highest number currently
> recorded is **D052** (#177's MIT year-coverage guard, which took the next free slot while this
> backlog was pre-review), so D053 is the next free slot. Decisions referenced as D0NN live in
> [`decisions.md`](decisions.md).

Each `E10-SN` section below is a GitHub issue body ready to paste **verbatim**. E10 is
**Stretch / Later** work (roadmap: not on the M1–M3 critical path — #129) filed now because
the research half is genuinely uncertain and a blog post's payoff is waiting on it.

**Package placement:** the population dimension lands as **`src/usvote/census/`** — a new
source-namespaced subpackage (D015), a sibling of `usvote/mit/` and `usvote/ucsb/`, with its
own scrape/parse/transform/load and a `pipeline.py` (`run_census_pipeline`). It **conforms to
the EC spine** (D006) — it reads the state roster and the recorded allotments *from* the
warehouse and never becomes a second source of truth for which states existed when. The
direction is `census -> spine`, never the reverse, exactly as MIT/UCSB depend on the spine.

**The whole backlog is gated on E10-S1.** #129 says it plainly and it bears repeating: the
research finding decides the source, its coverage floor, its format per era, and — the fork
that reshapes S5 and the snapshot/API stories — whether the data is **redistributable**. If
S1 finds the only full-history source is non-redistributable, S5 changes shape and the
public-surface work may vanish. S2–S5 are filed (#181–#184) but **are not final until S1 lands** — their shape is visible,
not settled, and S1's verdict may re-cut S2 in particular. Each filed issue says so at the top.

---

## Corrections to the epic as filed (#129 is three weeks stale)

#129 was filed 2026-08-02, before #143/#144 landed. Two of its statements are now wrong and
must be corrected when the stories are filed (flagged to Fred in Open question 6):

1. **`UNSUPPORTED_EC_YEARS` is now empty — 1868 and 1872 are in the loaded dataset** (#143,
   #144; CLAUDE.md). #129's out-of-scope bullet *"Population for the excluded Reconstruction
   years — 1868/1872 remain out of the loaded dataset"* is **stale**. Those years are ingested,
   so the census work **must** cover them, and the reconciliation (S4) inherits their two
   anomalies: 1872's `total_electoral_votes` is the **appointed 366** (AR/LA allotments
   restored, D046), and 1868 carries Georgia's disputed nine. The census-derived seat count
   reconciles against the **appointed** allotment (D041/D046), which is precisely the column
   those two years were built to state correctly.

2. **The EC record is complete 1824–2024** (not "1824–present, migration in progress" in the
   loose sense #129 implies). The electoral-vote numerator the per-capita series needs is fully
   in hand for every in-scope year.

Neither is a scope change Fred must approve — they are the repo catching up to itself — but
S3/S4's ACs are written against the corrected state, and Open question 6 asks Fred to confirm.

---

## Label conventions

- Epic label: **`epic:census`** — **already exists** (created when #129 was filed; color
  `C2E0C6`, description *"E10: US decennial census population by state — apportionment
  analysis"*). No `label create` step needed.
- Type labels: `enhancement`, `research`, `infrastructure`, `documentation`, `testing` (all exist).
- Priority labels: `priority:high` / `priority:medium` / `priority:low` (all exist). E10 is
  Stretch/Later, so priorities below are set **low/medium by default**; they rise to `high` only
  if Fred pulls E10 forward to unblock Post 4 (Open question 5).

---

## To be resolved at review

This backlog is **pre-review**, so — unlike the approved E7 backlog — there is no "resolved"
column yet. The epic-level questions Fred must settle before filing are collected in
**[Open questions](#open-questions)** at the bottom, each with options and a recommendation.
The load-bearing ones, in priority order:

1. **How much history does Post 4 actually need?** (the real cost lever — OQ1)
2. **The redistributable branch plan** if full-history data turns out non-redistributable (OQ4)
3. **Which population series is authoritative** for the per-capita question (OQ2)
4. **Whether E10 is pulled forward now** to unblock Post 4's payoff, or Post 4 ships without it (OQ5)

This section will be replaced with Fred's answers (the E7 backlog's "Resolved at review" shape)
once he reviews.

---

## The publishing driver, and the minimum subset for Post 4

**The driver.** Post 4 of the "Counted, Not Assumed" series — **"538 Is a Choice, Not a
Constant"** (`social/series-outline.md` §4; `CLAIM-538-is-a-choice`) — is the next pillar post.
Its **payoff instance**, `APPORT-per-capita-drift` (`social/candidates.md`), is **`method:
derived` and BLOCKED on this epic**: it needs *persons-per-electoral-vote by `(year, state)`*,
joining the recorded `total_electoral_votes` numerator (already in hand) against a decennial
state-population **denominator the project does not have**.

**The load-bearing sequencing fact.** Post 4 **can be written and published now, with no part
of E10.** The two `record` instances (`APPORT-1920-failure`, `APPORT-total-moves`) "carry the
whole argument; the `derived` instance is the payoff, not a prerequisite" (`candidates.md`, and
the deliberate ordering behind it). So **E10 does not block Post 4 from shipping** — it blocks
only the *third, strongest instance* within it.

**So what is the minimum subset?** There is **no 2-of-5 shortcut** for the payoff instance. To
publish `APPORT-per-capita-drift` as a **G5-compliant** derived claim (`social/scout.config.md`
G5 — *"state the window, state the denominator, publish the numbers, and let a reader re-run it
against the public API"*) you need the computed series (S5), which needs the population data
(S2), joined to the right census (S3), and validated (S4) — because under G5 **the numbers are
the evidence**, so uncertified numbers cannot ship. That is essentially the whole epic, in
dependency order S1 → S2 → S3 → S4 → S5.

**The real lever is coverage, not story count.** The post's finding is a *trend*; it does not
require 1790 or every state. Two reductions cut the cost dramatically and are the honest
minimum-subset answer:

- **Coverage floor.** A **modern, clean, unambiguously public-domain** window from
  `api.census.gov` (resident population, ~1900/1930–2020) carries the "two-century-ish drift"
  finding and **dodges the hardest work in the epic** — the PDF/scanned early-census parse
  (S2), the three-fifths / "Indians not taxed" apportionment-population modeling (D054), and the
  worst statehood/boundary corrections (S3, e.g. WV/VA 1863). The full 1790/1824 backfill stays
  the epic's eventual target but is **not** on Post 4's critical path.
- **Public-API exposure is optional for the post and licensing-gated anyway.** The
  analysis-surface per-capita view (S5, first half) is enough to **compute and cite** the
  numbers. Serving them on the public API — the part that lets a reader "re-run it" — is the
  ideal G5 form but is gated on S1's redistributable verdict; it can follow.

**Recommendation.** If Fred wants the payoff in Post 4, run **S1 → S2 → S3 → S4 → S5 over a
modern public-domain window first** (S2–S5 scoped to `api.census.gov`'s clean coverage), and
defer the full historical backfill to a follow-on pass. If Fred would rather Post 4 ship on its
two `record` instances and take the payoff later, E10 stays genuinely Stretch/Later and nothing
here is urgent. **This is Open question 1 + 5** — the single most consequential thing to settle
at review, because it decides whether S2–S5 are a two-week clean-CSV job or a multi-month
historical-parse epic.

---

## Epic (#129 — already filed; do not re-file)

The epic issue exists and is well-specified. **Do not rewrite its body.** When the stories are
filed, update #129 with the story checklist below and the two corrections above. The stories'
parent is #129.

**Stories checklist to add to #129:**

- [ ] #N — E10-S1: Source research + licensing finding (coverage, format-per-era, redistributable verdict) — *gates everything*
- [ ] #N — E10-S2: Ingest population into a conforming dimension (`usvote/census/`; local corpus like #89/D023)
- [ ] #N — E10-S3: Conform to the state spine + build the `election_year → governing_census_year` calendar
- [ ] #N — E10-S4: Reconcile census-derived seat counts against recorded `total_electoral_votes` (the D024-shaped two-way assert)
- [ ] #N — E10-S5: Expose persons-per-electoral-vote as a warehouse view; public exposure gated on the S1 verdict

**Dependency graph:** S1 gates all. Then S2 → S3 → S4 → S5 is the natural order (S3 needs the
loaded population from S2; S4 needs the calendar from S3; S5 reads the reconciled, calendar-joined
series). S3's `election_year → governing_census_year` mapping is the one artifact worth building
**first within S3** as an independently-testable unit, because both S4 and S5 depend on it.

---

### E10-S1: Source research + licensing finding

**Issue title:** Research state-population sources: coverage, format per era, and the redistributable verdict
**Labels:** `epic:census`, `research`, `priority:medium`

**Body:**

### Summary

Answer the question the epic opens with, **before any schema is committed**: *how far back does
publicly downloadable, redistributable state-population data actually go, and in what form?*
Produce a written recommendation in `.claude/specs/`, in the shape of
[`research-pv-source.md`](research-pv-source.md) — the E3 deliverable that settled the PV
sources. This story **gates every story below** and may re-cut their shape (S2 especially).

**This is a research spike, not code** — like #70 (E7-S1) and #13 (E3), its deliverable is a
*written finding*, so it does not fit the implement-review-merge loop the way a code story does.
Its "acceptance" is a document that answers the questions below with evidence, not a green test
suite. Budget it to run **well ahead** of S2–S5.

### Acceptance Criteria

- A written recommendation lands at `.claude/specs/research-census-source.md`, **mirroring the
  section structure of `research-pv-source.md`**: (1) Recommendation, (2) Source comparison
  head-to-head table, (3) **Licensing finding** with the verbatim license text and a per-source
  redistributable verdict, (4+) per-source characterization (coverage / grain / format / effort),
  a fallbacks scan, and a "what this unblocks" close.
- **Coverage-per-era is stated, not assumed** — for each candidate source, how far back it reaches
  and **in what machine-readability** *per era*. The specific unknown #129 names: whether the early
  censuses (pre-~1900) are structured downloads or **PDF/scanned tables**. The answer decides
  whether S2 is one clean-load story or must split into snapshot + parse + transform (see S2).
- **Both population series are addressed** (D054): whether each source publishes the
  **apportionment population** (the input to seat allocation) and the **resident population** (the
  per-capita denominator), and where they diverge historically (three-fifths clause pre-1868;
  "Indians not taxed" excluded through 1940; modern overseas-federal-personnel movements). A source
  that offers only one is a partial source and the finding must say so.
- **The candidates named in #129 are each verified, not assumed:** the **US Census Bureau**
  published apportionment tables + historical population volumes (the strongly-preferred
  public-domain option); **`api.census.gov`** (expected to cover only recent decennials — *verify
  the actual floor*); and **IPUMS NHGIS** (the known-complete 1790–2020 fallback that is **not**
  public domain and carries registration + redistribution terms).
- **An explicit redistributable / not-redistributable verdict per source, with reasoning** —
  the single most important output. US-government works are public domain (→ eligible for the
  public API surface, unlike UCSB); NHGIS is not (→ inherits the D030/UCSB analysis-only posture).
  **The trade — clean-but-shallow public-domain vs. complete-but-restricted — is the finding, not
  a decision made in passing.** If it forces a dual-source split (a modern public-domain core + a
  restricted historical layer), say so — that is the exact D014 MIT/UCSB shape.
- A recommended source (or dual-source split), a coverage floor, and a **first-cut answer to Open
  question 1** (what the minimum public-domain window is that would carry Post 4's per-capita
  finding without the hard historical parse).

### Implementation Notes

- Reuse E3's method: a head-to-head table plus a licensing table with **verbatim** license
  language, so the redistributable verdict is auditable and not a paraphrase. The `research-pv-source.md`
  §3 licensing table is the template.
- Check `api.census.gov`'s decennial endpoints for the actual earliest year available as structured
  data — this single fact most shapes S2's cost.
- If NHGIS becomes the recommended full-history source, state plainly that population inherits
  `redistributable=false` and cannot reach the snapshot — and that a public-domain **modern**
  subset can still serve the API (the D014 pattern applied to census).

### Dependencies

- None (research spike). Gates S2–S5.

_Story of epic #129 (E10 — census / apportionment analysis)._

---

### E10-S2: Ingest population into a conforming dimension (`usvote/census/`)

**Issue title:** Ingest decennial state population into a conforming dwh dimension via usvote/census/
**Labels:** `epic:census`, `enhancement`, `infrastructure`, `priority:low`

**Body:**

### Summary

Fetch, parse, transform, and load decennial state population into the warehouse as a new
**source-namespaced subpackage** `src/usvote/census/` (D015) — its own scrape/parse/transform/load
and a `pipeline.py` (`run_census_pipeline`), mirroring `usvote/mit/` and `usvote/ucsb/`. The
loaded grain is `(census_year, state, series, population)` where `series ∈ {apportionment,
resident}` (D054). Snapshot the source material locally (D023 / #89 pattern) so rebuilds need no
network.

> **Shape gated on S1 (do not final-file until S1 lands).** If S1 finds the source is a
> **structured download** (the `api.census.gov` / clean-table case), this is **one MIT-shaped
> story**: a read + a transform + a load. If S1 finds the early censuses are **PDF/scanned**, this
> is **UCSB-shaped** and must split into (a) corpus snapshot, (b) era-generic parse, (c)
> transform/load — three stories, as E4 was (#34/#35/#36). Re-scope this story against S1's verdict
> before filing. The ACs below are written for the structured-source case and annotated where the
> PDF case diverges.

### Acceptance Criteria

- `src/usvote/census/` exists as a subpackage (D015) with `scrape.py` / `parse.py` /
  `transform.py` / `load.py` / `pipeline.py` and a `__main__.py` dispatching a `load` subcommand
  (the D027 subcommand convention). It **imports the EC spine readers** (`usvote/spine.py` /
  `usvote/years.py`) and **nothing under `usvote/census/` names `dwh.votes`-authoring logic** — it
  reads the spine, it does not redefine it (the greppable D015 invariant, enforced by a test
  mirroring the existing layering guards).
- The load lands `(census_year, state, series, population)` in `dwh` with **`series` labeled**
  (`apportionment` / `resident`) — **never a single blended population column** (D054). Carrying
  only one series is the named failure mode; the schema must hold both and say which is which.
- **State conformance is deferred to S3** but the loader must not invent states: a population row
  for a jurisdiction the EC spine does not recognize in that era **raises**, it is not silently
  loaded (the reconciliation is S3/S4's job, but a load-time spine check catches gross parse
  errors early).
- The build runs **from a local corpus with zero network requests** once snapshotted — a
  `USVOTE_CENSUS_*` env var mirroring `USVOTE_EC_HTML_DIR` / `USVOTE_UCSB_HTML_DIR` /
  `USVOTE_MIT_CSV_PATH` (exact name architect's call; propose `USVOTE_CENSUS_CORPUS_DIR`), with a
  `manifest.json` carrying per-file sha256/bytes/source-url as the EC corpus does (#89).
- **No fabricated values (D005):** a state/year with no published figure loads as **NULL with
  provenance**, never a zero or an interpolation. Interpolation is explicitly out (D055, S3).
- **Licensing posture is set at load (D014 pattern):** every population row carries a `source` and
  a `redistributable` flag, exactly as PV rows do — so the S1 verdict is a first-class per-row data
  attribute, not a comment. If the source is non-redistributable, `redistributable=false` on every
  row and S5's structural guard (below) keeps it off the snapshot.
- **Public-repo licensing hygiene (D022):** if the corpus bytes are non-redistributable (NHGIS),
  **no source bytes are committed** and any test fixtures are **synthetic/hand-written**, exactly
  as the UCSB fixtures are — guarded by a test that no restricted bytes ship. If the source is
  public-domain (Census Bureau), real bytes may be committed as fixtures (as the EC Archives
  fixtures are).
- Unit tests run offline against a small synthetic input; any test loading real Postgres carries
  `@pytest.mark.integration` and is excluded from CI. `ruff` + `mypy` clean.

### Implementation Notes

- The `series` distinction is not cosmetic — it is the D054 split, the census analogue of D041's
  `ec_share_full` / `ec_share_hybrid`: two numbers equal in the easy modern years and divergent
  exactly where it matters historically. Load both wherever the source provides both; where the
  source provides only one, load it labeled and record the gap.
- Prefer loading the Census Bureau's **published** figures (apportionment population and, where
  available, resident population) directly over deriving anything. Do **not** re-run any
  apportionment algorithm here (that belongs nowhere — S4 reconciles against *published* seat
  counts, not a re-derivation).
- Whether the dimension lives in `dwh` (conforming to `state`) or a separate schema is **Open
  question 3** — resolve at design before writing the DDL.

### Dependencies

- **E10-S1 (gates shape and licensing).** EC spine (`usvote/spine.py`, `usvote/years.py`, shipped).

_Story of epic #129 (E10 — census / apportionment analysis)._

---

### E10-S3: Conform to the state spine + build the `election_year → governing_census_year` calendar

**Issue title:** Conform census states to the EC roster and build the election→governing-census mapping
**Labels:** `epic:census`, `enhancement`, `priority:low`

**Body:**

### Summary

Two jobs, both about making the population dimension line up with the electoral record it will be
joined to: (1) reconcile census state names/entries against the **EC participation roster** so
population conforms to the spine rather than establishing a second answer for which states existed
when (D006/D015); and (2) build the explicit **`election_year → governing_census_year`** mapping —
the join that decides *which census actually determined a given election's allotment* — as a
tested lookup, never an interpolation or a nearest-decade rounding (D055).

### Acceptance Criteria

- **The `election_year → governing_census_year` mapping is an explicit, tested lookup** (D055). The
  census taken in year *C* apportions the House for the following decade, so it governs presidential
  elections until the next census's apportionment takes effect. **The wrong-easy-answer is
  nearest-decade rounding**, which maps `2020 → 2020`; the correct mapping is **`2020 → 2010`**
  (the 2020 census was not apportioned until 2021 and first governed the 2024 presidential
  election). A test pins the sharp cases (2020→2010, 2024→2020) and the full series. Build this
  mapping **first** — S4 and S5 both depend on it.
- **State conformance reads the EC roster, never re-derives it** (D006). The population dimension
  conforms to `ec_state_roster_by_year.json` / the D024 `pv_state_status` participation model for
  "which states existed and participated in which year." A census jurisdiction that does not map to
  a spine state in that era is a **documented correction**, not a silent drop.
- **The hard state cases are handled as documented corrections with provenance** (the
  `docs/corrections.md` pattern): **West Virginia separating from Virginia in 1863** (population
  must not be double-counted across the 1860→1870 boundary), **statehood mid-series** (a state's
  population enters only from the census after it exists on the spine), and **DC** — which is **not
  a state, holds no census-apportioned House seats, but casts 3 electoral votes since 1964** (the
  23rd Amendment). DC's persons-per-EV is computable but its seat-reconciliation (S4) is special:
  its 3 votes are not census-apportioned.
- **No interpolated population anywhere in the loaded data** (D005/D055). An election year that is
  not a census year takes the **governing-census figure**, labeled as of that census — the
  staleness is stated, not smoothed away. A test asserts no synthesized between-census values exist.
- **The Reconstruction years are in scope** (correcting #129): 1868 → governing census 1860, 1872 →
  governing census 1870, both mapped and tested like any other year.
- New corrections land in `docs/corrections.md` with public-domain citations (the boundary/statehood
  facts are historical record, independently sourceable — so they ship regardless of the S1
  licensing verdict, exactly as `usvote/pv/absences.py`'s citations do).
- Unit tests offline; `ruff` + `mypy` clean.

### Implementation Notes

- The calendar mapping is small, pure, and dependency-light — factor it as its own tested constant
  (a `usvote/census/` module in the dependency-free spirit of `usvote/years.py`), so S4 and S5 read
  it by import rather than re-deriving the lag.
- "Governing census" is a fact about the *apportionment that was in force*, which the recorded
  `total_electoral_votes` already reflects — so S4's reconciliation is the check that this mapping
  is right, not an independent second opinion.
- Conform to the spine the way the PV sources do: read participation from the roster, add a
  correction where census geography and spine geography genuinely differ, and never let the
  population source vote on statehood.

### Dependencies

- **E10-S2** (loaded population to conform). EC roster / `usvote/years.py` / `pv_state_status` (shipped).

_Story of epic #129 (E10 — census / apportionment analysis)._

---

### E10-S4: Reconcile census-derived seat counts against recorded `total_electoral_votes`

**Issue title:** Assert census-derived seat counts reconcile against recorded total_electoral_votes across the series
**Labels:** `epic:census`, `testing`, `priority:medium`

**Body:**

### Summary

The epic's **strongest validation** (#129): the allotment implied by an apportionment is already
in `dwh.votes.total_electoral_votes`, so the census-derived seat count can be checked against it
across the whole series — the same two-way-assert shape as the D024 roster/fact reconciliation and
the E6 name-reconciliation guard. Where they disagree, **the recorded electoral votes win** (D006:
the Archives are authoritative) and the disagreement is a **documented correction, not a silent
adjustment**. Fail loud on an unexplained gap.

### Acceptance Criteria

- A reconciliation assert compares, per `(election_year, state)`, the **census-derived electoral
  allotment** against the recorded `total_electoral_votes`, across the full in-scope series
  (1824–2024, including the Reconstruction years 1868/1872).
- **The derivation reconciles the right quantity, and the wrong-easy-answer is named.**
  `total_electoral_votes` = the state's **apportioned House seats + 2 senatorial votes** (+ DC's 3
  since 1964, which are *not* census-apportioned). **Reconciling raw census House seats directly
  against `total_electoral_votes` is off by exactly 2 per state** (and wholly wrong for DC) — the
  assert must add the +2/state and special-case DC, or it will "fail" on every state in every year
  in a way that looks like a data problem.
- **Reconcile against the Census Bureau's *published* seats-per-state, not a re-run of the
  apportionment method.** Re-deriving seats from population (method of equal proportions since 1940,
  earlier methods before) introduces a second modeling surface with its own bugs; read the
  published apportionment result and reconcile *that*. (If S1 finds only population and not
  published seats for some era, that era reconciles on population→EV only where defensible and is
  flagged otherwise — do not silently re-derive.)
- **The basis is the appointed allotment** (D041/D046): the reconciliation target is
  `total_electoral_votes` (appointed), consistent with `ec_denominator`. 1872 reconciles against the
  **appointed 366** (AR/LA restored), not the 352 the Archives page totals; 1868 against its
  appointed allotment with Georgia's disputed votes handled as the recorded fact states.
- **Every disagreement is cataloged with a cause in `docs/corrections.md`** — the recorded EV wins,
  the census figure is annotated, and the reason is stated (a boundary case, a mid-cycle admission,
  a known Census/Archives discrepancy). An **unexplained** gap **fails the build**, it is not
  rounded away.
- The assert runs as a warehouse-build validation (the "validation is load-bearing" convention),
  offline-testable against synthetic frames; the live-series run carries `@pytest.mark.integration`.
- `ruff` + `mypy` clean; CI green without a live DB.

### Implementation Notes

- This is the census analogue of `usvote/pv/status.py::assert_catalog_matches_spine` — a two-way
  cross-check against the spine where the *second* direction (no spine allotment left unexplained by
  the census) is the one with teeth.
- Model the +2 senatorial votes and DC's 23rd-Amendment 3 explicitly; they are the difference
  between "House apportionment" and "electoral allotment" and the single most likely source of a
  spurious mismatch.
- The reconciliation is what certifies S5's numbers for G5 publication — treat a red assert as a
  publication blocker, not a warning.

### Dependencies

- **E10-S3** (the `election_year → governing_census_year` mapping and conformed states). Recorded
  `total_electoral_votes` (EC spine, shipped).

_Story of epic #129 (E10 — census / apportionment analysis)._

---

### E10-S5: Expose persons-per-electoral-vote as a warehouse view (public exposure gated on S1)

**Issue title:** Expose persons-per-electoral-vote by (year, state) as a warehouse view; gate public exposure on the S1 verdict
**Labels:** `epic:census`, `enhancement`, `priority:low`

**Body:**

### Summary

Materialize the derived per-capita series — **persons-per-electoral-vote by `(year, state)`** —
as a warehouse view alongside the existing join/hybrid views, rebuilt by `usvote/warehouse.py`,
so a consumer reads it straight off the view with **no computation in the consumer**. This is the
series Post 4's `APPORT-per-capita-drift` payoff reads. **Whether it reaches the public snapshot/API
is gated on the E10-S1 licensing verdict** and, if permitted, requires a `SNAPSHOT_SCHEMA_VERSION`
bump.

> **This story has two shapes, decided by S1 (do not final-file until S1 lands):**
> **(A) source is public-domain** → the per-capita series may reach the snapshot/API, and this
> story includes the snapshot materialization + schema bump + `/v1` route + the model↔column drift
> guard, mirroring E8-S9 (#139). **(B) source is non-redistributable** → the series is
> **analysis-only**, this story stops at the analysis-surface view, and the deliverable becomes the
> **structural guard** that keeps population-derived columns off the snapshot. The ACs below cover
> the common core plus each branch.

### Acceptance Criteria (common core)

- A warehouse view exposes **persons-per-electoral-vote by `(year, state)`** — the recorded
  `total_electoral_votes` numerator against the governing-census population denominator (S3
  calendar) — created and rebuilt by `usvote/warehouse.py::rebuild_views` after the join views, so
  a `run_warehouse` / `python -m usvote all` build leaves it populated (and a `--replace` build
  rebuilds it).
- **The view states which population series it used** (D054). The default per-capita denominator is
  **resident population** (Open question 2); the view carries the series label so a consumer can
  never mistake an apportionment-population figure for a resident-population one. A fan-out guard
  asserts one row per `(year, state)`.
- The view is EC-conformant: it exists for every `(year, state)` the spine carries in scope, and a
  year/state with no population figure reads **NULL, not zero** (D005) — an honest gap, paired with
  enough metadata to say *why* it is null (no census figure vs. pre-statehood).

### Acceptance Criteria — Branch A (source is redistributable / public-domain)

- The per-capita series is materialized into the snapshot (a new snapshot table or columns on the
  existing surface — architect's call), **`SNAPSHOT_SCHEMA_VERSION` is bumped** (the content hash
  covers only the existing data rows, so a shape change is invisible to it — the D039/D042
  handshake, exactly as #139 did), and `snapshot_schema.DATA_COLUMNS` is extended explicitly (the
  containment property: a view column does not reach the snapshot until listed there).
- A `/v1` route (or an extension of an existing one) exposes the series with the provenance/license
  `meta` block naming the Census Bureau + US-PD, mirroring the heterogeneous-provenance handling
  #139 introduced. `docs/api-snapshot.md` and the model↔column completeness test are updated.

### Acceptance Criteria — Branch B (source is non-redistributable)

- **The firewall is structural, not editorial** (D030/D057). The population-derived columns **cannot
  reach the snapshot** — enforced the way the UCSB firewall is: either (i) the snapshot build never
  imports `usvote/census/` and a `test_layering.py`-style subprocess test proves the snapshot builds
  with `usvote.census` made **unimportable**, or (ii) a two-view split where only a public-domain
  view could ever be named by the snapshot and the non-redistributable per-capita view is never
  referenced by `DATA_COLUMNS`. A **data assertion** (mirroring `snapshot.assert_redistributable_only`)
  is defense-in-depth, but the **structural** guard is primary — a data-only test can pass vacuously.
- No `SNAPSHOT_SCHEMA_VERSION` bump, no `/v1` route — the series is analysis-only, and Post 4 cites
  it as a computed finding rather than a live-API-reproducible one (the weaker but honest G5 form).

### Implementation Notes

- Follow the `join.py` / `pv/views.py` precedent: a parameterized builder + a pure pandas oracle as
  the tested expression of the same computation, so the SQL and the oracle cannot drift silently.
- Under G5, the numbers this view produces **are the evidence** for Post 4 — so a red S4
  reconciliation is a hard blocker on shipping this view's numbers, not a warning.
- Do **not** put any normative framing in the view or its docs (Publication guardrail G5 trap 2):
  it reports persons-per-EV; whether that is *a problem* is the reader's call and outside what the
  data can establish (#129 out-of-scope; `social/scout.config.md` G5).

### Dependencies

- **E10-S4** (certified reconciliation). **E10-S1** (decides Branch A vs B). `usvote/warehouse.py`,
  the snapshot build (shipped). For Branch A: E8-S1 snapshot plumbing (#94/#95).

_Story of epic #129 (E10 — census / apportionment analysis)._

---

## Proposed decisions (candidates for Fred + architect — NOT yet in `decisions.md`)

Record in [`decisions.md`](decisions.md) as **D058–D062** only once approved (append-only; the
highest recorded is **D057**). Summaries here for backlog readability.

> **Renumbered 2026-08-31.** This section originally proposed **D053–D057**, written when D052
> was the highest recorded. All five of those slots were taken while the backlog sat pre-review —
> D053 (public hybrid recomputed from the catalog, #102), D054 (Bot Fight Mode off the API zone),
> D055 (deploy gate asserts the serving snapshot), D056 (cross-repo Pages ownership), D057
> (`create_hybrid_views` derives through `build_hybrid_from_frames`). The candidates below keep
> their **D05N (proposed)** labels for continuity with the story bodies in #181–#184, but the
> mapping when they are recorded is **+5**: proposed D053 → **D058**, D054 → **D059**, D055 →
> **D060**, D056 → **D061**, D057 → **D062**. Confirm the next free slot at recording time rather
> than trusting this note — the same drift can happen again.

- **D053 (proposed) — The population dimension conforms to the EC spine and lands as
  `usvote/census/`, a source-namespaced subpackage (D006/D015).** It reads the state roster and
  recorded allotments *from* the warehouse and is never a second source of truth for which states
  existed when — the direction is `census -> spine`, never the reverse, exactly as MIT/UCSB depend
  on the spine. (Largely an application of D006/D015 to a non-election source; recorded to name the
  census-specific shape. May collapse into "just apply D006/D015" at Fred's discretion. **Note:** it
  does **not** pre-decide `dwh`-dimension vs. separate-schema — that is Open question 3.)
- **D054 (proposed) — Carry two population series, apportionment and resident, labeled, never
  blended.** The census analogue of D041's `ec_share_full` / `ec_share_hybrid` split: two numbers
  equal in the easy modern years and divergent exactly where it matters (three-fifths clause
  pre-1868; "Indians not taxed" excluded through 1940). Apportionment population answers *"why this
  many electoral votes?"* (the S4 reconciliation input); resident population answers *"how many
  people per electoral vote?"* (the per-capita denominator). Carrying only one is the failure mode;
  any derived figure states which it used. This is material with historical weight — a definition of
  "population" that counted some people as fractions of a person is not a column-naming wrinkle.
- **D055 (proposed) — The election→census join is an explicit `election_year →
  governing_census_year` lookup; no interpolated population, ever (D005).** The census that governs
  an election is the one whose apportionment was *in force*, not the nearest decade — `2020 → 2010`,
  not `2020 → 2020`. Between-census election years take the governing-census figure with the
  staleness labeled, never a smoothed interpolation (invented data, D005). Getting the lag wrong
  shifts every per-capita figure by up to ten years in a way that still looks plausible.
- **D056 (proposed) — The census-derived seat count reconciles against recorded
  `total_electoral_votes`; the Archives win on disagreement (D006), disagreements are documented
  corrections (`docs/corrections.md`), not silent adjustments.** The two-way assert (D024 shape) is
  the epic's strongest validation. It reconciles against the **appointed** allotment (D041/D046) and
  against the Census Bureau's **published** seats-per-state (never a re-run of the apportionment
  method), after adding the +2 senatorial votes per state and special-casing DC's non-apportioned 3.
  An unexplained gap fails the build.
- **D057 (proposed) — The population dimension's public-surface exposure is gated on the E10-S1
  licensing verdict and enforced structurally (extends D030).** Public-domain source (Census
  Bureau) → the per-capita series may reach the snapshot/API with a `SNAPSHOT_SCHEMA_VERSION` bump.
  Non-redistributable source (NHGIS) → it inherits the UCSB/D030 analysis-only posture, and a
  **structural** guard (import-graph / two-view split, proved with `usvote.census` unimportable in a
  subprocess — not a convention, not a data-only test that can pass vacuously) keeps
  population-derived columns off the snapshot. Every population row carries `source` +
  `redistributable` from load (D014), so the verdict is a first-class data attribute.

---

## Open questions

1. **How much history does Post 4 actually need? (the cost lever — pairs with OQ5.)** The payoff
   instance is a *trend*, not a 1790 census.
   - **(a)** Full ambition — 1824–2024 (ideally 1790–2020), both series, all boundary/statehood
     corrections. Complete, but front-loads the hard PDF-parse + apportionment-population modeling.
   - **(b)** *Recommended for the post:* a **modern, clean, public-domain window** from
     `api.census.gov` (resident population, ~1900/1930–2020) that carries the finding and dodges the
     hardest work; full historical backfill deferred to a follow-on pass.
   - **Recommendation: (b) to unblock Post 4, (a) as the epic's eventual target.** This decides
     whether S2–S5 are a ~two-week clean-load job or a multi-month historical-parse epic.

2. **Which population series is authoritative for the per-capita question?** (#129 OQ2)
   - **Recommendation: both, for different jobs** — **resident** population as the per-capita
     denominator (S5), **apportionment** population for the seat-count reconciliation (S4). Confirm
     during/after S1; it is the D054 split and shapes the S2 schema.

3. **Does the population dimension belong in `dwh` (conforming to `state`) or a separate schema?**
   (#129 OQ3) — it is not an election fact and does not fit the star schema's existing grain.
   - **Recommendation: a conforming dimension in `dwh` attached to `state`** (it conforms to the
     spine, D006), but flag that it is not an election fact — architect's call at S2 design. D053 is
     deliberately written *not* to pre-decide this.

4. **The redistributable branch plan, if full-history data turns out non-redistributable.** S1 may
   find the only complete 1790–2020 source (NHGIS) is restricted.
   - **(a)** Take the non-redistributable path for the whole series → population is analysis-only,
     Post 4 cites a computed finding (weaker G5, no live re-run).
   - **(b)** *Recommended:* **dual-source, the exact D014 shape** — a modern **public-domain** core
     (Census Bureau / `api.census.gov`) that reaches the public API, plus a restricted **historical**
     layer for analysis only. Public per-capita for the modern window, analysis-only before it.
   - **Recommendation: (b)** — it keeps the public API honest and mirrors the MIT/UCSB split the repo
     already runs. This is a real strategic fork; flagging it now so S5's shape is not a surprise.

5. **Is E10 pulled forward now to unblock Post 4's payoff, or does Post 4 ship on its two `record`
   instances and take the payoff later?** E10 is Stretch/Later on the roadmap; the publishing driver
   may reprioritize it.
   - **Recommendation: decide explicitly.** If the payoff instance matters for Post 4's impact, pull
     S1 forward now (it is a research spike that can run ahead of anything) and raise S1–S5 to
     `priority:medium/high`. If not, Post 4 ships whole on `APPORT-1920-failure` +
     `APPORT-total-moves`, and E10 stays low-priority. **Note:** even under "pull forward," Post 4
     need not *wait* — it can publish on the record instances and gain the payoff in a later revision
     once S5 lands.

6. **Confirm the #129 corrections.** The Reconstruction years 1868/1872 are now ingested
   (`UNSUPPORTED_EC_YEARS` is empty, #143/#144), reversing #129's out-of-scope bullet, so the census
   work covers them and S4 reconciles them against the **appointed** allotment (1872 → 366).
   - **Recommendation: confirm** (this is the repo catching up to itself, not a scope expansion). If
     Fred instead wants 1868/1872 population held out for a reason, say so — but the default is that
     an ingested election year gets its population like any other.
