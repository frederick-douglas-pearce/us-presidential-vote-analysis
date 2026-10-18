# Research: each candidate's party in each election, and where it comes from (#384, E8-S10)

> **Status: COMPLETE, accepted by the owner 2026-10-17** (the six calls are in §12). Compiled
> 2026-10-17. Its verdict is recorded as **D077**. #385 (`dwh.candidate_party` from Archives Table 1), #386
> (serving it on `/v1`), #387 and #388 (the curated rows) and #389 (the dashboard) build on it.
>
> **Verdict.** A candidate's party in an election is their **nominating party**: the party whose
> nominating body named them for President for that election, by the rules in §1. It is stored at
> most once per candidate per election, as one value from a closed vocabulary of snake_case codes
> (§2). A candidate named by two or more national bodies carries one **joint nomination** code
> that lists its component parties. Someone nobody nominated for President carries
> `no_nomination`, which is a served value. A candidate-year the dataset has no row for is served
> as null, for that one reason alone (§2.3). Where two sources name the same party differently,
> the value follows the name the higher-ranked source uses (§2.1). A row whose value rests on an
> exception to the plain case carries a short, sourced **row note** (§2.4).
>
> **Table 1 covers most of it.** The Archives print a party for the President and the Main
> Opponent in every election. A year-scoped token map (§4) turns those tokens into codes. The
> evidence found one printed token that is incomplete: 1872 Greeley ("D", but jointly
> nominated). #385 handles it with a correction constant. The population left to curate is the
> candidate-years with electoral votes cast that Table 1 does not cover (§8). The script below
> derives it, splits it by era at 1976, and names its size. Each row is classified C1
> (nominated) or C2 (no standing nomination), and given a source of record.
>
> **MIT's party stays, but as a check only.** From #389 on, where the dashboard shows a party it
> shows the nominating party, in every year, 1976 on included. MIT's `party` values are still
> served unchanged under `/v1`, with a rewritten description. They are no longer shown on the
> dashboard, and they never decide a value (§9).
>
> **Sources.** Every source of record is a US-government work, and each one's public-domain basis
> is stated (§0.2). **The American Presidency Project (UCSB) was not consulted for any part of
> this work, not even for lookup or cross-check.** Wikipedia and Wikidata appear nowhere as a
> source.

**Date:** 2026-10-17 · **Method:** the derivation script `.claude/specs/research-candidate-party-source.py`
(§10), three parallel read-only research agents, one per era, and a parent re-check. The parent
re-downloaded every source and matched every quoted passage against it (§0.3).

---

## §0 — Sources and evidence labels

### 0.1 What was not consulted

- **UCSB (presidency.ucsb.edu) was never consulted**, not even for lookup or cross-check (D022,
  owner ruling 2026-10-16). Every web search the research agents ran excluded that domain, and no
  page on it was fetched.
- **Wikipedia and Wikidata are not cited anywhere.** The agents were allowed to use them only
  as finding aids, to learn a name or date to search for.
- **Two Library of Congress pages were rejected** as sources of record. The web-archive records
  for the Libertarian and American Independent parties say their summaries were retrieved from
  DBpedia or Wikipedia, so they are neither a government text nor public domain.
- **Commercial compilations are not cited.** The Library of Congress election guides footnote
  their results tables to CQ Press, *Presidential Elections 1789–2008*. Only the guides' own prose
  is cited here, never a table's party label.

### 0.2 Sources of record

| Key | Source | Public-domain basis |
|---|---|---|
| **ARCH-yyyy** | National Archives, Electoral College results page for the year, Table 1 and Notes: `https://www.archives.gov/electoral-college/<yyyy>`. Read from the local corpus (#89). | Federal work (17 U.S.C. §105). The repo already carries it under `EC_SOURCE`/`EC_LICENSE` (`snapshot_schema.py`). |
| **VPB** | Senate Historical Office, *Vice Presidents of the United States 1789–1993*, S. Doc. 104-26: `https://www.govinfo.gov/content/pkg/CDOC-104sdoc26/pdf/CDOC-104sdoc26.pdf` | Federal work. Passages it quotes from secondary works are excluded. |
| **BDUSC** | *Biographical Directory of the United States Congress 1774–2005*, H. Doc. 108-222 (GPO): `https://www.govinfo.gov/content/pkg/GPO-CDOC-108hdoc222/pdf/GPO-CDOC-108hdoc222.pdf` | Federal work. It is the print form of Bioguide, which returned HTTP 403 to automated fetches, and it covers only people who served in Congress. |
| **SNP** | Senate, "Nominating Presidents": `https://www.senate.gov/about/parties-leadership/nominating-presidents.htm` | Federal work. |
| **ST-xx** | Senate, "States in the Senate" timeline for state `xx`: `https://www.senate.gov/states/<xx>/timeline.htm` | Federal work. |
| **SFB-name** | Senate featured biographies: `https://www.senate.gov/senators/FeaturedBios/Featured_Bio_<Name>.htm` | Federal work. |
| **TRIB** | *Tributes Delivered in Congress to Strom Thurmond*, S. Doc. 107-12: `https://www.govinfo.gov/content/pkg/CDOC-107sdoc12/pdf/CDOC-107sdoc12.pdf` | Federal work. |
| **ND** | Senate Historical Office, *200 Notable Days*: `https://www.govinfo.gov/content/pkg/GPO-200NOTABLEDAYS/pdf/GPO-200NOTABLEDAYS.pdf` | Federal work. Consulted; no passage is cited below. |
| **DOJ** | Department of Justice, Attorney General biography of William Wirt: `https://www.justice.gov/ag/bio/wirt-william` | Federal work. |
| **NPS-1840**, **NPS-1864**, **NPS-W** | National Park Service: `https://www.nps.gov/mava/learn/historyculture/the-election-of-1840.htm`; `https://www.nps.gov/articles/000/the-elections-of-1860-and-1864.htm`; the Thomas E. Watson NHL nomination, `https://npgallery.nps.gov/NRHP/GetAsset/NHLS/76002144_text` | Federal work. NPS-1840 was consulted, and no passage from it is cited below. The NHL form may have been prepared by a contractor; this was not checked, so NPS-W is cited only beside a federal corroborating source. |
| **LOC-yyyy** | Library of Congress research guide, "Presidential Election of yyyy": `https://guides.loc.gov/presidential-election-<yyyy>` | The guide's own prose is a federal work. Its results table is CQ-derived and is not a source of record. One table footnote, "Awarded by the South Carolina Legislature" (LOC-1832, LOC-1836), is cited only as context for how Floyd's and Mangum's votes arose (§3, §8.1), never for a value; #388 looks for a government prose source for it. |
| **CRS-xxx** | Congressional Research Service reports on congress.gov: R42533 (national conventions), IN12396 (2024 Democratic convention), R43824 (the Electoral College), RL32611 (the Electoral College): `https://www.congress.gov/crs_external_products/<R|IN|RL>/PDF/<id>/<id>.<n>.pdf` | Federal work. R42533 was consulted, and no passage from it is cited below. R43824's faithless-elector footnote credits FairVote for 1948–1988, so it is cited for the elector facts, not for nominations. |

Sources considered and **not** used for a party value:
- **House Clerk election statistics and FEC results** report **state ballot lines** under local names: Thurmond ran as "States' Rights Democrats (Democratic)" in Alabama, and Wallace as "Courage" in New York (agent OCR of the Clerk's 1948 and 1968 volumes, UNVERIFIED by the parent). A ballot line is the D018 sense of party, not a nomination, so neither source can back a value.
- **The Congressional Journals** record the electoral count, not nominations. They back vote facts the warehouse already holds, not a party.
- **Privately printed works on .gov hosts** (the Congressional Globe, newspapers on Chronicling America) are public domain by age at most. They are not federal works, so they may corroborate a claim but are never its source of record.

### 0.3 Evidence labels

| Label | Meaning |
|---|---|
| **VERIFIED** | The parent downloaded the source on 2026-10-17 and matched the quoted passage in it. |
| **RELAYED** | A research agent reports reading the passage, but the parent could not re-fetch the page. Not a source of record until re-checked. |
| **UNVERIFIED** | No US-government source was found. |

**The re-check.** The parent re-checked 82 relayed passages against fresh downloads. 79 matched
verbatim (ignoring case and punctuation). Two more matched once a PDF line break and a footnote
marker were allowed for. **One did not match:** SFB-LaFollette does not say "nominated for
president by the League for Progressive Political Action". It reads "ran for president on the
Progressive Party ticket in 1924", and that sentence is what §8 cites. The two newspaper
passages (Chicago Tribune, 1872-06-28; Evening Star, 1924-07-06) are RELAYED, because loc.gov
returned HTTP 403 to the parent.

---

## §1 — Field definition: the nominating party

**Definition.** A candidate's **nominating party** in an election is the party whose nominating
body named them as its candidate **for President** for that election. The field's **name** does
not use the bare term `party`, which on `/v1` stays the popular-vote source's ballot-line party
(D018, `docs/glossary.md`). The **label** readers see is `ba`'s, set at #389 (§9).

**Rules.** They are tested against every Table 1 row and every row in §8.

1. **A national nominating body counts.** That means a national convention (ST-KY: in December
   1831 Clay won "the presidential nomination of a political party, the National Republicans,
   meeting in convention in Baltimore", VERIFIED), or in 1824 the congressional caucus (SNP,
   §8.1). A body that acts by delegate roll call before its meeting is still the convention
   (CRS-IN12396 on 2024: "a planned virtual roll call … to nominate its presidential ticket before
   the convention begins", VERIFIED).
2. **A state-level nomination counts in exactly these cases: 1824 (candidates outside the
   caucus), 1828, and the 1836 Whigs.** The list is closed. Its value is the party the source of
   record names the candidate as running for, because a legislature belongs to no party. The
   evidence for each case:
   - 1824: the other candidates "encouraged their supporters to boycott the moribund caucus"
     (SNP, VERIFIED), and all of them were "Republicans" (VPB, Calhoun chapter, VERIFIED).
   - 1828: the Tennessee legislature "passed a resolution supporting Senator Andrew Jackson's
     candidacy for the 1828 presidential election" (ST-TN, VERIFIED).
   - 1836: the Whigs "chose not to hold a presidential nominating convention that year",
     fielding "several regional candidates, nominated at the state and local level" (VPB, Tyler
     chapter, VERIFIED).
3. **A formal endorsement by a national body counts as its nomination.** The government sources
   use "endorsed" and "nominated" interchangeably for the same act. On Bryan in 1896, for
   example, NPS-W says the Populists "nominated" him while BDUSC says he "was endorsed by the
   Populist and Silver Republican Parties" (both VERIFIED). A rule that admitted only the word
   "nominated" would depend on which source a row happened to cite. **Accepted by the owner
   (§12).** A value with a component that rests on an endorsement and not a nomination carries a
   note saying so (§2.4).
4. **A joint nomination is two or more national bodies naming the same person for President.**
   It counts even where they named different running mates. A state-level cross-endorsement
   never makes a joint nomination, and nor does a state ballot label (D018).
5. **The nomination must still stand when the electors vote.** A nomination withdrawn before then
   does not count. A nominee who died before the electors voted keeps the nomination for the votes
   cast for him, as Greeley does in 1872 (ARCH-1872: "Following Greeley's death, electors in
   several states cast their votes variously", VERIFIED). **Accepted by the owner (§12).** Both
   cases carry a note with the facts: the withdrawal and its date, or the death and its date
   (§2.4).
6. **A party that ran more than one candidate gives each one its own row.** The 1836 Whigs ran
   several, as rule 2 cites. In 1860 two national Democratic conventions each nominated a
   candidate: Douglas was nominated "by the northern faction of the Democratic Party" (ST-IL),
   and the southern delegates "held their own convention in Baltimore and nominated
   Breckinridge" (VPB, Breckinridge chapter), both VERIFIED. Those two bodies are two parties,
   coded separately (§2). The northern body keeps `democratic`, because the Archives print Douglas
   as "D" (§4).
7. **Only a presidential nomination counts.** Someone nominated for Vice President, or a loser
   of the presidential nomination, who receives a presidential electoral vote is
   `no_nomination` (§5).
8. **A source of record's statement is accepted as the nomination.** Where a US-government source
   of record states that the person was party P's candidate or nominee for President that year,
   or that a body of P supported or nominated them, that is accepted as P's nomination. Rule 1
   says what the field means, and this rule says what evidence establishes it. It decides every
   row whose cited passages name the party but not the body that nominated: 1824 Clay, 1832
   Wirt, 1836 White and Webster, 1856 Fillmore, 1860 Bell, 1892 Weaver, 1912 Taft, 1924
   La Follette, 1948 Thurmond and 1968 Wallace (the §8.1 passages). It also decides 1824
   Crawford: SNP names his caucus but says it "supported" him, not that it nominated him.
   Breckinridge's convention is named and "nominated" him, so rule 8 does not decide him. The
   rule is looser than rules 1–2 alone. **Accepted by the owner (§12)**, on the condition that
   each such row carries a note saying that its cited sources name the party, not the nominating
   body, or for Crawford, that the source says the caucus supported him (§2.4). The note says
   only that; whether some other source names the body or the act is not a claim it makes.

**The grain is (year, candidate)** (owner ruling, 2026-10-16). Each candidate has at most one row
per election in which they received an electoral vote; a candidate-year with no row is served as
null (§2.3).

---

## §2 — Closed vocabulary

### 2.1 Party codes

Each code names **one party organization**, and it means the same thing in every year it
appears. The one exception is `democratic_republican`, which is scoped to a name (below). Display
forms are `ba`'s (#386/#389): the name they render is fixed by the naming rule below, and `ba`
sets its case, punctuation and any disambiguation.

**Names are merged only for the same party (owner, §12).** Two sources' names become one code
only when they name the same party. The code then follows the name used by the higher-ranked
source (§6.2). The same name used for two different parties stays two codes, as the two
Progressives do. The rule settles which name is used once two names are known to name one
party; it does not decide whether they do. It decides three values:
- **The Populists** are `populist`. VPB (rank 2: "The Populists had already nominated") and BDUSC
  (rank 3: "Populist candidate for President in 1892") both use that name. "People's" appears
  only in a CQ-derived LOC table label, "Populist (People's)", and in a photograph caption, and
  neither is a source of record (§0.1).
- **1856 Fillmore's** first component stays `american`. VPB, his source of record, calls it "the
  … Know-Nothing party" in his chapter, and "the American (Know-Nothing)" party where it names it
  in full (VERIFIED). The two are one party, and the full name is the one used.
- **1824 Crawford** is `democratic_republican`, on a partial link (owner, §12). SNP names his
  caucus "Jeffersonian-Republican". VPB counts him in the 1824 field, with Adams and Jackson, who
  were "all Republicans" (Calhoun chapter), and the Archives print "Democratic-Republican" for
  Adams and Jackson (ARCH-1824), all VERIFIED. No cited passage says outright that the names are
  one party, so the link is partial. The Archives' name, the higher-ranked, is used.

**1828 Jackson is `democratic_republican`, because the Archives token stands (owner, §12).** The
Archives print "Democratic-Republican" for him in 1824 and in 1828, and no correction overrides a
Table 1 token without a VERIFIED source showing a different nominating body (§6.1). BDUSC's
"elected as a Democrat as President of the United States in 1828" names no different nominating
body, so the token stands, and by the owner's call it is not treated as a second name for the same
party. So the naming rule is not what decides this row. The code is scoped to the name the
Archives print for 1824 and 1828, and this doc claims no organizational continuity between the two
years, which no source of record here establishes.

**The "Years it appears" column** lists the years a code is a whole value, and then, as
"component", the years it appears only inside a joint code.

| Code | Party | Years it appears (in this data) | Basis |
|---|---|---|---|
| `democratic_republican` | the Democratic-Republican name the Archives print for 1824 and 1828 | 1824, 1828 | SNP, VPB, BDUSC Clay; ARCH-1824 and ARCH-1828 tokens (§4) |
| `national_republican` | National Republican | 1828, 1832 | ST-KY (1832); ARCH-1828 token (§4) |
| `democratic` | Democratic | 1832–2024; component only (1872, 1896, 1900) | §4 |
| `anti_masonic` | Anti-Masonic | 1832 | DOJ |
| `whig` | Whig | 1836–1852; component (1856) | VPB; LOC-1856 for the 1856 endorsement |
| `american` | American (Know-Nothing) | component only (1856) | VPB, Fillmore chapter |
| `republican` | Republican; includes its 1864 "National Union" name | 1856–2024 | NPS-1864 (§4) |
| `southern_democratic` | the Southern Democratic convention of 1860 | 1860 | VPB, Breckinridge chapter |
| `constitutional_union` | Constitutional Union | 1860 | ST-TN |
| `liberal_republican` | Liberal Republican | component only (1872) | BDUSC Greeley |
| `populist` | Populist | 1892; component (1896, 1900) | BDUSC Weaver; VPB, Stevenson chapter; LOC-1896 |
| `progressive_1912` | Progressive ("Bull Moose") party of 1912 | 1912 | VPB, Roosevelt and Sherman chapters |
| `progressive_1924` | the 1924 Progressive ticket | 1924 | SFB-LaFollette (§8) |
| `states_rights_democratic` | States' Rights Democratic ("Dixiecrat") | 1948 | TRIB, SFB-Thurmond |
| `american_independent` | American Independent | 1968 | ARCH-1968 |
| `libertarian` | Libertarian | 1972 | none yet (#387, §8.3) |

**The two Progressives are separate codes.** The government sources call both "Progressive". The
VPB's Roosevelt chapter says he "formed his own party, the Progressive or Bull Moose party"
(VERIFIED). That the 1924 ticket was a different organization rests on a RELAYED newspaper
headline, "CANDIDATES TO CARRY STANDARD OF NO PARTY" (Evening Star, 1924-07-06). Two codes keep
the rule "one organization per code" safe until #387 sources it. Merging them later would be
the cheaper direction if it turns out to be wrong.

### 2.2 Joint nominations and `no_nomination`

**Joint nominations are enumerated atomic codes.** Each one declares its component parties in
`usvote/party.py` (#385). Splitting a code at a separator is ruled out, because era tokens
already contain hyphens (`transform.PARTY_JOIN`'s comment). A joint code's name joins its
components in order of nomination, with the Table 1 token's order where one prints.

**A code never changes meaning.** Adding a component to a joint nomination (§4.2's open items),
merging the two Progressives, or adding any value makes a **new code**. Each needs a superseding
D-entry and an API changelog note, because a served value changes. So #385's hand-written literal
pins each code **with its component tuple, in order** (a single code maps to `()`), not the code
names alone: a component appended to `democratic_populist` under the same name must fail it.

| Code | Components | Candidate-year | Basis |
|---|---|---|---|
| `liberal_republican_democratic` | `liberal_republican`, `democratic` | 1872 Greeley | BDUSC Greeley: "nominated by the Liberal Republicans in Cincinnati in 1872 and by the Democrats in Baltimore for the Presidency" (VERIFIED) |
| `democratic_populist` | `democratic`, `populist` | 1896 Bryan, 1900 Bryan | LOC-1896: "William Jennings Bryan (Democratic/Populist)". VPB, Stevenson chapter, on 1900: "The Populists had already nominated the ticket of Bryan and Charles A. Towne" (both VERIFIED). See §4.2 for a third component. |
| `american_whig` | `american`, `whig` | 1856 Fillmore | VPB: "the 1856 presidential nomination of the … Know-Nothing party". LOC-1856: "The Whig Party also endorsed Fillmore for president." (both VERIFIED; joint under rule 3) |

**`no_nomination`** means that no body qualifying under §1 nominated the candidate for President
that year, or that the nomination did not stand when the electors voted (rule 5). It is a served
value, never null or blank. Its reader wording is `ba`'s (#386/#389), under three constraints: it
stays distinct from the null, it never reads as "no party", and it never says that a nominee
whose nomination was withdrawn was not nominated.

### 2.3 The null: one cause only

A served candidate-year with **no `dwh.candidate_party` row** is null in the API (JSON `null`),
in SQL (`NULL`) and in the CSV (an empty cell). That is the only reason it can be null.
"Not yet collected" is the absence of a row, not a vocabulary member, so #385's
closed-vocabulary check still holds.

- **A build guard proves the single cause, with four assertions, split by layer.**
  - **#385, in the warehouse:**
    1. every Table 1 key has exactly one row, and resolves to exactly one served candidate-year
       with votes cast;
    2. every curated row resolves to exactly one served candidate-year with votes cast, so no
       curated row is orphaned by a name or id drift;
    3. every served candidate-year has votes cast (the script's checks 4 and 5, moved into the
       build).

    That curated keys and Table 1 keys are disjoint is already in #385's scope, and stays there.
  - **#386, at the snapshot build:**
    4. the served null set, observed **on the served output** (the new column `IS NULL` on every
       `ec_pv` row and every `national_rollup` row), **equals** the population (§5) minus the
       curated keys, with both sides derived independently of that column.

  Part 4 must read the served column. Computed as an anti-join of the served candidate-years
  against `dwh.candidate_party`, it would be an identity given parts 1–3, and would miss a null
  arising after the row exists: a lost `carry=`, a key drift in the `ec_pv` join, or a row stored
  with a null value. A subset test would fail the same way: with every Table 1 key present, "null
  set ⊆ population" holds by construction. The mixed null and non-null case within one
  candidate-year is §9's constancy check. #385's acceptance criteria already call for a test that
  makes each guard fire as well as one that passes.
- **An unresolved source conflict ships no row**, so it shows as the same null. This doc names
  each such candidate-year (§8.3).
- **The one cause is stated** in the field description, in `docs/api-snapshot.md` and in a
  rewritten `labels.PARTY_NOTE`. The wording is `ba`'s, dataset-first, with no "yet".
- **No sibling status column is needed**, following the per-capita precedent (D069(c)).
- **Typing is #386's call.** A `Literal` over the full D077 vocabulary does not change at the
  #387/#388 cutovers, which add rows with existing values, unless a superseding D-entry adds a
  value (Davis if his nomination stood, a #387 rule-3 finding, or §4.2's Bryan item). That
  D-entry changes the `Literal` in the same change.

### 2.4 The row note (owner, §12)

Each row, Table 1 or curated, has a nullable **row note**: a short statement of fact about how
its value arose. It is stored with the value in `dwh.candidate_party` and served beside it.
"Row note" is this doc's working term; the field's name is #386's and `ba`'s.

- **Each row records the rules its value rests on**, as a closed set drawn from {2, 3, 5, 6, 8},
  empty for a plain row. It is build metadata, not served.
- **Required** wherever that set includes a rule the owner accepted as a call:
  - **rule 3,** a component that rests on an endorsement and not a nomination (1856 Fillmore,
    whose Whig component LOC-1856 records as an endorsement);
  - **rule 5,** a nomination withdrawn before the electors voted (1872 Davis, if confirmed), or a
    nominee who died before the electors voted (1872 Greeley, a Table 1 row);
  - **rule 8,** a value whose cited passages name the party but not the nominating body, or, as
    for 1824 Crawford, name the body but say only that it "supported" them (the twelve rows rule
    8 lists).
- **Allowed** for any other exceptional case. The cases this research found:
  - rule 2's state-level nominations (1824 Jackson, Adams and Clay; 1828 Jackson; the 1836 Whigs,
    Harrison included);
  - rule 6's two 1860 Democratic conventions (Douglas, Breckinridge);
  - Lincoln's 1864 "National Union" name;
  - how a C2 row's votes arose: a faithless elector, unpledged electors, a legislature's award, a
    vice-presidential nomination, or electors left free by the nominee's death (1872
    Hendricks and Jenkins). Every C2 row already cites this (§6.1), so the recommendation to #388
    is a note on each.
- **A note states only facts its row's citations support.** It adds no source of its own, and
  the editorial guardrails bind it like any published claim.
- **Its null means no note was recorded.** It is not the value's null, and §2.3's guard counts
  only the value.
- **Its facts are the research's; its wording follows `ba`.** The wording is fixed when #386
  first serves it.
- **It travels with the value.** It is constant per (year, candidate), so it uses the same
  rollup carry (§9) and the same CSV field set (§7).
- **A guard** (#385/#387/#388) fails the build where a row's rule set includes 3, 5 or 8 and its
  note is blank once stripped, so an empty string fails too. The keys this doc names (Fillmore,
  Greeley, the twelve rule-8 rows, and Davis once confirmed) are pinned as a hand-written literal
  floor, so a row cannot silently drop its rule set.

---

## §3 — Independent

**"Independent" is not a vocabulary value.** No electoral-vote recipient in this data needs one:

- **Floyd (1832) and Mangum (1836)** are labeled "Independent" (Floyd) and "Independent
  Democrat" (Mangum) only in the CQ-derived tables of LOC-1832 and LOC-1836. The same tables
  footnote their votes "Awarded by the South Carolina Legislature" (VERIFIED; context only,
  §0.2). No nominating body was found for either, so both are `no_nomination`.
- **Wallace (1968)** is the "American Independent Party candidate" in ARCH-1968 (VERIFIED), so
  he takes `american_independent`.
- **La Follette (1924)** ran "on the Progressive Party ticket" (SFB-LaFollette, VERIFIED), so he
  takes `progressive_1924`.

CRS-RL32611 notes that "political parties and independent candidacies nominate their national
candidates" (VERIFIED). So a future recipient whose own national slate named them would need a
value, and adding one is a superseding D-entry. YAGNI: none is added now.

**Accepted by the owner (§12), on one condition:** no source of record assigns "Independent" to
any recipient. The parent searched the fetched sources of record for the word, and the condition
holds:
- VPB, in its Agnew chapter, calls Wallace's an "independent candidacy" (VERIFIED). That
  describes the candidacy, and is not a party name. ARCH-1968, the higher-ranked source, names
  his party (§2.1).
- VPB, in its Roosevelt chapter, says "Roosevelt's independent candidacy came in second" in
  1912 (VERIFIED). That too describes the candidacy; the same chapter says he "formed his own
  party, the Progressive or Bull Moose party", and ARCH-1912 prints "P" (§4.1).
- VPB counts David Davis as one of "2 Independents" in the Senate. That is his later Senate
  label, not a label for his 1872 candidacy, and his row is unresolved anyway (§8.3).
- The only places a recipient's party is printed as "Independent" are LOC's CQ-derived tables
  (Floyd "Independent", Mangum "Independent Democrat"), which are not a source of record.

The alternative, `independent` as a value, would label two people no body nominated with a word
their sources of record do not use. If a source of record is later found that names a
recipient's party "Independent", §2.1's naming rule applies, and the value is added by a
superseding D-entry.

---

## §4 — The year-scoped Table 1 token map

### 4.1 The map

#385 stores the **printed** token, so the map is keyed on it: the raw parse, before
`transform.PARTY_CODE_FIXES`. Every pair below is one the script printed (§10, output (a)).

| Year(s) | Printed token | Code | Comment |
|---|---|---|---|
| 1824 | `Democratic-Republican` | `democratic_republican` | Jackson. The Archives token stands (§6.1). The caucus supported Crawford, and Jackson stood outside it, in the same party (SNP; VPB, Calhoun chapter; §1 rule 2). |
| 1824 | `D-R` | `democratic_republican` | Adams. Same reason. |
| 1828 | `Democratic-Republican` | `democratic_republican` | Jackson. BDUSC has "elected as a Democrat as President of the United States in 1828" (VERIFIED), which names no different nominating body, so the Archives token stands (§2.1, §6.1). |
| 1828, 1832 | `National Republican` | `national_republican` | 1832 Clay: ST-KY (§1). 1828 Adams: no US-government source names his nominating body (UNVERIFIED), so the Archives token stands, as §6.1 provides. |
| 1832–1892, 1904–2024 | `D` | `democratic` | No `D` prints in 1896 or 1900. |
| 1836–1852 | `Whig` | `whig` | |
| 1856–1908, 1916–2024 | `R` | `republican` | 1864: "the Republican Party chose to join with the War Democrats and called themselves the National Union Party" (NPS-1864, VERIFIED). |
| 1896, 1900 | `D-P` | `democratic_populist` | P = Populist here (LOC-1896; VPB, Stevenson chapter). |
| 1912 | `P` | `progressive_1912` | P = Progressive here (VPB, Roosevelt chapter). |

**The map is total and year-scoped.** Every (year, token) pair Table 1 prints has exactly one
row, and the ranges above leave out the years a token does not print. An unmapped pair fails
the #385 build, and so does a mapped pair that never occurs. "P" is the case that forces the
year key: it means `progressive_1912` in 1912 and is a component of `democratic_populist` in
1896 and 1900.

**Map entry or correction.** A map entry translates what a token means in a year, as "P" means
`progressive_1912` in 1912. A correction adds or replaces a party the token does not name, as for
1872 Greeley. No map entry renames the party a token prints: each entry gives the code for the
party the Archives name.

### 4.2 What the evidence routes to #385 as corrections

Table 1 rows are #385's, and curated rows may not overlap them. So a Table 1 token the evidence
contradicts or leaves incomplete is fixed in #385, by the house correction pattern: a constant,
a test and a `docs/corrections.md` row.

| Row | Printed | Evidence | Route |
|---|---|---|---|
| 1872 Greeley | `D` | Joint: Liberal Republican and Democratic conventions (BDUSC Greeley, VERIFIED) | **Correction constant** → `liberal_republican_democratic` |
| 1896 and 1900 Bryan | `D-P` | BDUSC Bryan: "endorsed by the Populist and Silver Republican Parties in the first and second campaigns" (VERIFIED) | **Open.** Under rule 3 the endorsement would add a third component. Which national body endorsed him in each year is not sourced, so no code is defined for it yet (§2.2). Until a source names the body for each year, `democratic_populist` stands, because that much is VERIFIED. |
| 1828 Jackson | `Democratic-Republican` | BDUSC: "elected as a Democrat" (VERIFIED) | **No correction.** BDUSC's "Democrat" shows no different nominating body, so the token stands (§2.1, §6.1). |
| 1916 Hughes | `R` | No source found either way | **Open question for #385:** did a second national body endorse him? No change without a source. |
| 1840 Harrison, 1848 Taylor, 1856 Frémont | `Whig`, `Whig`, `R` | No source found either way | **Open question for #385:** did a minor national body also nominate or endorse each? No change without a source. |

All other Table 1 rows matched the evidence the agents found, or found nothing against them.

---

## §5 — The C1 and C2 populations

**The remaining population** is the served candidate-years with electoral votes **cast**
(`president_electoral_votes > 0`), minus the Table 1 rows (§10, output (b)).

**Why cast, not counted.** Under the appointed ≥ cast ≥ counted ladder, a candidate can have
votes cast that Congress did not count. 1872 Greeley had 3 cast and 0 counted, and the script's
output (c) shows it. Defined on counted votes, he would leave the population, though the votes
cast for him are served.

**C1 (nominated)** is a member of the population with a nominating party under §1. **C2 (no
standing nomination)** is a member with `no_nomination`.

C2 is defined by the absence of a standing presidential nomination that year, not by how the
vote arrived. It covers five kinds of row:
- faithless electors' choices;
- unpledged electors' choices (1960 Byrd: CRS-RL32611 n.43 says Mississippi's eight were
  "unpledged Democratic" electors, VERIFIED. It counts Alabama's six as pledged electors who voted
  otherwise, which `research-faithless-electors.md` §2 disputes on non-CRS sources. Byrd is
  `no_nomination` either way, and #388 settles which kind of row his Alabama votes are);
- votes a legislature awarded to a candidate nobody nominated (1832 Floyd, 1836 Mangum, per LOC's
  table footnote, §0.2);
- vice-presidential nominees who drew a presidential vote (1872 Brown, 1988 Bentsen, 2004
  Edwards);
- electors left free by the nominee's death (1872 Hendricks and Jenkins, from Greeley's
  electors; ARCH-1872).

A third-party nominee is C1 however few votes they drew: 1972 Hospers had one, from a faithless
elector.

**MIT plays no part in membership** (architect, plan step). From 1976 on, the population is
the recipients Table 1 does not cover, not those without an MIT party.

---

## §6 — Evidence bar and conflict rule

### 6.1 What a row needs

- **A Table 1 row's source of record is the Archives page itself** (ARCH-yyyy), read through
  the token map. It is overridden only where a VERIFIED government source shows a different or
  an additional national nominating body, and then by a #385 correction (§4.2).
- **A curated row needs four things:**
  1. one source of record from §0.2, or another US-government work with its public-domain
     basis stated;
  2. a verbatim passage from it (40 words or fewer), stored with the row;
  3. its URL;
  4. that the passage was matched against the fetched source (VERIFIED) before the row ships.
- **A passage is enough when it meets rule 8:** it states that the person was a named party's
  candidate or nominee for President in that year, or that a body of that party nominated or
  supported them (1824 Crawford's caucus "supported" him). Two kinds of passage are
  never enough:
  - a state ballot label (House Clerk, FEC);
  - a party tag in a list compiled from a non-government source (CRS-R43824's faithless-elector
    footnote, LOC table labels).
- **A curated row carries a list of one or more citations.** A joint code needs at least one
  per component. Each citation holds the source key, the passage, the URL, a page locator for
  the large PDFs (VPB, BDUSC) and the date it was verified. "VERIFIED" is an attestation
  recorded with the row; no offline test can re-check it, so CI does not enforce it.
- **A row's class is the one §8 assigns.** A candidate-year with a nomination reported at any
  evidence level, RELAYED or UNVERIFIED included, may not take `no_nomination` until that
  nomination is shown not to stand under rule 5. This keeps Davis (1872) and Hospers (1972) out
  of C2 for want of research.
- **A C2 row (`no_nomination`) needs a source of record for how the votes arose:** a faithless
  elector, unpledged electors, a legislature's award, a vice-presidential nomination or
  the 1872 scatter. It also needs no VERIFIED source showing a standing presidential nomination.
  Absence of a nomination cannot be quoted, so the row cites the vote's origin and records what
  was searched in the curated catalog, beside its citations.

### 6.2 Source order, where sources differ

1. The Archives page for that year.
2. Senate Historical Office works: VPB, SNP, ST-xx, SFB.
3. BDUSC and CRS. For CRS, its own text only.
4. Other federal works: NPS, DOJ, the LOC guides' prose.
5. Public domain by age (Chronicling America): corroboration only.

**Specificity beats rank.** A source naming the nominating body outranks one giving a party
label.

### 6.3 Conflicts

- **A conflict this order does not resolve ships nothing.** The row stays absent, so it is
  served as null (§2.3), and the conflict is recorded here and in the row's issue.
- **A date conflict that leaves the party unchanged is not a party conflict.** VPB gives both
  May 20 and May 22, 1835 for the convention that nominated Van Buren; the row
  needs only the party (§11).

---

## §7 — License and provenance for curated rows

- **Table 1 rows reuse the EC pair** `EC_SOURCE = "NARA"` and `EC_LICENSE = "US-PD"`
  (`snapshot_schema.py:63–64`).
- **The curated rows' pair is `USGOV` / `US-PD` (owner, §12).**
  - **`USGOV`** names a publisher class, US-government works, as `NARA`, `MIT` and `USCB` each
    name a publisher. Each row's citations name the actual publisher (Senate, GPO, NPS, …), so
    `meta.provenance` does not grow with each new one. `CURATED` was rejected because it names a
    process, not a publisher.
  - **`US-PD`** states the sources' status, as `EC_LICENSE = "US-PD"` already does for the
    Archives, though this project's compilation of them includes corrections (the constants in
    `src/usvote/transform.py`, cataloged in `docs/corrections.md`). `US-PD` is the statutory
    status of a federal work (17 U.S.C. §105), and the values are facts drawn from such works, so no new license code is needed.
  - Each row's quotation is a short excerpt from a public-domain federal work, so it carries no
    third-party restriction. Text that is public domain by age only is never stored as the
    quotation (§6.1).
- **Where the provenance lands.**
  - `snapshot_meta` gains a fourth source/license pair for curated rows, beside NARA, MIT and
    USCB.
  - A meta pair says that curated values exist, not which ones they are. So #386 also ships
    #385's per-row source column (Archives or curated) beside the field, as `ec_pv.source` does
    for the popular vote.
  - A Table 1 row #385 corrects keeps the Archives source, as every other EC correction keeps
    NARA, and the correction is recorded in `docs/corrections.md`.
  - The dashboard picks a CSV's preamble sources from its field names (`export.sources()`), and
    every exported field must sit in exactly one field set. So #389 adds a field set for the new
    field that maps to the curated source. It never goes in `export.POPULAR_VOTE_FIELDS`, which
    would credit MIT, or in `EC_FIELDS`, which would never credit the curated source.

---

## §8 — The remaining population, row by row

The script derives the list (§10, output (b)). The run recorded in §10 found:
- the served candidate-years with electoral votes cast;
- less the Table 1 rows, 2 per election;
- leaving the population, split by era at `MIT_FLOOR = 1976`.

The script prints each count, so they are named there and not frozen here.

### 8.1 Before 1976

| Year | Candidate | Class | Proposed value | Source of record | Passage | Label |
|---|---|---|---|---|---|---|
| 1824 | William H. Crawford | C1 | `democratic_republican` | SNP; VPB, Calhoun chapter | "when the Jeffersonian-Republican caucus convened in the House Chamber … They supported Treasury Secretary William Crawford"; "In addition to Calhoun, Adams, and Crawford, the crowded field … —all Republicans" | VERIFIED. Rule 8 (the caucus "supported" him). The code's link to SNP's name is partial (§2.1). |
| 1824 | Henry Clay | C1 | `democratic_republican` | BDUSC Clay | "unsuccessful presidential candidate of the Democratic Republican Party in 1824" | VERIFIED |
| 1832 | John Floyd | C2 | `no_nomination` | BDUSC Floyd | "received the electoral vote of South Carolina for President in 1833". BDUSC dates the vote 1833, the year after the election; LOC-1832's table footnotes it "Awarded by the South Carolina Legislature" (§0.2). | VERIFIED (origin); no nomination found |
| 1832 | William Wirt | C1 | `anti_masonic` | DOJ | "In 1831, Wirt accepted the nomination of the Anti-Masonic Party for the presidency" | VERIFIED |
| 1836 | Hugh L. White | C1 | `whig` | VPB, Johnson chapter | "The Whig presidential candidates were Daniel Webster, Tennessee Senator and former Jacksonian Hugh Lawson White, and … William Henry Harrison" | VERIFIED |
| 1836 | Daniel Webster | C1 | `whig` | BDUSC Webster | "unsuccessful Whig candidate for president in 1836" | VERIFIED |
| 1836 | Willie P. Mangum | C2 | `no_nomination` | BDUSC Mangum | "received the eleven electoral votes of South Carolina for President of the United States in 1837" (BDUSC dates it 1837, the year after the election; LOC-1836's table footnote, as for Floyd) | VERIFIED (origin); no nomination found |
| 1856 | Millard Fillmore | C1 | `american_whig` | VPB, Fillmore chapter; LOC-1856 | "accepting the 1856 presidential nomination of the … Know-Nothing party"; "The Whig Party also endorsed Fillmore for president." | VERIFIED |
| 1860 | John C. Breckinridge | C1 | `southern_democratic` | VPB, Breckinridge chapter | "They held their own convention in Baltimore and nominated Breckinridge as their presidential candidate." | VERIFIED |
| 1860 | John Bell | C1 | `constitutional_union` | ST-TN | "John Bell of Nashville was nominated for president of the United States by the Constitutional Union Party" | VERIFIED |
| 1872 | Thomas A. Hendricks | C2 | `no_nomination` | VPB, Hendricks chapter; ARCH-1872 | VPB: "The Democrats instead nominated the eccentric newspaper editor Horace Greeley". ARCH: "Following Greeley's death, electors in several states cast their votes variously" | VERIFIED |
| 1872 | Benjamin Gratz Brown | C2 | `no_nomination` | BDUSC Brown | "unsuccessful Democratic candidate for Vice President of the United States on the ticket with Horace Greeley in 1872" | VERIFIED |
| 1872 | Charles J. Jenkins | C2 | `no_nomination` | ARCH-1872 | the ARCH-1872 passage in the Hendricks row | VERIFIED (origin); no nomination found |
| 1872 | David Davis | **unresolved** | — | — | Nominated by the National Labor Reform convention and withdrawn before the election, per his letter in the Chicago Tribune, 1872-06-28 (RELAYED, public domain by age only). BDUSC says only "candidate for nomination for president on the Liberal-Republican ticket in 1872" (VERIFIED). Rule 5 makes him `no_nomination` if the withdrawal is confirmed. | needs a source of record (§8.3) |
| 1892 | James B. Weaver | C1 | `populist` | BDUSC Weaver | "Populist candidate for President in 1892" | VERIFIED |
| 1912 | William H. Taft | C1 | `republican` | ARCH-1912 | "Republican Party candidate Taft, and Vice Presidential running mate James S. Sherman, received 8 electoral votes each" | VERIFIED |
| 1924 | Robert M. La Follette | C1 | `progressive_1924` | SFB-LaFollette | "ran for president on the Progressive Party ticket in 1924" | VERIFIED |
| 1948 | J. Strom Thurmond | C1 | `states_rights_democratic` | TRIB; SFB-Thurmond | "as the nominee of the States Rights Democratic Party, and won 39 electoral votes"; "He ran as the States' Rights Democratic (also known as Dixiecrat) candidate for president in 1948" | VERIFIED |
| 1956 | Walter B. Jones | C2 | `no_nomination` | ARCH-1956; CRS-R43824 | "An Alabama elector voted for Jones and Talmadge."; "an Alabama elector for Adlai Stevenson (D) voted for Walter Jones" | VERIFIED |
| 1960 | Harry F. Byrd | C2 | `no_nomination` | ARCH-1960 | "Byrd received electoral votes for President from Alabama (6), Mississippi (8) and Oklahoma (1)." Which of his votes came from unpledged slates: §5. | VERIFIED |
| 1968 | George C. Wallace | C1 | `american_independent` | ARCH-1968 | "American Independent Party candidate Wallace received 9,906,473 popular votes for President." | VERIFIED. No source found for a 1968 national convention; under §6.1 the ARCH passage is enough. |
| 1972 | John Hospers | C1 | `libertarian` | **needs a stronger source** | CRS-R43824 tags him "(Libertarian)" in a footnote credited to FairVote (VERIFIED), which §6.1 rules is not enough | #387 sources it (§8.3) |

### 8.2 From 1976 on

All of these are C2, `no_nomination`.

| Year | Candidate | Source of record | Passage | Label |
|---|---|---|---|---|
| 1976 | Ronald Reagan | ARCH-1976 | "A Washington (State) elector voted for Ronald Reagan." | VERIFIED |
| 1988 | Lloyd Bentsen | ARCH-1988; ST-TX | "A West Virginia elector voted for Bentsen as President and Dukakis as Vice President."; "ran unsuccessfully for vice president on the Democratic ticket" | VERIFIED |
| 2004 | John Edwards | ARCH-2004; ST-NC | "One Minnesota elector voted for John Edwards for both President and Vice President."; "nominated for vice president of the United States on the Democratic Party ticket" | VERIFIED |
| 2016 | Colin Powell | ARCH-2016 | "for President, Clinton 8, Colin Powell 3, and Faith Spotted Eagle 1" | VERIFIED |
| 2016 | Faith Spotted Eagle | ARCH-2016 | same passage | VERIFIED |
| 2016 | Bernie Sanders | ARCH-2016 | "for President, Clinton 3 and Bernie Sanders 1" | VERIFIED |
| 2016 | Ron Paul | ARCH-2016 | "for President, Trump 36, Ron Paul 1, and John Kasich 1" | VERIFIED |
| 2016 | John Kasich | ARCH-2016 | same passage | VERIFIED |

### 8.3 The null-result list

Two candidate-years ship no curated row until a source of record is found. Each is served as
null meanwhile (§2.3):

- **1872 David Davis.** #388 settles rule 5 for him. The withdrawal needs a government source,
  or a decision that the Tribune letter is enough to rule that his nomination did not stand. If
  it did not stand, he is C2, `no_nomination`, with a row note on the withdrawal (§2.4). If it
  stood, he is C1, and his National Labor Reform nomination needs a new code by a superseding
  D-entry (§2.2, §2.3); he ships no row until then.
- **1972 John Hospers.** A US-government passage naming him the Libertarian nominee is needed.
- **The open #385 corrections in §4.2.** These are Table 1 rows, so the current value stands
  until a source exists. No null results.

C1 and C2 split as the tables show. Of the pre-1976 rows, two are unresolved. Every row from
1976 on is C2.

---

## §9 — Relation to MIT's party (owner rulings Q4/Q5, architect, 2026-10-17)

- **What readers see.** From #389 on, where the dashboard shows a party it shows the nominating
  party, in every served year, 1976 on included (owner Q4). The field's **name** avoids bare
  `party`, because `/v1`'s `party` stays MIT's (§1). The reader's **label** is `ba`'s, in #389's
  label spec, which the owner approves. MIT's party is no longer displayed (owner Q4); whether it
  also leaves the dashboard CSV is #389's to settle.
- **The API.** MIT's **values** stay served unchanged as `party` under `/v1`. Its description,
  "Party of record" (`src/usvote/api/models.py`), stops being true when party authority moves, so
  `ba` rewrites it at #386 to say it is the popular-vote source's party. The nominating party is
  a new field, appended additively; #386 and `ba` name it. Repurposing `party` would break `/v1`
  consumers and reverse #386's own ruling ("not a repurposed `party`"). It would also credit
  MIT, in the docs, the CSV preamble and the snapshot meta, for values that come from the
  Archives. For #386 this is an additive minor `API_VERSION` bump, plus snapshot schema 4 → 5.
- **Authority: D077 amends D018.** D018's sentence "Party *authority* lives in the EC candidate
  dim (D006)" changes to `dwh.candidate_party` (year, candidate_id). `dwh.candidate.party`/
  `party_2` stay unchanged, as a non-authoritative per-candidate summary of the raw tokens with
  `PARTY_CODE_FIXES` still applied, so 1828 Jackson stays "D-R" there. No consistency guard
  links them, because the two use different vocabularies, and nothing new reads them. `pv`'s
  `party` stays "descriptive-only, not the key" (D018).
- **The rollup.** The value is constant per (year, candidate), repeated on every `ec_pv` state
  row, so it is inside the snapshot's content hash. It reaches `national_rollup` through the
  `carry=` map in `snapshot.build_national_rollup`, as MIT's `party` does there. In the hybrid
  path it belongs in `hybrid.CARRIED_CANDIDATE_COLUMNS`, the constancy guard, not `min`-resolved
  as MIT's `party` is. That guard counts `nunique(dropna=True)`, so it would miss a mix of null
  and non-null in one candidate-year; #385/#386 count nulls for this field too.
- **The MIT crosswalk and check.** MIT's party-bearing values on EC-vote recipients are the two
  in `mit.transform.EC_GETTER_PARTIES`. On the 1976+ Table 1 rows the script found only those,
  and on the 1976+ population rows it found none (§10, check 8). The crosswalk maps `DEMOCRAT` →
  `democratic` and `REPUBLICAN` → `republican`. The check:
  - every non-null MIT `party` maps to the nominating value, or to a component of a joint
    nomination;
  - an MIT value outside the crosswalk fails the build, as an unmapped token does (§4.1);
  - a row where MIT's party is null, or where the nominating party is null, is skipped, since
    MIT then adds nothing to compare;
  - a disagreement is a named exception constant with a `docs/corrections.md` row, or else it
    fails the build;
  - a state-level fusion line (D018) is never a nomination;
  - **a floor:** every 1976+ Table 1 candidate-year has at least one compared row, so a field
    that never reaches the compared frame fails rather than passing on zero comparisons.

  **The grain is #385's plan-gate question.** The recommendation is per (year, state, candidate)
  on `ec_pv` rows, because the rollup resolves MIT's `party` by `min`, which can hide a
  disagreement in one state.

  On the current snapshot every 1976+ Table 1 row agrees, and every 1976+ population row has a
  null MIT party, so none meets the check against `no_nomination` (§10).

---

## §10 — How to re-derive

```
uv run python .claude/specs/research-candidate-party-source.py
```

**What it reads.** Offline, with no network and no database credentials. It reads the Archives
corpus (`USVOTE_EC_HTML_DIR`), the TIGER shapefile (`USVOTE_SHAPEFILE_PATH`) and the served
snapshot (`USVOTE_API_SNAPSHOT_PATH`, opened `mode=ro`). The snapshot is required: without it
the run fails, unless `--allow-no-snapshot` is passed, which skips checks 5 and 8 and says so in
the last line.

**How it builds the frames.** It uses the warehouse's own composition,
`transform.transform_parsed_years`, so its candidate-years are the ones that composition loads
into `dwh.votes` and `dwh.candidate`. It never reads `dwh` itself; check 5 compares its set with
the served snapshot's. SQL over `dwh` cannot produce the list, because `dwh.candidate.party` is
aggregated per candidate across years.

**What it asserts.** It exits non-zero on any failure. Each check reads the frame it names:
1. the Table 1 years and the transform's national-totals years both equal `ec_ingest_years()`;
2. each Table 1 row resolves, through the transform's own name steps, to a candidate with votes
   cast that year (that it is only one follows from `national_totals`' no-duplicate check);
3. a year's two Table 1 rows are different candidates;
4. no candidate-year in the transform's national totals has zero votes cast;
5. the snapshot's `national_rollup` (year, slug) set, unfiltered, equals the transform's, in
   both directions, and every served row has votes cast. With check 4, this is what shows that
   the population is the whole served set less Table 1, so §2.3's null has no second cause;
6. no candidate-year has more votes counted than cast;
7. `usvote.ucsb` was never imported;
8. MIT's party, joined with every row matched to a served row: on each 1976+ Table 1 row it is
   the crosswalk value for the printed token (`D` → `DEMOCRAT`, `R` → `REPUBLICAN`), and on each
   1976+ population row it is null. The second half is a dated headline: if a later snapshot
   breaks it, §9 needs re-checking, not the data.

Three more asserts are **tripwires**: two Table 1 rows per year (which `parse.parse_table1`
guarantees), one match per Table 1 row (which `national_totals`' no-duplicate check guarantees),
and population plus Table 1 equals the cast-vote set (which follows from that check and checks 2
and 3). They cannot fail on their own, and are labeled so in the code.

The "Other Presidential Opponents" cross-check the plan listed as optional was not built.

**What it prints.** Markdown on stdout; the scrape and parse progress goes to stderr. Output (a)
is the raw Table 1 tokens, (b) the population by era, and (c) the candidate-years whose cast and
counted totals differ. It also prints the MIT `party` on each 1976+ Table 1 row and each 1976+
population row.

**The run this doc records.** Commit `47f4761`, clean (`git describe --dirty` printed no `-dirty`;
the later commit that records this run changes no script line), the corpus at
`~/Documents/Projects/data/presidential_vote_analysis/ec_raw`, and snapshot
`71b777de23181c224d80207fb756a9a4541fe18ce70cced28dd8de9d666c20a0` (schema 4). Every check
passed. That run printed:

- elections: 51 (1824–2024)
- cast-vote candidate-years: 132
- Table 1 rows: 102
- population: 30 (pre-1976 22, 1976+ 8)
- (c): 1868 Seymour (80 cast, 71 counted), 1872 Greeley (3, 0), 1872 Grant (300, 286)
- MIT values on 1976+ Table 1 rows: `DEMOCRAT` and `REPUBLICAN`, each on the D or R row
  respectively; on the 8 1976+ population rows: null on all

The numbers are that run's output. A re-run is the authority.

---

## §11 — Source reliability

- **VPB is inconsistent on two convention dates.** Its Van Buren chapter gives May 21, 1832 and
  May 20, 1835, and its Johnson chapter gives May 22 for both (VERIFIED). This doc cites it
  for parties only.
- **BDUSC dates some votes to the year after the election** (Floyd "1833", Mangum "1837"). Its
  party wording is checked against §4's map, not taken as a token.
- **BDUSC's La Follette entry** says only that he "several times unsuccessfully sought the
  Republican and Progressive Party presidential nominations" (VERIFIED), which is misleading on
  its own. §8 cites SFB-LaFollette instead.
- **Automated fetches were refused** by bioguide.congress.gov and the live senate.gov Vice
  President pages, and by loc.gov and congress.gov for one agent. The print editions on govinfo
  stand in for the first two.
- **Archives Notes for 1824–1860 say nothing about nominations.** They only explain the vote.

---

## §12 — The owner's calls at acceptance, what D077 records, and what passes on

**The owner accepted the verdict on 2026-10-17 (step 6 of the #384 plan) and made six calls:**
1. **Source code:** `USGOV` for the curated rows (§7).
2. **License:** `US-PD` (§7).
3. **Independent:** not a value, on the condition that no source of record assigns it to a
   recipient (§3, where the condition is checked). With it the owner set the **naming rule**:
   names merge into one code only when they name the same party, and the higher-ranked source's
   name is used (§2.1). It changed `peoples` to `populist`. At the code-review gate the owner
   chose option (B) for 1828 Jackson: `democratic_republican`, because the Archives token stands
   (BDUSC's "Democrat" names no different nominating body), and not because of the naming rule
   (§2.1). At the acceptance gate the owner accepted the partial link that makes 1824 Crawford
   `democratic_republican` (§2.1).
4. **Rule 3, an endorsement counts as a nomination,** with a note where a component rests on an
   endorsement and not a nomination. The owner also allowed the note for any other exceptional
   case (§2.4).
5. **Rule 5, a withdrawn nomination does not count,** with a note giving the facts (Davis, if
   confirmed).
6. **Rule 8, a source of record's "candidate of P" statement is accepted as P's nomination,** with
   a note. At the code-review gate the owner confirmed that this covers all eleven rows whose
   cited passages name no nominating body (§1 rule 8), not only the four first named (Wallace, La
   Follette, White, Webster). At the acceptance gate the owner added 1824 Crawford as a twelfth
   row, because his source says the caucus "supported" him. The per-row rule set that drives the
   required-note guard (§2.4) is the architect's design (§14), not one of the owner's calls.

**What D077 records.** It holds the rules and points at this doc for the evidence:
- **Rules:** §1's rules 1–8, the population (votes cast > 0, minus Table 1), the single-cause
  null and its four-part guard (§2.3), the evidence bar, source order and conflict rule (§6),
  MIT's check-only relation (§9), and the amendment to D018 (§9).
- **Policies:** one code per organization (with `democratic_republican` scoped to a name), and
  the naming rule (§2.1); joint codes as atomic values with declared components; `no_nomination`
  served; no `independent`; the row note, the per-row rule set and when a note is required
  (§2.4); the change procedure (§2.2).
- **The owner's six calls above.**
- **Three authorities, each for one thing:**
  - D077, for the rules;
  - `usvote/party.py` (#385), for the vocabulary, the token map, the correction constant, and
    the Table 1 rows' notes and rule sets (§4.1's Comment column is not their source);
  - the curated catalog (#387/#388), for the curated values, their notes, rule sets and
    citations.

  This doc is a dated evidence record, not an authority.
- **A guard:** #385 pins `party.py`'s vocabulary, each code with its component tuple, with a
  hand-written literal test, whose comment says a change needs a superseding D-entry (§2.2).

**Passed on:**
- **#385:** §4's map and its ranges, the 1872 Greeley correction, §4.2's open questions, parts
  1–3 of the null guard (§2.3), the MIT check with its floor and closed crosswalk, and its grain
  as a plan-gate question (§9), the D018 summary columns, the vocabulary literal with
  components (§2.2), and the row-note column with the Table 1 rows' notes, their rule sets and
  the required-note guard (§2.4).
- **#386:** the field's name and typing (§2.3), part 4 of the null guard on the served output
  (§2.3), serving the row note beside the value with `ba`'s wording (§2.4), `ba`'s rewrite of
  MIT `party`'s description (§9), the per-row source column and the `USGOV`/`US-PD` provenance
  pair (§7), the rollup carry (§9), and the schema 5 bump.
- **#387:** the C1 rows, including Hospers's source, the two-Progressives question, and a rule-3
  sweep of every C1 row for a second national body, as was done for Table 1 (e.g. whether a
  Socialist endorsement makes 1924 La Follette joint).
- **#388:** the C2 rows, each with a note on how its votes arose (§2.4), Davis's rule-5
  question, which decides whether he is C2 or needs a new code (§8.3), a government prose
  source for the South Carolina legislature's part in Floyd's and Mangum's votes (§0.2), and
  which kind of row Byrd's Alabama votes are (§5).
- **#389:** the export field set for the new field and its note (§7), the reader label and a
  qualified glossary term for MIT's `party`, since the glossary's Party entry and
  `labels.PARTY_NOTE` tie the word to the popular-vote source (§9), how the note is shown, the
  display forms (§2.1), and whether MIT's party leaves the CSV.

---

## §13 — Architect review of this verdict (2026-10-17)

A fresh `architect` reviewed the finished doc against #385–#389, read-only. Its verdict:
- **Blocking: none on design.** Two findings were blocking on the text, F1 and F2.
- **Important:** ten findings, F3–F12.
- **Minor:** eight notes, M1–M8.

All were adopted, and none was declined:
- **F1:** rule 2 became a closed list.
- **F2:** rule 8 was added, and made an owner call.
- **F3:** a reported nomination at any level bars `no_nomination`.
- **F4:** the null guard became four assertions, ending in equality.
- **F5:** `silver_republican` was dropped, and the change procedure added (§2.2).
- **F6:** the token ranges leave out the years a token does not print, and the map-entry and
  correction rule was added.
- **F7:** the curated row shape (§6.1).
- **F8:** D077 amends D018.
- **F9:** the per-row source column, and the CSV field-set route (§7).
- **F10:** the `Literal` typing note.
- **F11:** the script now prints MIT's party on the 1976+ population rows. All eight are null.
- **F12:** what D077 records, and the three authorities (§12).
- **M1:** the rollup's carry route.
- **M2:** field name vs reader label.
- **M3:** the CSV question passes to #389.
- **M4:** the license and source-code precedent (§7).
- **M5:** the C1 sweep passes to #387.
- **M6:** the 1860 Democratic sentence.
- **M7:** §4.2's uncited items became open questions.
- **M8:** rule 8 covers "supported".

The review is also recorded as a comment on #384.

**D077's slot was confirmed free when it was recorded** (2026-10-17): the last entry in
`decisions.md` on `main` was D076, and the only mentions of D077 on `main` were #384's own, in
`backlog-api.md`.

---

## §14 — Code review of this PR (2026-10-17)

**Round 1.** Three fresh reviewers read the PR: the code-review skill, a guard-efficacy lens, and
a `ba` wording finder. The wording finder's two checks were clean, because the PR ships no
reader-facing text. All 31 findings were acted on, after a fresh `architect` ruled on scope. Two
of them, the `ba` wording finder's findings on display names and on the word "note", were applied
in a modified form. The owner decided the two questions the architect referred:
- **1828 Jackson:** option (B), the Archives token standing (§2.1).
- **The rule-8 note:** it covers all eleven rows (§1).

The changes:
- **The script** compares the served set unfiltered, requires the snapshot by default, and
  asserts its MIT headlines. It labels the asserts that hold by construction as tripwires,
  records `git describe --dirty`, sends progress to stderr, and imports `MIT_PV_YEAR_MIN`.
- **The guards it prescribes:**
  - the null guard is split by layer, with part 4 read from the served output (§2.3);
  - the required-note guard is driven by a per-row rule set, the architect's design (§2.4);
  - the vocabulary literal pins component tuples (§2.2);
  - the MIT check gains a floor and a closed crosswalk (§9).
- **Wording:** the field's name and the reader's label are separated, and MIT `party`'s
  description rewrite is routed to #386 (§9). The display forms are `ba`'s, and the
  `no_nomination` wording was left to `ba` under three constraints (§2.2). The row note is
  named (§2.4).
- **Consistency:**
  - the grain sentence (§1) and the vocabulary's year column (§2.1);
  - `libertarian`'s basis (§2.1), and a fifth kind of C2 row (§5);
  - the §7 citations and §3's labels;
  - Davis's routing (§8.3), and D077's MIT skip rule and `no_nomination` definition.

**Round 2.** A fresh reviewer found the round-1 fixes discharged, apart from eight new findings.
The owner chose to drop the claim that BDUSC's 1828 "Democrat" is anachronistic, which no source
here supports: option (B) rests on the token standing alone (§2.1). The owner also attributed the
per-row rule set to the architect (§12). The rest were fixed as found: the verdict's "at most
once" and the grain wording, D077's `no_nomination` scope, null-guard summary and line wraps, the
script's tripwire reasons, check 2's label and its era labels, and this section's account of
round 1. A further fresh re-check found three more, all in wording: the PR description, two
finding IDs no reader could look up, and this section's labels. They were fixed, and the owner
chose to skip another re-check.

**Acceptance check.** A fresh verifier found every criterion met. It flagged four claims that went
beyond their citations and one contradiction about LOC's tables. Each claim was narrowed to what
its source says (§1 rules 1, 5 and 6, §2.4, §4.1, §11), §0.2 was reconciled with the footnote's
use, and the slot confirmation was written down (§13).

A fresh re-verify found eight more claims beyond their passages. The owner made 1824 Crawford a
twelfth rule-8 row, because SNP says his caucus "supported" him, and accepted the partial link
that makes him `democratic_republican` (§2.1). The rest were narrowed to their passages: the 1828
Tennessee resolution (§1 rule 2), Floyd's and Mangum's dates and the legislature footnote (§3,
§5, §8.1, §11), Byrd's unpledged electors with the CRS conflict routed to #388 (§5), the
"Independent" search (§3), and the 1856 Whig basis (§2.1).

