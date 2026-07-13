# Research: Popular-Vote Data Source Determination

> **Status: IN PROGRESS.** This is the E3 (issue #13) research deliverable. The MIT
> Election Lab source is characterized below (E3-S1, #15), and UCSB / American Presidency
> Project is now characterized alongside it (E3-S2, #16). Only the final consolidated
> recommendation (E3-S3, #20) remains. The dual-source direction is already decided — see
> [`decisions.md`](decisions.md) **D014** — so this doc records the evidence behind it and
> the open questions that gate the public API.

**Date started:** 2026-07-06 · **UCSB section added:** 2026-07-13

---

## 1. Summary of findings so far

The MIT Election Data + Science Lab presidential file is clean, well-structured, at the
right grain (state-level, per candidate), and openly published — an excellent modern core.
Its one hard limit is **coverage: it begins in 1976**, so it cannot on its own satisfy the
project's ~1824 MVP comparison window (D009). This is the empirical basis for the
**dual-source strategy (D014)**: MIT for the modern, API-eligible core; UCSB / American
Presidency Project for historical breadth (analysis-only, pending license).

## 2. MIT Election Lab — data characterization (E3-S1)

**Source file examined:** `~/Documents/Projects/data/presidential_vote_analysis/1976-2024-president.csv`
(downloaded by Fred; lives outside the repo, under the shared external data directory).

| Property | Value |
|---|---|
| Rows | 4,822 |
| Elections covered | **13 — 1976, 1980, …, 2024** (every 4 years) |
| Earliest year | **1976** (the coverage constraint) |
| Jurisdictions | 51 (50 states + DC) |
| Office | US President only |
| Grain | one row per **(year, state, candidate)** |
| Vote fields | `candidatevotes` (candidate's votes in that state), `totalvotes` (state total across all candidates) |
| Candidate metadata | `candidate`, `party_detailed`, `party_simplified`, `writein` (bool) |
| Geo metadata | `state_po` (USPS), `state_fips`, `state_cen`, `state_ic` |
| Housekeeping | `version`, `notes` |

**Strengths**
- State-level candidate totals are exactly the grain the fact table needs; national PV is a
  trivial roll-up (`sum(candidatevotes)` by year, or `sum` of state `totalvotes`).
- 50 states + DC aligns cleanly with the EC state dimension (DC has had electoral votes
  since 1964, so the modern-era join is 1:1 on geography).
- Covers both **modern EC/PV splits — 2000 and 2016** — so the headline modern flip analysis
  is fully supported by MIT alone.
- `writein` + party fields make it easy to filter to the MVP candidate scope (D007: only
  candidates who received electoral votes) and drop the minor-candidate long tail.

**Frictions to handle downstream**
- **Name format differs from the EC source.** MIT uses `"BIDEN, JOSEPH R. JR"`,
  `"TRUMP, DONALD J."`; the National Archives EC data uses `"Donald Trump"`. Reconciliation
  is the job of the canonical candidate key (D006 / issue #30, E2-S9).
- **Long tail grows steeply in recent cycles** — distinct candidate names per year run from
  16 (1976) to **167 (2024)**, mostly write-ins. Not a problem under D007 (filter to
  EC-getting candidates), but worth noting for anyone loading the raw file wholesale.

## 3. UCSB / American Presidency Project — data characterization (E3-S2)

**Source examined:** the APP election-statistics pages at
`https://www.presidency.ucsb.edu/statistics/elections/{year}` (index at
`/statistics/elections`). Raw HTML for **all 60 election years is already snapshotted
locally** at `~/Documents/Projects/data/presidential_vote_analysis/ucsb_raw/` (one
`{year}.html` per election 1789–2024, plus the index page). This pre-satisfies the E4
snapshot story (#34) — the parse/transform work builds on files already on disk, no live
scrape needed.

| Property | Value |
|---|---|
| Elections covered | **60 — every election 1789–2024** (the full MVP span and then some) |
| Earliest year | **1789** (reaches the entire ~1824 window and the pre-12th-Amendment era) |
| Jurisdictions | per-**state** rows (one row per state), plus a national total row |
| Office | US President |
| Grain | one row per **(year, state)** with candidate votes spread **across columns**, not one row per (year, state, candidate) as MIT is — melting required |
| Vote fields | per state: `TOTAL VOTE`; per candidate group: `Votes`, `%`, `EV` (electoral votes) |
| Candidate metadata | candidate name + party in the per-year header band; party also encoded by cell `bgcolor` |
| Format | one `<table class="table table-responsive">` per year; candidate column-groups built with `colspan`/`rowspan` multi-row headers; **the number of candidate groups drifts year to year** (e.g. 2 in 1876, 4 in 1824) |

**Strengths**
- **Coverage is the whole point.** 1789–2024 per state covers every pre-1976 election MIT
  cannot — including the decisive EC/PV splits of **1876 and 1888** and the **1824**
  contingent election. This is the historical-breadth half of D014 and the only source in
  hand reaching the ~1824 MVP floor (D009).
- Per-state grain with candidate `Votes` + `%` + `EV` is rich enough to roll up national PV
  and to cross-check against the EC spine's electoral counts.
- Already snapshotted locally, so ingestion is a pure parse/transform problem with no network
  fragility.

**Frictions to handle downstream (this is why E4 mirrors the EC scrape, not a CSV read)**
- **Wide, not long.** Candidates live in columns, so parsing must melt (year, state) × N
  candidate groups into per-(year, state, candidate) records — the same melt shape as the EC
  `votes_by_state` matrix.
- **Heavy era drift.** The count and layout of candidate column-groups changes every era; the
  `colspan`/`rowspan` header structure must be parsed generically, not by fixed column index.
  This is the core risk #35 calls out.
- **Missing popular vote by design.** Early elections mark states whose electors were **chosen
  by the legislature** (1824: Delaware, Georgia, Louisiana, New York, South Carolina, Vermont),
  with no PV — these must be flagged with provenance, **not** coerced to zero (D005/D014).
- **Name format differs from the Archives** (and from MIT), so UCSB names also reconcile via
  the canonical candidate/state keys (#30, #38).
- **Footnote/annotation rows** appear at table bottom (e.g. 1824's "elected by the House of
  Representatives") — parsing must not mistake them for data rows.

### License / redistributability finding

**Finding: treat UCSB as non-redistributable (`redistributable=false`) — analysis-only.**
This is the safe, defensible default and matches D008/D014; nothing found upgrades it.

- APP's About page carries only `Copyright © The American Presidency Project` and defers to
  **UCSB's general Terms of Use** — there is **no data-specific open license or reuse grant**.
- UCSB's Terms of Use are restrictive verbatim: *"Other materials accessible within UCSB Web
  space, without explicit permission, may not be copied, reproduced, republished, uploaded,
  posted, transmitted, or distributed in any way,"* with only a *"personal non-commercial home
  use"* download exception. Redistribution via a public API would fall under the general
  prohibition, and permission must be sought (`policy@ucsb.edu`).
- Consistent with D008's note of **no licensing reply to date**. Using UCSB for internal
  analysis (fair-use-adjacent, non-published) is fine; exposing UCSB-sourced rows on any
  public API surface is **not** cleared. Hence every UCSB row is tagged `source=UCSB`,
  `redistributable=false` (E4 / #37), and the D002 public surface excludes them (D014).

## 4. Other PV sources scanned (fallback context, not a second deep dive)

Lightweight per D008 — the point is a defensible comparison and a known fallback, not to
re-open the dual-source decision.

| Source | Coverage / grain | Format | License posture | One-line viability |
|---|---|---|---|---|
| **ICPSR Study 1 — US Historical Election Returns, 1824–1968** ([link](https://www.icpsr.umich.edu/web/ICPSR/studies/1)) | **county-level**, 1824–1968, all parties | structured data files (curated) | free **to ICPSR-member institutions**; not an open public-redistribution license | **Strongest fallback** if UCSB parsing stalls — cleaner structured returns reaching 1824, and Fred's MIT-affiliation may confer member access; finer (county) grain than we need, roll up to state. A companion study (ICPSR 79) covers **1788–1823**. |
| **Dave Leip's Atlas of U.S. Presidential Elections** ([uselectionatlas.org](https://uselectionatlas.org)) | state (and county) level, 1789–present | web / paid data downloads | **proprietary, paywalled**; explicitly not for redistribution | Authoritative and complete but commercial — usable as a **validation cross-check**, not a redistributable source. |
| **Wikipedia per-election articles** | state-level, 1789–present | HTML infobox/tables | **CC BY-SA** (redistributable *with* attribution + share-alike) | The only clearly **redistributable** historical option, but crowd-sourced provenance is below our citation bar; possible tie-breaker/gap-filler, not a primary. |
| **CQ Press — *Guide to U.S. Elections*** | state-level, comprehensive | print / licensed database | commercial license | Gold-standard reference; licensing cost + no bulk data feed make it impractical here. |

**Best fallback if the MIT path stalls or UCSB parsing proves intractable:** **ICPSR Study 1
(+ Study 79 for 1788–1823)** — structured, academically authoritative, reaches 1824 (and
earlier), and access is plausibly available through Fred's institutional affiliation. It
would not change the redistributability picture (still analysis-only, not an open license),
but it de-risks the *parsing* effort that is E4's main cost. UCSB remains the primary
historical source because its data is already snapshotted and its per-state grain matches the
spine; ICPSR is the insurance policy.

## 5. The coverage gap and why dual-source is required

MIT: **1976–2024** (13 elections). The MVP comparison window starts **~1824** (D009). Every
pre-1976 election in scope — including the historically decisive EC/PV splits of **1876 and
1888**, and the contingent election of **1824** — is outside MIT's range. UCSB / American
Presidency Project is (per Fred) the most complete PV dataset available and reaches back to
the early republic, but only as **raw HTML** requiring a scrape, with an **unresolved usage
license**. Hence D014: use both, with clearly separated roles and per-source provenance.

## 6. Open questions for MIT outreach (gate the public API)

These are the two questions the E3 recommendation (#20) needs answered before the public
API's coverage story (D002) is settled. Outreach is intentionally deferred until we have
analysis in hand back to at least 1976; the exact mechanics of outreach are still open.

1. **Usage license** — does MIT's license permit **redistribution via a public API**?
   ("open" is not specific enough; capture the exact license text/terms.) This is the gate
   on the D002 stretch goal.
2. **Coverage extension** — are there plans to extend the dataset **before 1976**? Even
   partial backfill would change the MIT-vs-UCSB division of labor.

### Outreach contacts (documented for when the time comes)

- **Zayne Sember** — https://www.linkedin.com/in/zaynesember/ — published the most recent MIT
  Election Lab dataset (the 1976–2024 president file); lead contact.
- **Sean Greene** — https://www.linkedin.com/in/sean-greene-a467097/ — additional contact.

## 7. What this unblocks

- **MIT PV ingestion** can be scoped against a known schema/grain (Section 2) — a clean CSV
  load, distinct from and much simpler than the UCSB scrape epic.
- **Canonical-key reconciliation** (#30) has a concrete second-source name format to design
  against.
- The **UCSB scrape epic** is confirmed as necessary and un-deferred (D014), since only it
  reaches the pre-1976 span of the MVP window.

## 8. Still to do

- [x] E3-S2 (#16) — characterize UCSB / American Presidency Project (coverage, grain, HTML
      structure across eras, license status) + note other alternatives. **Done (§3–§4).**
- [ ] E3-S3 (#20) — consolidate into the final recommendation, with the explicit MIT
      licensing finding and a per-source coverage/redistributability table.
