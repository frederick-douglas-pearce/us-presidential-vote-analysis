# US Presidential Vote Analysis — Hybrid Computation Backlog (E7)

> **Status: APPROVED FOR FILING (2026-07-28).** Fred approved this backlog and settled every open
> question at the 2026-07-28 review. This backlog expands **E7 (Hybrid computation)** from
> [`../docs/ROADMAP.md`](../docs/ROADMAP.md) (Milestone 3), which the roadmap named in one line —
> *"EC/PV average; flip detection; three-method margin comparison"* — but did not scope. Decisions
> referenced as D0NN live in [`decisions.md`](decisions.md); the decisions this round adds
> (**D037–D041**) are **recorded in `decisions.md`** (2026-07-28), summarized at the bottom for
> backlog readability.
>
> **Filed 2026-07-28:** epic **#120**; stories **#70** (E7-S1, re-labeled in place), **#121** (E7-S2),
> **#122** (E7-S3), **#123** (E7-S4), **#124** (E7-S5), **#125** (E7-S6); **#102** (E8-S8) amended to
> the D039 read seam.

> **Resolved at review (2026-07-28).** Fred settled every open question; the architect resolved OQ4.
> **All questions are resolved and this backlog is approved for filing (2026-07-28).** The formula,
> the EC-determinative rule, the margin unit, the two-grain view shape, the PV-denominator pick, the
> EC-majority basis, and the UCSB-absent behavior are all spec targets now (folded into the stories +
> D037–D041 below), not open questions.
> - **OQ4 (roll-up ownership) — RESOLVED (architect).** Not "reconcile later": the shared
>   national-aggregation derivation is **single-sourced now** — extract the primitive into
>   `usvote/hybrid.py` and have `snapshot.build_national_rollup` call it. The two roll-up *tables*
>   stay separate for MVP (D029). See D037.
> - **OQ5 (PV-completeness) — SETTLED: (b) (Fred, 2026-07-28).** The draft's rule (a) —
>   **withholding** the hybrid for any year containing a `legislature_chosen` state — is **rejected**.
>   Withholding would suppress the House-contingent, no-EC-majority elections the method exists to
>   speak to. Partial-PV years (including **1824**) stay in scope and **always get a hybrid computed**.
>   Fred picked **(b)** — compute with mismatched denominators, flagged via `pv_coverage`: *"I vote
>   for b. Simpler and sticks more closely to the historical record for ec, so as not to cause as much
>   confusion, just needs an explanatory footnote or similar."* The `apply_coverage_policy` seam stays
>   factored as a swappable policy anyway (it costs nothing and (c) remains implementable if the
>   explorer later wants it), but (b) is the shipped and only-configured rule. See D038.
> - **EC-majority basis (D041) — RESOLVED (Fred, 2026-07-28), and the earlier premise was corrected.**
>   Fred's principle: *"I would like the most historically accurate vote that is what was used to elect
>   the president, not a simplification on our part."* The earlier "cast vs appointed" open item was a
>   **misreading** of the code and is removed. `total_electoral_votes` is each state's **allotment
>   (appointed)**, not votes cast (verified against `docs/corrections.md` + `ELECTORAL_VOTE_SHORTFALLS`).
>   So `ec_denominator` = Σ `total_electoral_votes` (each state once) is an **appointed** denominator —
>   exactly the 12th Amendment's "majority of the whole number of Electors appointed" — while the
>   numerator (`president_electoral_votes`) is votes actually **cast**. That is the constitutionally
>   correct formulation and matches the historical record (2000: Bush 271 of 538 appointed, 270 needed).
>   D041's appointed citation is correct as written.
> - **UCSB-absent warehouse (E7-S2) — SETTLED: accept the NULLs (Fred, 2026-07-28).**
>   `hybrid_preferred` does **not** assert UCSB presence; over an EC+MIT-only warehouse it is simply a
>   1976-only surface with NULL `pv_share` / `hybrid_score` before that — honest per D005, no
>   fabrication. Revisitable once the display layer has an opinion.

Each `E7-SN` section below is a GitHub issue body ready for creation. E7 is M3 work. It is
scoped **against the merged EC+PV join views that already shipped in E6** (`src/usvote/join.py`,
built by `usvote/warehouse.py`) — not against a hypothetical. Every story states **which
view/column it reads and what it emits**, in the vocabulary those modules already use.

**Package name:** `usvote` (D013). The computation lands as **`src/usvote/hybrid.py`** — a
single top-level **EC-domain** module in the `spine.py` / `join.py` / `snapshot.py` /
`warehouse.py` family (D015/D027), a direct sibling of `join.py`: it names
`ec_pv_preferred` / `ec_pv_redistributable` (EC star-schema view knowledge), so the greppable
invariant *nothing under `src/usvote/pv/` names `dwh.votes`* keeps it **out** of `usvote/pv/`,
exactly as it keeps `join.py` out. The architect **endorsed the flat placement** — no D015/D027
strain, and `hybrid.py` is **not** a second composition root (it reads join views, it does not
sequence sources). It will be **denser than `join.py` from the start** because it carries two
things `join.py` does not: an explicit **roster read** (`dwh.pv_state_status`) and the **PV-denominator
policy switch**. **Split to a `usvote/hybrid/` subpackage** only when a concrete trigger fires:
when the **coverage-policy seam grows past one pure function**, or when **flip/margin needs its own
oracle distinct from the score oracle**. Until then, `join.py` (one parameterized builder + a pure
oracle + guards, all in one module) is the precedent for staying flat.

**The E7 deliverable is computed data + validated logic, not charts (D001/D011).** The
presentation/frontend is deferred (D001); E7 produces the numbers and the guards that make them
trustworthy. It implements the **common-case** average / flip / margin per **D011** — the formal
hybrid written spec (no-270, contingent-election legal treatment) is an explicitly named **future
workstream, NOT an E7 deliverable**. Where the unspecified edges bite (1824 contingent /
no-EC-majority; `took_office` vs `president_electoral_rank`, D010), E7 **flags, it does not
resolve** the *legal who-takes-office* question — but it **does compute** the hybrid score/winner/
margin for those years (that is the whole point). Per Fred's stated intent, "no EC majority" is the
hybrid's **motivating case**, a first-class expected state, not a data problem (see the epic
rationale and E7-S4).

**Depends on:** E6 (cross-source join, epic #63) — specifically the shipped `ec_pv_preferred`
(analysis surface) and `ec_pv_redistributable` (API surface) join views and the resolved PV
series they wrap (`pv_preferred` / `pv_redistributable`, D017/D026). E7 reads those views plus the
`dwh.pv_state_status` roster (D024); it does not touch `dwh.votes` / `dwh.pv_votes` directly. **E7
landing is what unblocks #102 (E8-S8)** — the hybrid/flip/margin fields on the API (D029).

---

**Label conventions:**
- Epic label: `epic:hybrid`
- Type labels: `enhancement`, `research`, `documentation`, `testing`, `infrastructure`
- Priority labels: `priority:high`, `priority:medium`, `priority:low`

> **Label note (2026-07-28):** the `epic:hybrid` label was auto-created when epic #120 was filed
> (the create-issue API creates a missing assigned label), so it landed with a **default gray color
> (`ededed`) and no description**. To match the intended spec, run once:
> `gh label edit "epic:hybrid" --color "5319E7" --description "E7: hybrid (EC/PV average) computation — flip detection + three-method margins"`.
> The type/priority labels already existed from earlier rounds.

---

## E7: Hybrid computation — epic #120

**Issue title:** Epic: hybrid EC/PV-average computation — flip detection + three-method margins
**Labels:** `epic:hybrid`, `enhancement`

**Body:**

### Summary

Compute the project's third way of determining a winner — the **hybrid**, Fred's original
contribution: for each candidate in an election, take their **share of the electoral votes** and
their **share of the national popular vote**, **average the two ratios, and the highest averaged
ratio wins** — and, alongside the EC and PV outcomes it averages, answer the thesis question (D001):
**for each election, would it have flipped under PV or the hybrid, and by how much?** This epic
delivers the *computed data and the validated logic*, not a chart (D001) — the analytical substrate
the explorer (E9) and the API's hybrid fields (#102 / E8-S8) read.

**Why the hybrid exists (Fred's stated intent — it drives the design, D037/D041).** The hybrid is
designed to **circumvent the House choosing the President when no candidate wins a majority of
electoral votes** — *"let the people decide when the EC is very close."* Two design consequences
follow directly and are **not** presentation niceties: (1) "no EC majority" is a **first-class,
expected outcome state** (`ec_determinative = false`), the very case the hybrid speaks to, not an
error to swallow; and (2) because the hybrid exists precisely for the House-contingent, partial-PV
elections, E7 **computes a hybrid for every in-scope year** — it does **not** withhold on partial PV
coverage (the rejected rule (a)). The fuller legal argument arrives later with the visualizations
(D001), so E7 **records the intent and computes the common case** without over-formalizing the legal
edges — the D011 boundary holds (no-270 / contingent legal treatment stays a future workstream).

E7 is scoped **directly onto E6's shipped join views**. The EC↔PV join (`usvote/join.py`, D026)
already produces, at the canonical `(year, state, candidate)` grain, one parameterized view per
resolved PV series:
- **`ec_pv_preferred`** — the **analysis surface** (full history, ~1824–2024; MIT wins the
  1976–2024 overlap, UCSB supplies pre-1976, incl. `redistributable=false` rows), and
- **`ec_pv_redistributable`** — the **API surface** (MIT-only, 1976–2024; can never carry a UCSB
  row, D016/D030).

Both already carry `national_electoral_votes` (a `SUM(...) OVER (PARTITION BY year, candidate_id)`
window, exact on the dense EC fact — D026 §5), `total_electoral_votes`, `candidate_votes`, and
`state_total_votes`. They do **not** carry `pv_status` — that lives only on the `dwh.pv_state_status`
roster (D024), which E7 reads explicitly (see below). E7 rolls those state rows up to **national**
three-method outcomes, detects flips, and computes three-method margins.

**The two-surface problem, and how one computation serves both (locked to spec, D037).** E7 is a
**pure computation parameterized by which resolved join view it reads** — the same "two views, one
builder" shape `join.py` itself uses (D026 §1). Run over `ec_pv_preferred` it emits
**`hybrid_preferred`** (analysis, full history); run over `ec_pv_redistributable` it emits
**`hybrid_redistributable`** (API, MIT-only). Because `hybrid_redistributable` wraps the
redistributable join view — which is defined **independently** as `WHERE redistributable` (D017,
never a filter over the preferred series) — **no UCSB-derived number can structurally reach the
public surface**. The snapshot (`usvote/snapshot.py`) materializes only `hybrid_redistributable`,
exactly as it materializes only `ec_pv_redistributable` today (D030). This is the seam #102 reads
(see the Read-seam handshake below).

**PV gaps are handled honestly — computed and flagged, never averaged over silently (D005/D024,
locked as D038).** The hybrid needs a *national* PV total, which is only strictly apples-to-apples
where every state that cast electoral votes also **held a popular vote**. The roster
(`dwh.pv_state_status`, D024) makes the exception explicit: a `legislature_chosen` state cast
electoral votes but never held a popular vote, so its electoral votes enter the EC denominator while
its (non-existent) popular vote cannot enter the PV denominator — a **structural denominator
asymmetry, not missing data** (there is deliberately no `unknown` status; a genuine parse/load gap
raises rather than hiding — D024 §4). E7 does **not** withhold the hybrid for such years (the
rejected rule (a)) — it **computes one and flags the coverage** via `pv_coverage` (D024 §8, the
EV-weighted share of the year's electoral votes cast by `popular_vote` states). How the mismatched
denominators are handled is **settled (D038): (b)** — compute with the mismatched denominators (EC
over all states, PV over PV states), flagged by `pv_coverage < 1.0`. Rule (c) (restrict both shares
to popular-vote-holding states so the denominators match) is **not shipped**; the
`apply_coverage_policy` seam keeps it swappable at zero cost, but (b) is the only configured rule and
applies globally to every affected year. See the split in E7-S2/S3.

### Roadmap position (note)

Per D029 the ROADMAP critical path is **E6 → E8 (API MVP)** directly, with **E7 + E9 → the
explorer** and **E7 → E8's later hybrid fields (#102)**. E7 does not block the shipped API MVP;
it **unblocks #102** (the hybrid/flip/margin fields) and feeds E9 (the mart).

### Scope

- An empirical **MIT-vs-UCSB overlap study** (folding in **#70**) producing a recommended
  cross-source tolerance and a **benign-seam verdict** — the evidence that a margin/flip *trend*
  crossing the 1976 source seam in `pv_preferred` is trustworthy (E7-S1).
- The **three-method national outcomes** — per `(year, candidate)` national EC / PV / hybrid
  scores and the per-method winner, plus the per-election `ec_determinative` flag — as a pure
  computation over a resolved join view, **with the `dwh.pv_state_status` roster as a first-class
  input** and the EC share **split into `ec_share_full` (policy-invariant, the only input to
  `ec_determinative`) and `ec_share_hybrid` (policy-selected, feeds the hybrid)** (E7-S2).
- The **PV-denominator policy** — one named pure function (`apply_coverage_policy`) owning
  `ec_share_hybrid`, `pv_share`, and the derived `pv_coverage`, defaulting to the settled **(b)**
  with (c) a swappable one-line switch (E7-S3).
- **Flip detection + three-method margin comparison** — per-election `pv_flip` / `hybrid_flip`
  booleans against the EC baseline, and the top-2 percentage-point margin under each method (E7-S4).
- **Two materialized views at two grains** — `hybrid_preferred` / `hybrid_redistributable`
  (per-candidate) each with a per-election `hybrid_summary` companion — from one parameterized
  builder, rebuilt by `usvote/warehouse.py`; carries the fan-out guard, the structural + data
  redistributable-leak guards, and the gated real-corpus integration test (E7-S5).
- The **explanatory coverage note** (D038/(b)) — enumerate, from the live `dwh.pv_state_status`
  roster, every year containing a `legislature_chosen` state with its `pv_coverage`, and write the
  note that ships with any surface exposing a partial-coverage hybrid (E7-S6).

### Out of scope (deferred)

- **The D011 formal hybrid written spec** — the no-EC-majority ("no candidate reaches a majority")
  and contingent-election (1824 House, 1836 Senate VP) legal treatment. E7 **flags** these
  elections (`ec_determinative = false`) and **computes** their hybrid; the formal legal method spec
  (who takes office, any future refinement) is a **named future workstream, not an E7 deliverable**
  (D010/D011).
- **Snapshot + API materialization of hybrid fields** — that is **#102 (E8-S8)**, gated on this
  epic. E7 stops at exposing `hybrid_redistributable`; #102 folds it into the snapshot and the
  `/v1` responses (and must **bump `SNAPSHOT_SCHEMA_VERSION`** — see the read-seam handshake).
- **E9 analytical explorer data mart** — E7 produces the computed substrate; the query/mart
  surface behind maps/narrative is E9.
- **Presentation / frontend** — deferred (D001). No charts, no dashboard here.
- **Pre-1976 hybrid on the public surface** — the redistributable surface stays MIT-only
  (D016/D030); `hybrid_preferred` carries the full history for analysis only.
- **Minor PV-only candidates** — candidate scope stays EC-getters (D007).
- **One merged national roll-up *table*** — for MVP E7 keeps its `hybrid_summary` and the snapshot's
  existing `national_rollup` as **separate tables** (D029). This is **not** "reconcile later": the
  shared national-aggregation *derivation* is single-sourced **now** — extracted into
  `usvote/hybrid.py` and called by `snapshot.build_national_rollup` (OQ4 resolved — D037/F). Two
  separate tables, one derivation.

### Success Criteria

- [ ] For each in-scope election, `hybrid_preferred` (per-candidate) + `hybrid_summary`
      (per-election) expose per-candidate national EC / PV / hybrid scores, the per-method winner,
      `ec_determinative`, `pv_coverage`, `pv_flip` / `hybrid_flip` against the EC baseline, and the
      three-method percentage-point margins — read straight off the views, no computation in a
      consumer
- [ ] The known EC≠PV splits (**2000, 2016**) show `pv_flip = true`, and the hybrid outcome for
      each is correct under the settled formula (D037)
- [ ] **A hybrid is computed for every in-scope year, including partial-PV / no-EC-majority years**
      (1824 and the pre-~1880 window) — never withheld (rule (a) rejected, D038); `pv_coverage`
      surfaces the coverage honestly, and `ec_determinative` and `pv_coverage` are **separate,
      orthogonal** per-election columns (both populated for 1824)
- [ ] `ec_share_full` (never a coverage-restricted share) is the **only** input to
      `ec_determinative`, so no coverage policy can ever manufacture or destroy an EC majority that
      never existed (D041/A)
- [ ] `ec_determinative = false` (no EC majority) is a populated, expected outcome — the hybrid's
      motivating case — not an error or a null-because-broken
- [ ] Candidate EC shares sum to **≤ 1.0, never == 1.0** — `ec_denominator` is the **appointed**
      allotment (Σ `total_electoral_votes`, each state once) while the numerators are votes **cast**,
      so real shortfalls (2000 DC abstention) make the sum fall slightly short; validation asserts
      ≤ 1.0 with 2000 pinned as the fixture (D041)
- [ ] `hybrid_redistributable` **never carries a `redistributable=false` (UCSB) row** — guarded
      **structurally** (its definition names `EC_PV_REDISTRIBUTABLE_VIEW`, never
      `EC_PV_PREFERRED_VIEW`) **and** by a data assertion on the pre-aggregation input frame (D030)
- [ ] Both views (both grains) are rebuilt idempotently by `usvote/warehouse.py` (`rebuild_views`)
      after any load
- [ ] The #70 finding records a recommended tolerance + a benign-seam verdict, and E7's analysis
      output carries the seam caveat wherever a cross-1976 trend is exposed (D017)
- [ ] Unit + gated real-corpus integration tests pass under the existing gates (`uv run pytest`,
      `ruff`, `mypy`), CI green without a live DB — tests ship **with** the code that owns them (no
      standalone test story)
- [ ] **#102 (E8-S8) is unblocked** — the read seam (`hybrid_redistributable` → snapshot) is
      concrete and documented, including the `SNAPSHOT_SCHEMA_VERSION` bump #102 owes

### Stories

- [ ] #70 — E7-S1: Quantify MIT vs. UCSB PV discrepancies across the 1976–2024 overlap (fold-in, re-labeled in place)
- [ ] #121 — E7-S2: Three-method national outcomes + `ec_share_full`/`ec_determinative` + roster read (`usvote/hybrid.py`)
- [ ] #122 — E7-S3: PV-denominator policy — `apply_coverage_policy` (`ec_share_hybrid`, `pv_share`, `pv_coverage`)
- [ ] #123 — E7-S4: Flip detection + three-method margin comparison
- [ ] #124 — E7-S5: Materialize the two grains (`hybrid_*` + `hybrid_summary`); wire into the warehouse; guards + integration test
- [ ] #125 — E7-S6: Write the partial-coverage explanatory note + enumerate affected years from the live roster

### Read-seam handshake with #102 (E8-S8)

**This epic decides that seam (D039):** E7 exposes **`hybrid_redistributable`** (+ its
`hybrid_summary`) — resolved warehouse views alongside the join views, rebuilt by
`warehouse.rebuild_views`. #102 materializes them into the snapshot in `usvote/snapshot.py` (the same
module that already materializes `ec_pv_redistributable`), minting `candidate_slug` and dropping
`candidate_id` there (D006) exactly as it does for `ec_pv` today — so E7's views stay
warehouse-internal and carry the internal `candidate` / `candidate_id`, no public-id leak. **#102's AC
was amended** to: (a) name `hybrid_redistributable` / `hybrid_summary` as the read sources; (b) join
the hybrid fields into the existing `national_rollup` snapshot table (or a sibling `hybrid_rollup`
table — architect's call) rather than a new extract path, with `build_national_rollup` a **reader** of
E7's single-sourced national derivation; (c) keep the E9 mart as a *possible later* read source behind
the same seam, not a dependency; **(d) bump `SNAPSHOT_SCHEMA_VERSION`** (`snapshot_schema.py:21`) — the
content hash covers only the `ec_pv` data rows, so adding a roll-up/shape field is **invisible** to the
hash and the version must be moved **manually** or consumers will not see the new shape (D039/H).

Because the redistributable surface is MIT-only 1976–2024, where every state holds a popular vote,
the PV-denominator policy **degrades to identity** on it — `ec_share_hybrid == ec_share_full`,
`pv_coverage == 1.0`, and `hybrid_redistributable` is **provably policy-invariant** under (b) or (c).
So **#102 is not blocked** by the (b)/(c) question either way.

### Settled hybrid computation (D037; the shape E7 builds to)

The formula is settled (D037). The EC share is deliberately **split in two** (A): `ec_share_full` is
policy-invariant and is the *only* input to `ec_determinative`; `ec_share_hybrid` is the
policy-selected share that feeds `hybrid_score`. Under (b) they are equal; under (c) `ec_share_hybrid`
is restricted to popular-vote states. Keeping them separate prevents a coverage policy from ever
flipping `ec_determinative` (e.g. restricting 1824's EC share to PV states must **not** be allowed to
push Jackson above 0.5 and assert a constitutional majority that never existed).

| Quantity | Grain | Derivation (over a resolved join view + the roster) |
|---|---|---|
| `national_electoral_votes` | (year, candidate) | already on the view (window SUM, D026 §5) |
| `ec_denominator` | (year) | total electoral votes **appointed** — each state's `total_electoral_votes` counted **once**, summed. **In SQL this MUST use a subquery/DISTINCT over `(year, state)`, not a bare aggregate** — a bare sum over the joined rows multiplies each state's EV by the candidate count (F) |
| `ec_share_full` | (year, candidate) | `national_electoral_votes / ec_denominator`. **Policy-invariant; the ONLY input to `ec_determinative`** (A) |
| `national_pv_votes` | (year, candidate) | `SUM(candidate_votes)` over the candidate's state rows, `min_count=1` (a no-PV getter stays NULL, honest) |
| `national_pv_denominator` | (year) | each state's `state_total_votes` counted **once** (per-state `max` skips the faithless-elector NULL), summed — the source's *provided* denominator, never a re-sum (D017); under (c) restricted to `popular_vote` states |
| `pv_share` | (year, candidate) | `national_pv_votes / national_pv_denominator` |
| `ec_share_hybrid` | (year, candidate) | **policy-selected** (`apply_coverage_policy`): `= ec_share_full` under **(b, shipped)**; restricted to `popular_vote` states under **(c, not shipped)**. Feeds `hybrid_score` only |
| `pv_coverage` | (year) | Σ `total_electoral_votes` over `popular_vote` states ÷ `ec_denominator` — the EV-weighted PV coverage (D024 §8). **A derivation, not a roster column** (B) |
| `hybrid_score` | (year, candidate) | **`(ec_share_hybrid + pv_share) / 2`** — the average of the two ratios (D037) |
| `ec_winner` / `pv_winner` / `hybrid_winner` | (year) | the candidate maximizing each score (over **non-NULL** scores; see the NULL handling in E7-S2) |
| `ec_determinative` | (year) | **`ec_share_full(ec_winner) > 0.5`** — true only if the EC leader has a **strict** majority; false = no EC majority = the hybrid's motivating case (D041). **Orthogonal to `pv_coverage`** — both are populated for 1824 (A) |
| `pv_flip` / `hybrid_flip` | (year) | `pv_winner != ec_winner` / `hybrid_winner != ec_winner` |
| `ec_margin` / `pv_margin` / `hybrid_margin` | (year) | top-2 **percentage-point** gap in each score (D037 — pp only) |

**The majority basis is the appointed allotment (D041, settled).** `ec_denominator` = Σ
`total_electoral_votes` (each state once) is the **appointed** electoral total — exactly the 12th
Amendment's "majority of the whole number of Electors **appointed**" — while the numerator
(`president_electoral_votes`) is votes actually **cast**. Verified in code: `total_electoral_votes`
is each state's allotment, not votes cast (`docs/corrections.md`: the 2000 DC abstention preserves
`total_electoral_votes=3`, tracking the 1-vote gap in `ELECTORAL_VOTE_SHORTFALLS`, with
`assert_row_votes_sum_to_total` checking cast == total − shortfall). So 2000 is Bush **271 of 538
appointed** (270 needed), not 269 of 537 cast. **Consequence:** because shortfalls are real, Σ
`president_electoral_votes` can be **less** than `ec_denominator`, so candidate EC shares sum to
**≤ 1.0**, never == 1.0 — any validation asserts ≤ 1.0, with 2000 pinned as the fixture.

**The national-aggregation half of this already exists** in `usvote/snapshot.py`
(`build_national_rollup`, `snapshot.py:203`), including a subtle dedup — per-state
`groupby(...).max()` (skip-NA) then sum, so a faithless-elector state carrying a NULL
`state_total_votes` is **not** dropped from the denominator — plus `min_count=1`. Two hand-written
copies of that logic will drift, and #102 puts both under one public artifact. **OQ4 is resolved
(D037/F):** extract the national-aggregation primitive into `usvote/hybrid.py` and have
`build_national_rollup` **call it** — a small in-place change touching **neither** the snapshot's
source view, **nor** its public columns, **nor** `SNAPSHOT_SCHEMA_VERSION`. The two roll-up *tables*
stay separate for MVP (D029).

---

### E7-S1: Quantify MIT vs. UCSB PV discrepancies across the 1976–2024 overlap — #70

> **This is issue #70, folded into E7 and re-labeled in place (D040).** Retitled unchanged, swapped
> `epic:pv-join` → `epic:hybrid`, kept `research` + `priority:medium` + the issue number and its
> existing AC, repointed the body's `**Epic:**` line to epic #120. **Not** close-and-refiled — #70 is
> referenced by number in **D017**'s action items and D017 layer 3 is calibrated by its finding; a
> fresh number would orphan those references. The AC amendments below reflect that **E6 has now
> shipped** — #70's body was written 2026-07-13, before the join views existed, and referred to them
> speculatively.
>
> **Note — distinct from E7-S6 (#125).** #70 is the **cross-source** question (do MIT and UCSB agree
> in the overlap?). E7-S6 is the **denominator/coverage** question (the settled (b) coverage note).
> Different spikes; do not merge.

**Issue title:** Quantify MIT vs. UCSB PV discrepancies across the 1976–2024 overlap
**Labels:** `epic:hybrid`, `research`, `priority:medium`

**Body:** (existing #70 body retained; the deltas below are the only changes)

### Summary

MIT (CC0, 1976–2024) and UCSB (analysis-only, 1789–2024) both carry popular-vote values for the
overlapping years **1976–2024**. Measure how far apart they actually are — per `(year, state,
candidate)` and at national roll-up — to empirically test the **benign-seam assumption** behind
D017 and to **calibrate the overlap-validation tolerance** (D017 layer 3). This is the evidence
that the MIT-preferred canonical series (`pv_preferred`) does not introduce a methodological step
at the 1976 source seam — which is exactly the trust E7's cross-1976 margin/flip **trend** metrics
depend on. It doubles as a cross-check of the UCSB parse against the authoritative CC0 MIT reference.

### Acceptance Criteria (amended for shipped E6)

- The MIT−UCSB delta is computed **directly off the shipped relations**, no throwaway re-extract:
  the raw `dwh.pv_votes` union keeps **both** source rows across the overlap (D017/#68), and the
  `pv_ucsb` vs `pv_redistributable` views are the two single-source series to difference. *(Was:
  "whatever throwaway comparison notebook/script produced the numbers" — the numbers now come from
  shipped views; the **finding** remains the deliverable.)*
- Distribution of MIT−UCSB differences reported at (a) **per (year, state, candidate)** grain —
  absolute + percentage delta, and (b) **national PV roll-up** per election — per-candidate
  national totals from each source. Compare on the **canonical keys** now that both reconcile
  stages have shipped (`reconcile_mit` #67, `reconcile_ucsb` #38) — mismatches are a finding, not a
  dropped row (guard the inner-join silent-drop hazard).
- Cells/elections disagreeing beyond a candidate tolerance are **listed with provenance**, not
  silently reconciled — feeds the D005 reliability flag.
- **Systematic (non-random) discrepancy patterns are characterized** — specifically "other/write-in"
  handling and the **denominator** (each source's provided `state_total_votes` vs. a re-sum of
  candidate rows), the two failure modes D017's benign-seam caveat names. Margins in the comparison
  use each source's **provided `state_total_votes`**, per D017 (denominator choice is measured, not
  uncontrolled).
- A short written finding (mirror the E3 research-doc style under `.claude/specs/`) states: (a) a
  recommended numeric **tolerance** for the overlap-validation gate, and (b) whether the evidence
  **confirms or challenges** the benign-seam assumption — i.e. whether margin/flip metrics are
  materially affected by source choice in the overlap.
- **Amended:** the finding flows back into **D017 layer 3** and — new — **E7's margin/flip
  trustworthiness caveat** (whether a pre-vs-post-1976 margin *trend* off `pv_preferred` is honest),
  and optionally into a **cross-source tolerance guard** E7-S2/S4 (#121/#123) can run. *(Was: "flow
  back into D017 layer 3 and the E6 join design" — E6 has shipped; the finding now informs E7, not
  the join.)*

### Dependencies (amended)

- **Shipped:** `dwh.pv_votes` union + `pv_ucsb` / `pv_redistributable` views (E6/#68); MIT read +
  reconcile (#64/#67); UCSB parse + reconcile (#35/#36/#38); canonical keys (#30). *(Was framed as
  "E4/E5 … landing"; they have landed.)*
- Policy context: **D017** (this task is its empirical backbone), D005, D006, D007, D014, D016.

### Sequencing note

E7-S1 **informs, it does not code-block** E7-S2/S3/S4 — the computation is mechanical over
`pv_preferred` regardless of the verdict. But the analysis output is only *trustworthy across the
seam* once this lands, so E7-S1 is sequenced first and its verdict must be folded into E7's caveats
before `hybrid_preferred` is considered analysis-ready. It can proceed in parallel with S2.

---

### E7-S2: Three-method national outcomes + `ec_share_full`/`ec_determinative` + roster read — #121

**Issue title:** Compute the three-method national outcomes (EC / PV / hybrid) in usvote/hybrid.py
**Labels:** `epic:hybrid`, `enhancement`, `priority:high`

**Body:**

### Summary

Implement the computation core in **`src/usvote/hybrid.py`** (sibling of `join.py`): roll the
resolved join view's `(year, state, candidate)` rows up to **national** per-candidate outcomes and
derive the method scores. A **parameterized builder** (one function, `pv`/redistributable view as
the argument, mirroring `build_ec_pv_join_sql`) and a **pure-pandas oracle** (mirroring `join_ec_pv`)
are the two testable expressions of the same policy. **The `dwh.pv_state_status` roster is a
first-class input to this story** (not bolted on later) so that the E7-S3 policy pick lands as a
one-line switch, not a rework of denominator logic.

### Acceptance Criteria

- `usvote/hybrid.py` reads a **resolved join view** (`ec_pv_preferred` for analysis; parameterized
  so `ec_pv_redistributable` is the same builder over the MIT-only view) **and the
  `dwh.pv_state_status` roster** (which states are `legislature_chosen` / `popular_vote` /
  `not_participating`), and emits a per-`(year, candidate)` national frame with:
  `national_electoral_votes` (carried), `ec_denominator`, **`ec_share_full`**, `national_pv_votes`,
  `national_pv_denominator`, `pv_share`, and `president_electoral_rank` / `took_office` (carried
  through). `ec_share_hybrid` / `hybrid_score` / `pv_coverage` come from the E7-S3 policy function
  (default policy (b) applied here so the frame is complete)
- **The roster read is explicit and load-bearing.** `EC_PV_COLUMNS` (`join.py:83`) carries
  `total_electoral_votes` but **not** `pv_status`, so which states are `legislature_chosen` lives
  **only** on `dwh.pv_state_status` and `hybrid.py` **must read it**. **Inferring coverage from a
  NULL `candidate_votes` is forbidden** — that conflates a `legislature_chosen` state (no PV ever
  existed) with a state MIT simply does not cover, the exact distinction D024's no-`unknown` design
  preserves
- **The EC share is split in two (A):** `ec_share_full = national_electoral_votes / ec_denominator`
  is **policy-invariant** and is the **only** input to `ec_determinative`. The coverage-restricted
  `ec_share_hybrid` (E7-S3) feeds `hybrid_score` **only** and can never reach `ec_determinative` —
  so no coverage policy can manufacture or destroy an EC majority that never existed (the 1824
  hazard: restricting the EC share to PV states must not push Jackson over 0.5)
- **The national-aggregation primitive is single-sourced (D037/F/OQ4-resolved):** extract the
  per-`(year, candidate)` roll-up (national EV `first`; `SUM(candidate_votes, min_count=1)`;
  per-state `state_total_votes.max()` then sum) into a named function in `hybrid.py`, and have
  `snapshot.build_national_rollup` (`snapshot.py:203`) **call it**. This touches neither the
  snapshot's source view, nor its public columns, nor `SNAPSHOT_SCHEMA_VERSION`
- **Denominators are deduped, never re-summed** — `ec_denominator` counts each state's
  `total_electoral_votes` **once**; in SQL via a subquery/DISTINCT over `(year, state)`, **not** a
  bare aggregate (a bare sum multiplies each state's EV by the candidate count). `national_pv_votes`
  uses `min_count=1` so a no-PV getter stays **NULL**, not a fabricated 0 (D005/D026 §2)
- **`ec_denominator` is the appointed allotment, and candidate EC shares sum to ≤ 1.0, never == 1.0
  (D041, settled).** `ec_denominator` = Σ `total_electoral_votes` (each state once) is the
  **appointed** electoral total — exactly the 12th Amendment's "majority of the whole number of
  Electors **appointed**" — while the numerators (`president_electoral_votes`) are votes actually
  **cast**. Because real shortfalls exist (2000 DC abstention, faithless electors), Σ
  `president_electoral_votes` can be **less** than `ec_denominator`, so candidate `ec_share_full`
  values sum to slightly **under** 1.0 in such a year. That is correct, not a bug: any validation
  asserts EC shares sum to **≤ 1.0**, never == 1.0. Verified against `docs/corrections.md` +
  `ELECTORAL_VOTE_SHORTFALLS` (the 2000 abstention preserves `total_electoral_votes=3`;
  `assert_row_votes_sum_to_total` checks cast == total − shortfall) — 2000 is Bush **271 of 538
  appointed** (270 needed), not 269 of 537 cast
- `ec_winner` / `pv_winner` / `hybrid_winner` per election are the score-maximizing candidate **over
  non-NULL scores**; a true tie (should not occur in the common case) **raises** — but the tie-raise
  **must not fire on an all-NULL argmax** (an all-NULL year resolves to a NULL winner gracefully;
  see the UCSB-absent note)
- **`ec_determinative` is a first-class per-election output (D041):** `true` only when
  `ec_share_full(ec_winner) > 0.5` (strict majority); `false` = **no EC majority**, a populated and
  expected state (the hybrid's motivating case), never a null-because-broken. The EC winner column
  is still populated in that case (the plurality/rank-1 leader). `ec_determinative` and `pv_coverage`
  are **orthogonal columns** — both populated for 1824 (EC not determinative **and** partial PV
  coverage are two separate true facts)
- **NULL handling is specified (G):**
  - **UCSB-absent warehouse — SETTLED: accept the NULLs (Fred, 2026-07-28).** `run_warehouse` can
    build **EC+MIT only** (UCSB is optional), making `hybrid_preferred` a **1976-only** surface with
    NULL `pv_share` (hence NULL `hybrid_score`) before 1976. `hybrid_preferred` does **not** assert
    UCSB presence — that is honest per D005, no fabrication. `hybrid_winner` is the `argmax` over
    **non-NULL** `hybrid_score`; an all-NULL year resolves to a NULL winner (no raise); the tie-raise
    must not fire on an all-NULL argmax. Revisitable once the display layer has an opinion.
  - **Faithless/no-PV getter** — a getter with no PV inside an otherwise-computable year has a NULL
    `pv_share` and simply **does not compete** for the PV/hybrid winner (it is not a fabricated 0).
- A **pure-pandas oracle** produces the identical frame offline from a synthetic
  `ec_pv_preferred`-shaped input + a synthetic roster (no DB), and unit tests pin it against the
  live-view SQL builder's shape
- The internal `candidate` / `candidate_id` are carried (this is a warehouse-internal view); the
  public `candidate_slug` is **not** minted here — that stays a snapshot concern (#102), consistent
  with how `ec_pv` is handled today (D006)

**Tests shipped with this story (no standalone test story, D):** the oracle vs. SQL-builder shape;
the three method winners; the `ec_determinative` boundary (exact-tie and just-under-majority); the
**2000/2016** known flips; **2000 → Σ `ec_share_full` < 1.0** (537 cast of 538 appointed) pinned as
the ≤-1.0 fixture (D041); and **1824 → hybrid winner = Jackson** pinned as a fixture (Jackson leads
both the EC (99; Adams 84, Crawford 41, Clay 37 — 261 cast, 131 needed) and the PV (~151k vs ~113k)
with a majority of neither; the House elected Adams, so `took_office = Adams` while
`president_electoral_rank == 1 = Jackson`; the hybrid returns **Jackson** under **both** (b) and (c)
— so the E7-S6 note explains the *margin*, not the winner, moves).

### Implementation Notes

- Keep the shares as exact ratios; do not round before comparison/flip (rounding is a presentation
  concern, deferred D001). The `> 0.5` test for `ec_determinative` is on the exact `ec_share_full`.
- The EC-getter scope is inherited for free (the join view holds only getters; `pv_preferred` is
  D007/D019/D025-scoped) — no candidate filtering here.

### Dependencies

- E6 / #69 (`ec_pv_preferred` / `ec_pv_redistributable` — shipped); `dwh.pv_state_status` (E4,
  shipped). E7-S1 (#70) informs (caveats), does not block.

---

### E7-S3: PV-denominator policy — `apply_coverage_policy` (`ec_share_hybrid`, `pv_share`, `pv_coverage`) — #122

**Issue title:** Factor the PV-denominator policy into one pure function (b) / (c)
**Labels:** `epic:hybrid`, `enhancement`, `priority:high`

**Body:**

### Summary

The hybrid averages an EC share against a PV share. For partial-PV years — those with a
`legislature_chosen` state that cast electoral votes but held no popular vote (D024 §1/§4) — the two
shares are computed over **different-sized electorates** unless something is done about it. Rule (a)
(withhold the hybrid for such years) is **rejected** (D038): it would suppress the House-contingent,
no-EC-majority elections the hybrid exists to speak to. So E7 **always computes a hybrid** and picks
one of two honest denominator treatments:
- **(b)** compute with the mismatched denominators — EC share over all EC-casting states, PV share
  over the PV states — and flag the mismatch with `pv_coverage < 1.0`; or
- **(c)** restrict **both** shares to the popular-vote-holding states so the denominators match over
  the same sub-electorate, still flagged with `pv_coverage`.

The pick is **settled: (b)** (D038, Fred 2026-07-28 — *"Simpler and sticks more closely to the
historical record for ec … just needs an explanatory footnote"*) and applies globally to every
affected year. This story builds the machinery: factor the whole policy into **one named pure
function**, defaulting to (b), so (c) stays a **one-line switch** if the explorer later wants it (it
is **not shipped**).

### Acceptance Criteria

- A single pure function — e.g. `apply_coverage_policy(joined, roster, policy) -> frame` — owns
  **both numerators and both denominators for the hybrid**, returning `ec_share_hybrid`, `pv_share`,
  and `pv_coverage`. `ec_share_full` and `ec_determinative` are **outside its reach** (computed in
  E7-S2, policy-invariant — A). The (b)/(c) choice is a **single `policy` argument**, defaulting to
  **(b)** (settled, D038); (c) remains a one-line switch but is **not shipped**
- Under **(b, shipped)**: `ec_share_hybrid == ec_share_full`; `national_pv_denominator` is the PV
  states' provided `state_total_votes` (deduped, D017); `pv_coverage < 1.0` marks the mismatch.
  Under **(c, not shipped)**: **both** shares' denominators are restricted to `popular_vote` states —
  the EC numerator/denominator drop the `legislature_chosen` states' EV, so `ec_share_hybrid` may
  differ from `ec_share_full`
- **`pv_coverage` is defined precisely and computed here (B)** — it **does not exist anywhere in
  `src/`** today and is **not** a roster column; E7 is the first place it is derived. Definition:
  **numerator = Σ `total_electoral_votes` over `popular_vote` states; denominator = the full
  `ec_denominator`** (all EC-casting states). It is EV-weighted, not state-count-weighted (D024 §8).
  Placed in `usvote/hybrid.py`, with a test
- **The roster drives coverage, never NULL `candidate_votes` (B).** Which states are
  `legislature_chosen` is read from `dwh.pv_state_status` (passed in from E7-S2), never inferred
  from a NULL PV cell — that would conflate a `legislature_chosen` state with a MIT-uncovered one
- **Confirming property (A):** on the MIT-only `ec_pv_redistributable` surface every state held a
  popular vote, so `apply_coverage_policy` **degrades to identity** — `ec_share_hybrid ==
  ec_share_full`, `pv_coverage == 1.0` — and `hybrid_redistributable` is **provably policy-invariant**
  under (b) or (c). A test pins this (so #102 is unblocked regardless of the policy)
- The policy is applied **inside the parameterized computation** so both views get it identically;
  it simply never changes anything on the redistributable view

**Tests shipped with this story (D):** the coverage-policy identity on the redistributable surface;
(b)-vs-(c) behavior on a synthetic partial-PV year (both must return the same *winner*, differing
only in *margin*); and the `pv_coverage` derivation cases (a full-PV year → `1.0`; a
`legislature_chosen` year → the EV-weighted fraction < 1.0).

### Implementation Notes

- Keep `apply_coverage_policy` a **single pure function** for the first landing — that is the
  concrete `usvote/hybrid.py` split trigger: if this seam grows **past one pure function**, promote
  `hybrid.py` to a `usvote/hybrid/` subpackage (I).
- This is the E7 analogue of the "validation is load-bearing" rule: the coverage classification is a
  **tested function**, not a comment. It **classifies** (it does not raise) — a `legislature_chosen`
  state is a legitimate, expected structural condition, distinct from a reconciliation miss (which
  already raises upstream at the join / the D024 roster asserts).

### Dependencies

- E7-S2 (#121, the national frame it augments); `dwh.pv_state_status` (E4, shipped). The `policy`
  default is **settled at (b)** (D038); E7-S6 (#125) documents it and enumerates the affected years —
  it does not change the default.

---

### E7-S4: Flip detection + three-method margin comparison — #123

**Issue title:** Detect flips and compute three-method margins per election
**Labels:** `epic:hybrid`, `enhancement`, `priority:high`

**Body:**

### Summary

On top of the national outcomes, compute the thesis answers per election: **`pv_flip`** and
**`hybrid_flip`** (each method's winner vs. the EC baseline) and the **three-method margins** — the
top-2 percentage-point gap under EC, PV, and hybrid. This is the "would it have flipped, and by how
much" surface, and it is where the EC-determinative rule (below) is applied.

### The EC baseline and the strict-majority rule (D041 — confirming Fred's intent)

Fred: the EC determines the outcome only if the leading candidate has **"50% or more"** of the
electoral votes; if no candidate clears that bar, the EC does **not** determine the election — and
that is the hybrid's motivating case, not an error. **Written precisely, and confirming (not
overriding) that intent:** implement a **strict majority (`ec_share_full > 0.5`)**. Reasoning
recorded in D041:
- At an exact **50/50** split, "50% or more" would name **two** winners — no unique EC winner — so
  the literal "≥ 50%" is ill-defined at the boundary. A strict `> 0.5` resolves it cleanly.
- An exact tie is therefore treated as **`ec_determinative = false`** — the *same branch* as
  no-majority — not as a tie to be broken. Both are "the EC did not settle it," which is exactly the
  condition the hybrid exists to speak to.

**The majority basis is the appointed allotment — settled and constitutionally correct (D041).**
`ec_denominator` = Σ `total_electoral_votes` (each state counted once) is the **appointed** electoral
total, exactly the 12th Amendment's "majority of the whole number of Electors **appointed**," while
the numerator (`president_electoral_votes`) is the electoral votes actually **cast**. This is verified
in the code: `total_electoral_votes` is each state's allotment, not votes cast — see
`docs/corrections.md` (the 2000 DC abstention preserves `total_electoral_votes=3`, tracking the 1-vote
gap separately in `ELECTORAL_VOTE_SHORTFALLS`, with `assert_row_votes_sum_to_total` checking cast ==
total − shortfall). So 2000 is Bush **271 of 538 appointed** (270 needed), not 269 of 537 cast. The
earlier "cast vs appointed" concern was a misreading of `total_electoral_votes` and is **resolved, not
open**; D041's appointed citation stands.

**Derived requirement — EC shares sum to ≤ 1.0, never == 1.0.** Because shortfalls are real (a state's
appointed EV can exceed its cast EV), **Σ `president_electoral_votes` can be less than
`ec_denominator`**, so candidate EC shares in such a year sum to slightly under 1.0. That is correct,
not a bug: any validation must assert shares sum to **≤ 1.0**, never == 1.0. 2000 (537 cast of 538
appointed) is the pinned fixture for it (implemented in E7-S2 / #121).

### Acceptance Criteria

- Per `(year)`: `pv_flip = (pv_winner != ec_winner)`, `hybrid_flip = (hybrid_winner != ec_winner)`,
  where `ec_winner` is the **rank-1 electoral-vote leader** (`president_electoral_rank == 1`), not
  `took_office`; where a method's winner is NULL (all-NULL scores, E7-S2 NULL handling), that flip is
  **NULL**, not `false`
- **`ec_determinative`** (from E7-S2) is carried onto the per-election summary: `true` iff
  `ec_share_full(ec_winner) > 0.5`; an exact tie ⇒ `false` (same branch as no-majority), per the
  D041 reasoning above
- `ec_margin` / `pv_margin` / `hybrid_margin` are the top-2 **percentage-point** gaps in each
  method's score, over **non-NULL** scores — **percentage points only** (D037); an all-NULL year's
  margin is NULL, gracefully
- **Known splits verified:** 2000 and 2016 show `pv_flip = true` with the correct PV winner; a test
  pins these against `hybrid_preferred`
- **Contingent / no-EC-majority elections are computed *and* flagged (not withheld) — 1824.** 1824
  is `ec_determinative = false` (no EC majority) with `pv_coverage < 1.0` (partial PV), and its
  hybrid **is computed** — returning **Jackson** (the EC and PV leader) under both (b) and (c). E7
  does **not** implement the D010/D011 legal treatment of who takes office (the House chose Adams);
  it computes the hybrid and flags the two orthogonal facts

**Tests shipped with this story (D):** the flip booleans and the three percentage-point margins on
the synthetic frames, plus the 2000/2016 flip pin (the 1824-winner pin lives in E7-S2).

### Implementation Notes

- Flip/margin read only the E7-S2/S3 national frame — no state-level recomputation.
- `hybrid_margin` is derived from `hybrid_score` so it moves with the formula automatically (D037).
- 1824 is the flagship D005/D010 "authentic history is a feature" case: modeled honestly (two flags
  populated, hybrid computed), not special-cased away; the D011 legal treatment of its House
  resolution stays out of scope.

### Dependencies

- E7-S2 (#121), E7-S3 (#122)

---

### E7-S5: Materialize the two grains (`hybrid_*` + `hybrid_summary`); wire into the warehouse; guards + integration test — #124

**Issue title:** Materialize the per-candidate and per-election hybrid views and rebuild them in the warehouse
**Labels:** `epic:hybrid`, `infrastructure`, `priority:high`

**Body:**

### Summary

Expose E7's computation as warehouse views at **two grains** (OQ6, settled): a **per-candidate**
view (`hybrid_preferred` for analysis, `hybrid_redistributable` for the API) carrying the scores,
**plus** a **per-election** `hybrid_summary` companion carrying winners / `ec_determinative` /
`pv_coverage` / flips / margins — all from the one parameterized builder — and have
`usvote/warehouse.py` (re)build them as the final view step. Both grains exist because the display
layer (still undesigned, D001) will report at different grains, so carrying both is the safe
default. This is the persistence seam #102 reads, and it carries E7's structural guards + the gated
real-corpus integration test.

### Acceptance Criteria

- Per-candidate views `hybrid_preferred` / `hybrid_redistributable` and per-election
  `hybrid_summary` views (one per surface) are created from the **same builder** over the two
  resolved join views (mirroring `create_ec_pv_views`), idempotent (`CREATE OR REPLACE VIEW`)
- The per-election `hybrid_summary` carries `ec_winner` / `pv_winner` / `hybrid_winner`,
  `ec_determinative`, `pv_coverage`, `pv_flip` / `hybrid_flip`, and `ec_margin` / `pv_margin` /
  `hybrid_margin`
- `usvote/warehouse.py::rebuild_views` builds them **after** `create_ec_pv_views` (they depend on
  the join views), so a `run_warehouse` / `python -m usvote all` build leaves all hybrid views
  populated — and a `--replace` build rebuilds them (the join views are always rebuilt, D027/#84b)
- **The redistributable-leak guard is primarily STRUCTURAL, data-assert as defense in depth (E):**
  - **Primary (structural):** a test asserts the `hybrid_redistributable` definition **names
    `EC_PV_REDISTRIBUTABLE_VIEW` and never `EC_PV_PREFERRED_VIEW`** — a greppable-invariant test in
    the style of `tests/unit/test_api_import_graph.py`. This is the primary guard because a
    **data-only test can pass vacuously** (e.g. if a fixture happens to carry no non-redistributable
    row).
  - **Defense in depth (data):** a data assertion mirroring `snapshot.assert_redistributable_only`
    (`snapshot.py:132`) — run on the **input `ec_pv` frame, pre-aggregation**, because after roll-up
    to `(year, candidate)` there is **no `source`/`redistributable` column left to assert on**.
- A **fan-out guard** asserts one row per grain (per `(year, candidate)` for the per-candidate view;
  per `(year)` for `hybrid_summary`) — the analogue of `assert_no_fan_out`
- A **gated real-corpus integration test** (`@pytest.mark.integration`, skips without the live
  warehouse / UCSB corpus env, excluded from CI) exercises both grains end-to-end, re-checks the
  2000/2016 flips against real data, and confirms the affected-year set — **which years carry a
  `legislature_chosen` state (so `pv_coverage < 1.0`) against the live roster**, replacing D024 §1's
  prose "~1880" estimate with the verified set (the same set E7-S6's note reports)
- The view-name **constants** live in `usvote/hybrid.py` (as `EC_PV_*_VIEW` do in `join.py`) so
  `snapshot.py` (#102) reads them by constant, no hand-rolled SQL path
- Nothing under `usvote/{mit,ucsb,pv}/` imports `usvote.hybrid` (the D015/D027 back-import
  invariant, enforced by a test mirroring the `dwh.votes` / `usvote.warehouse` guards)

### Implementation Notes

- The two-grain split maps cleanly onto #102's snapshot tables (`ec_pv` ↔ per-candidate,
  `national_rollup` ↔ `hybrid_summary`), so the seam stays a straight materialization. Reminder for
  #102: adding those fields to the snapshot **requires bumping `SNAPSHOT_SCHEMA_VERSION`** (H) — the
  content hash does not cover roll-up shape.
- Keep `rebuild_views` the single place the ordering (`pv union → join → hybrid`) is expressed, so a
  future `views` subcommand stays a thin wrapper (the #84 follow-up `rebuild_views` was factored for).

### Dependencies

- E7-S2 (#121), E7-S3 (#122), E7-S4 (#123) (the computation the views express); E6 / #69;
  `usvote/warehouse.py` (shipped)

---

### E7-S6: Write the partial-coverage explanatory note + enumerate the affected years from the live roster — #125

**Issue title:** Write the partial-coverage explanatory note and enumerate affected years from the live roster
**Labels:** `epic:hybrid`, `research`, `documentation`, `priority:medium`

**Body:**

### Summary

The PV-denominator policy is **settled: (b)** (D038) — for partial-PV years (any `legislature_chosen`
state, e.g. 1824 and the pre-~1880 window) the hybrid averages an EC share measured over **all**
EC-casting states against a PV share measured over **only** the popular-vote states, and flags the
mismatch with `pv_coverage < 1.0`. Fred picked (b) because it "sticks more closely to the historical
record for ec … just needs an explanatory footnote." **This story writes that footnote and produces
the evidence table it rests on.** It is no longer a (b)/(c) decision spike — the decision is made.

**This is distinct from #70 (E7-S1).** #70 is the **cross-source** question (MIT vs. UCSB agreement
in the overlap). This is the **coverage-explanation** artifact for the settled (b) policy. Do not
merge them.

### Acceptance Criteria

- From the **live `dwh.pv_state_status` roster**, enumerate **every year containing a
  `legislature_chosen` state**, and for each report its `pv_coverage` **both** by state count and by
  EC votes (the EV-weighted `pv_coverage` E7 actually carries, D024 §8). This replaces D024 §1's
  prose "~1880" estimate with the verified set (the same set E7-S5's gated integration test confirms)
- Write the **explanatory note** that ships with any surface exposing a hybrid for a partial-coverage
  year. It must state plainly that under policy (b): the **PV share is measured over the states that
  held a popular vote**, while the **EC share is measured over all of them**, and that this is why
  `pv_coverage < 1.0` is carried alongside — the honest coverage caveat, not a defect. It should note
  that 1824's winner (Jackson) is invariant to the policy; only the margin would move under (c), which
  is not shipped
- The note lives under `docs/` (the story's call on the exact file); it is the artifact the display
  layer (E9 / future frontend) will cite. Mirror the existing `docs/` doc style

### Implementation Notes

- This is a `research` / `documentation` story, smaller than the original spike — no (b)/(c)
  compute-both-ways is required (the pick is made). The one computed output is the affected-year /
  `pv_coverage` table off the live roster.
- Reuse the `pv_coverage` derivation from `usvote/hybrid.py` (E7-S3) rather than re-deriving it, so
  the note's numbers and the shipped column agree by construction.

### Dependencies

- E7-S3 (#122, the `pv_coverage` derivation the table reads); `dwh.pv_state_status` (E4, shipped).
  Informs the display layer; does not code-block the rest of E7.

---

## Decisions recorded this round (D037–D041 — in `decisions.md`)

These are **recorded in [`decisions.md`](decisions.md)** as D037–D041 (2026-07-28), approved by Fred
at the review. Summaries retained here for backlog readability; `decisions.md` is authoritative. D036
was the highest previously recorded.

- **D037 — The hybrid is the average of a candidate's EC-votes share and national-popular-vote share;
  highest average wins.** `hybrid_score = (ec_share_hybrid + pv_share) / 2`. The EC share is
  **split**: `ec_share_full` (policy-invariant, the only input to `ec_determinative`) and
  `ec_share_hybrid` (policy-selected, feeds the hybrid only). Pure computation over the resolved EC↔PV
  join views plus the `dwh.pv_state_status` roster, parameterized by view (`usvote/hybrid.py`, sibling
  of `join.py`, EC-domain): `hybrid_preferred` (analysis) and `hybrid_redistributable` (API, MIT-only)
  — the "two views, one builder" shape of D026. **Intent (Fred):** circumvent the House choosing when
  no candidate wins an EC majority. Margins are **percentage-point** top-2 gaps only. Deliverable is
  computed data + validated logic, not charts (D001). **Roll-up ownership (OQ4, resolved):** the
  national-aggregation primitive is extracted into `usvote/hybrid.py` and `snapshot.build_national_rollup`
  calls it; the two roll-up **tables** stay separate for MVP (D029).
- **D038 — The hybrid is computed for every in-scope year and flagged with `pv_coverage`; denominator
  policy (b) is settled.** Rule (a) (withhold on any `legislature_chosen` year) is **rejected** — it
  would suppress the House-contingent, no-EC-majority elections (incl. **1824**) the hybrid exists to
  speak to. The denominator policy is **settled: (b)** (Fred, 2026-07-28: *"Simpler and sticks more
  closely to the historical record for ec … just needs an explanatory footnote"*) — compute with
  mismatched denominators, flagged by `pv_coverage < 1.0`. Rule (c) is **not shipped**;
  `apply_coverage_policy` keeps it a swappable one-line policy at zero cost. **1824 (verified):**
  Jackson led both the EC (99 of 261 cast, 131 needed) and the PV (~151k vs ~113k) with a majority of
  neither; the House elected Adams. The hybrid returns **Jackson** under both (b) and (c), so the pick
  moves the **margin, not the winner** (1824 → Jackson pinned as a fixture). `ec_determinative` and
  `pv_coverage` are **orthogonal** (both populated for 1824). Extends D005/D024.
- **D039 — The #102 read seam is `hybrid_redistributable` (+ `hybrid_summary`), materialized by
  `usvote/snapshot.py`, rebuilt by `warehouse.rebuild_views`.** The redistributable hybrid views wrap
  the independently defined redistributable join view, so no UCSB-derived number can reach the public
  surface (extends D030); the PV-denominator policy degrades to identity on it, so
  `hybrid_redistributable` is policy-invariant and #102 is unblocked regardless of any (b)/(c) pick.
  #102's AC is amended to name this seam, to make `build_national_rollup` a **reader** of E7's
  single-sourced national derivation, and — critically — to **bump `SNAPSHOT_SCHEMA_VERSION`**
  (`snapshot_schema.py:21`): the content hash covers only the `ec_pv` data rows, so a roll-up/shape
  change is invisible to it and the version must be moved manually. The E9 mart may later slot in
  behind the same seam but is not a dependency.
- **D040 — #70 is folded into E7, re-labeled in place (`epic:hybrid`).** Reframed as E7's empirical
  trust prerequisite — feeding the margin/flip benign-seam caveat and an optional cross-source
  tolerance guard — rather than "the E6 join design" (now shipped). Number + AC retained; body's
  epic link repointed to #120. Distinct from the E7-S6 denominator note (cross-source vs.
  coverage/denominator).
- **D041 — The EC is determinative only on a strict majority of the appointed electoral allotment
  (`ec_share_full > 0.5`); otherwise the election is `ec_determinative = false`, the hybrid's
  motivating case.** Confirms (does not override) Fred's "50% or more": strict `> 0.5` because an
  exact 50/50 split yields no unique winner. An exact tie is the **same branch** as no-majority.
  `ec_determinative` reads **only** `ec_share_full` (policy-invariant). **The majority basis is the
  appointed allotment (settled, constitutionally correct):** `ec_denominator` = Σ `total_electoral_votes`
  (each state once) is the **appointed** total — exactly the 12th Amendment's "majority of the whole
  number of Electors **appointed**" — while the numerator (`president_electoral_votes`) is votes
  **cast**. Verified in code (`docs/corrections.md`: 2000 DC abstention preserves `total_electoral_votes=3`,
  gap tracked in `ELECTORAL_VOTE_SHORTFALLS`; `assert_row_votes_sum_to_total` checks cast == total −
  shortfall). So 2000 is Bush **271 of 538 appointed** (270 needed), not 269 of 537 cast. **Consequence:**
  candidate EC shares sum to **≤ 1.0** (never == 1.0), validated with 2000 pinned as the fixture. The
  earlier "cast vs appointed" concern was a misreading of `total_electoral_votes` and is resolved, not
  open. Contingent / no-majority elections (1824) are flagged and computed; the who-takes-office legal
  treatment stays in the D010/D011 future workstream.

## Open questions

**None — all resolved at the 2026-07-28 review** (see the "Resolved at review" note at the top). For
the record:

1. **PV-denominator basis (b) vs (c) — SETTLED: (b)** (Fred, 2026-07-28; D038). (c) stays swappable
   at zero cost but is not shipped.
2. **EC-majority basis — SETTLED: appointed allotment** (Fred, 2026-07-28; D041). The "cast vs
   appointed" item was a misreading of `total_electoral_votes` and is corrected — the denominator is
   already the appointed allotment, the constitutionally correct 12th-Amendment basis.
3. **UCSB-absent warehouse — SETTLED: accept the NULLs** (Fred, 2026-07-28; E7-S2). `hybrid_preferred`
   is honestly 1976-only until UCSB loads; revisitable once the display layer has an opinion.
