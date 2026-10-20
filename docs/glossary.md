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
wording lives in `dashboard/explore/labels.py` (`LABELS`, the closed-value tables, and the null
and help-text constants), with a few page-level sentences in `dashboard/explore/components.py`,
`dashboard/explore/export.py` and the modules under `dashboard/explore/pages/`. The API's
published text is its `/docs` page (also served at `/redoc` and `/openapi.json`) and the text of
its responses other than the data values they carry; `CLAUDE.md`, *Who writes wording*, lists
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
  only received popular votes are not in it. `/v1/candidates` lists each candidate once, with
  `candidate_slug`, `candidate` and the election years they appear in (*Election years a
  candidate appears in*).
- **Shown as:** `LABELS["candidate"]`; the candidate filter on `/election/<year>` and
  `/state/<usps>`; the name, as served, as the link to the candidate history page
  `/candidate/<slug>` in T2, T3 and T4, and as that page's heading (`pages/candidate.py`), or
  `HEADING` there until a name is read, which is also the page's title (`title`); and in
  `pages/candidate.py`, the page's link-preview `description` and its download name; on the
  API's `/docs` page, the `CandidateListItem.candidate` and `CandidateListItem.candidate_slug`
  field descriptions in `src/usvote/api/models.py`.
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
  gap, and the 1910 map electing 1924 and 1928); header wording: owner decision, 2026-10-10, #348;
  the help text's wording and historical claim: the owner's ruling at the #352 plan gate,
  2026-10-12, that the claim was checked (its citations are not yet recorded in the repo; #356,
  open, will record them and name the record here).
- **Not:** The census nearest the election.
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
  as served; #355); the count-status filter.
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
- **Not:** A not-found state (*Not-found state*): a link whose year, state code or candidate slug
  the dataset does not serve (`NOT_FOUND_SENTENCE` in `pages/election.py`, `pages/state.py` and
  `pages/candidate.py`). An empty filter result
  (`components.NO_ROWS`). The panel's own unavailable state (`PANEL_UNAVAILABLE`).
- **Status:** settled

### Election year
- **Plain:** The year the presidential election was held.
- **Precise:** `year`. The years served run from `meta.provenance.coverage.year_min` to
  `year_max`, read from the response, never written as a literal.
- **Shown as:** `LABELS["year"]`; the year-range slider (`/elections`, `/state/<usps>`); the label
  of the year control on `/candidate/<slug>`, and the lede sentence that offers it
  (`FILTER_SENTENCE` in `pages/candidate.py`).
- **Source:** `EcPvRow.year`, `YearListItem.year`; `Coverage.year_min` and `year_max`.
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
  hand; `labels.EC_WINNER` and `labels.EC_LEADER_NO_MAJORITY`, chosen by
  `labels.ec_winner_label` from `ec_determinative` for the panel row and its field-name list
  (`_panel` in `pages/election.py`, through `labels.glossary`'s `chosen` map); the cell
  `labels.winner`; `labels.flip`, which names the role in `labels.FLIP_YES` by the same test as
  `labels.ec_winner_label` (`labels._ec_role_is_winner`).
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
  D042 §2; D046 §4; help-text wording (`labels.EC_SHARE_HYBRID_NOTE`): approved by the owner in
  place on the #352 branch deploy, 2026-10-12.
- **Not:** A share of the votes cast.
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
  `labels.margin`; the panel note `labels.MARGIN_NOTE`.
- **Source:** `ElectionSummary.ec_margin`, `pv_margin`, `hybrid_margin` and
  `_ELECTION_SUMMARY_EXAMPLE` in `src/usvote/api/models.py`; D037; help-text wording
  (`labels.MARGIN_NOTE`): approved by the owner in place on the #352 branch deploy, 2026-10-12.
- **Not:** A percent change. A gap measured from the Electoral College's winner or leader.
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
  party the source of record names (D077 rule 2). A national party's endorsement counts as its
  nomination (rule 3), and so does a U.S. Government source's statement that the person was the
  party's candidate or nominee, or that a body of the party supported or nominated them (rule 8);
  a value resting on either carries a note saying so (*Nominating-party note*). `no_nomination` is
  a served value (rules 5 and 7). Null has one cause: the dataset has no row for that candidate-year. `nominating_party_source`
  says where each value comes from: `NARA`, the party the National Archives prints for the
  election's winner and main opponent (a value that a U.S. Government publication amends, such as
  1872 Greeley's, keeps `NARA`), or `USGOV`, a curated row citing U.S. Government publications;
  null exactly where the value is. A code never changes meaning: a new value or component is a new
  code (D077).
- **Shown as:** on the API's `/docs` page, the `EcPvRow.nominating_party`,
  `EcPvRow.nominating_party_source`, `NationalSummaryRow.nominating_party` and
  `NationalSummaryRow.nominating_party_source` field descriptions in `src/usvote/api/models.py`.
  On the dashboard as *Party*: `LABELS["nominating_party"]`, `labels.NOMINATING_PARTY`,
  `labels.NO_NOMINATION`. In each T2–T5 download, `nominating_party` and
  `nominating_party_source` as served.
- **Source:** D077; `PARTY_COMPONENTS`, `NO_NOMINATION`, `TABLE1_PARTY_CORRECTIONS` and
  `PARTY_SOURCES` in `src/usvote/party.py`; `CURATED_PARTY_ROWS` in
  `src/usvote/party_catalog.py` (the curated values, their rule sets and citations);
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
- **Plain:** A short sentence of fact on how a candidate's nominating party came to be what it
  is: for example, a joint nomination, an endorsement treated as a nomination, a nominee who died
  before the electors met, or sources that say which party the candidate ran for without naming
  the body that nominated them. A row may have none.
- **Precise:** `nominating_party_note`, nullable text, constant per (year, candidate). It states
  only facts its row's own citations support and adds no source. It is required where the value
  rests on rule 3, 5 or 8, and allowed for any other exceptional case. Null means no note was
  recorded: not that the value is missing, and not that the value is plain. Table 1 notes ship
  from `TABLE1_ROW_NOTES` in `src/usvote/party.py`; curated notes from `CURATED_PARTY_ROWS` in
  `src/usvote/party_catalog.py` (#387; #388 adds its rows there). The rows resting on rule 8
  share one sentence, and the two 1836 Whig rows share another.
  The text is a data value, served as stored.
- **Shown as:** on the API's `/docs` page, the `EcPvRow.nominating_party_note` and
  `NationalSummaryRow.nominating_party_note` field descriptions in `src/usvote/api/models.py`.
  On the dashboard: the party cell's help text where a row has a note, and once per candidate and
  election in the Party notes list under T2–T5 (`labels.PARTY_NOTES_HEADING`,
  `labels.PARTY_NOTE_ITEM`), shown as served; `LABELS["nominating_party_note"]` in their
  column-name lists; `nominating_party_note` in their downloads.
- **Source:** D077, "The row note"; research doc §2.4; `TABLE1_ROW_NOTES` (wording approved by
  the owner, 2026-10-18, #385 plan); `CURATED_PARTY_ROWS` (wording approved by the owner,
  2026-10-20, #387 plan).
- **Not:** the value's null (*Nominating party*). Not a citation. Not the count-status reason,
  which is the National Archives' own sentence about the count (*Count status*).
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
  `labels.population`), `labels.persons_per_electoral_vote`.
- **Source:** the comments on `NOT_IN_DATASET` and `_closed_value` in `labels.py`;
  `dashboard/CLAUDE.md`, `components.py`, `labels.py` (the "never No" rule);
  `.claude/specs/backlog-dashboard.md`, "Carry-forward constraints"; #348 acceptance criteria.
- **Not:** "No", which is a recorded negative. Zero. "Not held". *Unrecognized value*, where the
  dataset does hold something.
- **Status:** settled; wording pending (#375: whether the CSV preamble's last line,
  `export.NULL_LINE`, keeps the word "null")

### Not-found state (a link the dataset does not serve)
- **Plain:** What a page says when its link names a year, a state code or a candidate link this
  dataset does not serve.
- **Precise:** Rendered when a page's `validate` judge refuses its path value (D073, D074). It
  never repeats the value and fills nothing built from it. Candidate links match exactly, so a
  listed slug in another letter case is refused too.
- **Shown as:** `NOT_FOUND_SENTENCE` in `pages/election.py`, `pages/state.py` and
  `pages/candidate.py`; `NOT_FOUND_LINK` in `pages/candidate.py`.
- **Source:** D073; D074; `dashboard/CLAUDE.md`, `pages/`.
- **Not:** *Degraded state*; an empty filter result (`components.NO_ROWS`).
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
  `pages/election.py`); `NO_PV_SENTENCE` in `pages/election.py` above T3.
- **Source:** `ElectionSummary` docstring; `labels.in_pv_window`; `.claude/specs/backlog-dashboard.md`,
  E9-S3, "Election panel"; wording: owner decision, 2026-10-10, #348.
- **Not:** "No" (a false flip). A null inside the window, which names no cause.
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
  code used in URLs and filters.
- **Shown as:** `LABELS["state"]`; the state filter (on `/candidate/<slug>`, with
  `STATE_PLACEHOLDER`, and named by the lede's `FILTER_SENTENCE` or `FILTER_SENTENCE_ONE_YEAR`);
  `/states`; the name, as served, as the link to `/state/<usps>` in T2, T5 and T6
  (`components.state_cell`).
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
- **Plain:** This dataset holds a value that this page has no label for, so the page does not
  show the value itself. Where the value sits in a table, the table's download includes it.
- **Precise:** The reader cell for a non-null value outside what the dashboard has wording for: a
  closed-vocabulary code outside the known set (popular vote in this state, count status, borders
  used, census figure, party); a value of the wrong type in a yes-or-no cell (popular vote in this
  dataset, took office, flip, Electoral College majority); a winner's name on the election panel
  that is not text; a number of the wrong type, or a non-finite one, in a count, share, margin,
  population, people-per-electoral-vote or census-year cell; and a number too large to show as a
  share, margin or people-per-electoral-vote figure (a count, population or census year shows any
  integer). It is also the cell for a null figure whose cause field holds an unrecognized code: a
  popular-vote cell whose `pv_status` is unrecognized, a population cell whose `coverage` is, and a
  people-per-electoral-vote cell whose `coverage` is and whose allotment is not zero (a zero
  allotment explains the null first). Candidate and state names are an open vocabulary: candidate
  and state names in the tables, as link text, and as the heading of a state or candidate history
  page are shown as served (#367). In the Party notes list under a table, a candidate name that is
  not text reads this, while the table's cell shows that name as served. A null or blank text is
  not this: it names no cause (*Not in this dataset*), or the cause its row or year gives. No
  served year reaches this cell; it is defensive. In a CSV download the field is written as the API
  served it; for a null figure with an unrecognized cause, the figure's column is empty and the
  cause field carries the code.
- **Shown as:** `labels.UNRECOGNIZED`, with `labels.UNRECOGNIZED_NOTE` as each such cell's help text
  (set by `labels.cell`, and by `labels.nominating_party_cell`). Reached through `labels.pv_status`,
  `labels.count_status`, `labels._closed_value` (so `labels.boundary_basis`,
  `labels.per_capita_coverage`, `labels._null_per_capita`), `labels.popular_votes`,
  `labels.has_popular_vote`, `labels.yes_no`, `labels.flip`, `labels.ec_majority`, `labels.winner`,
  `labels.nominating_party`, `labels.party_notes` (the Party notes list's candidate name),
  `labels.margin`, `labels.number`, `labels.share` (so `labels.share_cell`), `labels.population`,
  `labels.persons_per_electoral_vote`, `labels.census_year`.
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
  preamble; `labels.BEFORE_WINDOW`; `NO_PV_SENTENCE` in `pages/election.py`.
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
| `ec_share_hybrid` | Electoral share |
| `hybrid_score` | Hybrid |

---

## Say instead

Words that reach readers too often without help, and what to say instead. **Ships in** names the
code that carries the wording today; "a rule" marks a row that no single string ships.

| Avoid | Say instead | Ships in | Why |
|---|---|---|---|
| "winner" for the Electoral College leader in a year with no majority | Electoral College leader (no majority) | `labels.ec_winner_label`, which picks `labels.EC_LEADER_NO_MAJORITY`; `labels.flip`, which names the role in `labels.FLIP_YES` by the same test (`labels._ec_role_is_winner`) | In 1824 the leader did not become president. |
| "not applicable" for a year outside the popular-vote window | that this dataset has no popular-vote figures for the year | `labels.NOT_APPLICABLE`; `NO_PV_SENTENCE` in `pages/election.py` | "Not applicable" reads as a claim that the method had no result at the time. |
| "no figure" without "in this dataset" | no figure in this dataset | `labels.NO_FIGURE`, `labels.NO_NATIONAL_FIGURE` | Without it, a reader can take the cell as zero votes. |
| a raw field name, a status code, or anything with an underscore | the plain label | `LABELS`; `labels.PV_STATUS`, `labels.COUNT_STATUS`, `labels.BOUNDARY_BASIS`, `labels.PER_CAPITA_COVERAGE` | Allowed only where the page presents it as a field name (owner decision, 2026-10-10). In the API's published text a public `/v1` name is written as served, and an internal name never appears (owner decision, 2026-10-15, #374). |
| "null" | no value in this dataset | `labels.NOT_IN_DATASET`; the CSV preamble's last line, `export.NULL_LINE`, still uses the word (#375 decides whether it stays) | Engineering term. In the API's published text, null is the JSON value and is written "null", never "None" (owner decision, 2026-10-15, #374). |
| "coverage" on its own | name which one: years covered; census figure; share of electors from popular-vote states | `LABELS["coverage"]`, `LABELS["pv_coverage"]`; years covered: the coverage list (`COVERAGE_ID`) built by `render` in `pages/home.py`, `export.preamble` | The project uses the word for three different things. |
| "counted" for anything but votes | used, covers, included | a rule (see Wording rules) | "Counted" is reserved for vote counts (owner decision, 2026-10-10). |
| "in force", "governs", "apportionment" | used; set the state's electoral votes; redistribute House seats | `LABELS["governing_census_year"]`, `labels.GOVERNING_CENSUS_NOTE` | Legal register. |
| "footprint" | borders | `LABELS["boundary_basis"]`, `labels.BOUNDARY_BASIS`, `labels.BOUNDARY_NOTE` | Survey jargon. |
| "the Archives" | the National Archives | `LABELS["electoral_count_status_reason"]` | A reader may not know which archive. |
| "EC", "PV" in the prose of the API's published text | Electoral College; popular vote | a rule (see Wording rules) | A reader may not know the abbreviations; `ec_` and `pv_` stay inside API field names (owner decision, 2026-10-15, #374). |
| "snapshot" | data version | `components.provenance_footer` (its version line); `export.preamble`; in the API's published text, a rule until #379 rewrites it | Engineering term (owner decision, 2026-10-10). The API's prose follows it too; the field name `snapshot_version` stays (owner decision, 2026-10-15, #374). |
| "No" for a missing value | Not in this dataset | `labels.NOT_IN_DATASET` | "No" is a recorded answer. |
| 0 for a missing figure | never | a rule | Zero is a measurement; a missing figure is not. |
| a party code with underscores or in capitals | the party's display form | `labels.NOMINATING_PARTY` | Owner decision, 2026-10-10; closed table since #389. |
| "party" alone where both are meant | name which: the party (the nominating party); the popular-vote source's party | a rule | The API serves both; they differ in vocabulary, years and source. |
| "No nomination", "no party" for `no_nomination` | Without a party's nomination for President when the electors voted | `labels.NO_NOMINATION` | "No party" is a different claim. "No nomination" denies that a withdrawn nominee was ever nominated (D077). |
| a hyphen between the parties of a joint nomination | "and" | `labels.NOMINATING_PARTY` | A hyphen reads as one party's name (Democratic-Republican). |
| "not yet collected", "not yet researched" | Not in this dataset | `labels.NOT_IN_DATASET`, `labels.PARTY_NULL_NOTE` | Dataset-first, with no promise (research §2.3). |
| "Nominating party" as a column header | Party | `LABELS["nominating_party"]` | Rule-2 rows had no national nomination. |
| "every election they ran in" for a candidate's elections | every election in which they received an electoral vote | `pages/candidate.py` (its lede); otherwise a rule | The two sets differ both ways. A run with no electoral votes is not in this dataset, and a person can receive an electoral vote in an election they did not run in (a faithless elector's choice). |

## Open decisions

Terms whose meaning no source settles yet (`proposed`), and settled terms and wording rules whose
merged reader wording still awaits the owner (`settled; wording pending`). Each line names the
decision and who makes it.

- **Not in this dataset**: whether the CSV preamble's last line, `export.NULL_LINE`, keeps the
  word "null" (#375). The owner decides, on a label spec from `ba`.
- **The API's published text** and **Candidate**: merged API text does not yet follow these
  rules: *The API's published text is reader wording*; *In the API's published text, public
  names are vocabulary*; *"Counted" is reserved for vote counts*; and *Plain words over legal
  and survey terms*. Separately, reader text does not call `candidate_slug` "durable" (owner
  decision, 2026-10-16, #379), but these still do: the *Candidate* entry's **Precise**; the
  `/v1/candidates/{slug}` docstring in `src/usvote/api/routes.py`; and the
  `EcPvRow.candidate_slug` and `NationalSummaryRow.candidate_slug` field descriptions in
  `src/usvote/api/models.py`. #379 rewrites all of them. The owner approves the rewrite, on a
  label spec from `ba`.
