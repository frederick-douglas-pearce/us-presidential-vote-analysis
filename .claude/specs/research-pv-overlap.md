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
   identical under both sources in all 13 of 13 years**. `pv_flip` — a headline E7 output (D037) — is
   therefore source-invariant across the entire overlap.
2. **They agree on the margin to well inside what could matter.** The largest cross-source
   disagreement in the national margin is **0.05 percentage points**, against a smallest actual
   margin of **0.53 pp** (2000). The worst-case source effect is ~10× smaller than the closest real
   election in the window, and no margin comes near crossing zero.
3. **At the raw cell grain they agree exactly 93.4% of the time**, and where they differ the
   difference is small and *structured* — concentrated in whole state-years, and tracking each
   source's provided state total rather than scattering randomly across candidates.

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
redistribution and is effectively irreversible (D022, D030). The bite is algebraic:

> **`UCSB = MIT − delta`.** An exact per-cell delta printed beside the public MIT value is a
> *lossless re-encoding of the UCSB integer*. A "delta" does not launder the source.

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
- **A band needs an absolute floor.** Votes are integers, so a `<0.1%` band on a ~5,000-vote cell
  implies ±5 votes — a near-pin, not a bound. Where a band's implied interval falls under ~500
  votes the cell is reported as a bare **diverges / magnitude withheld** flag. **20 of the 87
  divergent cells are reported that way.** Absolute magnitude and relative band are never published
  for the same cell.
- **A normalized margin is not reconstructive.** A national margin is one ratio in three unknowns
  (two candidate totals and a denominator); no integer is recoverable from it. This is the same
  property D017 relies on when it says ratios cancel the source — which is precisely why the
  decisive test in §5 can be published in full while §3's cell-level detail cannot.

One tightening beyond the above: the maximum *absolute* delta is **not** reported even unattributed,
because §3 also publishes the keys of the largest-band cells and the two could be matched by
inspection. Only relative statistics appear.

**Reproducibility is preserved.** Every withheld number is regenerable by anyone holding the UCSB
snapshot: the query script is `.claude/loop/epic-hybrid/issue-70.analysis.sql` (git-ignored with the
rest of the ledger) and §8 gives the full build recipe. If UCSB ever grants redistribution — a
one-row `pv_source` edit under D017 — this entire constraint dissolves and the withheld figures
become publishable.

---

## 3. Cell-grain agreement (AC-2a)

Joined **FULL OUTER** on the canonical `(year, state, candidate)`, so an unmatched row on either
side would surface as a finding rather than vanish ([[inner-join-silent-drop]]):

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

| Basis | p90 | p95 | p99 | max |
|---|---|---|---|---|
| Divergent cells only (n=87) | 0.699% | 1.347% | 4.696% | 9.593% |
| All cells (n=1326) | 0.000% | 0.002% | 0.276% | 9.593% |

**Divergent cells by year and band.** Bands are `<0.1%`, `0.1–1%`, `>1%`; the absolute floor of §2
applies within each.

| Year | `<0.1%` | `0.1–1%` | `>1%` | total | year exact-match |
|---|---|---|---|---|---|
| 1976 | 10 | 4 | 2 | 16 | 84.31% |
| 1980 | 5 | 7 | 0 | 12 | 88.24% |
| 1984 | 3 | 0 | 1 | 4 | 96.08% |
| 1988 | 0 | 0 | 0 | 0 | 100.00% |
| 1992 | 3 | 0 | 1 | 4 | 96.08% |
| 1996 | 11 | 0 | 0 | 11 | 89.22% |
| 2000 | 4 | 2 | 0 | 6 | 94.12% |
| 2004 | 5 | 0 | 1 | 6 | 94.12% |
| 2008 | 4 | 4 | 0 | 8 | 92.16% |
| 2012 | 0 | 0 | 0 | 0 | 100.00% |
| 2016 | 11 | 0 | 2 | 13 | 87.25% |
| 2020 | 5 | 0 | 0 | 5 | 95.10% |
| 2024 | 2 | 0 | 0 | 2 | 98.04% |

Band totals across all years: **63** in `<0.1%`, **17** in `0.1–1%`, **7** in `>1%`.

### 3.1 The D005 reliability list (AC-3)

Seven cells exceed 1%. Listed by key and band only:

| Year | State | Candidate | Party | Band |
|---|---|---|---|---|
| 1976 | Vermont | Gerald R. Ford | Republican | `>1%` |
| 1976 | Vermont | Jimmy Carter | Democrat | `>1%` |
| 1984 | Washington | Walter F. Mondale | Democrat | `>1%` |
| 1992 | South Carolina | William J. Clinton | Democrat | `>1%` |
| 2004 | Mississippi | George W. Bush | Republican | `>1%` |
| 2016 | New York | Donald J. Trump | Republican | `>1%` |
| 2016 | New York | Hillary Clinton | Democrat | `>1%` |

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
| max relative difference | 3.359% |

Every one of the five state-years holding a `>1%` cell is also a state-year where the two sources'
**provided totals disagree**. The cell-level difference and the denominator difference are the same
event seen twice.

### 4.1 The "other/write-in" question cannot be asked at the cell grain — and that is a finding

D017's benign-seam caveat names other/write-in handling as a failure mode. **It is structurally
absent from this comparison.** D007 scopes the PV fact to EC-getters, and across the whole overlap
that leaves **exactly 2 candidates in every one of the 663 state-years** — 18 distinct candidates,
2 distinct parties. There are no minor, "other", or write-in rows in the population at all, so no
partition of the divergent cells by candidate type is possible.

Where the handling *does* surface is the **residual** between each source's provided total and the
sum of its own retained candidates — which is why `pv/validate.py` asserts `<=` and not `==`:

| Source | Mean residual | Max residual |
|---|---|---|
| MIT | 4.974% | 31.981% |
| UCSB | 4.922% | 31.981% |

The two residuals are **near-identical in the mean and identical at the maximum**, which is the
useful reading: whatever each source counts as "everybody else", the two treat it the same way to
within 0.05 percentage points on average. This is corroborating evidence for the benign seam, but it
is a *secondary* test — the residual is dominated by the dropped-candidate population (D007), so it
measures scoping more than denominator methodology. The primary denominator test is §4(b).

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

### 5.2 National margin, per source, in percentage points (AC-2b)

| Year | MIT margin (pp) | UCSB margin (pp) | difference (pp) |
|---|---|---|---|
| 1976 | 2.1008 | 2.1043 | 0.0034 |
| 1980 | 10.6045 | 10.6065 | 0.0020 |
| 1984 | 18.3507 | 18.3391 | 0.0116 |
| 1988 | 7.8031 | 7.8031 | **0.0000** |
| 1992 | 6.9600 | 6.9102 | **0.0498** |
| 1996 | 9.4727 | 9.4729 | 0.0001 |
| 2000 | **0.5322** | 0.5295 | 0.0027 |
| 2004 | 2.4784 | 2.4880 | 0.0096 |
| 2008 | 7.3777 | 7.3591 | 0.0186 |
| 2012 | 3.9166 | 3.9166 | **0.0000** |
| 2016 | 2.2264 | 2.2007 | 0.0258 |
| 2020 | 4.5360 | 4.5355 | 0.0005 |
| 2024 | 1.5001 | 1.4997 | 0.0004 |

**Verdict against the bar:** (i) 13/13 winners agree ✓. (ii) Every margin is positive under both
sources; none approaches zero ✓. (iii) Max difference **0.0498 pp** (1992) vs. smallest actual
margin **0.5322 pp** (2000) — the source effect is **10.7× smaller** than the closest election in
the window ✓. **All three clauses met → CONFIRMED.**

For completeness, the national per-candidate roll-up (26 `(year, candidate)` rows) agrees exactly in
only 4 cases — small per-cell differences accumulate rather than cancel when summed — but the
**relative** disagreement stays tiny: p95 **0.089%**, max **0.100%**. This is exactly the asymmetry
D017 predicts: a raw national *count* series is the fragile reading, a normalized margin is not.

---

## 6. Recommended tolerance for the D017 layer-3 gate (AC-5a)

**Three parts, at three grains.** A single relative ceiling is the wrong instrument here: with 93.4%
of cells exactly equal, a methodological step that nudged many cells slightly could keep every cell
under any sane ceiling while the exact-match rate collapsed — and that regression is precisely what
D017 §3 exists to detect.

| # | Gate | Grain | Recommended threshold | Observed today | Catches |
|---|---|---|---|---|---|
| 1 | **Exact-match-rate floor** | cell | **≥ 90% overall**, and **≥ 80% in any single year** | 93.44% overall; worst year 84.31% (1976) | many cells drifting slightly — a methodology step |
| 2 | **Per-cell relative ceiling** | cell | **flag at 1%** (→ D005 list), **fail at 15%** | 7 cells flag; max 9.593%, so 0 fail | one blown cell — a parse or unit regression |
| 3 | **Margin difference** | national, in **pp** | **≤ 0.25 pp** | max 0.0498 pp | the only grain E7's published outputs actually depend on |

**Notes that make these auditable rather than arbitrary:**

- **The D017 layer-3 gate runs at the cell grain** (#1 and #2). #3 is the E7 trustworthiness check
  and belongs with the hybrid computation, not with the PV union.
- **Threshold #2's fail level has deliberate headroom.** The observed max is 9.593%, so a 10% fail
  line would sit 0.4 points from live data and would redden on an ordinary canvass revision. 15% is
  ~1.6× the observed max and still catches an order-of-magnitude error, which is what a hard fail
  should be for.
- **Threshold #3 is stated in percentage points, not as a ratio**, because that is the unit the
  claim is made in — and 0.25 pp remains 2× below the smallest actual margin in the window, so a
  passing gate still guarantees no source-induced winner change.
- **The roll-up grain is deliberately not gated.** Its relative agreement (max 0.100%) is tighter
  than the cell grain, so #1 and #2 dominate it; adding a fourth threshold would fire only where one
  of those already had.

---

## 7. What this does and does not license

**Licensed.** Reading `pv_preferred` across the 1976 seam for **normalized per-election metrics** —
flip booleans and margin percentages, which is what `hybrid_preferred` and
`hybrid_summary_preferred` publish. Within the overlap the source choice changes no winner and moves
no margin by as much as 0.05 pp.

**Not licensed, and the caveat is unchanged by this finding:**

- **A raw national PV *count* series read across the seam.** §5's roll-up figures show counts
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

```bash
docker run -d --name usvote-70 -e POSTGRES_PASSWORD=itest -e POSTGRES_DB=elections \
  -p 5436:5432 postgres:16
D=~/Documents/Projects/data/presidential_vote_analysis
PGHOST=localhost PGPORT=5436 PGUSER=postgres PGPASSWORD=itest PGDATABASE=elections \
USVOTE_EC_HTML_DIR=$D/ec_raw USVOTE_MIT_CSV_PATH=$D/1976-2024-president.csv \
USVOTE_SHAPEFILE_PATH=<TIGER tl_2019_us_state.shp> USVOTE_UCSB_HTML_DIR=$D/ucsb_raw \
  uv run python -m usvote all
PGPASSWORD=itest psql -h localhost -p 5436 -U postgres -d elections \
  -f .claude/loop/epic-hybrid/issue-70.analysis.sql
docker rm -f usvote-70
```

The build used here loaded EC 5755 rows, MIT 1326 PV rows, UCSB 4626 PV rows. **UCSB is required**
— without `USVOTE_UCSB_HTML_DIR` the warehouse builds EC + MIT only and this comparison has no
second source. The snapshot is non-redistributable and lives outside the repository (D022), so this
is a local-only reproduction and never runs in CI.

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
