# Research: Popular-Vote Data Source Determination

> **Status: IN PROGRESS.** This is the E3 (issue #13) research deliverable. The MIT
> Election Lab source is characterized below (E3-S1, #15). UCSB / American Presidency
> Project evaluation (E3-S2, #16) and the final consolidated recommendation (E3-S3, #20)
> are still to come. The dual-source direction is already decided — see
> [`decisions.md`](decisions.md) **D014** — so this doc records the evidence behind it and
> the open questions that gate the public API.

**Date started:** 2026-07-06

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

## 3. The coverage gap and why dual-source is required

MIT: **1976–2024** (13 elections). The MVP comparison window starts **~1824** (D009). Every
pre-1976 election in scope — including the historically decisive EC/PV splits of **1876 and
1888**, and the contingent election of **1824** — is outside MIT's range. UCSB / American
Presidency Project is (per Fred) the most complete PV dataset available and reaches back to
the early republic, but only as **raw HTML** requiring a scrape, with an **unresolved usage
license**. Hence D014: use both, with clearly separated roles and per-source provenance.

## 4. Open questions for MIT outreach (gate the public API)

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

## 5. What this unblocks

- **MIT PV ingestion** can be scoped against a known schema/grain (Section 2) — a clean CSV
  load, distinct from and much simpler than the UCSB scrape epic.
- **Canonical-key reconciliation** (#30) has a concrete second-source name format to design
  against.
- The **UCSB scrape epic** is confirmed as necessary and un-deferred (D014), since only it
  reaches the pre-1976 span of the MVP window.

## 6. Still to do

- [ ] E3-S2 (#16) — characterize UCSB / American Presidency Project (coverage, grain, HTML
      structure across eras, license status) + note any other alternatives.
- [ ] E3-S3 (#20) — consolidate into the final recommendation, with the explicit MIT
      licensing finding and a per-source coverage/redistributability table.
