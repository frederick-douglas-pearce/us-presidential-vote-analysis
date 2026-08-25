# Research: MIT vs. UCSB Popular-Vote Agreement Across the 1976–2024 Overlap

> **Status: COMPLETE.** This is the E7-S1 (issue #70) research deliverable. It measures how far
> apart the two popular-vote sources actually are where both cover the same election, calibrates the
> **D017 layer-3 overlap tolerance** (which had no implementation), and returns a verdict on D017's
> **benign-seam assumption** — the premise that `pv_preferred`'s source switch at 1976 introduces no
> methodological step. That premise is what every cross-1976 E7 output rests on, including the
> shipped `hybrid_*` views.

**Date:** 2026-08-22 · **Grain:** `(year, state, candidate)`, 1976–2024 · **Sources read:**
`dwh.pv_redistributable` (MIT, CC0) and `dwh.pv_ucsb` (UCSB, analysis-only) — the two D017
single-source views, differenced directly. No re-extract.

---

## 1. Recommendation

**The benign-seam assumption is CONFIRMED, on a pre-stated bar, with one named caveat.**

1. **The sources agree on the outcome in every overlap year.** The national popular-vote **winner is
   identical under both sources in all 13 of 13 years**. `pv_flip` — a headline E7 output, added in #123 and materialized
   by D050 — is therefore source-invariant across the entire overlap.
2. **They agree on the margin to well inside what could matter.** The largest cross-source
   disagreement in the national margin is **0.034 percentage points**, against a smallest actual
   margin of **0.511 pp** (2000). The worst-case source effect is **~15× smaller** than the closest
   real election in the window, and no margin comes near crossing zero. Margins are computed on
   each source's **provided** state-total denominator, as D017 requires — see §5.2.
3. **At the raw cell grain they agree exactly 93.4% of the time**, and where they differ the
   difference is small and *structured* — concentrated in whole state-years, and almost always
   accompanied by a difference in that state's provided total rather than scattering randomly
   across candidates.

**Recommended D017 layer-3 tolerance — a three-part rule, not one number** (§6). A single relative
ceiling was rejected: with 93.4% of cells *exactly* equal, the failure that matters is not one blown
cell but many cells drifting slightly, which any per-cell ceiling would pass.

**The caveat that survives a confirming result** (§7): this measures UCSB *within* the overlap and
uses it to license a claim about UCSB *before* it. That inference holds only if UCSB is
methodologically stationary across its own span. Nothing here can discharge that — it is the
residual assumption, and it should be stated wherever a cross-1976 trend is published.

---

## 2. What could and could not be published, and why

**This section is load-bearing, not boilerplate.** MIT is CC0 and already public; UCSB is
`redistributable=false` (D016) and this repository is public, where committing UCSB content **is**
redistribution and is effectively irreversible (**D022**; D030 sets the related
redistributable-only rule for the API surface). The bite is algebraic:

> **`UCSB = MIT − delta`.** An exact per-cell delta printed beside the public MIT value is a
> *lossless re-encoding of the UCSB integer*. A "delta" does not launder the source.

**What the rule is actually protecting, stated precisely.** UCSB's data is **publicly viewable** —
anyone can read it on the American Presidency Project site. It is not secret; it is *not
redistributable*. So the harm this rule guards against is **republication**, and the unit that
matters is the **individual `(year, state, candidate)` popular-vote record**. Aggregate and
distributional statistics over hundreds of such records are not republication of anybody's data and
are published here freely. The test applied throughout is therefore: *does this figure let a reader
reconstruct an individual record they would otherwise have to get from UCSB?* — not "is this figure
derived from UCSB at all", which would forbid the finding itself.

So this document publishes **population statistics, keys, and bucketed magnitude bands**, and
withholds anything from which a single UCSB value could be recovered. Issue #70's AC-3 ("cells …
listed with provenance") is met in substance — a reader learns exactly *which* cells are
unreliable and roughly how badly — and the narrowing is **recorded as an explicit amendment on
issue #70** rather than applied silently.

| Published here | Withheld |
|---|---|
| Counts, rates, and unattributed relative-delta percentiles | Any exact per-cell delta, absolute or relative |
| Divergent-cell **keys** with a **bucketed** band | Any absolute vote magnitude attached to a cell |
| Cross-source agreement rates on provided state totals | **UCSB's provided `state_total_votes`**, and any per-`(year, state)` provided-vs-resum gap |
| National roll-up agreement rates, relative only | National per-candidate UCSB totals |
| Normalized margins and winners (see below) | — |

**Three rules make this coherent rather than arbitrary:**

- **Equality with a public value is publishable.** "1239 of 1326 cells are exactly equal" lets a
  reader conclude `UCSB = MIT` for those cells — and that is fine, because the number is *already
  public by construction*. It is also the deliverable's entire point: D017 §3 calls this agreement
  the "empirical justification". Without this carve-out a literal reading of the rule would forbid
  the agreement rate itself, and no such document could exist.

  **Stated plainly rather than left implicit:** §3's two `100.00%` rows (1988 and 2012) go further
  than the aggregate — they identify **204 specific cells** as equal to their public MIT values.
  That is the largest individual-record identification in this document. It is accepted under this
  same carve-out, and the reason is the one above: those 204 integers are already public under CC0,
  so what transfers is UCSB's *agreement*, not its content.
- **A band needs an absolute floor.** Votes are integers, so a `<0.1%` band on a ~5,000-vote cell
  implies ±5 votes — a near-pin, not a bound. Where a band's implied interval (`MIT × band ceiling`)
  falls under 500 votes the cell is reported with **no band at all**, only as a divergence. **20 of
  the 87 divergent cells are reported that way**, and §3's table carries them in an explicit
  `withheld` column rather than silently folding them into a band. Absolute magnitude and relative
  band are never published for the same cell. The rule governs *UCSB-derived* magnitudes: MIT's own
  integers are CC0 and appear where one is needed to explain a threshold, as in the script's
  commentary on the floor.
- **A normalized margin does not reconstruct an individual record.** A national margin is one ratio
  in three unknowns (two candidate totals and a denominator), so no *state or candidate* value falls
  out of it. It is **not** an absolute claim that no integer is recoverable: where §5.3 reports a
  year exact, two unknowns are supplied and the year's national **denominator** does solve — a
  51-state aggregate, which is acceptable under the rule above, but worth stating precisely rather
  than overclaiming. This is the same
  property D017 relies on when it says ratios cancel the source — which is precisely why the
  decisive test in **§5.1–§5.2** can be published in full while §3's cell-level detail cannot. It
  does **not** extend to §5.3, whose roll-up figures are counts rather than ratios — see the note
  there.

**Two tightenings beyond the above, applied for the same reason.** §3.1 names seven cells, and in
three years exactly one of them is the year's only `>1%` cell — so a statistic that identifies *the
single most extreme cell* is attributable by inspection, and from an attributed relative delta
`UCSB = MIT / (1 ± rel)` recovers the integer. Therefore **neither the maximum absolute delta nor
the maximum relative delta is reported**, and the p99 is dropped with them; the tail is described by
**counts above thresholds** (§3), which bound the extreme without locating it. This is stricter than
a band and costs nothing #167 needs.

**The relative-delta basis, stated because the measure is asymmetric:** every `relpct` in this
document is `|MIT − UCSB| ÷ UCSB × 100` — UCSB is the denominator. #167 must implement its gate
against that definition.

**Reproducibility is preserved.** Every withheld number is regenerable by anyone holding the UCSB
snapshot: the query script ships beside this document as
[`research-pv-overlap.sql`](research-pv-overlap.sql) and §8 gives the full build recipe. If UCSB
ever grants redistribution — a one-row `pv_source` edit under D017 — this constraint dissolves and
the withheld figures
become publishable.

---

## 3. Cell-grain agreement (AC-2a)

Joined **FULL OUTER** on the canonical `(year, state, candidate)`, so an unmatched row on either
side would surface as a finding rather than vanish — the inner-join silent-drop hazard, where an
unmatched row disappears without any sum-based validator noticing:

| Measure | Value |
|---|---|
| Matched pairs in 1976–2024 | **1326** |
| Rows present in MIT but not UCSB | **0** |
| Rows present in UCSB but not MIT | **0** |
| Cells **exactly equal** | **1239 (93.44%)** |
| Cells divergent | **87 (6.56%)** |

The zero-drop is **measured, not assumed** — the reconcile stages (`reconcile_mit` #67,
`reconcile_ucsb` #38) land both sources on identical canonical keys with no residue in either
direction.

**Relative-delta percentiles.** The basis matters and is stated, because the two differ by orders of
magnitude and an unlabeled percentile would be uninterpretable:

| Basis | p50 | p90 |
|---|---|---|
| Divergent cells only (n=87) | 0.016% | 0.699% |
| All cells (n=1326) | 0.000% | 0.000% |

**The tail, as counts rather than as an extreme value** (per §2's second tightening):

| Divergent cells above… | 1% | 2% | 5% | 10% |
|---|---|---|---|---|
| count (of 87) | **7** | **2** | **1** | **0** |

**Divergent cells by year and band.** Bands are `<0.1%`, `0.1–1%`, `>1%`; the absolute floor of §2
applies within each.

| Year | `<0.1%` | `0.1–1%` | `>1%` | band withheld (floor) | divergent | year exact-match |
|---|---|---|---|---|---|---|
| 1976 | 4 | 4 | 2 | 6 | 16 | 84.31% |
| 1980 | 4 | 6 | 0 | 2 | 12 | 88.24% |
| 1984 | 1 | 0 | 1 | 2 | 4 | 96.08% |
| 1988 | 0 | 0 | 0 | 0 | 0 | 100.00% |
| 1992 | 3 | 0 | 1 | 0 | 4 | 96.08% |
| 1996 | 9 | 0 | 0 | 2 | 11 | 89.22% |
| 2000 | 4 | 2 | 0 | 0 | 6 | 94.12% |
| 2004 | 3 | 0 | 1 | 2 | 6 | 94.12% |
| 2008 | 4 | 4 | 0 | 0 | 8 | 92.16% |
| 2012 | 0 | 0 | 0 | 0 | 0 | 100.00% |
| 2016 | 7 | 0 | 2 | 4 | 13 | 87.25% |
| 2020 | 3 | 0 | 0 | 2 | 5 | 95.10% |
| 2024 | 2 | 0 | 0 | 0 | 2 | 98.04% |

Totals: **44** in `<0.1%`, **16** in `0.1–1%`, **7** in `>1%`, **20** with the band withheld under
the §2 floor — 87 divergent cells in all. *(This table is an assembly: the band columns come from the
script's query 3, the exact-match column from query 3b, and 1988/2012 appear as explicit zero rows
because query 3 groups only over divergent cells and so emits nothing for them.)*

### 3.1 The D005 reliability list (AC-3)

Seven cells exceed 1%. Listed by key and band only:

| Year | State | Candidate | Party | Band |
|---|---|---|---|---|
| 1976 | Vermont | Gerald R. Ford | `REPUBLICAN` | `>1%` |
| 1976 | Vermont | Jimmy Carter | `DEMOCRAT` | `>1%` |
| 1984 | Washington | Walter F. Mondale | `DEMOCRAT` | `>1%` |
| 1992 | South Carolina | William J. Clinton | `DEMOCRAT` | `>1%` |
| 2004 | Mississippi | George W. Bush | `REPUBLICAN` | `>1%` |
| 2016 | New York | Donald J. Trump | `REPUBLICAN` | `>1%` |
| 2016 | New York | Hillary Clinton | `DEMOCRAT` | `>1%` |

*Party is printed as the source stores it (MIT's uppercase spelling), not normalized — D050 records
that MIT and UCSB spell one party two ways.*

**All five state-years in this list also have differing provided state totals** — see §4.

---

## 4. Is the disagreement systematic? (AC-4)

**Yes, on two independent signals — it is not random noise.**

**(a) Divergence is paired within a state-year.** The 87 divergent cells sit in only **52 distinct
state-years** out of 663:

| Candidates diverging in a state-year | State-years |
|---|---|
| 0 | 611 |
| 1 | 17 |
| **2 (both)** | **35** |

If divergence were independent per candidate at the observed 6.6% rate, both-candidate state-years
would be rare. Instead they are the **majority of affected state-years**, which points at a
state-level cause — a revised or re-certified canvass that moves the whole state's tally — rather
than per-candidate transcription noise.

**(b) It tracks the provided state total.** Comparing each source's **provided
`state_total_votes`** for the same `(year, state)`:

| Measure | Value |
|---|---|
| State-years compared | 663 |
| Provided totals identical | **454 (68.48%)** |
| p95 relative difference | 0.778% |
| state-years at or above 1% / 2% / 3% | 28 / 11 / 2 |

**The relationship runs in one direction only** — the tempting reading, that a cell difference and
a denominator difference are the same event seen twice, is contradicted by the data. The 2×2 over
all 663 state-years:

| | provided totals identical | provided totals differ |
|---|---|---|
| **no divergent cell** | 452 | **159** |
| **≥1 divergent cell** | 2 | 50 |

So: **a divergent cell almost always sits in a state-year whose provided totals also differ (50 of
52)** — that direction is strong and is what the `>1%` list in §3.1 reflects. The converse fails
badly: **159 of the 209 state-years with differing provided totals (76%) carry no divergent
candidate cell at all.** A differing total is the common case; a differing candidate cell is the
rare one.

That asymmetry is itself informative, and §4.1 uses it.

### 4.1 The "other/write-in" question cannot be partitioned by candidate — but it *can* be measured

D017's benign-seam caveat names other/write-in handling as a failure mode. **No partition of the
divergent cells by candidate type is possible**, because the minor-candidate rows are not in the
population: across the whole overlap there are **exactly 2 candidates in every one of the 663
state-years** — 18 distinct candidates, 2 distinct parties. The script's query 4b checks this
directly (min and max candidates per state-year are both 2).

Two different mechanisms produce that, and they are worth naming separately because they are not
equally robust:

- **UCSB** is scoped against the EC getters: `usvote/ucsb/pipeline.py` calls
  `read_ec_getters` (defined in `usvote/spine.py`) and injects the frame across a DI seam, where
  `reconcile.py`'s curated `UCSB_CANDIDATE_RECONCILIATIONS` map does the rewriting and scoping and
  `_assert_getter_completeness` checks the result — a literal D007 scope.
- **MIT** is scoped by the **D019 party proxy**, `EC_GETTER_PARTIES = {"DEMOCRAT", "REPUBLICAN"}`
  (`src/usvote/mit/transform.py:74`), applied by `_filter_ec_getters`. The MIT file carries no rows
  at all for 2016's faithless-elector recipients, so nothing is in fact excluded there — but the
  filter tests **party only**, with no write-in predicate, so a named write-in coded `DEMOCRAT`
  would enter under the proxy where a name match would reject it.

A future MIT release coding a named write-in line as `DEMOCRAT` would change the population under
the proxy and not under the name match — so the "exactly 2" property is a current fact, not a
structural guarantee.

**But the question is still measurable, on the evidence §4(b) just produced.** The 159 state-years
where the two major-candidate cells are *identical* while the **provided state totals differ** are
precisely a measurement of the sources disagreeing about everybody else — that is the only thing
left that can move the total when the retained candidates match. That population is 24% of all
state-years. Strictly it is "everything not in the two retained cells" — which also absorbs MIT's
ballot-disposition rows (`UNDERVOTES` / `OVERVOTES` / `VOID`), so it is slightly broader than
other/write-in candidates as such; the formal definition below is the exact one.

Quantified as the **residual** between each source's provided total and the sum of its own retained
candidates — which is why `pv/validate.py::assert_totals_not_exceeded` asserts `<=` and not `==`:

| Measure | Value |
|---|---|
| MIT mean residual | 4.974% |
| UCSB mean residual | 4.922% |
| **Mean absolute *paired* difference** (per state-year) | **0.104 pp** |
| p95 of the paired difference | 0.755 pp |
| state-years at or above 1 / 2 / 3 pp | 25 / 4 / 1 |

**The paired figure is the honest one and it is not the difference of the two means.** Comparing
`4.974 − 4.922 = 0.05` would let opposite-signed per-state differences cancel; computed per
state-year and then averaged, the two sources' "everybody else" coverage differs by **0.104 pp on
average**, with only 4 state-years past 2 pp. That is small — and it is twice the number an
unpaired comparison would have suggested.

---

## 5. The decisive test: are E7's normalized metrics source-invariant? (AC-5b)

D017 blesses two normalized quantities — **flip booleans** and **margin percentages** — on the
grounds that ratios cancel the source. Those are exactly what E7 publishes, so they are what the
benign-seam verdict must be read off.

**The bar was stated before the numbers were read.** *Confirms* iff: (i) the national PV winner is
identical under both sources in every overlap year, (ii) no margin crosses zero, and (iii) the
maximum cross-source margin difference is smaller than the smallest actual PV margin in the window.

### 5.1 Winner agreement — 13 of 13

| Years compared | Winner identical | Winner differs |
|---|---|---|
| 13 | **13** | **0** |

### 5.2 National margin, per source, in percentage points (AC-5b)

**The denominator is each source's own provided state total**, summed over states —
`Σ_states max(state_total_votes)`, which is exactly what `usvote/hybrid.py::roll_up_national`
computes as `national_pv_denominator` and what `pv_margin` is derived from. D017 requires this and
forbids the alternative: re-summing candidate rows "would make margins sensitive to each source's
minor-candidate coverage — D007 scopes candidates to EC-getters, so re-summing would systematically
differ between sources." So these figures are directly comparable with the shipped
`hybrid_summary_preferred.pv_margin`, which is the whole point of the test.

| Year | MIT margin (pp) | UCSB margin (pp) | difference (pp) |
|---|---|---|---|
| 1976 | 2.0589 | 2.0636 | 0.0047 |
| 1980 | 9.7319 | 9.7329 | 0.0009 |
| 1984 | 18.2256 | 18.2163 | 0.0094 |
| 1988 | 7.7271 | 7.7264 | 0.0007 |
| 1992 | 5.5932 | 5.5594 | **0.0337** |
| 1996 | 8.5107 | 8.5208 | 0.0101 |
| 2000 | **0.5113** | 0.5097 | 0.0016 |
| 2004 | 2.4522 | 2.4630 | 0.0109 |
| 2008 | 7.2670 | 7.2534 | 0.0136 |
| 2012 | 3.8466 | 3.8488 | 0.0022 |
| 2016 | 2.0971 | 2.0774 | 0.0196 |
| 2020 | 4.4489 | 4.4527 | 0.0038 |
| 2024 | 1.4703 | 1.4719 | 0.0016 |

*Each column is rounded independently from full precision, so subtracting the two printed margins
can differ from the printed difference in the last digit; the difference column is the authoritative
one.*

**Verdict against the bar:** (i) 13/13 winners agree ✓. (ii) Every margin is positive under both
sources; none approaches zero ✓. (iii) Max difference **0.0337 pp** (1992) vs. smallest actual
margin **0.5113 pp** (2000) — the source effect is **15.2× smaller** than the closest election in
the window ✓. **All three clauses met → CONFIRMED.**

### 5.3 National roll-up per election (AC-2b)

Per-candidate national totals from each source, differenced. Reported as **counts by band**, with
no per-year extreme value — see the note below, which is the reason this table looks coarser than
§3's.

| Year | candidates | exact | >0 but <0.05% | ≥0.05% |
|---|---|---|---|---|
| 1976 | 2 | 0 | 2 | 0 |
| 1980 | 2 | 0 | 2 | 0 |
| 1984 | 2 | 0 | 2 | 0 |
| 1988 | 2 | **2** | 0 | 0 |
| 1992 | 2 | 0 | 1 | 1 |
| 1996 | 2 | 0 | 2 | 0 |
| 2000 | 2 | 0 | 2 | 0 |
| 2004 | 2 | 0 | 2 | 0 |
| 2008 | 2 | 0 | 1 | 1 |
| 2012 | 2 | **2** | 0 | 0 |
| 2016 | 2 | 0 | 1 | 1 |
| 2020 | 2 | 0 | 2 | 0 |
| 2024 | 2 | 0 | 2 | 0 |

Across all 26 rows: **4 exact**, **3 at or above 0.05%**, **1 at or above 0.10%**, and **none at or
above 0.15%**.

Only **4 of 26** rows agree exactly — and they are 1988 and 2012, the two years with no divergent
cell at all, which is the expected internal cross-check. Elsewhere small per-cell differences
**accumulate rather than cancel** when summed, but the disagreement stays under 0.15% everywhere.
This is exactly the asymmetry D017 predicts: a raw national *count* series is the fragile reading,
a normalized margin is not.

> **Why this table publishes no per-year maximum.** An earlier version carried a per-year `worst`
> relative deviation to four decimal places, and it was a **reconstruction vector**, caught in
> review. MIT's nationals are CC0 *and exactly reproducible from the recipe in §8*, so
> `UCSB_national = MIT_national / (1 ± worst/100)` inverts a 4-dp relative figure to within a few
> tens of votes; the sign ambiguity is one bit against seven significant figures, not a defence.
>
> **The national totals are not what made it disqualifying** — by the rule above, an aggregate over
> 51 states is not republication of anybody's record. What made it disqualifying is that it
> **chained down to individual records**: combined with §3.1's named keys, the recovered national
> delta narrowed four of those seven `(year, state, candidate)` cells to between 4 and 261 votes,
> against a band mechanism engineered to leave an interval 9–18% wide. That is the individual-record
> disclosure this document exists to avoid, arrived at by combining two figures each of which looked
> harmless alone — the same indirect shape as the #125 finding, whose fix is recorded in the
> provenance section of [`docs/pv-coverage.md`](../../docs/pv-coverage.md).
>
> Threshold counts bound the tail without locating it. The AC-2b finding is unaffected: "only 4 of
> 26 rows agree exactly, and differences accumulate rather than cancel" is what the criterion asks
> for.

## 6. Recommended tolerance for the D017 layer-3 gate (AC-5a)

**Three parts, at three grains.** A single relative ceiling is the wrong instrument here: with 93.4%
of cells exactly equal, a methodological step that nudged many cells slightly could keep every cell
under any sane ceiling while the exact-match rate collapsed — and that regression is precisely what
D017 §3 exists to detect.

| # | Gate | Grain | Recommended threshold | Observed today | Catches |
|---|---|---|---|---|---|
| 1 | **Exact-match-rate floor** | cell | **≥ 90% overall**, and **≥ 80% in any single year** | 93.44% overall; worst year 84.31% (1976) | many cells drifting slightly — a methodology step |
| 2 | **Per-cell relative ceiling** | cell | **flag at 1%** (→ D005 list), **fail at 15%** | 7 cells flag; 2 above 2%, 1 above 5%, **none above 10%** | one blown cell — a parse or unit regression |
| 3 | **Margin difference** | national, in **pp** | **≤ 0.25 pp** | max **0.0337 pp** | the grain E7's published outputs actually depend on |

**Notes that make these auditable rather than arbitrary:**

- **The D017 layer-3 gate runs at the cell grain** (#1 and #2). #3 is the E7 trustworthiness check
  and belongs with the hybrid computation, not with the PV union.
- **Threshold #2's fail level has deliberate headroom.** No divergent cell exceeds 10% today, and
  one exceeds 5%, so a 10% line would sit close enough to live data to redden on an ordinary canvass
  revision. 15% still catches an order-of-magnitude error, which is what a hard fail should be for.
  (The exact observed maximum is deliberately not printed — §2's second tightening.)
- **Threshold #1's floors carry headroom too, and less of it.** The 80% per-year floor sits 4.3
  points under 1976's observed 84.31%, which is the tightest margin in this table — a single
  state-year canvass revision in a bad year could approach it. That is a deliberate choice: the
  per-year floor is the instrument for exactly the localized regression that would move one year,
  so slack defeats it. Expect it to be the first threshold to need review.
- **Threshold #3 is stated in percentage points, not as a ratio**, because that is the unit the
  claim is made in. 0.25 pp sits ~2× below the smallest margin *in this window* (0.5113 pp), so
  within the measured range a passing gate leaves no margin close enough to flip. It is **not** a
  guarantee on unseen data: a future election decided by 0.2 pp would pass this gate and could still
  be source-sensitive.
- **The roll-up grain is deliberately not gated.** Every roll-up row lands under 0.15% (§5.3), which
  is tighter than the cell grain, so #1 and #2 dominate it; adding a fourth threshold would fire only
  where one of those already had.

---

## 7. What this does and does not license

**Licensed.** Reading `pv_preferred` across the 1976 seam for **normalized per-election metrics** —
flip booleans and margin percentages, which is what `hybrid_summary_preferred` publishes
(`hybrid_preferred`, the per-candidate view, carries the shares and scores but no flip or margin
column) — computed on the same provided-total denominator this study used (§5.2), so the comparison
is like-for-like. Within the overlap the source choice changes no
winner and moves no margin by as much as 0.034 pp.

**Not licensed, and the caveat is unchanged by this finding:**

- **A raw national PV *count* series read across the seam.** §5.3's roll-up figures show counts
  disagree far more readily than ratios do (only 4 of 26 exact). D017 already said this; the
  measurement confirms it rather than relaxing it.
- **The stationarity assumption.** This study measures MIT-vs-UCSB agreement *inside* 1976–2024 and
  uses it to license reading UCSB *before* 1976. That inference requires UCSB's pre-1976 methodology
  to match its post-1976 methodology — a property no in-overlap measurement can establish, because
  MIT does not reach back to test it against. **A confirming result here does not discharge it.**
  State it wherever a cross-1976 trend is published.
- **Any claim that 1976–2024 agreement implies pre-1976 *accuracy*.** Agreement is consistency
  between two modern sources, not correctness of a 19th-century tally.

---

## 8. Reproducing this

**The query script is committed beside this document** as
[`research-pv-overlap.sql`](research-pv-overlap.sql). It contains no UCSB values — only the queries
that derive aggregates from them — so it ships with the finding rather than living where a reader
cannot reach it. It emits the tables of §3, §4, §5.1, §5.2 and §5.3, though **not in document order** (§5.3's query
precedes §5.1's, and §4 reads its four queries out of sequence). A few published figures are
**assembled from more than one query rather than printed by any single one**: the percentile table's
*all-cells* row (query 2 with its divergence filter dropped), §3's band table (queries 3 and 3b plus
the two implied zero rows), and §6's whole "Observed today" column.

```bash
docker run -d --name usvote-70 -e POSTGRES_PASSWORD=itest -e POSTGRES_DB=elections \
  -p 5436:5432 postgres:16
until docker exec usvote-70 pg_isready -U postgres -d elections >/dev/null 2>&1; do sleep 1; done

D=~/Documents/Projects/data/presidential_vote_analysis
SHP=~/Documents/Projects/data/Maps/State_Shapes/tl_2019_us_state/tl_2019_us_state.shp
PGHOST=localhost PGPORT=5436 PGUSER=postgres PGPASSWORD=itest PGDATABASE=elections \
USVOTE_EC_HTML_DIR="$D/ec_raw" USVOTE_MIT_CSV_PATH="$D/1976-2024-president.csv" \
USVOTE_SHAPEFILE_PATH="$SHP" USVOTE_UCSB_HTML_DIR="$D/ucsb_raw" \
  uv run python -m usvote all

PGPASSWORD=itest psql -h localhost -p 5436 -U postgres -d elections \
  -q -f .claude/specs/research-pv-overlap.sql
docker rm -f usvote-70
```

The build used here loaded EC 5755 rows, MIT 1326 PV rows, UCSB 4626 PV rows. **UCSB is required**
— without `USVOTE_UCSB_HTML_DIR` the warehouse builds EC + MIT only and this comparison has no
second source. The snapshot is non-redistributable and lives outside the repository (D022), so this
is a local-only reproduction and **never runs in CI**.

---

## 9. Follow-ups this finding hands off

- **Implement the §6 gate.** D017 layer 3 currently has no implementation — no tolerance value and
  no overlap-validation check exists in `src/` or `tests/`. Filed as **#167**; deliberately **not**
  built here, since gating on a freshly-derived, untested number is premature.
- **Amend D017 layer 3** with the §6 thresholds, as a new decision-log entry (`decisions.md` is
  append-only, so this is a human-authorized act, not a side effect of this spike).
- **The E7 caveat is cross-referenced from [`docs/pv-coverage.md`](../../docs/pv-coverage.md)**, the
  companion doc E7 consumers actually read — a finding that lived only here would reach nobody
  looking at the hybrid surface.
