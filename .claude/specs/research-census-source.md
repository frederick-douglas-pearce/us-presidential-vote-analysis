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
> **A different frontier appeared in its place**, and it is narrower and sharper: **apportionment
> population by state is structured only back to 1910.** See §7.

**Date:** 2026-08-31 · **Method:** four parallel read-only research agents, one per source plus one
cross-cutting, each returning summaries with per-claim URLs and a verified/inferred label.

**How to read the evidence labels.** Every factual claim below is marked **VERIFIED** (an agent
fetched the artifact and read it) or **INFERRED** (reasoning from documentation or arithmetic). This
distinction is load-bearing: #129's own candidate list is explicitly *"working hypotheses to test,
not findings,"* and **two of its three hypotheses turned out wrong** (§8). Claims are not laundered
from one column to the other.

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
resolves to **shape (A)** — the per-capita series may reach the snapshot and public API. There is no
restricted historical layer, because there is no need for a restricted source.

**Answer to Open question 2 (which series is authoritative): the backlog's recommendation stands,
and §7 explains why it is not a preference but a requirement.** Resident population is the
per-capita denominator; apportionment population is the seat-allocation input. They differ in
**every census year 1790–2020** without exception.

### The one genuine constraint, and it is not the one anyone expected

**Apportionment population by state is structured only from 1910.** Before that, census.gov
publishes the apportionment base **nationally only** (Table B). VERIFIED.

This turns out **not to block E10**, and the reason is worth stating precisely, because it is the
difference between a blocked epic and an unblocked one: **#183's reconciliation does not need
apportionment population.** It needs *seats per state per census*, and those **are** published back
to **1789** — as a text-layer PDF that extracts cleanly (§4). Seats + 2 is the electoral-vote
allotment, which is exactly what #183 reconciles against `dwh.votes.total_electoral_votes`.

So the pre-1910 apportionment-population gap costs us one thing only: we cannot *re-derive* the
apportionment from its own population base before 1910. We can still check the seat counts
themselves for the full series, which is the assert #129 calls "the epic's strongest validation."

---

## 2. Source comparison (head-to-head)

| Axis | **Census Bureau published tables** | **`api.census.gov`** | **IPUMS NHGIS** | ICPSR 2896 *(fallback)* |
|---|---|---|---|---|
| **Resident pop coverage** | **1790–2020** | 2000–2020 (decennial); 1990+ (estimates) | 1790–2020 | 1790–1970 |
| **Reaches the 1824 EC floor?** | ✓ | ✗ (starts 2000) | ✓ | ✓ |
| **Apportionment pop by state** | **1910–2020 only** | ✗ **none at all** | ✗ (resident only, INFERRED) | not assessed |
| **Seats per state per census** | **✓ 1789–2010** (+2020 separately) | ✗ | not assessed | not assessed |
| **Format** | XLSX (resident, both eras); CSV/XLSX (apportionment 1910+); text-layer PDF (seats 1789+) | JSON REST | extract-builder → CSV | data files |
| **Machine-readable pre-1900?** | **✓ XLSX** | n/a | ✓ | ✓ |
| **Effort to ingest** | medium — multi-block XLSX + one PDF table parse | low, but irrelevant at this span | low-medium, account required | gated |
| **Account / key required?** | **none** | **API key now mandatory** for all data queries | **yes, with a click-through licence** | membership |
| **License** | US Gov work, 17 U.S.C. §105 (statutory inference — see §4) | **CC0 1.0, declared machine-readably** | "You will not redistribute the data without permission" | "agree not to redistribute … without the written agreement of ICPSR" |
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
| **Resident pop by state** (POP-twps0056, Tables 15–65) | **1790** | **XLSX** — real OOXML, 51 sheets (50 states + DC) | `https://www2.census.gov/library/working-papers/2002/demo/pop-twps0056/tabs15-65.xlsx` | **VERIFIED** — 329,123 B; values read (VA 1790 = 691,737, CT 1790 = 237,946) |
| Resident pop by state (Population Change) | 1910 | XLSX / PDF | `https://www2.census.gov/programs-surveys/decennial/2020/data/apportionment/population-change-data-table.xlsx` | VERIFIED — header + rows parsed |
| Apportionment pop + seats + seat change, by state | 1910 | **CSV**, XLSX, PDF | `https://www.census.gov/data/tables/time-series/dec/apportionment-data-text.html` → `apportionment.csv` | VERIFIED — earliest row 1910 |
| **Seats per state, full history** | **1789** | **text-layer PDF**, 2 pp | `https://www2.census.gov/programs-surveys/decennial/1990/data/apportionment/cph-2-1-1-table-3.pdf` | **VERIFIED** — `pdftotext -layout` extracts cleanly |
| Apportionment pop base + rep count — **NATIONAL only** | 1790 | legacy `.xls` + PDF | `https://www2.census.gov/programs-surveys/decennial/1990/data/apportionment/tabb.pdf` | VERIFIED — **no state dimension** |
| Forstall, *Population of States and Counties 1790–1990* | 1790 | **scanned PDF, unusable OCR** | `.../population-of-states-and-counties-of-the-united-states-1790-1990.pdf` | **VERIFIED unusable** — see below |
| *Historical Statistics, Colonial Times to 1970* (Ch. A) | 1610 | scanned PDF | `https://www2.census.gov/prod2/statcomp/documents/CT1970p1-01.pdf` | VERIFIED scanned |

**The scanned-PDF trap, with evidence.** The Forstall volume is the obvious-looking full-span source
and it is a trap. Its OCR text layer reads, verbatim: `Alabama 3,266,140` (true 1960 value
**3,266,740**), `Arizona ... 149.587` (true **749,587**), `Michigan ... 1.823,194` (true
**7,823,194**), `Maine ... 191.423` (true **791,423**), plus `913.77~` and `Califomia`. The
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

There is **no era in which they are identical**, because DC is always excluded. This is why the
schema must carry both and label which is which — the "carrying only one is the failure mode" point
#129 made, now with the evidence behind it:

| Census | Apportionment base | Resident (50 st. + DC) | Difference | Dominant driver |
|---|---|---|---|---|
| 1790–1860 | 3,615,823 → 29,550,038 | — | **−4% to −6%** | 2/5 enslaved + DC + territories + Indians |
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

**2000 is the trap in this table.** The two series agree to within 2,271 people out of 281 million —
close enough that a spot-check on 2000 would "confirm" that the series are interchangeable. They are
not; the near-cancellation of overseas personnel against DC is arithmetic coincidence, and 1970's
sign flip is the proof.

**The rule for E10:** use **resident** population as the per-capita denominator (#184), and
**apportionment** population only where the question is *why does this state have this many seats*
(#183, 1910+). Never use the apportionment base for per-capita work: it drops DC entirely and,
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
| *"Whether these are available as structured downloads or only as PDF/scanned tables for the early censuses is exactly the unknown."* | **WRONG — the good direction** | Pre-1900 state resident population **is** a real structured XLSX (`tabs15-65.xlsx`, 51 sheets, OOXML). VERIFIED by reading values: Virginia 1790 = 691,737. No OCR required. |
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
the resident series. Three concrete requirements this research adds:
- **Snapshot the source files locally** (the D023 pattern, alongside `USVOTE_EC_HTML_DIR` and the
  UCSB corpus) — mandatory rather than nice-to-have, because the API path now needs a key and the
  published files can be re-issued.
- **Pin the resident-population vintage** and record it, per §7's caveat.
- **Carry both series with an explicit label**, per §7 — and note that they are available over
  *different spans*, so the schema must tolerate apportionment population being absent pre-1910
  rather than treating that as a load failure.

**#182 (E10-S3 — conform + the governing-census mapping).** Unblocked and unchanged. This research
adds one input: the seats-per-state table's own hazards (§4) matter here, since page 2's reversed
layout and the `l8`/`18` encoding bug are exactly the kind of silent corruption a conforming step
should catch rather than propagate.

**#183 (E10-S4 — reconciliation).** Unblocked **for the full 1789–2024 series**, which was not
obvious before this research and is the finding that most changes the epic's value. The reconciliation
runs against **published seat counts**, not against a re-derived apportionment, so the pre-1910
apportionment-population gap does not reach it. Two things this research pins for its ACs:
- **DC must be special-cased**: it is `(X)` in every apportionment table and holds 3 electoral votes
  since 1964 that are not census-apportioned. The issue already names the +2 senatorial offset; DC is
  the second, separate correction.
- **1920 has no apportionment**, so the 1924/1928 elections ran on the 1910 apportionment. Any
  reconciliation that expects a 1920 row will find `…` and must treat it as expected, not missing.
  This is also the factual core of the blog series' `APPORT-1920-failure` instance, now confirmed
  against the Bureau's own table.

**#184 (E10-S5 — expose).** Resolves to **shape (A)** — public-domain source, so the per-capita
series may reach the snapshot and the public API, with the `SNAPSHOT_SCHEMA_VERSION` bump, the `/v1`
route and the model↔column drift guard that shape describes. Shape (B) and its structural guard are
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
| **#181 (S2)** — ingest | Unblocked; scope **confirmed** as a clean multi-file load, no OCR stage. Add: local snapshot (D023), pinned vintage, both series with different spans |
| **#182 (S3)** — conform + governing-census map | Unblocked; unchanged in shape |
| **#183 (S4)** — reconciliation | Unblocked **for 1789–2024** via published seat counts. Add: DC special case, 1920 no-apportionment case |
| **#184 (S5)** — expose | Resolves to **shape (A)**, public surface permitted |
| **Open questions** | **OQ1** premise void → take full span, not a modern window. **OQ2** confirmed: resident for per-capita, apportionment for seat reconciliation. **OQ4** branch not taken. **OQ3** (schema placement) still open — an architect call at S2, as the backlog said. **OQ5/OQ6** already answered on #129 |
| **Candidate decisions** | Record as **D058–D062** (the backlog's D053–D057 slots were taken 2026-08-27..30). Confirm the next free slot at recording time |
