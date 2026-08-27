# `pv_coverage` — what it measures, and why twelve elections read below 1.0 (E7-S6)

> **In one sentence.** For twelve elections between 1824 and 1876 some states appointed their
> electors without holding a popular vote, so the hybrid's popular-vote share is measured over
> fewer states than its Electoral College share; `pv_coverage` reports how much of the electoral
> college those popular-vote states represent, and a value below 1.0 is an honest caveat on a real
> number rather than a defect.

The hybrid method averages a candidate's **Electoral College share** with their **national
popular-vote share** ([decision **D037**](../.claude/specs/decisions.md)). That average is only
strictly apples-to-apples where every state that cast electoral votes also held a popular vote —
and for twelve elections between 1824 and 1876, one or more states did not. Their electors were
appointed by the state legislature, so there was no popular vote to count, anywhere in that state.

`pv_coverage` is the column that carries that mismatch. This page says what it measures, why the
project **flags** the mismatch rather than papering over it, and enumerates every affected year
with its verified numbers.

> **Scope.** This documents the **settled** denominator policy — rule **(b)** of
> [**D038**](../.claude/specs/decisions.md) — and the evidence table behind it. It is not a
> re-litigation of that decision, and it is **not** the cross-source question of whether MIT and
> UCSB agree in their 1976–2024 overlap, which is separate work. The authoritative,
> machine-readable derivation is
> [`pv_coverage_by_year`](../src/usvote/hybrid.py) in `src/usvote/hybrid.py`; this page is the
> human-browsable description of what it produces.
>
> **Which surface these numbers come from, because `pv_coverage` is surface-dependent by design.**
> The tables below are computed on **`ec_pv_preferred`**, the full-history analysis surface, and
> they are also what the **public API** now serves — but the two arrive there by different routes,
> and the third surface in play still reads NULL. Three things to keep apart:
>
> | Surface | Pre-1976 `pv_coverage` | Why |
> |---|---|---|
> | `ec_pv_preferred` (analysis) | the figures tabulated below | the full-history roster, UCSB included |
> | `hybrid_redistributable` (warehouse view) | **NULL** | its roster read is scoped to the sources the view carries, and MIT's roster starts at 1976 |
> | the **public API snapshot** | the figures tabulated below | since **#102** it derives coverage from the in-repo [`PV_ABSENCE_CATALOG`](../src/usvote/pv/absences.py), which reaches every served year |
>
> **The middle row and the bottom row disagree on purpose** — that is the one intended divergence
> between the warehouse view and the artifact built from it, and it is the whole of D048's action
> item for #102. The view's NULL is the honest reading of an absent *roster*; the snapshot's figure
> is the honest reading of the *election*, and it is available publicly because every classification
> behind it carries a public-domain citation rather than coming from UCSB. **An earlier version of
> this note said a public consumer reads NULL for every pre-1976 year. That is no longer true**, and
> the reproduction recipe below reflects the catalog-derived route.

## What the number measures

For each election year:

```
pv_coverage = Σ total_electoral_votes over the year's popular_vote states
              ────────────────────────────────────────────────────────────
              Σ total_electoral_votes over every state (the appointed allotment)
```

A year in which every state held a popular vote reads exactly `1.0`. A year in which some state
appointed its electors directly reads below `1.0`, by that state's share of the electoral votes.

**It is weighted by electoral votes, not by state count** ([D024
§8](../.claude/specs/decisions.md)) — electoral votes are the analytically relevant weight, and
they are already loaded. The two weightings are genuinely different numbers, not rounding variants
of each other: 1824 is **0.728** EV-weighted against **0.750** by state count, and 1864 is
**1.000** against **0.694**. A state-count check would pass while measuring the wrong quantity, so
both are reported in the tables below and the EV-weighted one is the column the hybrid carries.

**The roster drives this, and a null popular vote never may.** Coverage is derived from
`dwh.pv_state_status` — a complete roster of every state in every election with its `pv_status` —
never inferred from a missing `candidate_votes` cell. Inferring it from a null would conflate a
state where **no popular vote was ever held** with a state some **source simply does not cover**,
which is exactly the distinction D024's deliberately `unknown`-free enum exists to preserve. The
two cases have an identical shape in the data, and only the roster tells them apart.

## Policy (b): what the hybrid actually does with a partial year

Under the settled rule, for a partial-coverage year:

- the **EC share is measured over all EC-casting states** — the full appointed allotment;
- the **PV share is measured over only the states that held a popular vote**;
- and `pv_coverage < 1.0` is carried alongside as the flag that the two were measured over
  different electorates.

The denominators are deliberately **not** reconciled. The alternative that would reconcile them —
rule (c), restricting the EC share and the PV share alike to the popular-vote states — is
implemented behind the
`apply_coverage_policy` seam but **is not shipped**: that is D038's ruling, and
[D042 §2](../.claude/specs/decisions.md) is what enforces it. (b) is the only configured rule, and
`test_nothing_configures_a_policy_other_than_b` in `tests/unit/test_hybrid.py` fails CI on any
production call site that names a policy constant or passes a `policy` argument.

### Why a flag rather than a fix

The rejected alternative is the argument. Rule **(a)** was to withhold the hybrid entirely for any
year containing a legislature-chosen state. D038 rejected it because it would suppress precisely
the elections the method exists to speak to: the House-contingent, no-electoral-majority years —
1824 above all.

So `pv_coverage < 1.0` is **an honest caveat on a real number, not a defect and not a data
quality problem.** Nothing is missing, mis-parsed, or estimated. In 1824 the six legislature-chosen
states really did appoint 71 electors without holding an election, and the national popular vote of
that year really is a complete measurement of a smaller electorate — not an incomplete measurement
of the full one. Consumers should display the number and the coverage together, never the number
alone and never neither.

## The affected years

**Every year containing a `legislature_chosen` state**, with both weightings. Twelve elections,
1824–1876; from 1880 onward every year reads exactly `1.0`.

| year | legislature-chosen states (EV) | PV states / all | covered EV / appointed EV | `pv_coverage` (EV) | by state count |
|---|---|---|---|---|---|
| 1824 | Delaware (3), Georgia (9), Louisiana (5), New York (36), South Carolina (11), Vermont (7) | 18 / 24 | 190 / 261 | **0.7280** | 0.7500 |
| 1828 | Delaware (3), South Carolina (11) | 22 / 24 | 247 / 261 | **0.9464** | 0.9167 |
| 1832 | South Carolina (11) | 23 / 24 | 277 / 288 | **0.9618** | 0.9583 |
| 1836 | South Carolina (11) | 25 / 26 | 283 / 294 | **0.9626** | 0.9615 |
| 1840 | South Carolina (11) | 25 / 26 | 283 / 294 | **0.9626** | 0.9615 |
| 1844 | South Carolina (9) | 25 / 26 | 266 / 275 | **0.9673** | 0.9615 |
| 1848 | South Carolina (9) | 29 / 30 | 281 / 290 | **0.9690** | 0.9667 |
| 1852 | South Carolina (8) | 30 / 31 | 288 / 296 | **0.9730** | 0.9677 |
| 1856 | South Carolina (8) | 30 / 31 | 288 / 296 | **0.9730** | 0.9677 |
| 1860 | South Carolina (8) | 32 / 33 | 295 / 303 | **0.9736** | 0.9697 |
| 1868 | Florida (3) | 33 / 37 | 291 / 294 | **0.9898** | 0.8919 |
| 1876 | Colorado (3) | 37 / 38 | 366 / 369 | **0.9919** | 0.9737 |

Three things this table settles, which prose estimates could not:

- **South Carolina is the whole story for eight consecutive elections.** From 1832 through 1860 it
  is the only state in the country appointing electors without a popular vote — the last holdout
  of a practice that even in 1824 was already the minority, used by six states of twenty-four.
- **The set is exactly twelve, and it ends at 1876.** It confirms the enumeration D024 §1 gave
  from the source-corpus survey in [`ucsb-html-formats.md`](ucsb-html-formats.md), which records
  Colorado 1876 as the last legislature-chosen state and no PV-absent state anywhere from 1880 on.
  Those two and the table above share a lineage, so that is consistency rather than independent
  attestation; the genuinely independent compilation is the in-repo catalog, and the cross-check
  against it is described under [what keeps these numbers honest](#what-keeps-these-numbers-honest).
  **1872 is in scope and absent from this table on purpose** — it was reviewed and found to have no
  absences at all, a finding rather than a silence, and it reads 1.0.
- **Only 1824 is badly covered.** Ten of the twelve years sit above 0.96; the two that are not are
  1824 (0.728) and 1828 (0.946). 1824 is the year the caveat is really about — and it is also the
  year with no electoral-vote majority at all, which is why it is the hybrid's motivating case
  rather than an awkward edge. This is an observation about magnitude, **not** a licence to drop
  the caveat above some threshold: every year in this table is below 1.0 and every one should be
  displayed with its coverage.

### Companion: years with `not_participating` states

Two elections carry a different kind of absence — states that took no part in the election at all,
rather than states that appointed electors without a popular vote. **These do not behave the way
you would expect, and the surprise is worth stating plainly.**

Every state named below carries **0** electoral votes, which is the whole point of the section —
so no allotments are shown in this table, unlike the one above.

| year | non-participating states | `pv_coverage` (EV) | by state count | what actually drives the number |
|---|---|---|---|---|
| 1864 | Alabama, Arkansas, Florida, Georgia, Louisiana, Mississippi, North Carolina, South Carolina, Tennessee, Texas, Virginia — eleven states | **1.0000** (233 / 233) | 0.6944 (25 / 36) | nothing — see below |
| 1868 | Mississippi, Texas, Virginia — three states | **0.9898** (291 / 294) | 0.8919 (33 / 37) | **Florida alone**, which is legislature-chosen, not non-participating |

**A non-participating state has zero electoral votes**, so it contributes nothing to *either* side
of the ratio — it is a 0/0 non-contributor. The property is enforced in code, not assumed: check 2
of [`assert_catalog_matches_spine`](../src/usvote/pv/absences.py) rejects any catalogued
`not_participating` state that carries a non-zero allotment, and any `legislature_chosen` state
that carries zero.

The consequence is that **1864 reads full EV coverage despite eleven absent states**, and that is
the correct answer rather than a bug: every electoral vote cast in 1864 was cast by a state that
held a popular vote. 1864 is where the two weightings diverge maximally — 1.000 against 0.694 —
and a consumer who sees eleven missing states and *expects* low coverage is the reader this
section is for. The honest message is reassuring, not cautionary.

1868 appears in **both** tables, and only its Florida row moves the number. The two statuses are
kept distinct throughout (D024 §4) precisely so that "appointed electors without a popular vote"
and "took no part" never collapse into one undifferentiated bucket.

## Worked example: 1824, where the policy is most visible

1824 is the year with the lowest coverage, no electoral-vote majority, and a president chosen by
the House. It is the natural test of whether the denominator policy changes any conclusion.

| candidate | EC votes | `ec_share_full` (b) | (c) restricted EC share |
|---|---|---|---|
| Andrew Jackson | 99 | 0.3793 | 84 / 190 = 0.4421 |
| John Quincy Adams | 84 | 0.3218 | 48 / 190 = 0.2526 |
| William H. Crawford | 41 | 0.1571 | 25 / 190 = 0.1316 |
| Henry Clay | 37 | 0.1418 | 33 / 190 = 0.1737 |

The EC column sums to 261 and the restricted column to 190, so both share columns sum to exactly
1.0. Note what (c) does to the *ordering* of the also-rans: Clay overtakes Crawford, reversing a
4-vote Crawford lead into an 8-vote Clay one. The mechanism is **differential exposure, not
concentration** — Crawford's support was not mostly in legislature-chosen states, since 25 of his
41 electoral votes came from popular-vote Virginia (24) and Maryland (1). What matters is the
*proportion* each candidate loses when those states come out: Crawford drops 16 of 41 (Georgia's
nine, New York's five, Delaware's two — 39%), Clay only 4 of 37 (New York's four — 11%).

> **Why the popular-vote columns are not printed here.** This project's pre-1976 popular vote comes
> from a source that grants no redistribution rights (D016/D022), so per-candidate popular-vote
> shares and national vote totals for 1824 are **deliberately absent from this page** — as they are
> from the public API, which serves popular votes only from 1976. The hybrid *scores* are omitted
> for the same reason and not merely for tidiness: a score is the mean of the EC and PV shares, so
> printing it beside the EC share would reconstruct the PV share exactly. What is stated below are
> the two **derived margins**, which the acceptance criteria ask for by name and which reconstruct
> no candidate's share — see [the provenance note](#provenance-and-how-to-reproduce-these-numbers)
> for exactly what they do and do not expose.

**The winner is invariant; only the margin moves.** Jackson leads on both measures — he has the
most electoral votes and the largest popular vote — and wins the hybrid under **both** (b) and (c).
What the policy changes is the top-two gap:

- under shipped policy **(b)**, `hybrid_margin` = **8.09 percentage points**;
- under unshipped policy **(c)**, it would be **14.69 points** — because (c) restricts Jackson's EC
  share to the popular-vote states, where he took 84 of 190 electoral votes (0.4421) against
  Adams's 0.2526, a wider lead than the 0.3793-to-0.3218 he holds over the full 261.

That is the sentence a display surface should carry: for the worst-covered election in the record,
the coverage policy moves the **margin**, not the **outcome**.

Two further properties of 1824 are worth naming, because they are easy to misread:

- **`ec_share_full` is policy-invariant, and no coverage policy can move it.** Jackson stays at
  99/261 = 0.3793 under both rules. This is a deliberate safety property (D037/A): the EC share is
  split in two, and only the policy-invariant half feeds `ec_determinative`. The hazard it
  neutralises is concrete: pairing the **full** 99-vote numerator with the **restricted** 190-vote
  denominator gives 0.52 — over the line, a constitutional majority that never existed. That
  pairing is a mistake rather than a policy, and
  [`_restricted_ec_numerator`](../src/usvote/hybrid.py) names it as one; (c) done correctly
  restricts *both* halves and puts Jackson at 84/190 = 0.442, still well under. Either way
  `ec_determinative` never reads this column, which is what makes the mistake harmless instead of
  catastrophic. The real answer is 99/261 = 0.379, no majority, and the House decided the
  election.
- **`ec_determinative` is `false` here, and that is a populated result, not a null.** Coverage and
  determinativeness are orthogonal: 1824 is both "no EC majority" and "partial PV coverage", and
  neither caused the other.

## A null `pv_coverage` is a third thing again

Distinguish three readings, because they mean different things and a display surface must not
merge them:

| value | meaning | what to render |
|---|---|---|
| `1.0` | every state that cast an electoral vote also held a popular vote | the hybrid, no caveat needed |
| `< 1.0` | at least one state appointed electors without a popular vote — the caveat this page explains | the hybrid **and** the coverage, together |
| `NULL` | **unknown** on this surface — the roster does not reach that year here | the hybrid **and** an explicit "coverage not established" marker |

`NULL` is emphatically not `0.0`. A year the roster says nothing about is a year nobody has
established anything about; reporting it as zero coverage would assert a fact that was never
checked. A real `0.0` — a year the roster reaches in which no state held a popular vote — is a
different, known result, and the derivation keeps the two apart on purpose.

**On NULL, never suppress the hybrid.** Withholding it is rule (a) coming back through the side
door, and D038 rejected rule (a). Show the number with the coverage unestablished, and never render
NULL as `0%`.

### Suggested display copy

Templates rather than fixed strings, so one year's numbers cannot be shipped for another. Keep the
wording, substitute the values:

- `< 1.0` — *"Popular-vote coverage: {coverage:.0%} of electoral votes. {n} state(s) appointed
  electors without holding a popular vote in {year}, so the popular-vote share is measured over the
  remaining states."*
  Instantiated for 1824: *"Popular-vote coverage: 73% of electoral votes. 6 states appointed
  electors without holding a popular vote in 1824, …"* — and for 1832: *"…: 96% of electoral votes.
  1 state appointed electors …"*
- `1.0` — *"Popular-vote coverage: complete."*
- `NULL` — *"Popular-vote coverage is not established for this election on this data surface."*

Note which of these a public consumer reaches for a pre-1976 year: since **#102**, the **`< 1.0`**
one — the public snapshot carries a real catalog-derived figure for every served year, so 1824
renders as "73% of electoral votes" rather than as "not established". The **`NULL`** template is
still live, but now only for the `hybrid_redistributable` warehouse view, whose roster does not
reach those years.

## Provenance, and how to reproduce these numbers

Every figure in the tables above is public-domain, and rests on two inputs:

- the **electoral-vote allotments** are National Archives data (`dwh.votes`, loaded from
  <https://www.archives.gov/electoral-college/results>);
- the **classification** of which states held no popular vote comes from
  [`PV_ABSENCE_CATALOG`](../src/usvote/pv/absences.py), an in-repo catalog whose every entry
  carries a public-domain citation. *McPherson v. Blacker*, 146 U.S. 1, 27–28 (1892) attests the
  1824 six by name and South Carolina's run through 1860; the Omnibus Act, 15 Stat. 73 (25 June
  1868) covers Florida and the three unreadmitted states in 1868; Colo. Const. of 1876, Schedule
  § 19 covers Colorado, with the Enabling Act (ch. 139, 18 Stat. 474) and Proclamation No. 230 for
  the 1 August admission date that explains *why*; and the H.R. 126 joint resolution covers 1864.
  Each `legislature_chosen` row additionally cites U.S. Const. art. II, § 1, cl. 2, the clause that
  permits legislative appointment — the clause permits it, the source attests that the state
  actually used it.

**The third input, named because this page depends on it and does not print it.** Coverage is a
statement *about* the popular vote, and the pre-1976 popular vote in this project's warehouse comes
from a source that grants no redistribution rights (D016/D022). No popular-vote count, no
per-candidate popular-vote share, and no national popular-vote total from before 1976 appears
anywhere on this page, and **no count, no individual share, and no total is recoverable from what
does** — the same boundary the public API draws by serving popular votes only from 1976 onward.

**Three printed figures are the exception, and they are PV-derived**: the two 1824 hybrid margins
(8.09 and 14.69 points) and the ~10.4-point gap below. Everything else on the page — every table
cell, every share, every ratio — comes from the two public-domain inputs above.

Stated precisely, because an absolute claim here would be the wrong kind of claim to make. One
derived quantity *is* recoverable from those three: the two margins plus the printed EC shares give
the **gap between the two leaders' popular-vote shares** in 1824, about 10.4 points, since a margin
is the mean of an EC gap and a PV gap. That is a difference between two candidates, not either
one's share — the two
margins yield one equation in two unknowns, so no individual share falls out, and Crawford's and
Clay's never enter a top-two margin at all. It is here because the acceptance criteria ask for the
margins by name and the movement of the margin *is* the finding, which is the same exception
[`ucsb-html-formats.md`](ucsb-html-formats.md) draws for quoting a vote number. `pv_coverage`
itself is unaffected: it is a ratio of *electoral votes*, and the
only thing it takes from the popular-vote side is the yes/no of whether a state held one, which is
the independently-cited classification above.

The decision record makes the same distinction directly: D024's licensing note holds that the
roster's free-text `note` column is non-redistributable source prose, while "the `pv_status` enum
is a bare historical fact and carries no such restriction."

**From the public API** (no database required — one request per year). Note that `pv_coverage` is
**not itself a served field today**; until the hybrid fields land on the API, derive it from the
served `pv_status` and `state_electoral_votes`, which is what this does:

```bash
curl -s https://api.us-presidential-election-center.org/v1/elections/1824 \
  | python3 -c 'import json,sys
rows = json.load(sys.stdin)["data"]
st = {r["state"]: (r["pv_status"], r["state_electoral_votes"]) for r in rows}
den = sum(ev for _, ev in st.values())
cov = sum(ev for s, ev in st.values() if s == "popular_vote")
print(f"{cov}/{den} = {cov/den:.4f}")'
# → 190/261 = 0.7280
```

**From a local warehouse**, calling the shipped derivation rather than re-deriving it:

```python
from usvote.hybrid import pv_coverage_by_year

pv_coverage_by_year(ec_pv_df, roster_df)   # → year, ec_denominator,
                                           #   covered_electoral_votes, pv_coverage
```

### What keeps these numbers honest

The table above is prose, and prose drifts. Three code guarantees are what it actually rests on:

- **[`assert_catalog_matches_spine`](../src/usvote/pv/absences.py)** cross-checks the catalog
  against the Electoral College spine in both directions — every catalogued state must exist in
  the spine with the electoral-vote count its status implies, and, the direction with teeth, no
  zero-electoral-vote state in the spine may be left classified `popular_vote` by the residual.
- **`CURATED_YEARS` / `CURATED_YEAR_COUNT`** in the same module fix and pin the catalog's scope:
  `build_curated_roster` **raises** for a year outside it, so the catalog's *silence* about an
  unreviewed year can never be read as "no absences there", and the count pin catches the ingest
  span moving underneath it.
- **`TestRealCorpus`** in `tests/unit/test_ucsb_transform.py` checks the classification of all
  2,204 state-year pairs across 51 years against an independent source, set-equal. It is skipped
  in CI by design and is run locally.
- **`test_hybrid_views_over_a_real_full_warehouse`** in `tests/integration/test_hybrid_views.py`
  (#124) pins **this page's table** against the materialized `hybrid_summary_preferred` view over
  a real EC + MIT + UCSB warehouse: the twelve years set-equal, each `pv_coverage` value to
  1e-6, each `ec_denominator`, every other year exactly `1.0` — so a year *leaving* the set is
  caught as well as one joining — and 1864 explicitly `1.0`. Like `TestRealCorpus` it is gated on
  the local corpora and skipped in CI, so running it is a merge precondition rather than
  something CI can vouch for.

The twelve-year set in this page was produced from a full local warehouse and cross-checked
against the in-repo catalog over the same Electoral College spine: 2,204 state-year pairs, **zero
classification disagreements**. Note what that does and does not show — the shared *membership* is
the design, not a finding, since D024 §6 has both rosters take their state-years from the same
spine. Only the classification is an independent check.

## A second caveat, on the other side of 1976: the source seam

`pv_coverage` describes how much of a year's electoral college is *covered* by a popular vote. A
different question applies to the years that are fully covered: **which source the coverage came
from.** `pv_preferred` reads MIT from 1976 on and UCSB before it (D017), so any comparison drawn
*across* 1976 — a margin trend above all — spans a source switch.

That switch has now been measured rather than assumed. See
[`research-pv-overlap.md`](../.claude/specs/research-pv-overlap.md) (E7-S1, #70), which differences
the two sources across the 1976–2024 window where both cover the same elections. The short version:

- The national popular-vote **winner is identical under both sources in all 13 overlap years**, so
  `pv_flip` is source-invariant there.
- The largest cross-source difference in the national **margin** is **0.034 pp**, against a smallest
  actual margin of 0.511 pp (2000) — about 15× smaller than the closest real election in the window.
  Both are computed on each source's **provided** state-total denominator, the same one
  `roll_up_national` uses, so they are directly comparable with the shipped `pv_margin`.
- So the **normalized** metrics this doc's neighbours publish — flips and margin percentages — are
  safe to read across the seam. A raw national vote **count** series is not: counts disagree far
  more readily than ratios do.

**The residual assumption, which that finding explicitly could not discharge:** agreement measured
*inside* the overlap licenses reading UCSB *before* it only if UCSB is methodologically stationary
across its own span, and MIT does not reach back far enough to test that. State it wherever a
cross-1976 trend is published.

## See also

- [**D037**](../.claude/specs/decisions.md) — the hybrid method and the split EC share
- [**D038**](../.claude/specs/decisions.md) — the settled denominator policy (b)
- [**D042**](../.claude/specs/decisions.md) — why (c) is implemented but not shipped
- [**D024**](../.claude/specs/decisions.md) — the `pv_state_status` roster (§1 the enumeration,
  §4 the three-value enum, §8 the EV weighting)
- [`src/usvote/hybrid.py`](../src/usvote/hybrid.py) — `pv_coverage_by_year`,
  `apply_coverage_policy`, `ec_denominator_by_year`, and (#124) the SQL builders that
  materialize them as the `hybrid_*` views
- [**D050**](../.claude/specs/decisions.md) — how the hybrid views materialize this column
- [`src/usvote/pv/absences.py`](../src/usvote/pv/absences.py) — the absence catalog and its
  citations
- [`research-pv-overlap.md`](../.claude/specs/research-pv-overlap.md) — E7-S1 (#70): the measured
  MIT-vs-UCSB agreement across the 1976 source seam, and the D017 layer-3 tolerance it
  recommended — **adopted** as [D051](../.claude/specs/decisions.md) and **implemented** in #167
  ([`src/usvote/pv/overlap.py`](../src/usvote/pv/overlap.py), plus gate 3 in
  [`src/usvote/hybrid.py`](../src/usvote/hybrid.py))
- [`ucsb-html-formats.md`](ucsb-html-formats.md) — the source-corpus survey the roster design came
  from
