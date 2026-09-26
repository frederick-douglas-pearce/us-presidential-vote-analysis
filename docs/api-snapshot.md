# The API snapshot — serving contract (E8-S1)

The internal API (E8) serves a **read-only SQLite snapshot**, never a live database
([decision **D028**](../.claude/specs/decisions.md)). The local Postgres warehouse stays
the source of truth; a CLI build step materializes the shipped `ec_pv_redistributable`
join view (E6 / [`src/usvote/join.py`](../src/usvote/join.py)) into an immutable snapshot
file, and the running API reads only that file — so it starts and answers requests with
Postgres stopped (the scale-to-zero cost/reliability lever). This page is the contract the
API layer (E8-S2/S3) consumes; the authority is the module
[`src/usvote/snapshot.py`](../src/usvote/snapshot.py).

## Building it

```
export USVOTE_API_SNAPSHOT_PATH=/path/to/snapshot.sqlite
export USVOTE_CENSUS_CORPUS_DIR=/path/to/census_corpus   # required since #245
python -m usvote all           # (re)build the warehouse incl. both source views
python -m usvote.snapshot      # read the views, write the snapshot (needs local Postgres)
```

`python -m usvote.snapshot` requires the local warehouse **at build time only** — it reads
`dwh.ec_pv_redistributable` and `dwh.election_per_capita`, and fails loud if either view is
absent.

**The census corpus is a required input since #245** ([D069](../.claude/specs/decisions.md)).
The per-capita view exists only on a warehouse that loaded census; `python -m usvote all`
skips census (with a NOTICE) when `USVOTE_CENSUS_CORPUS_DIR` is unset, so a public EC + MIT
clone can still build a **warehouse** but no longer a **snapshot**. Fetch the corpus once
with `python -m usvote.census snapshot`. The Bureau's tables are public domain, which is
what makes requiring them acceptable. The UCSB corpus is the opposite case: it is **not**
required and must never become required (D022/D030).

Pass `-o/--out` to override `USVOTE_API_SNAPSHOT_PATH`. The build is **reproducible
and idempotent**: the same warehouse data always yields the same `snapshot_version`, and
re-running overwrites the file atomically.

## Two windows, three provenances

The snapshot reads `ec_pv_redistributable`, which wraps `pv_redistributable` — defined
independently as `WHERE redistributable` (MIT / CC0 only, [D016](../.claude/specs/decisions.md)
/ [D017](../.claude/specs/decisions.md)) — so **no UCSB / `redistributable=false` row can
reach it** (D030). The build re-asserts this at the source (defense-in-depth over the
endpoint and regression guards in E8-S3/S5).

`ec_pv_redistributable` is EC-**left**, so it carries every EC state row from 1824 on with
PV attached only where MIT covers it. Until [D048](../.claude/specs/decisions.md) the build
*filtered away* the rows with no PV and served only 1976–2024. It no longer does:

| | window | source | license |
|---|---|---|---|
| **Electoral college** — every EC column | **1824–2024** (`year_min`/`year_max`) | U.S. National Archives (`NARA`) | public domain, a work of the U.S. Government (`US-PD`) |
| **Popular vote** — `candidate_votes`, `state_total_votes`, `party`, `source`, `reliability` | **1976–2024** (`pv_year_min`/`pv_year_max`) | MIT Election Lab (`MIT`) | `CC0-1.0` |
| **Per-capita population** — the `per_capita` table (#245) | **1824–2024** (the served window) | U.S. Census Bureau (`USCB`) | public domain, a work of the U.S. Government (`US-PD`) |

Both windows are in `snapshot_meta` and in every response's `meta.provenance.coverage`, so
coverage is **stated, never inferred from a field of nulls**. That distinction is the whole
reason the surface widened: most of the table is now pre-1976, where the only data is the
Archives', and a `meta` block naming only MIT would tell a reader MIT covers 1824.

Within the popular-vote window, an EC getter MIT does not cover (a faithless elector, an
unpledged slate) keeps its EC row with **NULL** PV — an honest gap, never a fabricated 0.

### `pv_status` — why a null popular vote is never bare

Widening the window without this column would have committed, on the public artifact, the
exact missing-vs-zero conflation this project exists to describe. Every `ec_pv` row carries
one of three values ([D024](../.claude/specs/decisions.md)):

| `pv_status` | means | `popular_votes` |
|---|---|---|
| `popular_vote` | a popular vote was held in this state that year | the figure, if the year is inside the popular-vote window; **null** otherwise |
| `legislature_chosen` | the state's legislature appointed the electors — no popular vote was ever held | always null |
| `not_participating` | the state took no part in this election at all | always null |

So 1860 South Carolina (`legislature_chosen`) and 1860 New York (`popular_vote`) both show
`popular_votes: null`, and the two nulls mean different things — one is a fact about the
election, the other about this surface's reach.

**Where these classifications come from.** Not from UCSB. The pre-1976 statuses are derived
at build time from an **in-repo catalog** of 32 `(year, state)` absences, each carrying a
public-domain citation ([`src/usvote/pv/absences.py`](../src/usvote/pv/absences.py)),
layered over state membership read from the EC spine; `popular_vote` is the residual. The
warehouse's own `dwh.pv_state_status` table is **never read** by this build — its pre-1976
rows are UCSB-derived, and UCSB grants no redistribution rights (D022). UCSB's roster is a
cross-source *control* that validates ours, never an input to it. A test proves the property
rather than asserting it: `usvote.snapshot` imports cleanly in a process where `usvote.ucsb`
is unimportable.

### Cast vs counted electoral votes

Three measures form a ladder — **appointed ≥ cast ≥ counted**
([D046](../.claude/specs/decisions.md)):

- `total_electoral_votes` — electors **appointed** (the state's allotment).
- `president_electoral_votes` — votes the electors **cast**.
- `president_electoral_votes_counted` — votes that entered Congress's **final count**.

They diverge in exactly two elections. In 1872 Grant's electors cast 300 votes and Congress
counted 286; Greeley's Georgia electors cast 3 and Congress counted none. In 1868 Georgia's
nine votes for Seymour were cast and the two chambers never agreed whether to accept them.
`count_status` (`counted` / `not_counted` / `disputed`) says which happened, and
`count_status_reason` carries the Archives' own sentence explaining it.

**`president_electoral_rank` and `took_office` are on the counted basis**, because who won
is settled by the votes Congress counted. A reader of 1872 will see Grant at
`national_electoral_votes: 300` and `electoral_rank: 1` and should not try to reconcile the
rank against the cast column.

`count_status_reason` is the one free-text column on the public surface, and it ships for a
specific reason: Archives pages are works of the U.S. Government (17 U.S.C. § 105), unlike
`pv_state_status.note`, which is verbatim UCSB prose and never leaves the warehouse. The
build pins every served reason to the sentences in
`usvote.transform.COUNT_STATUS_OVERRIDES` — which bounds *which* sentences can ship (a
value from anywhere else fails the build) but does **not** by itself prove where they came
from, since that map is also where a new correction is added. The provenance rests on review
of the catalog, where each entry carries its Archives URL. See the note in
`assert_count_status_reasons_are_catalogued`.

## The five tables

### `ec_pv` — the joined fact

One row per `(year, state, candidate_slug)` over the window — that grain is the table's
**PRIMARY KEY**, so a join-view or slug-mapping fan-out fails loud at build (INSERT) rather
than silently shipping duplicates the content hash would bless. Secondary indexes on
`state` / `state_usps` / `candidate_slug` serve the by-state/by-candidate endpoints (the
`year` lookups ride the PK's leftmost prefix). Every EC state row is kept — winners **and**
0-EV losers (the dense-fact rows the thesis explores: "lost the EC, won the PV").

| column | type | notes |
|---|---|---|
| `year`, `state` | INTEGER, TEXT | canonical grain |
| `state_usps` | TEXT | USPS code (`CA`), a clean path key for `/v1/states/{...}` (#97) |
| `candidate` | TEXT | canonical display name |
| `candidate_slug` | TEXT | **public** candidate id (see below) |
| `total_electoral_votes` | INTEGER | the state's EV allotment |
| `president_electoral_votes` | INTEGER | EVs this candidate's electors **cast** in this state (0 for a loser) |
| `national_electoral_votes` | INTEGER | national **cast** EV total (window sum over the candidate's states) |
| `president_electoral_rank`, `took_office` | INTEGER | national EC context, broadcast onto every row; both on the **counted** basis |
| `source`, `party`, `reliability` | TEXT | PV provenance (NULL outside the popular-vote window, or where MIT has no PV) |
| `candidate_votes`, `state_total_votes` | INTEGER | PV count and the source's provided denominator (NULL where no PV) |
| `pv_status` | TEXT **NOT NULL** | why this state has or lacks a popular vote (see above) |
| `president_electoral_votes_counted` | INTEGER | of the cast votes, those Congress **counted** |
| `national_counted_electoral_votes` | INTEGER | national **counted** EV total |
| `count_status` | TEXT **NOT NULL** | `counted` / `not_counted` / `disputed` |
| `count_status_reason` | TEXT | the Archives' sentence explaining a non-`counted` status; NULL otherwise |

`pv_status` and `count_status` are `NOT NULL` deliberately: "a null popular vote is never
bare" and "every row says whether its votes were counted" are per-row promises, so the store
enforces them per row rather than leaving it to a build-time assert.

Public field names differ from these column names where the internal `president_*` prefix
would read wrong to an external consumer — `president_electoral_votes` → `electoral_votes`,
`president_electoral_votes_counted` → `electoral_votes_counted`,
`national_counted_electoral_votes` → `national_electoral_votes_counted`, `count_status` →
`electoral_count_status` (unambiguous next to `popular_votes`), `candidate_votes` →
`popular_votes`. A drift guard asserts every column maps to a field.

`candidate_id` — the warehouse's internal, row-order surrogate — is **dropped** and never
exposed ([`docs/canonical-keys.md`](canonical-keys.md), D006). The durable public id is
`candidate_slug`, minted deterministically from the canonical name
([`src/usvote/slug.py`](../src/usvote/slug.py); `Donald J. Trump` → `donald-j-trump`). Two
distinct names colliding onto one slug (the same-name residual) fails the build loud.

### `national_rollup` — precomputed summary

One row per `(year, candidate_slug)` so `/v1/elections/{year}/summary` **reads** instead of
computing in a route handler: `national_electoral_votes` (cast),
`national_counted_electoral_votes` (counted), `national_electoral_denominator`,
`national_pv_votes` (NULL for a no-PV getter), and `national_pv_denominator` (each state's
total counted once — the **non-null** `state_total_votes` per state, so a no-PV getter's
NULL row never drops the state from the sum). Safe to precompute because the popular-vote
window is single-source (MIT), so there is no cross-source denominator ambiguity (D017).

`national_electoral_denominator` is the year's whole number of electors **appointed**, each
state counted once — the 12th Amendment's denominator (D041). It is here so a counted total
is checkable: 1872 is Grant at **286 of 366**, and 1824 has the **261** the House-contingent
story turns on. Without it a consumer would have to re-sum `total_electoral_votes` off the
fact table, which multiplies every state's allotment by the candidate count — the exact bug
`usvote.hybrid.ec_denominator_by_year` was written to prevent, so the surface answers it
rather than delegating it.

**Pre-1976 rows are kept, with their EC columns populated and the PV aggregates NULL.**
Dropping them would reintroduce, one level up, the "this year doesn't exist" problem the
widening exists to kill. There is deliberately **no `pv_status` on this table**: a year can
be *mixed* — in 1824 six legislatures appointed electors while eighteen states held a
popular vote — so no single status is true of a whole year. A summary's null popular vote is
disambiguated at **year** level instead, via `meta.provenance.coverage` and the
`has_popular_vote` flag on `GET /v1/elections`. Per-state reasons live on `ec_pv`.

### `hybrid_summary` — the per-election three-method comparison

Added in **#102** (E8-S8). One row per **year** — not per candidate — carrying the three
winners (each with its public `candidate_slug` beside the display name), the two flip
booleans, the three top-2 margins in **percentage points**, `ec_determinative`,
`ec_denominator` and `pv_coverage`. `/v1/elections/{year}` and
`/v1/elections/{year}/summary` return it as a single `election` key.

The grain is why it is a fourth table rather than more columns on `national_rollup`: the
winners and margins are properties of the *election*, and broadcasting them across a
per-candidate table would repeat one answer once per candidate and invite a consumer to
group by the wrong key. The **per-candidate** half of the hybrid — `ec_share_full`,
`pv_share`, `ec_share_hybrid`, `pv_coverage` and `hybrid_score` — does live on
`national_rollup`, because that table's grain already *is* the hybrid frame's public grain.

**Every null here is meaningful, and never a `false`.** Before the popular-vote window this
surface has no popular vote, so `pv_winner`, `hybrid_winner`, both flips and two of the
three margins are NULL — never `false`, which would assert that the popular vote *agreed*
with the electoral college in a year there was none. The electoral-college fields
(`ec_winner`, `ec_margin`, `ec_denominator`, `ec_determinative`) are populated for every
served year back to 1824. And `ec_determinative: false` is a **real answer** — no candidate
reached a majority of the appointed electors, which is 1824 and is the case the hybrid
exists to speak to — not a missing value.

**`ec_share_full` and `ec_share_hybrid` are shipped separately even though they are equal.**
The published coverage policy never restricts the electoral share, so no coverage rule can
manufacture a majority that did not exist (D037/A). Both columns ship precisely so a
consumer can *check* that rather than take it on trust; one column would make the guarantee
invisible.

#### One intended difference from the warehouse view

The snapshot derives the hybrid **in-process from the in-repo absence catalog**
(`usvote/pv/absences.py`), not by reading the `hybrid_redistributable` warehouse view
(#102, superseding D039's read mechanism; D048's action item). Everything the two produce is
identical **except `pv_coverage`**, and that one column differs on purpose:

| | pre-1976 `pv_coverage` |
|---|---|
| `hybrid_redistributable` (warehouse view) | **NULL** — its roster read is scoped to the sources the view carries, and MIT's roster starts at 1976 |
| this snapshot | the **real** figure — 1824 is 190/261 ≈ 0.728 |

The reason is provenance, not convenience: the warehouse roster's pre-1976 rows are
UCSB-derived, and UCSB grants no redistribution rights (D022/D030), whereas every entry in
the in-repo catalog carries a public-domain citation. Under the published policy
`pv_coverage` feeds no score, so replacing it changes no share, winner, flip or margin —
which is what makes the divergence safe as well as deliberate. If you are diffing the view
against the artifact, this column is the expected difference and the only one.

### `per_capita` — persons per electoral vote (#245)

One row per `(year, state)`: how many residents each of a state's electoral votes stood
for. Read from the warehouse view `dwh.election_per_capita` (#184), which is over the
persisted election-grain table `dwh.election_population` ([D064](../.claude/specs/decisions.md)).
A table of its own because of grain: `ec_pv` is per candidate, so columns there would repeat
one state's figure once per candidate. `PRIMARY KEY (year, state)`; indexed on `state_usps`.

| column | type | meaning |
|---|---|---|
| `year` | INTEGER | election year (the view's `election_year`) |
| `state` / `state_usps` | TEXT | full name and USPS code |
| `governing_census_year` | INTEGER | the census whose apportionment was in force — 2020 reads 2010, and 1924/1928 read 1910 |
| `total_electoral_votes` | INTEGER | the appointed allotment, the ratio's denominator (public name `state_electoral_votes`) |
| `population` | INTEGER, nullable | the governing census's resident population |
| `population_series` | TEXT, nullable | `resident`; NULL exactly where `population` is |
| `boundary_basis` | TEXT | `at_election` or `present_day` ([D066](../.claude/specs/decisions.md)) |
| `coverage` | TEXT | `covered` or `no_governing_figure` |
| `persons_per_electoral_vote` | REAL, nullable | `population / total_electoral_votes` |

**A NULL ratio is never bare, and needs no status column.** It has two causes and each is
readable off the row: a NULL `population` with `coverage = 'no_governing_figure'` (one
cell, 1848 Texas, which the US did not enumerate in 1840), or a zero allotment (fourteen
cells, the withheld electoral votes of 1864 and 1868). The build refuses any other NULL,
and any ratio that is not exactly `population / total_electoral_votes`.

**Agreement with `ec_pv`.** Both tables derive from the EC spine's participation roster, so
they cover the same `(year, state)` pairs with the same allotments. The build asserts both:
the key sets are equal in both directions, and every per-capita `total_electoral_votes`
equals the served election rows' figure for the same key. The second check exists because a
stale census load can keep every key and still carry an old allotment — the shape of #243's
Nevada 1864 correction.

Served at `GET /v1/elections/{year}/per-capita` (every state in one election; optional
`state` filter) and `GET /v1/states/{usps}/per-capita` (one state across years;
`year_from` / `year_to`). The view name, the columns read and the three vocabularies are
**copies** in `usvote/snapshot.py` and `usvote/snapshot_schema.py`, because neither module
may import `usvote.census`. `tests/unit/test_snapshot.py::TestPerCapitaContract` holds each
copy equal to its census original.

### `snapshot_meta` — one provenance row

`snapshot_version`, `schema_version`, `row_count`, `candidate_count`, `year_min`/`year_max`
(served) and `pv_year_min`/`pv_year_max` (popular vote), `source` = MIT / `license` =
CC0-1.0 (read from the `pv_source` reference data), `ec_source` = NARA / `ec_license` =
US-PD, `census_source` = USCB / `census_license` = US-PD (the per-capita population, #245),
and an informational `build_timestamp`. Feeds the API `meta` block and the ETag.

The windows are **descriptive of the snapshot's actual content**. Note that a *scoped*
warehouse can no longer produce a snapshot at all (D048): the build derives `pv_status` over
the full in-scope election span and **fails loud** if the warehouse is short a year. That is
deliberate — a snapshot silently missing 1868 is a coverage gap rendered as a nonexistence,
the same class of error `pv_status` exists to prevent one level down.

## `snapshot_version` is a content hash, not a timestamp

`snapshot_version` is a SHA-256 over the `ec_pv` rows in a deterministic
`ORDER BY (year, state, candidate_slug)`, then the `per_capita` rows in `(year, state)`
order, plus `schema_version`. The build timestamp is
**excluded** from it. This is the single value that reconciles reproducibility ("same
warehouse, same version") with the freshness/ETag contract ("identical data, identical
version") the API (E8-S2) serves.

Because the hash covers only the source-data rows (`ec_pv` and `per_capita`) — **not** the
derived `national_rollup` or `hybrid_summary` — a change to how those are *computed* over identical underlying data
would not move the hash on its own. Such a change therefore **must** bump
`SNAPSHOT_SCHEMA_VERSION` (which is folded into the hash), so cached consumers see a new
version. #102 is the worked example: it added a whole table and five roll-up columns without
touching a single fact row, so the hash would not have moved at all — the version went 2 → 3
by hand.

Widening the hash to cover the derived tables was considered and rejected. The version is a
*content* address for the facts; a derived table that changed while the facts did not is a
**code** change, and the schema version is the instrument for that.

**`per_capita` is inside the hash because it is not derived** (#245). It carries a second
source's numbers, so a census reload can move a population while every electoral fact stays
put. With the hash over `ec_pv` alone that reload would ship under the old version, and the
D034 edge-cache cutover would never fire. Every `per_capita` column is hashed **except the
ratio**. The ratio is a pure function of two hashed integers and the view's formula.
Leaving it out keeps the hash free of floats. A change to the formula is not absorbed
silently: the build checks that every ratio equals `population / total_electoral_votes`
and refuses a snapshot where it does not, so a formula change forces an edit to the build,
which is when the schema version should move. A separator byte sits between the two
tables' rows as defence in depth. It has no test of its own. On clean data it makes no
difference, because the tables serialize to different field counts. Nothing yet stops a
string value from containing the hash's own delimiter characters, though, and with such a
value two different snapshots can collide; the separator closes only one such case. The
general fix is a build guard that rejects control characters, tracked as a follow-up. The
version went 3 → 4.
