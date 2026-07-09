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
[`tests/test_transform.py`](../tests/test_transform.py). When you add coverage for a
new election year (E2-S7 extends below 1892 and will surface new anomalies), add the
correction the same way: one constant entry + a small `apply_*`/reconcile function,
one test, and one row in the table below.

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
