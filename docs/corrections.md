# Historical data corrections catalog

Each ingest patches or tolerates a handful of real historical anomalies in its source
data. The **Electoral College** catalog comes first, then the **UCSB popular-vote**
catalog; each source's constants live in that source's own module, per the
source-namespacing convention (D006/D015). A third section follows them and is a
different kind of thing — the **in-repo popular-vote absence catalog** (#140), which
corrects nobody's data and is instead an original compilation of historical facts this
project asserts on its own public-domain evidence.

The Electoral College pipeline patches a handful of real historical anomalies in the
National Archives source data. Each is **hard-won correctness** — a value confirmed
against the Archives' own Notes sections (or, for 2000, a direct email reply from the
Archives) — and must survive the notebook → package migration as an **explicit,
documented, tested** correction rather than a scattered inline edit.

This file is the human-browsable **index**. The authoritative, machine-readable
source of truth is the set of provenance-carrying constants in
[`src/usvote/transform.py`](../src/usvote/transform.py) (the "Corrections" section
near the top of the module); each is locked by a test in
[`tests/test_transform.py`](../tests/test_transform.py). Extending EC coverage below
1892 toward the ~1824 comparison floor (#32) surfaced the 19th-century anomalies in
the table below; adding a new election year follows the same pattern: one constant
entry + a small `apply_*`/reconcile function, one test, and one row in the table.

## Catalog

| Year(s) | Anomaly | Correction applied | `transform.py` constant | Source / provenance |
|---|---|---|---|---|
| 2016 | Table 2 collapses the seven faithless electors' votes into two unnamed "Other" columns | Replace the placeholders with the real recipients — Bernie Sanders, Ron Paul, John Kasich, Colin Powell, Faith Spotted Eagle — and their per-state electoral votes | `OTHER_CANDIDATES_2016`, `OTHER_VOTES_2016` (applied by `apply_other_candidates`, `_votes_matrix`) | Names + electoral-vote counts collected manually from the [Archives 2016 Notes](https://www.archives.gov/electoral-college/2016) |
| 2016 | Colin Powell has no politically-defined home state (he grew up in NY but was not a politician) | Home state left `None` rather than guessing | `OTHER_CANDIDATES_2016` (`state=None`) | Editorial; [Archives 2016](https://www.archives.gov/electoral-college/2016) |
| 2016 | The generic name parser mis-splits the two-word surname "Faith Spotted Eagle" (middle="Spotted", last="Eagle") | Force `name_middle=None`, `name_last="Spotted Eagle"` | `SPOTTED_EAGLE_NAME`, `SPOTTED_EAGLE_LAST` | Editorial (name structure) |
| 2016, 2020 | Trump is printed "Donald Trump" (2016 Table 2, New York) but "Donald J. Trump" (2020 Table 2, Florida), so his two state rows would not collapse to one candidate | Unify the 2016 spelling to the canonical "Donald J. Trump" (+ middle initial "J.") before aggregation, so he becomes one candidate spanning NY/FL | `CANDIDATE_NAME_FIXES` (applied in `_candidate_states`; vote side via `reconcile_vote_candidate_names`) | Archives [2016](https://www.archives.gov/electoral-college/2016) / [2020](https://www.archives.gov/electoral-college/2020) |
| 1972 | Table 2 prints "George McGovern"; Table 1 has "George S. McGovern" | Rewrite the Table-2 name to the canonical form and fill the middle initial "S." | `CANDIDATE_NAME_FIXES` | Archives [1972](https://www.archives.gov/electoral-college/1972) |
| 1996 | Table 1 (party) prints "Bob Dole"; Table 2 prints "Robert Dole", so the two tables' names would not reconcile | Rewrite the Table-1 name to "Robert Dole" | `PARTY_NAME_FIXES` | Archives [1996](https://www.archives.gov/electoral-college/1996) |
| 2000 | DC elector Barbara Lett-Simmons cast a blank ballot, so DC cast only 2 of its 3 allotted electoral votes; the national Totals row is likewise 537 of 538. A naive row-sum check reads this as a broken parse. | Record the confirmed 1-vote shortfall so `assert_row_votes_sum_to_total` adds it back instead of raising; the allotment (`total_electoral_votes=3`) is preserved | `ELECTORAL_VOTE_SHORTFALLS` (used by `_expected_shortfall`) | [Archives 2000 Notes](https://www.archives.gov/electoral-college/2000) **and a direct email reply from the National Archives** confirming total=3 / cast=2 is correct |
| 1824, 1832, 1836, 1860 | Table 2 collapses the minor presidential candidates into a single unnamed "Others" column (parsed with `state=None`, like 2016's "Other") | Split "Others" back into its named candidates with the per-state electoral votes read from each year's Notes: **1824** Crawford (41) / Clay (37); **1832** Floyd (11) / Wirt (7); **1836** White (26) / Webster (14) / Mangum (11); **1860** Breckinridge (72) / Bell (39) | `OTHER_CANDIDATES_1824/1832/1836/1860`, `OTHER_VOTES_*` (applied by `apply_other_candidates`, `_votes_matrix`) | Per-state counts from each year's Archives Notes ("&lt;State&gt; cast N votes for &lt;Name&gt; as President"): [1824](https://www.archives.gov/electoral-college/1824), [1832](https://www.archives.gov/electoral-college/1832), [1836](https://www.archives.gov/electoral-college/1836), [1860](https://www.archives.gov/electoral-college/1860) |
| 1824 (era) | The Archives prints the early Democratic-Republican party inconsistently — "Democratic-Republican" (Jackson) vs. "D-R" (Adams) — for the same party, so one party would read under two labels and the "-" join delimiter would mis-split "D-R" into a spurious `party_2` | Normalize the label to "D-R" before aggregation, and join a candidate's distinct parties on `|` (never present in a party code) instead of "-" | `PARTY_CODE_FIXES`, `PARTY_JOIN` (in `_candidate_parties`) | [Archives 1824](https://www.archives.gov/electoral-college/1824) |
| 1832 | Two of Maryland's electors did not vote, so Maryland cast 8 of its 10 allotted votes (Jackson 3, Clay 5); the national Totals row is likewise 286 of 288 | Record the 2-vote shortfall so `assert_row_votes_sum_to_total` adds it back; the allotment is preserved and the Totals shortfall is derived | `ELECTORAL_VOTE_SHORTFALLS` | [Archives 1832 Notes](https://www.archives.gov/electoral-college/1832) ("two electors from Maryland did not vote, making the total number of votes cast 286") |
| 1824 | No candidate reached an Electoral College majority; Jackson led (99 EC votes) but the House elected John Quincy Adams (84), so the EC leader is *not* who took office | Mark the actual office-holder with `took_office=True` (Adams) while EC-winner stays derived from `president_electoral_rank == 1` (Jackson) — the two are kept distinct, not conflated | `CONTINGENT_OFFICE_HOLDERS` (applied by `_add_took_office`) | [Archives 1824 Notes](https://www.archives.gov/electoral-college/1824) |
| 1868 | The page ends with **two totals rows** — `Totals (excluding Georgia's votes)` 285 and `Totals (including Georgia's votes)` 294 — and marks neither authoritative, because the Senate and House deadlocked over whether Georgia's nine votes counted. Downstream, `state == "Totals"` is a single per-year row, so both cannot survive. | Keep the totals row whose `total_electoral_votes` equals the sum of the page's own per-state allotments — **derived from the source, not a curated literal**, and not a way of taking a side: the allotment column counts electors *appointed*, and Georgia's nine were appointed beyond dispute. That resolves 1868 to **294** by D041's existing rule. Zero or several reconciling rows raise rather than guess. | `_select_totals_row`, `TOTALS_LABEL_PREFIX` (`parse.py`) | [Archives 1868](https://www.archives.gov/electoral-college/1868); re-verified against the fixture's own tokens — its 37 state rows sum to 294 / Grant 214 / Seymour 80, matching the *including* row exactly (D043 §1, D044) |
| 1868 | Georgia's votes are printed **parenthesized**, `(9)`, in Seymour's column — the Archives' marking for votes cast but whose counting was in question. No other cell in the corpus uses the notation. | Parse a *wholly* parenthesized cell as the number it wraps, then flag the row `count_status='disputed'` with the Archives' own sentence as the reason — `disputed`, not `not_counted`: Congress decided **nothing** here (D043 §3/§5). **No** `ELECTORAL_VOTE_SHORTFALLS` entry is added — those votes were *cast*, so the row still sums to its allotment and the two mechanisms stay disjoint by construction (D043 §6). Aggregate (`is_total`) rows stay `counted`: one enum value cannot say "80, of which 9 disputed" (D044) | `_PARENTHESIZED_VOTES_RE` (`parse.py`); `COUNT_STATUS_OVERRIDES` (`transform.py`); the enum in `count_status.py` | [Archives 1868 Notes](https://www.archives.gov/electoral-college/1868): "The electoral votes of Georgia were contested and the Senate and the House of Representatives could not agree whether to accept – and count – them or not." |
| 1868 | Mississippi, Texas and Virginia carry a dash in the **allotment** column itself (`Electoral Vote of Each State`), not just in the vote columns — they were not yet readmitted and appointed **no** electors. | No correction needed: `-` already reads as `0`, so they load as genuine 0-electoral-vote rows. Pinned by a test, because the distinction is load-bearing — contrast 1872's Arkansas and Louisiana, which also print `-` but *did* appoint electors whose returns were never counted (D043 §2, #144) | (`parse.py`'s `-` → 0 rule; cross-checked by `PV_ABSENCE_CATALOG`'s zero-EV assert) | [Archives 1868 Notes](https://www.archives.gov/electoral-college/1868): "Mississippi, Texas, and Virginia did not participate in the election because they were not yet readmitted to the Union." |
| 1872 | Table 2 collapses **four** Greeley-elector recipients into one unnamed "Others" column — the widest split in the corpus. Greeley died between the popular vote and the meeting of the electors, so his pledged electors scattered their presidential votes. | Split "Others" back into Brown (18) / Hendricks (42) / Jenkins (2) / Davis (1), with per-state counts read from the page's own Table 2 notes 4-9. Every split reproduces the parsed Others column in all six affected states and each recipient's total matches note 10 and Table 1 — so this half needs **no** external source. | `OTHER_CANDIDATES_1872`, `OTHER_VOTES_1872` (applied by `apply_other_candidates`, `_votes_matrix`) | [Archives 1872](https://www.archives.gov/electoral-college/1872) Table 2 notes 1 (home states) and 4-10 (per-state counts) |
| 1872 | **17 electoral votes that were cast are missing from the table entirely** — they exist only in footnote prose. Georgia's president side prints 8 against an allotment of 11 (Greeley's column reads `-`); Arkansas and Louisiana print `-` in every cell. A row-sum check reads Georgia as a broken parse. | Synthesize the votes from the notes *before* the row-sum assert, then flag each `count_status='not_counted'` with the source's own sentence: Georgia's 3 for Greeley (rejected by House resolution), Arkansas's 6 and Louisiana's 8 for Grant (returns refused). Georgia then reconciles at 11 = 6 + 2 + 3. **This corrects D043 §6**, which assumed the rejected votes were already rows. **No** `ELECTORAL_VOTE_SHORTFALLS` entry — these votes were cast, so the two mechanisms stay disjoint. | `UNPRINTED_ELECTORAL_VOTES`, `COUNT_STATUS_OVERRIDES` (`transform.py`); enum in `count_status.py` | [Archives 1872](https://www.archives.gov/electoral-college/1872) notes 3 and 4 for the refusals and Georgia's recipients; **H. Misc. Doc. No. 13, 44th Cong., 2d Sess. (1877)**, *Counting Electoral Votes* (printed by order of the House, public domain) for the AR/LA **recipient**, which the Archives page does not name: "the votes of Arkansas, 6, and Louisiana, 8, cast for U. S. Grant" |
| 1872 | **The Archives' own totals row (352) is not the year's electoral-vote denominator.** Arkansas and Louisiana print `-` in the allotment column, but both appointed their full complement — only their *returns* were refused. Congress announced a whole number of **366**, majority 184. | Restore the two allotments (AR 6, LA 8), then recompute the totals row's allotment from the state rows so 366 is **derived, never entered** (D044 §2's discipline, applied to the denominator). This is a **documented divergence from the source's printed figure**, not a parse fix. Kept a separate constant from the vote synthesis above even though the numbers coincide — the identity is a coincidence of this year, and `assert_row_votes_sum_to_total` cross-checks the two for free. | `APPOINTED_ELECTORS_NOT_IN_TABLE` (applied by `_apply_appointed_elector_corrections`) | **CRS Report RL30769**, *Electoral Vote Counts in Congress* (2000-12-13, a US Government work): the announced whole number of **366** with **349 counted** and 17 rejected (GA 3, AR 6, LA 8). Independently derivable from the **Apportionment Act of 1872**, 17 Stat. 28 — 37 states x 2 + 292 representatives = 366; AR 4+2 = 6; LA 6+2 = 8 |
| 1868, 1872 | A single electoral-vote measure cannot state both what electors **cast** and what Congress **counted** — 1868 Seymour is 80 cast / 71 counted, 1872 Grant is 300 / 286 — so either the familiar published totals or the rejected votes had to be absent from the fact. | Carry **both**: `president_electoral_votes` (cast, unchanged) and `president_electoral_votes_counted` (new). The counted rule is strict — `disputed` is excluded alongside `not_counted` — which makes *both* of the Archives' printed 1868 totals rows reproducible, 294 as cast and 285 as counted. Counted is what `president_electoral_rank`, `took_office` and `hybrid.ec_share_full` are computed from, because who won is settled by the votes Congress counted. | `COUNTED_VOTES_COLUMN` (`count_status.py`); `_add_counted_votes`, `assert_counted_matches_count_status`, `assert_counted_totals_equal_state_sum` (`transform.py`) | D046. Derived from the Archives pages already cited above — no new external source; the counted measure is a function of `count_status`, not a separately-sourced figure |

## UCSB popular-vote catalog

Source-namespaced per D006/D015, exactly as MIT's reconciliations are: these anomalies
are in the **UCSB** popular-vote source, so their constants live in that subpackage
rather than the EC `transform.py` — parse-stage anomalies in
[`src/usvote/ucsb/parse.py`](../src/usvote/ucsb/parse.py) (locked by
[`tests/unit/test_ucsb_parse.py`](../tests/unit/test_ucsb_parse.py)) and transform-stage
ones in [`src/usvote/ucsb/transform.py`](../src/usvote/ucsb/transform.py) (locked by
[`tests/unit/test_ucsb_transform.py`](../tests/unit/test_ucsb_transform.py)). The
`ucsb/parse.py` constant column below names which module each lives in.

One difference from the EC catalog above is worth stating plainly: the EC corrections
*rewrite* wrong values, whereas most UCSB entries are anomalies the parser must
**tolerate without correcting** — UCSB is not the source of truth for anything the
Electoral College spine already carries (D006), so a wrong percent is recorded and
worked around, never silently "fixed" into a number UCSB never published.

| Year(s) | Anomaly | Handling | `ucsb/` constant (module) | Source / provenance |
|---|---|---|---|---|
| 1836 | Rhode Island's third candidate cell is a single `-` (one hyphen), where every other year spells "not on the ballot" as `--`. A literal `"--"` test reads it as an unparseable vote and raises. | Model the absence token as a **set**, not a literal, so both spellings parse to `None` — never to `0` (D024 §2) | `ABSENT_VOTE_TOKENS` (`parse.py`) | UCSB [1836](https://www.presidency.ucsb.edu/statistics/elections/1836); `-` appears in exactly this one cell corpus-wide |
| 1860 | **Vermont, Virginia and Wisconsin** each publish the Douglas percent as a duplicate of the *next* candidate's (Breckinridge's) — `4.16`, `44.46` and `0.58` respectively, against true values of 19.57%, 9.74% and 42.73%. The columns are provably aligned: each row's four candidates sum to exactly its TOTAL VOTE, and **all 28 other 1860 states agree with their published percent to 0.00pp**, which is what shows these are isolated source typos rather than a column shift. | Tolerated, never rewritten (UCSB is not the source of truth here). The percent cross-check asserts on the **mismatch rate**, not per cell, so isolated typos do not fail the year while a systematic shift still does. At transform these three cells are flagged `reliability='unreliable'` — the page contradicts itself and we cannot know which published number is wrong | `PERCENT_MISMATCH_RATE`, `PERCENT_TOLERANCE` (`parse.py`); `_cell_reliability` (`transform.py`) | UCSB [1860](https://www.presidency.ucsb.edu/statistics/elections/1860); the three-state extent established in #36 (the earlier catalog entry recorded Vermont only) |
| 1968 | Utah publishes `31.1` where 156,665/422,568 is 37.1 — transposed digits. That row's candidates also reconcile against its total. | Tolerated, and flagged `reliability='unreliable'`, as above | `PERCENT_MISMATCH_RATE` (`parse.py`); `_cell_reliability` (`transform.py`) | UCSB [1968](https://www.presidency.ucsb.edu/statistics/elections/1968) |
| 1864, 1868 | **Fourteen states took no part in the election at all** — 1864's eleven Confederate states, and 1868's Mississippi/Texas/Virginia, not yet readmitted. The defining property is that this has **no markup whatsoever**: the state's row is simply absent from the page, so it cannot be parsed, only enumerated (D024 §4 case 2). | Enumerated with its cause, and emitted as a `not_participating` row in `dwh.pv_state_status` — **never** as a null or zero vote in `pv_votes` (D024 §1/§2, D005). Cross-checked against the EC spine, which carries these states with `total_electoral_votes = 0`. All 14 entries are retained, and since #143 ingested 1868 all 14 are **consumed** (it was 11 while 1868 was gated out of the EC spine). The scope is derived from `ec_ingest_years()`, so admitting the year required no edit under `usvote/ucsb/` | `UCSB_NONPARTICIPATING_STATES` (`transform.py`) | Settled history; the 1868 trio independently corroborated by the EC spine's own `UNSUPPORTED_EC_YEARS` note, and every in-scope entry verified against `dwh.votes` |
| 1852, 1964–2016 | UCSB prints two state labels that differ from the canonical `dwh.state` key: `New jersey` (1852, a lower-case "j" typo) and `Dist. of Col.` (1964–2016; 2020/2024 print `District of Columbia` in full). Unreconciled, DC reads as two different states across the series and the roster assert reports both as phantom states. | Rewritten to the canonical full name before anything roster-related. The map is **exhaustive** over all 53 corpus labels rather than exceptions-only, so an unseen future spelling fails loudly instead of vanishing in a join | `UCSB_STATE_RECONCILIATIONS` (`transform.py`) | UCSB state-column labels, all 60 pages; RHS per the EC state dimension (TIGER2019) |
| 1872 | Kentucky's published percents (45.5 / 54.5) contradict its own votes: 88,970 / 100,208 of a 191,552 total is 46.45 / 52.31. They are also the year's only pair summing to exactly 100.0, where every other state leaves room for the minor candidates. **No single denominator reproduces both**, since 88,970/100,208 = 0.888 while 45.5/54.5 = 0.835 — so this is not a "computed against a different denominator" case; the two figures are inconsistent with each other. Every other 1872 state agrees with its votes to ≤0.06pp, which is what shows this is an isolated source error rather than a column misalignment. | Tolerated, as above — and now **flagged per cell**: since #144 ingested 1872 both Kentucky rows carry `reliability='unreliable'`. The votes are never edited; the flag marks the cell (D017) | `PERCENT_MISMATCH_RATE`, `RELIABILITY_UNRELIABLE` | UCSB [1872](https://www.presidency.ucsb.edu/statistics/elections/1872) |
| 1872 | UCSB's candidate **column header is misspelled `HORACE GREEFLEY`** (the body prose spells it correctly three times). An unmapped header is dropped, silently losing the year's second-largest popular vote — 2.8M votes, 43.8% nationally. | Reconciled to the canonical `Horace Greeley` in the curated candidate map, where a source's spelling meets the canonical one (D006), rather than patched at the parse seam. The reciprocal completeness guard (#38) is what makes the drop impossible to miss: it raised on this column | `UCSB_CANDIDATE_RECONCILIATIONS` (`ucsb/reconcile.py`) | UCSB [1872](https://www.presidency.ucsb.edu/statistics/elections/1872) header cell; canonical RHS from [Archives 1872](https://www.archives.gov/electoral-college/1872) |
| 1872 | Four candidates received electoral votes but have **no UCSB column at all** — Greeley died between the popular vote and the meeting of the electors, and his pledged electors scattered their presidential votes across Hendricks (42), Brown (18), Jenkins (2) and Davis (1). None of the four ran for president. | Exempted from the reciprocal getter-completeness guard, which otherwise reads a getter with no popular-vote row as a reconciliation miss. This is a **third cause** alongside the existing two (legislature-chosen slates, faithless electors), and the largest single-year addition to the set | `EC_GETTERS_WITHOUT_POPULAR_VOTE` (`getters.py`) | [Archives 1872 Notes](https://www.archives.gov/electoral-college/1872): "Following Greeley's death, electors in several states cast their votes variously for President or Vice President." |
| 1864, 1944 | The totals row is labelled singular `Total`, not `Totals`. A `== "Totals"` test drops the row, leaves `totals=None`, and silently no-ops the sum validator. | Match against a set of labels, case-insensitively | `TOTALS_LABELS` | UCSB [1864](https://www.presidency.ucsb.edu/statistics/elections/1864), [1944](https://www.presidency.ucsb.edu/statistics/elections/1944) |
| 1940 | The state-column header is plural `STATES`, not `STATE` — and `select_results_table` keys on exactly that cell, so a singular-only test finds no results table and the year reads as having no popular vote. | Match against a set of labels, case-insensitively | `STATE_HEADER_LABELS` | UCSB [1940](https://www.presidency.ucsb.edu/statistics/elections/1940) |

Structural (rather than per-year) UCSB format quirks — the six header layouts, the
trailing summary blocks, 1976's narrower header — are **not** data corrections and are
catalogued instead in [`ucsb-html-formats.md`](ucsb-html-formats.md) §9, with the
reasoning that produced each rule.

## In-repo popular-vote absence catalog (#140)

**This is not a correction to anybody's data**, and saying so plainly matters — the two
catalogs above are organized around fixing or tolerating what a source got wrong, and
this third one is not that. It is an **original, in-repo compilation**: the 32 pre-1976
`(year, state)` pairs at which no popular vote for president was held, each classified
from public-domain sources. Nothing upstream is being corrected. It lives here because
this file is where a reader looks for "which historical facts does this project assert,
and on what evidence" — which is exactly the question it answers.

**Why it exists.** Until #140, the pre-1976 `pv_status` classifications had one origin:
parsing UCSB's markup. UCSB grants no reuse rights and this repo is public (D022), and
the API snapshot is redistributable-only *at the source* (D030) — so a public surface
reporting a `pv_status` for every `(year, state)` back to 1824 (#139) cannot be built on
UCSB-derived rows. Enumerating the absences ourselves, with our own citations, is what
makes the classification ours to ship.

`UCSB_NONPARTICIPATING_STATES` **stays** and is not superseded: UCSB's own transform still
needs it to derive UCSB's roster. The two are independent, and that independence is the
whole design — `TestRealCorpus` uses UCSB as the **control** that validates this catalog,
inverting the dependency exactly as D016 already does for the PV facts.

What that control corroborates, stated precisely: both rosters take their `(year, state)`
**membership** from the same EC spine, because D024 §6 requires both to — so the shared
2,204-row count is the *design*, not a finding. What is genuinely independent is the
`pv_status` on each row (UCSB's parsed from their markup, ours curated with its own
citations), and above all the **32 absences**, which the test checks first and on their
own because they are the entire claim.

**On provenance, stated precisely.** The firewall is over *machine* provenance: no UCSB
byte, parse, or artifact reaches these classifications, and `tests/unit/test_layering.py`
enforces that structurally (in both directions — a `usvote/ucsb/` back-import would make
the control test circular). It is **not** a claim that the curator worked in ignorance of
UCSB. Each row is independently attested and independently cited; the exact coincidence
with UCSB's set is **corroboration**, and it is checked deliberately.

| Year(s) | Absence | Classification | `pv/` constant (module) | Source / provenance |
|---|---|---|---|---|
| 1824 | Six states' legislatures still appointed electors directly — Delaware, Georgia, Louisiana, New York, South Carolina, Vermont — so no popular presidential vote was held in them | `legislature_chosen` (they cast electoral votes; they just held no popular vote) | `PV_ABSENCE_CATALOG` (`pv/absences.py`) | *McPherson v. Blacker*, 146 U.S. 1, 27 (1892), which names all six; U.S. Const. art. II, § 1, cl. 2 |
| 1828 | Delaware and South Carolina alone retained legislative appointment (New York had moved to districts) | `legislature_chosen` | `PV_ABSENCE_CATALOG` | Bracketed by *McPherson* at 27–28 (legislature in 1824; general ticket in all states but S.C. "after 1832"); Delaware first voted popularly in 1832. **The Delaware Constitution of 1792 is not the instrument** — it carries no presidential-elector provision at all (checked 2026-08-07), so the appointment was statutory |
| 1832, 1836, 1840, 1844, 1848, 1852, 1856, 1860 | South Carolina's General Assembly appointed the state's electors in every election through 1860 — the last state to adopt a popular presidential vote | `legislature_chosen` | `PV_ABSENCE_CATALOG` | *McPherson*, 146 U.S. at 28: "After 1832 electors were chosen by general ticket in all the states excepting South Carolina, where the legislature chose them up to and including 1860." S.C. first held a popular presidential vote in 1868 |
| 1864 | The eleven Confederate states took no part. Nine appointed no electors and submitted no returns; **Louisiana and Tennessee did** submit returns via Unionist reconstruction governments, and Congress refused to count them — same classification, materially different history, so they carry their own citation | `not_participating` | `PV_ABSENCE_CATALOG` | Joint Resolution (H.R. 126, 38th Cong.), adopted before the 8 February 1865 count, declaring the states in insurrection not entitled to representation in the Electoral College. **Independently corroborated by the EC spine itself** — exactly these eleven carry `total_electoral_votes = 0` in 1864, and a test asserts the two sets are equal |
| 1876 | Colorado was admitted 1 August 1876, three months before the election and too late to organize one; its General Assembly appointed the state's three electors. The last time any state chose electors without a popular vote | `legislature_chosen` | `PV_ABSENCE_CATALOG` | Colo. Const. of 1876, Schedule § 19 (a one-time provision); Proclamation No. 230 (admission); Colorado Enabling Act, ch. 139, 18 Stat. 474 (1875) |
| 1868 | Florida's legislature appointed its electors (readmitted 25 June 1868, too late to organize an election); Mississippi, Texas and Virginia were not readmitted in time and cast no votes | `legislature_chosen` / `not_participating` | `PV_ABSENCE_CATALOG` | Omnibus Act, 15 Stat. 73 (25 June 1868), readmitting six states but not MS/TX/VA (readmitted 1870). **Catalogued in #140 while the year was still gated, and consumed unchanged when #143 ingested it** — the payoff of recording an out-of-scope finding rather than deferring it. MS/TX/VA are independently corroborated by the EC spine, which carries them at `total_electoral_votes = 0` in 1868 |

**What CI can and cannot prove, stated plainly.** The 14 `not_participating` rows are
verified *in both directions* against the committed public-domain EC roster fixture — they
must be exactly the 1864/1868 zero-EV set — so those are genuinely proven in CI. The 18
`legislature_chosen` rows are not: a legislature-appointed state cast electoral votes like
any other, so the spine cannot distinguish it from a state that held a popular vote. They
are pinned as an explicit expected set with non-empty citations, and independently checked
against UCSB by `TestRealCorpus`, which **skips in CI** (D022 — no UCSB bytes are
committed). Running that class locally with `USVOTE_UCSB_HTML_DIR` set is a **merge
precondition** for anything touching the catalog, not a CI gate.

`CURATED_YEARS` is the catalog's **scope marker**, and it is load-bearing rather than
bookkeeping: without it, "the catalog is silent about 1868" and "1868 was reviewed and has
no further absences" are indistinguishable — the same failure mode D024 §3 rejects for the
roster itself, one level up. `build_curated_roster` therefore **raises** for any year
outside it rather than quietly returning an all-`popular_vote` roster.

## Notes

- **The `ELECTORAL_VOTE_SHORTFALLS` map is keyed on per-state anomalies only.** The
  national "Totals" row's expected shortfall is *derived* (summed over the year's
  states) inside `_expected_shortfall`, so a future multi-state anomaly (e.g. the
  1872 votes for the deceased Horace Greeley, which Congress rejected across several
  states) needs only its per-state entries here — never a hand-maintained Totals
  bump that could silently drift.
- **The name reconciliations** (Trump, Dole, McGovern) are the first instance of the
  canonical-candidate-key problem the popular-vote sources (UCSB/MIT) reconcile
  against; `CANDIDATE_NAME_FIXES` / `PARTY_NAME_FIXES` are the EC-side catalog
  (D006 / #30). The **MIT** realization lives in its own source-namespaced map,
  `MIT_CANDIDATE_RECONCILIATIONS` / `MIT_STATE_RECONCILIATIONS` in
  [`src/usvote/mit/reconcile.py`](../src/usvote/mit/reconcile.py) (#67, D020) — MIT's
  `"LAST, FIRST M."` format shares no keys with the EC fixes, only the canonical RHS
  targets; see [`canonical-keys.md`](canonical-keys.md) for how each source conforms.
- **Format handling vs. data corrections.** Two pre-1892 fixes are parse-level format
  robustness rather than per-year data corrections, so they live in
  [`src/usvote/parse.py`](../src/usvote/parse.py), not the catalog above: superscript
  footnote markers are stripped from state-name and vote cells (`strip_footnotes`), and
  the totals row's `<th>Totals</th>` plural/`<th>` form is recognized (older years use
  it; a singular-only check silently dropped the totals row and emptied the votes fact).
- **Contingent elections — which field is authoritative (#29, D010).** In a contingent
  election the House (or, for the VP, the Senate) chooses the office-holder, so the
  Electoral College leader is not necessarily who took office. The `votes` fact keeps the
  two facts on separate columns, and **downstream flip/margin logic (E6/E7) must read them
  as follows**:
  - **"Who won under the Electoral College"** → `president_electoral_rank == 1` (on a
    year's totals rows). This is the single source of truth for the EC outcome; do **not**
    re-derive it from `took_office`.
  - **"Who assumed office"** → `took_office == True`. Defaults to the EC winner and is
    overridden only for the contingent years in `CONTINGENT_OFFICE_HOLDERS`; it is
    broadcast to every one of a candidate's rows (like the rank). A flip where the EC
    leader did not become president is the year whose `rank == 1` candidate has
    `took_office == False`.

  Scope: `took_office` models **president** office-holding only, and only **1824** (Jackson
  EC rank 1, Adams `took_office`) is within the loaded coverage and exercised in tests.
  **1836** (a VP-only contingency — the Senate chose the VP while President Van Buren won
  normally, so there is no president-level divergence) and **1800** (pre-12th-Amendment,
  two undifferentiated presidential votes, below the 1804 load floor) are representable by
  the same boolean but are not loaded or tested here; their office outcomes become markable
  when those eras are ingested under the deferred pre-12th-Amendment epic (D010).
- **UCSB candidate reconciliation onto the canonical key (#38, D025).**
  `UCSB_STATE_RECONCILIATIONS` (above) canonicalizes **state** names in #36; UCSB
  **candidate** names are reconciled onto the canonical EC `name` in
  [`src/usvote/ucsb/reconcile.py`](../src/usvote/ucsb/reconcile.py) via
  `UCSB_CANDIDATE_RECONCILIATIONS` — a curated map keyed by `(year, ucsb_native_name)`
  (115 EC-getter columns). The spellings are non-mechanical, mirroring the EC/MIT
  catalogs: `STROM THURMOND` → `J. Strom Thurmond`, `ADLAI E. STEVENSON` → `Adlai
  Stevenson`, `WENDELL WILLKIE` → `Wendell L. Willkie`, `AL GORE` → `Albert Gore Jr.`,
  and the accent restored in `JOHN C. FREMONT` → `John C. Frémont`. (The 1872 `HORACE
  GREEFLEY` typo was catalogued while that year was gated out of the EC spine; #144
  ingested 1872, so it is now reconciled like any other — the #38 reciprocal guard raised
  on the column rather than letting 2.8M votes drop silently.) The **D007 candidate scope** is
  applied in the same stage: the 8 popular-vote-only minors UCSB prints are dropped
  (`UCSB_NON_GETTER_COLUMNS` — Van Buren '48, Hale '52, Debs '12, Anderson '80, Perot
  '92/'96, Nader '00, G. Johnson '16), and a reciprocal completeness guard against an
  injected EC-getter frame proves no major was silently lost.
  `EC_GETTERS_WITHOUT_POPULAR_VOTE` (17 entries) exempts the getters that held no popular
  vote — faithless/unpledged electors (1960 Byrd, 2016's five, 2004 Edwards, …) and the
  1832/1836 South Carolina legislature-chosen awards. With #38 landed, MIT and UCSB rows
  now share the EC-getter candidate grain in `dwh.pv_votes` (totals/margins were never
  affected — `state_total_votes` is carried verbatim).
- **1944 Franklin D. Roosevelt footnote asterisk (EC-side, D025).** Table 2 of the
  National Archives [1944 page](https://www.archives.gov/electoral-college/1944) prints
  `Franklin D. Roosevelt*` — a footnote marker (he died in office the following April) —
  while every other year prints him unmarked. Left in, the `*` splits one person across
  two canonical keys (`Franklin D. Roosevelt` in 1932–1940 vs. `…Roosevelt*` in 1944),
  giving FDR a second, party-less candidate row and breaking the D006 canonical key.
  `usvote.transform.strip_name_footnote_markers` strips a trailing `*` from both tables'
  names at normalize time, so the marker never reaches the canonical `name`; it is a
  no-op for every unmarked candidate and 1944 FDR is the only one affected in current
  coverage. Discovered while authoring the #38 UCSB candidate map (the RHS must equal the
  clean EC name for the E6 join to key on it). Source: the 1944 Table 2 + Notes.
- **No deferred Reconstruction years remain.** `UNSUPPORTED_EC_YEARS` in
  [`years.py`](../src/usvote/years.py) (re-exported from
  [`pipeline.py`](../src/usvote/pipeline.py)) is now **empty**, and both years are
  corrected in the catalog above rather than deferred past it.
  **1872 was ingested by #144** (D045/D046): Horace Greeley died after the popular vote
  and his electors scattered across four recipients, Georgia's three votes for him were
  rejected by the House, and Arkansas's and Louisiana's returns were refused — 17 votes
  the Archives table does not print at all, synthesized from its own footnotes before
  being flagged `count_status='not_counted'`. Arkansas and Louisiana also recover the
  allotments the table prints as `-`, which is what makes the year's denominator the 366
  Congress announced rather than the 352 the page totals.
  **1868 was ingested by #143** (D044): its dual
  "excluding/including Georgia" totals rows are resolved by the source's own allotment
  sum, Georgia's nine carry `count_status='disputed'`, and MS/TX/VA load as genuine
  0-electoral-vote rows — see the three 1868 rows in the Electoral College catalog above.
  **UCSB ingestion inherits this gate by derivation** (D024 §6): `ucsb_ingest_years()` is
  `ec_ingest_years()` minus the pre-1824 no-popular-vote years, so lifting 1868 admitted
  it to E4 with **no change under `usvote/ucsb/`** — its four 1868 rows (three
  non-participating states and the Florida legislature-chosen row) are now consumed.
