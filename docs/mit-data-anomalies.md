# MIT Election Lab source-data anomalies

Anomalies observed in the **MIT Election Lab** `1976-2024-president.csv`
(Harvard Dataverse [`doi:10.7910/DVN/42MVDX`](https://doi.org/10.7910/DVN/42MVDX),
CC0 1.0) while ingesting it into this project's shared popular-vote pipeline
(`usvote/mit/`, issue #65). Unlike the [EC corrections catalog](corrections.md) — which
patches the National Archives source — this file records quirks in the **MIT** source.

Each entry says what was observed (with exact figures so it is verifiable against the
raw file), how this pipeline handles it downstream, and whether it looks like an
upstream data issue worth raising with MIT. **This doc is intended partly as an
outreach artifact** — the figures below can be quoted directly to the MIT Election Lab.

Figures were read from the copy of the file in hand at ingest time; MIT versions the
CSV (a `version` column per row), so quote the `version` value alongside any figure
when reporting upstream.

## Anomalies

### A1 — 2020 District of Columbia: the entire result is flagged `writein=True` (highest priority)

In 2020, **6 of the 7** DC rows carry `writein=True`, **including both major-party
nominees**:

| candidate | `party_simplified` | `candidatevotes` | `writein` |
|---|---|---|---|
| BIDEN, JOSEPH R. JR | DEMOCRAT | 317,323 | **True** |
| TRUMP, DONALD J. | REPUBLICAN | 18,586 | **True** |
| JORGENSEN, JO | LIBERTARIAN | 2,036 | True |
| HAWKINS, HOWIE | OTHER | 1,726 | True |
| LA RIVA, GLORIA ESTELLA | OTHER | 855 | True |
| PIERCE, BROCK | OTHER | 693 | False |
| (blank) | OTHER | 3,137 | True |

DC does **not** conduct its presidential election by write-in — these are the regular
general-election results — so `writein=True` on Biden/Trump appears to be a
mislabeling. No other year/state codes its major-party nominees as write-ins.

- **Why it matters:** a naive "drop write-ins" filter silently deletes Biden's 317,323
  and Trump's 18,586 votes — an entire jurisdiction's major-candidate result vanishes.
- **How this pipeline handles it:** the MIT transform does **not** filter on the
  `writein` flag. Candidate scope (D007/D019) is enforced purely by
  `party_simplified ∈ {DEMOCRAT, REPUBLICAN}`, which retains named write-in-flagged
  major lines while still excluding the minor write-in long tail. See
  `_drop_unattributable_rows` in
  [`src/usvote/mit/transform.py`](../src/usvote/mit/transform.py) and its test
  `test_named_writein_major_candidate_is_retained`.
- **Suggested question for MIT:** is the `writein` flag on the 2020 DC rows intentional,
  or a coding artifact? If intentional, what does it denote there?

### A2 — 2024 DC and NY: `sum(candidatevotes)` ≠ `totalvotes` (inconsistent `totalvotes` semantics)

For 2024, two states' candidate rows do not sum to the reported state `totalvotes`
(`version` 2025-11-20); every other (year, state) cell in the file reconciles exactly:

| year | state | `sum(candidatevotes)` | `totalvotes` | difference |
|---|---|---|---|---|
| 2024 | DISTRICT OF COLUMBIA | 328,404 | 325,869 | **+2,535** |
| 2024 | NEW YORK | 8,380,555 | 8,381,429 | **−874** |

**Root cause (not a disputed/litigated result — checked; DC was a routine ~90% Harris
win).** In 2024 MIT itemizes ballot-disposition buckets — `UNDERVOTES`, `OVERVOTES`,
`VOID` — as their own pseudo-candidate rows (coded `party_simplified=OTHER`). The two
states then treat `totalvotes` **inconsistently** relative to those rows:

- **DC** — `totalvotes` (325,869) **excludes** the under/overvote rows, but the candidate
  sum **includes** them: `UNDERVOTES` 2,075 + `OVERVOTES` 460 = **2,535**, exactly the
  surplus. So `totalvotes` here = valid presidential ballots only.
- **NY** — `totalvotes` (8,381,429) appears **inclusive** (it exceeds the itemized sum),
  leaving an **874**-ballot residual present in `totalvotes` but not itemized in any row.
  So NY's `totalvotes` is defined oppositely to DC's, plus an unexplained 874.

- **How this pipeline handles it:** the `{DEMOCRAT, REPUBLICAN}` scope already drops every
  `OTHER` disposition row, so the transformed output is unaffected. The pre-filter
  reconciliation check (`assert_totals_reconcile`) treats these two as documented, *exact*
  expected discrepancies via `TOTALS_RECONCILIATION_EXCEPTIONS`, so the guard still fires
  if a future MIT re-release changes them or a new mismatch appears.
- **Suggested questions for MIT:** (1) Is `totalvotes` intended to include or exclude
  `UNDERVOTES`/`OVERVOTES`/`VOID`? DC and NY 2024 disagree. (2) What is NY 2024's 874-ballot
  residual (in `totalvotes` but not any itemized row)? (3) Is itemizing
  under/overvotes/void as `OTHER` "candidate" rows a 2024-only change, or intended going
  forward? (It affects anyone summing `candidatevotes`.)

### A3 — 66 unnamed non-write-in minor lines (1976–2016)

66 rows across 8 election years (1976, 1980, 1988, 1996, 2000, 2008, 2012, 2016) have a
**blank `candidate`** but `writein=False`. All are minor lines — `party_simplified` is
`OTHER` (65) or `LIBERTARIAN` (1); `party_detailed` values include INDEPENDENT,
NO PARTY AFFILIATION, CONSTITUTION PARTY, NOMINATED BY PETITION, etc. **None are
Democratic or Republican.**

- **How this pipeline handles it:** these are dropped as unattributable (no candidate to
  key on), which is safe because none fall in the `{DEMOCRAT, REPUBLICAN}` scope. As a
  guardrail, a *non-write-in* unnamed row coded DEMOCRAT/REPUBLICAN would raise rather
  than be dropped — none exist today, but it protects against a future mislabel.
- **Lower priority / possibly intentional:** a blank name for an aggregated "all other"
  or petition line may be by design. Worth confirming, but not a correctness risk here.

## How these are enforced in code

The machine-readable source of truth is [`src/usvote/mit/transform.py`](../src/usvote/mit/transform.py):
`TOTALS_RECONCILIATION_EXCEPTIONS` (A2), `_drop_unattributable_rows` + the
party-not-`writein` scoping via `EC_GETTER_PARTIES` (A1, A3). Each is locked by a test in
[`tests/unit/test_mit_transform.py`](../tests/unit/test_mit_transform.py).
