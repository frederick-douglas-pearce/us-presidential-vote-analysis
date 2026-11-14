# Glossary

What this project's terms mean, for readers who are not engineers, for developers who build on the
public API (API users), and for the people writing to them. Maintained by the `ba` agent; whatever
awaits the owner is listed under **Open decisions**.

**Statuses.** Every entry and wording rule ends with one of three. `settled`: a source settles
the meaning, and no merged reader wording for it is known to await the owner. It does not claim
the owner approved that wording: where the owner did, the entry's **Source** says so (#378 will check
this for every entry). `settled; wording pending (<what awaits the owner>)`: the meaning is
settled, but merged reader wording for it (for a rule, merged wording the rule governs) is known
to await the owner, for example a historical-claim check, a review on the live dashboard, or a
rewrite of merged text that does not yet follow the rule. `proposed (<the decision the owner
needs to make>)`: no source settles the meaning yet. An entry or rule that is not plain `settled`
is also listed under **Open decisions**. Wording still under review in an open pull request is
not marked here; that pull request carries it.

**This file records what terms mean; the code ships the wording.** The dashboard's shipped
wording lives in `dashboard/explore/labels.py` (`LABELS`, the metric labels `METRIC_LABELS`,
the closed-value tables, the null and help-text constants, the names of the site's controls and links, and every chart's text),
with a few page-level sentences in `dashboard/explore/components.py`,
`dashboard/explore/export.py` and the modules under `dashboard/explore/pages/`, and the site
title in `dashboard/explore/config.py` (`SITE_TITLE`). The API's published text is its
`/docs` page (also served at `/redoc` and `/openapi.json`) and the text of its responses
other than the data values they carry; `CLAUDE.md`, *Who writes wording*, lists
what that includes. It ships from five files under `src/usvote/api/`:

- `models.py`: field descriptions, response-model docstrings, and the prose inside response
  examples (the example error message in `_ERROR_EXAMPLE`).
- `routes.py`: the data endpoints' summaries and docstrings, query-parameter descriptions, and
  the error messages served for a year, state or candidate not in the data (404) and for an
  inverted year range (422).
- `app.py`: the API title (`API_TITLE`), summary (`API_SUMMARY`) and description; the tag names
  and descriptions (`_OPENAPI_TAGS`); the `/health` docstring; and the `/v1/meta` summary and
  docstring.
- `origin_guard.py`: the 403 error message (`_FORBIDDEN_BODY`).
- `provenance.py`: the `redistributable_note` text.

Each entry points at that code under **Shown as**; an API description reads "on the API's
`/docs` page, the `Model.field` field description in `src/usvote/api/models.py`". Some entry
names, a few plain definitions and the **Say instead** table use the same words readers see,
because those words are the plain term; each Say instead row names the code that ships its
wording, or marks it a rule that no single string ships. The code is the shipped form: if this
file and the code disagree, the code is what readers see; fix whichever is wrong and say which.

**Audiences.** Public readers of the dashboard at `explore.us-presidential-election-center.org`,
non-technical readers first (epic #275, product frame 3); readers of the "Counted, Not Assumed"
blog series under `posts/`; people who download a table as CSV; developers who build on the
public API at `api.us-presidential-election-center.org` and read its `/docs` page (**API
users**; owner decision, 2026-10-15, #374); the owner; and the agents who write labels, help
text and the API's published text. Plain definitions are written for the least technical of
them.

**The published posts are the best evidence of reader-facing wording.** They are owner-edited.
Where a post settles how a term reads, it is cited under **Source**; where a post and the code
disagree, the disagreement is a finding for the owner, and the post is never edited.

---

## Wording rules

These bind every label, cell, note and sentence a reader sees, and every wording drawn from this
file. They govern three surfaces: the dashboard (its pages and its CSV downloads), the API's
published text (its `/docs` page and its responses), and the marketing prose (the blog posts,
articles and announcements). Every rule binds all three unless the rule states an exception.

- **Editorial guardrails** (`CLAUDE.md`, "Publishing"): nothing critical of a data source is ever
  published, and every historical claim is checked before publishing. Wording describes what the
  dataset holds, never a fault in a source. *Source:* `CLAUDE.md`; #275, carry-forward
  constraints. *Status:* settled.
- **No underscores and no raw field names in reader wording.** A raw field name may appear only
  where the page presents it as a field name: a column header's tooltip, the "Column names" (or
  panel "Field names") list, and a CSV header row. It never appears in a label, a cell, a note, a
  preamble sentence or page prose, and neither does a raw coded value (for example a status code).
  The view link in a CSV preamble is exempt, as a header row is: it carries the API's own query
  names because it has to reopen the view exactly. The API's published text is the other
  exception: it writes public `/v1` names as served (*In the API's published text, public names
  are vocabulary*, below).
  *Source:* owner decision, 2026-10-10, #348; the view-link exemption, owner decision, 2026-10-11,
  #348; the API exception: owner decision, 2026-10-15, #374. *Status:* settled.
- **The API's published text is reader wording.** Everything the API publishes as text, on its
  `/docs` page and in its responses, follows these rules. `CLAUDE.md`, *Who writes wording*,
  lists what that includes, and the top of this file maps where each kind ships. Its readers are
  API users. The `ba` agent writes that text as a label spec checked against this file, and the
  parent agent applies it.
  *Source:* owner decision, 2026-10-15, #374. *Status:* settled; wording pending (#379: merged
  API text does not yet follow these rules).
- **In the API's published text, public names are vocabulary.** A public `/v1` field name, query
  parameter or served closed value (for example `legislature_chosen`, a `pv_status` value) is the
  word API users code against, so the API's text writes it as served, underscores included. A
  name that is also a public `/v1` field, query parameter or served value counts as public, even
  where a warehouse column has the same name (`took_office`, `pv_status`). The JSON value is
  null, never Python's None. The API's text never names any other warehouse table, view or column
  (`dwh.*`, `total_electoral_votes`, `president_*`, `candidate_votes`), a table inside the data
  file the API serves (`ec_pv`, `national_rollup`, `hybrid_summary`, `per_capita`), an internal
  key (`candidate_id`), or a project tracking reference (an issue number, a decision id such as
  D046, a story id such as E8-S8); a public document is linked by its URL. Prose spells out
  "Electoral College" and "popular vote"; `ec_` and `pv_` appear only inside field names.
  *Source:* owner decision, 2026-10-15, #374. *Status:* settled; wording pending (#379: merged
  API text does not yet follow this rule).
- **Every term an API description uses can be looked up here.** Each public `/v1` field with a
  meaning beyond its name has a defining entry whose **Shown as** names its `/docs` description,
  and each domain term the API's published text uses has an entry (which need not name every
  description that uses it). Fields that describe the response rather than the elections
  (`meta.count`, `schema_version`, `row_count`, `build_timestamp`, the license URLs) need no
  entry: their description is the definition. An API description is never a **Key index** row;
  that index lists `LABELS` keys only. Until #380 is done, most entries for `/v1` fields do not
  name their `/docs` description, and some fields and terms have no entry; that gap is in this
  file, not in wording readers see.
  *Source:* owner decision, 2026-10-15, #374. *Status:* settled.
- **"Counted" is reserved for vote counts** (Congress's count of electoral votes, and popular-vote
  counts). Anything else that is counted, such as people in a census or states in a total, gets
  other wording. On every surface these rules bind, a total that includes each state once says
  "each state included once", not "counted once". *Source:* owner decision, 2026-10-10, #348;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md` (appointed, cast, counted); "each state
  included once": owner decision, 2026-10-15, #374. *Status:* settled; wording pending (#379:
  merged API text does not yet follow this rule).
- **Plain words over legal and survey terms**: "census used" rather than "census in force", no
  "governs", "borders" rather than "footprint", no "apportionment" in reader wording, and "the
  National Archives" rather than "the Archives". The precise terms stay in this file. The API's
  published text has one exception: a public field name or served value that contains one of
  these words (`governing_census_year`, `no_governing_figure`) is written as served. *Source:*
  owner decision, 2026-10-10, #348; the API exception: owner decision, 2026-10-15, #374.
  *Status:* settled; wording pending (#379: merged API text does not yet follow this rule).
- **A chart title describes; a caption may state a finding.** A chart title says what the chart
  shows, never what it finds. Its caption may state a finding or carry narrative. A finding is a
  historical claim: it is checked before it is published and is never critical of a source
  (*Editorial guardrails*). An argument for the hybrid belongs only in its labeled opinion tab
  (*Hybrid*). Every chart's text (chart title, axis titles, trace names, legend title, hover text,
  annotations, caption, and any text written in place of tick numbers) ships from `labels.py`
  under a `ba` spec. *Source:* owner decision, 2026-11-05, #432;
  `.claude/specs/backlog-dashboard.md`, E9-S6, "Conventions every chart follows".
  *Status:* settled.

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
  rung of the ladder **appointed ≥ cast ≥ counted**. `electoral_denominator` on each
  `/v1/elections/summary` item is the same national figure.
- **Shown as:** `LABELS["state_electoral_votes"]` (T2, T4, T6, T7, and the C4/C5 table and C4's bars with one
  state chosen);
  `LABELS["national_electoral_denominator"]` (T3); in C1, the hover line "Electors appointed"
  (`labels.C1_EC_HOVER`), the majority line's label `labels.C1_MAJORITY_LINE`, and the caption
  sentences `labels.C1_BASES`, `labels.C1_EC_BASIS` and `labels.C1_MAJORITY_NOTE`. In C3, the hover
  line "Electors appointed" (`labels.C3_BAR_HOVER`) and the caption sentence `labels.C3_RATIO`. In
  C2, the hover line "Electors appointed" (`labels.C2_HOVER`), the line label
  `labels.C2_MAJORITY_LINE`, and the caption sentences `labels.C1_EC_BASIS` and
  `labels.C2_MAJORITY_NOTE`. `LABELS["electoral_denominator"]` (the C4/C5 table with all
  states); in C4: the bars, `labels.C4_X_AXIS`, the hover line "Electors appointed",
  `labels.C4_TITLE`, `labels.C4_TITLE_STATE`, `labels.C4_TITLE_SELECTED`,
  `labels.C4_NO_ELECTORS_TOOK_NO_PART`, `labels.C4_NO_ELECTORS`, `labels.C4_BASIS`,
  `labels.C4_ALL_STATES` and `labels.C4_ZERO_NOTE`.
- **Source:** `EcPvRow.state_electoral_votes`, `PerCapitaRow.state_electoral_votes` and
  `NationalSummaryRow.national_electoral_denominator` in `src/usvote/api/models.py`;
  `ElectionSummary.electoral_denominator`;
  `ElectionStateRow` (the same field, on `/v1/elections/states`); D041; D046 §5;
  D068; `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "Appointed, not cast" (the reader
  wording: allotment, electors appointed).
- **Not:** *Electoral votes cast.* An appointed elector who did not vote opens a gap between the
  two (`ELECTORAL_VOTE_SHORTFALLS` in `src/usvote/transform.py`). Not "electoral votes won".
- **Status:** settled

### Average margin (over the elections shown)
- **Plain:** For the elections the list on the Elections page shows, the typical gap between first
  and second place under one method: the Electoral College or the popular vote. Each average says
  how many elections it covers and which years, because this dataset has popular-vote figures only
  for recent elections, so the two averages can cover different elections.
- **Precise:** The arithmetic mean of a served margin (*Margin*): `ec_margin` or `pv_margin` on the
  `elections` items of `/v1/elections/summary`, over the years in T1's shown list (the same parsed
  filters T1 applies), each election weighted equally. A null is left out, never read as zero. N is
  the number of elections whose margin entered the average; its years are the earliest and latest of
  those, so they can be narrower than the years shown (over 1960–2024, the popular-vote average
  covers 1976–2024). Computed by the dashboard (`metrics.mean`), never served by the API, under
  D097: only count, sum and mean over served fields of one grain, never a ratio of fields or a
  recomputed served figure. Shown in percentage points to one decimal through `labels.margin`, so
  the average over one election equals that year's panel cell. With no contributing election it
  reads *No average*. A margin of the wrong type or a non-finite one among the years shown, or a
  mean no figure can show, reads *Unrecognized value*. If `/v1/elections/summary` cannot be read
  or is malformed, the two averages are replaced by one sentence and the count of elections shown
  still shows.
- **Shown as:** `labels.METRIC_LABELS["ec_margin_mean"]` and `labels.METRIC_LABELS["pv_margin_mean"]`;
  the value `labels.metric_mean` (`labels.METRIC_OVER`, `labels.METRIC_OVER_ONE`); under the
  averages, `labels.MARGIN_NOTE`, then `labels.METRIC_DIFFERENT_ELECTIONS` only when both averages
  are numbers, their number of elections or years differ, and at least one year in the electoral
  average lies outside the popular-vote window (`coverage`'s `pv_year_min`–`pv_year_max`), so the
  window is a cause of the difference; a difference that comes only from a missing margin inside
  the window shows no note, since each average shows its own number and years.
  `labels.METRIC_SAME_ELECTIONS` follows that note while the popular-vote filter is off.
  `METRICS_UNAVAILABLE` in `pages/elections.py`. On `/elections`, under `LIST_HEADING`, after the
  count of elections shown and before T1.
- **Source:** #437 acceptance criteria; the rule, owner-approved 2026-11-05 (#437 issue body),
  recorded in D097; `ElectionSummary.ec_margin` and `pv_margin` in `src/usvote/api/models.py`;
  `METRICS` in `dashboard/explore/metrics.py`; reader wording: `ba` spec for #437, approved at its
  plan gate.
- **Not:** A margin the API serves (*Margin*). The hybrid margin, which has no average. An average
  weighted by electors or votes. A gap measured from the Electoral College's winner or leader. Two
  averages over the same elections unless their number and years match.
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
  `labels.BOUNDARY_NOTE` (on each cell and under T6 and T7). In C3, the series names
  (`labels.BOUNDARY_BASIS` values), the plain series' name `labels.C3_PLAIN_SERIES` where a plain
  row is not at the election, the striped bars for `present_day`, the hover line "Borders used", and
  the caption sentences `labels.C3_STRIPES` (followed by `labels.BOUNDARY_NOTE`),
  `labels.C3_ALL_AT_ELECTION` and `labels.C3_PLAIN_MIXED`.
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
  only received popular votes are not in it. `/v1/candidates` lists each candidate once, with
  `candidate_slug`, `candidate` and the election years they appear in (*Election years a
  candidate appears in*).
- **Shown as:** `LABELS["candidate"]`; the candidate filter on `/election/<year>/states` (named by
  that page's `FILTER_SENTENCE` in `pages/election_states.py`) and `/state/<usps>`; the name, as served, as
  the link to the candidate history page `/candidate/<slug>` in T2, T3 and T4, and as that page's
  heading (`pages/candidate.py`), or `HEADING` there until a name is read, which is also the
  page's title (`title`) on any link that is not refused; on a refused link, `NOT_FOUND_HEADING`
  there, as heading and title (*Not-found state*); and in `pages/candidate.py`, the page's
  link-preview `description` and its download name; on the API's `/docs` page, the
  `CandidateListItem.candidate` and `CandidateListItem.candidate_slug` field descriptions in
  `src/usvote/api/models.py`.
- **Source:** `EcPvRow.candidate` and `candidate_slug`; D006; D007; `docs/canonical-keys.md`,
  "The two keys are two-tier"; `CandidateListItem` in `src/usvote/api/models.py`.
- **Not:** Everyone on the ballot.
- **Status:** settled; wording pending (#379: reader text does not call `candidate_slug`
  "durable", by owner decision, 2026-10-16, but these still do: this entry's **Precise**; the
  `/v1/candidates/{slug}` docstring in `src/usvote/api/routes.py`; and the
  `EcPvRow.candidate_slug` and `NationalSummaryRow.candidate_slug` field descriptions in
  `src/usvote/api/models.py`)

### Candidates in the dataset (dataset-wide count)
- **Plain:** How many different people received at least one electoral vote in any election in
  the dataset, each listed once however many elections they appear in.
- **Precise:** `candidate_count` on `/v1/meta`: the number of distinct `candidate_slug` values
  across every year served. A candidate is someone who received at least one electoral vote cast
  in some election (D007), so 1872's Greeley (3 cast, 0 counted) is included.
- **Shown as:** on the API's `/docs` page, the `SnapshotMetaResponse.candidate_count` field
  description in `src/usvote/api/models.py`. Not shown on the dashboard; showing it needs its own
  qualified `LABELS` key.
- **Source:** `SnapshotMetaResponse.candidate_count` in `src/usvote/api/models.py`; the
  `candidate_count` build in `src/usvote/snapshot.py` (distinct `candidate_slug`); D006; D007.
- **Not:** *Candidates with electoral votes (count per election)*; the sum of the per-election
  counts (a candidate in several elections is listed once).
- **Status:** settled

### Candidates with electoral votes (count per election)
- **Plain:** How many candidates received electoral votes in that election.
- **Precise:** `candidate_count` on a `/v1/elections` row: the number of distinct candidates in
  that year's national roll-up, which holds every candidate who received at least one electoral
  vote cast that year, including one whose votes Congress did not count (1872, Greeley: 3 cast,
  0 counted). `/v1/meta` also has a `candidate_count` with another meaning: see *Candidates in
  the dataset (dataset-wide count)*.
- **Shown as:** `LABELS["candidate_count"]` (T1); on the API's `/docs` page, the
  `YearListItem.candidate_count` field description in `src/usvote/api/models.py`.
- **Source:** `YearListItem.candidate_count` in `src/usvote/api/models.py`;
  `SnapshotRepository.list_years` in `src/usvote/api/repository.py` (per-year count over
  `national_rollup`), which counts distinct candidates because `national_rollup` is keyed
  `(year, candidate_slug)` in `src/usvote/snapshot.py`; D007; the `labels.py` module docstring;
  header wording: owner decision, 2026-10-10, #348.
- **Not:** Candidates on the ballot; *Candidates in the dataset (dataset-wide count)*; only
  candidates whose votes Congress counted.
- **Status:** settled

### Census figure (per-capita coverage)
- **Plain:** Whether there is a census population figure for that state at that election.
- **Precise:** `coverage` on a per-capita row: `covered`, or `no_governing_figure` where no
  census figure exists for the state and year (one cell, 1848 Texas, which the United States had
  not enumerated in 1840). `no_governing_figure` holds exactly where `population` is null.
- **Shown as:** `LABELS["coverage"]`; values `labels.PER_CAPITA_COVERAGE`, read by
  `labels.per_capita_coverage`, `labels.population` and `labels.persons_per_electoral_vote`. In C3,
  the marker label `labels.C3_NO_CENSUS_FIGURE`, with the full cell in its hover
  (`labels.C3_NO_FIGURE_HOVER`).
- **Source:** `PerCapitaRow.coverage`; D060(h); D069(e); value wording: owner decision,
  2026-10-10, #348 (no "governs").
- **Not:** *Years covered* (`meta.provenance.coverage`) or the *share of electors from
  popular-vote states* (`pv_coverage`). The plain `LABELS` key `coverage` means this one only
  (`labels.py` module docstring).
- **Status:** settled

### Census used (governing census)
- **Plain:** The census used for the latest redistribution of House seats among the states made
  before the election. Electoral votes follow House seats, so that redistribution also shared out
  the electoral votes. Its population figure for the state, where it has one, is the one shown.
  For most states and years that census also set the state's electoral votes. It did not for a
  state at the elections between its admission and the first redistribution of House seats that
  included it, for California from 1852 to 1860, or for DC from 1964.
- **Precise:** `governing_census_year`: the census of the apportionment that the rule for
  electors applies at that election. A state's electors equal the senators and representatives it
  is entitled to when the President chosen takes office, except that where no apportionment has
  been made after the latest census at the time electors are chosen, the existing apportionment
  applies (Act of March 1, 1792, ch. 8, § 1, 1 Stat. 239; the same rule and proviso are in
  3 U.S.C. § 3). So it is the census of the latest apportionment made before electors are chosen,
  not the one the sitting House was elected under: at the November 1912 election the House still
  sat on the 1900 apportionment, because the act of August 8, 1911 took effect after March 3,
  1913, yet 1912's electors follow the 1910 apportionment. Nor is it the nearest census. By the
  proviso, 2020 reads 2010 (the 2020 census was apportioned in 2021, after electors were
  chosen), and 1924 and 1928 read 1910 (Congress made no apportionment after the 1920 census, the
  only census without one). The act of June 18, 1929 provided for
  apportioning each census; the 1930 census was the first apportioned under it, and 1932 the first
  election its apportionment set. The 1940 census's seats were fixed by a further act, of November
  15, 1941, which also amended the 1929 act so that each later census is apportioned without a new
  act of Congress. `governing_census_year` in `src/usvote/apportionment.py`
  computes the year: the latest census, taken at least two years before the election, that
  produced an apportionment, which skips 1920. `GOVERNING_CENSUS_BY_ELECTION` is that function
  over every election in the dataset. This is the vintage axis of D066(b): which census supplies
  the figure. It is not always where the state's allotment came from (D066(b)'s third axis). The
  allotment did not come from this census for a state at the elections between its admission and
  the first apportionment that included it (West Virginia 1864 and 1868 among them: its three
  seats came out of Virginia's 1860 allotment when it was formed in 1863), for California
  1852–1860 (two seats under its admission act, which the House Historian's table lists under
  1850), and for DC from 1964 (the Twenty-third Amendment). The row still shows this census's
  population, where it has one. `docs/governing-census.md` lists the rows.
- **Shown as:** `LABELS["governing_census_year"]`; help text `labels.GOVERNING_CENSUS_NOTE` under T6
  and T7 and in their downloads' preambles; on the API's `/docs` page, the
  `PerCapitaRow.governing_census_year` field description in `src/usvote/api/models.py`. In C3,
  the title `labels.C3_TITLE` (the census year), the hover line "Census used"
  (`labels.C3_BAR_HOVER`), and the caption sentences `labels.C3_CENSUS` and
  `labels.C3_CENSUS_MIXED`. These, and the help text `labels.GOVERNING_CENSUS_NOTE`, follow this
  entry's Plain and do not say the census set the state's electoral votes.
- **Source:** `PerCapitaRow.governing_census_year`; `governing_census_year` in
  `src/usvote/apportionment.py`, which computes it, and `GOVERNING_CENSUS_BY_ELECTION` there, that
  function over every election; `tests/unit/test_apportionment.py`, which pins the mapping to a
  hand-written list of every election; D060(b) ("a derivation plus a named exception set"); D064;
  D066(b); the rule for electors: Act of March 1, 1792, ch. 8, § 1, 1 Stat. 239, and 3 U.S.C. § 3
  (June 25, 1948, ch. 644, 62 Stat. 672); `docs/governing-census.md` (#356), which records the
  citations for the help text's historical claim, finds the mapping right for every election, and
  lists the rows where the census used did not set the state's electoral votes;
  `posts/2026-09-03-how-did-we-get-to-538-electors.md`, "The decade Congress skipped" (the 1920
  gap, and the 1910 map electing 1924 and 1928); header wording: owner decision, 2026-10-10, #348;
  the help text's wording: the owner's ruling at the #352 plan gate, 2026-10-12, reworded so that
  no row contradicts its first clause (it describes the population a row shows, and 1848 Texas
  shows none): owner decision, 2026-11-13, #423; this definition
  (Plain: the census of the latest apportionment made before electors are chosen; Precise: the
  rule for electors, anchored to the term of the President chosen, with its proviso): owner
  decision, 2026-11-02, #356 code review.
- **Not:** The census nearest the election. Not, in every row, the census that set the state's
  electoral votes (see **Precise**). Not a population figure in every row: 1848 Texas has none
  (*Census figure*).
- **Status:** settled; wording pending (#379: the `PerCapitaRow.governing_census_year` field
  description in `src/usvote/api/models.py` says "in force at this election", which does not hold
  for 1912 and the other elections two years after a census, and uses "apportionment" in prose)

### Chart (C1, C2, …)
- **Plain:** A drawing of some of this dataset's numbers on a page, with a title, a caption under
  it and a link to the table on the same page that holds its numbers. The tables are the record.
  A chart is another way to see it, and the page works without one.
- **Precise:** Built only by `components.chart(chart_id, figure, table_id, caption)`. It is an
  HTML `figure` element holding, in order, the **chart title**, the drawing, and a caption
  (`figcaption`). The title is written as page text (a paragraph, not a heading), so it shows and
  wraps even when the drawing cannot load. The caption ends with the table pointer,
  `labels.CHART_TABLE_POINTER`, a link to the chart's *Companion table*. The builder refuses a
  chart with no title or no caption. Each series writes its own hover text or shows none. A figure
  that breaks the chart rules `charts.figure_problems` checks (a series whose hover text would be
  plotly's own, a color that is not a theme token, and the rest) is not drawn. The chart keeps its
  title, its caption and the pointer, with nothing shown between them, as when plotly.js cannot
  load. The page keeps its tables and its other charts, and the failure is logged at error level
  for the developer. Readers see no message about it. The chart title is plain text and says what
  the chart shows; the caption may state a finding (*A chart title describes; a caption may state
  a finding*). For assistive technology, a drawn chart, and one still waiting for plotly.js or
  whose load failed, is an image named by its chart title, and what is drawn inside it is skipped;
  a chart that is not drawn is no image, only its title and caption as text. Either way the
  companion table carries the numbers. Pointing at a mark shows only the hover text written for
  that series, for the nearest point. Axis numbers are
  written in full with thousands separators, as the tables write them, never shortened ("80M",
  "1.2B"). The legend is only a key: clicking it hides nothing. A reader cannot zoom or drag a
  chart, and no toolbar shows on it. Every chart has a **chart ID**, `C<n>`, issued in order of
  story filing. An ID is never renumbered or reused, and a retired ID stays retired. The closed
  registry `CHARTS` in `dashboard/explore/charts.py` maps each ID to its page and its companion
  table. The chart's element id is the ID in lower case (`c1`), so `/elections#c2` is a link to
  that chart. The part after `#` never reaches the server and changes neither the canonical link
  nor `og:url`. Readers meet the ID only in such a link, never in page text. Colors come from the
  page's theme tokens and follow the *Theme in effect*: switching the theme redraws every chart on
  the page, with no reload and no request. Series always differ by more than color. The drawing
  needs plotly.js, which the browser fetches from plotly's CDN when the page's first chart
  mounts; a page with no chart fetches nothing from it. If the fetch fails, or the figure breaks
  the chart rules, no drawing appears, and the title, the caption, the pointer and the page's
  tables still show. A chart is never a page's success marker. A chart has no download of its
  own: its companion table's CSV carries its numbers.
- **Shown as:** `components.chart`, which writes each chart's title as page text above the drawing
  (`html.P`, class `chart-title`, id `<chart element id>-title`) and its caption below it;
  `labels.CHART_TABLE_POINTER`; each chart's own wording (title, axis titles, trace names, legend
  title, hover text, annotations, caption) in `labels.py`; the axis number format, the hover
  behavior and the inert legend in `charts.TEMPLATE`, and the absent toolbar in
  `charts.CHART_CONFIG`, both in `dashboard/explore/charts.py`. C1, on the election overview
  (`/election/<year>`), is the first chart a page renders. C3 is on an election's People per
  electoral vote page (`/election/<year>/per-capita`). The home page's lede (`pages/home.py`)
  already says "Tables and charts". C2 is on the elections index (`/elections`), above the filters.
  C4 and C5 are on `/elections`, after the list of elections, followed by the one companion
  table they share.
- **Source:** #432 acceptance criteria; `.claude/specs/backlog-dashboard.md`, E9-S6,
  "Conventions every chart follows"; owner decisions, 2026-11-05 (titles describe the chart and a
  caption may state a finding or carry narrative; plotly.js from its CDN, loaded lazily, with no
  SRI), recorded in D087; the drawing put in only once plotly.js has loaded, so a failed load
  leaves its space empty: owner decision on #452, 2026-11-07, recorded in D088; owner decisions
  at #432's plan gate, 2026-11-06 (the table pointer's wording, no toolbar, no chart IDs in
  reader text); `CHARTS` and `dom_id`, `TEMPLATE` and `CHART_CONFIG` in
  `dashboard/explore/charts.py`; a figure that breaks the chart rules is not drawn, and its page
  keeps its tables: #467 acceptance criteria, recorded in D095.
- **Not:** A *figure*: in this file and on the page, a figure is a number ("no popular-vote
  figure"), and Plotly's and HTML's word for a chart stays in code. Not a page's title (the
  browser tab, `og:title`): a chart has a chart title. Not a stand-in for its companion table.
  Not a column-name list.
- **Status:** settled

### Companion table
- **Plain:** The table on the same page that holds a chart's numbers. The link at the end of the
  chart's caption goes to it, and its download is how to take those numbers away.
- **Precise:** The table that each chart's registry row names by its element id. Two charts can
  share one companion table (C4 and C5). On `/elections` the state filter switches both charts
  and their table together (D100).
  `components.chart` refuses any other table. The table pointer links to `#<table id>`, the table
  element itself, below the table's heading. Every chart's pointer has the same text; the caption
  it ends tells the reader which chart it belongs to. Like every table, it is built by
  `components.table` with its own CSV. A filter on the page can narrow the table without
  narrowing the chart, so the pointer says only that the chart's numbers are in a table on the
  page, never that the table shows "the same" or "all" of them.
- **Shown as:** `labels.CHART_TABLE_POINTER`, at the end of each chart's caption.
- **Source:** #432 ("a pointer to the table on the page that holds the same values"); E9-S6
  conventions ("a companion table holding the same values"); `CHARTS` in
  `dashboard/explore/charts.py`; the pointer's wording: owner decision, 2026-11-06, #432.
- **Not:** The chart's caption. A table on another page. The column-name list under the table.
- **Status:** settled

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
  values `labels.COUNT_STATUS`; the cell `labels.count_status`, which shows the reason verbatim
  only when it is text with something in it, and leaves it out otherwise (the download keeps it
  as served; #355); the count-status filter on `/election/<year>/states` (named "count status" by
  that page's `FILTER_SENTENCE` in `pages/election_states.py`).
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
  `labels.HAS_POPULAR_VOTE_NOTE` and the page ledes, among them the election overview's `LEDE` in
  `pages/election.py`, which names that page's sections in the order they appear (the election panel
  before National results). `LEDE` and `FILTER_SENTENCE` in `pages/elections.py`.
- **Source:** `CLAUDE.md`, "Publishing" (editorial guardrail); `.claude/specs/backlog-dashboard.md`,
  "Carry-forward constraints"; D030; D070; `posts/2026-08-06-222-votes-away.md`, "The record the
  argument runs on top of" (the 1976 popular-vote edge described as a licensing boundary, not a
  records one); the order of `LEDE` in `pages/election.py`, which follows the order of the
  page's sections (owner approval at #433's plan gate, 2026-11-09; recorded here with #466);
  since #465, Results by state and People per electoral vote are pages of their own (*Election
  pages*).
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
- **Not:** A not-found state (*Not-found state*): a link whose year, state code or candidate slug
  the dataset does not serve, or whose election section the site does not have
  (`labels.ELECTION_NOT_FOUND_SENTENCE` for the election pages, and `NOT_FOUND_SENTENCE` in
  `pages/state.py` and `pages/candidate.py`). An empty filter result (`components.NO_ROWS`). The
  panel's own unavailable state (`PANEL_UNAVAILABLE`). A chart that is not drawn (*Chart*): its page
  still shows, with its tables. A chart section's own unavailable state (`C2_UNAVAILABLE` in
  `pages/elections.py`, id `elections-leader-unavailable`): the rest of the page still shows. The
  averages' own unavailable state (`METRICS_UNAVAILABLE` in `pages/elections.py`): the count of
  elections shown and the rest of the page still show. The over-time section's own states:
  `OVER_TIME_UNAVAILABLE` (`pages/elections.py`) when `/v1/elections/summary` cannot be read,
  with the rest of the page still shown; and `OVER_TIME_NO_STATES` when `/v1/elections/states`
  cannot be read or is malformed, with the all-states charts and their table still shown.
- **Status:** settled

### Election pages (overview, results by state, people per electoral vote)
- **Plain:** Each election in this dataset has three pages. The overview shows who led under each
  method and the national results, with a chart. Results by state shows every state's electoral
  votes for each candidate, which a reader can narrow by state, candidate, popular-vote status or
  count status. People per electoral vote shows, in a chart and a table, how many people each state's electoral votes stood for; a reader can narrow the table to one state, which the chart then marks. Links near the top of each page go between the
  three, and the page being read is marked. On each page, the earlier and later links go to the
  same page for the neighboring election.
- **Precise:** Three registered pages: `/election/<year>`, the overview (the election panel,
  National results with C1 and T3, and the provenance footer; no filters); `/election/<year>/states`
  (T2 and its four filters, `state`, `candidate`, `pv_status` and `electoral_count_status`); and
  `/election/<year>/per-capita` (C3, T6 and a `state` filter, checked against T6's own rows, which falls
  back to every state when the code is not among them). Each page checks the year against
  `/v1/elections`; a year it refuses gets the same not-found state on all three (*Not-found state*),
  and a link naming a section the site does not have (`/election/1824/x`) reaches the overview,
  whose check refuses it, so it gets the overview's not-found state too, with the same status and
  title (*Not-found state*), never *Page not found*. On a successful
  render each page carries the section links, a landmark named `labels.ELECTION_SECTIONS_LABEL`:
  the page being read is text marked `aria-current="page"`, and the other two are links that open
  without reloading the page. The earlier and later links on a subpage go to the same subpage of the
  neighboring served year, with no filters. A link to `/election/<year>` that carries any of T2's
  filters is redirected (302) to `/election/<year>/states` with those filters. "Overview" is never
  "summary", which is the API's name for T3's data (`summary` on `/v1/elections/{year}`).
- **Shown as:** the section links `labels.SECTION_OVERVIEW`, `labels.SECTION_STATES` and
  `labels.SECTION_PER_CAPITA` and their landmark name `labels.ELECTION_SECTIONS_LABEL` (read by
  assistive technology, not shown); the overview's `HEADING`, `LEDE` and `description` in
  `pages/election.py`; `STATES_HEADING`, `STATES_GENERIC_HEADING`, `LEDE`, `FILTER_SENTENCE` and
  `description` in `pages/election_states.py`; `PER_CAPITA_HEADING`, `PER_CAPITA_GENERIC_HEADING`,
  `LEDE`, `FILTER_SENTENCE` and `description` in `pages/election_per_capita.py`.
- **Source:** #465 (owner decisions, 2026-11-09: the split, the per-capita state filter, the earlier
  and later links keeping the page, the 302); D092; reader wording: `ba` spec for #465, approved by
  the owner at its plan gate (2026-11-10).
- **Not:** *Site navigation*. The earlier and later links (*Election year*). The API's `summary`.
  A filter: the section links change the page, not the rows. The API route `/v1/elections/states`,
  which has one item per state per election and no candidate rows; Results by state shows
  candidates' results.
- **Status:** settled

### Election year
- **Plain:** The year the presidential election was held.
- **Precise:** `year`. The years served run from `meta.provenance.coverage.year_min` to
  `year_max`, read from the response, never written as a literal. On each election page (*Election
  pages*), the earlier and later links go to the nearest year before and after it that
  `/v1/elections` serves, on the same page (the overview, results by state, or people per
  electoral vote), read from that index and never computed as four years before or after; a year
  with no served year on one side has no link on that side. "Earlier" and "later" are about the years this
  dataset serves, not a claim that no election fell between two linked years.
- **Shown as:** `LABELS["year"]`; the year-range slider (`/elections`, `/state/<usps>`); the label
  of the year control on `/candidate/<slug>`, and the lede sentence that offers it
  (`FILTER_SENTENCE` in `pages/candidate.py`); the election pages' headings: `HEADING` on the overview
  (`pages/election.py`), `STATES_HEADING` (`pages/election_states.py`) and `PER_CAPITA_HEADING`
  (`pages/election_per_capita.py`), each the `H1` that page's `render` builds and the start of its
  title (`title`); on the degraded state, and in the title before a year is checked, "Election" on
  the overview (a literal in `layout` there), `STATES_GENERIC_HEADING` and
  `PER_CAPITA_GENERIC_HEADING`; the earlier and later links on every election page
  (`labels.EARLIER_LINK` and `labels.LATER_LINK`) and their accessible names
  (`labels.ELECTION_NAV_LABEL` on the overview and `labels.ELECTION_NAV_SECTION_LABEL` on the
  subpages, read by assistive technology, not shown). The
  links sit in a bordered bar above the page heading, the earlier link at the left and the later
  at the right, each with a chevron pointing its way (before the earlier link's text, after the
  later's). The chevrons are drawn shapes with no text: they are not part of either link's name
  and are never read aloud, so the words "Earlier" and "Later" carry the direction.
- **Source:** `EcPvRow.year`, `YearListItem.year`; `Coverage.year_min` and `year_max`; the
  earlier and later links: #324; their reader wording: owner decision, 2026-10-30, #324; the bar
  above the heading and its decorative chevrons: #464; the links keeping the page on the
  subpages: #465.
- **Not:** *Census used*, which is also a year.
- **Status:** settled

### Election years a candidate appears in (`years`)
- **Plain:** The election years in which a candidate received at least one electoral vote, oldest
  first.
- **Precise:** `years` on a `/v1/candidates` item: the distinct `year` values of that candidate's
  rows, sorted oldest first, which are the years `/v1/candidates/{slug}` returns rows for. The basis
  is electoral votes cast, as for `candidate_count` on `/v1/elections`, so 1872 is among Horace
  Greeley's years (3 cast, 0 counted). Never empty. Candidates who received popular votes only are
  not in this dataset, so they are not listed.
- **Shown as:** on the API's `/docs` page, the `CandidateListItem.years` field description in
  `src/usvote/api/models.py`. The same years are the year options on `/candidate/<slug>` (with
  `ALL_YEARS` first, and no control for a candidate with one year), which the page builds from
  that candidate's `/v1/candidates/{slug}` rows, not from the `years` field; the two agree because
  `years` lists exactly the years that endpoint returns rows for. `years` itself is not shown, and
  showing the field needs its own `LABELS` key.
- **Source:** `CandidateListItem.years` in `src/usvote/api/models.py` and
  `SnapshotRepository.list_candidates` in `src/usvote/api/repository.py` (#330); D007.
- **Not:** Years the candidate ran or was on the ballot; only years whose electoral votes Congress
  counted (*Electoral votes counted*); years the candidate took office (*Took office*).
- **Status:** settled

### Elections shown (count)
- **Plain:** How many elections the list on the Elections page shows under the filters in effect,
  out of all the elections in this dataset.
- **Precise:** The number of `/v1/elections` rows T1 shows after the year-range and popular-vote
  filters (`metrics.count`), beside the number of elections served. An average's own number of
  elections (*Average margin*) can be smaller: it includes only elections that have that margin.
- **Shown as:** `labels.METRIC_LABELS["elections_shown"]`, the count line above T1 on `/elections`.
- **Source:** #437 acceptance criteria; D097; `METRICS` in `dashboard/explore/metrics.py`.
- **Not:** The number of elections an average covers. *Candidates in the dataset*. Another page's
  "Showing n of m rows" line, which counts table rows.
- **Status:** settled

### Electoral College winner, or leader with no majority (`ec_winner`)
- **Plain:** The candidate with the most electoral votes counted. When that candidate has a
  majority of the electors appointed, they are the Electoral College winner. When no one has a
  majority, they are only the Electoral College leader, and the House chose the president: in
  1824 Jackson led and the House chose Adams.
- **Precise:** `ec_winner`, the candidate with the largest counted electoral share. Its reader
  name depends on `ec_determinative` from the same election block: true reads as the Electoral
  College winner; false reads as the Electoral College leader with no majority; null reads as
  the Electoral College leader, claiming neither a majority nor its absence (owner decision, 2026-10-11, #348); so does a value this page does not recognize.
  Neither name says who took office.
- **Shown as:** `LABELS["ec_winner"]`, the label wherever no recognized `ec_determinative` is in
  hand; `labels.EC_WINNER` and `labels.EC_LEADER_NO_MAJORITY`, chosen by `labels.ec_winner_label`
  from `ec_determinative` for the panel row and its field-name list (`_panel` in
  `pages/election.py`, through `labels.glossary`'s `chosen` map); the cell `labels.winner`;
  `labels.flip`, which names the role in `labels.FLIP_YES` by the same test as
  `labels.ec_winner_label` (`labels._ec_role_is_winner`). In C2, the title `labels.C2_TITLE`, the
  caption sentences `labels.C2_LEADER_POINT` and `labels.C2_TOOK_OFFICE`, the companion table's
  heading `C2_TABLE_HEADING` and its notes `labels.C2_LEADER_ROW` and `labels.C2_TOOK_OFFICE`.
- **Source:** owner decision, 2026-10-10, #348; `ElectionSummary.ec_winner` and `ec_determinative`;
  D041; D038 (the 1824 rationale); `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "The one time
  it happened" (the electoral leader, majority outright, who took office);
  `posts/2026-08-06-222-votes-away.md`, "The record the argument runs on top of" (Electoral College
  winner); `posts/2026-08-18-presidential-elections-are-messy.md` (1824: Jackson led with no
  majority, and the House chose John Quincy Adams).
- **Not:** *Took office*, which is who became president. *Electoral College majority*, which is
  the yes or no behind the name.
- **Status:** settled

### Electoral College leader's share chart (C2)
- **Plain:** A chart on the Elections page with a row for each election in this dataset, oldest at
  the top. Each row has one point: the electoral share of that election's Electoral College leader,
  the candidate with the most electoral votes counted, labeled with its number as the table on the
  same page writes it. A dashed line marks half of each election's electors appointed. A leader
  whose share is more than half had a majority of them. With half or less, no candidate had a
  majority, and the election went to the House of Representatives. The leader did not always take
  office: in 1824 the House chose John Quincy Adams. Its table also says whether each leader took
  office. The chart and its table always show every election in this dataset; the list's year and
  popular-vote filters narrow only the list of elections and the averages computed from it, and
  the state choice changes only the charts of electors appointed and the total popular vote.
- **Precise:**
  - Chart ID C2 in `CHARTS` (`dashboard/explore/charts.py`), on `/elections`, element id `c2`.
  - Its *Companion table* is `elections-leader-table`, in the C2 section, before the list of
    elections. Its columns, by public field name: `year`, `candidate`,
    `national_electoral_votes_counted`, `national_electoral_denominator`, `ec_share_full`,
    `ec_determinative` (`labels.ec_majority`), `took_office` (`labels.yes_no`). `took_office` is in
    the table only, never drawn; it is there so `labels.C2_TOOK_OFFICE` can be checked.
  - It sits after the lede and before the filters, under `C2_HEADING`.
  - Data: built from `/v1/elections/summary`, filled on first use (declared in `on_miss`, D074(ii))
    and read in the same view as `/v1/elections`. Each year `/v1/elections` serves gets one point,
    from that year's single `data` row with `electoral_rank` 1: its served `ec_share_full`, with
    that year's `elections` item's `ec_determinative`. A body with a year missing, a second rank-1
    row or an unserved year shows the section's unavailable state.
  - It derives nothing. Each point's text is `labels.share_cell`. The hover writes the companion
    table's cells: votes counted and electors appointed, never votes cast (1868: 214 and 294; 1872:
    286 and 366; 2016: 304 and 538).
  - The share axis runs 0–100%. The line stands at 0.5 and the test is strict, so a point on the
    line is not a majority.
  - A share that is not a finite number draws a marker at zero, labeled `labels.C1_NO_SHARE` or
    `labels.UNRECOGNIZED`. That marker trace is `labels.C2_NO_SHARE_SERIES`, never shown. A year is
    never dropped.
  - No popular-vote figure or hybrid score is drawn.
  - Neither the chart nor its companion table is narrowed by a filter (D093(a); fork B, D096,
    amending D093(c)).
  - If the summary read fails, the section shows `C2_UNAVAILABLE`, with no chart and no companion
    table, and T1 still renders.
- **Shown as:**
  - Placed by `pages/elections.py` through `components.chart`.
  - Chart text in `labels.py`: `labels.C2_TITLE`; the axis `labels.C2_X_AXIS`
    (`LABELS["ec_share_full"]`); the line label `labels.C2_MAJORITY_LINE`; the hover
    `labels.C2_HOVER`; the marker labels `labels.C1_NO_SHARE` and `labels.UNRECOGNIZED`; the caption
    `labels.C2_LEADER_POINT`, `labels.C1_EC_BASIS`, `labels.C2_MAJORITY_NOTE` and
    `labels.C2_TOOK_OFFICE`, then `labels.CHART_TABLE_POINTER`; the trace names
    `LABELS["ec_share_full"]` and `labels.C2_NO_SHARE_SERIES` (never shown).
  - In `pages/elections.py`: `C2_HEADING`, `C2_TABLE_HEADING`, the companion table's columns
    (existing `LABELS` keys, `took_office` last), the table notes `labels.C2_LEADER_ROW` and
    `labels.C2_TOOK_OFFICE`, the download "the Electoral College leaders"
    (`elections-electoral-college-leaders.csv`), and `C2_UNAVAILABLE`. After the section,
    `LIST_HEADING` heads the filters, the count of elections shown, the averages (*Average
    margin*) and T1: the list of elections and the numbers computed from it, the only part of the
    page the year and popular-vote filters narrow.
- **Source:** #434 acceptance criteria (the counted basis: owner, 2026-11-05); `CHARTS`;
  `NationalSummaryRow.ec_share_full`, `electoral_rank`, `national_electoral_votes_counted` and
  `national_electoral_denominator`, `ElectionSummary.ec_determinative` and
  `AllElectionsSummaryResponse` in `src/usvote/api/models.py`; D041; D046 §4; D091; D093; D096;
  `posts/2026-08-18-presidential-elections-are-messy.md` (Jackson 99 of 261, 37.9 percent; the House
  chose John Quincy Adams); `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "The one time it
  happened"; reader wording: `ba` spec for #434, approved at its plan gate (2026-11-11), with its
  historical claims.
- **Not:** A chart of winners: in 1824 the leader had no majority. The chart does not show who took
  office (*Took office*); its companion table does, in its last column. Not votes cast. The line is
  not a fixed number such as 270. Not the hybrid. Not a stand-in for its companion table. A marker
  is not a zero.
- **Status:** settled

### Electoral College majority
- **Plain:** Whether any candidate won more than half of all the electors appointed that year. If
  none did, the election went to the House.
- **Precise:** `ec_determinative`: true exactly when the leader's *electoral share* (votes counted
  ÷ electors appointed) is above 0.5. The test is strict, so an exact tie reads as no majority.
  `false` is a real outcome (1824), not missing.
- **Shown as:** `LABELS["ec_determinative"]`; `labels.EC_MAJORITY`, `labels.NO_EC_MAJORITY`, via
  `labels.ec_majority`; in C1, the dashed line at half of the electors appointed, labeled
  `labels.C1_MAJORITY_LINE`, and the caption sentences `labels.C1_MAJORITY_NOTE` and, in a year with
  popular-vote figures, `labels.C1_LINE_EC_ONLY`. In C2, the dashed line labeled
  `labels.C2_MAJORITY_LINE`, the caption sentence `labels.C2_MAJORITY_NOTE`, the hover's last line
  (`labels.ec_majority`), the companion table's column, and the section heading `C2_HEADING`.
- **Source:** `ElectionSummary.ec_determinative`; D041; D046 §4;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "Appointed, not cast".
- **Not:** A majority of the votes cast or counted; the base is the electors appointed. A null,
  which names no cause.
- **Status:** settled

### Electoral rank
- **Plain:** Where a candidate finished nationally by electoral votes counted (1 = most).
- **Precise:** The national finishing rank on the counted basis, so it may not order the cast
  totals. Candidates with equal counted totals share a rank.
- **Shown as:** `LABELS["electoral_rank"]` (T3); on the API's `/docs` page, the
  `EcPvRow.electoral_rank` and `NationalSummaryRow.electoral_rank` field descriptions in
  `src/usvote/api/models.py`.
- **Source:** `NationalSummaryRow.electoral_rank`; D046 §4.
- **Not:** *Took office* (1824).
- **Status:** settled

### Electoral share
- **Plain:** A candidate's electoral votes counted, as a share of all the electors appointed that
  year.
- **Precise:** `ec_share_full` = counted ÷ appointed. No coverage policy can move it, and it is
  the only input to `ec_determinative`. Because some appointed electors never vote, shares can sum
  to less than 100% (D041). `ec_share_hybrid` is the electoral share fed into the hybrid; under
  the only configured policy, (b), it equals `ec_share_full`, and the API serves it separately so
  that can be checked.
- **Shown as:** `LABELS["ec_share_full"]` (T3, the name of C1's electoral-share series, and the
  start of the hover of C1's marker for a null or blank electoral share); `labels.share_cell`; in C1
  (*Electoral share and popular-vote share chart (C1)*), the titles `labels.C1_TITLE` and
  `labels.C1_TITLE_NO_PV`, the hover text `labels.C1_EC_HOVER`, the label `labels.C1_NO_SHARE` of
  the marker drawn in place of a null or blank electoral-share bar, and the caption sentences
  `labels.C1_BASES`, `labels.C1_EC_BASIS`, `labels.C1_MAJORITY_NOTE`, `labels.C1_LINE_EC_ONLY` and
  `labels.C1_ROW_ORDER`; each electoral-share bar's text is T3's cell for the same value.
  `ec_share_hybrid` is on no dashboard page and in no download since #358; the API serves it. In C2,
  the title `labels.C2_TITLE`, the axis `labels.C2_X_AXIS`, each point's text (`labels.share_cell`),
  the hover `labels.C2_HOVER`, the marker label `labels.C1_NO_SHARE` and the caption sentence
  `labels.C1_EC_BASIS`.
- **Source:** `NationalSummaryRow.ec_share_full` and `ec_share_hybrid`; D037; D038; D041;
  D042 §2; D046 §4; one electoral share on the page and in T3's download: owner decision,
  2026-11-02, #358.
- **Not:** A share of the votes cast.
- **Status:** settled

### Electoral share and popular-vote share chart (C1)
- **Plain:** A chart on an election's overview page, with a row for each candidate. Each row has a
  bar for the candidate's electoral share and, in a year this dataset has popular-vote figures
  for, a bar for their popular-vote share. A dashed line marks half of the electors appointed: a
  candidate whose electoral share is more than half has a majority of them. Every bar is labeled
  with its number, written as the National results table on the same page writes it. Where this
  dataset has no popular-vote figure for a candidate, the row shows a labeled marker in place of
  the bar, never a bar of zero length; a real zero is a drawn bar, labeled with its zero.
- **Precise:** Chart ID C1 in `CHARTS` (`dashboard/explore/charts.py`), on `/election/<year>`,
  with T3 as its *Companion table* (`election-nation`, `NATION_TABLE_ID` in `pages/election.py`);
  its element id is `c1`. It sits in the National results section of the election overview, between
  that section's heading and T3; Results by state is a page of its own (*Election pages*). Horizontal grouped bars, one row per
  candidate in T3, with the candidate's name as the row label (that axis has no title) and
  `labels.C1_X_AXIS` on the share axis. The electoral-share series is `ec_share_full`
  (*Electoral share*: votes counted ÷ electors appointed), named `LABELS["ec_share_full"]`; the
  popular-vote series is `pv_share` (*Popular-vote share*), named `LABELS["pv_share"]`, drawn only
  in a year inside the popular-vote window. In each row the upper bar is the electoral share. Each
  drawn bar's text is T3's cell for the same value, so the chart and the table write each number
  alike; a zero is drawn and labeled (1872, Greeley's counted electoral share, 0.0%). Inside the
  window, a null or blank popular-vote share draws, in the bar's place, a marker labeled
  `labels.C1_NO_FIGURE` (*No popular-vote figure in this dataset*). In any year, a null or blank
  electoral share, which T3 shows as `labels.NOT_IN_DATASET` (*Not in this dataset*), draws a
  marker labeled `labels.C1_NO_SHARE`, whose hover names the series as T3's header does. A value
  in either series that the page has no label for draws a marker labeled `labels.UNRECOGNIZED`
  (*Unrecognized value*). All three markers belong to one series, named
  `labels.C1_NO_FIGURE_SERIES` for the figure rules and kept off the legend, so no reader sees
  that name. The dashed line stands at 0.5 on the
  share axis, half of the electors appointed (*Electoral College majority*); the test is strict,
  so a bar that ends on the line is not a majority. The line applies to the electoral share only.
  The electoral-share hover gives the votes counted and the electors appointed, never the votes
  cast. The caption, in a year with popular-vote figures, is `labels.C1_BASES`,
  `labels.C1_MAJORITY_NOTE`, `labels.C1_LINE_EC_ONLY` and `labels.C1_ROW_ORDER`, then
  `labels.C1_NO_FIGURE_NOTE` only when a marker labeled `labels.C1_NO_FIGURE` is drawn; in a year
  without them, `labels.C1_EC_BASIS`, `labels.C1_MAJORITY_NOTE` and `labels.C1_NO_PV_CAPTION`.
  No caption sentence explains the other two markers: the label and hover of each say what it
  stands for. `components.chart` then appends `labels.CHART_TABLE_POINTER`. In a year without
  popular-vote figures, `NO_PV_SENTENCE` in `pages/election.py` still shows above T3.
- **Shown as:** the chart, placed by `pages/election.py` through `components.chart`; its wording
  in `labels.py`: the title `labels.C1_TITLE`, or `labels.C1_TITLE_NO_PV` in a year without
  popular-vote figures; the share axis `labels.C1_X_AXIS`; the series names
  `LABELS["ec_share_full"]` and `LABELS["pv_share"]`; the majority line's label
  `labels.C1_MAJORITY_LINE`; the marker labels `labels.C1_NO_FIGURE`, `labels.C1_NO_SHARE` and
  `labels.UNRECOGNIZED`; the hover text `labels.C1_EC_HOVER`, `labels.C1_PV_HOVER` and
  `labels.C1_NO_FIGURE_HOVER` (which writes `labels.NO_NATIONAL_FIGURE`; for a null or blank
  electoral share, `LABELS["ec_share_full"]`, a colon and `labels.NOT_IN_DATASET`; or
  `labels.UNRECOGNIZED` with `labels.UNRECOGNIZED_NOTE`); the caption sentences
  `labels.C1_BASES`, `labels.C1_EC_BASIS`, `labels.C1_MAJORITY_NOTE`, `labels.C1_LINE_EC_ONLY`,
  `labels.C1_ROW_ORDER`, `labels.C1_NO_FIGURE_NOTE` and `labels.C1_NO_PV_CAPTION`; then
  `labels.CHART_TABLE_POINTER`. The marker series' name, `labels.C1_NO_FIGURE_SERIES`, is never
  shown.
- **Source:** #433; `CHARTS` in `dashboard/explore/charts.py`; the two series:
  `NationalSummaryRow.ec_share_full` and `pv_share` in `src/usvote/api/models.py`, D041, D046 §4;
  the majority line: `ElectionSummary.ec_determinative`, D041; reader wording, the order of the
  page's sections (National results before Results by state), the row-order sentence, counted
  votes only in the hover, and the majority line's label: owner approval at #433's plan gate,
  2026-11-09; the marker for a null or blank electoral share, its label and its hover: owner
  approval with #466.
- **Not:** A stand-in for T3, which holds the numbers and the download. Not a chart of votes
  cast: the electoral share is votes counted out of electors appointed. Not the hybrid: no hybrid
  score is drawn. A marker is not a zero, and a bar of zero length never stands for a missing
  figure. The dashed line is not a fixed number of electoral votes such as 270: it is half of that
  year's electors appointed, and it does not apply to the popular-vote share.
- **Status:** settled

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
- **Shown as:** `LABELS["electoral_votes_counted"]`, `LABELS["national_electoral_votes_counted"]`;
  in C1, the hover line "Electoral votes counted" (`labels.C1_EC_HOVER`) and the caption sentences
  `labels.C1_BASES` and `labels.C1_EC_BASIS`. In C2, the hover line "Electoral votes counted"
  (`labels.C2_HOVER`), and the caption sentences `labels.C2_LEADER_POINT` and `labels.C1_EC_BASIS`.
- **Source:** `EcPvRow.electoral_votes_counted`; `count_status.COUNTED_VOTES_COLUMN`; D046;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "Then there is a third number".
- **Not:** *Electoral votes cast.*
- **Status:** settled

### Electors appointed and total popular vote over time (charts C4 and C5)
- **Plain:** Two charts on the Elections page with a row for each election in this dataset,
  oldest at the top. The first shows the electors appointed in each election and the second the
  total popular vote. With All states they show the national figures. With one state chosen they
  show that state's own figures, starting at its first election in this dataset. Where there is
  nothing to draw, a row shows a labeled marker, never a bar of zero length; a state that
  appointed no electors (its allotment was 0) is marked that way too. In the second chart, the
  shaded years are those before this dataset's popular-vote figures begin; shading does not mean
  no popular vote was held. One table on the page holds both charts' numbers. The state choice
  changes only these two charts and their table, and the list's year and popular-vote filters do
  not change them.
- **Precise:**
  - C4 and C5 are in `CHARTS` on `/elections`, ids `c4` and `c5`, sharing one companion table.
    The section follows T1's column-name list and comes before the footer, under
    `OVER_TIME_HEADING`.
  - All states: C4 reads the N1 `elections` items' `electoral_denominator`. C5 reads each year's
    one distinct `national_pv_denominator` across N1's `data` rows; two distinct values make the
    section unavailable.
  - One state: `state_electoral_votes`, `state_popular_total` and `pv_status` from
    `/v1/elections/states`, filled on first use (`on_miss`, D074(ii)). The dashboard adds nothing
    up.
  - `state` is a USPS code under the single-value rule, kept only if served; otherwise the view is
    All states. It switches the series rather than marking a second trace (D100, amending D093(a),
    D093(c) and D096(b)).
  - A bar is drawn where the cell is a figure and, in C4, above zero. A zero allotment is a marker
    (the D091 exception, D100). Every other value is a marker at zero, one series per cause, each
    with its own symbol. In C5 the band alone marks a `popular_vote` row outside the popular-vote
    window, which gets no marker; every other cause gets a labeled marker wherever it falls, inside
    the band included.
  - The band's bounds come from `meta.provenance.coverage`. Hover and bar text are the table's
    cells. A title or caption that would name a state that fails the plain-text check uses its
    "selected state" form.
  - If `/v1/elections/summary` cannot be read or is malformed, the section shows
    `OVER_TIME_UNAVAILABLE` only. If `/v1/elections/states` cannot be read or is malformed, the
    section keeps the all-states charts and their table, hides the state control and shows
    `OVER_TIME_NO_STATES` in its place; a `state` in the link stays in it but is not applied. T1,
    the chart of each election's Electoral College leader and the averages are unaffected either
    way.
- **Shown as:** `OVER_TIME_*`, `ALL_STATES` (the state control's placeholder), the table heading
  and the downloads "electors appointed and the total popular vote, all states"
  (`elections-electors-and-popular-vote-all-states.csv`) and "electors appointed and the total
  popular vote for this state" (`elections-electors-and-popular-vote-<usps>.csv`) in
  `pages/elections.py`; `C4_*`, `C5_*`, `FIRST_ELECTION_NOTE` and `FIRST_ELECTION_NOTE_SELECTED`, `NO_STATE_TOTAL` and `NO_NATIONAL_TOTAL` in `labels.py`; then
  `labels.CHART_TABLE_POINTER`.
- **Source:**
  - #436 ACs (owner, 2026-11-05);
  - decisions D091, D093, D096 and D100;
  - `ElectionSummary.electoral_denominator`, `NationalSummaryRow.national_pv_denominator` and
    `ElectionStateRow`;
  - posts 2026-08-18 (messy), 2026-08-25 (270 of what) and 2026-08-06 (222 votes away);
  - the ba spec for #436; the zero allotments and legislature-chosen years C4 and C5 mark are
    tabled with their citations in `docs/pv-coverage.md`.
- **Not:**
  - electoral votes cast or counted;
  - turnout;
  - a candidate's popular votes;
  - anything narrowed by the year or popular-vote filters;
  - "no popular vote", which the band is not;
  - a missing figure, which a C4 zero-allotment marker is not;
  - a zero, which a C5 marker is not.
- **Status:** settled

### Faithless vote (faithless elector)
- **Plain:** An elector's vote for someone other than the candidate the elector had pledged to
  support.
- **Precise:** The National Archives' term on its 2016 page ("Due to faithless voting, the
  electoral votes for Washington were: …"). This dataset records no pledges and has no field for
  one. In a nominating-party note, the word appears only where the note's own cited passage uses
  it. Other single-elector votes (1956 Jones, 1976 Reagan, 1988 Bentsen, 2004 Edwards) are
  described by what the elector did.
- **Shown as:** `HAWAII_2016_NOTE`, `TEXAS_2016_NOTE`, `WASHINGTON_2016_NOTE` in
  `src/usvote/party_catalog.py`, served as `nominating_party_note`; and, as a term, the
  `EcPvRow.nominating_party_note` and `NationalSummaryRow.nominating_party_note` field
  descriptions on the API's `/docs` page; and, as a term, the `EcPvRow.pv_status` field
  description and the `EcPvRow` description on the API's `/docs` page.
- **Source:** U.S. House of Representatives, Office of the Historian, "Faithless Electors" (blog,
  2020-11-17), https://history.house.gov/Blog/2020/November/11-17-Faithless-Electors/: "Many
  states use strict rules and the threat of fines to "bind" electors to the candidate to whom they
  pledged their vote. The Constitution does, however, allow electors to change their vote. When
  they do, they are known as "faithless electors."" Also ARCH-2016.
- **Not:** *Unpledged electors*, who had no pledge. Not an appointed elector who did not vote
  (*Appointed electors*). A note never applies the word to a vote its own cited passage does not
  call faithless.
- **Status:** settled

### Flip (another method picks a different winner)
- **Plain:** Whether the popular vote, or the hybrid, would have picked someone other than the
  Electoral College's winner (or, with no majority, its leader).
- **Precise:** `pv_flip` / `hybrid_flip`: true when that method's winner differs from `ec_winner`,
  false when it is the same person. Null where the method has no winner (outside the popular-vote
  window): null, never false, because a method with no winner neither agrees nor disagrees. The
  reader wording names the Electoral College side the same way `ec_winner` does.
- **Shown as:** `LABELS["pv_flip"]`, `LABELS["hybrid_flip"]`; the cell `labels.flip`, given
  `ec_determinative`, which fills `labels.FLIP_YES` with the Electoral College's role by the same
  test as `labels.ec_winner_label` (winner only on a true majority, otherwise leader).
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
  `LABELS["hybrid_flip"]`; help text `labels.HYBRID_NOTE` (panel, and under T3 and in its
  download's preamble).
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
  `labels.margin`; the panel note `labels.MARGIN_NOTE`, also shown under the averages on
  `/elections` (*Average margin*).
- **Source:** `ElectionSummary.ec_margin`, `pv_margin`, `hybrid_margin` and
  `_ELECTION_SUMMARY_EXAMPLE` in `src/usvote/api/models.py`; D037; help-text wording
  (`labels.MARGIN_NOTE`): approved by the owner in place on the #352 branch deploy, 2026-10-12.
- **Not:** A percent change. A gap measured from the Electoral College's winner or leader. An
  average over several elections (*Average margin*).
- **Status:** settled

### Nominating party
- **Plain:** The party that nominated the candidate for President in that election. A candidate
  nominated by two parties at once has one value that names both. Having no party's nomination is an
  answer too: no party nominated them for President that year, or the nomination was withdrawn
  before the electors voted.
- **Precise:** `nominating_party`, one code per (year, candidate) from the closed vocabulary
  `PARTY_COMPONENTS` in `src/usvote/party.py`, repeated on each of the candidate's state rows and
  carried to the national row. A joint nomination is one atomic code that declares its components
  (`liberal_republican_democratic`, `democratic_populist`, `american_whig`). For 1824 candidates
  outside the caucus, 1828, and the 1836 Whigs, where no national body nominated, the code is the
  party the source of record names (D077 rule 2). A national party's endorsement is treated as its
  nomination (rule 3), and so is a U.S. Government source's statement that the person was the
  party's candidate or nominee, or that a body of the party supported or nominated them (rule 8); a
  value resting on either carries a note saying so (*Nominating-party note*). `no_nomination` is a
  served value (rules 5 and 7). Null has one cause: the dataset has no row for that candidate-year.
  `nominating_party_source` says where each value comes from: `NARA`, the party the National
  Archives prints for the election's winner and main opponent (a value that a U.S. Government
  publication amends, such as 1872 Greeley's, keeps `NARA`), or `USGOV`, a curated row citing U.S.
  Government publications; null exactly where the value is. For a `no_nomination` row, its citations
  record how the candidate received electoral votes, and none states the value itself (D079). A code
  never changes meaning: a new value or component is a new code (D077).
- **Shown as:** on the API's `/docs` page, the `EcPvRow.nominating_party`,
  `EcPvRow.nominating_party_source`, `NationalSummaryRow.nominating_party` and
  `NationalSummaryRow.nominating_party_source` field descriptions in `src/usvote/api/models.py`.
  On the dashboard as *Party*: `LABELS["nominating_party"]`, `labels.NOMINATING_PARTY`,
  `labels.NO_NOMINATION`. In each T2–T5 download, `nominating_party` and
  `nominating_party_source` as served.
- **Source:** D077; `PARTY_COMPONENTS`, `NO_NOMINATION`, `TABLE1_PARTY_CORRECTIONS` and
  `PARTY_SOURCES` in `src/usvote/party.py`; `CURATED_PARTY_ROWS` in
  `src/usvote/party_catalog.py` (the curated values, their rule sets and citations), the C2 rows
  (#388, D079);
  `.claude/specs/research-candidate-party-source.md` §1, §2.2, §2.3, §7 (the evidence record,
  not an authority);
  `posts/2026-08-25-it-takes-270-but-270-of-what.md` (Greeley, "the Democratic and Liberal
  Republican nominee": a joint nomination in reader prose).
- **Not:** *Popular-vote source's party*: a separate field, from 1976 on, never the basis of this
  one. Not a ballot line or a state party's label. `no_nomination` is not "no party"
  and not a missing value, and for a withdrawn nomination it does not say the person was never
  nominated. A null is not `no_nomination`.
- **Status:** settled

### Nominating-party note
- **Plain:** A short sentence or two of fact about a candidate's nominating party. Where a party
  nominated the candidate, it says how that came to be: for example, a joint nomination, an
  endorsement treated as a nomination, a nominee who died before the electors met, or sources that
  say which party the candidate ran for without naming the body that nominated them. Where no
  party nominated the candidate, it says how they came to receive electoral votes for President,
  for example a faithless elector's vote. A row may have none; in this dataset, every candidate
  recorded as without a party's nomination has one.
- **Precise:** `nominating_party_note`, nullable text, constant per (year, candidate). It states
  only facts its row's own citations support and adds no source. It is required where the value
  rests on rule 3, 5 or 8, and on every curated `no_nomination` row. There it says how the
  candidate's electoral votes arose and does not repeat what `no_nomination` means (D079). It is
  allowed for any other exceptional case. Null means no note was recorded: not that the value is
  missing, and not that the value is plain. Table 1 notes ship from `TABLE1_ROW_NOTES` in
  `src/usvote/party.py`; curated notes ship from `CURATED_PARTY_ROWS` in
  `src/usvote/party_catalog.py` (#387, #388). A rule-8 row with nothing else to explain carries
  the shared `RULE_8_NOTE`. The 1836 Whig rows share `WHIG_1836_NOTE`. The 2016 Texas and
  Washington recipients share their state's note (`TEXAS_2016_NOTE`, `WASHINGTON_2016_NOTE`). A
  row with more to explain has a note of its own. The text is a data value, served as stored.
- **Shown as:** on the API's `/docs` page, the `EcPvRow.nominating_party_note` and
  `NationalSummaryRow.nominating_party_note` field descriptions in `src/usvote/api/models.py`. On
  the dashboard: the party cell's help text where a row has a note (on a `no_nomination` row, after
  `labels.NO_NOMINATION_NOTE`), and once per candidate and election in the Party notes list under
  T2–T5 (`labels.PARTY_NOTES_HEADING`, `labels.PARTY_NOTE_ITEM`), shown as served;
  `LABELS["nominating_party_note"]` in their column-name lists; `nominating_party_note` in their
  downloads.
- **Source:** D077, "The row note"; D079 (the `no_nomination` notes); research doc §2.4, §16;
  `TABLE1_ROW_NOTES` (wording approved by the owner, 2026-10-18, #385 plan); `CURATED_PARTY_ROWS`
  (wording approved by the owner, 2026-10-20, #387 plan; the #388 notes, approved by the owner,
  2026-10-21, #388 plan).
- **Not:** the value's null (*Nominating party*). Not a citation. Not the count-status reason,
  which is the National Archives' own sentence about the count (*Count status*). On a
  `no_nomination` row, not the reason no party nominated the candidate: it says how the votes
  arose.
- **Status:** settled

### No average (no election shown has that margin)
- **Plain:** The page shows no average because none of the elections shown has that margin in this
  dataset: no election matches the filters, or, for the popular vote, every election shown is from
  years this dataset has no popular-vote figures for. It is not zero.
- **Precise:** `labels.metric_mean` of an average with no contributing election and no unrecognized
  value. Its cause is checked in order: no row shown (`labels.METRIC_NO_AVERAGE_FILTERS`); for the
  popular-vote average, no year shown inside the popular-vote window of `meta.provenance.coverage`
  (`labels.METRIC_NO_AVERAGE_PV_YEARS`, which names `pv_year_min`–`pv_year_max`); otherwise every
  margin among the years shown is null (`labels.METRIC_NO_AVERAGE_NULL`; no served year reaches it).
  Never 0, "nan" or an empty cell.
- **Shown as:** `labels.METRIC_NO_AVERAGE_FILTERS`, `labels.METRIC_NO_AVERAGE_PV_YEARS`,
  `labels.METRIC_NO_AVERAGE_NULL`, through `labels.metric_mean`.
- **Source:** #437 acceptance criteria ("An empty selection shows 'no figure', never zero or NaN");
  D097; reader wording: `ba` spec for #437, approved at its plan gate.
- **Not:** Zero, or a margin of zero. *Not in this dataset* for one value. *No popular-vote figure in
  this dataset*, a candidate's missing popular-vote count. *Unrecognized value*. The "no figure" of
  D097's rule for a sum, whose reader wording a later spec sets.
- **Status:** settled

### No popular-vote figure in this dataset (inside the window)
- **Plain:** A state held a popular vote in a year this dataset covers, but the dataset has no
  figure for this candidate there, or, for a total, no total for that state or election.
- **Precise:** A null `popular_votes` (or `national_pv_votes`) on a row whose `pv_status` is
  `popular_vote`, in a year inside the popular-vote window. Typically a candidate the popular-vote
  source does not cover, such as an unpledged slate or a faithless elector's choice. No status
  narrows it further (D005).
- **Shown as:** `labels.NO_FIGURE` (T2, T4); `labels.NO_NATIONAL_FIGURE` (T3, and the hover text
  of C1's marker, `labels.C1_NO_FIGURE_HOVER`); in C1, the label of the marker drawn in place of a
  popular-vote bar, `labels.C1_NO_FIGURE`, and the caption sentence `labels.C1_NO_FIGURE_NOTE`,
  shown only when such a marker is drawn; `labels.NO_STATE_TOTAL`, `labels.NO_NATIONAL_TOTAL`
  and `labels.C5_NO_TOTAL` (the C4/C5 table and C5).
- **Source:** `EcPvRow` docstring and `pv_status` description; `NationalSummaryRow` docstring;
  `.claude/specs/backlog-dashboard.md`, E9-S3 null table;
  `posts/2026-08-18-presidential-elections-are-messy.md`, "One empty cell, five different
  histories" (a number the record does not carry is not a zero).
- **Not:** Zero popular votes.
- **Status:** settled

### Not in this dataset (a value with no cause given)
- **Plain:** This dataset has no value here. It says nothing about why, or about what happened at
  the time.
- **Precise:** The cell for a null or blank value that the row does not explain. It is
  also the cell for `has_popular_vote: false` and for a null or blank nominating party (*Party*),
  whose one cause is that this dataset records no party for that candidate in that election
  (`labels.PARTY_NULL_NOTE`); it is not *without a nomination*. Both are about what the dataset
  holds. In a CSV download the same thing is an empty cell (`export.NULL_LINE`). A
  cause, where one is known, follows it after a colon (*Outside the popular-vote window*).
- **Shown as:** `labels.NOT_IN_DATASET`, reached through `labels.has_popular_vote`, `labels.yes_no`,
  `labels.number`, `labels.share` (so `labels.share_cell`), `labels.census_year`,
  `labels.pv_status`, `labels.count_status`, `labels.popular_votes`, `labels.nominating_party` (with
  `labels.PARTY_NULL_NOTE` through `labels.nominating_party_cell`), `labels.party_notes` (the Party
  notes list's candidate name), `labels._closed_value`, `labels._null` (so `labels.winner`,
  `labels.flip`, `labels.margin`), `labels.ec_majority`, `labels._null_per_capita` (so
  `labels.population`), `labels.persons_per_electoral_vote`. In C1, a null or blank electoral share
  draws a marker labeled `labels.C1_NO_SHARE`, and its hover (`labels.C1_NO_FIGURE_HOVER`) writes
  `labels.NOT_IN_DATASET` after `LABELS["ec_share_full"]` and a colon, as T3 shows that cell under
  its header. In C3, the short label of a marker drawn in place of a bar (through
  `labels.C3_MARKER_LABELS`), and, in `labels.C3_NO_FIGURE_HOVER`, the full cell (for
  `UNRECOGNIZED`, with `labels.UNRECOGNIZED_NOTE`). In `labels.C3_BAR_HOVER`, each of the row's
  other T6 cells (population, electors appointed, census used, borders used) as T6 shows it; for the
  borders cell the caption adds `labels.C3_PLAIN_MIXED`. In C4,
  `labels.NOT_IN_DATASET` labels the marker drawn in place of a bar for a null allotment, in the
  series `labels.C4_NO_FIGURE_SERIES` (never shown), with `labels.C4_NO_FIGURE_NOTE` in the
  caption; its hover (`labels.C4_HOVER` or `labels.C4_STATE_HOVER`) writes the same cell.
- **Source:** the comments on `NOT_IN_DATASET` and `_closed_value` in `labels.py`;
  `dashboard/CLAUDE.md`, `components.py`, `labels.py` (the "never No" rule);
  `.claude/specs/backlog-dashboard.md`, "Carry-forward constraints"; #348 acceptance criteria.
- **Not:** "No", which is a recorded negative. Zero. "Not held". *Unrecognized value*, where the
  dataset does hold something.
- **Status:** settled; wording pending (#375: whether the CSV preamble's last line,
  `export.NULL_LINE`, keeps the word "null")

### Not-found state (a link the dataset does not serve)
- **Plain:** What a page says when its link names a year, a state code or a candidate link this
  dataset does not serve, or, on an election's pages, a section the site does not have. Its heading
  and the browser tab say that the election, state or
  candidate was not found, and so does a shared link's preview once the site has checked the
  link; before that, the preview names no year, state or candidate.
- **Precise:** Rendered when a page's `validate` judge refuses its path value (D073, D074). It
  never repeats the value and fills nothing built from it. Candidate links match exactly, so a
  listed slug in another letter case is refused too. "Not found" is about the link: it never
  claims that the dataset lacks the election, state or candidate, or that it did not happen. The
  page shows its not-found heading, its sentence and its link, and no lede. Once the judge's source
  is in the dashboard's memory, the index answers 404 with `noindex`, and the title (the browser
  tab, `og:title` and `twitter:title`) is the not-found heading followed by the site title; before
  then, the index answers 200 and the title is the page's generic one, which names no year or code
  (#325). Its link-preview description is the page's not-found sentence:
  `labels.ELECTION_NOT_FOUND_SENTENCE` on the three election pages, and `NOT_FOUND_SENTENCE` in
  `pages/state.py` and `pages/candidate.py`. A percent-encoded link
  is read as the link it spells once decoded, as Dash's router reads it, so it gets whatever that
  link gets: `/election%2F1825` gets this state, with the same status and title, just as
  `/election/1825` does. `/election/18%32%34` is not a not-found link at all: it opens 1824, with
  `/election/1824` as its canonical link (D089). On the election pages, the overview and both
  subpages (`/election/1825/states`) share one heading and sentence, and so does a link naming a
  section the site does not have (`/election/1824/x`), which reaches the overview: the sentence is
  about the link, so it holds whether the year or the section is what the site does not have.
- **Shown as:** `labels.ELECTION_NOT_FOUND_HEADING` and `labels.ELECTION_NOT_FOUND_SENTENCE` for
  the three election pages, and `NOT_FOUND_HEADING` and `NOT_FOUND_SENTENCE` in `pages/state.py`
  and `pages/candidate.py`; the links "Browse every election in the dataset"
  (`labels.ELECTION_NOT_FOUND_LINK`, built by `election_view.not_found`), "Browse every state in the dataset" (`not_found` in
  `pages/state.py`) and `NOT_FOUND_LINK` in `pages/candidate.py`; the title on a not-found link,
  built in `dashboard/explore/app.py` from the heading and `config.SITE_TITLE`.
- **Source:** D073; D074; D083; D089 (a percent-encoded link is matched after decoding);
  `dashboard/CLAUDE.md`, `pages/`; the heading and title: #325;
  their reader wording: owner decision, 2026-11-01, #325.
- **Not:** *Degraded state*; *Page not found*, a link that matches no page at all; an empty filter
  result (`components.NO_ROWS`).
- **Status:** settled

### Outside the popular-vote window
- **Plain:** The dataset has no popular-vote figures for this year, so nothing computed from them
  can be shown.
- **Precise:** A null popular-vote or hybrid field in a year outside the popular-vote window of
  `meta.provenance.coverage` (`labels.in_pv_window` is false, or, in T3, the year's
  `has_popular_vote` is false). It names its cause, and one wording serves the panel and T3's
  popular-vote columns and hybrid score (`national_pv_votes`, `pv_share`, `hybrid_score`;
  owner decision, 2026-10-12, #352). A null party has nothing to do with the window: in any year
  it reads *Not in this dataset* with `labels.PARTY_NULL_NOTE`. T2 and T4 name the window's side
  (`labels.BEFORE_WINDOW`, `labels.AFTER_WINDOW`).
- **Shown as:** `labels.NOT_APPLICABLE` (panel; T3 through `_national_pv` in
  `pages/election.py`); `NO_PV_SENTENCE` in `pages/election.py` above T3; in C1, where no
  popular-vote bar is drawn, the title `labels.C1_TITLE_NO_PV` and the caption sentence
  `labels.C1_NO_PV_CAPTION`; `labels.NOT_APPLICABLE` as the national total's cell outside the
  window (the C4/C5 table); C5's band, `labels.C5_BEFORE_BAND`, `labels.C5_AFTER_BAND`,
  `labels.C5_BEFORE_NOTE` and `labels.C5_AFTER_NOTE`.
- **Source:** `ElectionSummary` docstring; `labels.in_pv_window`; `.claude/specs/backlog-dashboard.md`,
  E9-S3, "Election panel"; wording: owner decision, 2026-10-10, #348.
- **Not:** "No" (a false flip). A null inside the window, which names no cause.
- **Status:** settled

### Page not found (a link that matches no page)
- **Plain:** What the site says when a link leads to no page on it at all.
- **Precise:** `pages/not_found_404.py`, Dash's custom-404 page, rendered for a path that matches
  no page once its percent-escapes are decoded, as Dash's router reads it. A percent-encoded link
  gets the same page as the link it spells: `/election%2F1825` gets the election page's
  *Not-found state*, as `/election/1825` does (D089). The index answers 404
  with `noindex`, and the title (the browser tab, `og:title` and `twitter:title`) is its heading
  followed by the site title. It reads no data, so it has no degraded state.
- **Shown as:** `NOT_FOUND_HEADING`, `NOT_FOUND_SENTENCE` and `NOT_FOUND_LINK` in
  `pages/not_found_404.py`.
- **Source:** #325; D083; D089; `resolve` in `dashboard/explore/app.py` (Dash's `not_found_404`
  convention); reader wording: owner decision, 2026-11-01, #325.
- **Not:** *Not-found state*, where the link names a kind of page (an election, a state, a
  candidate) but a value this dataset does not serve; *Degraded state*. A request for a file the
  site does not serve (for example a script under `/_dash-component-suites/`, #430), which answers
  the web server's default 404 with no text of ours and no page. A link whose decoded path holds
  a line break (`%0A`), which the web server answers with its own default 404 before the site
  loads, with no text of ours (D089).
- **Status:** settled

### Party
- **Plain:** The party a candidate ran for in that election: the party that nominated them for
  President. A candidate nominated by two parties at once shows both, joined by "and". A candidate
  without a party's nomination for President when the electors voted is shown as such. Where this
  dataset records no party, the cell reads *Not in this dataset*.
- **Precise:** The dashboard's word for the nominating party (*Nominating party* defines the value).
  One value per candidate per election, the same on each of the candidate's rows (owner ruling,
  2026-10-16). The popular-vote source's party is shown on no page and in no download. Each code
  reads its display form from the closed table `labels.NOMINATING_PARTY`: a single party by its
  name, written as the name is written (Democratic-Republican, Anti-Masonic, States' Rights
  Democratic); the American party as "American (Know-Nothing)", its full name in its source of
  record; the two Progressive codes by year; a joint nomination as its components' names in code
  order, joined by "and", never a hyphen, which would read as one party's name. `no_nomination`
  reads `labels.NO_NOMINATION`. A null or blank reads *Not in this dataset*. Any other value,
  including a code outside the table, reads *Unrecognized value*. A download keeps
  `nominating_party`, `nominating_party_source` and `nominating_party_note` as served.
- **Shown as:** `LABELS["nominating_party"]`; the cell `labels.nominating_party_cell`, through
  `labels.nominating_party` (`labels.NOMINATING_PARTY`); `labels.NO_NOMINATION`, with
  `labels.NO_NOMINATION_NOTE` as its help text; `labels.PARTY_NOTE` and `labels.PARTY_NULL_NOTE`
  under T2, T3, T4 and T5 and in their downloads' preambles, and `labels.PARTY_NULL_NOTE` as a null
  cell's help text; the row note: see *Nominating-party note*.
- **Source:** D077 ("From #389 on, wherever the dashboard shows a party, it shows this one, in every
  year"); research doc §2.1, §2.2, §9 (owner Q4); one party per candidate-year: owner ruling,
  2026-10-16; label, display forms and notes: owner approval at #389's plan gate, 2026-10-19;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md` (the Democratic name; Greeley "the Democratic
  and Liberal Republican nominee").
- **Not:** *Popular-vote source's party* (`party` on the API). Not a ballot line or a state party's
  label. Being without a nomination is not "no party" and not a missing value. *Not in this dataset*
  is not "without a nomination".
- **Status:** settled

### People per electoral vote
- **Plain:** How many residents each of a state's electoral votes stood for at that election.
- **Precise:** `persons_per_electoral_vote` = `population` ÷ `state_electoral_votes` (appointed),
  shown to a whole person. Null where the population is null (no census figure) or the allotment
  is 0 (votes withheld: eleven states in 1864, three in 1868). Never 0 and never infinite: a figure of 0 or less, or one that is not finite, reads *Unrecognized value*, since no state's population divided by its electors appointed can be one. Where a
  row carries both causes, the missing census figure is the one shown.
- **Shown as:** `LABELS["persons_per_electoral_vote"]`; `labels.persons_per_electoral_vote`;
  `labels.NO_ELECTORAL_VOTES`; the heading of T7 (`pages/state.py`); the per-capita page's
  `PER_CAPITA_HEADING` and `PER_CAPITA_GENERIC_HEADING` (`pages/election_per_capita.py`); the
  section link `labels.SECTION_PER_CAPITA`. In C3 (*People per electoral vote chart (C3)*), the
  titles `labels.C3_TITLE` and `labels.C3_TITLE_NO_CENSUS`, the axis title
  (`LABELS["persons_per_electoral_vote"]`), each bar's text (T6's cell), the hover text
  `labels.C3_BAR_HOVER` and `labels.C3_NO_FIGURE_HOVER`, the marker label
  `labels.C3_NO_ELECTORAL_VOTES` with `labels.NO_ELECTORAL_VOTES` in its hover, and the caption
  sentences `labels.C3_RATIO` and `labels.C3_NO_FIGURE_NOTE`.
- **Source:** `PerCapitaRow`; `ElectionStateRow` (the same field, on `/v1/elections/states`);
  D064(c), (d); D069. `posts/2026-09-03-how-did-we-get-to-538-electors.md`
  names the same measure "persons per electoral vote"; readers see "people" (owner decision, 2026-10-11, #348).
  The field name `persons_per_electoral_vote` stays where field names are allowed.
- **Not:** People per elector who voted. Zero.
- **Status:** settled

### People per electoral vote chart (C3)
- **Plain:** A chart on an election's People per electoral vote page, with a bar for each state
  and DC: how many people each of the state's electoral votes stood for in that election. The bars
  run from the most people per electoral vote to the fewest, and each is labeled with its number,
  written as the table on the same page writes it. The title names the census used. Striped bars
  use present-day borders. Where there is no figure to draw for a state, its row shows a marker
  with a short label saying why, never a bar of zero length, and those rows come last. When the
  page is narrowed to one state, the chart marks that state at the start of its row and still
  shows every state.
- **Precise:** Chart ID C3 in `CHARTS` (`dashboard/explore/charts.py`), on
  `/election/<year>/per-capita`, with T6 as its *Companion table* (`election-per-capita`,
  `PER_CAPITA_TABLE_ID` in `pages/election_per_capita.py`); its element id is `c3`. It sits after
  the section links and before the state control. It is built from every T6 row, never narrowed
  by the page's `state` filter (D093), and every number and label it shows is T6's cell string
  (`labels.per_capita_strings`). A bar is drawn only where `labels.finite` accepts
  `persons_per_electoral_vote` and T6's cell is that figure. Drawn bars are ordered by the ratio,
  most first, ties by state name. Every other row follows in T6's order (by state name), with a
  marker at zero on the axis whose label is looked up by T6's cell in `labels.C3_MARKER_LABELS`
  (`labels.C3_NO_CENSUS_FIGURE` for 1848 Texas, `labels.C3_NO_ELECTORAL_VOTES` for a zero
  allotment: eleven states in 1864, three in 1868; `labels.NOT_IN_DATASET`; or
  `labels.UNRECOGNIZED` for any other cell), with T6's cell in full in its hover; never a
  zero-length bar and never an infinity. The bars are two series split on T6's border cell,
  sharing one row slot: striped exactly where the cell is `BOUNDARY_BASIS["present_day"]`, plain
  for every other row. The stripes mean present-day borders in every year. The legend has an entry for each bar series drawn and, when a state is selected, one for its mark (`labels.C3_SELECTED`); the marker series has none (its name, `labels.C3_NO_FIGURE_SERIES`, is never shown). The plain series is named `BOUNDARY_BASIS["at_election"]` when every
  plain row is at the election, and `labels.C3_PLAIN_SERIES` otherwise, and in that case the
  caption adds `labels.C3_PLAIN_MIXED`. The selected state (the page's filter, once T6's rows name
  it) is marked by one diamond, filled with the page color (`--page`) and ringed in the text color (`--text`), at zero in its row (the start of the row), in a series of its own named
  `labels.C3_SELECTED`, with no hover of its own; its row label is unchanged. The title names
  `governing_census_year` only when every row's census-year cell is the same year (2024 reads
  2020; 1924 and 1928 read 1910). The axis's tick labels are hidden, because every bar and marker
  carries its own label. No average line: the API serves none.
- **Shown as:** the chart, placed by `pages/election_per_capita.py` through `components.chart`;
  its wording in `labels.py`: the title `labels.C3_TITLE`, or `labels.C3_TITLE_NO_CENSUS`; the
  axis `labels.C3_X_AXIS` (`LABELS["persons_per_electoral_vote"]`); the series names
  `labels.BOUNDARY_BASIS` values and `labels.C3_SELECTED`; the hidden name
  `labels.C3_NO_FIGURE_SERIES`; the plain series' legend name `labels.C3_PLAIN_SERIES` where it
  applies; marker labels `labels.C3_MARKER_LABELS`; the hover text `labels.C3_BAR_HOVER` and
  `labels.C3_NO_FIGURE_HOVER`; the caption sentences `labels.C3_RATIO`, `labels.C3_CENSUS` or
  `labels.C3_CENSUS_MIXED`, then `labels.C3_STRIPES` followed by `labels.BOUNDARY_NOTE`,
  `labels.C3_ALL_AT_ELECTION`, `labels.C3_PLAIN_MIXED`, then `labels.C3_NO_FIGURE_NOTE` only when
  a marker is drawn, then `labels.C3_SELECTED_NOTE` only when a state is selected; then
  `labels.CHART_TABLE_POINTER`.
- **Source:** #435 (acceptance criteria, amended 2026-11-10 at #465's plan gate); `CHARTS` in
  `dashboard/explore/charts.py`; `PerCapitaRow` in `src/usvote/api/models.py`; D064(c), (d);
  D066; D069; D091 (the C1 pattern it follows); D093; reader wording: `ba` spec for #435,
  approved by the owner at its plan gate (2026-11-10).
- **Not:** A stand-in for T6, which holds the numbers and the download. Not a chart of electoral
  votes cast: the base is the electors appointed. A marker is not a zero. Not narrowed by the
  page's filter. Not an average; no national figure is drawn.
- **Status:** settled

### Popular vote held in this state (`pv_status`)
- **Plain:** Whether the state held a popular vote for president that year: a popular vote was
  held; the state legislature chose the electors instead; or the state took no part in the
  election.
- **Precise:** `pv_status`, one of exactly three values per `(year, state)`: `popular_vote`,
  `legislature_chosen`, `not_participating`. Never null, and there is no "unknown". It is a fact
  about the election, not about the dataset: a `popular_vote` row can still lack a figure. The
  public values come from the in-repo absence catalog (D048 §3). On `/v1/elections/states` it is
  served once per `(year, state)`; on the candidate rows it repeats on each of the state's rows.
- **Shown as:** `LABELS["pv_status"]`; values `labels.PV_STATUS` (cell and filter);
  `labels.LEGISLATURE_CHOSE` and `labels.TOOK_NO_PART` in the popular-vote cell. The filter is
  named "popular-vote status" by the states page's `FILTER_SENTENCE`
  (`pages/election_states.py`); on the API's `/docs` page, the `EcPvRow.pv_status` and
  `ElectionStateRow.pv_status` field descriptions in `src/usvote/api/models.py`; the C4/C5
  table's column, with one state chosen; the hover line in `labels.C4_STATE_HOVER` and
  `labels.C5_STATE_HOVER`; `labels.C5_LEGISLATURE`, `labels.C5_TOOK_NO_PART` and
  `labels.C4_NO_ELECTORS_TOOK_NO_PART`.
- **Source:** `src/usvote/pv/status.py`, `PV_STATUS_VALUES` and its comment; `EcPvRow.pv_status`;
  D024 §4; D048 §2–3; `posts/2026-08-18-presidential-elections-are-messy.md`, "How the record
  keeps them apart" (the three values as readers see them: held, the legislature chose the
  electors, took no part); `posts/2026-08-06-222-votes-away.md` (a status saying whether a popular
  vote was held there at all); `ElectionStateRow.pv_status`; #428.
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
  with `LEGISLATURE_CHOSE`, `TOOK_NO_PART`, `BEFORE_WINDOW`, `AFTER_WINDOW`, `NO_FIGURE`; in C1,
  the hover line "Popular votes" (`labels.C1_PV_HOVER`).
- **Source:** `EcPvRow.popular_votes`; `NationalSummaryRow.national_pv_votes`; D024; D048 §2;
  `.claude/specs/backlog-dashboard.md`, E9-S3 null table.
- **Not:** Zero. *Total popular vote (nation)* and *State's total popular vote*, which include
  every candidate.
- **Status:** settled

### Popular-vote share
- **Plain:** A candidate's share of all votes cast for president nationally.
- **Precise:** `pv_share` = national popular votes ÷ total votes cast nationally. Null outside the
  popular-vote window.
- **Shown as:** `LABELS["pv_share"]` (T3, and the name of C1's popular-vote series); in C1, the
  title `labels.C1_TITLE`, the hover text `labels.C1_PV_HOVER`, and the caption sentences
  `labels.C1_BASES` and `labels.C1_ROW_ORDER`; each popular-vote bar's text is T3's cell for the
  same value.
- **Source:** `NationalSummaryRow.pv_share`.
- **Not:** *Electoral share*.
- **Status:** settled

### Popular-vote source's party (`party` on the API)
- **Plain:** The party the popular-vote source records for a candidate's votes in a state, from 1976
  on. The API serves it; the dashboard does not show it.
- **Precise:** `party` on `/v1` rows, in the source's own code (`DEMOCRAT`, `REPUBLICAN`;
  `EC_GETTER_PARTIES` in `src/usvote/mit/transform.py` limits the public codes, D019). Null outside
  the popular-vote window and wherever that source has no figure for the candidate. A build-time
  check on the nominating party, never its source (D077 amends D018). Not on any dashboard page or
  download since #389.
- **Shown as:** on the API's `/docs` page, the `EcPvRow.party` and `NationalSummaryRow.party` field
  descriptions in `src/usvote/api/models.py`.
- **Source:** `EcPvRow.party`, `NationalSummaryRow.party`; D018; D019; D024 §5; D077; research doc
  §9, §12.
- **Not:** *Party*, the dashboard's word, which is the nominating party. Not a second party record.
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
- **Shown as:** `LABELS["population"]`; `labels.population`. In C3, the hover line "Population"
  (`labels.C3_BAR_HOVER`) and the caption sentences `labels.C3_RATIO` and `labels.C3_CENSUS`.
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

### Site name (this site)
- **Plain:** The name of this website, where these tables are: "Explore — US Presidential
  Election Center", shortened to "Explore" on a narrow screen. "This site" means these pages
  only.
- **Precise:** The pages served at `config.CANONICAL_HOST` (D071(c)). The full form is
  `config.SITE_TITLE`'s text; the short form is its first word, so the visible short name is
  the start of the site-name link's accessible name, which is the full form at every width
  (WCAG 2.5.3). The API's `/docs` page, at `config.API_HOST`, is not on this site. The home
  page's heading, "US Presidential Election Center", is the full form without "Explore —".
- **Shown as:** the browser tab and link previews (`config.SITE_TITLE`), as the title of `/`
  (`pages/home.py`) and after the heading on a not-found link (`api.NotFound.title`, in
  `dashboard/explore/api.py`); the site navigation's link to `/` (`labels.SITE_NAME_SHORT`,
  always shown, and `labels.SITE_NAME_REST`, shown from 45rem up and visually hidden below);
  "this site" in `NOT_FOUND_SENTENCE` in `pages/not_found_404.py`; the home page's heading
  (`labels.HOME_HEADING`, in `layout` in `pages/home.py`).
- **Source:** `config.SITE_TITLE`; `config.CANONICAL_HOST`; D071(c); the short form and the
  link's accessible name: #448; reader wording: owner decision at #448's plan gate, 2026-11-06
  ("Explore" for now; the owner may switch the short form to "Home" once it is seen on the
  built page).
- **Not:** The *Dataset*. The API, which serves the dataset from its own address.
  "Dashboard", the project's own word for these pages, which no reader-facing string in
  `dashboard/explore/` uses.
- **Status:** settled

### Site navigation (the bar at the top of every page)
- **Plain:** The row of links at the top of every page: the site's name, which goes to the home
  page, then links to the list of elections, the list of states and the API's documentation
  page. The theme toggle sits at the end of the same row. The link for the part of the site the
  reader is in is marked.
- **Precise:** A `nav` landmark named `labels.SITE_NAV_LABEL`, inside the site header and
  before `Main`, on every page, including every not-found state, the degraded state and the
  custom 404 page; the theme toggle follows it in the header, outside the landmark (D086). It
  reads no data. The site-name link carries `aria-current="page"` on `/`, as Elections does on
  `/elections` and States on `/states`. Elections carries `aria-current="true"` on
  `/election/<year>`, `/election/<year>/states` and `/election/<year>/per-capita`, and States on
  `/state/<usps>`, matched by route, so a link the dataset does
  not serve marks its section too: the mark names the section, not the page being read. Nothing
  is marked on `/candidate/<slug>` or the custom 404 page. Elections, States and the site name
  navigate client-side. API docs is an ordinary same-tab link to the API's `/docs` page, which
  is not on this site (*Site name*).
- **Shown as:** `labels.SITE_NAV_LABEL` (read by assistive technology, not shown);
  `labels.SITE_NAME_SHORT` and `labels.SITE_NAME_REST`; `labels.NAV_ELECTIONS`,
  `labels.NAV_STATES`, `labels.NAV_API_DOCS`; the API docs link's tooltip,
  `labels.NAV_API_DOCS_TITLE`; then, in the header, the theme toggle (*Theme choice*). Built by
  `components.site_nav`, placed in `app.layout` (`dashboard/explore/app.py`).
- **Source:** #448 (owner decisions fixed in the issue and the owner's comment, 2026-11-06);
  D086; reader wording: owner decision at #448's plan gate, 2026-11-06.
- **Not:** The earlier and later links on the election pages and their landmarks
  (`labels.ELECTION_NAV_LABEL`, `labels.ELECTION_NAV_SECTION_LABEL`; *Election year*), and the
  links between an election's three pages (`labels.ELECTION_SECTIONS_LABEL`; *Election pages*). The in-body "Browse…" links on the home page and the
  not-found states, which stay. A menu: the bar has at most four entries at the right, the
  toggle counted, and never collapses.
- **Status:** settled

### Sources
- **Plain:** Where each kind of figure comes from (electoral votes, popular votes, population,
  parties): the organization that publishes it, and the license it is published under.
- **Precise:** Electoral votes: `ec_source_name`, `ec_license`. Popular votes: `source_name`,
  `license`. Population: `census_source_name`, `census_license`. Rendered from `meta.provenance`,
  never written in by hand. Nominating parties: per row, `nominating_party_source`; `NARA` values
  share the electoral-vote pair, and `USGOV` values use `usgov_source_name` and `usgov_license`. On
  the dashboard, a table carrying the party credits the U.S. Government publications source in its
  download's preamble, and the footer always lists it, both labeled by what it supplies (parties the
  National Archives does not print). Parties the National Archives prints share the electoral-vote
  line.
- **Shown as:** `components.provenance_footer`; `export.preamble`; `export.EC_SOURCE`, `PV_SOURCE`,
  `CENSUS_SOURCE`, `USGOV_SOURCE` (the footer's fourth line, `components.SOURCES`); on the API's
  `/docs` page, the `Provenance.ec_source`, `Provenance.ec_license`, `Provenance.usgov_source`,
  `Provenance.usgov_source_name` and `Provenance.usgov_license` field descriptions in
  `src/usvote/api/models.py`, the note built by `redistributable_note()` in the API description's
  "Data provenance & licensing." paragraph (`_DESCRIPTION_TEMPLATE`, filled by
  `_render_description`, in `src/usvote/api/app.py`), and `redistributable_note` and
  `usgov_source_name` in the `Provenance` response example (`_PROVENANCE_EXAMPLE` in `models.py`,
  also the example inside `Meta` and `SnapshotMetaResponse`); in the body of every successful `/v1`
  data response, under `meta.provenance`, and of `/v1/meta`, under `provenance`:
  `redistributable_note` (built by `redistributable_note()`) and `usgov_source_name` (the `USGOV`
  entry of `_SOURCES`, which the note also names), both in `src/usvote/api/provenance.py`.
- **Source:** `Provenance` in `src/usvote/api/models.py`; D030; D048 §6; D069(f); #275,
  carry-forward constraints; D077, Provenance.
- **Not:** —
- **Status:** settled

### State
- **Plain:** One of the 50 states, or the District of Columbia.
- **Precise:** The full state name, the canonical display key; `state_usps` is the two-letter
  code used in URLs and filters. The state history page, `/state/<usps>`, lists one state's rows
  in every election this dataset holds for it (T4) and its people per electoral vote in each
  (T7); an election outside the years this dataset covers (*Years covered*) is not on it.
- **Shown as:** `LABELS["state"]`; the state control on `/elections` (placeholder "All
  states"), named by `OVER_TIME_FILTER_SENTENCE` and, while it cannot be offered,
  `OVER_TIME_NO_STATES` (`pages/elections.py`); `labels.C4_TITLE_STATE`, `labels.C5_TITLE_STATE`
  and their "selected state" forms; `labels.FIRST_ELECTION_NOTE` and its "selected state" form `labels.FIRST_ELECTION_NOTE_SELECTED`; the name linking to
  `/state/<usps>` in the C4/C5 table; the state filter on `/election/<year>/states`, named by that
  page's `FILTER_SENTENCE` (`pages/election_states.py`), and on `/election/<year>/per-capita`, named
  by its `FILTER_SENTENCE` (`pages/election_per_capita.py`), both with the placeholder "All states",
  and on `/candidate/<slug>`, with `STATE_PLACEHOLDER` and named by the lede's `FILTER_SENTENCE` or
  `FILTER_SENTENCE_ONE_YEAR` in `pages/candidate.py`; `/states`; the name, as served, as the link to
  the state history page `/state/<usps>` in T2, T5 and T6 (`components.state_cell`), and as that
  page's heading (`render` in `pages/state.py`), or, on the degraded state, "State history" (a
  literal in `layout` there); in `pages/state.py`, the page's lede (`LEDE`), its title (`title`,
  which names at most the code, never the name, and only once the index has checked it), its
  link-preview `description` and T4's download name (`"this state's history"`); its not-found state
  (`NOT_FOUND_HEADING`, also its title, and `NOT_FOUND_SENTENCE` with its link to `/states`, in
  `pages/state.py`); and the home page's lede and its "Browse by state" link (`pages/home.py`). The
  site navigation's States link, `labels.NAV_STATES`, goes to `/states` and is marked on `/states`
  and on `/state/<usps>`. In C3, the row labels, the selected-state series `labels.C3_SELECTED` and
  the caption sentence `labels.C3_SELECTED_NOTE`.
- **Source:** `EcPvRow.state`, `state_usps`; D006; `docs/canonical-keys.md`, "The two keys are
  two-tier"; the state history page: #279 (T4), #280 (T7), and its lede in `pages/state.py`.
- **Not:** —
- **Status:** settled

### State's total popular vote (`state_popular_total`)
- **Plain:** All the votes for President in a state in one election, for every candidate,
  including candidates who are not in this dataset, as the popular-vote source reports them.
- **Precise:** `state_popular_total` on `/v1` rows (warehouse column `state_total_votes`, MIT
  Election Lab's `totalvotes`). On `/v1/elections/states` it is served once per
  `(year, state)` (`ElectionStateRow`). On the candidate rows (`EcPvRow`) it repeats on each of
  the state's rows, and is null on a row whose candidate has no popular-vote figure (a
  faithless elector's choice, for example in 2016). Null in every year outside the
  popular-vote window. Inside the window, a year's values, each state included once, add up
  to `national_pv_denominator`. The candidates' `popular_votes` in a state can add up to less
  than it, because it includes votes for candidates who are not in this dataset.
- **Shown as:** on the API's `/docs` page, the `ElectionStateRow.state_popular_total` and
  `EcPvRow.state_popular_total` field descriptions and the `ElectionStateRow` model docstring in
  `src/usvote/api/models.py`; the `/v1/elections/states` summary and docstring in
  `src/usvote/api/routes.py`; and the API description's **Persons per electoral vote.** paragraph
  (`_DESCRIPTION_TEMPLATE` in `src/usvote/api/app.py`). `LABELS["state_popular_total"]`; with one
  state chosen, C5's bars, `labels.C5_STATE_HOVER`, `labels.C5_TITLE_STATE` and
  `labels.C5_TITLE_SELECTED`, and the null cells `labels.LEGISLATURE_CHOSE`, `TOOK_NO_PART`,
  `BEFORE_WINDOW`, `AFTER_WINDOW` and `NO_STATE_TOTAL`.
- **Source:** `EcPvRow.state_popular_total`, `ElectionStateRow.state_popular_total`;
  `_aggregate_fusion_lines`, `assert_totals_reconcile` and `assert_totals_not_exceeded` in
  `src/usvote/mit/transform.py`; `docs/api-snapshot.md` (`national_pv_denominator`); #428 plan
  measurements (snapshot `37af4064`).
- **Not:** *Popular votes* (one candidate's). The sum of the dataset's candidates' popular votes
  in the state. Zero where a total is missing.
- **Status:** settled; wording pending (#379: the `EcPvRow.state_popular_total` description
  writes "None" and "PV")

### Theme choice (Dark, Auto or Light)
- **Plain:** How the site looks: dark pages, light pages, or Auto, which follows the light or
  dark setting of the reader's device. Auto is the starting choice. A choice is remembered in
  that browser and applies on every page. If the browser won't let the site save it, the choice
  lasts until the page is reloaded or opened in a new tab.
- **Precise:** The viewer's color preference for the dashboard, one of three choices. Auto is
  the absence of a saved choice: the page follows `prefers-color-scheme`. Dark and Light override
  it in both directions. Auto stays selected whenever no choice is saved, whichever palette the
  device's setting gives. Its internal value, `labels.THEME_AUTO` (`"auto"`), is never stored or
  shown. A choice is saved in the browser's `localStorage` under `THEME_STORAGE_KEY`
  (`dashboard/explore/app.py`) and applied as `data-theme` on `<html>` before first paint. Where
  the browser refuses `localStorage`, the choice lasts for the document: it carries across
  in-site (client-side) navigation to other pages, but not a reload or a new tab. It describes
  the page, not the data: it is never in the URL, `og:url`, a CSV download or any API request.
- **Shown as:** the theme toggle, after the site navigation (*Site navigation*) in the site
  header on every page, placed in `app.layout` (`dashboard/explore/app.py`) and built by
  `components.theme_control`: three icon buttons in the order Dark, Auto, Light. Each button's name, `labels.THEME_CHOICES`, is hidden text inside it, read
  by assistive technology. Each button's tooltip is `labels.THEME_TITLES`. The group's name,
  `labels.THEME_CONTROL`, is read by assistive technology and not shown on the page. The stored
  values `light` and `dark` are never shown.
- **Source:** #359 (the three choices, the device's setting as the default, remembered per
  browser, nothing in the URL); reader wording: owner decision, 2026-11-05, #359; the order
  Dark, Auto, Light and the name Auto (formerly System): owner decision, 2026-11-05, #447; the
  three tooltips (`labels.THEME_TITLES`): owner approval at #447's plan gate, 2026-11-05.
- **Not:** *Theme in effect*, which is always light or dark. A chart's color palette (#432).
- **Status:** settled

### Theme in effect (the resolved theme)
- **Plain:** Whether the page is showing its light or its dark colors right now.
- **Precise:** `light` or `dark`: the *Theme choice* when it is Light or Dark; under Auto, the
  device's current `prefers-color-scheme`, updated when that setting changes. Held in the
  `dcc.Store` `components.THEME_STORE_ID`. The chart callback (`CHART_CALLBACK` in
  `dashboard/explore/charts.py`) reads it to redraw every chart on the page in that palette, with
  no reload and no request.
- **Shown as:** Nowhere as text; readers see it only as the page's colors, a chart's included.
- **Source:** #359, acceptance criterion "Expose the resolved theme to Dash"; #432.
- **Not:** *Theme choice*, which can also be Auto.
- **Status:** settled

### Three-method comparison (`election`, `elections`)
- **Plain:** For one election: who led under each of the three methods (the Electoral
  College, the popular vote and the hybrid), whether the popular vote or the hybrid would
  have picked someone other than the Electoral College's winner or leader, each method's
  margin, whether any candidate won a majority of the electors appointed, and the share of
  electors from states that held a popular vote.
- **Precise:** One object per election year (`ElectionSummary`): `year`,
  `electoral_denominator`, `ec_winner`, `pv_winner`, `hybrid_winner` and their `_slug`
  fields, `ec_determinative`, `pv_coverage`, `pv_flip`, `hybrid_flip`, `ec_margin`,
  `pv_margin`, `hybrid_margin`. Served as `election` on `/v1/elections/{year}` and
  `/v1/elections/{year}/summary`, where it is null if the data has no comparison for a
  served year, and as each item of `elections` on `/v1/elections/summary`, one per election
  year, oldest first. Outside the popular-vote window the popular-vote and hybrid fields are
  null (*Outside the popular-vote window*); the Electoral College fields and `pv_coverage`
  have values for every year served.
- **Shown as:** on the API's `/docs` page, the `/v1/elections/summary` summary and docstring
  (`get_all_election_summaries` in `src/usvote/api/routes.py`), and the
  `AllElectionsSummaryResponse` docstring and its `data` and `elections` field descriptions in
  `src/usvote/api/models.py`; the `/v1/elections/{year}/summary` summary in
  `src/usvote/api/routes.py`. On the dashboard, the election panel shows these fields under the
  heading "Under each method" (`pages/election.py`), each with its own `LABELS` key. On the
  dashboard, `/elections` reads `/v1/elections/summary` for C2 (each item's `ec_determinative`, in
  C2's hover and its companion table) and for the averages (each item's `ec_margin` and
  `pv_margin`, *Average margin*).
- **Source:** `ElectionSummary` and its class docstring ("The per-election three-method
  comparison") in `src/usvote/api/models.py`; `_election_summary` in
  `src/usvote/api/routes.py`; D037; D053; #102; #431.
- **Not:** The per-candidate national results (`data` on the `/summary` routes, `summary`
  on `/v1/elections/{year}`). Not an item of `/v1/elections`, which lists election years.
  Not the dashboard panel's heading.
- **Status:** settled

### Took office
- **Plain:** Whether the candidate became president for that term.
- **Precise:** `took_office`, a recorded yes or no.
- **Shown as:** `LABELS["took_office"]` (T3 on `/election/<year>`, and the companion table of C2,
  `elections-leader-table`, on `/elections`); `labels.yes_no`.
- **Source:** `NationalSummaryRow.took_office`; owner decision, 2026-10-10, #348 (a separate term
  from the Electoral College winner); `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "The one
  time it happened"; the C2 companion-table column: owner, #434 plan gate (2026-11-11).
- **Not:** *Electoral College winner, or leader with no majority* (1824).
- **Status:** settled

### Total popular vote (nation) (`national_pv_denominator`)
- **Plain:** All the votes for President across the country in one election, for every
  candidate, including candidates who are not in this dataset, as the popular-vote source reports
  them. This dataset has it only for the years its popular-vote figures cover.
- **Precise:** `national_pv_denominator` on `NationalSummaryRow`, repeated on each candidate row
  of a year; null outside the window. Inside the window it equals the year's
  `state_popular_total` added up, each state once. It is the base of `pv_share`, and the
  dashboard reads the year's one distinct value.
- **Shown as:** `LABELS["national_pv_denominator"]`; in C5 with All states, the bars,
  `labels.C5_HOVER` and `labels.C5_ALL_STATES`; the null cells `labels.NOT_APPLICABLE` and
  `labels.NO_NATIONAL_TOTAL`; and the API `/docs` field description.
- **Source:** `NationalSummaryRow.national_pv_denominator`; `docs/api-snapshot.md`; the #428 and
  #436 surveys (snapshot `37af4064`).
- **Not:**
  - Popular votes (`national_pv_votes`);
  - turnout;
  - the sum of the votes of this dataset's candidates;
  - zero where missing.
- **Status:** settled; wording pending (#379: "each state counted once")

### Unpledged electors
- **Plain:** Electors who, at the election, were not pledged to vote for any particular candidate
  for President. Because they made no pledge, a vote they cast for anyone is not a faithless vote.
  In this dataset the term appears in one note: Mississippi in 1960, where unpledged Democratic
  electors later agreed to support Harry F. Byrd.
- **Precise:** Used in a row note only where that row's own cited passage uses the word:
  CLERK-1960, Mississippi table, footnote 4 ("Unpledged Democratic elector vote, who later agreed
  to support Senator Byrd."). The note does not say the unpledged electors won Mississippi,
  because neither cited passage says so. It gives Byrd's electoral votes by state from ARCH-1960
  in a separate sentence. It gives no kind for his six Alabama votes or his one Oklahoma vote,
  because U.S. Government sources disagree (D079).
- **Shown as:** `BYRD_1960_NOTE` in `src/usvote/party_catalog.py`, served as
  `nominating_party_note` for 1960 Byrd; on the dashboard, in the party cell's help text and the
  Party notes list; and, as a term, the `EcPvRow.pv_status` field description on the API's
  `/docs` page.
- **Source:** CLERK-1960 n.4 (the passage itself sets "unpledged" against "later agreed to
  support"); ARCH-1960; D079.
- **Not:** *Faithless vote*: an unpledged elector had no pledge to break.
- **Status:** settled

### Unrecognized value
- **Plain:** This dataset holds a value that this page has no label for, so the page does not
  show the value itself. Where the value sits in a table, the table's download includes it.
- **Precise:** The reader cell for a non-null value outside what the dashboard has wording for: a
  closed-vocabulary code outside the known set (popular vote in this state, count status, borders
  used, census figure, party); a value of the wrong type in a yes-or-no cell (popular vote in this
  dataset, took office, flip, Electoral College majority); a winner's name on the election panel
  that is not text; a number of the wrong type, or a non-finite one, in a count, share, margin,
  population, people-per-electoral-vote or census-year cell; and a number too large to show as a
  share, margin or people-per-electoral-vote figure (a count, population or census year shows any integer); and a people-per-electoral-vote figure of zero or less, which no state's population divided by its electors appointed can be. It is also the cell for a null figure whose cause field holds an unrecognized code: a
  popular-vote cell whose `pv_status` is unrecognized, a population cell whose `coverage` is, and a
  people-per-electoral-vote cell whose `coverage` is and whose allotment is not zero (a zero
  allotment explains the null first). Candidate and state names are an open vocabulary: candidate
  and state names in the tables, as link text, and as the heading of a state or candidate history
  page are shown as served (#367). In the Party notes list under a table, a candidate name that is
  not text reads this, while the table's cell shows that name as served. A null or blank text is
  not this: it names no cause (*Not in this dataset*), or the cause its row or year gives. No
  served year reaches this cell; it is defensive. On `/elections`, an average margin reads it too
  when a margin among the years shown is of the wrong type or not finite, or when the average is a
  number no margin cell could show; it then names no number of elections or years (*Average
  margin*). In a CSV download the field is written as the API
  served it; for a null figure with an unrecognized cause, the figure's column is empty and the
  cause field carries the code.
- **Shown as:** `labels.UNRECOGNIZED`, with `labels.UNRECOGNIZED_NOTE` as each such cell's help text
  (set by `labels.cell`, and by `labels.nominating_party_cell`). In C1, `labels.UNRECOGNIZED` labels
  the marker drawn in place of a bar for such a value, and `labels.C1_NO_FIGURE_HOVER` writes it
  with `labels.UNRECOGNIZED_NOTE` as that marker's hover text. Reached through `labels.pv_status`,
  `labels.count_status`, `labels._closed_value` (so `labels.boundary_basis`,
  `labels.per_capita_coverage`, `labels._null_per_capita`), `labels.popular_votes`,
  `labels.has_popular_vote`, `labels.yes_no`, `labels.flip`, `labels.ec_majority`, `labels.winner`,
  `labels.nominating_party`, `labels.party_notes` (the Party notes list's candidate name),
  `labels.margin`, `labels.number`, `labels.share` (so `labels.share_cell`), `labels.population`,
  `labels.persons_per_electoral_vote`, `labels.census_year`. In C3, the short label of a marker
  drawn in place of a bar (through `labels.C3_MARKER_LABELS`), and, in `labels.C3_NO_FIGURE_HOVER`,
  the full cell (for `UNRECOGNIZED`, with `labels.UNRECOGNIZED_NOTE`). In `labels.C3_BAR_HOVER`,
  each of the row's other T6 cells (population, electors appointed, census used, borders used) as T6
  shows it, without `labels.UNRECOGNIZED_NOTE`: in T6 that note is the cell's help text, not part of
  the cell, and for the borders cell the caption adds `labels.C3_PLAIN_MIXED`. On `/elections`,
  `labels.metric_mean` writes it for an average margin, with `labels.UNRECOGNIZED_NOTE` as the
  value's help text (set by `labels.cell`). In C4 and C5, `labels.UNRECOGNIZED` labels
  the marker drawn in place of a bar for such a value (C5 through `labels.C5_MARKER_LABELS`), and
  `labels.C4_HOVER`, `labels.C4_STATE_HOVER`, `labels.C5_HOVER` and `labels.C5_STATE_HOVER` write
  it with `labels.UNRECOGNIZED_NOTE`.
- **Source:** owner decision, 2026-10-10, #348 (no raw values in cells); wording: owner decision,
  2026-10-11, #348; the rule (a null names no cause; a non-null value outside the known set reads
  this) and its reach to the numeric cells and the census year: owner decisions at the #355 plan
  gate, 2026-10-13; help text on every such cell: owner decision, 2026-10-13, #355 (its wording:
  owner decision at the #354 plan gate, 2026-10-15); a party code with no letter or digit: owner
  decision, 2026-10-13, #355 (code review) (the party rules from #355 were replaced at #389: the
  party is a closed vocabulary); the comment on `UNRECOGNIZED` and the `labels.py` module docstring.
- **Not:** *Not in this dataset*, which means the dataset holds nothing here. Not a claim that the
  value is wrong, or about any source: only that this page has no wording for it. Not *disputed*,
  which is a recorded fact (see Count status).
- **Status:** settled

### Years covered
- **Plain:** The span of election years the dataset covers: Electoral College results for every
  year in it, and popular votes for a narrower, recent span (the popular-vote window).
- **Precise:** `meta.provenance.coverage`: `year_min` / `year_max` for every year served and
  `pv_year_min` / `pv_year_max` for the years that also carry popular votes. It describes the
  data; it is not a promise. Pages read it from the response, never from a literal.
- **Shown as:** the coverage list (`COVERAGE_ID`) built by `render` in `pages/home.py`; the CSV
  preamble; `labels.BEFORE_WINDOW`; `NO_PV_SENTENCE` in `pages/election.py`; C1's caption sentence
  `labels.C1_NO_PV_CAPTION`, and on `/elections` `labels.METRIC_NO_AVERAGE_PV_YEARS` and
  `labels.METRIC_DIFFERENT_ELECTIONS`, each of which names the years the popular-vote figures
  cover; `labels.C5_BEFORE_BAND`, `labels.C5_AFTER_BAND`, `labels.C5_BEFORE_NOTE`,
  `labels.C5_AFTER_NOTE` and `labels.OVER_TIME_WINDOW_NOTE`.
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
| `nominating_party` | Party |
| `nominating_party_note` | Nominating-party note |
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
| `hybrid_score` | Hybrid |
| `electoral_denominator` | Appointed electors |
| `national_pv_denominator` | Total popular vote (nation) |
| `state_popular_total` | State's total popular vote |

Metric keys (`labels.METRIC_LABELS`) are not `LABELS` keys; each is named under its entry's
**Shown as**: `elections_shown` (*Elections shown*), `ec_margin_mean` and `pv_margin_mean`
(*Average margin*).

---

## Say instead

Words that reach readers too often without help, and what to say instead. **Ships in** names the
code that carries the wording today; "a rule" marks a row that no single string ships.

| Avoid | Say instead | Ships in | Why |
|---|---|---|---|
| "winner" for the Electoral College leader in a year with no majority | Electoral College leader (no majority) | `labels.ec_winner_label`, which picks `labels.EC_LEADER_NO_MAJORITY`; `labels.flip`, which names the role in `labels.FLIP_YES` by the same test (`labels._ec_role_is_winner`) | In 1824 the leader did not become president. |
| "leading candidate" or "winner" for every year's rank-1 candidate | Electoral College leader | `labels.C2_*`, `C2_TABLE_HEADING` and the download name (`pages/elections.py`) | "Leading" alone can mean the popular vote's leader, and "winner" is false for 1824. |
| "not applicable" for a year outside the popular-vote window | that this dataset has no popular-vote figures for the year | `labels.NOT_APPLICABLE`; `NO_PV_SENTENCE` in `pages/election.py` | "Not applicable" reads as a claim that the method had no result at the time. |
| "no figure" without "in this dataset" | no figure in this dataset | `labels.NO_FIGURE`, `labels.NO_NATIONAL_FIGURE`, `labels.C1_NO_FIGURE` | Without it, a reader can take the cell as zero votes. |
| a raw field name, a status code, or anything with an underscore | the plain label | `LABELS`; `labels.PV_STATUS`, `labels.COUNT_STATUS`, `labels.BOUNDARY_BASIS`, `labels.PER_CAPITA_COVERAGE` | Allowed only where the page presents it as a field name (owner decision, 2026-10-10). In the API's published text a public `/v1` name is written as served, and an internal name never appears (owner decision, 2026-10-15, #374). |
| "null" | no value in this dataset | `labels.NOT_IN_DATASET`; the CSV preamble's last line, `export.NULL_LINE`, still uses the word (#375 decides whether it stays) | Engineering term. In the API's published text, null is the JSON value and is written "null", never "None" (owner decision, 2026-10-15, #374). |
| "coverage" on its own | name which one: years covered; census figure; share of electors from popular-vote states | `LABELS["coverage"]`, `LABELS["pv_coverage"]`; years covered: the coverage list (`COVERAGE_ID`) built by `render` in `pages/home.py`, `export.preamble` | The project uses the word for three different things. |
| "counted" for anything but votes | used, covers, included | a rule (see Wording rules) | "Counted" is reserved for vote counts (owner decision, 2026-10-10). |
| "in force", "governs", "apportionment" | used; redistribute House seats | `LABELS["governing_census_year"]`, `labels.GOVERNING_CENSUS_NOTE` | Legal register. Do not swap them for "set the state's electoral votes" when describing the census used: that is false for a state at the elections between its admission and the first redistribution of House seats that included it, for California 1852–1860, and for DC from 1964 (`docs/governing-census.md`). |
| "footprint" | borders | `LABELS["boundary_basis"]`, `labels.BOUNDARY_BASIS`, `labels.BOUNDARY_NOTE` | Survey jargon. |
| "the Archives" | the National Archives | `LABELS["electoral_count_status_reason"]` | A reader may not know which archive. |
| "EC", "PV" in the prose of the API's published text | Electoral College; popular vote | a rule (see Wording rules) | A reader may not know the abbreviations; `ec_` and `pv_` stay inside API field names (owner decision, 2026-10-15, #374). |
| "snapshot" | data version | `components.provenance_footer` (its version line); `export.preamble`; in the API's published text, a rule until #379 rewrites it | Engineering term (owner decision, 2026-10-10). The API's prose follows it too; the field name `snapshot_version` stays (owner decision, 2026-10-15, #374). |
| "No" for a missing value | Not in this dataset | `labels.NOT_IN_DATASET` | "No" is a recorded answer. |
| 0 for a missing figure | never | a rule; in C1, a labeled marker in the bar's place (`labels.C1_NO_FIGURE` for a missing popular-vote figure, `labels.C1_NO_SHARE` for a missing electoral share, or `labels.UNRECOGNIZED` for a value the page has no label for), never a bar of zero length; in C3, a marker with a short label looked up by T6's cell (`labels.C3_MARKER_LABELS`), the full cell in its hover, never a bar of zero length or an infinity; on `/elections`, an average with no contributing election reads *No average* (`labels.METRIC_NO_AVERAGE_FILTERS`, `labels.METRIC_NO_AVERAGE_PV_YEARS`, `labels.METRIC_NO_AVERAGE_NULL`) | Zero is a measurement; a missing figure is not. A real zero is still a drawn, labeled bar. |
| "the state you chose" for a filter's state | Selected state | `labels.C3_SELECTED`, `labels.C3_SELECTED_NOTE` | A shared link carries the filter; the reader who opens it chose nothing. |
| a party code with underscores or in capitals | the party's display form | `labels.NOMINATING_PARTY` | Owner decision, 2026-10-10; closed table since #389. |
| "party" alone where both are meant | name which: the party (the nominating party); the popular-vote source's party | a rule | The API serves both; they differ in vocabulary, years and source. |
| "No nomination", "no party" for `no_nomination` | Without a party's nomination for President when the electors voted | `labels.NO_NOMINATION` | "No party" is a different claim. "No nomination" denies that a withdrawn nominee was ever nominated (D077). |
| a hyphen between the parties of a joint nomination | "and" | `labels.NOMINATING_PARTY` | A hyphen reads as one party's name (Democratic-Republican). |
| "not yet collected", "not yet researched" | Not in this dataset | `labels.NOT_IN_DATASET`, `labels.PARTY_NULL_NOTE` | Dataset-first, with no promise (research §2.3). |
| "Nominating party" as a column header | Party | `LABELS["nominating_party"]` | Rule-2 rows had no national nomination. |
| "every election they ran in" for a candidate's elections | every election in which they received an electoral vote | `pages/candidate.py` (its lede); otherwise a rule | The two sets differ both ways. A run with no electoral votes is not in this dataset, and a person can receive an electoral vote in an election they did not run in (a faithless elector's choice). |
| "figure" for a chart | chart | a rule | In this file and on the page a figure is a number ("no popular-vote figure"). Plotly and HTML call the chart a figure. |
| "C1", "C2" … in page text | the chart's title | a rule | A chart ID is a registry key and a link fragment; readers know a chart by its title (owner decision, 2026-11-06, #432). |
| "previous election", "next election" for a link to a neighboring year | Earlier: the {year} election; Later: the {year} election | `labels.EARLIER_LINK`, `labels.LATER_LINK`, on every election page | The links follow the years this dataset serves, read from the data. "Previous" and "next" claim no election fell between, which nothing in the code checks. |
| "Summary" for an election's first page | Overview | `labels.SECTION_OVERVIEW` | The API serves T3's data as `summary`; one term, one meaning. |
| an arrow character ("←", "→", "«", "»") typed into a link's text | a drawn chevron beside the text, with the words unchanged | a rule (`.neighbor-nav` in `dashboard/explore/assets/style.css`) | A typed arrow is read aloud ("left arrow") and becomes part of the link's name; the words already say which way the link goes. |
| "win margin", "winning margin" | margin | `labels.METRIC_LABELS`, `LABELS["ec_margin"]`, `LABELS["pv_margin"]` | A margin is first place's lead over second under one method; in 1824 the Electoral College leader did not win. |
| "mean" in reader text | average | `labels.METRIC_LABELS` | The plain word; "mean" stays in code and D097. |
| "turnout" | "total popular vote" | `labels.C5_*` | Turnout is a share of eligible voters, which this dataset doesn't have. |
| "no popular vote before 1976" | "this dataset's popular-vote figures begin in {pv_year_min}" | `labels.C5_BEFORE_BAND`, `labels.C5_BEFORE_NOTE` | |

## Open decisions

Terms whose meaning no source settles yet (`proposed`), and settled terms and wording rules whose
merged reader wording still awaits the owner (`settled; wording pending`). Each line names the
decision and who makes it.

- **Not in this dataset**: whether the CSV preamble's last line, `export.NULL_LINE`, keeps the
  word "null" (#375). The owner decides, on a label spec from `ba`.
- **The API's published text** and **Candidate**: merged API text does not yet follow these
  rules: *The API's published text is reader wording*; *In the API's published text, public
  names are vocabulary*; *"Counted" is reserved for vote counts*; and *Plain words over legal
  and survey terms*. That text includes the `EcPvRow.state_popular_total` description (*State's
  total popular vote*), which writes "None" and "PV". Separately, reader text does not call `candidate_slug` "durable" (owner
  decision, 2026-10-16, #379), but these still do: the *Candidate* entry's **Precise**; the
  `/v1/candidates/{slug}` docstring in `src/usvote/api/routes.py`; and the
  `EcPvRow.candidate_slug` and `NationalSummaryRow.candidate_slug` field descriptions in
  `src/usvote/api/models.py`. So do the descriptions of `NationalSummaryRow.national_pv_denominator`,
  `national_electoral_denominator` and `ElectionSummary.electoral_denominator`, which should say
  "each state counted once". #379 rewrites all of them. The owner approves the rewrite, on a
  label spec from `ba`.
- **Census used**: the API's `PerCapitaRow.governing_census_year` description says "in force at
  this election", which does not hold for 1912 and the other elections two years after a census,
  and uses "apportionment" in prose. #379 rewords it (owner decision, 2026-11-02). The owner
  approves the rewrite, on a label spec from `ba`.
