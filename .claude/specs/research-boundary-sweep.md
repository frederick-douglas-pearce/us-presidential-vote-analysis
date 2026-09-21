# Boundary-discrepancy sweep: is Virginia the only material case in the 1824–2024 EC span?

**Issue:** #208 (carved out of #180 at the owner's direction) · **Status:** **Analysis complete — AC-5 deferred to #251** (see *Deferrals*)
**Date:** 2026-09-19 · **Deliverable shape:** written recommendation, per `research-census-source.md`

---

## 0. Evidence labels

Every load-bearing claim below carries exactly one label, and **labels are never laundered
upward**:

| Label | Meaning |
|---|---|
| **VERIFIED** | Reproduced here — a figure read out of a primary document, or computed by a script in this repo against the local corpora, with the command given |
| **ATTRIBUTED** | A specific named source states it, but this document did not open the primary artifact |
| **UNVERIFIED** | Believed, with no source that can be pointed at. Present so it is visible, never as a basis for a correction |
| **CONTRADICTED** | Two sources disagree; both are given |

---

## 1. Verdict

**Virginia is NOT the only material case — but the second case is also Virginia.**

| # | Case | Jurisdictions | Effective | Affected elections | Magnitude | Ruling |
|---|---|---|---|---|---|---|
| 1 | **West Virginia separation** | VA → WV | 1863 | 1824–1860 (ten) | **12.7%–21.3%** understatement of Virginia's denominator | **MATERIAL** — already corrected (#181) |
| 2 | **Alexandria retrocession** | DC → VA | 1846 | **1824–1844** (**six** — resolved by #253/D066, which rules borders-at-election; the **seven** this report used throughout is the apportionment-basis count and is superseded) | **0.79%–0.91%** *overstatement* of Virginia's denominator, *after* correction 1 is applied | **MATERIAL** — **not corrected; this is the new finding** |

Every other post-1824 boundary change is ruled **immaterial**, and §6 gives each one its reason — including the **Toledo Strip**, which §6.5 classifies but which also leaves the sweep's one
**unquantified residual** — on **both** Michigan and Ohio, equal and opposite, now that #253/D066 rules borders-at-election (§6.5 always declined to clear Ohio; this resolves the criterion it was waiting on). Read §6.5 before quoting this row.
Two of those reasons are structural rather than magnitude-based, and the distinction matters:
Berkeley/Jefferson washes out of the arithmetic, and the territory-to-state cases move no
population *between states* at all.

**The two corrections run in opposite directions and do not cancel.** Correction 1 adds West
Virginia's counties (large); correction 2 removes Alexandria County (small). Applied together, the
1820/1830/1840-governed elections need `file_VA + file_WV − Alexandria`.

---

## 2. The new finding, and how it was reached

`tabs15-65.xlsx` reports every census on **present-day** state footprints. #180 established this,
measured Virginia's West Virginia gap, and **flagged a residual it could not close**: its acceptance
verifier found the 1820/1830/1840 file sums running "roughly 9,600–10,000 above commonly-cited
enumerated Virginia totals," with that figure itself unverified. #181 shipped the correction anyway
and left an honest hedge on the affected rows naming this issue by number.

**The residual is real, it is in five censuses rather than three, and it is exactly explained.**

The mechanism is the **retrocession of Alexandria County from the District of Columbia to Virginia
in 1846**. The land was ceded by Virginia in **1791**, Congress assumed jurisdiction in 1801 and
the county was organised as Alexandria County that year, and it returned to Virginia in 1846 — so
the 1800 census already returned it as *"District of Columbia, in Virginia"*. (Three dates, all
real; §5.2 and §6.6 use the 1791 cession, this paragraph the 1801 organisation.) On a
**present-day** footprint it is Virginia
throughout — so for the censuses of **1800–1840**, when it was enumerated as part of the District,
`tabs15-65.xlsx` assigns its people to Virginia.

That predicts two things at once, and **both hold to the person** — each against a *separately
published* series, not against the other (VERIFIED, §4.1 and §5.2): Virginia's file figure runs
*above* the enumerated Virginia by the Alexandria population, and the District's file figure runs
*below* the enumerated District by the same amount. The second identity is what keeps the first
from being circular, and it needs the Bureau's own District series (§5.2) to be a test at all. 1790 is clean because the District
did not yet exist; 1850 and 1860 are clean because retrocession had already happened.

**Why this was worth finding.** #180's reasoning about the other candidates was *"sparsely
populated" — a judgement, not a measurement*, and the issue was filed to replace it with one. The
case it actually turned up was not on anybody's candidate list: it is not a transfer between two
**states**, so a sweep looking only for state-to-state moves would have missed it, and it hides
*inside* the one case everybody already knew about.

---

## 3. The materiality threshold — proposed and argued

AC-1 asks for a threshold to be **argued for, not adopted**. Three were considered.

**Candidate A — magnitude (the issue's own suggestion): ≥1% of the affected state's population in
any census governing an election it held electoral votes for.** Rejected as the *primary* test.
Under it Alexandria (0.79%–0.91%) is immaterial by a margin of roughly one part in a thousand — a
threshold that decides a real question by where a round number happens to fall.

**Candidate B — rank: does the correction change the state's persons-per-electoral-vote rank in any
election it held votes for?** Retained, but as a **diagnostic**, not the gate. Two reasons. It is
*derived* — it depends on how close the neighbours happen to be, so the same error is material in
one decade and not the next for reasons having nothing to do with the error. And it is
**surface-specific**: it answers for a ranked display and says nothing about a reader who quotes a
single state's figure.

**Candidate C — ADOPTED. A boundary change is material when its effect is all three of:**

1. **systematic** — present in every governing census across the affected span, not a one-off;
2. **one-directional** — always the same sign, so it cannot average out across elections;
3. **quantifiable from sources** — so a correction can be *stated with provenance* rather than
   estimated.

**Magnitude sets priority, not materiality.**

**The argument.** A and B both ask *"would anyone notice?"* — and a systematic, one-directional
bias is precisely the class **nobody** notices. It shifts every affected election the same way, so
it survives averaging, it survives within-year comparison, and it surfaces only when someone
reconciles against an independent source. That is the failure mode this epic has hit repeatedly and
names in its own decision log: *plausible wrong numbers rather than load errors*. A large but
one-off or sign-varying discrepancy is comparatively self-announcing — someone eventually looks at
it and asks. A steady 0.8% lean is never looked at.

Condition 3 is what keeps the test from becoming unbounded: a change nobody can quantify cannot be
corrected, only disclosed, and §6 marks those cases as such rather than ruling them material.

**This threshold was set by the repo owner at the plan gate**, in preference to a rank-primary test
recommended by the architect pass. Recorded as a human decision.

**Under it, Alexandria is MATERIAL**: present in all three governing censuses (1820/1830/1840),
always the same sign (always an overstatement), and quantifiable to the person — and §5 shows it is
not merely quantifiable but **already published by the Census Bureau**.

### 3.1 The rank diagnostic — and it went against the prediction

The architect pass predicted, as "my strong expectation," that Virginia's rank would be **unchanged
in every** affected election, and recommended ruling the case immaterial on that basis. **It was
computed rather than predicted, and the prediction is CONTRADICTED** (VERIFIED, §4):

| Election | Governing census | VA EV | Shipped (with Alexandria) | As enumerated | Rank shift |
|---|---|---|---|---|---|
| 1824 | 1820 | 24 | 44,795 — rank 23/24 | 44,390 — rank 23/24 | same |
| 1828 | 1820 | 24 | 44,795 — rank 23/24 | 44,390 — rank 23/24 | same |
| **1832** | 1830 | 23 | 53,086 — **rank 24/24** | 52,670 — rank 23/24 | **24 → 23** |
| **1836** | 1830 | 23 | 53,086 — **rank 26/26** | 52,670 — rank 25/26 | **26 → 25** |
| **1840** | 1830 | 23 | 53,086 — **rank 26/26** | 52,670 — rank 25/26 | **26 → 25** |
| 1844 | 1840 | 17 | 73,516 — rank 26/26 | 72,929 — rank 26/26 | same |
| 1848 | 1840 | 17 | 73,516 — rank 29/29 | 72,929 — rank 29/29 | same |

(Rank 1 = fewest persons per electoral vote.)

**In three consecutive elections the error changes which state was the most under-represented in the
Electoral College.** The swap partner is **South Carolina** every time, and the margin is thin:
with Alexandria, Virginia reads 53,086 against South Carolina's 52,835 and takes last place; as
enumerated it reads 52,670 and sits ahead of it. **9,573 people decide it.**

So the case is material under the adopted test *and*, in **3 of the 7** affected elections, under
the architect's own rank test — which is the value of having computed it. The lesson is the one the
architect itself stated: for a question this close, a prediction about a rank is not evidence.

---

## 4. Empirical results (VERIFIED — reproducible offline)

All three checks below run with **no network and no database**, against the two local corpora
(`USVOTE_CENSUS_CORPUS_DIR` and `USVOTE_EC_HTML_DIR`). The script is reproduced in Appendix A.

### 4.1 Parent/child reconciliation — the #180 technique, extended

| census | file VA | file WV | VA+WV | file DC | Alexandria | VA+WV − Alex | enumerated VA |
|---|---|---|---|---|---|---|---|
| 1790 | 691,737 | 55,873 | **747,610** | — | — | — | **747,610** ✓ |
| 1800 | 807,557 | 78,592 | 886,149 | 8,144 | 5,949 | **880,200** | **880,200** ✓ |
| 1810 | 877,683 | 105,469 | 983,152 | 15,471 | 8,552 | **974,600** | **974,600** ✓ *(§5.3)* |
| 1820 | 938,261 | 136,808 | 1,075,069 | 23,336 | 9,703 | **1,065,366** | **1,065,366** ✓ |
| 1830 | 1,044,054 | 176,924 | 1,220,978 | 30,261 | 9,573 | **1,211,405** | **1,211,405** ✓ |
| 1840 | 1,025,227 | 224,537 | 1,249,764 | 33,745 | 9,967 | **1,239,797** | **1,239,797** ✓ |
| 1850 | 1,119,348 | 302,313 | **1,421,661** | 51,687 | — | — | **1,421,661** ✓ |
| 1860 | 1,219,630 | 376,688 | **1,596,318** | 75,080 | — | — | **1,596,318** ✓ |

File columns: **VERIFIED**. Enumerated and Alexandria columns: see §5 for each cell's own label.

### 4.2 National-total reconciliation — what it does and does not establish

**All 21 census years 1790–1990 reconcile EXACTLY** against a published US total, and the script now **asserts** it rather than printing it (VERIFIED —
census.gov CPH-2 *Table 4. Population: 1790 to 1990* for 1790–1900, and the census.gov
population-change table for 1910–1990).

Two notes worth keeping:

- **1930 and 1940 reconcile only after Alaska's off-cycle rows are added back** (1929 = 59,278;
  1940's counterpart 1939 = 72,524). The parser emits those faithfully and `SOURCE_SPANS` drops
  them (D061) — so the "missing" 59,278 and 72,524 are a *scope* decision working correctly, and
  the national check is what makes that visible.
- **Two Census publications disagree for 1910–1940** (CONTRADICTED). CPH-2 Table 4 prints
  92,228,496 / 106,021,537 / 123,202,624 / 132,164,569 where the modern table prints 92,228,531 /
  106,021,568 / 123,202,660 / 132,165,129. `tabs15-65.xlsx` tracks the **modern** series exactly.
  This is a vintage difference between two Bureau publications, not a defect in the file — the same
  two-vintage hazard D059 already carries as a per-row `vintage` column.

**What this check does NOT establish, stated because the first draft of this plan got it wrong.**
A state-to-state transfer is **conservative at the national level**: if a county moves from state A
to state B, the sum is unchanged whichever state the file assigns it to. So a clean national total
is compatible with arbitrarily large unlisted state-to-state reassignment — **the Virginia/West
Virginia case itself passes this check silently.** It is therefore *not* a completeness backstop.
What it does establish is real but narrower: the file's jurisdiction set is complete and
non-duplicated, and no population crossed the **US** boundary unaccounted.

### 4.3 The structural completeness argument — why the empirical sweep can stop

The parent/child technique applies only where the file contains **both** jurisdictions. So the
question "which cases could this technique have caught?" has an exact answer, obtained by asking
which states carry population in the file **before they first appear in the EC record**, and then
asking what they were carved out of:

(Read the criterion as *"areas whose **first** EC appearance falls after the span opens"*. The
literal wording would select all 51, since the EC record starts at 1824 and every area carries
population from some earlier census — though **not** all from 1790: only **18 of 51** report a 1790
figure, which the script's own check-A line prints. **27 areas** qualify under the corrected
reading — 26 states **and the District of Columbia** — and of those, exactly two have a **state**
predecessor. Both are named below; DC is one of them, which is why the count is of *areas* and not
of states.)

- **West Virginia** carries population from 1790 and first holds electoral votes in 1864. Its
  predecessor is **Virginia — a state.** ✓ caught
- **District of Columbia** carries population from 1800 and first holds electoral votes in 1964.
  Its overlap with Virginia is the Alexandria case. ✓ caught
- **Every other case is territory → state** (Alaska, Arizona, New Mexico, Utah, Washington, the
  Dakotas, Oklahoma, Michigan, Wisconsin, Arkansas, Florida, and the rest). A territory is not
  another state's denominator, so no state's per-capita figure is affected by the transfer.
- **The pre-1824 state-to-state separations** — Kentucky from Virginia (1792), Tennessee from North
  Carolina (1796), Vermont (1791), and **Maine from Massachusetts (1820)** — are **out of scope by
  AC-3**, which bounds this sweep to the EC span. Stated rather than silently omitted, as AC-3
  requires. Note that this is a scope decision, not a finding that they are immaterial: on a
  present-day footprint, pre-1824 Massachusetts figures exclude Maine, and any future widening of
  the span below 1824 would have to revisit them.

**So within the EC span, this scan finds exactly two jurisdiction pairs, and both are reported
above.** But note carefully what it does **not** reach, because §6 turned up a case that proves the
limit is real rather than theoretical.

**The scan sees a transfer only when one side is a *newly appearing* jurisdiction.** A transfer
between two states that **both already existed** leaves no trace in it: neither state appears late,
so neither is flagged, and there is no parent whose total the pair should sum back to. The
Massachusetts ↔ Rhode Island exchange of 1862 (§6.4) is exactly that shape, and this scan is blind
to it. Detecting that class empirically would need an external **as-enumerated per-state** figure
for every state and census — which is precisely what #180 declined to acquire, and what makes the
documentary sweep in §6 load-bearing rather than a formality.

**The predicate that actually bounds the problem is not this scan but the Bureau's own restatement
rule** (§5.1): a transfer is restated *only if one or more whole counties moved*. That is what
disposes of Massachusetts ↔ Rhode Island, Boston Corner, the Delaware Wedge and the rest — without
needing a population figure for any of them. §4 finds the cases; §5 supplies the rule that rules
them in or out.

---

## 5. Primary sourcing — the Bureau documents this case itself

**The strongest result in this report: the correction does not need to be derived at all.** The
Census Bureau publishes both the method and the Alexandria figures, in the companion volume to the
very working paper `tabs15-65.xlsx` comes from.

**Source (VERIFIED — downloaded and read directly, not relayed):** *Population of States and
Counties of the United States: 1790 to 1990*, Bureau of the Census, March 1996
([PDF](https://www2.census.gov/library/publications/decennial/1990/population-of-states-and-counties-us-1790-1990/population-of-states-and-counties-of-the-united-states-1790-1990.pdf)).

**Provenance check first.** That volume's Virginia row for 1790–1850 reads `691,737 / 807,557 /
877,683 / 938,261 / 1,044,054 / 1,025,227 / 1,119,348` — **identical to `tabs15-65.xlsx`**. So this
is the same series, and its explanatory notes describe the file we load.

### 5.1 The method, in the Bureau's words (VERIFIED, quoted verbatim)

> "Throughout this report, to facilitate comparisons over time, each State is shown as closely as
> possible in its **present-day boundaries**, as far back as separate census data are available for
> counties now included in that State."

> "Where areas have been transferred between Territories or States, **revision of earlier census
> totals has been made if one or more whole counties was involved** in the transfer… For
> **inter-State transfers of territory smaller than a county, the population transferred usually is
> not available**; for a few such transfers, the population affected is specified in the notes."

**That second paragraph is the predicate this whole sweep turns on** — it tells you exactly which
boundary changes the file restates and which it leaves alone. §6 applies it.

### 5.2 The Alexandria case, stated by the Bureau on both sides (VERIFIED, verbatim)

**Virginia, Note 2:**

> "State totals for 1800-1840 **include** population of the portion of the District of Columbia
> taken from Virginia (Fairfax County) in 1791 but **retroceded to Virginia in 1846** (1800: 5,949;
> 1810: 8,852; 1820: 9,703; 1830: 9,573; 1840: 9,967). This area became Alexandria County in 1801…
> Alexandria County was renamed Arlington in 1920."

**District of Columbia note:**

> "In 1846 the portion south of the Potomac River, including Alexandria, was retroceded to Virginia…
> **All populations shown in the table exclude the portion returned to Virginia in 1846.**"

**And the volume's front matter names the correction outright:**

> "the Virginia table **does** include the present Arlington County and the city of Alexandria, both
> of which were part of the District of Columbia from 1791 to 1846. Following the Virginia table,
> the State note for Virginia gives the total population at the early censuses **for the State as
> then defined**, including the West Virginia counties in 1790-1860 but **excluding Arlington and
> Alexandria in 1800-1840**."

**And the District note prints the enumerated series itself** — this is the **independent** input
that makes §2's two-sided claim a test rather than a restatement, and §4.1's identity a
reconciliation rather than an identity (VERIFIED, verbatim, read in the same extraction):

> "Population of the District as then constituted: **1800: 14,093; 1810: 24,023; 1820: 33,039;
> 1830: 39,834; 1840: 43,712.**"

Subtracting the file's present-day District figures (8,144 / 15,471 / 23,336 / 30,261 / 33,745)
gives **5,949 / 8,552 / 9,703 / 9,573 / 9,967** — the Alexandria series, from a source that never
mentions Virginia. An earlier revision of this report cited this note without the series and so left
the derivation circular; the series is the whole reason it is not.

### 5.3 The figures, and how they compare to the derivation

| census | Virginia Note 2 | District note − file DC | `Arlington` county row | original enumeration | agree? |
|---|---|---|---|---|---|
| 1800 | **5,949** | 5,949 | 5,949 | **5,949** — 1800 Return p. 52, *"Total number of souls, 5,949"* | ✓ four ways |
| 1810 | **8,852** | **8,552** | **8,552** | *volume not digitised* | **CONTRADICTED — resolves to 8,552** |
| 1820 | **9,703** | 9,703 | 9,703 | **9,703** — Census for 1820, printed p. 102 | ✓ four ways |
| 1830 | **9,573** | 9,573 | 9,573 | **9,573** — Fifth Census *Abstract* p. 45, sub-totalled outright | ✓ four ways |
| 1840 | **9,967** | 9,967 | 9,967 | **9,967** — *Compendium of the Sixth Census* | ✓ four ways |

**Labels for that table, since §0 requires one per load-bearing claim.** The *Virginia Note 2*,
*District note* and *`Arlington` row* columns are **VERIFIED** — read in an extraction of the volume
taken here. The **original enumeration** column is **ATTRIBUTED**: those four volumes were located
and read by a delegated primary-source pass, and this report did not re-open them. They corroborate
the first three columns; nothing rests on them alone.

**The 1810 disagreement is a typo in the Bureau's volume, not an OCR artifact, and it resolves to
8,552.** An earlier draft of this report guessed OCR — the text layer *is* Acrobat Paper Capture and
a 5/8 confusion is the commonest error on such a scan, so the guess was plausible. It was wrong.
**Two** independent readings inside the same volume give **8,552** — and the count matters, because
an earlier draft of this section claimed three:

1. the **District note's** series minus the file's DC figure (`24,023 − 15,471`);
2. the volume's **`Arlington` county row**, read at 500 dpi.

**The arithmetic is not a third reading.** The identity `15,471 + x = 24,023` *is* reading 1, and the
second equation — `877,683 + 105,469 − x = 974,600` — needs `974,600`, which comes from a
*different* publication and which §5.4 itself flags **CONTRADICTED** against the 1850 restatement's
974,622. Worse, it leans on the answer: §5.4 prefers 974,600 partly *because the file's components
reproduce it*, and those components already presuppose 8,552. The rival pair (Alexandria **8,530**,
enumerated Virginia **974,622**) is perfectly self-consistent under the Virginia identity alone.

**So the District note is what actually breaks the tie** — `15,471 + 8,530 = 24,001 ≠ 24,023` — with
the `Arlington` row agreeing independently. That is sufficient, and it is all that is claimed.
Virginia Note 2's `8.852` is a defect in the printed note.

**It still governs no in-span election** — the 1810 census governs 1812–1820 — so nothing here
depends on it. It is recorded because the earlier draft asserted that re-reading the page image was
the only way to settle it, and that was false: the same volume settles it two pages away.

**A naming trap worth carrying into #251:** in 1820 the row printed *"County of Alexandria"* is the
**rural remainder only** (1,485); the county total is that plus *"Alexandria"* (8,218) = 9,703. And
the correct continuation of pre-1846 Alexandria County is the volume's **`Arlington`** row — its
`Alexandria` row is the modern independent city and is not comparable.

### 5.4 Enumerated Virginia, 1790–1860, established from primary Bureau figures

The owner's added scope asks for the **enumerated Virginia totals** from a primary source, "not
from recall, and not from a secondary compilation." The Bureau does not print that total directly;
it prints the **two components**, and the front matter says in as many words that the state note
composes them. So the total is established as a stated arithmetic over three published figures:

`enumerated VA  =  Virginia table  +  West Virginia counties (Note 1)  −  Alexandria (Note 2)`

**Note 1 (VERIFIED, verbatim):** *"Totals for 1790-1860 exclude counties wholly or primarily in
what is now West Virginia (1790: 55,873; 1800: 78,592; 1810: 105,469; 1820: 136,808; 1830: 176,924;
1840: 224,537; 1850: 302,313; 1860: 376,688)."* — **identical to `tabs15-65.xlsx`'s West Virginia
rows**, a third independent cross-check on the file's provenance. The same note adds that the
*"Total for 1800 includes 48 persons not credited to any county."*

| census | VA table | + WV (Note 1) | − Alexandria (Note 2) | **= enumerated Virginia** |
|---|---|---|---|---|
| 1790 | 691,737 | 55,873 | — (District did not exist) | **747,610** |
| 1800 | 807,557 | 78,592 | 5,949 | **880,200** |
| 1810 | 877,683 | 105,469 | 8,552 *(§5.3; Note 2's 8,852 is a defect)* | **974,600** |
| 1820 | 938,261 | 136,808 | 9,703 | **1,065,366** |
| 1830 | 1,044,054 | 176,924 | 9,573 | **1,211,405** |
| 1840 | 1,025,227 | 224,537 | 9,967 | **1,239,797** |
| 1850 | 1,119,348 | 302,313 | — (retroceded 1846) | **1,421,661** |
| 1860 | 1,219,630 | 376,688 | — (retroceded 1846) | **1,596,318** |

**1790, 1850 and 1860 reproduce the three totals #180 verified independently** — so the composition
is confirmed against a known answer at all three points where one exists, which is what licenses
reading the other rows off it. **1810 resolves to 8,552 per §5.3**, so the composed total is
974,600.

**CONTRADICTED — 1810 and 1820 each have two published Bureau totals, and only one pair closes the
identity.** The original returns give **974,600** and **1,065,366** (as reprinted in *A Century of
Population Growth*, 1909, Table 11); the **1850 Seventh Census restatement** gives **974,622** and
**1,065,379**, internally consistent there. They differ by **22** and **13**. The file's component
series reproduce the **original-return** pair exactly, so that is the pair used throughout this
report and in the script — pick the restatement and the identity misses by those amounts. This is
recorded because a later reader sourcing "the enumerated Virginia" from the 1850 volume will get a
different number and conclude the reconciliation is broken when it is not.

**Retrocession, dated** (for #251's provenance) — **ATTRIBUTED**, from the same delegated pass;
the statutes were fetched and read there, not here: Act of **9 July 1846**, ch. XXXV, **9 Stat. 35**,
whose §4 made it conditional on a referendum of the county; the poll ran **1–2 September 1846**
(763 for, 222 against) and President Polk proclaimed it in force on **7 September 1846** (9 Stat.
Appendix p. 1000). So the 1850 census counted Alexandria in Virginia, which is why 1850 and 1860
need no Alexandria term.

### 5.5 A caveat the Bureau raises that #180 did not (VERIFIED, verbatim)

> "the date given for both Virginia and West Virginia is 1860, because the population of the present
> territory of each State can be determined for 1860 by adding up the counties that formed West
> Virginia… **Prior to 1860 this cannot be done exactly, because the present Virginia-West Virginia
> State boundary did not correspond to county boundaries in 1850 or earlier.**"

This qualifies — it does not overturn — #180 §4's "three exact reconciliations settle the mechanism
beyond argument." The reconciliations prove the split is **exhaustive** (nobody is lost or
double-counted). They do **not** prove it is **accurate** at the county-assignment level before
1860, and the Bureau says plainly that it is not exact. Worth carrying into
`apply_virginia_boundary_correction`'s provenance text, which currently implies the arithmetic
settles everything.

---

## 6. Documentary sweep — post-1824 boundary changes

**Provenance of this section, stated because it differs from §4 and §5.** The enumeration below was
produced by a delegated research pass whose spine source was Van Zandt, *Boundaries of the United
States and the Several States*, **USGS Professional Paper 909 (1976)**. **I did not read PP909
myself**, so every claim sourced to it is **ATTRIBUTED (relayed)**, not VERIFIED, however confident
the relay sounded. What I *did* verify myself is the Census volume in §5 — and that is what settles
the two cases that matter, because §5.1's whole-county rule decides them without needing PP909 at
all.

### 6.1 The rule that decides most of this section

Per §5.1, the file restates a transfer **only if one or more whole counties moved**. So:

- **Whole-county transfers → restated → a potential error.** Virginia/West Virginia (counties) and
  Alexandria (Fairfax County's detached portion, which became Alexandria County) are both of this
  kind. Both are found, and both are in §1.
- **Sub-county transfers → not restated → the file already carries the borders-in-force figure →
  no error.** This disposes of most of the list below *without* needing a population figure, which
  matters because the boundary literature almost never reports one.

### 6.2 Transfers that moved inhabited land between two states after 1824

| Case | Direction | Effect | Whole county? | Ruling |
|---|---|---|---|---|
| **West Virginia separation** | VA → WV | 1863 | **yes** | **MATERIAL** — §1 case 1, corrected in #181 |
| **Alexandria retrocession** | DC → VA | 1846 | **yes** | **MATERIAL** — §1 case 2, **uncorrected** |
| **Berkeley & Jefferson Counties** | VA → WV | 1863/66, upheld *Virginia v. West Virginia*, 78 U.S. 39 (1871) | yes | **IMMATERIAL BY CONSTRUCTION** — see 6.3 |
| **Massachusetts ↔ Rhode Island** | both ways | SCOTUS decree 1861, effective 1 Mar 1862 | **no** (towns) | **IMMATERIAL** — see 6.4 |
| **Toledo Strip** | Michigan Terr. → Ohio | 1836/37 | no — a sliver across Monroe Co., and **not restated** (§6.5) | **IMMATERIAL** (unquantifiable), with an **unquantified residual on both sides** — see 6.5 |
| **Boston Corner** | MA → NY | 10 Stat. 602, 1855 | no (a hamlet) | immaterial — sub-county, not restated |
| **Delaware Wedge** | PA → DE | compact ratified 1921 | no (684 acres) | immaterial — sub-county, not restated |
| **Fair Haven strip** | VT → NY | 21 Stat. 72, 1880 | no | immaterial — sub-county |
| **Bristol main street** | TN → VA | 31 Stat. 1465, 1901 | no (half a street) | immaterial — sub-county |
| **Wisconsin ↔ Minnesota islands** | both ways | 40 Stat. 959, 1917 | no | immaterial — sub-county |
| **North Carolina ↔ South Carolina resurvey** | both ways | effective 1 Jan 2017 | no (19 homes) | immaterial — sub-county, and post-1990 so outside the file |
| **Ellis Island filled land** | NY → NJ | *New Jersey v. New York*, 523 U.S. 767 (1998) | no | immaterial — **no residents**, and post-1990 |
| Mississippi/Arkansas river tracts; NJ↔DE 1934; GA↔SC 1990; MO↔IL islands | various | various | no | immaterial — river bottom or island, no reported population |

All citations in that table are **ATTRIBUTED (relayed from PP909)** except the two in §1, which
§5 verifies directly.

### 6.3 Berkeley and Jefferson — immaterial for a structural reason, not a small one

These two counties carried **27,060 people in 1860** (Berkeley 12,525 + Jefferson 14,535 —
ATTRIBUTED), which is far from negligible. They are nonetheless immaterial **here**, because they
moved from Virginia to West Virginia and the correction this repo applies is `VA + WV`: the
transfer is **inside the sum** and cancels. Saying "too small" would be wrong; the right statement
is that the arithmetic is invariant to it.

### 6.4 Massachusetts ↔ Rhode Island — the case the empirical technique could not have caught

This is the one the delegated sweep contributed that §4's method would have missed, and it is worth
being explicit about why. The 1862 exchange moved the whole Massachusetts town of **Pawtucket** and
most of **Seekonk** (which became East Providence, RI) — Seekonk's own population falls **2,662
(1860) → 1,021 (1870)** (ATTRIBUTED). Both states already existed and neither was carved out of the
other, so §4.3's "which state appears before it held electoral votes" scan cannot see it, and the
parent/child sum has no parent to reconcile against.

**It is nonetheless immaterial, and the Bureau's own rule is why.** The transfer was **town-level,
not whole-county**, so under §5.1 the file did **not** restate it — and the Rhode Island state note,
which describes the 1862 exchange as "a sizable exchange of territory," **specifies no population**,
which is exactly what §5.1 says happens when no revision was made. So the file's Massachusetts 1860
(1,231,066) and Rhode Island 1860 (174,620) are already the **as-enumerated** figures, which are
also the apportionment basis for the 1864 and 1868 elections. **No correction is owed.**

Note the direction of the luck: had the transfer been whole-county, this would have been a third
material case affecting two elections at roughly 2–3% of Rhode Island.

### 6.5 The Toledo Strip — classified immaterial, with a residual on BOTH sides

**An earlier draft got this backwards and a later one over-corrected.** The first said the strip's
1830 people "belong to **Ohio**" and declined to rule; the second ruled, but cleared Ohio outright.
What is actually established is narrower than either.

**Established: the strip was never restated** (VERIFIED as to the file arithmetic; the Bureau quote
is **ATTRIBUTED**, since the 1996 volume is not in the local corpus and this is a reading of it, not
a reproduction anyone here can re-run). The Michigan note says the pre-statehood coverage *"included
population in the strip that was ceded to Ohio in 1836"*, and the tell is the adjacent clause, which
says the 1820 and 1830 censuses also covered settlements in present-day Wisconsin *"**shown under
that State**."* The Wisconsin population was moved; the strip's was not. Within the file,
**Michigan (28,004) + Wisconsin (3,635) = 31,639**, the enumerated Michigan Territory total for 1830
(the two file figures VERIFIED; the territory total **ATTRIBUTED**, not sourced from a primary
table). Neither leg suffices alone — the arithmetic is also consistent with the strip never having
been in Michigan Territory's total — so the quote is load-bearing.

**Not established: that Ohio is therefore clean.** If the strip was never restated, its people sit
in Michigan's column and are **absent from Ohio's** — and Ohio held the strip at the 1840 election.
So Ohio's figure is short by exactly what Michigan's is long: **an equal-and-opposite residual, not
an absence of one.** A previous revision cleared Ohio by calling 937,903 "the basis its 21 electoral
votes were apportioned on" while convicting Michigan because its figure "includes a strip that was
Ohio's" — two different criteria, applied in one paragraph, with the switch unnamed. That is the
open question in §6.7, and this section does not pretend to have settled it.

**The ruling, which does not depend on resolving that:** **IMMATERIAL**, because condition 3 of the
§3 threshold fails — **no source gives the strip's population.** The best figure located is Toledo
*city* at roughly 1,205 in 1835 (ATTRIBUTED, and a city is not a strip). Note what this ruling rests
on: unquantifiability alone. It is **not** the structural clearance Massachusetts ↔ Rhode Island
gets in §6.4, where the whole-county rule shows there is no error to measure.

**Which elections.** The cession took effect at Michigan's statehood on **26 January 1837**, which
*postdates* the November **1836** election. On a borders-at-election reading only **1840** is
affected; on an apportionment-basis reading the question does not arise for Michigan at all in 1836,
since its three electoral votes came from its admission act rather than from the 1830 apportionment.
An earlier revision named both years without noticing that its own date excluded one.

**Read "immaterial" here as "cannot be corrected", not "is small."** Michigan's 1830 base is only
28,004, so a strip of even 1,000 people is **3.6%** of its denominator — several times Alexandria's
0.79%–0.91%, and well past the ≥1% screen §3 rejected as a primary test. **This is the one case
where the adopted threshold and a magnitude threshold disagree**, and it is stated rather than
buried: a rule keyed on quantifiability rules out a case a rule keyed on size would rule in.

**What would close it** is one bounded figure: the 1830 census enumeration for the strip's territory
within Monroe County, Michigan Territory.

### 6.6 An open question this sweep raises and does NOT answer

**Which footprint should a per-capita denominator use — the borders in force at the *election*, or
the basis the state's *apportionment* was computed on?** They differ exactly when a boundary moved
between a census and an election, which is every case in this report.

This is not a loose end of the write-up; it decides numbers:

- **Toledo (§6.5).** Under borders-at-election, Ohio carries a residual for 1840. Under
  apportionment-basis, it does not. The same choice governs Michigan.
- **Alexandria, and the headline count in §1.** Retrocession took effect **7 September 1846**
  (§5.4), so the **1848** election was held on post-retrocession borders — Alexandria was Virginia
  in November 1848. Under borders-at-election, case 2 affects **six** elections, 1824–1844. The
  **seven** stated in §1 and used by the script is the *apportionment-basis* count: 1848's 17
  electoral votes were apportioned from the 1840 enumerated Virginia, which excluded Alexandria.

> **SUPERSEDED IN PART — 2026-09-21, by #253/D066.** The open question below is **answered**:
> a per-capita denominator uses the **borders in force at the election**. So case 2 affects **six**
> elections (1824–1844), not seven, and Ohio **does** carry a Toledo residual for 1840 — equal and
> opposite to Michigan's, and still immaterial, because §6.5's unquantifiability ruling is
> untouched. D066 also corrects a premise stated below and in #253: `governing_census_year` is a
> *vintage* selector only and encodes no footprint answer, so the contradiction was between **this
> report** and `conform.py`, not between two modules. The text below stands as what the sweep
> concluded; read D066 over it.

**This report uses the apportionment basis throughout** — that is what `governing_census_year`
expresses, and it is why §1 says seven. It did **not** establish that this is the right choice, and
an earlier revision silently used the other one to clear Ohio.

**The repo has a stake and a stated position.** `usvote/census/conform.py:115-130` says the question
is *"whether a figure is on the borders **in force at the election**"* and that asserting
`at_election` for all fifty states *"is precisely the unverified claim **#208** exists to settle."*
So the at_election reading has a claim on this issue's remit that this report does not discharge.

**Filed as #253**, because #251 would otherwise inherit the ambiguity into a `src/` constant: the
correction it implements is six elections or seven depending on the answer.

### 6.7 Explicitly out of scope, stated rather than omitted (AC-3)

- **Maine / Massachusetts, 1820** — pre-1824. Its footprint effect is real (present-day
  Massachusetts figures for 1790–1810 exclude Maine) but every affected election precedes the span.
- **The original DC cession, 1791** — pre-1824. Only the 1846 retrocession is in scope.
- **Kentucky from Virginia (1792), Tennessee from North Carolina (1796), Vermont (1791)** — pre-1824
  whole-state separations, all restated by the file under §5.1, none affecting an in-span election.
- **Cases that moved nothing** — the Honey War (*Missouri v. Iowa*, 1849), Carter Lake
  (*Nebraska v. Iowa*, 1892), McKissick's Island, *Michigan v. Wisconsin*, *California v. Nevada*,
  *Maryland v. West Virginia*, *Virginia v. Tennessee*, the Georgia/Tennessee 35th-parallel dispute.
  Each **confirmed** a line already being administered rather than transferring territory
  (ATTRIBUTED). Ruling them out matters as much as ruling the others in.
- **State ↔ federal territory** — the Platte Purchase (1837), Greer County (1896, ~5,336 people in
  1890), Texas's 1850 cession, Nevada's 1866 additions. These move population between a state and
  *federal territory*, so no other state's denominator changes. Listed because the issue asked that
  they be distinguished rather than merged with state-to-state transfers.
- **International** — the Chamizal transfer (1963/67) and the Rio Grande *bancos* move land between
  a US state and Mexico. Outside both categories; flagged, not investigated.

---

## 7. Recommendations

1. **Correct the Alexandria overstatement** for the 1800/1810/1820/1830/1840 censuses, as a
   **separate provenance-carrying constant** — *not* as a second term inside
   `apply_virginia_boundary_correction`. That function's docstring makes a load-bearing claim that
   the correction "needs no external source," because the file proves the arithmetic on its own.
   Alexandria County's population is **not in the file**, so folding it in would launder an
   externally-sourced figure under a self-verifying docstring. It is also a different mechanism
   (1846, DC↔VA) from that function's job (1863, VA→WV).

   **The constant's provenance is unusually strong and should be cited, not derived** (§5.2): the
   Census Bureau publishes the five figures itself, in the Virginia State note of the companion
   volume to the working paper this file comes from. Cite that note. **Do not compute the term as
   `enumerated_DC − file_DC`** — that derivation is what this report used to *find* the case, and it
   would make the correction depend on a second external series when a published figure exists.
   **The 1810 cell is the one exception and it is now resolved, not ambiguous** (§5.3): use
   **8,552**, and comment that Virginia Note 2's `8,852` is a defect in the printed note, corrected
   by the same volume's District note and `Arlington` row. An earlier revision of this report called
   it an OCR artifact and told #251 to carry the ambiguity forward; both were wrong. #251 carries a
   correction comment covering the 8,552 value — but **that comment predates this report's final
   narrowing**, so it still reflects the retracted "three readings" count and the retracted "Ohio is
   clean" ruling. A second comment re-syncs it; read §5.3 and §6.5 here as authoritative over
   either. It governs no in-span election either way.

2. **Rewrite, do not retire, the `(see #208)` hedge** in `usvote/census/transform.py`. It currently
   reads *"computed by the same arithmetic, but not re-verified against a primary source for this
   census."* The temptation on closing this issue is to delete it as discharged. **That would be
   wrong**: this sweep's finding is that those five censuses are *not* clean — they carry a known,
   systematic overshoot. The replacement must say the residual is explained, quantified, and
   corrected.

3. **Fix two adjacent statements that are now known to be slightly false** for 1800–1840: the row's
   `basis` is set to `as_enumerated` (`census/transform.py:311`) and its note says *"restated onto
   the borders in force"* — but the figure also includes Alexandria, which was **not** in Virginia's
   borders at those censuses. Both become true once recommendation 1 lands, and not before.

4. **`VIRGINIA_VERIFIED_CENSUSES` needs a third state, not a wider membership.** It is currently a
   binary set (`{1790, 1850, 1860}`, `transform.py:124`). **Its own docstring says the check is that
   the file's Virginia + West Virginia sum "reproduces the **separately-published** enumerated
   Virginia exactly"** — so it already depends on an external total, and describing it as
   "file arithmetic alone" (as an earlier draft of this report did, and as #251 inherited) is a
   misdescription of the thing being changed. The real distinction is *which* external check:
   1790/1850/1860 are confirmed against a published **Virginia total**, whereas 1800–1840 are
   composed from two published **component** series. That is still a third category the binary set
   cannot express, so the recommendation stands; the characterisation does not.

   **And the function's docstring overstates what the exact sums prove** (§5.5). The Bureau states
   that before 1860 the Virginia/West Virginia split "cannot be done exactly, because the present
   Virginia-West Virginia State boundary did not correspond to county boundaries in 1850 or
   earlier." The three exact reconciliations show the split is **exhaustive**, not that it is
   **accurate** county by county. The docstring currently reads as though they settle both.

5. **Assert non-collision with `BOUNDARY_SUCCESSIONS`** (#182/D060). Alexandria's affected censuses
   (1800–1840) do not overlap the succession's (1860 → the 1864/1868 elections), so there is no
   conflict — but both now edit Virginia's population by census, and the non-overlap should be
   *asserted* rather than assumed.

6. **Scope note: none of 1–5 lands under #208 — they are filed as #251.** They are `src/` work with a test gate, in a
   `research`-routed row that has none. They go to a follow-up `code` issue, on the #183 → #243
   precedent, and **the `docs/corrections.md` catalog row goes with them** — this repo's pattern is
   constant + test + catalog row landing together, so a row describing a constant that does not yet
   exist would be a false claim about the tree. **Filed 2026-09-20 as #251**, carrying all of 1–5
   as acceptance criteria plus the sequencing note in 7.

7. **Note for #245.** If the per-capita series reaches the public snapshot before this correction
   lands, **six** elections (1824–1844, per #253/D066) ship with a denominator known to be
   ~0.8–0.9% high, and correcting it later
   moves the snapshot content hash (D034 cutover). Sequencing the fix ahead of #245 avoids
   publishing a figure this repo already knows is wrong.

---

## Deferrals and open items

Stated in one place so nothing here reads as delivered.

| Item | Disposition | Why |
|---|---|---|
| **AC-5** — `docs/corrections.md` row + provenance-carrying constant + test | **Deferred to #251** | `src/` work with a test gate, inside a `research`-routed row that carries none. The catalog row lands **with** the constant, never ahead of it: a row describing a constant that does not exist would be a false claim about the tree. Owner-approved at the plan gate; #183 → #243 precedent. |
| **#208 itself** | **Stays open until #251 lands** | AC-5 is dispositioned, not discharged, so this PR does not close the issue. |
| **Toledo Strip** (§6.5) | **Classified immaterial; residual unquantified on *both* sides** | Condition 3 of the §3 threshold fails. One figure closes it — the 1830 enumeration for the strip within Monroe County, Michigan Territory. |
| **Which footprint a denominator should use** (§6.6) | **CLOSED 2026-09-21 — #253/D066: borders at the election** | Case 2 affects **six** elections (1824–1844); Ohio **does** carry a Toledo residual for 1840, equal and opposite to Michigan's and still immaterial on §6.5's unquantifiability ruling. This report used the apportionment basis throughout and did not establish that it should; D066 supersedes that choice. §3.1's rank table is unaffected — its rows are correct as computed, and only 1848's disposition changes. |
| **1810 Alexandria cell** (§5.3) | **Resolved to 8,552**, Virginia Note 2's `8.852` recorded as a defect in the printed note | Governs no in-span election. |
| **1810 / 1820 enumerated Virginia** (§5.4) | **CONTRADICTED between two Bureau publications**; original-return pair used | The file's components close only on that pair. |
| **§6's citations** | **ATTRIBUTED (relayed)**, not reproduced | The documentary sweep leaned on USGS Professional Paper 909, which this report's author did not read. §4 and §5 were run or read directly. |

---

## Appendix A — reproducing §4

The script is committed beside this document as
[`research-boundary-sweep.py`](research-boundary-sweep.py) — the same arrangement
`research-pv-overlap.md` / `research-pv-overlap.sql` already uses. It needs both local corpora and
**no network and no database**:

```
uv run python .claude/specs/research-boundary-sweep.py
```

It reads `USVOTE_CENSUS_CORPUS_DIR` and `USVOTE_EC_HTML_DIR` when set, and otherwise falls back to
this developer's corpus paths. Check C is the one that needs the Archives corpus (for each
election's `total_electoral_votes`); checks A and B need only the census workbook.

**Checks A and B assert their headlines and the script exits non-zero on failure.** An earlier
revision printed its results and asserted nothing — a degraded input would have produced a plausible
table rather than an error, which is the failure mode this whole report is about. **Check C is the
exception and it is deliberate:** it computes and prints the rank table, raising only on missing
input, because §3 designates rank as a *diagnostic* rather than as the gate. An earlier wording of
this appendix said "every check", which over-claimed for exactly that one. The asserts were
checked for non-vacuity by mutation: perturbing `ENUMERATED_DC`, `ENUMERATED_VA`, `NATIONAL` or the
expected census set by one each turns the run red. Check C additionally **names every state
excluded from a ranking** with its reason and its electoral votes — `(1848, Texas)` at 4 EV is the
one live exclusion, and it is why that year's denominator reads 29 rather than 30.
