# Research: State-Population Source Determination

> **Status: COMPLETE.** This is the E10-S1 (issue #180) research deliverable. It characterizes the
> three candidate state-population sources named in #129 — the **Census Bureau's published tables**,
> **`api.census.gov`**, and **IPUMS NHGIS** — scans the fallbacks, resolves the apportionment-vs-
> resident series question, and delivers the **redistributable verdict** that gates E10-S2..S5
> (#181–#184). It mirrors the section structure of [`research-pv-source.md`](research-pv-source.md),
> the E3 deliverable that settled the PV sources, because #180's acceptance criteria require it.
>
> **The headline reverses #129's framing.** The epic was scoped around a trade — *clean-but-shallow
> public-domain vs. complete-but-restricted* — and expected NHGIS to be the likely full-history
> fallback, inheriting the UCSB analysis-only posture (D022/D030). **That trade does not exist for
> the series this project needs.** State **resident** population is available, public domain and
> fully structured, back to **1790**. NHGIS is not needed at all.
>
> **One correction rides along with it, and it is not optional.** That file reports every census on
> **present-day** state boundaries rather than as enumerated, so Virginia's denominator for the ten
> elections 1824–1860 omits the counties that became West Virginia — understating it by **12.7% to
> 21.3%**. Measured, not estimated (§4). It is a one-state, ten-election documented correction
> rather than a re-parse, which is why the recommendation stands; but a reader who takes the file at
> face value will produce plausible, wrong per-capita figures.
>
> **A different frontier appeared in place of the expected trade**, narrower and sharper:
> **apportionment population by state is not published as a column at all.** Seats are, back to
> 1789; the population behind them is national-only before 1910 and, from 1910, **derivable from
> seats × a rounded average rather than read off** — approximate by design. See §4.

**Date:** 2026-08-31 · **Method:** four parallel read-only research agents, one per source plus one
cross-cutting, each returning summaries with per-claim URLs and a verified/inferred label.

**How to read the evidence labels.** Every factual claim below is marked **VERIFIED** (an agent
fetched the artifact and read it) or **INFERRED** (reasoning from documentation or arithmetic). This
distinction is load-bearing: #129's own candidate list is explicitly *"working hypotheses to test,
not findings,"* and **two of its three hypotheses turned out wrong** (§8). Claims are not laundered
from one column to the other.

**Where the labels sit, and one deliberate exception.** §§3–8 carry per-claim labels; **§2 is a
comparison matrix whose cells are summaries of those sections**, and carries labels only where a cell
asserts something its section does not establish. **§§9–11 are
*derived* sections** — the fallback scan, the per-story consequences, and the checklist — and they
restate facts established and labeled upstream rather than introducing new evidence. Two rules keep
that from becoming a loophole: **a claim about an external artifact appearing first in §10 is
labeled inline** (they are marked below), and **§11 is an index with one admitted exception** —
every cell restates a section that carries the evidence, *except* the two rows tracking this
epic's own bookkeeping (open-question status and decision numbering), which have no natural home in
a source evaluation and are marked **"(stated first here)"** where they appear. Any *other* checklist
row saying something no earlier section does is a defect in the checklist, not a finding.

**A verification limit worth stating plainly.** The source characterizations in §§3–6 rest on the
research agents' fetches; the parent independently re-fetched only three artifacts —
`tabs15-65.xlsx` (downloaded and **parsed**, §4), `cph-2-1-1-table-3.pdf`, and
`apportionment-2020-tableC1.xlsx` (both HTTP-verified). **The §3 licensing table was not
independently re-fetched by the parent.** Every quote carries the URL it came from precisely so a
reader can discharge that themselves, which is the standard this document is held to rather than
one it claims to have already met.

---

## 1. Recommendation

**Adopt a single-source, two-file strategy on Census Bureau published tables. No dual-source split
is required, and NHGIS should not be used.**

- **US Census Bureau published tables — the whole answer, public domain, 1790–2020.** Resident
  population by state is available as genuinely structured XLSX for the full span, in two files
  that together cover it. This is both the per-capita denominator E10 needs and the series that
  reaches the 1824 EC floor.
- **`api.census.gov` — a convenience layer for 2000 onward only, not a spine.** Verified CC0, but
  its decennial floor is **2000** and it carries **no apportionment population at all**. Useful for
  cross-checking modern values; useless for a series that starts in 1824.
- **IPUMS NHGIS — do not use.** Its coverage is genuinely complete, but its restriction is
  **contractual and accepted at registration**, so it binds even though the underlying counts are
  uncopyrightable federal facts. Since the same numbers are obtainable unrestricted from census.gov,
  taking on that contract would buy nothing and cost the public surface. This is a *stronger*
  reason to decline than UCSB's, and it is worth stating plainly: **we would be choosing a
  restriction we do not have to accept.**

**Coverage floor: 1790 for resident population — the full EC span and then some.** #129's
hard-case worry (are the early censuses scanned PDFs?) resolves **favorably**: they are not. There
is a real XLSX.

**Answer to Open question 1 (the cost lever): OQ1's premise is void — take (a), not (b).** The
backlog recommended *(b) a modern clean public-domain window, deferring the hard historical parse*.
There is no hard historical parse to defer for resident population. **The recommended scope is the
full 1790–2020 series**, and the work is XLSX parsing, not OCR. OQ1's option (b) was insurance
against a cost that does not exist.

**Answer to Open question 4 (the redistributable branch plan): the branch is not taken.** #184
resolves to **Branch A** — the per-capita series may reach the snapshot and public API. There is no
restricted historical layer, because there is no need for a restricted source.

**Answer to Open question 2 (which series is authoritative): the backlog's recommendation stands,
and §7 explains why it is not a preference but a requirement.** Resident population is the
per-capita denominator; apportionment population is the seat-allocation input. They differ in
**every census year 1790–2020** without exception.

### Two constraints, and neither is the one anyone expected

**The first is the boundary basis.** The recommended file is a present-day-footprint
reconstruction, materially affecting Virginia across ten elections (§4). Measured, bounded, and
correctable in the `docs/corrections.md` pattern — with the residual sweep carved out as **#208**.
It is named here, in the section written to be read alone, because it produces *plausible numbers*
rather than an error — as do two others this document records, and they are worth naming together
since a reader guards against errors and not against plausibility: **§7's 2000 near-cancellation**
(the two population series agree to 2,271 people, by coincidence, so a spot-check on 2000 "confirms"
they are interchangeable) and **§4's two resident vintages**, which disagree by amounts that will
never trip an assert.

**The second is a coverage frontier**, and note there is a **third** requirement of the same silent
kind that is not a *constraint* on the source but on how it is read — the stitch year between the
two resident files (§4), which #181 must pin explicitly:

**Apportionment population by state is never published as a column.** Before 1910 census.gov gives
the apportionment base **nationally only** (Table B, VERIFIED). From 1910 the state-level files
publish *seats* and a **rounded average population per seat**, so the population is **derived and
approximate**, not structured — off by 25 persons on California 2020 (§4, VERIFIED by re-fetch).

This turns out **not to block E10**, and the reason is worth stating precisely, because it is the
difference between a blocked epic and an unblocked one: **#183's reconciliation does not need
apportionment population.** It needs *seats per state per census*, and those **are** published back
to **1789** — as a text-layer PDF that extracts cleanly (§4).

**But `seats + 2` is not an identity, and #183 must not be planned as though it were.** It is the
*rule*, with a documented exception list this repo can already enumerate — so the reconciliation is
unblocked for the full series only in the sense that the data exists for it, never in the sense that
it will reconcile cleanly. The exceptions are catalogued in §10 under #183; the largest is that
**14 `(year, state)` rows in our own EC fact carry `total_electoral_votes == 0` while the governing
census gave those states seats** (1864 and 1868 — the fixture proves it), so the naive identity
computes 13 against a stored 0. The affected years are **1864 and 1868** — 1872 has no zero-EV
row (§10).

So the pre-1910 apportionment-population gap costs us one thing only: we cannot *re-derive* the
apportionment from its own population base before 1910. We can still check the seat counts
themselves for the full series, which is the assert #129 calls "the epic's strongest validation."

---

## 2. Source comparison (head-to-head)

| Axis | **Census Bureau published tables** | **`api.census.gov`** | **IPUMS NHGIS** | ICPSR 2896 *(fallback)* |
|---|---|---|---|---|
| **Resident pop coverage** | **1790–2020, across two files** — 1790–1990 + 1910–2020, overlapping 1910–1990 at **different vintages** (§4) | 2000–2020 (decennial); 1990+ (estimates) | 1790–2020 | 1790–1970 (INFERRED — not characterized; ICPSR is disqualified on licence, §3, so its coverage was never assessed) |
| **Reaches the 1824 EC floor?** | ✓ | ✗ (starts 2000) | ✓ | ✓ |
| **Apportionment pop by state** | **never a published column** — national-only pre-1910; from 1910 **derived** as seats × rounded average, approximate (§4) | ✗ **none at all** | ✗ (resident only, INFERRED) | not assessed |
| **Seats per state per census** | **✓ 1789–2010** (+2020 separately) | ✗ | not assessed | not assessed |
| **Format** | XLSX (resident, both eras); CSV/XLSX (apportionment 1910+); text-layer PDF (seats 1789+) | JSON REST | extract-builder → CSV | data files |
| **Machine-readable pre-1900?** | **✓ XLSX** | n/a | ✓ | ✓ |
| **Boundary basis** | **modern state footprints, not as-enumerated** (§4) — a correction E10 must apply | not assessed (its span begins 2000, after the last relevant change) | harmonized (that is its selling point) | not assessed |
| **Effort to ingest** | medium — two resident XLSX + the apportionment CSV + Table 3 PDF + Table C1 XLSX, **plus the Virginia boundary correction** | low, but irrelevant at this span | low-medium, account required | gated |
| **Account / key required?** | **none** | **API key now mandatory** for all data queries | **yes, with a click-through licence** | membership |
| **License** | US Gov work, 17 U.S.C. §105 (statutory inference — see §3) | **CC0 1.0, declared machine-readably** | "You will not redistribute the data without permission" | "agree not to redistribute … without the written agreement of ICPSR" *(secondary read, flagged — §3)* |
| **Public-API redistributable?** | **YES** | **YES** | **NO** | **NO** |
| **Role** | **the spine** | modern cross-check | not used | not used |

---

## 3. Licensing finding (the D030 gate)

The public API surface (D030) may carry only redistributable data. Per-source verdict:

| Source | License (verbatim) | Redistributable via public API? | Basis |
|---|---|---|---|
| **`api.census.gov`** | Every dataset record in `data.json` carries a `license` field; across all **1,798** datasets the value is `https://creativecommons.org/publicdomain/zero/1.0/` (1,548), its `http://` variant (200), or a `.../1.0/unidentified` variant (50). **Every dataset carries a CC0 URL; none carries anything else.** | **YES — cleared, explicitly.** CC0 is a public-domain dedication; no permission, no attribution obligation. | `https://api.census.gov/data.json` dataset metadata, VERIFIED 2026-08-31 (confirmed individually for `2000 dec/sf1`, `2020 dec/pl`, `2020 dec/dhc`, `2019 pep/population`) |
| **Census Bureau published tables** | No census.gov page states in so many words that Census **data** is public domain. The governing statute: *"Copyright protection under this title is not available for any work of the United States Government…"* (17 U.S.C. §105(a)). The nearest agency statement is **scoped to software**: *"This Software was created by U.S. Government employees and therefore is not subject to copyright in the United States (17 U.S.C. §105)."* The data-facing statement is a **citation norm, not a licence**: *"Data users who create their own estimates using data from disseminated tables and other data should cite the Census Bureau as the source of the original data only."* | **YES — sound, but by statutory inference rather than an explicit data licence.** See the honesty note below. | 17 U.S.C. §105(a) (law.cornell.edu); census.gov X-13 software disclaimer; census.gov Public-Use Statement; file metadata carries `Author: U.S. Census Bureau` / Population Division (VERIFIED for `t3.pdf`, `taba.xls`, `tabb.xls`) |
| **IPUMS NHGIS** | *"All persons are granted a limited license to use data and documentation from IPUMS NHGIS, subject to the following conditions: **Redistribution**: You will not redistribute the data without permission. You may publish a subset of the data to meet journal requirements for accessing data related to a particular publication. Contact us for permission for any other redistribution… **Citation**: You will cite NHGIS appropriately. […] These terms of use are a legally binding agreement."* | **NO.** Publishing analysis **results** is permitted; republishing the **data** — via our API or in a public git repo — is not, absent written permission. | `https://www.nhgis.org/citation-and-use-nhgis-data`, identical at `https://www.ipums.org/about/terms` and `https://www.nhgis.org/ipums-nhgis-terms-use` — all VERIFIED |
| **ICPSR 2896** | Members *"agree not to redistribute data or other materials without the written agreement of ICPSR"*; redistribution requests go to the Data Stewardship Policy Committee. Also explicitly bars supplying data to LLMs that retain it. | **NO — disqualifying.** | `https://www.icpsr.umich.edu/sites/icpsr/about/policies/redistribution` (VERIFIED via search snippet — secondary read, flagged) |
| **HathiTrust / Internet Archive scans** | Underlying federal documents are public domain; the **platform's** terms and bulk-download rules are separate. | **Underlying data yes; not a practical source** — scans require OCR. | hathitrust.org copyright/access page |
| **Kaggle "US Population by State (1790–2024)"** | Third-party derivative; license not verified. | **Convenience only — never cite as provenance.** | — |

### Two honesty notes on the licensing verdict

**(1) The published files rest on statutory inference; the API data does not.** This asymmetry is
real and worth carrying forward. `api.census.gov` **declares** CC0 in machine-readable metadata on
every dataset. The static published files carry no equivalent declaration — their public-domain
status follows from 17 U.S.C. §105 applied to works authored by Census Bureau employees, which is
sound but is a legal inference we are making, not a grant the agency has written down for data.
USAGov is explicitly hedged on this point: *"Not everything that appears on a federal government
website is a government work… Content on federal websites may include protected intellectual
property used with the right holder's permission."* The files we propose to use all carry Census
Bureau authorship in their metadata (VERIFIED), which is what makes the inference safe here.

**This is the MIT/UCSB depth Fred approved, and every quote above carries the URL it came from**, so
the verdict is re-checkable rather than taken on trust.

**(2) NHGIS's restriction is contractual, which makes it stronger than UCSB's, not weaker.** The
underlying decennial counts are uncopyrightable federal facts — the same numbers from census.gov
carry no restriction whatever. But NHGIS presents its licence as a click-through at registration,
and the terms say *"the data,"* full stop, with **no carve-out separating its value-added products
(time series, crosswalks, GIS files) from the raw federal counts**. So the restriction binds by
agreement even where copyright would not reach. The practical consequence is the recommendation in
§1: there is no reason to accept a contract we can simply decline by using the primary source.

### API terms vs. data terms (`api.census.gov`)

These are distinct and the distinction matters operationally. The **data** is CC0 — nothing
propagates to consumers of data we republish. The **key** governs only our access channel: the ToS
*"Right to Limit"* clause lets Census throttle or block **our key**. Since a key is now mandatory
for every data query (VERIFIED — all unkeyed queries 302 to a "Missing Key" page), **a blocked or
rotated key would break ingest**. That is an argument for treating Census as a **build-time
snapshot input**, exactly as `USVOTE_EC_HTML_DIR` and the UCSB corpus already are (D023) — never a
serve-time dependency. The ToS also asks (as a *"should"*, not a *"must"*) that applications display:
*"This product uses the Census Bureau Data API but is not endorsed or certified by the Census
Bureau."* Recommend displaying it regardless if we ever use the API.

---

## 4. Census Bureau published tables — data characterization

**The recommended source.** Coverage, per era, with format — the AC that #129 flagged as the real
unknown:

| Series / era | Earliest | Format | URL | Status |
|---|---|---|---|---|
| **Resident pop by state** (POP-twps0056, Tables 15–65) | **1790–1990** — note the **1990 ceiling** | **XLSX** — real OOXML, 51 sheets (50 states + DC) | `https://www2.census.gov/library/working-papers/2002/demo/pop-twps0056/tabs15-65.xlsx` | **VERIFIED** — 329,123 B, content-type `spreadsheetml.sheet`, re-checked independently; values read (VA 1790 = 691,737, CT 1790 = 237,946) |
| Resident pop by state (Population Change) | 1910–2020 | XLSX / PDF | `https://www2.census.gov/programs-surveys/decennial/2020/data/apportionment/population-change-data-table.xlsx` | VERIFIED — header + rows parsed |
| **Seats + seat change + average apportionment population per seat**, by state — **not apportionment population itself** (see below) | 1910–2020 | **CSV**, XLSX, PDF | `https://www.census.gov/data/tables/time-series/dec/apportionment-data-text.html` → `apportionment.csv` | VERIFIED — earliest row 1910 |
| **Seats per state, full history** | **1789–2010** | **text-layer PDF**, 2 pp | `https://www2.census.gov/programs-surveys/decennial/1990/data/apportionment/cph-2-1-1-table-3.pdf` | **VERIFIED** — `pdftotext -layout` extracts cleanly |
| **Seats per state, 2020** (Table C1) — closes the 2020/2024 gap; the file spans 1910–2020, but only its **2020** column is needed, since Table 3 already covers 1789–2010 | 1910–2020 | XLSX | `https://www2.census.gov/programs-surveys/decennial/2020/data/apportionment/apportionment-2020-tableC1.xlsx` | **VERIFIED** — HTTP 200, 15,245 B, content-type `spreadsheetml.sheet` |
| Apportionment pop base + rep count — **NATIONAL only** | 1790 | legacy `.xls` + PDF | `https://www2.census.gov/programs-surveys/decennial/1990/data/apportionment/tabb.pdf` | VERIFIED — **no state dimension** |
| Forstall, *Population of States and Counties 1790–1990* | 1790 | **scanned PDF, unusable OCR** | `.../population-of-states-and-counties-of-the-united-states-1790-1990.pdf` | **VERIFIED unusable** — see below |
| *Historical Statistics, Colonial Times to 1970* (Ch. A) | 1610 | scanned PDF | `https://www2.census.gov/prod2/statcomp/documents/CT1970p1-01.pdf` | VERIFIED scanned |

### Correction: state apportionment population is **derivable, not published**

An earlier draft labeled the apportionment file *"apportionment pop + seats + seat change, by
state"* and marked it VERIFIED. **That was wrong, and the acceptance gate falsified it by fetching
the file.** Re-fetched and confirmed by the parent, 2026-08-31 — `apportionment.csv`'s columns are

> `Name, Geography Type, Year, Resident Population, Percent Change in Resident Population, Resident
> Population Density, Resident Population Density Rank, Number of Representatives, Change in Number
> of Representatives, Average Apportionment Population Per Representative`

— and the companion XLSX is titled *"Apportionment of Seats in the U.S. House of Representatives and
**Average Population Per Seat**: 1910 to 2020."* **No file in this set carries a state apportionment
population column.**

**It is back-derivable as `seats × average apportionment population per seat`, and that is lossy**,
because the published average is rounded to whole persons: California 2020 gives 52 × 761,091 =
**39,576,732** against a true apportionment population of **39,576,757** — off by **25**. Small, and
not small enough to launder: a reconciliation asserting equality against a derived figure fails on
rounding rather than on substance, which is the worst kind of failing assert.

**What survives and what does not.** The **1910 floor survives** — the CSV's earliest year is 1910,
verified — and so does everything §1 concludes, since the recommendation rests on the *resident*
series and #183 reads *seats*. What does not survive is the word **"structured"** applied to the
state apportionment series: it is **derived and approximate**, and #181's "carry both series"
requirement must say so rather than implying a column that can be read off.

**The national apportionment base remains exact** — Table B publishes it directly (1790–1990), which
is what §7's divergence table is built on. The gap is specifically **by state**.

**The scanned-PDF trap, with evidence.** The Forstall volume is the obvious-looking full-span source
and it is a trap. Its OCR text layer reads, verbatim: `Alabama 3,266,140` (true 1960 value
**3,266,740**), `Arizona ... 149.587` (true **749,587**), `Michigan ... 1.823,194` (true
**7,823,194**), `Maine ... 191.423` (true **797,423** — the value in `tabs15-65.xlsx`; an earlier
draft of this document wrote 791,423, a figure carried over from a research summary and never
re-checked, which is the very failure this paragraph warns about), plus `913.77~` and `Califomia`. The
corruption is systematic — 7→1 and comma→period. **Do not build on OCR of these volumes.** The
`tabs15-65.xlsx` path avoids them entirely, which is the single most useful finding in this document
for S2's cost.

> **One unresolved cross-check, recorded rather than smoothed over.** A second agent reported a
> Forstall **Part II `.xls`** at
> `https://www2.census.gov/programs-surveys/decennial/tables/1990/population-of-states-and-counties-us-1790-1990/population_partii.xls`
> returning HTTP 200 with `application/vnd.ms-excel`. That is a **different artifact** from the
> scanned PDF above, and it was verified only by **content-type, not by opening it**. It may be a
> perfectly good structured alternative. It is **not** the recommended path here, because
> `tabs15-65.xlsx` was verified by reading actual values out of it, and a source whose contents we
> have seen beats one whose headers we have seen. Worth ten minutes at S2 to check.

### The boundary-basis trap — the most consequential correction in this document

**`tabs15-65.xlsx` reports each census on *present-day* state boundaries, not as enumerated.** The
file proves it arithmetically: it carries **Virginia 1790 = 691,737 *and* West Virginia 1790 =
55,873**, which sum to **747,610** — exactly the enumerated 1790 Virginia. Likewise **Maine 1790 =
96,540 + Massachusetts 378,787 = 475,327**, exactly the enumerated 1790 Massachusetts, which then
included Maine.

**This is a reconstruction, and E10 must correct for it rather than consume it naively.** The
failure is quiet and it lands squarely on #184's per-capita series:

- **Virginia's denominator is wrong for every election it was apportioned for pre-1863.** Take the
  worst case *inside* the affected window — the **1850** census, which governed the 1852, 1856 and
  1860 elections: the file's Virginia (1,119,348) omits the 302,313 people in the counties that
  became West Virginia, understating the denominator by **21.3%** and so **overstating Virginia's
  per-capita electoral weight by ~27.0%**. (The 1860 census is larger still at 23.6%/+30.9%, but it
  first governed 1864 — a year Virginia held **zero** electoral votes — so quoting it would overstate
  the operative maximum. An earlier draft did exactly that.)
- **West Virginia gets a population for censuses in which it had no electoral votes**, which is a
  divide-by-zero or a spurious infinite-weight row rather than a number.

Neither shows up as a load error. Both produce plausible-looking figures, which is what makes this
the trap it is — and note it is the *same* class of defect as §7's 2000 near-cancellation: an
artifact that looks like a measurement.

**The as-enumerated figures are what E10 needs**, since the question is *how many people did this
state's electors actually stand for*.

#### How big is this, actually? Measured, not assumed

The first draft of this section recorded the defect and stopped there, which left #181 an
unactionable instruction. So the file was **downloaded and parsed** (329,123 B; 51 sheets; stdlib
`zipfile` + `xml.etree`, since the repo has no `openpyxl`) and the question answered directly.
**VERIFIED, by reading every state sheet:**

| Census | VA in file | WV in file | sum | enumerated VA | match | WV share |
|---|---|---|---|---|---|---|
| 1790 | 691,737 | 55,873 | 747,610 | 747,610 | **exact** | 7.5% |
| 1820 | 938,261 | 136,808 | 1,075,069 | — | — | 12.7% |
| 1830 | 1,044,054 | 176,924 | 1,220,978 | — | — | 14.5% |
| 1840 | 1,025,227 | 224,537 | 1,249,764 | — | — | 18.0% |
| 1850 | 1,119,348 | 302,313 | 1,421,661 | 1,421,661 | **exact** | 21.3% |
| 1860 | 1,219,630 | 376,688 | 1,596,318 | 1,596,318 | **exact** | 23.6% |

Three exact reconciliations against the enumerated Virginia settle the mechanism beyond argument.
(The intermediate censuses are left blank rather than filled from memory — the enumerated figures
for 1800–1840 were not re-verified from a primary source, and an approximate figure in a
match column would manufacture a discrepancy that is mine, not the file's.)

**The material scope, within the 1824–2024 EC span, is Virginia and only Virginia** — the sole
post-1824 transfer of a populous territory *between two states*. The error in Virginia's per-capita
denominator runs from **12.7%** (1820 census) to **21.3%** (1850 census), across the **ten**
elections from 1824 to 1860. From 1864 Virginia and West Virginia are separate in the record and in
the file alike, and Virginia holds zero electoral votes in 1864 and 1868 anyway.

**The second consequence is already handled by a decision this repo made years earlier.** The file
starts each state at the first census in which its modern footprint had a countable population —
Alabama and Michigan at 1800, Wisconsin at 1820, Arizona and Nevada at 1860 — so it supplies
population for many `(census, state)` pairs where the state held no electoral votes. That never
reaches a per-capita figure, because **E10 conforms to the EC participation roster (D006/D015)**
rather than to the population file's own state list: a state with no roster entry has no row to
divide into. Worth stating explicitly because it looks like a second defect and is in fact the
conformance requirement already doing its job. (Alaska and Hawaii are *not* backfilled — both start
at 1960 — so the file is not uniformly retroactive, which is one more reason not to infer its
behavior rather than read it.)

**So the correction is a `docs/corrections.md`-shaped entry, not a re-parse** — one state, ten
elections, one documented adjustment with provenance, exactly the pattern the repo already runs for
historical anomalies. This is what keeps the OQ1 answer standing: the boundary problem is real, and
it is *bounded*, and bounding it is what makes "no hard historical parse to defer" a claim about
measured scope rather than a hope.

**The residual, stated rather than buried.** Virginia is confirmed material and the minor post-1824
adjustments (the Toledo Strip, the Platte Purchase, assorted river-boundary moves) involve land that
was sparsely populated — but *"sparsely populated"* is a judgement here, not a measurement, and no
exhaustive sweep of all fifty states was run. **#208 carries that sweep**, with a clean done
condition; it is deliberately not folded into #181, because it is an analysis question and not an
ingestion step.

### The stitch point — two files, one overlap, two vintages

`tabs15-65.xlsx` **stops at 1990.** The 2000/2010/2020 columns come only from the popchange table.
So the resident series is **two files that overlap on 1910–1990**, and §7's vintage caveat is not a
separate curiosity — **it is a property of this overlap**: popchange gives 1910 = 92,228,531 where
the original publication gives 92,228,496.

**S2 must fix the stitch year and record which file wins in the overlap.** Recommendation: take
1790–1990 from `tabs15-65.xlsx` and 2000–2020 from popchange, so the overlap is never resolved by
accident and each census comes from exactly one file. Whatever is chosen must be written down, since
the two disagree by small amounts that will never trip an assert.

**Parsing cost, concretely (for S2's estimate).** `tabs15-65.xlsx` is one sheet per state; each sheet
holds a NUMBER block **and** a PERCENT block with duplicate year labels, plus interleaved
`. Sample` / `. 15% sample` sub-rows and `(NA)`/`(X)` sentinels. The apportionment and popchange
XLSX files are awkward differently: decade-blocks laid **side by side across columns**, repeating the
`State` column, with literal `"This cell is intentionally blank."` filler cells. All tractable; none
require OCR.

**The seats table has two verified parsing hazards** worth knowing before S3 estimates it: page 2
**reverses the layout** (year columns *precede* the state label), and the font encoding emits `l8`
for `18` (e.g. Michigan 1980). Missing states are `(X)`. The table stops at **2010** — 2020 seats
come from the separate Table C1 XLSX.

---

## 5. `api.census.gov` — data characterization

**Verified floor: 2000.** The full catalog (`data.json`, 5.2 MB, 1,798 datasets) contains 64 `dec/*`
datasets across exactly three vintages — **2000, 2010, 2020**. `/data/1990.json` resolves but lists
no `dec/*` dataset at all (only `cbp`, `cps/basic/*`, `pep/int_*`, `sipp/*`); `/data/1970.json` and
`/data/1980.json` return 404. Earliest decennial with state population: **`2000 dec/sf1`**, variable
**`P001001`**, with `{"name":"state","geoLevelDisplay":"040"}` in its geography. 2010 uses
`P001001`; 2020 uses `P1_001N`.

**No apportionment population, at all.** Grepping the entire 1,798-dataset catalog for `apportion`
yields exactly **one** hit — the word "apportioning" in an unrelated description. VERIFIED absent
from every dataset checked; INFERRED absent API-wide.

**Non-decennial reach-back is estimates, not counts.** `2000 pep/int_population` carries `POP`,
labeled verbatim *"Resident population"*, at state level. The 1990 intercensal set
(`pep/int_charagegroups`) has state data but its geography list is **`['county']` only** and it is
broken out by age/race/sex, so a state total requires aggregation. These are **annual model-based
estimates**, and must never be presented as enumerated census counts.

**A key is now mandatory** — every data query 302-redirects to a *"Missing Key"* page; the old
unkeyed small-query allowance is gone. Metadata endpoints remain unkeyed, which is how all of the
above was verified. **No actual data values were retrieved** (no key), so that queries return the
expected rows is INFERRED from verified metadata.

**Role:** a modern cross-check for 2000/2010/2020, and nothing more. At a span starting in 1824 it
cannot be the spine.

---

## 6. IPUMS NHGIS — data characterization

**Not recommended (§1), and characterized here anyway** — because "we did not use it" is only a
defensible finding if we established what we were declining.

**Coverage: genuinely complete.** The data-availability page states *"Decennial census data
(1790-2020)"*, *"County and state tables since 1790"*, and time-series tables of state and county
data *"that go back to 1790 for Total Population"* (VERIFIED,
`https://www.nhgis.org/data-availability`). No gaps for our use. This is the one axis on which NHGIS
genuinely beats every alternative on convenience: a single harmonized extract rather than two files
plus a PDF.

**Series: resident population only** (INFERRED — nothing on the availability page mentions
apportionment population, and NHGIS republishes the published decennial tables). So it does **not**
close the pre-1910 apportionment gap that §4 leaves open, which removes the one reason we might have
tolerated its terms.

**Format and effort:** an extract-builder producing CSVs via an email-notified asynchronous job;
an account is required to extract, though browsing and building are not. There is an official API
with R (`ipumsr`) and Python clients, though `https://www.nhgis.org/api` itself 404s as of
2026-08-31 (VERIFIED). A one-time pull of state total population for all decennials is roughly
30–60 minutes, mostly spent selecting tables.

**Registration is where the restriction attaches.** The same licence is presented as a click-through
at signup (`https://uma.pop.umn.edu/nhgis/user/new`, VERIFIED):

> "IPUMS NHGIS data are available free of charge. Before using the data, researchers must complete
> this registration and agree to abide by the usage license specified below. […] By completing this
> registration, you agree to the following terms of use. **Redistribution: You will not redistribute
> the data without permission.**"

The form collects name, institution, occupation, field of research, and a research statement. IPUMS
user agreements are valid for one year and may be renewed (VERIFIED, `ipums.org/about/terms`).

**Why this is a firmer bar than UCSB's, restated because it is the crux.** UCSB's is a copyright
assertion over its own presentation. NHGIS's is a **contract we would sign**, and its terms say
*"the data,"* with no carve-out separating NHGIS's value-added products from the raw federal counts
underneath. The nearest adjacent statement — the IPUMS producers table's *"Primarily public use
data, plus agreements with research groups"* (VERIFIED, `ipums.org/producers`) — describes IPUMS's
**upstream** rights, not ours. Since 17 U.S.C. §105 means the same counts are unrestricted from
census.gov, obtaining them from NHGIS would convert public-domain facts into contractually
restricted ones **by our own act**. That is the whole argument for §1's recommendation.

**Permission is available for the asking, and we should not need to ask.** The terms invite requests
and say IPUMS *"will consider requests for free and commercial redistribution"* — so an
asked-for yes is plausible, as it was for MIT. It is simply unnecessary here.

---

## 7. The two population series — and why carrying one is the failure mode

The most authoritative single statement is footnote 1 of Census Bureau **Table B**, *"Population
Base for Apportionment and the Number of Representatives Apportioned: 1790 to 1990"* (VERIFIED):

> "Excludes the population of District of Columbia; the population of the territories; prior to
> 1940, the number of American Indians not taxed; and, prior to 1870, two-fifths of the slave
> population. In 1990 and 1970, includes selected segments of Americans abroad."

| Rule | Era (census years) | Effect on the apportionment base | Status |
|---|---|---|---|
| **Three-fifths clause** (Art. I §2 cl. 3) | **1790–1860**; superseded by 14th Am. §2 (ratified 1868), so **1870 is the first census without it** | subtracts **2/5 of each state's enslaved population** | VERIFIED |
| **"Indians not taxed"** (in **both** Art. I §2 cl. 3 and 14th Am. §2 — the 14th removed the slave fraction, **not** this clause) | **1790–1930**; ends at the **1940** census | subtracts untaxed American Indians | VERIFIED |
| **District of Columbia** | **every year, 1790–2020** | DC's entire resident population excluded | VERIFIED |
| **Territories** (incl. pre-statehood AK/HI, PR) | every year | excluded until the year of statehood | VERIFIED |
| **Overseas federal personnel** | **1900** (one-time), **1970**, **1990**, **2000**, **2010**, **2020**; **not** 1910–1960, **not 1980** | **adds** to the base; never in resident population or sub-state data | VERIFIED |
| **1920 — no apportionment at all** | 1920 | Congress passed no apportionment act; Table B shows `…` | VERIFIED (Table B fn. 5) |

### Correction to our own working note: "Indians not taxed" ended with 1930, not 1940

Our note said the exclusion ran *"through 1940."* **It is off by one census.** The Bureau's footnote
says *"prior to 1940,"* and its historical-perspective page says *"In 1940, it was determined that
there were no longer any American Indians who should be classed as 'not taxed.'"* So **1930 is the
last census that excluded them; 1940 is the first that did not.**

The arithmetic corroborates exactly (INFERRED, but the residual is zero to the person): for **1940**,
apportionment base 131,006,184 against resident 132,165,129 leaves 1,158,945 — which is *precisely*
DC (663,091) + Alaska (72,524) + Hawaii (423,330), with **nothing left over** for an Indian
exclusion. The same reconciliation leaves ~194,722 unexplained in 1930 and ~37,425 in 1910. The
exclusion is live in 1930 and dead in 1940.

**Do not attribute the change to the Indian Citizenship Act of 1924** — the 1930 base still excluded
them. Census attributes it to a determination made in 1940. (Secondary sources name a 1940 opinion
of Attorney General Robert Jackson; the Bureau itself does not name him, so treat the attribution as
secondary.)

### The two series differ in every census year, 1790–2020

There is **no era in which they are identical**, because DC is always excluded. **The table below is
illustrative, not exhaustive** — 1870–1900 and 1950 are omitted for space, and the claim rests on the
always-excluded-DC argument rather than on the rows shown. This is why the
schema must carry both and label which is which — the "carrying only one is the failure mode" point
#129 made, now with the evidence behind it:

| Census | Apportionment base | Resident (50 st. + DC) | Difference | Dominant driver |
|---|---|---|---|---|
| 1790–1860 | 3,615,823 → 29,550,038 | 3,929,214 → 31,443,321 | **−6.0% to −9.1%** | 2/5 enslaved + DC + territories + Indians |
| 1910 | 91,603,772 | 92,228,531 | −624,759 | DC+AK+HI (587,334) + ~37k Indians |
| 1920 | *(no apportionment)* | 106,021,568 | n/a | — |
| 1930 | 122,093,455 | 123,202,660 | −1,109,205 | DC+AK+HI (914,483) + ~195k Indians |
| 1940 | 131,006,184 | 132,165,129 | −1,158,945 | DC+AK+HI **exactly**; Indians = 0 |
| 1960 | 178,559,217 | 179,323,175 | −763,958 | DC only (AK/HI now states) |
| **1970** | 204,053,025 | 203,211,926 | **+841,099** | overseas exceeds DC — **sign flips** |
| 1980 | 225,867,174 | 226,545,805 | −678,631 | DC only; **no overseas** |
| 1990 | 249,022,783 | 248,709,873 | **+312,910** | overseas (919,810) − DC |
| 2000 | 281,424,177 | 281,421,906 | **+2,271** | overseas ≈ DC — **near-cancellation, a coincidence** |
| 2010 | 309,183,463 | 308,745,538 | **+437,925** | overseas (1,039,648) − DC (601,723) |
| 2020 | 331,108,434 | 331,449,281 | −340,847 | DC (689,545) > overseas (348,698) |

**The 1790–1860 row is computed, and its basis is stated** — 1790 = −8.0%, 1810 = −9.1%, 1860 =
−6.0%, from the Table B bases against standard resident totals (apportionment bases VERIFIED; the
percentages are arithmetic, hence INFERRED). An earlier draft of this document gave the band as
"−4% to −6%", which **excluded both endpoints of the era it described** and understated the
divergence in precisely the years §7 calls most dangerous. It was the one figure in the table
carrying no evidence label, and it was the one that was wrong — which is the argument for the
labeling discipline, made against this document rather than for it.

**2000 is the trap in this table.** The two series agree to within 2,271 people out of 281 million —
close enough that a spot-check on 2000 would "confirm" that the series are interchangeable. They are
not; the near-cancellation of overseas personnel against DC is arithmetic coincidence, and 1970's
sign flip is the proof.

**The rule for E10:** use **resident** population as the per-capita denominator (#184), and
**apportionment** population only where the question is *why does this state have this many seats*
as population arithmetic — which is **not** what #183 does: that reconciliation reads published
**seat counts** (§10), so it needs no apportionment population at all. Never use the apportionment base for per-capita work: it drops DC entirely and,
before 1868, undercounts enslaved states by two-fifths of the people held in slavery there.

**One measurement caveat, VERIFIED.** census.gov publishes more than one **vintage** of resident
population. The popchange table gives 1910 = 92,228,531 and 1970 = 203,211,926, whereas the commonly
cited original publications give 92,228,496 and 203,302,031. **S2 must pin a vintage explicitly and
record which**, exactly as the EC pipeline pins its Archives corpus.

---

## 8. The #129 hypotheses, tested

The issue named three candidates as hypotheses to verify. Recording the results explicitly, since
two are wrong and one is right-for-the-wrong-reason:

| #129's hypothesis | Verdict | What is actually true |
|---|---|---|
| *"`api.census.gov` is expected to cover only the recent decennials, not the 19th century. Verify rather than assume."* | **Right, and worse than expected** | The floor is **2000**, not 1990. `/data/1990.json` resolves but contains **no `dec/*` dataset at all**; `/data/1970.json` and `/1980.json` are 404. VERIFIED. |
| *"Whether these are available as structured downloads or only as PDF/scanned tables for the early censuses is exactly the unknown."* | **WRONG — the good direction, with one string attached** | Pre-1900 state resident population **is** a real structured XLSX (`tabs15-65.xlsx`, 51 sheets, OOXML). VERIFIED by reading values. **But the figures are on modern state boundaries, not as enumerated** — the very value that proves the file is readable, Virginia 1790 = 691,737, is *also* the value that proves the reconstruction, since it needs West Virginia's 55,873 added to reach the enumerated 747,610 (§4). Structured, yes; ready to use as-is, no. |
| *"IPUMS NHGIS … is the likely fallback … If it becomes the source, the population dimension inherits the UCSB posture."* | **WRONG — not needed** | NHGIS's coverage claim is accurate, but census.gov covers the same span unrestricted, so the fallback is never reached. |

**A third correction, to this repo's own working note rather than to #129.** Our note that "Indians
not taxed" were excluded from apportionment counts *"through 1940"* is **off by one census**. The
exclusion applied **through 1930** and ended **with the 1940 census**. See §7 — it is corroborated
both by the Bureau's own footnote and by exact arithmetic.

---

## 9. Other sources scanned (fallback context)

- **ICPSR 2896** — the upstream of most NHGIS pre-1970 tables. **Disqualifying**: members *"agree not
  to redistribute data or other materials without the written agreement of ICPSR."* Notably, its
  policy also explicitly bars supplying the data to LLMs that retain it.
- **HathiTrust / Internet Archive** — scans of the original decennial volumes. The underlying federal
  documents are public domain, but the machine-readability is OCR-of-scans, i.e. the §4 trap. Good
  for **citation and human verification**, unusable as an ingest source.
- **Library of Congress census guides** — scans and finding aids; US Government work, public domain.
  Same limitation.
- **Kaggle "US Population by State (1790–2024)"** — a tidy CSV in exactly the shape we want, which is
  precisely why it is dangerous: it is a third-party derivative with unverified license and unknown
  provenance. **Convenience cross-check at most; never a cited source.**

---

## 10. What this unblocks, story by story

**#181 (E10-S2 — ingest).** Unblocked, and **cheaper than the backlog feared**. Shape: one clean
load per file, no OCR stage, so the feared snapshot + parse + transform split is **not** required for
the resident series. **Five** concrete requirements this research adds:
- **Snapshot the source files locally** (the D023 pattern, alongside `USVOTE_EC_HTML_DIR` and the
  UCSB corpus) — mandatory rather than nice-to-have, because the API path now needs a key and the
  published files can be re-issued.
- **Pin the resident-population vintage** and record it, per §7's caveat.
- **Carry both series with an explicit label**, per §7 — and note that they are available over
  *different spans*, so the schema must tolerate apportionment population being absent pre-1910
  rather than treating that as a load failure.
- **Apply the boundary correction for Virginia, 1824–1860** (§4), or record loudly that it is uncorrected. `tabs15-65.xlsx` is
  built on **modern** state footprints, so pre-1863 Virginia excludes the West Virginia counties it
  was actually apportioned for, and West Virginia carries population in censuses where it held no
  electoral votes. This is the **only one of the five that silently produces wrong numbers
  rather than a load error**, and it is the one most likely to be missed, since the file is otherwise
  exemplary. The schema should carry the basis as a labeled attribute the way `pv_status` labels
  coverage — a figure whose basis is not stated is the D005 problem in a new place. Scope is
  **measured**: one state, ten elections, 12.7%–21.3% (§4). Residual sweep: **#208**.
- **Fix the stitch year between the two resident files and write it down** (§4).

**#182 (E10-S3 — conform + the governing-census mapping).** Unblocked and unchanged. This research
adds one input: the seats-per-state table's own hazards (§4) matter here, since page 2's reversed
layout and the `l8`/`18` encoding bug are exactly the kind of silent corruption a conforming step
should catch rather than propagate.

**#183 (E10-S4 — reconciliation).** **The seat data exists for the full 1789–2024 series** — that is
the finding, and it is what most changes the epic's value, since the reconciliation runs against
**published seat counts** rather than a re-derived apportionment, so the pre-1910
apportionment-population gap never reaches it.

**But do not plan this story as `seats + 2 == total_electoral_votes`.** That is the rule, not an
identity, and this repo can already enumerate its exceptions. Written as a bare assert it fails on
its first run, on rows we know about in advance. Five things this research pins for its ACs:

- **14 rows where a state has seats but zero electoral votes.** `tests/fixtures/ec_state_roster_by_year.json`
  records `total_electoral_votes == 0` for **11 states in 1864** (the Confederate states) and **3 in
  1868** (Mississippi, Texas, Virginia). All held apportioned seats under the governing **1860**
  census — 1868 still ran on the 1860 apportionment, the 1870 census first governing 1872 — and
  Virginia reads `11` in Table 3's 1860 column (VERIFIED — the fixture counts are VERIFIED against
  the repo; the Table 3 readings in this bullet and the three that follow are VERIFIED by the agent
  that extracted the PDF, not re-checked by the parent) — so the naive identity computes 13 against
  a stored 0 for Virginia — and 7 against 0 for Mississippi (5 seats), 6 against 0 for Texas (4). The
  affected years are **1864 and 1868 only**: the fixture has no zero-EV rows in 1872, so this is not
  "every Reconstruction year". These are **not** data errors: they are the Reconstruction exclusions the EC fact
  states correctly, and the reconciliation must treat them as expected, in the `docs/corrections.md`
  pattern.
- **West Virginia fails in the opposite direction, which is why a one-sided rule is not enough.** It
  is `(X)` in Table 3's 1860 seats column, yet appears in the 1864 and 1868 rosters as a
  participating state **absent from `zero_ev_states`** — i.e. holding electoral votes. (The fixture
  deliberately carries **no** electoral-vote counts, per D024 §5, so it establishes *that* West
  Virginia had votes, never *how many*; the count itself lives in `dwh.votes`.) So the assert must tolerate both *seats without electoral votes* and *electoral votes
  without seats*, and the second is the case a "missing state" guard would silently pass.
- **The seats source is inconsistent about mid-decade admissions** (VERIFIED by extraction), and this is the actual hazard
  rather than a curiosity: Nevada and Nebraska are **retroactively filled in** at 1 seat in the 1860
  column, while West Virginia is **not**. The table cannot be read as a uniform statement of "seats
  as of that census". Likewise the **1950 column sums to 437, not the 435 actually apportioned**,
  because Alaska and Hawaii are retroactively included — which is precisely what makes the 1960
  election's 537 electors reconcile, so it is load-bearing rather than noise.
- **DC must be special-cased**: it is `(X)` in every apportionment table and holds 3 electoral votes
  since 1964 that are not census-apportioned. The issue already names the +2 senatorial offset; DC is
  the second, separate correction.
- **1920 — get the right table.** Congress passed no apportionment act after the 1920 census, so the
  1924/1928 elections ran on the 1910 apportionment; this is the factual core of the blog series'
  `APPORT-1920-failure` instance, now confirmed against the Bureau's own table. **But the `…` is in
  Table B (apportionment *population*), not in the seats table** — and #183 does not read Table B.
  The seats table's 1920 column is **fully populated, repeating the 1910 seats verbatim** (US 435,
  NY 43, Maine 4, Michigan 13 — VERIFIED by extraction). A guard written for a missing 1920 row would never fire, and might
  mishandle the real duplicated column it does find.

**#184 (E10-S5 — expose).** Resolves to **Branch A** — public-domain source, so the per-capita
series may reach the snapshot and the public API, with the `SNAPSHOT_SCHEMA_VERSION` bump, the `/v1`
route and the model↔column drift guard that shape describes. Branch B and its structural guard are
**not** needed. The series it exposes must be built on **resident** population (§7).

**Post 4 (`CLAIM-538-is-a-choice` / `APPORT-per-capita-drift`).** The blocked payoff instance is
unblocked for the **full span**, not a modern window — so the per-capita drift can be shown from
1790 rather than from 2000. Post 4 still does not need to wait: it ships on its two `record`
instances and gains this as a later revision, exactly as the ledger planned.

**Nothing here needs a new source-namespacing decision.** `usvote/census/` remains a sibling
subpackage conforming to the EC spine (D006/D015), as the backlog specified.

---

## 11. Story checklist

| Story | Status after this finding |
|---|---|
| **#180 (S1)** — this document | **Complete** |
| **#181 (S2)** — ingest | Unblocked; scope **confirmed** as a clean multi-file load, no OCR stage. Add **five** requirements: local snapshot (D023), pinned vintage, both series over different spans, the **stitch year** between the two resident files, and the **boundary correction** for Virginia 1824–1860 (§4) — the last is the only one of the five that fails silently. Residual sweep: **#208** |
| **#182 (S3)** — conform + governing-census map | Unblocked; unchanged in shape |
| **#183 (S4)** — reconciliation | Seat data exists **for 1789–2024**, but `seats + 2` is a **rule with a known exception list, not an identity** — 14 zero-EV rows in 1864/1868, West Virginia failing the other way, retroactive mid-decade fills (NV/NE 1860, and 1950 summing to 437), DC, and the 1920 column being **populated** rather than missing (§10) |
| **#184 (S5)** — expose | Resolves to **Branch A**, public surface permitted |
| **Open questions** *(OQ3/OQ5/OQ6 statuses stated first here)* | **OQ1** premise void → take full span, not a modern window. **OQ2** confirmed with a correction: resident for per-capita; #183's seat reconciliation reads published **seat counts** and needs no apportionment population at all (§7, §10), and the by-state apportionment series is derived-and-approximate in any case (§4). **OQ4** branch not taken. **OQ3** (schema placement) still open — an architect call at S2, as the backlog said. **OQ5/OQ6** already answered on #129 |
| **Candidate decisions** *(stated first here — §§1–10 do not cover decision numbering)* | Record as **D058–D062** (the backlog's D053–D057 slots were taken 2026-08-27..30). Confirm the next free slot at recording time |
