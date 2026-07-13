# Historical data corrections catalog

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

## Notes

- **The `ELECTORAL_VOTE_SHORTFALLS` map is keyed on per-state anomalies only.** The
  national "Totals" row's expected shortfall is *derived* (summed over the year's
  states) inside `_expected_shortfall`, so a future multi-state anomaly (e.g. the
  1872 votes for the deceased Horace Greeley, which Congress rejected across several
  states) needs only its per-state entries here — never a hand-maintained Totals
  bump that could silently drift.
- **The name reconciliations** (Trump, Dole, McGovern) are the first instance of the
  canonical-candidate-key problem the popular-vote sources (UCSB/MIT) will reconcile
  against; `CANDIDATE_NAME_FIXES` / `PARTY_NAME_FIXES` are expected to be reused there
  (D006 / #30).
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
- **Deferred Reconstruction years (1868, 1872).** These are **excluded** from the
  default ingest (`UNSUPPORTED_EC_YEARS` in [`pipeline.py`](../src/usvote/pipeline.py)),
  not corrected here, because their tables encode contested/uncounted electoral votes
  that need dedicated modeling: 1868's Georgia votes were contested (dual
  "excluding/including Georgia" totals rows; MS/TX/VA had not been readmitted), and
  1872's Horace Greeley died after the popular vote, scattering his electoral votes with
  Georgia's rejected by Congress. Ingesting them is tracked as follow-up work (#57).
