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
python -m usvote all           # (re)build the warehouse incl. ec_pv_redistributable
python -m usvote.snapshot      # read the view, write the snapshot (needs local Postgres)
```

`python -m usvote.snapshot` requires the local warehouse **at build time only** — it reads
`dwh.ec_pv_redistributable` and fails loud (pointing you at `usvote all`) if that view is
absent. Pass `-o/--out` to override `USVOTE_API_SNAPSHOT_PATH`. The build is **reproducible
and idempotent**: the same warehouse data always yields the same `snapshot_version`, and
re-running overwrites the file atomically.

## Two windows, two provenances

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
`pv_state_status.note`, which is verbatim UCSB prose and never leaves the warehouse. That
provenance is enforced, not asserted — the build pins every served reason to the closed
three-sentence vocabulary in `usvote.transform.COUNT_STATUS_OVERRIDES`.

## The three tables

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

### `snapshot_meta` — one provenance row

`snapshot_version`, `schema_version`, `row_count`, `candidate_count`, `year_min`/`year_max`
(served) and `pv_year_min`/`pv_year_max` (popular vote), `source` = MIT / `license` =
CC0-1.0 (read from the `pv_source` reference data), `ec_source` = NARA / `ec_license` =
US-PD, and an informational `build_timestamp`. Feeds the API `meta` block and the ETag.

The windows are **descriptive of the snapshot's actual content**. Note that a *scoped*
warehouse can no longer produce a snapshot at all (D048): the build derives `pv_status` over
the full in-scope election span and **fails loud** if the warehouse is short a year. That is
deliberate — a snapshot silently missing 1868 is a coverage gap rendered as a nonexistence,
the same class of error `pv_status` exists to prevent one level down.

## `snapshot_version` is a content hash, not a timestamp

`snapshot_version` is a SHA-256 over the `ec_pv` rows in a deterministic
`ORDER BY (year, state, candidate_slug)` plus `schema_version`. The build timestamp is
**excluded** from it. This is the single value that reconciles reproducibility ("same
warehouse, same version") with the freshness/ETag contract ("identical data, identical
version") the API (E8-S2) serves.

Because the hash covers only the `ec_pv` data rows — **not** the derived `national_rollup`
— a change to how the roll-up is *computed* over identical underlying data would not move
the hash on its own. Such a change therefore **must** bump `SNAPSHOT_SCHEMA_VERSION` (which
is folded into the hash), so cached consumers see a new version.
