# The governing census: sources and checks

Each per-capita row reads the population of one census, its **governing census**
(`governing_census_year`): the census of the latest apportionment of House seats made before the
election, when the state's electors were chosen. That is the census the law ties a state's
electoral votes to. A state has as many electors as the senators and representatives it is entitled
to when the President chosen at that election takes office, except that where no apportionment has
followed the latest census by the time electors are chosen, the existing apportionment applies
([11], [12]).

The dashboard explains the choice in one line under each per-capita table,
`labels.GOVERNING_CENSUS_NOTE`, which read as follows on 2026-11-02 (its rewording is #423):

> Each election uses the census that set the state's electoral votes, not the nearest one: 2020
> uses the 2010 census, and 1924 and 1928 use 1910, because Congress did not redistribute House
> seats after the 1920 census.

This page records the sources for that note and the check of the pipeline's election → census
mapping against them, so the research is not repeated (#356). Checked 2026-11-02.

## Findings

| Claim in the note | Finding | Sources |
|---|---|---|
| Congress did not redistribute House seats after the 1920 census. | **Confirmed.** No apportionment act followed the 1920 census, the only census in US history without one. The next apportionment came under the act of June 18, 1929, which made reapportionment automatic from the 1930 census. | [1] note 2; [2]; [3] |
| 1924 and 1928 use the 1910 census. | **Confirmed.** With no apportionment after the 1920 census, electors were chosen in 1924 and 1928 under the existing one, the 1910 census's (the act of August 8, 1911). Every state's allotment is the same in 1912, 1916, 1920, 1924 and 1928. | [1] note 2; [4]; [11]; [12]; this dataset (below) |
| 2020 uses the 2010 census. | **Confirmed.** The President transmits each apportionment at the first regular session of the Eighty-second Congress (1951) "and of each fifth Congress thereafter", so the 2020 census's came in 2021, after the 2020 electors were chosen. 2020 therefore used the existing 2010 apportionment, which had set 2012 and 2016 as well; the 2020 census's first set 2024. | [6]; [7]; [12]; this dataset |
| Each election uses the census that set the state's electoral votes. | **True for every state-year except those in the next section.** 2,152 of the 2,174 non-zero state allotments outside DC equal two plus the House seats apportioned from the governing census. The other 22 are the admission rows and West Virginia's two rows listed below. California 1852–1860 matches the table, but its seats came from its admission act; DC is outside the count. For all of these the governing census is still the census of the latest apportionment, but it did not set that state's electoral votes. | [1] notes 3, 5, 7; [8] |

The note's three examples stand. Its opening clause overstates for the rows in the next section;
rewording it is #423 (owner decision, 2026-11-02, at #356's acceptance-criterion 4).

## Where a census did not set a state's electoral votes

A state's electoral votes equal its senators plus its representatives (U.S. Const. art. II, § 1,
cl. 2; [11]; [12]), so a census sets them through the House apportionment. Some rows take their
seats from somewhere else:

- **A state at the elections between its admission and the next census's apportionment (20
  state-years).** "As new states joined the Union, the House assigned a specific number of
  Representatives to that state," and the next census's apportionment replaced it ([1] note 3).
  Arkansas and Michigan 1836 and 1840; Florida, Iowa, Texas and Wisconsin 1848; Minnesota and
  Oregon 1860; Nevada 1864 and 1868; Nebraska 1868; Colorado 1876 and 1880; Utah 1896 and 1900;
  Oklahoma 1908 (five seats, [5] note 3); Alaska and Hawaii 1960 (one seat each, [5] note 1).
- **West Virginia, 1864 and 1868 (2 state-years).** When it was formed in 1863 it was assigned
  three of Virginia's 1860 seats ([1] note 7), so these rows match no census's figure for West
  Virginia.
- **California, 1852–1860.** Its 1850 census returns were incomplete when the apportionment law
  passed in 1852, so Congress allowed it two representatives, "as prescribed in the act of
  admission," until the next census ([1] note 5). The Historian's table lists those two seats under
  1850, so the comparison below counts these rows as matches.
- **The District of Columbia, from 1964.** Its electors are set by the Twenty-third Amendment: as
  many as it would have if it were a state, but no more than the least populous state ([8]). No
  census apportionment sets them.

These rows still show the population of their governing census, where it has one. Texas 1848 has
none: Texas was not part of the United States at the 1840 census, so the row carries no population
(`no_governing_figure`).

Arizona and New Mexico (1912) are not exceptions: the 1911 act provided their seats in advance of
admission ([1] note 4; [3]).

## Each census and the first election it governed

The first election a census governed is the first one at which the allotments it set appear. In
this dataset every change in a state's allotment, between two elections at which it had one,
falls on an election in this table's third column, or on 1868, when seven states that had none in
1864 took part again after the Civil War. No allotment changes at any other election.

| Census | Apportionment | First election governed | Elections governed |
|---|---|---|---|
| 1820 | Act of March 7, 1822 | 1824 | 1824, 1828 |
| 1830 | Act of May 22, 1832 | 1832 | 1832–1840 |
| 1840 | Act of June 25, 1842 | 1844 | 1844, 1848 |
| 1850 | Act of May 23, 1850 (amended June 30, 1852) | 1852 | 1852–1860 |
| 1860 | Act of March 4, 1862, which raised the House to 241 seats (the 1850 act had set 233 and the method) | 1864 | 1864, 1868 |
| 1870 | Acts of February 2 and May 30, 1872 | 1872 | 1872–1880 |
| 1880 | Act of February 25, 1882 | 1884 | 1884, 1888 |
| 1890 | Act of February 7, 1891 | 1892 | 1892–1900 |
| 1900 | Act of January 16, 1901 | 1904 | 1904, 1908 |
| 1910 | Act of August 8, 1911 | 1912 | 1912–1928 |
| 1920 | none | — | — |
| 1930 | Automatic, act of June 18, 1929 | 1932 | 1932–1940 |
| 1940 onward | Automatic (2 U.S.C. § 2a; method set by the act of November 15, 1941) | the census year plus 2 or 4: 1944, 1952, 1964, 1972, 1984, 1992, 2004, 2012, 2024 | until the next census's first election |

Act dates are as the Census Bureau lists them ([3], [9], [10]). 1824 is the first election in this
dataset.

## How the mapping was checked

The function `governing_census_year` in `src/usvote/apportionment.py` returns the latest census,
at or before two years before the election, that produced an apportionment, so 1920 is skipped.
`GOVERNING_CENSUS_BY_ELECTION` is that function over every election in the dataset. The check, run
2026-11-02 against the API snapshot built 2026-10-21 (`snapshot_version`
`37af4064698c8e1519675c90f1b2b05353f5ed791207ad2b28767457fd62e8f7`, read only):

1. **Mapping.** Every one of the 2,204 per-capita rows carries the census
   `GOVERNING_CENSUS_BY_ELECTION` gives for its year: 0 disagreements over 51 elections, 1824–2024.
2. **Change years.** For each state, comparing each non-zero allotment with its previous
   non-zero one, the changes fall at 1832, 1844, 1852, 1864, 1872, 1884, 1892, 1904, 1912, 1932,
   1944, 1952, 1964, 1972, 1984, 1992, 2004, 2012 and 2024, each the first election after an
   apportioning census. The only other is 1868, for seven states that had no allotment in 1864: the
   1860 census's allotment is their first since 1860's. Mississippi, Texas and Virginia also had
   none in 1868 and returned in 1872, on the 1870 census's allotment. No allotment changes in
   1916–1928.
3. **Per state-year.** Each non-zero allotment outside DC was compared with two plus the seats
   the House Historian's table ([1], transcribed by hand; every column sums to the table's Total
   row) gives the state under its governing census. 2,152 of 2,174 match; the 22 that do not are
   the 20 admission rows and West Virginia's 2 listed above. The 14 zero-allotment rows (eleven
   states in 1864, and Mississippi, Texas and Virginia in 1868) were left out.

The mapping agrees with the findings for every election year, so nothing was filed against it.
Two tests already pin it: `test_the_mapping_matches_the_hand_written_oracle` in
`tests/unit/test_apportionment.py` (every election, against a hand-written list), and
`test_the_allotment_change_years_match_this_mapping` in `tests/integration/test_census_conform.py`
(check 2, against `dwh.votes`).

## Sources

1. Office of the Historian, U.S. House of Representatives. "Representatives Apportioned to Each
   State (1st to 24th Census, 1790–2020)." <https://history.house.gov/Institution/Apportionment/state_apportionment_pdf_2021/>
   (linked from <https://history.house.gov/Institution/Apportionment/Apportionment/>).
2. Office of the Historian, U.S. House of Representatives. "The Permanent Apportionment Act of
   1929." <https://history.house.gov/Historical-Highlights/1901-1950/The-Permanent-Apportionment-Act-of-1929/>
3. U.S. Census Bureau. "Apportionment Legislation 1890 – Present."
   <https://www.census.gov/about/history/historical-censuses-and-surveys/census-programs-surveys/decennial-census/legislation-1890-present.html>
4. Act of August 8, 1911, ch. 5, 37 Stat. 13 (Pub. L. 62-5), § 1: "after the third day of March,
   nineteen hundred and thirteen." <https://www.govinfo.gov/link/statute/37/13>
5. U.S. Census Bureau. "Congressional Apportionment: Historical Apportionment Data (1910–2020)."
   <https://www.census.gov/data/tables/time-series/dec/apportionment-data-text.html>
6. National Archives. "Distribution of Electoral Votes" (U.S. Electoral College): "The
   allocations below are based on the 2020 Census. They are effective for the 2024 and 2028
   presidential elections." <https://www.archives.gov/electoral-college/allocation>
7. 2 U.S.C. § 2a (act of June 18, 1929, ch. 28, § 22, 46 Stat. 26; amended November 15, 1941,
   ch. 470, 55 Stat. 761): the President transmits the apportionment at the first regular session
   of the Eighty-second Congress and of each fifth Congress thereafter. Also Congressional Research
   Service, *Apportionment and Redistricting Process for the U.S. House of Representatives*,
   R45951. <https://www.law.cornell.edu/uscode/text/2/2a>
8. U.S. Const. amend. XXIII, § 1 (ratified March 29, 1961).
   <https://www.archives.gov/founding-docs/amendments-11-27>
9. U.S. Census Bureau. "Apportionment Legislation 1790 – 1830."
   <https://www.census.gov/about/history/historical-censuses-and-surveys/census-programs-surveys/decennial-census/legislation-1790-1830.html>
10. U.S. Census Bureau. "Apportionment Legislation 1840 – 1880."
    <https://www.census.gov/about/history/historical-censuses-and-surveys/census-programs-surveys/decennial-census/legislation-1840-1880.html>
11. Act of March 1, 1792, ch. 8, § 1, 1 Stat. 239: electors "equal to the number of Senators and
    Representatives, to which the several states may by law be entitled at the time, when the
    President and Vice President, thus to be chosen, should come into office: Provided always,
    That where no apportionment of Representatives shall have been made after any enumeration, at
    the time of choosing electors, then the number of electors shall be according to the existing
    apportionment." <https://www.govinfo.gov/link/statute/1/239> (text as transcribed at
    <https://en.wikisource.org/wiki/Presidential_Succession_Act_1792>).
12. 3 U.S.C. § 3 (June 25, 1948, ch. 644, 62 Stat. 672), which carries the same rule and
    proviso today. <https://www.law.cornell.edu/uscode/text/3/3>
