# Glossary

What this project's terms mean, for readers who are not engineers and for the people writing to
them. Maintained by the `ba` agent; the owner settles anything marked `proposed`.

**This file records meaning, not display text.** The dashboard's shipped wording lives in
`dashboard/explore/labels.py` (`LABELS`, the closed-value tables, and the null and help-text
constants), with a few page-level sentences in `dashboard/explore/components.py`,
`dashboard/explore/export.py` and the modules under `dashboard/explore/pages/`. Each entry points
at that code under **Shown as** and does not repeat its wording. If the two disagree, the code is
what readers see; fix whichever is wrong and say which.

**Audiences.** Public readers of the dashboard at `explore.us-presidential-election-center.org`,
non-technical readers first (epic #275, product frame 3); readers of the "Counted, Not Assumed"
blog series under `posts/`; people who download a table as CSV; the owner; and the agents who
write labels and help text. Plain definitions are written for the least technical of them.

**The published posts are the best evidence of reader-facing wording.** They are owner-edited.
Where a post settles how a term reads, it is cited under **Source**; where a post and the code
disagree, the disagreement is a finding for the owner, and the post is never edited.

---

## Wording rules

These bind every label, cell, note and sentence a reader sees, and every wording drawn from this
file.

- **Editorial guardrails** (`CLAUDE.md`, "Publishing"): nothing critical of a data source is ever
  published, and every historical claim is checked before publishing. Wording describes what the
  dataset holds, never a fault in a source. *Source:* `CLAUDE.md`; #275, carry-forward
  constraints. *Status:* settled.
- **No underscores and no raw field names in reader wording.** A raw field name may appear only
  where the page presents it as a field name: a column header's tooltip, the "Column names" (or
  panel "Field names") list, and a CSV header row. It never appears in a label, a cell, a note, a
  preamble sentence or page prose, and neither does a raw coded value (for example a status code).
  The view link in a CSV preamble is exempt, as a header row is: it carries the API's own query
  names because it has to reopen the view exactly.
  *Source:* owner decision, 2026-10-10, #348; the view-link exemption, owner decision, 2026-10-11, #348. *Status:* settled.
- **"Counted" is reserved for vote counts** (Congress's count of electoral votes, and popular-vote
  counts). Anything else that is counted, such as people in a census or states in a total, gets
  other wording. *Source:* owner decision, 2026-10-10, #348;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md` (appointed, cast, counted). *Status:* settled.
- **Plain words over legal and survey terms**: "census used" rather than "census in force", no
  "governs", "borders" rather than "footprint", no "apportionment" in reader wording, and "the
  National Archives" rather than "the Archives". The precise terms stay in this file. *Source:*
  owner decision, 2026-10-10, #348. *Status:* settled.

---

## Terms

### Appointed electors
- **Plain:** How many electors a state was entitled to choose in an election, which is its number
  of electoral votes (its allotment). Added up across states, it is the whole Electoral College for
  that year.
- **Precise:** The state's electoral-vote allotment for the year (warehouse column
  `total_electoral_votes`). The national figure is the sum over states, each included once: the
  12th Amendment's "whole number of Electors appointed", and the base for every majority test and
  electoral share. It can be 0 for a state whose votes were withheld (1864, 1868). It is the top
  rung of the ladder **appointed ≥ cast ≥ counted**.
- **Shown as:** `LABELS["state_electoral_votes"]` (T2, T4, T6, T7); `LABELS["national_electoral_denominator"]` (T3).
- **Source:** `EcPvRow.state_electoral_votes`, `PerCapitaRow.state_electoral_votes` and
  `NationalSummaryRow.national_electoral_denominator` in `src/usvote/api/models.py`; D041; D046 §5;
  D068; `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "Appointed, not cast" (the reader
  wording: allotment, electors appointed).
- **Not:** *Electoral votes cast.* An appointed elector who did not vote opens a gap between the
  two (`ELECTORAL_VOTE_SHORTFALLS` in `src/usvote/transform.py`). Not "electoral votes won".
- **Status:** settled

### Borders used for the population (boundary basis)
- **Plain:** Which borders a population figure describes: the state's borders when the election
  was held, or the state as the Census Bureau's table reports it today.
- **Precise:** Closed vocabulary on a per-capita row. `at_election` means the figure is
  established to describe the state's borders in force at the election. `present_day` is the
  default: the source's modern borders, which the dataset does not assert match the borders at the
  election. This is the footprint axis only, separate from which census supplies the figure
  (*Census used*) and where the allotment came from (D066(b)).
- **Shown as:** `LABELS["boundary_basis"]`; values `labels.BOUNDARY_BASIS`; help text
  `labels.BOUNDARY_NOTE` (on each cell and under T6 and T7).
- **Source:** `PerCapitaRow.boundary_basis`; D060(f); D066(a), (b), (e); D067; vocabulary copied
  into `snapshot_schema.py` per D069(b). Header and value wording: owner decision, 2026-10-10,
  #348 (no "counted", no "footprint").
- **Not:** The census table's own `basis` label, which is about the census, not the election
  (D060(f)). Not a statement about the accuracy of the Census Bureau's figure.
- **Status:** settled

### Candidate
- **Plain:** A person who received at least one electoral vote in that election.
- **Precise:** The canonical display name (D006), with `candidate_slug` as its durable public id.
  The dataset's candidate scope is candidates who received electoral votes (D007); candidates who
  only received popular votes are not in it.
- **Shown as:** `LABELS["candidate"]`; the candidate filter on `/election/<year>` and
  `/state/<usps>`.
- **Source:** `EcPvRow.candidate` and `candidate_slug`; D006; D007; `docs/canonical-keys.md`,
  "The two keys are two-tier".
- **Not:** Everyone on the ballot.
- **Status:** settled

### Candidates with electoral votes (count per election)
- **Plain:** How many candidates received electoral votes in that election.
- **Precise:** `candidate_count` on a `/v1/elections` row: distinct candidates with national
  roll-up rows that year. `/v1/meta` also has a `candidate_count`, meaning distinct candidates
  across the whole dataset; showing that one needs its own qualified `LABELS` key.
- **Shown as:** `LABELS["candidate_count"]` (T1).
- **Source:** `YearListItem.candidate_count` and `SnapshotMetaResponse.candidate_count` in
  `src/usvote/api/models.py`; D007; the `labels.py` module docstring; header wording: owner
  decision, 2026-10-10, #348.
- **Not:** Candidates on the ballot; the dataset-wide count.
- **Status:** settled

### Census figure (per-capita coverage)
- **Plain:** Whether there is a census population figure for that state at that election.
- **Precise:** `coverage` on a per-capita row: `covered`, or `no_governing_figure` where no
  census figure exists for the state and year (one cell, 1848 Texas, which the United States had
  not enumerated in 1840). `no_governing_figure` holds exactly where `population` is null.
- **Shown as:** `LABELS["coverage"]`; values `labels.PER_CAPITA_COVERAGE`, read by
  `labels.per_capita_coverage`, `labels.population` and `labels.persons_per_electoral_vote`.
- **Source:** `PerCapitaRow.coverage`; D060(h); D069(e); value wording: owner decision,
  2026-10-10, #348 (no "governs").
- **Not:** *Years covered* (`meta.provenance.coverage`) or the *share of electors from
  popular-vote states* (`pv_coverage`). The plain `LABELS` key `coverage` means this one only
  (`labels.py` module docstring).
- **Status:** settled

### Census used (governing census)
- **Plain:** The census that set how many electoral votes a state had at that election. Its
  population figure is the one used.
- **Precise:** `governing_census_year`: the census whose apportionment was in force at the
  election. It is not the nearest census: 2020 reads 2010, and 1924 and 1928 read 1910, because
  Congress passed no apportionment after the 1920 census. This is the vintage axis of D066(b).
- **Shown as:** `LABELS["governing_census_year"]`; help text `labels.GOVERNING_CENSUS_NOTE`
  under T6 and T7.
- **Source:** `PerCapitaRow.governing_census_year`; D064; D066(b);
  `posts/2026-09-03-how-did-we-get-to-538-electors.md`, "The decade Congress skipped" (the 1920
  gap, and the 1910 map electing 1924 and 1928); header wording: owner decision, 2026-10-10, #348.
- **Not:** The census nearest the election.
- **Status:** settled. The reworded help text restates a historical claim and waits on the owner's
  claim check before it ships.

### Count status
- **Plain:** Whether Congress counted the electoral votes that were cast: counted; not counted,
  because Congress decided not to count them; or disputed, because Congress never reached a
  decision.
- **Precise:** `electoral_count_status`, one of exactly three values, per `(year, state,
  candidate)`. `not_counted`: cast, and Congress decided not to count them (1872). `disputed`:
  cast, and the two chambers never resolved the question (1868 Georgia). `disputed` is a recorded
  fact, not an "unknown". Every row that is not `counted` carries the National Archives' own
  sentence, verbatim, in `electoral_count_status_reason`; the reason is null when the votes were
  counted. National totals rows are never flagged (D044).
- **Shown as:** `LABELS["electoral_count_status"]`, `LABELS["electoral_count_status_reason"]`;
  values `labels.COUNT_STATUS`; the cell `labels.count_status`; the count-status filter.
- **Source:** `src/usvote/count_status.py`, `COUNT_STATUS_VALUES` and the comment on each value;
  `EcPvRow.electoral_count_status` and `electoral_count_status_reason`; D043; D044; D047; D048 §4;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "When the record itself won't say" (the
  reader wording for not counted and disputed).
- **Not:** Appointed electors who never voted, a different gap (`ELECTORAL_VOTE_SHORTFALLS`).
- **Status:** settled

### Data version
- **Plain:** Which edition of the data a page shows. It changes whenever the data is rebuilt.
- **Precise:** `snapshot_version`, a content hash of the served snapshot (also the response
  `ETag`). A page reads one version for its whole render.
- **Shown as:** the version line of `components.provenance_footer` (`SNAPSHOT_ID`); the CSV
  preamble (`export.preamble`).
- **Source:** `Provenance.snapshot_version`; D028; D069(c); `dashboard/CLAUDE.md`, `api.py`;
  reader wording: owner decision, 2026-10-10, #348 ("data version", not "snapshot").
- **Not:** The build date; the schema version.
- **Status:** settled

### Dataset ("this dataset")
- **Plain:** The data this site shows: Electoral College results from 1824 on, popular votes for
  recent elections, and census population. Nothing else.
- **Precise:** The public API's snapshot, which is the dashboard's only data input (D070(b)) and
  carries redistributable data only (D030). "In this dataset" is a statement about what the
  snapshot holds, never about what happened historically and never about a source.
- **Shown as:** throughout, for example `labels.NOT_IN_DATASET`, `labels.BEFORE_WINDOW`,
  `labels.HAS_POPULAR_VOTE_NOTE` and the page ledes.
- **Source:** `CLAUDE.md`, "Publishing" (editorial guardrail); `.claude/specs/backlog-dashboard.md`,
  "Carry-forward constraints"; D030; D070; `posts/2026-08-06-222-votes-away.md`, "The record the
  argument runs on top of" (the 1976 popular-vote edge described as a licensing boundary, not a
  records one).
- **Not:** "The historical record".
- **Status:** settled

### Degraded state (the data service is not responding)
- **Plain:** What a page says when it cannot read the data right now.
- **Precise:** `components.unavailable`, rendered when a page's read fails: the API cannot be
  reached, the data version changes mid-render, or a response is malformed (`ApiUnavailable`,
  `KeyError`, `TypeError` in a page layout). `scripts/probe_dashboard.sh` greps its wording, so
  that wording is load-bearing.
- **Shown as:** `components.UNAVAILABLE_MESSAGE`.
- **Source:** `dashboard/explore/components.py`; `dashboard/CLAUDE.md`, `components.py`.
- **Not:** A not-found state, which is a year or state the dataset does not serve
  (`NOT_FOUND_SENTENCE` in `pages/election.py` and `pages/state.py`). An empty filter result
  (`components.NO_ROWS`). The panel's own unavailable state (`PANEL_UNAVAILABLE`).
- **Status:** settled

### Election year
- **Plain:** The year the presidential election was held.
- **Precise:** `year`. The years served run from `meta.provenance.coverage.year_min` to
  `year_max`, read from the response, never written as a literal.
- **Shown as:** `LABELS["year"]`; the year-range slider.
- **Source:** `EcPvRow.year`, `YearListItem.year`; `Coverage.year_min` and `year_max`.
- **Not:** *Census used*, which is also a year.
- **Status:** settled

### Electoral College winner, or leader with no majority (`ec_winner`)
- **Plain:** The candidate with the most electoral votes counted. When that candidate has a
  majority of the electors appointed, they are the Electoral College winner. When no one has a
  majority, they are only the Electoral College leader, and the House chose the president: in
  1824 Jackson led and the House chose Adams.
- **Precise:** `ec_winner`, the candidate with the largest counted electoral share. Its reader
  name depends on `ec_determinative` from the same election block: true reads as the Electoral
  College winner; false reads as the Electoral College leader with no majority; null reads as
  the Electoral College leader, claiming neither a majority nor its absence (owner decision, 2026-10-11, #348).
  Neither name says who took office.
- **Shown as:** `LABELS["ec_winner"]` and the panel row label chosen with `ec_determinative`;
  `labels.winner`; referred to by `labels.FLIP_YES`.
- **Source:** owner decision, 2026-10-10, #348; `ElectionSummary.ec_winner` and
  `ec_determinative`; D041; D038 (the 1824 rationale); `posts/2026-08-25-it-takes-270-but-270-of-what.md`,
  "The one time it happened" (the electoral leader, majority outright, who took office);
  `posts/2026-08-06-222-votes-away.md`, "The record the argument runs on top of" (Electoral
  College winner).
- **Not:** *Took office*, which is who became president. *Electoral College majority*, which is
  the yes or no behind the name.
- **Status:** settled

### Electoral College majority
- **Plain:** Whether any candidate won more than half of all the electors appointed that year. If
  none did, the election went to the House.
- **Precise:** `ec_determinative`: true exactly when the leader's *electoral share* (votes counted
  ÷ electors appointed) is above 0.5. The test is strict, so an exact tie reads as no majority.
  `false` is a real outcome (1824), not missing.
- **Shown as:** `LABELS["ec_determinative"]`; `labels.EC_MAJORITY`, `labels.NO_EC_MAJORITY`, via
  `labels.ec_majority`.
- **Source:** `ElectionSummary.ec_determinative`; D041; D046 §4;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "Appointed, not cast".
- **Not:** A majority of the votes cast or counted; the base is the electors appointed. A null,
  which names no cause.
- **Status:** settled

### Electoral rank
- **Plain:** Where a candidate finished nationally by electoral votes counted (1 = most).
- **Precise:** The national finishing rank on the counted basis, so it may not order the cast
  totals.
- **Shown as:** `LABELS["electoral_rank"]` (T3).
- **Source:** `NationalSummaryRow.electoral_rank`; D046 §4.
- **Not:** *Took office* (1824).
- **Status:** settled

### Electoral share
- **Plain:** A candidate's electoral votes counted, as a share of all the electors appointed that
  year.
- **Precise:** `ec_share_full` = counted ÷ appointed. No coverage policy can move it, and it is
  the only input to `ec_determinative`. Because some appointed electors never vote, shares can sum
  to less than 100% (D041). `ec_share_hybrid` is the electoral share fed into the hybrid; under
  the only configured policy, (b), it equals `ec_share_full`, and it is served separately so that
  can be checked.
- **Shown as:** `LABELS["ec_share_full"]`, `LABELS["ec_share_hybrid"]` (T3); `labels.share_cell`;
  `labels.EC_SHARE_HYBRID_NOTE` under T3.
- **Source:** `NationalSummaryRow.ec_share_full` and `ec_share_hybrid`; D037; D038; D041;
  D042 §2; D046 §4.
- **Not:** A share of the votes cast.
- **Status:** settled. The reader note explaining the second share is drafted for the owner's
  review on the dashboard.

### Electoral votes cast
- **Plain:** The electoral votes that electors actually cast for a candidate.
- **Precise:** `electoral_votes` per state row and `national_electoral_votes` per candidate. A
  candidate who got none in a state shows 0, a real zero (the dense Electoral College fact, D026).
  The middle rung of appointed ≥ cast ≥ counted.
- **Shown as:** `LABELS["electoral_votes"]`, `LABELS["national_electoral_votes"]`.
- **Source:** `EcPvRow.electoral_votes`; `NationalSummaryRow.national_electoral_votes`;
  `count_status.CAST_VOTES_COLUMN`; D046; `posts/2026-08-25-it-takes-270-but-270-of-what.md`.
- **Not:** *Electoral votes counted* (they differ in 1868 and 1872); *Appointed electors*.
- **Status:** settled

### Electoral votes counted
- **Plain:** Of the electoral votes cast, the ones Congress counted in its final tally.
- **Precise:** A state row's counted votes equal its cast votes when the count status is
  `counted`, and 0 otherwise; a national total is the sum of its state rows. Counted and cast
  differ only in 1868 and 1872. The counted figure decides rank, the electoral share and the
  majority test.
- **Shown as:** `LABELS["electoral_votes_counted"]`, `LABELS["national_electoral_votes_counted"]`.
- **Source:** `EcPvRow.electoral_votes_counted`; `count_status.COUNTED_VOTES_COLUMN`; D046;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "Then there is a third number".
- **Not:** *Electoral votes cast.*
- **Status:** settled

### Flip (another method picks a different winner)
- **Plain:** Whether the popular vote, or the hybrid, would have picked someone other than the
  Electoral College's winner (or, with no majority, its leader).
- **Precise:** `pv_flip` / `hybrid_flip`: true when that method's winner differs from `ec_winner`,
  false when it is the same person. Null where the method has no winner (outside the popular-vote
  window): null, never false, because a method with no winner neither agrees nor disagrees. The
  reader wording names the Electoral College side the same way `ec_winner` does.
- **Shown as:** `LABELS["pv_flip"]`, `LABELS["hybrid_flip"]`; `labels.flip`, `labels.FLIP_YES`.
- **Source:** `ElectionSummary.pv_flip`, `hybrid_flip` and the class docstring; owner decision,
  2026-10-10, #348 (consistency with `ec_winner`).
- **Not:** "No", which is a recorded agreement. *Outside the popular-vote window*, which is no
  answer.
- **Status:** settled

### Hybrid
- **Plain:** The project's third way of picking a winner: average each candidate's electoral share
  and popular-vote share; the highest average wins.
- **Precise:** `hybrid_score` = (`ec_share_hybrid` + `pv_share`) / 2; `hybrid_winner` has the
  highest score. Null outside the popular-vote window. The denominator policy is (b) (D038), and
  `pv_coverage` flags a year whose popular vote covers only some states.
- **Shown as:** `LABELS["hybrid_score"]`, `LABELS["hybrid_winner"]`, `LABELS["hybrid_margin"]`,
  `LABELS["hybrid_flip"]`, `LABELS["ec_share_hybrid"]`; help text `labels.HYBRID_NOTE` (panel and
  T3).
- **Source:** `NationalSummaryRow.hybrid_score`; `ElectionSummary.hybrid_winner`; D037; D038;
  `docs/pv-coverage.md`.
- **Not:** A forecast or an endorsement. Help text says what it computes and nothing about its
  merits (`labels.HYBRID_NOTE` comment); argument for it belongs only in a clearly labeled opinion
  tab (#275, E9-S7).
- **Status:** settled

### Margin
- **Plain:** How far the leader was ahead of the runner-up under one method, in percentage points.
  Each method has its own top two.
- **Precise:** The gap between the top two candidates in that method's measure (electoral share,
  popular-vote share, or hybrid score), in percentage points as the API serves it. In 2000 the
  popular-vote margin is Gore's lead over Bush. `ec_margin` is null with fewer than two scored
  candidates; the popular-vote and hybrid margins are null outside the popular-vote window.
- **Shown as:** `LABELS["ec_margin"]`, `LABELS["pv_margin"]`, `LABELS["hybrid_margin"]`;
  `labels.margin`; the panel note `labels.MARGIN_NOTE`, drafted for the owner's review on the
  dashboard.
- **Source:** `ElectionSummary.ec_margin`, `pv_margin`, `hybrid_margin` and
  `_ELECTION_SUMMARY_EXAMPLE` in `src/usvote/api/models.py`; D037.
- **Not:** A percent change. A gap measured from the Electoral College's winner or leader.
- **Status:** settled

### No popular-vote figure in this dataset (inside the window)
- **Plain:** A state held a popular vote in a year this dataset covers, but the dataset has no
  figure for this candidate there.
- **Precise:** A null `popular_votes` (or `national_pv_votes`) on a row whose `pv_status` is
  `popular_vote`, in a year inside the popular-vote window. Typically a candidate the popular-vote
  source does not cover, such as an unpledged slate or a faithless elector's choice. No status
  narrows it further (D005).
- **Shown as:** `labels.NO_FIGURE` (T2, T4); `labels.NO_NATIONAL_FIGURE` (T3).
- **Source:** `EcPvRow` docstring and `pv_status` description; `NationalSummaryRow` docstring;
  `.claude/specs/backlog-dashboard.md`, E9-S3 null table;
  `posts/2026-08-18-presidential-elections-are-messy.md`, "One empty cell, five different
  histories" (a number the record does not carry is not a zero).
- **Not:** Zero popular votes.
- **Status:** settled

### Not in this dataset (a value with no cause given)
- **Plain:** This dataset has no value here. It says nothing about why, or about what happened at
  the time.
- **Precise:** The cell for a null, blank or non-finite value that the row does not explain. It is
  also the cell for `has_popular_vote: false` and for a null `party`, both of which are about what
  the dataset holds. In a CSV download the same thing is an empty cell (`export.NULL_LINE`). A
  cause, where one is known, follows it after a colon (*Outside the popular-vote window*).
- **Shown as:** `labels.NOT_IN_DATASET`, reached through `labels.has_popular_vote`,
  `labels.party`, `labels._closed_value`, `labels._null`, `labels.ec_majority`,
  `labels.share_cell`, `labels.margin`, `labels.persons_per_electoral_vote`.
- **Source:** the comments on `NOT_IN_DATASET` and `_closed_value` in `labels.py`;
  `dashboard/CLAUDE.md`, `components.py`, `labels.py` (the "never No" rule);
  `.claude/specs/backlog-dashboard.md`, "Carry-forward constraints"; #348 acceptance criteria.
- **Not:** "No", which is a recorded negative. Zero. "Not held". *Unrecognized value*, where the
  dataset does hold something.
- **Status:** settled

### Outside the popular-vote window
- **Plain:** The dataset has no popular-vote figures for this year, so nothing computed from them
  can be shown.
- **Precise:** A null popular-vote or hybrid field in a year outside the popular-vote window of
  `meta.provenance.coverage` (`labels.in_pv_window` is false, or, in T3, the year's
  `has_popular_vote` is false). It names its cause, and one wording serves the panel and T3's
  popular-vote columns and hybrid score (`national_pv_votes`, `pv_share`, `hybrid_score`;
  owner decision, 2026-10-12, #352). A null party in such a year reads *Not in this dataset*
  with `labels.PARTY_NOTE` (see Party: its null has two causes), and T2 and T4 name the window's
  side (`labels.BEFORE_WINDOW`, `labels.AFTER_WINDOW`).
- **Shown as:** `labels.NOT_APPLICABLE` (panel; T3 through `_national_pv` in
  `pages/election.py`); `NO_PV_SENTENCE` in `pages/election.py` above T3.
- **Source:** `ElectionSummary` docstring; `labels.in_pv_window`; `.claude/specs/backlog-dashboard.md`,
  E9-S3, "Election panel"; wording: owner decision, 2026-10-10, #348.
- **Not:** "No" (a false flip). A null inside the window, which names no cause.
- **Status:** settled

### Party
- **Plain:** The candidate's party as the popular-vote source records it, shown as a name in
  ordinary capitalization.
- **Precise:** The party of record from the popular-vote source. The API serves the source's own
  code; the dashboard shows a display form of that code (capitalization, plus a short list of
  exceptions where the name is not the code's case form: `DEMOCRAT` reads "Democratic", the
  party's own name, owner decision, 2026-10-11, #348). The download keeps the code as served.
  Null outside the popular-vote window and wherever that source has no figure for the candidate.
  The codes the public data can carry are limited by `EC_GETTER_PARTIES` in
  `src/usvote/mit/transform.py` (D019).
- **Shown as:** `LABELS["party"]`; `labels.party_cell`, with `labels.PARTY_NOTE` as help text on a
  null cell and under T2, T3 and T4.
- **Source:** `EcPvRow.party`, `NationalSummaryRow.party`; D019; D024 §5 (citing D018: party must
  not become a second source of party truth); display rule: owner decision, 2026-10-10, #348;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "Then there is a third number" (the
  Democratic name in reader prose).
- **Not:** An Electoral College attribute; the dataset serves none. Not a second party record:
  the display form changes how a code is written, never which party a row carries.
- **Status:** settled

### People per electoral vote
- **Plain:** How many residents each of a state's electoral votes stood for at that election.
- **Precise:** `persons_per_electoral_vote` = `population` ÷ `state_electoral_votes` (appointed),
  shown to a whole person. Null where the population is null (no census figure) or the allotment
  is 0 (votes withheld: eleven states in 1864, three in 1868). Never 0 and never infinite. Where a
  row carries both causes, the missing census figure is the one shown.
- **Shown as:** `LABELS["persons_per_electoral_vote"]`; `labels.persons_per_electoral_vote`;
  `labels.NO_ELECTORAL_VOTES`; the T6 and T7 headings.
- **Source:** `PerCapitaRow`; D064(c), (d); D069. `posts/2026-09-03-how-did-we-get-to-538-electors.md`
  names the same measure "persons per electoral vote"; readers see "people" (owner decision, 2026-10-11, #348).
  The field name `persons_per_electoral_vote` stays where field names are allowed.
- **Not:** People per elector who voted.
- **Status:** settled

### Popular vote held in this state (`pv_status`)
- **Plain:** Whether the state held a popular vote for president that year: a popular vote was
  held; the state legislature chose the electors instead; or the state took no part in the
  election.
- **Precise:** `pv_status`, one of exactly three values per `(year, state)`: `popular_vote`,
  `legislature_chosen`, `not_participating`. Never null, and there is no "unknown". It is a fact
  about the election, not about the dataset: a `popular_vote` row can still lack a figure. The
  public values come from the in-repo absence catalog (D048 §3).
- **Shown as:** `LABELS["pv_status"]`; values `labels.PV_STATUS` (cell and filter);
  `labels.LEGISLATURE_CHOSE` and `labels.TOOK_NO_PART` in the popular-vote cell.
- **Source:** `src/usvote/pv/status.py`, `PV_STATUS_VALUES` and its comment; `EcPvRow.pv_status`;
  D024 §4; D048 §2–3; `posts/2026-08-18-presidential-elections-are-messy.md`, "How the record
  keeps them apart" (the three values as readers see them: held, the legislature chose the
  electors, took no part); `posts/2026-08-06-222-votes-away.md` (a status saying whether a popular
  vote was held there at all).
- **Not:** *Popular vote in this dataset*, which is year-level and about the dataset.
- **Status:** settled

### Popular vote in this dataset (`has_popular_vote`)
- **Plain:** Whether this dataset has popular-vote figures for that election year.
- **Precise:** `has_popular_vote`: whether the year carries popular-vote figures on the public
  surface. False for every year outside the popular-vote window. It says nothing about whether a
  popular vote was held.
- **Shown as:** `LABELS["has_popular_vote"]`; `labels.has_popular_vote`;
  `labels.HAS_POPULAR_VOTE_NOTE`; the T1 popular-vote checkbox.
- **Source:** `YearListItem.has_popular_vote`; `NationalSummaryRow` docstring.
- **Not:** *Popular vote held in this state.*
- **Status:** settled

### Popular votes
- **Plain:** Votes a candidate received from voters, in one state or nationally.
- **Precise:** `popular_votes` per state row; `national_pv_votes` per candidate. A missing figure
  is never 0. `labels.popular_votes` gives every null in a state cell its reason: the legislature
  chose; the state took no part; a vote was held before or after the popular-vote window; or a
  vote was held inside it with no figure in this dataset for this candidate.
- **Shown as:** `LABELS["popular_votes"]`, `LABELS["national_pv_votes"]`; `labels.popular_votes`
  with `LEGISLATURE_CHOSE`, `TOOK_NO_PART`, `BEFORE_WINDOW`, `AFTER_WINDOW`, `NO_FIGURE`.
- **Source:** `EcPvRow.popular_votes`; `NationalSummaryRow.national_pv_votes`; D024; D048 §2;
  `.claude/specs/backlog-dashboard.md`, E9-S3 null table.
- **Not:** Zero.
- **Status:** settled

### Popular-vote share
- **Plain:** A candidate's share of all votes cast for president nationally.
- **Precise:** `pv_share` = national popular votes ÷ total votes cast nationally. Null outside the
  popular-vote window.
- **Shown as:** `LABELS["pv_share"]` (T3).
- **Source:** `NationalSummaryRow.pv_share`.
- **Not:** *Electoral share*.
- **Status:** settled

### Popular-vote winner
- **Plain:** The candidate with the largest share of the national popular vote.
- **Precise:** `pv_winner`: the largest national popular-vote share, a plurality rather than a
  majority. Null outside the popular-vote window.
- **Shown as:** `LABELS["pv_winner"]`; `labels.winner`.
- **Source:** `ElectionSummary.pv_winner`; `posts/2026-08-06-222-votes-away.md` (led the national
  popular vote count).
- **Not:** A majority winner.
- **Status:** settled

### Population
- **Plain:** The state's resident population from the census used for that election.
- **Precise:** The governing census's resident population (`population_series` is `resident`),
  described on the row's boundary basis. Null only where no census figure exists.
- **Shown as:** `LABELS["population"]`; `labels.population`.
- **Source:** `PerCapitaRow.population` and `population_series`; D059; D064(b); D066; header
  wording: owner decision, 2026-10-10, #348.
- **Not:** Voting-age population; votes cast.
- **Status:** settled

### Share of electors from popular-vote states (`pv_coverage`)
- **Plain:** Of all the electors appointed that year, the share that came from states holding a
  popular vote.
- **Precise:** The allotments of `popular_vote` states ÷ all allotments, weighted by electoral
  votes, not by number of states. 100% from 1880 on and 72.8% in 1824. 1864 reads 100% although
  eleven states took no part, because those states had no electoral votes. A value below 100% is
  a caveat on a real number, not a defect.
- **Shown as:** `LABELS["pv_coverage"]` (panel and T3's meaning); `labels.share_cell`.
- **Source:** `docs/pv-coverage.md`, "What the number measures";
  `NationalSummaryRow.pv_coverage`, `ElectionSummary.pv_coverage`; D024 §8; D038.
- **Not:** How much of the popular vote this dataset holds (*Popular vote in this dataset*, *Years
  covered*).
- **Status:** settled

### Sources
- **Plain:** The three public organizations the figures come from, and the license each is
  published under.
- **Precise:** Electoral votes: `ec_source_name`, `ec_license`. Popular votes: `source_name`,
  `license`. Population: `census_source_name`, `census_license`. Rendered from
  `meta.provenance`, never written in by hand.
- **Shown as:** `components.provenance_footer`; `export.preamble`; `export.EC_SOURCE`,
  `PV_SOURCE`, `CENSUS_SOURCE`.
- **Source:** `Provenance` in `src/usvote/api/models.py`; D030; D048 §6; D069(f); #275,
  carry-forward constraints.
- **Not:** —
- **Status:** settled

### State
- **Plain:** One of the 50 states, or the District of Columbia.
- **Precise:** The full state name, the canonical display key; `state_usps` is the two-letter
  code used in URLs and filters.
- **Shown as:** `LABELS["state"]`; the state filter; `/states`.
- **Source:** `EcPvRow.state`, `state_usps`; D006; `docs/canonical-keys.md`, "The two keys are
  two-tier".
- **Not:** —
- **Status:** settled

### Took office
- **Plain:** Whether the candidate became president for that term.
- **Precise:** `took_office`, a recorded yes or no.
- **Shown as:** `LABELS["took_office"]` (T3); `labels.yes_no`.
- **Source:** `NationalSummaryRow.took_office`; owner decision, 2026-10-10, #348 (a separate term
  from the Electoral College winner); `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "The one
  time it happened".
- **Not:** *Electoral College winner, or leader with no majority* (1824).
- **Status:** settled

### Unrecognized value
- **Plain:** The dataset has a value here that this page does not have a label for. The download
  shows it as served.
- **Precise:** The reader cell for a closed-vocabulary value outside the known set (a status,
  boundary basis or census-figure code the dashboard does not label). Today these fall back to the
  raw value as text, which the no-raw-names rule forbids.
- **Shown as:** a new constant, wording "Unrecognized value". Today the fallbacks are in `labels.pv_status`,
  `labels.count_status`, `labels._closed_value` and `labels.popular_votes`.
- **Source:** the "renders as text rather than as a claim" docstrings in `labels.py`; owner
  decision, 2026-10-10, #348 (no raw values in cells); wording: owner decision, 2026-10-11, #348.
- **Not:** *Not in this dataset*, which means the dataset holds nothing here.
- **Status:** settled

### Years covered
- **Plain:** The span of election years the dataset covers: Electoral College results for every
  year in it, and popular votes for a narrower, recent span (the popular-vote window).
- **Precise:** `meta.provenance.coverage`: `year_min` / `year_max` for every year served and
  `pv_year_min` / `pv_year_max` for the years that also carry popular votes. It describes the
  data; it is not a promise. Pages read it from the response, never from a literal.
- **Shown as:** the home page's coverage list; the CSV preamble; `labels.BEFORE_WINDOW`;
  `NO_PV_SENTENCE` in `pages/election.py`.
- **Source:** `Coverage` in `src/usvote/api/models.py`; D048 §1;
  `posts/2026-08-06-222-votes-away.md` (both windows published on every response).
- **Not:** *Census figure* (per-capita `coverage`); *Share of electors from popular-vote states*.
  A table showing these windows needs a qualified `LABELS` key (`labels.py` module docstring).
- **Status:** settled

---

## Key index

Every `LABELS` key and the entry that defines it.

| `LABELS` key | Entry |
|---|---|
| `year` | Election year |
| `candidate_count` | Candidates with electoral votes |
| `has_popular_vote` | Popular vote in this dataset |
| `state` | State |
| `candidate` | Candidate |
| `party` | Party |
| `state_electoral_votes` | Appointed electors |
| `electoral_votes` | Electoral votes cast |
| `electoral_votes_counted` | Electoral votes counted |
| `electoral_count_status` | Count status |
| `electoral_count_status_reason` | Count status |
| `pv_status` | Popular vote held in this state |
| `popular_votes` | Popular votes |
| `national_electoral_votes` | Electoral votes cast |
| `national_electoral_votes_counted` | Electoral votes counted |
| `national_electoral_denominator` | Appointed electors |
| `electoral_rank` | Electoral rank |
| `took_office` | Took office |
| `national_pv_votes` | Popular votes |
| `ec_share_full` | Electoral share |
| `pv_share` | Popular-vote share |
| `governing_census_year` | Census used |
| `population` | Population |
| `boundary_basis` | Borders used for the population |
| `coverage` | Census figure |
| `persons_per_electoral_vote` | People per electoral vote |
| `ec_winner` | Electoral College winner, or leader with no majority |
| `pv_winner` | Popular-vote winner |
| `hybrid_winner` | Hybrid |
| `pv_flip` | Flip |
| `hybrid_flip` | Flip |
| `ec_margin` | Margin |
| `pv_margin` | Margin |
| `hybrid_margin` | Margin |
| `ec_determinative` | Electoral College majority |
| `pv_coverage` | Share of electors from popular-vote states |
| `ec_share_hybrid` | Electoral share |
| `hybrid_score` | Hybrid |

---

## Say instead

Words that reach readers too often without help, and what to say instead.

| Avoid | Say instead | Why |
|---|---|---|
| "winner" for the Electoral College leader in a year with no majority | Electoral College leader (no majority) | In 1824 the leader did not become president. |
| "not applicable" for a year outside the popular-vote window | that this dataset has no popular-vote figures for the year | "Not applicable" reads as a claim that the method had no result at the time. |
| "no figure" without "in this dataset" | no figure in this dataset | Without it, a reader can take the cell as zero votes. |
| a raw field name, a status code, or anything with an underscore | the plain label | Allowed only where the page presents it as a field name (owner decision, 2026-10-10). |
| "null" | no value in this dataset | Engineering term. |
| "coverage" on its own | name which one: years covered; census figure; share of electors from popular-vote states | The project uses the word for three different things. |
| "counted" for anything but votes | used, covers, included | "Counted" is reserved for vote counts (owner decision, 2026-10-10). |
| "in force", "governs", "apportionment" | used; set the state's electoral votes; redistribute House seats | Legal register. |
| "footprint" | borders | Survey jargon. |
| "the Archives" | the National Archives | A reader may not know which archive. |
| "snapshot" | data version | Engineering term (owner decision, 2026-10-10). |
| "No" for a missing value | Not in this dataset | "No" is a recorded answer. |
| 0 for a missing figure | never | Zero is a measurement; a missing figure is not. |
| a party code in capitals | the party name in ordinary capitalization | Owner decision, 2026-10-10. |

## Open decisions

Terms or wordings no source settles yet. Each needs the owner.

- Census used: the reworded help text restates the 1920 claim and needs the owner's historical
  claim check before it ships. (owner)
- Margin and the second electoral share: the drafted notes await the owner's review on the
  dashboard. (owner)
