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
  (*Hybrid*). A chart that draws the hybrid calls it the project's proposal in its key, hover and
  caption (D108); that label is not an argument. Every chart's text (chart title, axis titles, trace names, legend title, hover text,
  annotations, caption, and any text written in place of tick numbers) ships from `labels.py`
  under a `ba` spec. *Source:* owner decision, 2026-11-05, #432;
  `.claude/specs/backlog-dashboard.md`, E9-S6, "Conventions every chart follows".
  *Status:* settled.
- **A page-level sentence shows only in the page states where it is true.** A page that reads data
  has a successful render and a degraded state (*Degraded state*); a page about one election, state
  or candidate also has a not-found state (*Not-found state*). Every state shows a heading: on
  success the page's own; on the not-found state its not-found heading; on the degraded state its
  generic heading, which names no year, state or candidate. The lede says what the page shows, so it
  shows on success and on the degraded state, never on the not-found state, and it names nothing on
  the page itself that only a successful render shows (a filter, a list, a table). It may point at
  another page, since the site navigation, which sits outside the page container and shows in every
  page state, still reaches that page. A sentence that offers the page's controls (a filter
  sentence) shows only on success, after the lede, and names only the controls that render shows.
  Everything else of the page's own (the earlier and later links, the section links, section
  headings, count lines, notes, charts, tables and their downloads, and the provenance footer) shows
  only on success. The not-found state shows only its heading, its sentence and its link; the
  degraded state only its heading, its lede and `components.UNAVAILABLE_MESSAGE`. *Source:* no lede
  on the not-found state: owner decision, 2026-11-01, #325; the filter sentence only where filters
  show: #331 (PR #390) and #419 (filed on the owner's approval); the election subpages: `ba` spec
  for #465, approved by the owner at its plan gate (2026-11-10); this rule: #392. *Status:* settled;
  wording pending (the `/states` lede, a literal in `layout` in `pages/states.py`, says "Open one to
  see …" on the degraded state too, where the list it points at does not show).

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
  `/v1/elections/summary` item is the same national figure. In reader text, a state "appointed
  electors" in a year exactly when its allotment is greater than 0 (D115).
- **Shown as:** `LABELS["state_electoral_votes"]` (T2, T4, T6, T7, and the C4/C5 table and C4's bars
  with one state chosen); `LABELS["national_electoral_denominator"]` (T3); in C1, the hover line
  "Electors appointed" (`labels.C1_EC_HOVER`), the majority line's label `labels.C1_MAJORITY_LINE`,
  and the caption sentences `labels.C1_BASES`, `labels.C1_EC_BASIS` and `labels.C1_MAJORITY_NOTE`.
  In C3, the hover line "Electors appointed" (`labels.C3_BAR_HOVER`) and the caption sentence
  `labels.C3_RATIO`. In C2, the hover line "Electors appointed" (`labels.C2_HOVER`), the majority
  line's key entry `labels.C2_MAJORITY_KEY` (#596, D110), and the caption sentences
  `labels.C1_EC_BASIS` and `labels.C2_MAJORITY_NOTE`. `LABELS["electoral_denominator"]` (the C4/C5
  table); in C4: the bars, the value-axis title `labels.C4_VALUE_AXIS`, the hover line "Electors
  appointed", `labels.C4_TITLE`, the key entries `labels.C4_NO_ELECTORS_TOOK_NO_PART` and
  `labels.C4_NO_ELECTORS`, `labels.C4_BASIS`, `labels.C4_ALL_STATES` and `labels.C4_ZERO_NOTE`. C7
  on the state history: its bars, `labels.C4_TITLE_STATE` or `labels.C7_TITLE_THIS_STATE`,
  `labels.C4_VALUE_AXIS`, the hover line "Electors appointed" (`labels.C4_STATE_HOVER`), the key
  entries, `labels.C4_BASIS` and `labels.C4_ZERO_NOTE`, and `LABELS["state_electoral_votes"]` in its
  companion table. On `/elections/over-time`, the figures `labels.METRIC_LABELS["ec_appointed_first"]` and `["ec_appointed_latest"]` (*Earliest and latest electors appointed*). On `/state/<usps>`, it decides which elections the figure `labels.METRIC_LABELS["state_elections_count"]` includes (*Elections in which a state appointed electors*), with `labels.METRIC_NO_FIGURE_NO_ELECTORS` and `labels.METRIC_ZERO_ALLOTMENT_NOTE`.
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
- **Shown as:** `LABELS["candidate"]`; the candidate filter on `/election/<year>/states` and on
  `/state/<usps>/elections`, each with the placeholder "All candidates" (a literal in `_controls` in
  `pages/election_states.py` and in `pages/state_results.py`) and named by that page's `FILTER_SENTENCE`;
  the name, as served, as the link to the candidate history page `/candidate/<slug>` in T2, T3 and
  T4, and as that page's heading (`pages/candidate.py`), or `HEADING` there until a name is read or
  when that name has nothing to read (it is not text, is blank, or is made only of whitespace,
  formatting or control characters, such as a zero-width space; #532); `HEADING` is also the
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

### Candidates with electoral votes chart (C9)
- **Plain:** A chart on the list of elections, with election years running left to right, oldest at
  the left. Each bar is one election, and its height is how many candidates received electoral
  votes in it. Hovering over or tapping a bar shows the year, that number, and each candidate who
  received electoral votes that year, with their electoral votes cast and counted. The page's
  filters narrow the chart and the list together.
- **Precise:** C9 in `CHARTS` on `/elections`, id `c9`, companion table T1 (`elections-table`),
  in the list's card after the pair (the filters, the count and the averages), full width, above
  T1. One bar per distinct year T1 shows, at its year on the year axis (D104), its height the
  served `candidate_count` of that year's `/v1/elections` row; the dashboard counts nothing
  (D097, D091). One series, `--chart-ec` (D109), with no key and no bar text (D104(c)). The hover
  is the year, T1's count cell and that year's *Recipients* lines, escaped (D091). The caption's
  finding is computed from the served counts of the years shown: one sentence for one year, and
  otherwise how many of the elections shown had more than two candidates with electoral votes and
  the most in one election, with every year that ties for the most, or a sentence that none did.
  The year-range and popular-vote filters narrow C9 with T1 (D110, D116(b)); a filter leaving no
  year shows `labels.NO_ELECTIONS_MATCH` and no chart. Two degradation tiers (D116(e)). Tier 1:
  N1 cannot be read, its `elections` items fail `elections_view.n1_items`, the bounds of the
  index's popular-vote window fail `query.year_span` (a missing bound is the whole page's defect),
  or any served year's item lacks a field T1's N1 cells or `election_view.margin_cells` read (T1's
  four N1 fields and `hybrid_margin`). C9 is replaced by `labels.C9_UNAVAILABLE` (id `elections-c9-unavailable`),
  and every N1 cell in T1 reads `labels.UNAVAILABLE_CELL`. Tier 2: `elections_view.n1_recipients`
  refuses a row (a row with no votes cast is refused, never left out), or a year's number of rows
  differs from its `candidate_count`, which must also be at least 1. Both tiers' checks run over
  every served year, before the filters apply, and the tier comes from the check, never from a
  cell. C9 is replaced by the same sentence, and only
  T1's Recipients cells read `labels.UNAVAILABLE_CELL`. Every drawn year's count is reconciled
  first, so C9 has no labeled marker.
- **Shown as:** `labels.C9_TITLE`, `labels.C9_VALUE_AXIS`, `labels.C9_HOVER` (its recipients
  written with `labels.RECIPIENT_LINE`), the caption sentences in order `labels.C9_BASIS`,
  `labels.C9_CAST_NOTE`, one of `labels.C9_FINDING`, `labels.C9_FINDING_NONE` or
  `labels.C9_FINDING_ONE` (tied years through `labels.metric_years`), and
  `labels.C9_HOVER_NOTE`, then `labels.CHART_TABLE_POINTER`; `labels.C9_UNAVAILABLE`; the year
  axis's title (`LABELS["year"]`); `FILTER_SENTENCE` in `pages/elections.py`, which names the
  chart and the list.
- **Source:** #563 acceptance criteria; D116 (amending D075, and D093(a) through D110(a));
  D091; D097; D104; D110; `YearListItem.candidate_count` and the `NationalSummaryRow` fields in
  `src/usvote/api/models.py`; `CHARTS` in `dashboard/explore/charts.py`; reader wording: `ba`
  spec for #563, approved by the owner at its plan gate (2026-11-22).
- **Not:** Candidates on the ballot. Only the candidates whose votes Congress counted (1872's
  Greeley is included). *Candidates in the dataset (dataset-wide count)*. A count the dashboard
  makes itself.
- **Status:** settled; wording pending (the historical claim in `labels.C9_CAST_NOTE`, that in
  1872 Horace Greeley received 3 electoral votes cast and none counted, awaits the owner's check)

### Candidates with electoral votes (count per election)
- **Plain:** How many candidates received electoral votes in that election.
- **Precise:** `candidate_count` on a `/v1/elections` row: the number of distinct candidates in
  that year's national roll-up, which holds every candidate who received at least one electoral
  vote cast that year, including one whose votes Congress did not count (1872, Greeley: 3 cast,
  0 counted). `/v1/meta` also has a `candidate_count` with another meaning: see *Candidates in
  the dataset (dataset-wide count)*.
- **Shown as:** `LABELS["candidate_count"]` (T1); in C9 (*Candidates with electoral votes chart
  (C9)*), each bar's height, `labels.C9_TITLE`, the value-axis title `labels.C9_VALUE_AXIS` and
  the count line of `labels.C9_HOVER`; on the API's `/docs` page, the
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
  it (on most charts the reader opens it with "About this chart"), and a link, always shown, to
  the table on the same page that holds its numbers. The tables are the record.
  A chart is another way to see it, and the page works without one.
- **Precise:** Built only by `components.chart(chart_id, figure, table_id, caption)`. It is an HTML
  `figure` element holding, in order, the **chart title**, the drawing, and a caption
  (`figcaption`). The title is written as page text (a paragraph, not a heading), so it shows and
  wraps even when the drawing cannot load. The caption sits in a disclosure (`details`), closed when
  the page loads and opened by its summary, `labels.CHART_CAPTION_SUMMARY`. The table pointer,
  `labels.CHART_TABLE_POINTER`, a link to the chart's *Companion table*, follows it outside the
  disclosure and is always shown. C1's caption stays open, unfolded and with no summary, because its
  bar-order sentence is its one cue apart from color (#593). The builder refuses a chart with no
  title or no caption. Each series writes its own hover text or shows none. A figure that breaks the
  chart rules `charts.figure_problems` checks (a series whose hover text would be plotly's own, a
  color that is not a theme token, and the rest) is not drawn. The chart keeps its title, its
  caption and the pointer, with nothing shown between them, as when plotly.js cannot load. The page
  keeps its tables and its other charts, and the failure is logged at error level for the developer.
  Readers see no message about it. The chart title is plain text and says what the chart shows; the
  caption may state a finding (*A chart title describes; a caption may state a finding*). For
  assistive technology, a drawn chart, and one still waiting for plotly.js or whose load failed, is
  an image named by its chart title, and what is drawn inside it is skipped; a chart that is not
  drawn is no image, only its title and caption as text. Either way the companion table carries the
  numbers. Pointing at a mark shows only the hover text written for that series, for the nearest
  point. Axis numbers are written in full with thousands separators, as the tables write them, never
  shortened ("80M", "1.2B"), with two exceptions: C5's and C10's value axes (the total popular
  vote, the nation's and a state's) write their numbers short, as "0, 50M, 100M, 150M" ("M" is
  millions, "k" thousands), and their hover text and companion tables still write each total in
  full. The legend is only a key: clicking it hides nothing. A reader
  cannot zoom or drag a chart, and no toolbar shows on it. Every chart has a **chart ID**, `C<n>`,
  issued in order of story filing. An ID is never renumbered or reused, and a retired ID stays
  retired. The closed registry `CHARTS` in `dashboard/explore/charts.py` maps each ID to its page
  and its companion table. The chart's element id is the ID in lower case (`c1`), so
  `/elections/majority#c2` is a link to that chart. The part after `#` never reaches the server and
  changes neither the canonical link nor `og:url`. Readers meet the ID only in such a link, never in
  page text. Colors come from the page's theme tokens and follow the *Theme in effect*. Each measure
  has one color on every chart (#593, owner decision 2026-11-19): values derived from electoral
  votes (electoral share, electors appointed) `--chart-ec`, red; values derived from popular votes
  (popular-vote share, total popular vote) `--chart-pv`, blue; the hybrid score `--chart-hybrid`,
  purple. Switching the theme redraws every chart on the page, with no reload and no request. Series
  always differ by more than color. The drawing needs plotly.js, which the browser fetches from
  plotly's CDN when the page's first chart mounts; a page with no chart fetches nothing from it. If
  the fetch fails, or the figure breaks the chart rules, no drawing appears, and the title, the
  caption, the pointer and the page's tables still show. A chart is never a page's success marker. A
  chart has no download of its own: its companion table's CSV carries its numbers.
- **Shown as:** `components.chart`, which writes each chart's title as page text above the drawing
  (`html.P`, class `chart-title`, id `<chart element id>-title`) and its caption below it;
  `labels.CHART_TABLE_POINTER`; `labels.CHART_CAPTION_SUMMARY`; each chart's own wording (title,
  axis titles, trace names, legend title, hover text, annotations, caption) in `labels.py`; the axis
  number format, the hover behavior and the inert legend in `charts.TEMPLATE`, and C5's and C10's
  short value-axis numbers, the two exceptions, named on their `CHARTS` rows (`short_value_ticks`),
  and the
  absent toolbar in `charts.CHART_CONFIG`, both in `dashboard/explore/charts.py`. C1, on the
  election overview (`/election/<year>`), is the first chart a page renders. C3 is on an election's
  People per electoral vote page (`/election/<year>/per-capita`). The home page's lede
  (`pages/home.py`) already says "Tables and charts". C2 is on `/elections/majority`, after the
  page's year filters and followed by its companion table. C4 and C5 are on `/elections/over-time`,
  after the page's year filters, C4 above C5 with their year axes lined up, followed by the one
  companion table they share. C7 is on a state's history page (`/state/<usps>`); C10 is directly below C7, their plots lined up (#582), and the one companion table they share follows both (#618). C9 is on `/elections`, in the list's card after the filters, the count and the
  averages, full width above T1, its companion table (#563, D116).
- **Source:** #432 acceptance criteria; `.claude/specs/backlog-dashboard.md`, E9-S6,
  "Conventions every chart follows"; owner decisions, 2026-11-05 (titles describe the chart and a
  caption may state a finding or carry narrative; plotly.js from its CDN, loaded lazily, with no
  SRI), recorded in D087; the drawing put in only once plotly.js has loaded, so a failed load
  leaves its space empty: owner decision on #452, 2026-11-07, recorded in D088; owner decisions
  at #432's plan gate, 2026-11-06 (the table pointer's wording, no toolbar, no chart IDs in
  reader text); `CHARTS` and `dom_id`, `TEMPLATE` and `CHART_CONFIG` in
  `dashboard/explore/charts.py`; a figure that breaks the chart rules is not drawn, and its page
  keeps its tables: #467 acceptance criteria, recorded in D095; the collapsed caption, the
  measure colors and the summary's wording: #593 (D109, amending D102, D104, D108); `ba` spec for
  #593; C5's short value-axis numbers: owner decision, 2026-11-20, #596 (D110, amending this rule).
- **Not:** A *figure*: in this file and on the page, a figure is a number ("no popular-vote
  figure"), and Plotly's and HTML's word for a chart stays in code. Not a page's title (the
  browser tab, `og:title`): a chart has a chart title. Not a stand-in for its companion table.
  Not a column-name list. The measure colors are not party colors: red does not mean Republican
  and blue does not mean Democratic.
- **Status:** settled

### Companion table
- **Plain:** The table on the same page that holds a chart's numbers. The link under the chart,
  after its caption, goes to it, and its download is how to take those numbers away.
- **Precise:** The table that each chart's registry row names by its element id. Two charts can share one companion table (C4 and C5; C7 and C10). C4 and C5's table, on `/elections/over-time`, shows all
  states; the page's year filters narrow it and both charts alike, as they narrow C2 and its table
  on `/elections/majority` (#596). On a state's history page, C7 and C10 share one companion table, `state-electors`, below both charts (#618). There, a fault that removes one chart leaves the table, with that chart's column reading *Not available right now*. On `/elections`, T1 is C9's companion table,
  and the page's filters narrow both alike (#563, D110, D116(b)); C9's hover also lists the
  recipients, which T1 shows on the page but leaves out of its download (*Recipients*).
  `components.chart` refuses any other table. The table pointer links
  to `#<table id>`, the table element itself, below the table's heading. Every chart's pointer has
  the same text; the caption it ends tells the reader which chart it belongs to. Like every table,
  it is built by `components.table` with its own CSV. A filter on the page can narrow the table
  without narrowing the chart, so the pointer says only that the chart's numbers are in a table on
  the page, never that the table shows "the same" or "all" of them.
- **Shown as:** `labels.CHART_TABLE_POINTER`, after each chart's caption, outside its collapsed
  part.
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
  only when it has something to read (it is text, not blank, and not made only of whitespace,
  formatting or control characters, such as a zero-width space; #532), and leaves it out otherwise (the download keeps it
  as served; #355); the count-status filter on `/election/<year>/states`, with the placeholder
  "Any" (a literal in `_controls` in `pages/election_states.py`), named "count status" by that
  page's `FILTER_SENTENCE`.
- **Source:** `src/usvote/count_status.py`, `COUNT_STATUS_VALUES` and the comment on each value;
  `EcPvRow.electoral_count_status` and `electoral_count_status_reason`; D043; D044; D047; D048 §4;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "When the record itself won't say" (the
  reader wording for not counted and disputed).
- **Not:** Appointed electors who never voted, a different gap (`ELECTORAL_VOTE_SHORTFALLS`); and
  *Electors without a counted vote*, which adds votes never cast to the votes not counted or
  disputed.
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
  before National results). `LEDE` and `FILTER_SENTENCE` in `pages/elections.py`; the `LEDE`s of
  `pages/elections_majority.py` and `pages/elections_over_time.py`.
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
  The page keeps a heading and its lede, but no filter sentence and nothing else of its own; on a
  page about one election, state or candidate, the heading is the page's generic one, which names
  none of them (*A page-level sentence shows only in the page states where it is true*).
- **Shown as:** `components.UNAVAILABLE_MESSAGE`.
- **Source:** `dashboard/explore/components.py`; `dashboard/CLAUDE.md`, `components.py`.
- **Not:** A not-found state (*Not-found state*): a link whose year, state code or candidate slug
  the dataset does not serve, or whose election section the site does not have
  (`labels.ELECTION_NOT_FOUND_SENTENCE` for the election pages, `labels.STATE_NOT_FOUND_SENTENCE`
  for the three state pages, and `NOT_FOUND_SENTENCE` in `pages/candidate.py`). An empty filter result
  (`components.NO_ROWS`; on the three elections pages, `labels.NO_ELECTIONS_MATCH`; *No elections
  match*). The panel's own unavailable state (`PANEL_UNAVAILABLE`). A chart that is not drawn
  (*Chart*): its page still shows, with its tables. A chart section's own unavailable state
  (`C2_UNAVAILABLE` in `pages/elections_majority.py`, id `elections-leader-unavailable`, and
  `OVER_TIME_UNAVAILABLE` in `pages/elections_over_time.py`, when `/v1/elections/summary` cannot be
  read): each is the only section on its page, and the page keeps its heading, lede and section
  links. The averages' own unavailable state (`METRICS_UNAVAILABLE` in `pages/elections.py`): the
  count of elections shown and the rest of the page still show. C9's and T1's N1 columns' own
  unavailable states on `/elections` (#563, D116(e)). In tier 1 (N1 cannot be read, its
  `elections` items fail their check, the bounds of the popular-vote window fail theirs, or a
  served year's item lacks a field T1's N1 cells are built from; checked over every served year
  before the filters): `labels.C9_UNAVAILABLE` (id
  `elections-c9-unavailable`) in C9's place, `labels.UNAVAILABLE_CELL` in each of T1's five N1
  columns, and `T1_N1_UNAVAILABLE_NOTE` first among T1's notes and in its download where one is offered,
  and among the notes even when the filters leave no election (the tier comes from the check, never from a cell; C9 then shows nothing).
  In tier 2 (a recipient row fails its check, a row with no votes cast included, or a year's rows
  do not match its `candidate_count`, which must be at least 1):
  `labels.C9_UNAVAILABLE`, and `labels.UNAVAILABLE_CELL` in the Recipients cells only, with no
  note. The rest of T1 and the page still show. In a download made while N1 can't be read, an
  empty cell in the four columns the note names means not read. It does not mean null, even
  though the preamble's last line (`export.NULL_LINE`) still prints; the note overrides it (owner
  decision at #563's plan gate, 2026-11-22). The state history's own unavailable states (#618):
  `C7_UNAVAILABLE` or `C10_UNAVAILABLE` in place of a chart, *Not available right now* in that
  chart's column of the shared table with `ELECTORS_UNAVAILABLE_NOTE` or `TOTALS_UNAVAILABLE_NOTE`
  first among its notes, and, when a fault reaches both charts, `ELECTORS_TOTALS_TABLE_UNAVAILABLE`
  in place of the table. The page stays.
- **Status:** settled

### Earliest and latest electors appointed (figures)
- **Plain:** On the page of electors appointed and the total popular vote over time: the electors appointed across all states in the earliest and in the latest election shown, each with its year, and how many elections they are taken from.
- **Precise:** `metrics.select` over (year, `electoral_denominator`) pairs from the `elections` items of `/v1/elections/summary`, for the years the over-time companion table shows under the parsed `year_from`/`year_to`/`pv` filters (D110, D112(g)), picking `first` and `latest`. N is the number of those years whose value is not null or blank (`labels.is_blank`); a null or blank is left out whatever its cell reads, even a cell that reads *Unrecognized value*, since that cell names why the value is missing, not a value; it is never an extreme and N does not count it. The value is that year's own cell in the companion table (`labels.number`), so figure and table cannot disagree; never a difference, ratio or percentage change (D112(d)). With N = 1 the earliest names its one year and the latest reads `labels.METRIC_SELECT_SAME`. Any other value `labels.finite` refuses, or any value whose own table cell reads *Unrecognized value* (a number the table cannot show), whichever year holds it, makes both figures of the pair read *Unrecognized value* with no N or years, since they share one selection. With N = 0 it reads *No figure*. The figures read the same checked summary rows as charts C4 and C5, so a failed or malformed read removes the section, figures included; when the filters leave no year, *No elections match* shows and no figure does.
- **Shown as:** `labels.METRIC_LABELS["ec_appointed_first"]` and `["ec_appointed_latest"]`; the value through `labels.metric_select` (`labels.METRIC_SELECT`, `labels.METRIC_SELECT_ONE`, `labels.METRIC_SELECT_SAME`, with `labels.METRIC_SELECT_OTHER`, the word "earliest" it names); `labels.METRIC_NO_FIGURE["ec_appointed_first"]`; `labels.UNRECOGNIZED`. On `/elections/over-time`, in the `dl.metrics` block `elections-over-time-metrics` inside the charts' card, after the filters and before chart C4 (`pages/elections_over_time.py`).
- **Source:** #569 (figure set approved by the owner, 2026-11-18); #600; D112(d), (g) and its addendum; `ElectionSummary.electoral_denominator` in `src/usvote/api/models.py`; `METRICS` in `dashboard/explore/metrics.py`; reader wording: `ba` spec for #600, approved at its plan gate.
- **Not:** The change between the two years, or any ratio of them. A state's electors appointed (chart C7). Electoral votes cast or counted.
- **Status:** settled

### Earliest and latest total popular vote (figures)
- **Plain:** On the same page: the total popular vote across the country in the earliest and in the latest election shown that has a total in this dataset, each with its year. This dataset's popular-vote figures begin later than its Electoral College results, so the earliest total shown is the earliest this dataset has, not the earliest election; a note under the figures names the years they cover.
- **Precise:** `metrics.select` over (year, `national_pv_denominator`) pairs, the year's one distinct value across `NationalSummaryRow`s (the same value chart C5 reads), for the years the over-time companion table shows (D110, D112(g)), picking `first` and `latest`. N, nulls, the value as the table's cell (`labels.national_total`) and N = 1 follow *Earliest and latest electors appointed*. Any other value `labels.finite` refuses, or any value whose own table cell reads *Unrecognized value*, whichever year holds it, makes both total popular vote figures read *Unrecognized value* with no N or years, since they share one selection; the electors figures have a selection of their own and are not affected. `coverage` supplies only the window (`pv_year_min`–`pv_year_max`), never the first year (D112(d)). While the figures show a number, `labels.METRIC_PV_TOTAL_WINDOW_NOTE` names the window under the block; it does not say the N years lie inside it. With N = 0 it reads *No figure*: `labels.METRIC_NO_FIGURE_PV_YEARS` when no year shown lies inside the window, otherwise `labels.METRIC_NO_FIGURE["pv_total_first"]`.
- **Shown as:** `labels.METRIC_LABELS["pv_total_first"]` and `["pv_total_latest"]`; the value through `labels.metric_select` (`labels.METRIC_SELECT`, `labels.METRIC_SELECT_ONE`, `labels.METRIC_SELECT_SAME`, with `labels.METRIC_SELECT_OTHER`, the word "earliest" it names); `labels.METRIC_PV_TOTAL_WINDOW_NOTE`; `labels.METRIC_NO_FIGURE_PV_YEARS`; `labels.METRIC_NO_FIGURE["pv_total_first"]`; `labels.UNRECOGNIZED`. In `elections-over-time-metrics` on `/elections/over-time`.
- **Source:** #569; #600; D112(b), (d), (g) and its addendum; `NationalSummaryRow.national_pv_denominator`; `METRICS`; reader wording: `ba` spec for #600, approved at its plan gate.
- **Not:** The first election held by popular vote. Turnout. A change or growth rate between the two years. Zero where missing.
- **Status:** settled

### A state's first election
- **Plain:** The first election in this dataset in which a state appointed electors. A state's history page starts its charts and table there, so a state that joined the Union after 1824, such as Texas (1848), does not open on years before it took part. An election later on in which the state appointed no electors (Texas in 1864 and 1868) stays on the charts and in the table.
- **Precise:** `first_election(records)` in `pages/state.py`: the earliest year of C7's collapse (`electors()`) whose `state_electoral_votes` is an `int` (never a `bool`) above 0. This is the same rule as the *Elections in which a state appointed electors* count, whose first year is this one, and #621's figure reads the same function. If C7's collapse cannot be built, the page's span falls back to the state's first served row (`over_time.state_series`' own start), and no caption names a first election. On served data no state lacks one, and every state's first served row is its first election (checked against the live API for #620). It is about this dataset's rows, not a historical claim about when the state first voted.
- **Shown as:** `labels.FIRST_ELECTION_START_NOTE` (else `labels.FIRST_ELECTION_START_NOTE_THIS_STATE`) in C7's and C10's captions, only when the years shown start there and it is after `coverage.year_min`. The default start of the Years slider on `/state/<usps>`.
- **Source:** #620 scope and ACs (owner, 2026-11-23); D115(c) ("appointed electors"); D119; reader wording: `ba` spec for #620, approved by the owner at its plan gate (2026-11-23).
- **Not:** The dataset's first year (`year_min`). The first year a state has a row. "Took part" (D115). The first election held by popular vote in the state.
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
  `pages/election.py`, its section headings "Under each method" (a literal in `_panel`; *Three-method
  comparison*) and "National results" (a literal in `render`), and T3's download, named "the
  national results" in the file `election-{year}-national.csv` (`_download`); `STATES_HEADING`,
  `STATES_GENERIC_HEADING`, `LEDE`, `FILTER_SENTENCE` and `description` in
  `pages/election_states.py`, and T2's download, named "the results by state" in the file
  `election-{year}-by-state.csv` (`_download`); `PER_CAPITA_HEADING`, `PER_CAPITA_GENERIC_HEADING`,
  `LEDE`, `FILTER_SENTENCE` and `description` in `pages/election_per_capita.py`, and T6's download
  (*People per electoral vote*). On each page, `LEDE` shows on a successful render and on the
  degraded state, and the subpages' `FILTER_SENTENCE` only on a successful render; the not-found
  state shows neither (*A page-level sentence shows only in the page states where it is true*).
  The generic headings are under *Election year*. `election_view.py` ships no wording of its own:
  the section links, the earlier and later links and the not-found state it builds take their
  words from `labels.py`.
- **Source:** #465 (owner decisions, 2026-11-09: the split, the per-capita state filter, the earlier
  and later links keeping the page, the 302); D092; reader wording: `ba` spec for #465, approved by
  the owner at its plan gate (2026-11-10).
- **Not:** *Site navigation*. *State pages*, whose results by election and people per electoral vote pages' section links carry the year range (D105, D118). The earlier
  and later links (*Election year*). The API's `summary`.
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
- **Shown as:** `LABELS["year"]`; the year axis of C2 on `/elections/majority`, of C4 and C5 on
  `/elections/over-time`, of C9 on `/elections` and of C7 and C10 on `/state/<usps>`, a numeric axis with a tick every 4, 8, 10, 20
  or 40 years, the smallest of those that goes into the span of years shown at most five times, so
  the axis writes at most five ticks (every 40 years over every served year); the year-range slider
  (`/elections`, `/elections/majority`, `/elections/over-time`, `/state/<usps>`,
  `/state/<usps>/elections`, `/state/<usps>/per-capita`), labeled "Years" on each
  (`labels.YEARS_FILTER`; a literal on the two state subpages) and offered by each page's `FILTER_SENTENCE`; the label of the year control on
  `/candidate/<slug>`, and the lede sentence that offers it (`FILTER_SENTENCE` in
  `pages/candidate.py`); the election pages' headings: `HEADING` on the overview
  (`pages/election.py`), `STATES_HEADING` (`pages/election_states.py`) and `PER_CAPITA_HEADING`
  (`pages/election_per_capita.py`), each the `H1` that page's `render` builds and the start of its
  title (`title`); on the degraded state, and in the title before a year is checked, "Election" on
  the overview (a literal in both `layout` and `title` there), `STATES_GENERIC_HEADING` and
  `PER_CAPITA_GENERIC_HEADING`; the earlier and later links on every election page
  (`labels.EARLIER_LINK` and `labels.LATER_LINK`) and their accessible names
  (`labels.ELECTION_NAV_LABEL` on the overview and `labels.ELECTION_NAV_SECTION_LABEL` on the
  subpages, read by assistive technology, not shown). The links sit in a bordered bar above the page
  heading, the earlier link at the left and the later at the right, each with a chevron pointing its
  way (before the earlier link's text, after the later's). The chevrons are drawn shapes with no
  text: they are not part of either link's name and are never read aloud, so the words "Earlier" and
  "Later" carry the direction.
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
  showing the field needs its own `LABELS` key. The number of these years shown, under the year
  choice, is `labels.METRIC_LABELS["candidate_elections_count"]` (*Elections in which electors
  voted for a candidate*); tests check it against `years` (D112(f)).
- **Source:** `CandidateListItem.years` in `src/usvote/api/models.py` and
  `SnapshotRepository.list_candidates` in `src/usvote/api/repository.py` (#330); D007.
- **Not:** Years the candidate ran or was on the ballot; only years whose electoral votes Congress
  counted (*Electoral votes counted*); years the candidate took office (*Took office*).
- **Status:** settled

### Elections in which a state appointed electors (count)
- **Plain:** On a state's history page: how many elections in this dataset the state appointed electors in, with the earliest and latest. An election in which the state appointed no electors (Georgia in 1864) is left out, so the number can be smaller than the years the electors chart shows; a note names the years left out.
- **Precise:** The number of years on `/v1/states/{usps}` whose one allotment, collapsed by `electors()` (`state_electoral_votes`), is an `int` (never a `bool`) greater than 0. In reader text this is "appointed electors", never "took part" (D115). First and last are the earliest and latest of those years. It is unfiltered: the history page's Years filter does not reach it (D119), and the filters on the results by election page (`/state/<usps>/elections`) do not reach it (D112(g)), and it matches C7's unfiltered companion table. If any year's allotment is not an `int` 0 or above, both state figures read *Unrecognized value* and C7 stays. If the collapse itself fails, because a year's allotments disagree, C7's chart gives way to its note, the table's electors column reads *Not available right now*, and the figures go with it (D112(c); #618). With no year above 0 it reads `labels.METRIC_NO_FIGURE_NO_ELECTORS`. While it shows a number and some year's allotment is exactly 0, `labels.METRIC_ZERO_ALLOTMENT_NOTE` names those years through `labels.metric_years`. Recorded Georgia: 50 elections (1824–2024); C7 shows 51 years, and 1864 is left out.
- **Shown as:** `labels.METRIC_LABELS["state_elections_count"]`; the value through `labels.metric_elections` (`labels.METRIC_COUNT_ELECTIONS`, `labels.METRIC_COUNT_ELECTIONS_ONE`); `labels.METRIC_NO_FIGURE_NO_ELECTORS`; `labels.METRIC_ZERO_ALLOTMENT_NOTE`; `labels.METRIC_ALL_YEARS_NOTE`, under the figures while the Years filter applies a narrower range than the state's span (#620); `labels.UNRECOGNIZED`. On `/state/<usps>`, in `state-history-metrics` inside the card C7 and C10 share, after its heading and before the chart; the value `state-elections-count` (`pages/state.py`).
- **Source:** #569; #601; D112(c), (e), (g); D115; `EcPvRow.state_electoral_votes` in `src/usvote/api/models.py`; `METRICS` in `dashboard/explore/metrics.py`; reader wording: `ba` spec for #601, approved at its plan gate.
- **Not:** The years with rows. Elections the state's people voted in. A count of electors.
- **Status:** settled

### Elections in which a state's electors voted for the candidate who took office (count)
- **Plain:** On a state's history page: in how many of the elections in which the state appointed electors, its electors cast at least one electoral vote for the candidate who became president for that term. A delegation that split counts if any of its votes went to that candidate.
- **Precise:** `metrics.flag_count` over one flag per year in which the state appointed electors (an allotment that is an `int` greater than 0), counting true. In each such year the one row with `took_office` true picks the candidate, and that row's cast `electoral_votes` decides: above 0 is true, 0 is false (D112(a) as amended by D115; D112(e)). A null or blank `electoral_votes` there leaves the year out of N, so N can be smaller than the elections count beside it; the figure shows its own N ("27 of 50 elections") and never claims the two are equal. This figure alone reads *Unrecognized value* when a year that appointed electors has no `took_office`-true row or two, a row with a null, missing or non-boolean `took_office`, or a took-office row whose `electoral_votes` is neither null, blank nor an `int` 0 or above; the elections count, C7, C10, their shared table and the page stay. When an allotment is unrecognized, both figures read it. Comparing `electoral_votes` with `state_electoral_votes` would be wrong: it gives Georgia 28 where the answer is 27. First and last are the earliest and latest of the N years. It is unfiltered (D112(g)) and never a percentage (D097(a)). T4 does not show `took_office`. With no year that appointed electors it reads `labels.METRIC_NO_FIGURE_NO_ELECTORS`; with such years but every one left out, `labels.METRIC_NO_FIGURE["state_took_office_count"]`. The density this rests on was checked on the live API for every state (#601, 2026-11-22): one `took_office` row per year with electors, none null; 33 split delegations. Recorded Georgia: 27 of 50 (1824–2024).
- **Shown as:** `labels.METRIC_LABELS["state_took_office_count"]`; the value through `labels.metric_count` (`labels.METRIC_COUNT_OF`, `labels.METRIC_COUNT_OF_ONE`); `labels.METRIC_NO_FIGURE_NO_ELECTORS`; `labels.METRIC_NO_FIGURE["state_took_office_count"]`; `labels.METRIC_ALL_YEARS_NOTE` (as for the elections count); `labels.UNRECOGNIZED`. In `state-history-metrics` on `/state/<usps>`, the value `state-took-office-count`.
- **Source:** #601; D112(a), (e), (g); D115; `EcPvRow.took_office` and `EcPvRow.electoral_votes`; `METRICS`; reader wording: `ba` spec for #601, approved at its plan gate.
- **Not:** "Voted for the winner" or "the eventual winner": in 1824 the Electoral College leader did not take office (*Took office*). The state's popular-vote winner. A share or percentage.
- **Status:** settled

### Elections in which electors voted for a candidate (count)
- **Plain:** On a candidate's page: how many elections in this dataset electors cast at least one electoral vote for the candidate in, with the earliest and latest. It follows the page's year choice, never its State filter.
- **Precise:** `metrics.count` over the distinct `year` values of the candidate's `/v1/candidates/{slug}` rows for the chosen year, or for all years (never T5's shown rows, which follow the State filter too). A year choice outside the candidate's years falls back to all years. The basis is votes cast, so Greeley 1872 (3 cast, 0 counted) is one election. It equals the length of `years` on the candidate's `/v1/candidates` item, checked in tests only (D112(f)). On a successful render it is never 0; `labels.METRIC_NO_FIGURE_NO_CANDIDATE_ELECTIONS` is defensive. While the State filter is applied, `labels.METRIC_ALL_STATES_NOTE` shows under the block. Recorded Andrew Jackson: 3 elections (1824–1832); with 1828 chosen, 1 election (1828).
- **Shown as:** `labels.METRIC_LABELS["candidate_elections_count"]`; `labels.metric_elections` (`labels.METRIC_COUNT_ELECTIONS`, `labels.METRIC_COUNT_ELECTIONS_ONE`); `labels.METRIC_NO_FIGURE_NO_CANDIDATE_ELECTIONS`; `labels.METRIC_ALL_STATES_NOTE`. On `/candidate/<slug>`, in `candidate-metrics` inside T5's card, after the controls and before the count line; the value `candidate-elections-count` (`pages/candidate.py`).
- **Source:** #601; D112(f), (g); D115; `EcPvRow.year`; `CandidateListItem.years`; reader wording: `ba` spec for #601, approved at its plan gate.
- **Not:** Elections the candidate ran in (*Say instead*). Elections whose votes Congress counted. Elections the candidate took office in.
- **Status:** settled

### Elections shown (count)
- **Plain:** How many elections the list on the Elections page shows under the filters in effect,
  out of all the elections in this dataset.
- **Precise:** The number of `/v1/elections` rows T1 shows after the year-range and popular-vote
  filters (`metrics.count`), beside the number of elections served. An average's own number of
  elections (*Average margin*) can be smaller: it includes only elections that have that margin.
- **Shown as:** `labels.METRIC_LABELS["elections_shown"]`, the count line above T1 on `/elections`.
- **Source:** #437 acceptance criteria; D097; `METRICS` in `dashboard/explore/metrics.py`.
- **Not:** The number of elections an average covers. *Candidates in the dataset*. *Rows shown*,
  the count line above a table on another page, which counts that table's rows.
- **Status:** settled

### Elections with a different popular-vote winner (count)
- **Plain:** On the Electoral College majority page: how many of the elections shown had a popular-vote winner other than the Electoral College leader. It is out of the elections shown that have a popular-vote winner in this dataset, and names the earliest and latest of those years. A note under it names the years this dataset's popular-vote figures cover. Those begin later than its Electoral College results, so this number usually covers fewer elections than the count beside it. It says nothing about elections without a popular-vote winner in this dataset.
- **Precise:** `metrics.flag_count` over (year, `pv_flip`) pairs for the years C2's companion table shows under the parsed `year_from`/`year_to`/`pv` filters (D110), counting true. N is the number of those years whose flag is true or false. A null or a blank (`labels.is_blank`) is never counted as false and is left out of N. C2's own check (`_agrees` in `pages/elections_majority.py`) makes `pv_flip` true or false exactly when the year has a `pv_winner_slug`, so N is the years shown that have a popular-vote winner in this dataset, whatever their year. First and last are the earliest and latest of the N years, not the filter bounds (D112(b)). It is never a percentage (D097(a)). While the figure shows a number, a note under the block says the count includes only elections with a popular-vote winner in this dataset and names the popular-vote window from `meta.provenance.coverage` (`pv_year_min`–`pv_year_max`), never a literal; the note does not say the N years lie inside that window. When N is zero it reads *No figure*: `labels.METRIC_NO_FIGURE_PV_YEARS` when no year shown lies inside the window, otherwise `labels.METRIC_NO_FIGURE["pv_flip_count"]`. A `pv_flip` that is not true, false or null, a blank included, fails C2's own check first, so the section reads `C2_UNAVAILABLE`; for this figure, both the blank-as-null rule and the *Unrecognized value* reading are defensive. It reads the same checked summary rows as C2, so a failed or malformed read removes the section, figure included. When the filters leave no year, *No elections match* shows and no figure does.
- **Shown as:** `labels.METRIC_LABELS["pv_flip_count"]`; the value through `labels.metric_count` (`labels.METRIC_COUNT_OF`, `labels.METRIC_COUNT_OF_ONE`); the note `labels.METRIC_PV_WINDOW_NOTE`; `labels.METRIC_NO_FIGURE_PV_YEARS`, `labels.METRIC_NO_FIGURE["pv_flip_count"]`. On `/elections/majority`, in the `dl.metrics` block `majority-metrics` inside C2's card, after the filters and before the chart; the value `majority-pv-flip-count` (`pages/elections_majority.py`).
- **Source:** #569 (figure set approved by the owner, 2026-11-18); D097; D112; `ElectionSummary.pv_flip` in `src/usvote/api/models.py`; `METRICS` in `dashboard/explore/metrics.py`; reader wording: `ba` spec for #569, approved at its plan gate.
- **Not:** A percentage or share. A claim that no different popular-vote winner occurred before the popular-vote window. The hybrid's flip. *Flip* for one election. A popular-vote "leader".
- **Status:** settled

### Elections with no Electoral College majority (count)
- **Plain:** On the Electoral College majority page: how many of the elections shown had an Electoral College leader with no majority of the electors appointed. It is out of the elections shown for which this dataset says whether there was one, and names the earliest and latest of those years.
- **Precise:** `metrics.flag_count` over (year, `ec_determinative`) pairs for the years C2's companion table shows under the parsed `year_from`/`year_to`/`pv` filters (D110), counting false. N is the number of those years whose flag is true or false. A null or a blank (`labels.is_blank`) is never counted as false and is left out of N. First and last are the earliest and latest of the N years, not the filter bounds (D112(b)). It is never a share compared with one half and never a percentage (D097(a)). Any other value that is not true or false among the years shown makes this figure alone read *Unrecognized value*, with no N or years; the other figure, the chart and the table stay. With every flag null or blank it reads *No figure*. Failure and empty-filter behavior are the same as for *Elections with a different popular-vote winner*.
- **Shown as:** `labels.METRIC_LABELS["ec_no_majority_count"]`; the value through `labels.metric_count` (`labels.METRIC_COUNT_OF`, `labels.METRIC_COUNT_OF_ONE`); `labels.METRIC_NO_FIGURE["ec_no_majority_count"]`; `labels.UNRECOGNIZED`. In `majority-metrics` on `/elections/majority`, the value `majority-ec-no-majority-count`.
- **Source:** #569; D097; D112; `ElectionSummary.ec_determinative`; `METRICS`; reader wording: `ba` spec for #569, approved at its plan gate.
- **Not:** *Electoral College majority*, the yes or no for one election. The leader's electoral share. A count of elections decided by the House. A percentage.
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
- **Plain:** A chart on the Electoral College majority page, one of the Elections pages, with
  election years running left to right, oldest at the left. Each year's marks are for that
  election's Electoral College leader, the candidate with the most electoral votes counted. A circle
  is their electoral share. For the years this dataset has popular-vote figures, a solid triangle is
  their popular-vote share, a thin line joins it to the circle, and a short crossbar on that line,
  halfway between the two, is their hybrid score, the project's own proposal and not an official
  measure. Marks along the top of the chart show a year in which a different candidate won the
  popular vote (an asterisk) or had the highest hybrid score (a pentagon). Years before (or after)
  the popular-vote figures are shaded; shading does not mean no popular vote was held. Hovering over
  or tapping a mark shows its number as the table on the same page writes it. A dashed line across
  the chart marks half of each election's electors appointed; it applies to the electoral share
  only. A leader whose share is more than half had a majority of them. With half or less, no
  candidate had a majority, and the election went to the House of Representatives. A popular-vote
  share under half is not unusual: a candidate can win the popular vote with less than half. The
  leader did not always take office: in 1824 the House chose John Quincy Adams. Its table also says
  whether each leader took office. With no filter, the chart and its table show every election in
  this dataset. A reader can narrow both to a range of years, or to only the years with a popular
  vote in this dataset, which leaves no shaded years.
- **Precise:**
  - Chart ID C2 in `CHARTS` (`dashboard/explore/charts.py`), on `/elections/majority`, element
    id `c2`.
  - Its *Companion table* is `elections-leader-table`, after the chart. Its columns, by public
    field name: `year`, `candidate`, `national_electoral_votes_counted`,
    `national_electoral_denominator`, `ec_share_full`, `ec_determinative` (`labels.ec_majority`),
    `took_office` (`labels.yes_no`), then, appended by #564 (D108(h)): `pv_share`,
    `hybrid_score` (both on T3's year rule, `labels.national_pv`: `labels.NOT_APPLICABLE` where
    the index row's `has_popular_vote` is false, `labels.NO_NATIONAL_FIGURE` for a null inside
    it), `pv_winner`, `hybrid_winner` (`labels.winner` with the popular-vote window).
    `took_office` is in the table only, never drawn; it is there so `labels.C2_TOOK_OFFICE` can be
    checked.
  - It sits after the lede, the section links and the page's year filters, under the page's heading
    (`HEADING` in `pages/elections_majority.py`).
  - Inside its card, between the filters and the chart, the block `majority-metrics` shows the two
    counts (#569).
  - Data: built from `/v1/elections/summary`, filled on first use (declared in `on_miss`, D074(ii))
    and read in the same view as `/v1/elections`. Each year `/v1/elections` serves gets the
    marks of that year's single `data` row with `electoral_rank` 1 (its served `ec_share_full`,
    `pv_share` and `hybrid_score`), with that year's `elections` item's `ec_determinative`,
    `pv_winner`, `hybrid_winner`, `pv_flip` and `hybrid_flip`. A body with a year missing, a
    second rank-1 row, an unserved year, a leader whose slug is not `ec_winner_slug`, or a flip
    that disagrees with the winner it names (null exactly when there is no winner, true exactly
    when the winner is another candidate; D108 as amended) shows the section's unavailable
    state. The index's popular-vote window and each year's `has_popular_vote` must agree, or the
    whole page shows its degraded state.
  - It derives nothing. No mark carries a text label; each hover writes the companion table's
    cells: votes counted and electors appointed, never votes cast (1868: 214 and 294; 1872: 286
    and 366; 2016: 304 and 538).
  - The leader's `pv_share` (solid upward triangle, `triangle-up`) and `hybrid_score` (a short
    horizontal crossbar, `line-ew`, on the connector at the midpoint of the circle and triangle) are
    drawn wherever the cell is a share; a thin connector line joins the triangle to the circle, with
    no hover and no key entry. The crossbar is 10 px wide, a little wider than the circle (7 px) and
    the triangle (8 px), and is drawn last, over the circles, triangles, strip marks and markers, so
    neither the circle nor the triangle can hide it; the chart's key keeps its order (#596, D110).
  - Colors by measure (#593, D109): circle `--chart-ec`, triangle `--chart-pv`, crossbar
    `--chart-hybrid`; the connector `--chart-axis`; the strip marks `--text`. Height 560 px. No
    gridline at 50%, where the majority line is the one dashed line; the 50% tick stays.
  - A strip series per method, at a fixed height above 100%, drawn only where the served
    `pv_flip` / `hybrid_flip` is true, never from a list of years: `asterisk` when the
    popular-vote winner differs, `pentagon` when the hybrid winner differs, each named in the key.
  - The solid upward triangle is C2's alone; C4's open upward triangle means no electors
    appointed (D104(d) as D108 extends it).
  - Bands over the years outside the popular-vote window, from the index's `coverage`
    (`over_time.pv_bands`, shared with C5); the before band's label sits inside the band at its top
    when the band spans at least half the year axis, and otherwise above the plot at the band's left
    edge (only a year filter leaves it that narrow; #596, D110); the after band's above the plot.
  - Election year runs along the bottom as a number, so a gap between served elections is drawn at
    its true width, with a tick every 4, 8, 10, 20 or 40 years, the smallest of those that goes into
    the span of years shown at most five times, so the axis writes at most five ticks (every 40
    years over every served year). The value axis runs up the side, with ticks from 0 to 100% (it
    runs to 112% to hold the strip). The line is horizontal at 0.5 and the test is strict, so a
    point on the line is not a majority. It is drawn under every mark, across the year axis's whole
    range, with no hover. It has no label in the plot: on every view it is the last entry in the
    chart's key, `labels.C2_MAJORITY_KEY`, so a year filter cannot set its words among the marks
    (#596, D110, replacing the in-plot label of D104(e) as D108 amended it).
  - A share or score that is not a finite number draws a marker at zero with no text label, one
    point per label and year (two missing marks of one label in one year share it, their hovers
    joined), in a
    series named by its label (`labels.C2_NO_FIGURE` for no figure in this dataset, or
    `labels.UNRECOGNIZED`), which the chart's key shows, and the caption adds
    `labels.C2_NO_SHARE_NOTE`. A year is never dropped.
  - The key is always shown, above the plot; its last entry is the majority line.
  - The page's year filters (`year_from`, `year_to`, `pv`, the list page's) narrow the chart, its
    companion table and its download alike; with none, every served year shows (#596, D110,
    reversing D096's "no filter"). The bands follow the years shown, so with only the years with a
    popular vote none is drawn. When the filters leave no year, `labels.NO_ELECTIONS_MATCH` takes
    the place of the chart and table, and the filters stay. A failed summary read still shows
    `C2_UNAVAILABLE`.
  - If the summary read fails, the section shows `C2_UNAVAILABLE`, with no chart and no companion
    table, and the page keeps its heading, lede and section links.
- **Shown as:**
  - Placed by `pages/elections_majority.py` through `components.chart`.
  - Chart text in `labels.py`: `labels.C2_TITLE`; the axes `LABELS["year"]` and
    `labels.C2_VALUE_AXIS` (`labels.C2_TITLE_NO_PV` and `labels.C2_VALUE_AXIS_NO_PV` when no year
    shown has popular-vote figures); the band labels `labels.C5_BEFORE_BAND` /
    `labels.C5_AFTER_BAND`; the hovers `labels.C2_HOVER`, `labels.C2_PV_HOVER`,
    `labels.C2_HYBRID_HOVER`, `labels.C2_PV_DIFFERENT_HOVER` and `labels.C2_HYBRID_DIFFERENT_HOVER`;
    the key entries `LABELS["ec_share_full"]`, `LABELS["pv_share"]`, `labels.C2_HYBRID_KEY`,
    `labels.C2_PV_DIFFERENT_KEY` and `labels.C2_HYBRID_DIFFERENT_KEY` (each when drawn),
    `labels.C2_NO_FIGURE` and `labels.UNRECOGNIZED`, shown only when such a marker is drawn, and,
    last on every view, the majority line's entry `labels.C2_MAJORITY_KEY` (#596, D110); the caption
    `labels.C2_LEADER_POINT`, `labels.C2_EC_MARK`, `labels.C1_EC_BASIS`, `labels.C2_PV_MARK`,
    `labels.C2_HYBRID_MARK`, `labels.C2_MAJORITY_NOTE`, `labels.C1_LINE_EC_ONLY`,
    `labels.C2_PLURALITY_NOTE`, `labels.C2_TOOK_OFFICE`, then, each only when drawn,
    `labels.C2_BEFORE_NOTE`, `labels.C5_AFTER_NOTE`, `labels.C2_PV_DIFFERENT_NOTE`,
    `labels.C2_HYBRID_DIFFERENT_NOTE` and `labels.C2_NO_SHARE_NOTE`, then
    `labels.CHART_TABLE_POINTER`.
  - In `pages/elections_majority.py`: `HEADING` (the page's, formerly C2's section heading), `LEDE`,
    `FILTER_SENTENCE` (success only, after `LEDE`), the filters' `labels.YEARS_FILTER` and
    `labels.PV_ONLY_FILTER`, `labels.NO_ELECTIONS_MATCH`, `labels.METRIC_PV_WINDOW_NOTE`,
    `C2_TABLE_HEADING`, the companion table's
    columns (existing `LABELS` keys), the table notes `labels.C2_LEADER_ROW`,
    `labels.C2_TOOK_OFFICE`, `labels.C2_TABLE_METHODS_NOTE`, `labels.HYBRID_NOTE` and
    `labels.C2_HYBRID_TABLE_NOTE`, the download "the Electoral College leaders"
    (`elections-electoral-college-leaders.csv`), and `C2_UNAVAILABLE`.
- **Source:** #434 acceptance criteria (the counted basis: owner, 2026-11-05); #564 acceptance
  criteria; `CHARTS`; `NationalSummaryRow.ec_share_full`, `pv_share`, `hybrid_score`,
  `electoral_rank`, `national_electoral_votes_counted` and `national_electoral_denominator`,
  `ElectionSummary.ec_determinative`, `pv_winner`, `hybrid_winner`, `pv_flip`, `hybrid_flip` and
  `AllElectionsSummaryResponse` in `src/usvote/api/models.py`; D041; D046 §4; D091; D093; D096;
  #558; D104; #562; D107; D108; #596 (owner decisions, 2026-11-20); D110; `ba` spec for #596;
  `posts/2026-08-18-presidential-elections-are-messy.md` (Jackson 99 of 261, 37.9 percent; the House
  chose John Quincy Adams); `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "The one time it
  happened"; the 1992 example (William J. Clinton, 43.0%) checked against served N1; reader wording:
  `ba` spec for #434, approved at its plan gate (2026-11-11), with its historical claims, and `ba`
  spec for #564, approved at its plan gate (2026-11-19); #593; D109; `ba` spec for #593; the
  majority line named in the key rather than labeled in the plot: owner decision at #596's plan gate
  (2026-11-20), D110.
- **Not:** A chart of winners: in 1824 the leader had no majority. The chart does not show who took
  office (*Took office*); its companion table does. Not votes cast. The line is not a fixed number
  such as 270. The crossbar (the hybrid score) is not an official measure. A strip mark is not a correction or recount:
  it says only who came first under that method. Shading is not "no popular vote". Not a
  stand-in for its companion table. A marker is not a zero.
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
  popular-vote figures, `labels.C1_LINE_EC_ONLY`. In C2, the dashed line, named in the chart's key
  by `labels.C2_MAJORITY_KEY` (#596, D110), the caption sentence `labels.C2_MAJORITY_NOTE`, the
  hover's last line (`labels.ec_majority`), the companion table's column, the Electoral College
  majority page's heading (`HEADING` in `pages/elections_majority.py`) and its section link
  `labels.SECTION_MAJORITY`; `labels.C1_LINE_EC_ONLY` in C2's caption; on the same page, the count
  *Elections with no Electoral College majority* (`labels.METRIC_LABELS["ec_no_majority_count"]`).
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
  `ec_share_hybrid` is on no dashboard page and in no download since #358; the API serves it. In C2, the circle series `LABELS["ec_share_full"]`, in the chart's key; the title `labels.C2_TITLE`; the value axis `labels.C2_VALUE_AXIS`; the hover `labels.C2_HOVER` (its share line is `labels.share_cell`; no mark carries text); the key entry `labels.C2_NO_FIGURE` for a missing electoral share (#564; formerly `labels.C1_NO_SHARE`); and the caption sentences `labels.C2_EC_MARK`, `labels.C1_EC_BASIS` and, when a marker is drawn, `labels.C2_NO_SHARE_NOTE`.
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
  Electoral-share bars `--chart-ec`, popular-vote bars `--chart-pv` (#593).
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
- **Shown as:** `LABELS["electoral_votes"]`, `LABELS["national_electoral_votes"]`. On
  `/candidate/<slug>`, `national_electoral_votes` is added up over the elections shown in
  `labels.METRIC_LABELS["candidate_ev_cast_total"]`, and on `/state/<usps>` the took-office row's
  `electoral_votes` decides `labels.METRIC_LABELS["state_took_office_count"]`. On `/elections`,
  each recipient's cast number in T1's Recipients column and C9's hover (`labels.RECIPIENT_LINE`;
  *Recipients*).
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
  On `/candidate/<slug>`, `labels.METRIC_LABELS["candidate_ev_counted_total"]`. On `/elections`,
  each recipient's counted number in T1's Recipients column and C9's hover
  (`labels.RECIPIENT_LINE`; *Recipients*).
- **Source:** `EcPvRow.electoral_votes_counted`; `count_status.COUNTED_VOTES_COLUMN`; D046;
  `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "Then there is a third number".
- **Not:** *Electoral votes cast.*
- **Status:** settled

### Electoral votes outside the top two (`electoral_votes_outside_top_two`)
- **Plain:** In one election, how many electoral votes were cast for candidates who finished
  below second place.
- **Precise:** `electoral_votes_outside_top_two` on `ElectionSummary`: the sum of
  `national_electoral_votes` (cast) over the year's candidates whose `electoral_rank` is 3 or
  more. Rank is ordered by votes counted and candidates with equal counted totals share a rank, so
  a tie at second leaves every tied candidate inside the top two, and a tie at first makes the next
  candidate second. The sum adds votes cast: 1872 is 24, including Greeley's 3 cast and 0
  counted (he ranks below second). Computed when the data file is built, never by the API at
  request time. A whole number for every year served; 0 is a real value.
- **Shown as:** on the API's `/docs` page, the `ElectionSummary.electoral_votes_outside_top_two`
  field description in `src/usvote/api/models.py`, and the sentence in the `ElectionSummary`
  class docstring that says it is never null; served on each `elections` item of
  `/v1/elections/summary` and in `election` on `/v1/elections/{year}` and
  `/v1/elections/{year}/summary`. On `/elections`, `LABELS["electoral_votes_outside_top_two"]`
  (T1, #563), with the note `OUTSIDE_TOP_TWO_NOTE` under T1 and in its download
  (`pages/elections.py`).
- **Source:** #570 (figure approved by the owner, 2026-11-17); `ElectionSummary` in
  `src/usvote/api/models.py`; the build in `src/usvote/snapshot.py`; D046 §4; D094(iv); reader
  wording: `ba` spec for #570, approved at its plan gate; T1's label and `OUTSIDE_TOP_TWO_NOTE`:
  `ba` spec for #563, approved at its plan gate (2026-11-22).
- **Not:** A sum of votes counted. A ranking by votes cast. "Third-party votes": rank, not party,
  decides who is outside. The candidates' number (*Candidates with electoral votes*).
- **Status:** settled; wording pending (the historical claim in `OUTSIDE_TOP_TWO_NOTE` awaits the owner's check)

### Electors appointed and total popular vote over time (charts C4 and C5)
- **Plain:** Two charts on their own page, one of the Elections pages, with election years running
  left to right, oldest at the left. Each bar is one election, for all states together. The first
  chart shows the whole Electoral College's electors appointed, and the second the national total
  popular vote. Where there is nothing to draw, a marker stands in the bar's place, never a bar of
  zero length, and the chart's key says what each kind of marker means. In the second chart, the
  shaded years are those before this dataset's popular-vote figures begin; shading does not mean no
  popular vote was held. Hovering over or tapping a bar or marker shows its numbers, and one table
  on the page holds both charts' numbers. With no filter they show every election in this dataset; a
  reader can narrow the charts and the table together to a range of years, or to the years with a
  popular vote in this dataset. The second chart writes the numbers up its side short ("150M" is 150
  million); its hover and the table give them in full. A state's own electors appointed and total
  popular vote are on that state's page (charts C7 and C10).
- **Precise:**
  - C4 and C5 are in `CHARTS` on `/elections/over-time`, ids `c4` and `c5`, sharing one companion
    table. They sit under the page's heading (`HEADING`), after the section links and the page's
    year filters, stacked, C4 above C5, with the same fixed left and right margins so their year
    axes line up, and the table below.
  - C4 `--chart-ec` (red), C5 `--chart-pv` (blue) (#593, D109).
  - C7 draws one state's series of electors appointed on that state's history page
    (*State's electors appointed over time*).
  - C4 reads the N1 `elections` items' `electoral_denominator`. C5 reads each year's one distinct
    `national_pv_denominator` across N1's `data` rows; two distinct values make the section
    unavailable. The dashboard adds nothing up.
  - A bar is drawn where the cell is a figure and, in C4, above zero. A zero allotment is a marker
    (the D091 exception, D100). Every other value is a marker at zero. There is one series per
    label, each with its own symbol and named in the chart's key; no bar or marker carries a text
    label (D104). In C5 the band alone marks a year outside the popular-vote window, which gets
    no marker; every other cause gets a marker wherever it falls, inside the band included.
  - Both charts put election year on one numeric axis along the bottom (D100(a) as amended by D104
    and D107), with a tick every 4, 8, 10, 20 or 40 years, the smallest of those that goes into the
    span of years shown at most five times, so the axis writes at most five ticks (every 40 years
    over every served year). The value axis runs up the side: C4's ticks are full numbers; C5's are
    short (d3's SI form with trailing zeros trimmed, `~s`: "0, 50M, 100M, 150M"), one of the chart
    rule's two exceptions, with C10 (C5's `CHARTS` row, `short_value_ticks`, #596, D110; C10's,
    #582, D113), and with no bar drawn C5 writes no value ticks. Their shared left margin is sized
    for C5's short ticks. C5's band is vertical, spanning the years outside the window, and its
    label sits inside the band at its top when the band spans at least half the year axis, and
    otherwise above the plot at the band's left edge (only a year filter leaves it that narrow;
    #596, D110), beginning "Shaded:"; the after band's label, where drawn, sits above the plot. The
    key sits above the plot.
  - The band's bounds come from `meta.provenance.coverage`. Hover text is the table's cells.
  - If `/v1/elections/summary` cannot be read or is malformed, the section shows
    `OVER_TIME_UNAVAILABLE` only; the section links, heading and lede still show.
  - The one-state mode (D100(a), (c), (e), (f)) retired with #562 (D107).
- **Shown as:** `HEADING`, `LEDE`, `OVER_TIME_TABLE_HEADING`, `OVER_TIME_UNAVAILABLE` and the
  download "electors appointed and the total popular vote, all states"
  (`elections-electors-and-popular-vote-all-states.csv`) in `pages/elections_over_time.py`; the
  section link `labels.SECTION_OVER_TIME`; `FILTER_SENTENCE` (success only, after `LEDE`); the
  filters' `labels.YEARS_FILTER` and `labels.PV_ONLY_FILTER`; `labels.NO_ELECTIONS_MATCH`;
  `labels.C5_SHORT_TICKS_NOTE`; `C4_*`, `C5_*` and `NO_NATIONAL_TOTAL` in `labels.py`;
  `LABELS["year"]` (the year axis); then `labels.CHART_TABLE_POINTER`.
- **Source:**
  - #436 ACs (owner, 2026-11-05);
  - decisions D091, D093, D096, D100 and D107;
  - #593; D109;
  - #596 (owner decisions, 2026-11-20); D110; the ba spec for #596;
  - #558; D104; #562;
  - `ElectionSummary.electoral_denominator` and `NationalSummaryRow.national_pv_denominator`;
  - posts 2026-08-18 (messy), 2026-08-25 (270 of what) and 2026-08-06 (222 votes away);
  - the ba specs for #436 and #562; the zero allotments and legislature-chosen years are tabled
    with their citations in `docs/pv-coverage.md`.
- **Not:**
  - electoral votes cast or counted;
  - turnout;
  - a candidate's popular votes;
  - one state's figures (C7 and C10, on the state's page);
  - "no popular vote", which the band is not;
  - a missing figure, which a C4 zero-allotment marker is not;
  - a zero, which a C5 marker is not.
- **Status:** settled

### Electors without a counted vote (`electors_without_a_counted_vote`)
- **Plain:** In one election, how many of the electors appointed have no vote in Congress's
  final count, either because they never voted or because their vote was cast but not counted.
- **Precise:** `electors_without_a_counted_vote` on `ElectionSummary`: `electoral_denominator`
  minus the year's electoral votes counted, added up over its candidates. It spans both gaps of
  the ladder appointed ≥ cast ≥ counted: votes never cast (`ELECTORAL_VOTE_SHORTFALLS`: 1832
  Maryland 2, 1864 Nevada 1, 2000 District of Columbia 1) and votes cast whose count status is
  `not_counted` or `disputed` (1868: 9, Georgia, disputed; 1872: 17, not counted). A state with
  no electors appointed (1864, 1868) adds nothing. Computed when the data file is built; a whole
  number for every year served; 0 is a real value.
- **Shown as:** on the API's `/docs` page, the `ElectionSummary.electors_without_a_counted_vote`
  field description in `src/usvote/api/models.py`, and the sentence in the `ElectionSummary`
  class docstring that says it is never null; served where *Electoral votes outside the top
  two* is. On `/elections`, `LABELS["electors_without_a_counted_vote"]` (T1, #563), with the note
  `NO_COUNTED_VOTE_NOTE` under T1 and in its download (`pages/elections.py`).
- **Source:** #570 (figure approved by the owner, 2026-11-17); `ElectionSummary`;
  `ELECTORAL_VOTE_SHORTFALLS` and the count-status overrides in `src/usvote/transform.py`; D041;
  D044; D046; reader wording and the name: `ba` spec for #570, approved at its plan gate; T1's
  label and `NO_COUNTED_VOTE_NOTE`: `ba` spec for #563, approved at its plan gate (2026-11-22).
- **Not:** The `not_counted` count status, which is only part of the second gap. "Electors not
  counted": electors are appointed, votes are counted. Faithless votes, which are cast and counted.
- **Status:** settled; wording pending (the historical claim in `NO_COUNTED_VOTE_NOTE` awaits the owner's check)

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
  test as `labels.ec_winner_label` (winner only on a true majority, otherwise leader). In C2 (#564), a strip series per method above the data, from the served flag: `asterisk`, `labels.C2_PV_DIFFERENT_KEY`; `pentagon`, `labels.C2_HYBRID_DIFFERENT_KEY`; their hovers and `labels.C2_PV_DIFFERENT_NOTE` / `labels.C2_HYBRID_DIFFERENT_NOTE`. On `/elections/majority`, the count *Elections with a different popular-vote winner* (`labels.METRIC_LABELS["pv_flip_count"]`).
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
  `pv_coverage` flags a year whose popular vote covers only some states. In reader text, "the
  project" names who proposes the hybrid: the people behind this site, its dataset and the
  "Counted, Not Assumed" series. It is the only reader-facing use of the word; any other use needs
  a `ba` spec.
- **Shown as:** `LABELS["hybrid_score"]`, `LABELS["hybrid_winner"]`, `LABELS["hybrid_margin"]`,
  `LABELS["hybrid_flip"]`; help text `labels.HYBRID_NOTE` (panel, and under T3 and in its
  download's preamble, and under C2's companion table); in C2 (#564, #593), the crossbar
  (`labels.C2_HYBRID_KEY`, `labels.C2_HYBRID_HOVER`, `labels.C2_HYBRID_MARK`), its strip series
  (`labels.C2_HYBRID_DIFFERENT_KEY`, `labels.C2_HYBRID_DIFFERENT_HOVER`,
  `labels.C2_HYBRID_DIFFERENT_NOTE`), its table columns `hybrid_score` and `hybrid_winner`, and
  `labels.C2_HYBRID_TABLE_NOTE`.
- **Source:** `NationalSummaryRow.hybrid_score`; `ElectionSummary.hybrid_winner`; D037; D038;
  D108; `docs/pv-coverage.md`; "the project's proposal": owner decision at #564's plan gate,
  2026-11-19.
- **Not:** A forecast, an endorsement or an official measure. Help text says what it computes and
  nothing about its merits (`labels.HYBRID_NOTE` comment). Where a chart draws it (C2), its key,
  hover and caption call it the project's proposal (D108). Argument for it belongs only in a
  clearly labeled opinion tab (#275, E9-S7).
- **Status:** settled

### Lowest and highest people per electoral vote (figures)
- **Plain:** On a state's People per electoral vote page: the fewest and the most people one of the state's electoral votes stood for, among the elections in the years shown, each with the election or elections that hold it, and how many elections have a figure.
- **Precise:** `metrics.select` over (year, `persons_per_electoral_vote`) pairs from T7's shown rows (the page's year range, D112(g)), picking `lowest` and `highest`. N is the number of those rows whose value is not null or blank; a null or blank (no census figure, or a zero allotment) is left out whatever its cell reads, even a cell that reads *Unrecognized value* (an unknown `coverage` code on a null figure), since that cell names why the figure is missing, not a value; it is never an extreme and N does not count it. A tie names every year that holds it, joined "1824 and 1828" or "1852, 1856 and 1860". The value is T7's own cell (`labels.per_capita_strings`), to a whole person. With N = 1 the lowest names its one year and the highest reads `labels.METRIC_SELECT_SAME`. Any other value `labels.finite` refuses, or any value whose own T7 cell reads *Unrecognized value* (a figure of zero or less), whichever year holds it, makes both figures read *Unrecognized value* with no N or years, since they share one selection; T7 and the page stay. With N = 0 it reads *No figure*: `labels.METRIC_NO_FIGURE_NO_ELECTIONS` when the range holds no row, otherwise `labels.METRIC_NO_FIGURE["state_per_capita_lowest"]`. Never a difference, ratio or percentage change (D112(d)).
- **Shown as:** `labels.METRIC_LABELS["state_per_capita_lowest"]` and `["state_per_capita_highest"]`; the value through `labels.metric_select` (`labels.METRIC_SELECT`, `labels.METRIC_SELECT_ONE`, `labels.METRIC_SELECT_SAME`, with `labels.METRIC_SELECT_OTHER`, the word "lowest" it names, the tie join `labels.METRIC_YEARS_AND`); `labels.METRIC_NO_FIGURE_NO_ELECTIONS`; `labels.METRIC_NO_FIGURE["state_per_capita_lowest"]`; `labels.UNRECOGNIZED`. On `/state/<usps>/per-capita`, in `state-per-capita-metrics` inside the page's card, after the year control and before the count line (`pages/state_per_capita.py`).
- **Source:** #569; #600; D112(d), (g) and its addendum; `PerCapitaRow.persons_per_electoral_vote`; `METRICS`; reader wording: `ba` spec for #600, approved at its plan gate.
- **Not:** A ranking of states. A claim about whose vote counts more. The lowest or highest across states in one election (a different grain, which would need its own keys).
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
  `/elections` (*Average margin*). On `/elections`, T1's `ec_margin` and `pv_margin` columns
  (#563), whose cells come from `election_view.margin_cells`, the election panel's own cell
  function, so a year reads the same in both (D116(f)); a popular-vote margin outside the
  popular-vote window reads `labels.NOT_APPLICABLE`. `labels.MARGIN_NOTE` is also the last of
  T1's notes, so it shows twice on that page (kept with the #563 spec, approved at its plan gate).
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
  T2–T5 (`labels.PARTY_NOTES_HEADING`, `labels.PARTY_NOTE_ITEM`), shown as served, and not shown
  when it has nothing to read (it is not text, is blank, or is made only of whitespace, formatting
  or control characters, such as a zero-width space; #532);
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
  this dataset*, a candidate's missing popular-vote count. *Unrecognized value*. *No figure*, a
  count's. The "no figure" of D097's rule for a sum, whose reader wording a later spec sets.
- **Status:** settled

### No elections match (an empty filter result)
- **Plain:** What a page says when the filters leave no election, for example
  only the years with a popular vote in this dataset together with a range of years that ends
  before those years begin. It is about the filters, not the data: widening the years, or
  clearing the popular-vote checkbox, brings elections back (on a state's history page, widening
  the years does).
- **Precise:** On `/elections`, it stands in T1's place; the count line reads 0 of all elections
  and each average reads `labels.METRIC_NO_AVERAGE_FILTERS`. On `/elections/majority` and
  `/elections/over-time`, it is one note in place of the chart or charts, their companion table
  and its download; the heading, lede, filter sentence, section links, filters and provenance
  footer stay, and the page keeps its success marker. A failed summary read shows that section's
  unavailable sentence instead. On `/state/<usps>`, it stands in place of C7, C10 and their table
  when the Years filter leaves no election (for example 1849–1851 for Texas); the heading, lede,
  filter sentence, slider, section links, headline figures with `labels.METRIC_ALL_YEARS_NOTE`, and
  footer stay, and the page keeps its success marker.
- **Shown as:** `labels.NO_ELECTIONS_MATCH` (T1's empty text in `pages/elections.py`, and the note
  on the two chart pages); `labels.STATE_NO_ELECTIONS_IN_RANGE` (`/state/<usps>`, #620).
- **Source:** #596 acceptance criteria (owner, 2026-11-20); D110; `ba` spec for #596; T1's empty
  text since #306; #620 and D119 (the state history's form; `ba` spec for #620, approved at its
  plan gate).
- **Not:** *Degraded state*. *Not-found state*. `components.NO_ROWS`, which other tables show
  ("rows"). *No average*. "No data": the elections are in this dataset; the filters leave none shown.
- **Status:** settled

### No figure (a figure with no election to include)
- **Plain:** The page shows no number because none of the elections shown can enter it. Either all of them fall in years this dataset has no popular-vote figures for, or this dataset has no value for any of them, or, on a state's page, the years shown hold no election for that state, or this state appointed electors in no election, or, for a candidate's total, one or more of the elections shown has no number. It is not zero: a count of zero shows 0.
- **Precise:** `labels.metric_count`, `labels.metric_select`, `labels.metric_total` or `labels.metric_elections` with no unrecognized value and no value to show. Causes are checked in order. First, on a state's People per electoral vote page, no row in the year range (`labels.METRIC_NO_FIGURE_NO_ELECTIONS`). On a state's history page, no year with an allotment above 0 (`labels.METRIC_NO_FIGURE_NO_ELECTORS`, both figures). On a candidate's page, no election (`labels.METRIC_NO_FIGURE_NO_CANDIDATE_ELECTIONS`, defensive). Then, for a figure read against the popular-vote window, no year shown inside the window of `meta.provenance.coverage` (`labels.METRIC_NO_FIGURE_PV_YEARS`). Otherwise the value is null, worded per metric key (`labels.METRIC_NO_FIGURE`): a count or select is null when every value is null, a sum when any year is (D097), which is why its wording says "one or more". On the elections pages no year shown is not a cause: the page shows *No elections match* and no figure. It is never 0, "nan" or an empty cell.
- **Shown as:** `labels.METRIC_NO_FIGURE_NO_ELECTIONS`, `labels.METRIC_NO_FIGURE_NO_ELECTORS`, `labels.METRIC_NO_FIGURE_NO_CANDIDATE_ELECTIONS`, `labels.METRIC_NO_FIGURE_PV_YEARS`, and `labels.METRIC_NO_FIGURE` (keyed by metric key), through `labels.metric_count`, `labels.metric_select`, `labels.metric_total` and `labels.metric_elections`.
- **Source:** #569 acceptance criteria; D097; D112; #601; D115; reader wording: `ba` specs for #569, #600 and #601.
- **Not:** Zero. *No average* (a mean). *No popular-vote figure in this dataset* (a cell). *Unrecognized value*.
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
  shown only when such a marker is drawn; `labels.NO_NATIONAL_TOTAL` and `labels.C5_NO_TOTAL`
  (the C4/C5 table and C5); `labels.NO_STATE_TOTAL` (the state history's table of electors appointed and total popular vote) and `labels.C5_NO_TOTAL`
  (C10's key, through `labels.C10_MARKER_LABELS`, #582, which also gives it to a total with no
  status, *Not in this dataset*). In C2 (#564): `labels.NO_NATIONAL_FIGURE` in the companion table's `pv_share` / `hybrid_score` cells and in the triangle's and crossbar's marker hovers.
- **Source:** `EcPvRow` docstring and `pv_status` description; `NationalSummaryRow` docstring;
  `.claude/specs/backlog-dashboard.md`, E9-S3 null table;
  `posts/2026-08-18-presidential-elections-are-messy.md`, "One empty cell, five different
  histories" (a number the record does not carry is not a zero).
- **Not:** Zero popular votes.
- **Status:** settled

### Not available right now (a cell)
- **Plain:** A cell this page could not read just now. It is not a value: the dataset may well
  hold one, and trying again in a minute may show it. Different from *Not in this dataset*.
- **Precise:** One string, `labels.UNAVAILABLE_CELL` (moved from `T1_N1_UNAVAILABLE_CELL`,
  `pages/elections.py`, unchanged), in every cell of a column whose source could not be read or
  checked in this render. Its uses, each with the note it comes with or none: on `/elections`
  (#563, D116(e)), in tier 1 (N1 cannot be read or fails its checks), all five of T1's N1
  columns, with `T1_N1_UNAVAILABLE_NOTE` first among T1's notes, which names the five columns and
  says that in the download the four of them it carries have empty cells because they were not
  read right now, not because the dataset holds no value there; on `/elections`, in tier 2 (a
  recipient row fails its check, or a year's rows do not match its `candidate_count`), T1's
  Recipients column only, with no note, since Recipients is shown on the page only and has no
  download column; and on `/state/<usps>` (#618, D117), the electors column or the total popular
  vote column of the table C7 and C10 share, each with its own note first among the table's
  (`ELECTORS_UNAVAILABLE_NOTE`, `TOTALS_UNAVAILABLE_NOTE`), which names the column and says that
  in the download its cells are empty because they were not read, not because the dataset has
  no value.
- **Shown as:** `labels.UNAVAILABLE_CELL`; the notes `T1_N1_UNAVAILABLE_NOTE` (`pages/elections.py`,
  tier 1 only; tier 2 has no note), `ELECTORS_UNAVAILABLE_NOTE` and `TOTALS_UNAVAILABLE_NOTE`
  (`pages/state.py`).
- **Source:** #563 (owner decision at its plan gate, 2026-11-22); #618 (owner's ruling,
  2026-11-23); reader wording: `ba` spec for #618, approved by the owner at its plan gate
  (2026-11-23).
- **Not:** *Not in this dataset* (the dataset has no value). *Unrecognized value* (a value the page
  has no label for). Zero. The *Degraded state* (the whole page).
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
  `labels.NOT_IN_DATASET` names, in the chart's key, the series of markers drawn in place of a bar
  for a null allotment, with `labels.C4_NO_FIGURE_NOTE` in the caption; its hover
  (`labels.C4_HOVER` or `labels.C4_STATE_HOVER`) writes the same cell. In C2 (#564): `labels.C2_NO_FIGURE`, C2's one open-circle key entry for any missing share or score, and `labels.C2_NO_SHARE_NOTE`. In C10 (#582),
  `labels.NOT_IN_DATASET` is the table cell, and its hover's, for a total with no status to
  explain it; the chart's key names that marker `labels.C5_NO_TOTAL`, the same entry as a
  missing total inside the window.
- **Source:** the comments on `NOT_IN_DATASET` and `_closed_value` in `labels.py`;
  `dashboard/CLAUDE.md`, `components.py`, `labels.py` (the "never No" rule);
  `.claude/specs/backlog-dashboard.md`, "Carry-forward constraints"; #348 acceptance criteria.
- **Not:** "No", which is a recorded negative. Zero. "Not held". *Unrecognized value*, where the
  dataset does hold something.
- **Status:** settled; wording pending (#375: whether the CSV preamble's last line,
  `export.NULL_LINE`, keeps the word "null")

### Not-found state (a link the dataset does not serve)
- **Plain:** What a page says when its link names a year, a state code or a candidate link this
  dataset does not serve, or, on an election's or a state's pages, a section the site does not
  have. Its heading
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
  `labels.ELECTION_NOT_FOUND_SENTENCE` on the three election pages,
  `labels.STATE_NOT_FOUND_SENTENCE` on the three state pages, and `NOT_FOUND_SENTENCE` in
  `pages/candidate.py`. A percent-encoded link
  is read as the link it spells once decoded, as Dash's router reads it, so it gets whatever that
  link gets: `/election%2F1825` gets this state, with the same status and title, just as
  `/election/1825` does. `/election/18%32%34` is not a not-found link at all: it opens 1824, with
  `/election/1824` as its canonical link (D089). On the election pages, the overview and both
  subpages (`/election/1825/states`) share one heading and sentence, and so does a link naming a
  section the site does not have (`/election/1824/x`), which reaches the overview: the sentence is
  about the link, so it holds whether the year or the section is what the site does not have. On
  the state pages, all three (`/state/ZZ`, `/state/ZZ/elections`, `/state/ZZ/per-capita`) and a
  link naming a section the site does not have (`/state/GA/x`) share one heading and sentence.
- **Shown as:** `labels.ELECTION_NOT_FOUND_HEADING` and `labels.ELECTION_NOT_FOUND_SENTENCE` for
  the three election pages, `labels.STATE_NOT_FOUND_HEADING` and `labels.STATE_NOT_FOUND_SENTENCE`
  for the three state pages, and `NOT_FOUND_HEADING` and `NOT_FOUND_SENTENCE` in
  `pages/candidate.py`; the links "Browse every election in the dataset"
  (`labels.ELECTION_NOT_FOUND_LINK`, built by `election_view.not_found`), "Browse every state in
  the dataset" (`labels.STATE_NOT_FOUND_LINK`, built by `state_view.not_found`) and
  `NOT_FOUND_LINK` in `pages/candidate.py`; the title on a not-found link,
  built in `dashboard/explore/app.py` from the heading and `config.SITE_TITLE`.
- **Source:** D073; D074; D083; D089 (a percent-encoded link is matched after decoding);
  `dashboard/CLAUDE.md`, `pages/`; the heading and title: #325;
  their reader wording: owner decision, 2026-11-01, #325; the state pages' shared sentence: #559.
- **Not:** *Degraded state*; *Page not found*, a link that matches no page at all; an empty filter
  result (`components.NO_ROWS`; on the three elections pages, `labels.NO_ELECTIONS_MATCH`; *No
  elections match*).
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
  (`labels.BEFORE_WINDOW`, `labels.AFTER_WINDOW`). C2's leader table follows T3's rule (`has_popular_vote`, #564).
- **Shown as:** `labels.NOT_APPLICABLE` (panel; T3 and C2's leader table through
  `labels.national_pv`, called from `pages/election.py` and `pages/elections_majority.py`);
  `NO_PV_SENTENCE` in `pages/election.py` above T3; in C1, where no popular-vote bar is drawn, the
  title `labels.C1_TITLE_NO_PV` and the caption sentence `labels.C1_NO_PV_CAPTION`;
  `labels.NOT_APPLICABLE` as the national total's cell outside the window (the C4/C5 table); C5's
  band (vertical, over the years outside the window) and its labels `labels.C5_BEFORE_BAND`, inside
  the band at its top (above the plot when a year filter leaves the band under half the axis, #596),
  and `labels.C5_AFTER_BAND`, above the plot, with `labels.C5_BEFORE_NOTE` and
  `labels.C5_AFTER_NOTE`. In C2 (#564): the bands (`labels.C5_BEFORE_BAND` / `labels.C5_AFTER_BAND`,
  reused), `labels.C2_BEFORE_NOTE`, `labels.C5_AFTER_NOTE`, and `labels.NOT_APPLICABLE` in its four
  appended columns. In C10 (#582): the bands `labels.C5_BEFORE_BAND` / `labels.C5_AFTER_BAND`, with
  `labels.C5_BEFORE_NOTE` and `labels.C5_AFTER_NOTE`. Its table names the window's side
  (`labels.BEFORE_WINDOW`, `labels.AFTER_WINDOW`), as T4 does.
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

### Pages for all elections (list of elections, Electoral College majority, electors appointed and total popular vote)
- **Plain:** The Elections part of the site has three pages: the list of elections, with filters,
  the average margins and a chart of how many candidates received electoral votes in each
  election; the Electoral College majority page, a chart and table of whether each
  election's Electoral College leader won more than half of the electors appointed; and the electors
  appointed and total popular vote page, two charts and a table of those totals in every election,
  for all states together. Links near the top of each page go between the three, and the page being
  read is marked. On each of the three, a reader can narrow the years shown, or show only the years
  with a popular vote in this dataset, and the links between the pages keep that choice. The
  majority page also shows, where this dataset has popular-vote figures, the leader's popular-vote
  share and the hybrid score the project proposes.
- **Precise:** Three registered pages. `/elections` (`pages/elections.py`): C9, T1, their
  year-range and popular-vote filters, the count of elections shown and the averages; it reads
  `/v1/elections` and N1. T1's eight columns, in order: `year`, `candidate_count`,
  `has_popular_vote`, `electoral_votes_outside_top_two`, `electors_without_a_counted_vote`,
  `ec_margin` and `pv_margin` (the seven served fields, `FIELDS`), then *Recipients*, on the page
  only (`PAGE_ONLY`, D116(a)). `/elections/majority` (`pages/elections_majority.py`): C2 and `elections-leader-table`; it
  reads N1 and has the same year-range and popular-vote filters as `/elections`.
  `/elections/over-time` (`pages/elections_over_time.py`): C4, C5 and their one table, all states
  only; it reads N1 and has the same filters. On a successful render each page carries the section
  links, a landmark named `labels.ELECTIONS_SECTIONS_LABEL`; the page being read is text marked
  `aria-current="page"`, and the others are links that open without reloading the page and carry the
  filters the render applied (`year_from`, `year_to`, `pv`), as a state's results by election and
  people per electoral vote pages carry the year range (D105, D118). The three pages share one filter parser and one filter callback
  (`elections_view.py`). When the filters leave no election, `/elections` shows
  `labels.NO_ELECTIONS_MATCH` in place of C9 and T1 and each chart page shows it in place of its charts and
  table; the filters and section links stay. A failed N1 degrades only the sections that read it. An
  old `/elections?state=<usps>` link answers 302 to `/state/<usps>` when the state roster in memory
  accepts the code; otherwise `/elections` is served with the key ignored. An old `/elections#c2`,
  `#c4` or `#c5` link lands on `/elections`, without its chart, because the part after `#` never
  reaches the server.
- **Shown as:** the section links `labels.SECTION_ELECTIONS_LIST`, `labels.SECTION_MAJORITY`,
  `labels.SECTION_OVER_TIME` and the landmark name `labels.ELECTIONS_SECTIONS_LABEL` (read by
  assistive technology, not shown); on `/elections`, the H1 "Elections" (a literal), `LEDE`,
  `FILTER_SENTENCE` (success only), `LIST_HEADING`, `RECIPIENTS_HEADER`, T1's notes in order
  (`T1_N1_UNAVAILABLE_NOTE` first in tier 1 only, then `labels.HAS_POPULAR_VOTE_NOTE`,
  `RECIPIENTS_DOWNLOAD_NOTE`, `OUTSIDE_TOP_TWO_NOTE`, `NO_COUNTED_VOTE_NOTE` and
  `labels.MARGIN_NOTE`), C9's wording (*Candidates with electoral votes chart (C9)*), the title
  and description; on
  `/elections/majority` and `/elections/over-time`, `HEADING`, `LEDE`, `FILTER_SENTENCE` (success
  only), the title and description in each page's module; on all three, the filters'
  `labels.YEARS_FILTER` and `labels.PV_ONLY_FILTER` and the empty note `labels.NO_ELECTIONS_MATCH`.
  `elections_view.py` ships no wording of its own.
- **Source:** #562 (owner agreement at the 2026-11-17 review); D092 (the subpage pattern); D107;
  reader wording: `ba` spec for #562, approved at its plan gate (2026-11-19); `LEDE` and description on `/elections/majority`: `ba` spec for #564, approved at its plan gate (2026-11-19); #596 (owner decisions, 2026-11-20); D110; reader wording: `ba` spec for #596; C9 and T1's N1 columns: #563, D116; reader wording: `ba` spec for #563, approved at its plan gate (2026-11-22).
- **Not:** *Election pages* (one election's three pages). *Site navigation*. A filter: the section
  links change the page, not the rows; the filters they carry are the reader's own.
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
  `labels.NO_ELECTORAL_VOTES`; on a state's People per electoral vote page
  (`/state/<usps>/per-capita`, *State pages*), its `PER_CAPITA_HEADING` and
  `PER_CAPITA_GENERIC_HEADING`, the notes `labels.GOVERNING_CENSUS_NOTE` and `labels.BOUNDARY_NOTE`
  under T7, and T7's download, named "people per electoral vote" in the file
  `state-{usps}-per-capita.csv`, whose view link is the subpage with the year range only; the per-capita
  page's `PER_CAPITA_HEADING` and `PER_CAPITA_GENERIC_HEADING` (`pages/election_per_capita.py`), and
  T6's download there, named "people per electoral vote" in the file
  `election-{year}-per-capita.csv` (`_download`); the section link `labels.SECTION_PER_CAPITA`, on
  the election pages and the state pages. In
  C3 (*People per electoral vote chart (C3)*), the titles `labels.C3_TITLE` and
  `labels.C3_TITLE_NO_CENSUS`, the axis title (`LABELS["persons_per_electoral_vote"]`), each bar's
  text (T6's cell), the hover text `labels.C3_BAR_HOVER` and `labels.C3_NO_FIGURE_HOVER`, the marker
  label `labels.C3_NO_ELECTORAL_VOTES` with `labels.NO_ELECTORAL_VOTES` in its hover, and the
  caption sentences `labels.C3_RATIO` and `labels.C3_NO_FIGURE_NOTE`. On a state's People per electoral vote page, the figures `labels.METRIC_LABELS["state_per_capita_lowest"]` and `["state_per_capita_highest"]` (*Lowest and highest people per electoral vote*).
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
  for every other row. Both are `--chart-ec`, red, the color of values derived from electoral
  votes (owner, #593's plan gate). The stripes mean present-day borders in every year. The legend has an entry for each bar series drawn and, when a state is selected, one for its mark (`labels.C3_SELECTED`); the marker series has none (its name, `labels.C3_NO_FIGURE_SERIES`, is never shown). The plain series is named `BOUNDARY_BASIS["at_election"]` when every
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
  `labels.LEGISLATURE_CHOSE` and `labels.TOOK_NO_PART` in the popular-vote cell. The filter on
  `/election/<year>/states` and on `/state/<usps>/elections` has the placeholder "Any" (a literal in
  `_controls` in `pages/election_states.py` and in `pages/state_results.py`), and each page's
  `FILTER_SENTENCE` names it "popular-vote status". On the API's `/docs` page, the
  `EcPvRow.pv_status` and `ElectionStateRow.pv_status` field descriptions in
  `src/usvote/api/models.py`. The hover line in `labels.C4_STATE_HOVER` (C7) and the C7 key
  entry `labels.C4_NO_ELECTORS_TOOK_NO_PART`; the hover line in `labels.C10_HOVER` (C10) and
  C10's key entries `labels.C5_LEGISLATURE` and `labels.C5_TOOK_NO_PART` (#582). C5 draws all
  states only since #562, so `labels.national_total` never returns the cells those two key
  entries map from there.
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
  `labels.HAS_POPULAR_VOTE_NOTE`; the popular-vote checkbox on the three elections pages,
  `labels.PV_ONLY_FILTER`, which `labels.METRIC_SAME_ELECTIONS` names by its text.
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
  same value. In C2 (#564): the solid triangle (`LABELS["pv_share"]` in the key, `labels.C2_PV_HOVER`, `labels.C2_PV_MARK`, `labels.C2_PLURALITY_NOTE`) and the companion table's `pv_share` column.
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
- **Shown as:** `LABELS["pv_winner"]`; `labels.winner`. In C2 (#564): the companion table's `pv_winner` column, `labels.C2_PV_DIFFERENT_KEY`, `labels.C2_PV_DIFFERENT_HOVER`, `labels.C2_TABLE_METHODS_NOTE`.
- **Source:** `ElectionSummary.pv_winner`; `posts/2026-08-06-222-votes-away.md` (led the national
  popular vote count).
- **Not:** A majority winner. In C2 it may name a different candidate from the row's.
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

### Recipients (who received electoral votes, per election)
- **Plain:** In the list of elections, the candidates who received electoral votes in each
  election, one line each, with their electoral votes cast and counted.
- **Precise:** For one year, N1's `data` rows for that year, in served order, each written from
  `candidate`, `national_electoral_votes` (cast) and `national_electoral_votes_counted`. Every row
  has more than 0 votes cast and from 0 to that number counted (`elections_view.n1_recipients`);
  a row with none cast is refused, never left out, since the API counts every N1 row in
  `candidate_count` (D116(d)). So the lines are exactly the candidates *Candidates with electoral
  votes (count per election)* counts. Their number equals that year's `candidate_count`, which is
  at least 1; a refused row, a mismatch or a count below 1 is C9's tier 2. Both
  numbers always show, even when they are equal. It is a page-only column (D116(a), amending
  D075), the last in T1 after its seven served columns. It is built through
  `components.table(..., page_only=)`, with its header marked `components.PAGE_ONLY_CLASS` and
  `RECIPIENTS_FIELDS` as the header's tooltip. It is never in T1's download: each election's own
  national results table and its download carry the same rows. No public field holds it, so it
  has no `LABELS` key and no Key index row. The same lines make up C9's hover.
- **Shown as:** `RECIPIENTS_HEADER`, `RECIPIENTS_FIELDS` (the header's tooltip and the entry in
  T1's column-name list, through `PAGE_ONLY`) and `RECIPIENTS_DOWNLOAD_NOTE`, in
  `pages/elections.py`; `labels.RECIPIENT_LINE`, one line per recipient with `labels.number`
  cells, separated by line breaks in the table and joined with `<br>` in `labels.C9_HOVER`;
  `labels.UNAVAILABLE_CELL` in both degradation tiers.
- **Source:** #563 (update 1); D116; `NationalSummaryRow.candidate`, `national_electoral_votes`
  and `national_electoral_votes_counted` in `src/usvote/api/models.py`; D007; reader wording:
  `ba` spec for #563, approved by the owner at its plan gate (2026-11-22).
- **Not:** A public `/v1` field. A `LABELS` key. Candidates on the ballot. Only the candidates
  whose votes Congress counted. The winners.
- **Status:** settled

### Rows shown (count line)
- **Plain:** The line above a table that says how many of its rows the table shows under the
  filters in effect, out of all the rows it has, for example "Showing 3 of 12 rows".
- **Precise:** "Showing {shown} of {total} rows": the number of rows the table shows after the
  page's filters, then the number of rows the page read for that table. A row is one line of that
  table, so what it stands for follows the table: in T2, T4 and T5, one candidate in one state at
  one election; in T6, one state at the election; in T7, the state at one election. On the state
  pages, T4's line follows its three filters and T7's follows the year range, the only filter on
  its page. When the filters leave no rows, the line reads "Showing 0 of
  n rows" and the table's place shows `components.NO_ROWS`. Shown only on a successful render.
- **Shown as:** a literal paragraph with class `count`, in `render` in `pages/election_states.py`
  (above T2), `pages/candidate.py` (above T5) and `pages/state_results.py` (above T4); in
  `render` in `pages/state_per_capita.py` (above T7); and in `render` in
  `pages/election_per_capita.py` (above T6).
- **Source:** the page modules named under **Shown as**, which settle what each line counts.
- **Not:** *Elections shown*, the count line above T1 on `/elections`, which counts elections
  (`labels.METRIC_LABELS["elections_shown"]`). A count of candidates or states. A count of
  anything beyond the rows the page read.
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
  `/state/<usps>`, `/state/<usps>/elections` and `/state/<usps>/per-capita`, matched by route, so a link the dataset does
  not serve marks its section too: the mark names the section, not the page being read.
  Elections also carries `aria-current="true"` on `/elections/majority` and
  `/elections/over-time` (#562). Nothing
  is marked on `/candidate/<slug>` or the custom 404 page. Elections, States and the site name
  navigate client-side. API docs is an ordinary same-tab link to the API's `/docs` page, which
  is not on this site (*Site name*). Not the links between the three Elections pages
  (`labels.ELECTIONS_SECTIONS_LABEL`; *Pages for all elections*).
- **Shown as:** `labels.SITE_NAV_LABEL` (read by assistive technology, not shown);
  `labels.SITE_NAME_SHORT` and `labels.SITE_NAME_REST`; `labels.NAV_ELECTIONS`,
  `labels.NAV_STATES`, `labels.NAV_API_DOCS`; the API docs link's tooltip,
  `labels.NAV_API_DOCS_TITLE`; then, in the header, the theme toggle (*Theme choice*). Built by
  `components.site_nav`, placed in `app.layout` (`dashboard/explore/app.py`).
- **Source:** #448 (owner decisions fixed in the issue and the owner's comment, 2026-11-06);
  D086; reader wording: owner decision at #448's plan gate, 2026-11-06.
- **Not:** The earlier and later links on the election pages and their landmarks
  (`labels.ELECTION_NAV_LABEL`, `labels.ELECTION_NAV_SECTION_LABEL`; *Election year*), and the links
  between an election's three pages (`labels.ELECTION_SECTIONS_LABEL`; *Election pages*) and between
  a state's three pages (`labels.STATE_SECTIONS_LABEL`; *State pages*). The in-body "Browse…" links on
  the home page and the not-found states, which stay. A menu: the bar has at most four entries at
  the right, the toggle counted, and never collapses.
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
  code used in URLs and filters. Each state has three pages (*State pages*): its history,
  `/state/<usps>` (C7, C10); its results by election, `/state/<usps>/elections` (T4); and its
  people per electoral vote, `/state/<usps>/per-capita` (T7); an election outside the years this
  dataset covers (*Years covered*) is on none.
- **Shown as:** `LABELS["state"]`; `labels.C4_TITLE_STATE` (C7) and `labels.FIRST_ELECTION_START_NOTE`
  (C7 and C10, #620); `labels.C10_TITLE_STATE` (C10, #582); the state filter on `/election/<year>/states`, named by that page's `FILTER_SENTENCE`
  (`pages/election_states.py`), and on `/election/<year>/per-capita`, named by its `FILTER_SENTENCE`
  (`pages/election_per_capita.py`), both with the placeholder "All states" (a literal in `_controls`
  in `pages/election_states.py` and in `_control` in `pages/election_per_capita.py`), and on
  `/candidate/<slug>`, with `STATE_PLACEHOLDER` and named by the lede's `FILTER_SENTENCE` or
  `FILTER_SENTENCE_ONE_YEAR` in `pages/candidate.py`; `/states`; the name, as served, as the link to
  the state history page `/state/<usps>` in T2, T5 and T6 (`components.state_cell`), and the heading
  of the state history page; the state pages' own wording is under *State pages*. The home page's
  lede and its "Browse by state" link (`pages/home.py`). The site navigation's States link,
  `labels.NAV_STATES`, goes to `/states` and is marked on `/states`, `/state/<usps>`,
  `/state/<usps>/elections` and `/state/<usps>/per-capita`. In C3, the row labels, the selected-state series `labels.C3_SELECTED`
  and the caption sentence `labels.C3_SELECTED_NOTE`.
- **Source:** `EcPvRow.state`, `state_usps`; D006; `docs/canonical-keys.md`, "The two keys are
  two-tier"; the results by election page: #279 (T4), #619, its lede in
  `pages/state_results.py`, whose filter sentence shows only on a successful render (#392); the per-capita page: #280 (T7), #559.
- **Not:** —
- **Status:** settled

### State pages (state history, results by election, people per electoral vote)
- **Plain:** Each state in this dataset has three pages. The state history shows the state's
  electors appointed and its total popular vote in each election, in two charts and one table,
  with headline figures. Results by election shows the state's electoral votes for each candidate
  in every election this dataset holds for it, with the popular vote where the dataset has it; a
  reader can narrow it by year, candidate or popular-vote status. People per electoral vote shows
  how many people the state's electoral votes stood for in each of those elections; a reader can
  narrow it by year. Links near the top of each page go between the three, and the page being read
  is marked. Following one from any of the three pages keeps the years chosen. The state history
  can be narrowed by year, from the state's first election (*A state's first election*).
- **Precise:** Three registered pages: `/state/<usps>`, the state history (chart C7, then chart
  C10, then their one companion table `state-electors` (#618; `state-popular-total` is retired),
  and the provenance footer; the year range `year_from`/`year_to` only, its own `query=` parser,
  judged against the state's span from its first election to the latest served year, so a bound
  outside it falls back to that end, defaulting to that whole span (D119); when neither chart's
  half can be built, the slider and `FILTER_SENTENCE` do not render and the table's place shows
  `ELECTORS_TOTALS_TABLE_UNAVAILABLE`); `/state/<usps>/elections`, results
  by election (T4, its three filters `year_from`/`year_to`, `candidate` and `pv_status`, T4's party
  notes, and the footer), both filled from `/v1/states/{usps}`; and `/state/<usps>/per-capita` (T7
  and the year range only), filled from `/v1/states/{usps}/per-capita`. The two subpages are
  registered with `order=` ahead of the history page's template. Each checks the code against the
  state roster; a code it refuses, and a link naming a section the site does not have
  (`/state/GA/x`), get the same not-found state (*Not-found state*). On a successful render each
  page carries the section links, a landmark named `labels.STATE_SECTIONS_LABEL`: the page being
  read is text marked `aria-current="page"`, and the others are links that open without reloading
  the page and carry the year range the page applied in their query string, never `candidate` or
  `pv_status`; the history page's links carry the range it applied (D119). An old
  `/state/<usps>` link naming `candidate` or `pv_status` answers 302 to `/state/<usps>/elections`,
  the year range riding along (D092's `moved=`, D118); one naming only the year range opens the
  history page, which applies it (D119).
- **Shown as:** the section links `labels.SECTION_STATE_HISTORY`,
  `labels.SECTION_RESULTS_BY_ELECTION` and `labels.SECTION_PER_CAPITA`, and their landmark name
  `labels.STATE_SECTIONS_LABEL` (read by assistive technology, not shown). In `pages/state.py`, the
  history page's heading (the state's name as served, from `render`; on the degraded state "State
  history", a literal in `layout`), `LEDE` (success and degraded; reworded by #560, #582 and #619),
  `FILTER_SENTENCE` (success only, while the slider shows; #620), the Years slider
  (`labels.YEARS_FILTER`), `labels.STATE_NO_ELECTIONS_IN_RANGE`, the section headings `C7_HEADING`, `C10_HEADING` and
  `ELECTORS_TOTALS_TABLE_HEADING`, C7's `C7_UNAVAILABLE`, C10's `C10_UNAVAILABLE`, the shared
  table's `TOTALS_UNAVAILABLE_NOTE`, `ELECTORS_UNAVAILABLE_NOTE` and
  `ELECTORS_TOTALS_TABLE_UNAVAILABLE`, its title (`title`: the code, then "state history", then the
  site title once the code is checked, and before then "State history" and the site title; never
  the state's name) and its `description`. In `pages/state_results.py`, `RESULTS_HEADING` ("{state}:
  results by election") and `RESULTS_GENERIC_HEADING`, `LEDE`, `FILTER_SENTENCE` (success only),
  `title` (the code, then "results by election", then the site title; before then the generic
  heading and the site title), `description`, the controls "Years", "All candidates" and "Any", and
  T4's download, named "the results by election" in the file `state-{usps}-by-election.csv`. In
  `pages/state_per_capita.py`, `PER_CAPITA_HEADING` ("{state}: people per electoral vote") and
  `PER_CAPITA_GENERIC_HEADING`, `LEDE`, `FILTER_SENTENCE`, `title`, `description`, the year
  control's label "Years", and T7's download (*People per electoral vote*). The not-found state,
  shared by all three: `labels.STATE_NOT_FOUND_HEADING`, `labels.STATE_NOT_FOUND_SENTENCE` and
  `labels.STATE_NOT_FOUND_LINK`. The shared state module, `state_view.py`, ships no wording of its
  own.
- **Source:** #559 (owner agreement, 2026-11-17 review: the split, the year range as the subpage's
  only filter and carried by the section links); #619 (T4 to its own page; owner's goal: make the
  data visible and cut scrolling); D092 (the subpage pattern); D105, as amended by D118; #279 (T4),
  #280 (T7); reader wording: `ba` specs for #559 (approved by the owner at its plan gate,
  2026-11-18), #619 (approved at its plan gate, 2026-11-23) and #620 (approved at its plan gate,
  2026-11-23); #620 and D119 (the history page's year range).
- **Not:** *Election pages* (Results by state is an election's page; Results by election is a
  state's). *Site navigation*. A filter: the section links change the page; the year range they
  carry is the reader's own.
- **Status:** settled

### State's electors appointed over time (chart C7)
- **Plain:** A chart on each state's history page with election years running left to right; each
  bar is the electors the state appointed in one election, from its first election in this dataset (*A state's first election*); the Years filter can narrow it to a range of years.
  Where there is nothing to draw, a marker stands in the bar's place, never a bar of zero length,
  and the chart's key says what each kind of marker means; an election in which the state appointed
  no electors (its allotment was 0) is marked that way too. A table below it and the total popular vote chart holds its numbers beside the state's total popular vote, with one download for both.
- **Precise:** `CHARTS["C7"]` on `/state/<usps>`, id `c7`, companion table `state-electors`, shared with C10 since #618 (fields `year`, `state_electoral_votes`, `pv_status`, `state_popular_total`; CSV extra `state_usps`). One point per served year,
  collapsed from `/v1/states/{usps}` rows (one per candidate per year); the rows of one year must agree on the allotment and on the status, and what a disagreement removes is set out below. Its values equal C4's one-state
  series for the same state. Bars, markers, symbols, the key and the year axis are C4's (D100,
  D104). Narrowed by the page's Years filter together with C10 and their table, after the collapse (D119, amending D093(a), D106); no selection trace. If the series cannot be built because of a fault only C7 reads (a year's allotments disagree), the chart and the headline figures give way to `C7_UNAVAILABLE` after the heading, and the table's electors column reads *Not available right now* with `ELECTORS_UNAVAILABLE_NOTE` first among its notes, while C10, its column and the success marker stay. A fault C10 also reads (a year's `pv_status`, a year missing after the state's first, the state's name with no text) shows `C7_UNAVAILABLE` and `C10_UNAVAILABLE` and, under the table heading, `ELECTORS_TOTALS_TABLE_UNAVAILABLE`, with no table (D117, amending D113(a), (c)).
  Bars `--chart-ec`; the key above the plot (#593).
- **Shown as:** in `pages/state.py`, `C7_HEADING`, `C7_UNAVAILABLE`, the shared table's heading `ELECTORS_TOTALS_TABLE_HEADING`, `ELECTORS_UNAVAILABLE_NOTE` and the download "this state's electors appointed and total popular vote in each election" (`state-{usps}-electors-and-total-popular-vote.csv`); in
  `labels.py`, `C4_TITLE_STATE` (else `C7_TITLE_THIS_STATE`), `C4_VALUE_AXIS`, `C4_STATE_HOVER`, the
  key entries `C4_NO_ELECTORS_TOOK_NO_PART`, `C4_NO_ELECTORS`, `NOT_IN_DATASET` and `UNRECOGNIZED`,
  the caption sentences `C4_BASIS`, `C4_ZERO_NOTE`, `C4_NO_FIGURE_NOTE`, `FIRST_ELECTION_START_NOTE` (else
  `FIRST_ELECTION_START_NOTE_THIS_STATE`; `FIRST_ELECTION_NOTE`, `C10_FIRST_ELECTION_NOTE` and their
  `_THIS_STATE` forms are retired, #620) (`C7_FILTERS_NOTE` is retired with the page's filters, #619);
  `LABELS["year"]` (the year axis); the table's notes `C4_BASIS`, `C5_BASIS` and `OVER_TIME_WINDOW_NOTE`; then `labels.CHART_TABLE_POINTER`.
- **Source:** #560 ACs; D091, D093(a), D096(d), D100, D104, D106; `EcPvRow.state_electoral_votes`
  and `EcPvRow.pv_status` on `/v1/states/{usps}`; reader wording: `ba` spec for #560, approved by
  the owner at its plan gate (2026-11-18); #618 (one table, owner's ruling 2026-11-23; D117); reader wording: `ba` spec for #618, approved by the owner at its plan gate (2026-11-23).
- **Not:** electoral votes cast or counted; the *Degraded state*
  (a C7 that cannot be built shows its own sentence in its place and the page stays; only a fault in what the whole page reads, such as rows that fail the state's rows check or a missing popular-vote window bound, degrades it, D118); a second definition of C4's
  series (same values, another page).
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
  (`_DESCRIPTION_TEMPLATE` in `src/usvote/api/app.py`). On the dashboard,
  `LABELS["state_popular_total"]` and chart C10 and the last column of the table it shares with C7 on `/state/<usps>`
  (*State's total popular vote over time*), its null-inside-the-window cell
  `labels.NO_STATE_TOTAL` (#582; C5's one-state mode showed it until #562).
- **Source:** `EcPvRow.state_popular_total`, `ElectionStateRow.state_popular_total`;
  `_aggregate_fusion_lines`, `assert_totals_reconcile` and `assert_totals_not_exceeded` in
  `src/usvote/mit/transform.py`; `docs/api-snapshot.md` (`national_pv_denominator`); #428 plan
  measurements (snapshot `37af4064`).
- **Not:** *Popular votes* (one candidate's). The sum of the dataset's candidates' popular votes
  in the state. Zero where a total is missing.
- **Status:** settled; wording pending (#379: the `EcPvRow.state_popular_total` description
  writes "None" and "PV")

### State's total popular vote over time (chart C10)
- **Plain:** A chart on each state's history page, below the chart of its electors appointed,
  with election years running left to right; each bar is the state's total popular vote in one
  election. The shaded years are those before this dataset's popular-vote figures begin (and any
  after they end); shading does not mean no popular vote was held. Where an election has no
  total to draw, a marker stands in the bar's place, never a bar of zero length, and the chart's
  key says why: the legislature chose the electors, the state took no part, or this dataset has
  no total. A table below it holds its numbers beside the state's electors appointed, with one download for both.
- **Precise:** `CHARTS["C10"]` on `/state/<usps>`, id `c10`, directly below C7 in the card they share; its companion table is C7's, `state-electors` (#618). One point per served year from the state's first election (*A state's first election*) by default, collapsed from
  `/v1/states/{usps}` rows (`popular_totals` in `pages/state.py`): a year's total is read from
  every row except one whose `popular_votes` and `state_popular_total` are both null (a row
  without a candidate figure carries no state total, per *State's total popular vote*); every
  other row must carry a total, and those must agree (D113(b), as amended). A fault in a total, or a popular-vote window bound that is present and malformed, shows C10's heading and `C10_UNAVAILABLE` in place of the chart, and the table's total popular vote column reads *Not available right now* with `TOTALS_UNAVAILABLE_NOTE` first among its notes and no `OVER_TIME_WINDOW_NOTE`, while C7, the headline figures, the electors column and the success marker stay; a fault in what
  C7 reads too (a year missing after the state's first, the state's name with no text,
  `pv_status`) shows both charts' notes and `ELECTORS_TOTALS_TABLE_UNAVAILABLE` in place of the table; a missing window bound degrades the page, since the shared table's download reads both (D113(c), as amended; D117; D118). Bars, band, markers
  and year axis are C5's (D100(d), D104), drawn by `over_time.total_figure` (D113(d)); band
  bounds from `meta.provenance.coverage`. Its value axis writes its numbers short, as C5's does
  (D113(e)). Its plot shares C7's left and right margin (`over_time.STATE_MARGIN`, D113(f)).
  Narrowed by the page's Years filter together with C7 and their table, after the collapse (D119, amending D093(a), D113). Bars `--chart-pv`; key above the plot. Values equal N2's
  `state_popular_total` for the state.
- **Shown as:** in `pages/state.py`, `C10_HEADING`, `C10_UNAVAILABLE`, `TOTALS_UNAVAILABLE_NOTE`, and the shared table and download (*chart C7*); in `labels.py`, `C10_TITLE_STATE` (else
  `C10_TITLE_THIS_STATE`), `C5_VALUE_AXIS`, `C10_HOVER`, the bands `C5_BEFORE_BAND` /
  `C5_AFTER_BAND`, the key entries through `C10_MARKER_LABELS` (`C5_LEGISLATURE`,
  `C5_TOOK_NO_PART`, `C5_NO_TOTAL`, `UNRECOGNIZED`; `C5_NO_TOTAL` is the one entry for a
  table cell of either `NO_STATE_TOTAL` or `NOT_IN_DATASET`; C5 draws the same entry for its own
  missing total), the caption sentences
  `C5_BASIS`, `C10_SHORT_TICKS_NOTE`, `C5_BEFORE_NOTE`, `C5_AFTER_NOTE`, `C5_MARKER_NOTE`,
  `FIRST_ELECTION_START_NOTE` (else `FIRST_ELECTION_START_NOTE_THIS_STATE`; C10's own
  first-election sentences are retired, #620) (`C7_FILTERS_NOTE` is retired, #619);
  the table's cells through `labels.popular_votes(..., no_figure=NO_STATE_TOTAL)` and
  `labels.pv_status`, its notes (*chart C7*); `LABELS["year"]`; then
  `labels.CHART_TABLE_POINTER`.
- **Source:** #582 ACs; D091, D093(a), D096(d), D100(c)(d), D104, D106, D113;
  `EcPvRow.state_popular_total`, `EcPvRow.pv_status`, `EcPvRow.popular_votes`; reader wording:
  `ba` spec for #582 (C5's one-state wording approved at #436), approved by the owner at its plan gate (2026-11-21); #618 (one table, owner's ruling 2026-11-23; D117); reader wording: `ba` spec for #618, approved by the owner at its plan gate (2026-11-23); #620 and D119 (the Years filter and the start sentence; `ba` spec for #620, approved at its plan gate, 2026-11-23).
- **Not:** turnout; a candidate's popular votes; the national total (C5); a zero, which no
  marker is; "no popular vote", which the band is not.
- **Status:** settled.

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
  electors from states that held a popular vote. It also gives how many electoral votes were
  cast for candidates below second place, and how many electors appointed have no vote in
  Congress's count.
- **Precise:** One object per election year (`ElectionSummary`): `year`,
  `electoral_denominator`, `ec_winner`, `pv_winner`, `hybrid_winner` and their `_slug`
  fields, `ec_determinative`, `pv_coverage`, `pv_flip`, `hybrid_flip`, `ec_margin`,
  `pv_margin`, `hybrid_margin`, `electoral_votes_outside_top_two`,
  `electors_without_a_counted_vote`. Two electoral-vote tallies ride on the same object:
  `electoral_votes_outside_top_two` and `electors_without_a_counted_vote` (see their entries);
  they are not part of the comparison. Served as `election` on `/v1/elections/{year}` and
  `/v1/elections/{year}/summary`, where it is null if the data has no comparison for a
  served year, and as each item of `elections` on `/v1/elections/summary`, one per election
  year, oldest first. Outside the popular-vote window the popular-vote and hybrid fields are
  null (*Outside the popular-vote window*); the Electoral College fields and `pv_coverage`
  have values for every year served.
- **Shown as:** on the API's `/docs` page, the `/v1/elections/summary` summary and docstring
  (`get_all_election_summaries` in `src/usvote/api/routes.py`), and the
  `AllElectionsSummaryResponse` docstring and its `data` and `elections` field descriptions in
  `src/usvote/api/models.py`; the `/v1/elections/{year}/summary` summary in
  `src/usvote/api/routes.py`. On the dashboard, the election panel on the election overview shows
  these fields under the heading "Under each method" (a literal in `_panel`, `pages/election.py`),
  each with its own `LABELS` key, and lists their field names in the panel's field-name list,
  whose toggle reads "Field names" (a literal in `_panel`). Where the API serves `election` as
  null for the year, the panel shows `PANEL_UNAVAILABLE` (`pages/election.py`) under the same
  heading instead, and the rest of the page still shows. On the dashboard, `/elections` reads
  `/v1/elections/summary` for the averages (each item's `ec_margin` and `pv_margin`, *Average
  margin*), `/elections/majority` for C2 (each item's `ec_determinative`, in C2's hover and its
  companion table), and `/elections/over-time` for C4 (each item's `electoral_denominator`).
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
  `elections-leader-table`, on `/elections/majority`); `labels.yes_no`. On `/state/<usps>`,
  `took_office` picks the row whose electoral votes decide
  `labels.METRIC_LABELS["state_took_office_count"]`; the column itself is not shown there.
- **Source:** `NationalSummaryRow.took_office`; owner decision, 2026-10-10, #348 (a separate term
  from the Electoral College winner); `posts/2026-08-25-it-takes-270-but-270-of-what.md`, "The one
  time it happened"; the C2 companion-table column: owner, #434 plan gate (2026-11-11).
- **Not:** *Electoral College winner, or leader with no majority* (1824). "The eventual winner".
- **Status:** settled

### Total electoral votes cast and counted for a candidate (figures)
- **Plain:** On a candidate's page: the electoral votes cast for the candidate in all states, and the ones Congress counted, added up over the elections the year choice shows. The two differ when Congress did not count some votes cast (1868, 1872).
- **Precise:** Two `metrics.sum` figures over one `(year, value)` pair per year, from `national_electoral_votes` and from `national_electoral_votes_counted`, over the same rows as *Elections in which electors voted for a candidate*. Both are national, all states included, whatever the State filter. Each year's value is the one value of that field across the year's rows, checked by the page through `labels.is_blank` and then `over_time.same`, separately for each field and each year (D098's pattern). A row whose field is null or blank (`labels.is_blank`, the dashboard's rule of what is null) holds a null, so a year whose rows hold a null on one and a blank on another holds one null, not two values that differ. If every row of a year holds a null, that year's value is null and that total reads *No figure* (D097: a sum with any null). If a null sits beside a value, two values differ, or a row lacks the field, that total alone reads *Unrecognized value*; the other total, the count and T5 stay. A value that is not an `int` 0 or above (a `bool`, a float, text) also reads *Unrecognized value*. A total of 0 is a value (Greeley 1872 counted). Never a sum of state `electoral_votes` (D097(j)), and never a difference, ratio or percentage. T5 does not show these national fields. Recorded Andrew Jackson: 496 cast and 496 counted over 3 elections (1824–1832).
- **Shown as:** `labels.METRIC_LABELS["candidate_ev_cast_total"]` and `["candidate_ev_counted_total"]`; the value through `labels.metric_total` with `labels.METRIC_OVER` or `labels.METRIC_OVER_ONE` (the averages' span text, reused); `labels.METRIC_NO_FIGURE["candidate_ev_cast_total"]` and `["candidate_ev_counted_total"]`; `labels.METRIC_ALL_STATES_NOTE`; `labels.UNRECOGNIZED`. In `candidate-metrics` on `/candidate/<slug>`, the values `candidate-ev-cast-total` and `candidate-ev-counted-total`.
- **Source:** #601; D097; D112(f), (g); D115 (the `sum` kind and its three states; `METRIC_NO_FIGURE` keyed by sum, amending D114(d)); `EcPvRow.national_electoral_votes` and `national_electoral_votes_counted`; reader wording: `ba` spec for #601, approved at its plan gate; null and blank as one null: owner, option A at #612's code review (D115, amendment).
- **Not:** The selected state's votes. Electors appointed. Popular votes. "Received" for the counted total.
- **Status:** settled

### Total popular vote (nation) (`national_pv_denominator`)
- **Plain:** All the votes for President across the country in one election, for every
  candidate, including candidates who are not in this dataset, as the popular-vote source reports
  them. This dataset has it only for the years its popular-vote figures cover.
- **Precise:** `national_pv_denominator` on `NationalSummaryRow`, repeated on each candidate row
  of a year; null outside the window. Inside the window it equals the year's
  `state_popular_total` added up, each state once. It is the base of `pv_share`, and the
  dashboard reads the year's one distinct value.
- **Shown as:** `LABELS["national_pv_denominator"]`; in C5, the bars, `labels.C5_HOVER` and `labels.C5_ALL_STATES`; the null cells `labels.NOT_APPLICABLE` and `labels.NO_NATIONAL_TOTAL`; on `/elections/over-time`, the figures `labels.METRIC_LABELS["pv_total_first"]` and `["pv_total_latest"]` (*Earliest and latest total popular vote*); and the API `/docs` field description.
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
  that is not text, or that is text made only of formatting or control characters that are not
  whitespace, with or without whitespace beside them, which carry nothing to read (a zero-width
  space, or a control code such as U+0001; Unicode categories Cf and Cc, except the control codes
  that count as whitespace, which make a value blank); a number of the wrong type, or a non-finite one, in a count, share, margin,
  population, people-per-electoral-vote or census-year cell; and a number too large to show as a
  share, margin or people-per-electoral-vote figure (a count, population or census year shows any integer); and a people-per-electoral-vote figure of zero or less, which no state's population divided by its electors appointed can be. It is also the cell for a null figure whose cause field holds an unrecognized code: a
  popular-vote cell whose `pv_status` is unrecognized, a population cell whose `coverage` is, and a
  people-per-electoral-vote cell whose `coverage` is and whose allotment is not zero (a zero
  allotment explains the null first). Candidate and state names are an open vocabulary: candidate
  and state names in the tables, as link text, and as the heading of a state or candidate history
  page are shown as served (#367), except that a candidate name with nothing to read heads the
  candidate history page with that page's general heading (*Candidate*). In the Party notes list
  under a table, a candidate name that is not text, or is made only of formatting or control
  characters that are not whitespace, with or without whitespace beside them, reads this, while
  the table's cell shows that name as served. A null or blank text
  (empty, or only whitespace: spaces, tabs, line breaks, and the few other control codes that count as whitespace, such as U+001F) is not this: it names no cause (*Not in this dataset*), or the cause its row or year gives. No
  served year reaches this cell; it is defensive. On `/elections`, an average margin reads it too
  when a margin among the years shown is of the wrong type or not finite, or when the average is a
  number no margin cell could show; it then names no number of elections or years (*Average
  margin*). On `/elections/majority`, a count of elections reads it too when a flag among the years
  shown is neither yes, no nor null; on `/elections/over-time` and a state's People per electoral
  vote page, an earliest, latest, lowest or highest figure reads it when a value among the years
  shown is not a finite number, or when any such value's own table cell reads it, whichever year
  holds it; both figures of that pair then read it and name no number of elections or years. A
  null or blank value is left out first, even where its cell reads it. On a state's history page,
  both figures read it when an allotment is not an `int` 0 or above, and the took-office figure
  alone when a year that appointed electors has no `took_office`-true row or two, a null, missing
  or non-boolean `took_office`, or a took-office row whose electoral votes are neither null, blank
  nor an `int` 0 or above. On a candidate's page, one total reads it when a year's rows disagree in
  that field (a null or blank beside a value included), a row lacks it, or a value is not an
  `int` 0 or above; the other total, the count of elections and T5 stay (#601, D115). A year
  whose rows are each null or blank (`labels.is_blank`), a null on one row and a blank on
  another included, holds one null: its total reads *No figure*, not this. In a CSV download the field is written as the API
  served it; for a null figure with an unrecognized cause, the figure's column is empty and the
  cause field carries the code.
- **Shown as:** `labels.UNRECOGNIZED`, with `labels.UNRECOGNIZED_NOTE` as each such cell's help text
  (set by `labels.cell`, and by `labels.nominating_party_cell`); for a headline total, through
  `labels.metric_total`. In C1, `labels.UNRECOGNIZED` labels
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
  value's help text (set by `labels.cell`). `labels.metric_count` writes it for a count on
  `/elections/majority`, and `labels.metric_select` for a figure on `/elections/over-time` and a
  state's People per electoral vote page. In C2, C4, C5, C7 and C10, `labels.UNRECOGNIZED`
  names, in the chart's key, the series of markers drawn in place of a point or bar for such a
  value (C5 and C10 through `labels.C5_MARKER_LABELS` and `labels.C10_MARKER_LABELS`), and
  `labels.C4_HOVER`, `labels.C4_STATE_HOVER`, `labels.C5_HOVER` and `labels.C10_HOVER` write
  it with `labels.UNRECOGNIZED_NOTE`.
- **Source:** owner decision, 2026-10-10, #348 (no raw values in cells); wording: owner decision,
  2026-10-11, #348; the rule (a null names no cause; a non-null value outside the known set reads
  this) and its reach to the numeric cells and the census year: owner decisions at the #355 plan
  gate, 2026-10-13; help text on every such cell: owner decision, 2026-10-13, #355 (its wording:
  owner decision at the #354 plan gate, 2026-10-15); a party code with no letter or digit: owner
  decision, 2026-10-13, #355 (code review) (the party rules from #355 were replaced at #389: the
  party is a closed vocabulary); a winner's or Party notes name made only of formatting or control
  characters that are not whitespace reads this: owner decision at the #532 plan gate, 2026-11-15 ("better to know there is
  a problem"); the comment on `UNRECOGNIZED` and the `labels.py` module docstring.
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
- **Shown as:** the coverage list (`COVERAGE_ID`) built by `render` in `pages/home.py`; the CSV preamble; `labels.BEFORE_WINDOW`; `NO_PV_SENTENCE` in `pages/election.py`; C1's caption sentence `labels.C1_NO_PV_CAPTION`, and on `/elections` `labels.METRIC_NO_AVERAGE_PV_YEARS` and `labels.METRIC_DIFFERENT_ELECTIONS`, on `/elections/majority` `labels.METRIC_PV_WINDOW_NOTE` and `labels.METRIC_NO_FIGURE_PV_YEARS`, and on `/elections/over-time` `labels.METRIC_PV_TOTAL_WINDOW_NOTE` and `labels.METRIC_NO_FIGURE_PV_YEARS`, each of which names the years the popular-vote figures cover; `labels.C5_BEFORE_BAND`, `labels.C5_AFTER_BAND`, `labels.C5_BEFORE_NOTE`, `labels.C5_AFTER_NOTE` and `labels.OVER_TIME_WINDOW_NOTE`.
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
| `state_popular_total` | State's total popular vote |
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
| `electoral_votes_outside_top_two` | Electoral votes outside the top two |
| `electors_without_a_counted_vote` | Electors without a counted vote |

T1's recipients column has no `LABELS` key: its header is a page constant (`RECIPIENTS_HEADER`,
*Recipients*).

Metric keys (`labels.METRIC_LABELS`) are not `LABELS` keys; each is named under its entry's
**Shown as**: `elections_shown` (*Elections shown*), `ec_margin_mean` and `pv_margin_mean`
(*Average margin*), `ec_no_majority_count` (*Elections with no Electoral College majority*),
`pv_flip_count` (*Elections with a different popular-vote winner*), `ec_appointed_first` and
`ec_appointed_latest` (*Earliest and latest electors appointed*), `pv_total_first` and
`pv_total_latest` (*Earliest and latest total popular vote*), and `state_per_capita_lowest` and
`state_per_capita_highest` (*Lowest and highest people per electoral vote*), `state_elections_count`
(*Elections in which a state appointed electors*), `state_took_office_count` (*Elections in which a
state's electors voted for the candidate who took office*), `candidate_elections_count` (*Elections
in which electors voted for a candidate*), and `candidate_ev_cast_total` and
`candidate_ev_counted_total` (*Total electoral votes cast and counted for a candidate*).
`labels.METRIC_NO_FIGURE` is keyed by the flag-count, select and sum keys among them (D114(d) as
amended by D115); a plain count's no-figure wording is a constant of its own.

---

## Say instead

Words that reach readers too often without help, and what to say instead. **Ships in** names the
code that carries the wording today; "a rule" marks a row that no single string ships.

| Avoid | Say instead | Ships in | Why |
|---|---|---|---|
| "Overview" for the elections index's section link | List of elections | `labels.SECTION_ELECTIONS_LIST` | "Overview" is an election's first page; one term, one meaning. |
| "winner" for the Electoral College leader in a year with no majority | Electoral College leader (no majority) | `labels.ec_winner_label`, which picks `labels.EC_LEADER_NO_MAJORITY`; `labels.flip`, which names the role in `labels.FLIP_YES` by the same test (`labels._ec_role_is_winner`) | In 1824 the leader did not become president. |
| "leading candidate" or "winner" for every year's rank-1 candidate | Electoral College leader | `labels.C2_*`, `C2_TABLE_HEADING` and the download name (`pages/elections_majority.py`) | "Leading" alone can mean the popular vote's leader, and "winner" is false for 1824. |
| "not applicable" for a year outside the popular-vote window | that this dataset has no popular-vote figures for the year | `labels.NOT_APPLICABLE`; `NO_PV_SENTENCE` in `pages/election.py` | "Not applicable" reads as a claim that the method had no result at the time. |
| "no figure" without "in this dataset" | no figure in this dataset | `labels.NO_FIGURE`, `labels.NO_NATIONAL_FIGURE`, `labels.C1_NO_FIGURE` | Without it, a reader can take the cell as zero votes. |
| "popular-vote leader", "led the popular vote" | Popular-vote winner | `LABELS["pv_winner"]`, `labels.C2_PV_DIFFERENT_KEY`, `labels.METRIC_LABELS["pv_flip_count"]` | In this glossary "leader" means the Electoral College's rank-1 candidate. |
| an unlabeled "hybrid score" in a chart, or "hybrid result" | Hybrid score (the project's proposal) | `labels.C2_HYBRID_KEY`, `labels.C2_HYBRID_HOVER` | It is not an official measure. |
| a raw field name, a status code, or anything with an underscore | the plain label | `LABELS`; `labels.PV_STATUS`, `labels.COUNT_STATUS`, `labels.BOUNDARY_BASIS`, `labels.PER_CAPITA_COVERAGE` | Allowed only where the page presents it as a field name (owner decision, 2026-10-10). In the API's published text a public `/v1` name is written as served, and an internal name never appears (owner decision, 2026-10-15, #374). |
| "null" | no value in this dataset | `labels.NOT_IN_DATASET`; the CSV preamble's last line, `export.NULL_LINE`, still uses the word (#375 decides whether it stays) | Engineering term. In the API's published text, null is the JSON value and is written "null", never "None" (owner decision, 2026-10-15, #374). |
| "coverage" on its own | name which one: years covered; census figure; share of electors from popular-vote states | `LABELS["coverage"]`, `LABELS["pv_coverage"]`; years covered: the coverage list (`COVERAGE_ID`) built by `render` in `pages/home.py`, `export.preamble` | The project uses the word for three different things. |
| "counted" for anything but votes | used, covers, included | a rule (see Wording rules) | "Counted" is reserved for vote counts (owner decision, 2026-10-10). |
| "in force", "governs", "apportionment" | used; redistribute House seats | `LABELS["governing_census_year"]`, `labels.GOVERNING_CENSUS_NOTE` | Legal register. Do not swap them for "set the state's electoral votes" when describing the census used: that is false for a state at the elections between its admission and the first redistribution of House seats that included it, for California 1852–1860, and for DC from 1964 (`docs/governing-census.md`). |
| "footprint" | borders | `LABELS["boundary_basis"]`, `labels.BOUNDARY_BASIS`, `labels.BOUNDARY_NOTE` | Survey jargon. |
| "the Archives" | the National Archives | `LABELS["electoral_count_status_reason"]` | A reader may not know which archive. |
| "the selected state" on a state's own page | this state, or the state's name | `labels.C7_TITLE_THIS_STATE`, `labels.FIRST_ELECTION_START_NOTE_THIS_STATE`, `labels.C10_TITLE_THIS_STATE` | The state comes from the page address; no one selected it. |
| "EC", "PV" in the prose of the API's published text | Electoral College; popular vote | a rule (see Wording rules) | A reader may not know the abbreviations; `ec_` and `pv_` stay inside API field names (owner decision, 2026-10-15, #374). |
| "snapshot" | data version | `components.provenance_footer` (its version line); `export.preamble`; in the API's published text, a rule until #379 rewrites it | Engineering term (owner decision, 2026-10-10). The API's prose follows it too; the field name `snapshot_version` stays (owner decision, 2026-10-15, #374). |
| "No" for a missing value | Not in this dataset | `labels.NOT_IN_DATASET` | "No" is a recorded answer. |
| 0 for a missing figure | never | a rule; in C1, a labeled marker in the bar's place (`labels.C1_NO_FIGURE` for a missing popular-vote figure, `labels.C1_NO_SHARE` for a missing electoral share, or `labels.UNRECOGNIZED` for a value the page has no label for), never a bar of zero length; in C3, a marker with a short label looked up by T6's cell (`labels.C3_MARKER_LABELS`), the full cell in its hover, never a bar of zero length or an infinity; on `/elections`, an average with no contributing election reads *No average* (`labels.METRIC_NO_AVERAGE_FILTERS`, `labels.METRIC_NO_AVERAGE_PV_YEARS`, `labels.METRIC_NO_AVERAGE_NULL`); on `/elections/majority`, a count with no election to include, and on `/elections/over-time` and a state's People per electoral vote page, a figure with none, reads *No figure* (`labels.METRIC_NO_FIGURE_PV_YEARS`, `labels.METRIC_NO_FIGURE_NO_ELECTIONS`, `labels.METRIC_NO_FIGURE`); on a state's history page and a candidate's page, *No figure* (`labels.METRIC_NO_FIGURE_NO_ELECTORS`, `labels.METRIC_NO_FIGURE_NO_CANDIDATE_ELECTIONS`, `labels.METRIC_NO_FIGURE` for the took-office figure and both totals) | Zero is a measurement; a missing figure is not. A real zero is still a drawn, labeled bar. |
| "the state you chose" for a filter's state | Selected state | `labels.C3_SELECTED`, `labels.C3_SELECTED_NOTE` | A shared link carries the filter; the reader who opens it chose nothing. |
| a party code with underscores or in capitals | the party's display form | `labels.NOMINATING_PARTY` | Owner decision, 2026-10-10; closed table since #389. |
| "party" alone where both are meant | name which: the party (the nominating party); the popular-vote source's party | a rule | The API serves both; they differ in vocabulary, years and source. |
| "No nomination", "no party" for `no_nomination` | Without a party's nomination for President when the electors voted | `labels.NO_NOMINATION` | "No party" is a different claim. "No nomination" denies that a withdrawn nominee was ever nominated (D077). |
| a hyphen between the parties of a joint nomination | "and" | `labels.NOMINATING_PARTY` | A hyphen reads as one party's name (Democratic-Republican). |
| "not yet collected", "not yet researched" | Not in this dataset | `labels.NOT_IN_DATASET`, `labels.PARTY_NULL_NOTE` | Dataset-first, with no promise (research §2.3). |
| "Nominating party" as a column header | Party | `LABELS["nominating_party"]` | Rule-2 rows had no national nomination. |
| "the eventual winner", "the winner" for the candidate who became president | the candidate who took office | `labels.METRIC_LABELS["state_took_office_count"]` | In 1824 the Electoral College leader did not take office; "winner" claims a method. |
| "every election they ran in" for a candidate's elections | every election in which they received an electoral vote | `pages/candidate.py` (its lede); `labels.METRIC_LABELS["candidate_elections_count"]`; otherwise a rule | The two sets differ both ways. A run with no electoral votes is not in this dataset, and a person can receive an electoral vote in an election they did not run in (a faithless elector's choice). |
| "figure" for a chart | chart | a rule | In this file and on the page a figure is a number ("no popular-vote figure"). Plotly and HTML call the chart a figure. |
| "C1", "C2" … in page text | the chart's title | a rule | A chart ID is a registry key and a link fragment; readers know a chart by its title (owner decision, 2026-11-06, #432). |
| "previous election", "next election" for a link to a neighboring year | Earlier: the {year} election; Later: the {year} election | `labels.EARLIER_LINK`, `labels.LATER_LINK`, on every election page | The links follow the years this dataset serves, read from the data. "Previous" and "next" claim no election fell between, which nothing in the code checks. |
| "Summary" for an election's first page | Overview | `labels.SECTION_OVERVIEW` | The API serves T3's data as `summary`; one term, one meaning. |
| an arrow character ("←", "→", "«", "»") typed into a link's text | a drawn chevron beside the text, with the words unchanged | a rule (`.neighbor-nav` in `dashboard/explore/assets/style.css`) | A typed arrow is read aloud ("left arrow") and becomes part of the link's name; the words already say which way the link goes. |
| "win margin", "winning margin", "winner's margin" | margin | `labels.METRIC_LABELS`, `LABELS["ec_margin"]`, `LABELS["pv_margin"]` | A margin is first place's lead over second under one method; in 1824 the Electoral College leader did not win. |
| "mean" in reader text | average | `labels.METRIC_LABELS` | The plain word; "mean" stays in code and D097. |
| "turnout" | "total popular vote" | `labels.C5_*`, `labels.C10_*` | Turnout is a share of eligible voters, which this dataset doesn't have. |
| "no popular vote before 1976" | "this dataset's popular-vote figures begin in {pv_year_min}" | `labels.C5_BEFORE_NOTE`, `labels.C2_BEFORE_NOTE` | The band label, `labels.C5_BEFORE_BAND`, says "no popular-vote figures in this dataset" and leaves the year to these notes (#593). |
| "first popular vote", "the first total popular vote" for the earliest figure | the earliest total popular vote in this dataset, with the window named | `labels.METRIC_LABELS["pv_total_first"]`, `labels.METRIC_PV_TOTAL_WINDOW_NOTE` | The dataset's popular-vote figures begin later than its elections; "first" alone reads as the first election held by popular vote, a historical claim the page does not make. |
| "Electoral votes" alone as the name of a state's page of candidate results | Results by election | `labels.SECTION_RESULTS_BY_ELECTION` | A state's electoral votes are its electors appointed, which the history page shows (C7); the results page is each candidate's. |

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
- **A page-level sentence shows only in the page states where it is true** (wording rule): the
  `/states` lede (a literal in `layout` in `pages/states.py`) says "Open one to see …" on the
  degraded state too, where the list of states it points at does not show. A follow-up rewords or
  splits it; the owner approves, on a label spec from `ba`.
- **Candidates with electoral votes chart (C9)**, **Electoral votes outside the top two** and
  **Electors without a counted vote**: the historical claims in the #563 wording await the
  owner's check: 1872, Horace Greeley 3 electoral votes cast and none counted
  (`labels.C9_CAST_NOTE`); 1872, the votes cast outside the top two include Greeley's 3
  (`OUTSIDE_TOP_TWO_NOTE`); 2000, one elector from the District of Columbia did not vote
  (`NO_COUNTED_VOTE_NOTE`). The owner checks them.
