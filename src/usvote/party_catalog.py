"""The curated nominating-party catalog (#387, D077, D078).

The rows of ``dwh.candidate_party`` that Archives Table 1 does not cover. Each row comes
from one or more cited U.S. Government works, not from a printed token (D077, Sources).
This module is the **third authority** D077 names. It holds the curated values, their
notes, their rule sets and their citations. :mod:`usvote.party` holds the vocabulary
and the Table 1 constants. D077 holds the rules.

- :data:`SOURCES` is the source registry. Each source of record has its publisher, its
  base URL and its **public-domain basis**. A citation names a registered source, so a
  privately printed work on a ``.gov`` host (research doc §0.2) cannot be cited by
  accident: it has no registry entry.
- :data:`CATALOG` holds the curated rows, each a :class:`CatalogEntry` pairing a
  :class:`~usvote.party.CuratedPartyRow` with its citations.
- :data:`CURATED_PARTY_ROWS` is the rows alone. It is the default
  :func:`usvote.transform.build_candidate_party` merges.
- :func:`check_curated_catalog` is the catalog's contract, run at import.

#387 added the C1 rows: candidates a party nominated (research doc §5, §8.1). #388 adds
the C2 rows (``no_nomination``) in the same shape (D079). A C2 citation records how the
candidate's votes arose, which states no party, so its ``supports`` is empty. What
stands for the absence of a nomination is the entry's ``searched`` record, since an
absence cannot be quoted (research doc §6.1). 1836 Mangum and 1872 Davis have no row:
the research doc's §16 gives each one's reason.

**Stdlib-only, like** :mod:`usvote.party`. Its only ``usvote`` import is
:mod:`usvote.party`.
``test_layering.py::test_the_party_catalog_module_imports_only_the_party_module``
enforces this.

**A passage is verbatim** from the fetched source: 40 words or fewer, with "…" marking
an omission. ``verified`` is the date the parent matched it against a fresh download
(AC4). No offline test can re-check that match. The research doc's §15 records it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from usvote.party import (
    NO_NOMINATION,
    NOMINATING_PARTIES,
    PARTY_COMPONENTS,
    TABLE1_PARTY_CORRECTIONS,
    TABLE1_ROW_NOTES,
    TABLE1_ROW_RULES,
    CuratedPartyRow,
    PartyContractError,
)

# --- the source registry ------------------------------------------------------

#: The public-domain basis of a work of the U.S. Government.
_FEDERAL_WORK = "a work of the U.S. Government (17 U.S.C. §105)"


@dataclass(frozen=True)
class Source:
    """A registered source of record: who published it, and why it is public domain."""

    publisher: str
    title: str
    url: str
    basis: str


#: Every source a catalog citation may name, keyed by the research doc's source keys
#: (§0.2). Only works of the U.S. Government. A member's own words in the bound
#: Congressional Record count, Extensions of Remarks included; matter inserted into the
#: Record does not (D078).
SOURCES: Mapping[str, Source] = {
    "VPB": Source(
        "U.S. Senate Historical Office",
        "Vice Presidents of the United States 1789–1993 (S. Doc. 104-26)",
        "https://www.govinfo.gov/content/pkg/CDOC-104sdoc26/pdf/CDOC-104sdoc26.pdf",
        _FEDERAL_WORK,
    ),
    "BDUSC": Source(
        "U.S. Congress, Joint Committee on Printing",
        "Biographical Directory of the United States Congress 1774–2005 "
        "(H. Doc. 108-222)",
        "https://www.govinfo.gov/content/pkg/GPO-CDOC-108hdoc222/pdf/"
        "GPO-CDOC-108hdoc222.pdf",
        _FEDERAL_WORK,
    ),
    "BDUSC-1927": Source(
        "U.S. Congress",
        "Biographical Directory of the American Congress 1774–1927 (H. Doc. 69-783)",
        "https://www.govinfo.gov/content/pkg/SERIALSET-08732_00_00-002-0783-0000/pdf/"
        "SERIALSET-08732_00_00-002-0783-0000.pdf",
        _FEDERAL_WORK,
    ),
    "ST-TN": Source(
        "U.S. Senate",
        "States in the Senate: Tennessee Timeline",
        "https://www.senate.gov/states/TN/timeline.htm",
        _FEDERAL_WORK,
    ),
    "SFB-LaFollette": Source(
        "U.S. Senate",
        "Robert La Follette: A Featured Biography",
        "https://www.senate.gov/senators/FeaturedBios/Featured_Bio_LaFollette.htm",
        _FEDERAL_WORK,
    ),
    "SFB-Thurmond": Source(
        "U.S. Senate",
        "Strom Thurmond: A Featured Biography",
        "https://www.senate.gov/senators/FeaturedBios/Featured_Bio_Thurmond.htm",
        _FEDERAL_WORK,
    ),
    "TRIB": Source(
        "U.S. Senate",
        "Tributes Delivered in Congress: Strom Thurmond (S. Doc. 107-12)",
        "https://www.govinfo.gov/content/pkg/CDOC-107sdoc12/pdf/CDOC-107sdoc12.pdf",
        _FEDERAL_WORK,
    ),
    "DOJ": Source(
        "U.S. Department of Justice",
        "Attorney General: William Wirt",
        "https://www.justice.gov/ag/bio/wirt-william",
        _FEDERAL_WORK,
    ),
    "ARCH-1912": Source(
        "U.S. National Archives and Records Administration",
        "1912 Electoral College Results",
        "https://www.archives.gov/electoral-college/1912",
        _FEDERAL_WORK,
    ),
    "ARCH-1968": Source(
        "U.S. National Archives and Records Administration",
        "1968 Electoral College Results",
        "https://www.archives.gov/electoral-college/1968",
        _FEDERAL_WORK,
    ),
    "LOC-1856": Source(
        "Library of Congress",
        "Presidential Election of 1856: A Resource Guide (the guide's own prose)",
        "https://guides.loc.gov/presidential-election-1856",
        _FEDERAL_WORK,
    ),
    "CR-1976": Source(
        "U.S. Congress",
        "Congressional Record, bound edition, vol. 122 (1976)",
        "https://www.govinfo.gov/content/pkg/GPO-CRECB-1976-pt27/pdf/"
        "GPO-CRECB-1976-pt27-1-3.pdf",
        _FEDERAL_WORK + "; a member's own words, not inserted matter (D078)",
    ),
    **{
        f"ARCH-{year}": Source(
            "U.S. National Archives and Records Administration",
            f"{year} Electoral College Results",
            f"https://www.archives.gov/electoral-college/{year}",
            _FEDERAL_WORK,
        )
        for year in (1832, 1872, 1956, 1960, 1976, 1988, 2004, 2016)
    },
    "ST-TX": Source(
        "U.S. Senate",
        "States in the Senate: Texas Timeline",
        "https://www.senate.gov/states/TX/timeline.htm",
        _FEDERAL_WORK,
    ),
    "ST-NC": Source(
        "U.S. Senate",
        "States in the Senate: North Carolina Timeline",
        "https://www.senate.gov/states/NC/timeline.htm",
        _FEDERAL_WORK,
    ),
    "CLERK-1960": Source(
        "U.S. House of Representatives, Clerk of the House",
        "Statistics of the Presidential and Congressional Election of November 8, 1960",
        "https://clerk.house.gov/member_info/electionInfo/1960election.pdf",
        _FEDERAL_WORK,
    ),
}


# --- citations and catalog entries --------------------------------------------

#: The most words a stored passage may have (research doc §6.1).
MAX_PASSAGE_WORDS = 40


@dataclass(frozen=True)
class Citation:
    """One passage from a registered source, and what it supports.

    ``supports`` names the party codes this passage backs. For a single code it is that
    code; for a joint code, the components it backs. Across a row's citations, the union
    must cover the value (:func:`check_curated_catalog`). A ``no_nomination`` row's
    citations say how the votes arose and back no code, so theirs is empty; only a
    passage stating the absence or a withdrawal would back ``no_nomination`` (D079).
    """

    source_key: str
    locator: str
    passage: str
    verified: date
    supports: frozenset[str]


@dataclass(frozen=True)
class CatalogEntry:
    """A curated row and the citations it rests on; a row with none is refused.

    ``searched`` records what was searched for a nomination, and is required on a
    ``no_nomination`` row (research doc §6.1). It is build metadata: it never reaches
    :class:`~usvote.party.CuratedPartyRow`, so it is neither stored nor served.
    """

    row: CuratedPartyRow
    citations: tuple[Citation, ...]
    searched: str | None = None


# --- the row notes (wording by ``ba``, owner-approved 2026-10-20, #387 plan) -----

#: The note on a row resting on rule 8: its sources name the party but no nominating
#: body. Shared by the rule-8 rows that need no other fact, so that readers learn one
#: marker; a rule-8 row with more to say (the 1836 Whigs, Fillmore) carries its own
#: note, which says the same. The pronoun fits every row today; a future row it does
#: not fit needs its own wording.
RULE_8_NOTE = (
    "This dataset's sources say which party he ran for, but do not name a convention, "
    "caucus or other body that nominated him."
)

#: The note on the two 1836 Whig rows (rules 2 and 8; VPB, Johnson chapter).
WHIG_1836_NOTE = (
    "The Whigs ran several candidates in 1836, nominated by local caucuses. This "
    "dataset's sources name him as one of them but do not say which caucus nominated "
    "him."
)

#: 1856 Fillmore (rules 3 and 8): the Know-Nothing nomination (VPB) and the Whig
#: endorsement (LOC-1856).
FILLMORE_1856_NOTE = (
    "Fillmore accepted the presidential nomination of the American Party "
    "(Know-Nothing), and the Whig Party endorsed him. This dataset treats that "
    "endorsement as a Whig nomination. This dataset's sources do not name a "
    "convention, caucus or other body that nominated or endorsed him."
)

#: 1924 La Follette: the body that nominated him has a different name from the party
#: the value names (BDUSC-1927; SFB-LaFollette; owner, D078).
LA_FOLLETTE_1924_NOTE = (
    "La Follette ran on the Progressive Party ticket, which the Conference for "
    "Progressive Political Action nominated at Cleveland."
)


#: The date the parent matched each C1 passage below against a fresh download (#387,
#: AC4).
_VERIFIED = date(2026, 10, 20)

#: The date the parent matched each C2 passage against a fresh download (#388; UTC,
#: research doc §16).
_VERIFIED_C2 = date(2026, 10, 21)


def _cite(
    source_key: str,
    locator: str,
    passage: str,
    *supports: str,
    verified: date = _VERIFIED,
) -> Citation:
    return Citation(source_key, locator, passage, verified, frozenset(supports))


def _origin(source_key: str, locator: str, passage: str) -> Citation:
    """A C2 citation: how the votes arose, backing no code (D079)."""
    return _cite(source_key, locator, passage, verified=_VERIFIED_C2)

_R8 = frozenset({8})

# --- the C2 notes (wording by ``ba``, owner-approved 2026-10-21, #388 plan) ----------
#
# A C2 note says only how the candidate's electoral votes arose. On the dashboard it
# follows ``labels.NO_NOMINATION_NOTE``, so none repeats that no party nominated them.

#: 1832 Floyd. ARCH-1832; the year is the election's (BDUSC dates the vote 1833, when
#: Congress counted it). No "legislature": the source naming South Carolina's
#: legislature covers 1832 only by inference (research doc §16).
FLOYD_1832_NOTE = (
    "South Carolina cast 11 electoral votes for Floyd for President in 1832."
)

#: 1872 Hendricks. VPB names the Greeley fusion ticket; ARCH-1872 the scatter.
HENDRICKS_1872_NOTE = (
    "The Democrats and the Liberal Republicans nominated Horace Greeley for President "
    "in 1872. Greeley died before the electors voted, and electors in several states "
    "then voted for various candidates. Some voted for Hendricks for President."
)

#: 1872 Brown, Greeley's running mate (ARCH-1872).
BROWN_1872_NOTE = (
    "Brown was Horace Greeley's running mate in 1872. Greeley died before the electors "
    "voted, and electors in several states then voted for various candidates. Some "
    "voted for Brown for President."
)

#: 1872 Jenkins, from Georgia's electors (ARCH-1872, note 4).
JENKINS_1872_NOTE = (
    "Horace Greeley died before the electors voted in 1872, and electors in several "
    "states then voted for various candidates. Two Georgia electors voted for Jenkins "
    "for President."
)

JONES_1956_NOTE = "In 1956, one Alabama elector voted for Jones for President."

#: 1960 Byrd: one sentence per passage, so the note never says the unpledged slate won
#: Mississippi; Alabama's six and Oklahoma's one are given no kind, because U.S.
#: Government sources disagree on it (research doc §16, D079).
BYRD_1960_NOTE = (
    "In 1960, Mississippi's popular vote included votes for unpledged Democratic "
    "electors, who later agreed to support Byrd. He received electoral votes for "
    "President from Mississippi (8), Alabama (6) and Oklahoma (1)."
)

REAGAN_1976_NOTE = (
    "In 1976, one Washington State elector voted for Reagan for President."
)

BENTSEN_1988_NOTE = (
    "Bentsen ran for Vice President on the Democratic ticket in 1988. One West "
    "Virginia elector voted for him for President and for Dukakis for Vice President."
)

EDWARDS_2004_NOTE = (
    "Edwards was the Democratic nominee for Vice President in 2004. One Minnesota "
    "elector voted for him for both President and Vice President."
)

#: The 2016 notes, one per state; each is true of every row that carries it.
HAWAII_2016_NOTE = (
    "In 2016, one Hawaii elector cast a faithless vote for Bernie Sanders for "
    "President."
)
TEXAS_2016_NOTE = (
    "In 2016, two Texas electors cast faithless votes for President: one for Ron Paul "
    "and one for John Kasich."
)
WASHINGTON_2016_NOTE = (
    "In 2016, four Washington electors cast faithless votes for President: three for "
    "Colin Powell and one for Faith Spotted Eagle."
)

# --- what was searched for each C2 row (research doc §6.1, §16) -----------------
#
# An absence cannot be quoted, so each C2 row records what was searched for a
# presidential nomination. Not served. The research doc's §16 lists the works.

_SEARCHED_1832 = (
    "U.S. Government works on the 1832 election (research doc §16), for a presidential "
    "nomination of Floyd by any body, a Nullifier one included: none found."
)
_SEARCHED_1872 = (
    "VPB, BDUSC and ARCH-1872 (research doc §16), for a presidential nomination in "
    "1872: none found; the Democrats and the Liberal Republicans nominated Greeley."
)
_SEARCHED_1956 = (
    "ARCH-1956 and the U.S. Government works research doc §16 lists, for a "
    "presidential nomination of Jones in 1956: none found."
)
_SEARCHED_1960 = (
    "ARCH-1960, the House Clerk's 1960 statistics, the Statistical Abstract 1961, CRS "
    "RL32611, the House Historian and the Congressional Record of 1961–62 (research "
    "doc §16), for a presidential nomination of Byrd: none found."
)
_SEARCHED_1976 = (
    "ARCH-1976 (research doc §16), for a 1976 presidential nomination of Reagan: none "
    "found."
)
_SEARCHED_VP = (
    "BDUSC and the Senate state timeline (research doc §16): a nomination for Vice "
    "President that year; no presidential nomination found."
)
_SEARCHED_2016 = (
    "ARCH-2016 and the BDUSC entries for Paul, Sanders and Kasich (research doc §16), "
    "for a 2016 presidential nomination of any of the five: none found."
)

#: VPB's Johnson chapter, p. 127, cited by both 1836 Whig rows.
_VPB_1836_WHIGS = (
    _cite(
        "VPB",
        "ch. 9, Richard Mentor Johnson, p. 127",
        "The Whig presidential candidates were Daniel Webster, Tennessee "
        "Senator and former Jacksonian Hugh Lawson White, and Johnson's former "
        "commander, General William Henry Harrison.",
        "whig",
    ),
    _cite(
        "VPB",
        "ch. 9, Richard Mentor Johnson, p. 127",
        "they offered a series of sectional candidates nominated by local "
        "caucuses",
        "whig",
    ),
)

#: ARCH-2016's three faithless-vote notes, each cited by every row it names.
_ARCH_2016_HAWAII = (
    "Due to faithless voting, the electoral votes for Hawaii were: for President, "
    "Clinton 3 and Bernie Sanders 1"
)
_ARCH_2016_TEXAS = (
    "Due to faithless voting, the electoral votes for Texas were: for President, "
    "Trump 36, Ron Paul 1, and John Kasich 1"
)
_ARCH_2016_WASHINGTON = (
    "Due to faithless voting, the electoral votes for Washington were: for President, "
    "Clinton 8, Colin Powell 3, and Faith Spotted Eagle 1"
)

#: The curated rows. Keys are ``(year, name)`` as the candidate dimension spells the
#: name. Rule sets and notes follow D077 §2.4.
CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        CuratedPartyRow(1824, "William H. Crawford", "democratic_republican"),
        (
            _cite(
                "VPB",
                "ch. 8, Martin Van Buren, p. 107",
                "Van Buren backed the Republican caucus nominee, Treasury Secretary "
                "William H. Crawford.",
                "democratic_republican",
            ),
            _cite(
                "BDUSC",
                "CRAWFORD, William Harris, p. 892",
                "unsuccessful Democratic Republican candidate for President of the "
                "United States in 1824",
                "democratic_republican",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(
            1824, "Henry Clay", "democratic_republican", frozenset({2, 8}), RULE_8_NOTE
        ),
        (
            _cite(
                "BDUSC",
                "CLAY, Henry, p. 833",
                "unsuccessful presidential candidate of the Democratic Republican "
                "Party in 1824",
                "democratic_republican",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(1832, "William Wirt", "anti_masonic", _R8, RULE_8_NOTE),
        (
            _cite(
                "DOJ",
                "Attorney General: William Wirt",
                "In 1831, Wirt accepted the nomination of the Anti-Masonic Party for "
                "the presidency of the United States",
                "anti_masonic",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(
            1836, "Hugh L. White", "whig", frozenset({2, 8}), WHIG_1836_NOTE
        ),
        (
            *_VPB_1836_WHIGS,
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(
            1836, "Daniel Webster", "whig", frozenset({2, 8}), WHIG_1836_NOTE
        ),
        (
            _cite(
                "BDUSC",
                "WEBSTER, Daniel, p. 2131",
                "unsuccessful Whig candidate for president in 1836",
                "whig",
            ),
            *_VPB_1836_WHIGS,
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(
            1856,
            "Millard Fillmore",
            "american_whig",
            frozenset({3, 8}),
            FILLMORE_1856_NOTE,
        ),
        (
            _cite(
                "VPB",
                "ch. 12, Millard Fillmore, p. 176",
                "accepting the 1856 presidential nomination of the anti-Catholic, "
                "anti-immigrant Know-Nothing party",
                "american",
            ),
            _cite(
                "LOC-1856",
                "Introduction",
                "Former president Millard Fillmore was the American Party "
                "(Know-Nothing) candidate, a nativist party that was anti-Catholic and "
                "anti-immigrant. The Whig Party also endorsed Fillmore for president.",
                "american",
                "whig",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(
            1860, "John C. Breckinridge", "southern_democratic", frozenset({6})
        ),
        (
            _cite(
                "VPB",
                "ch. 14, John Cabell Breckinridge, p. 197",
                "the southern delegates walked out. They held their own convention in "
                "Baltimore and nominated Breckinridge as their presidential candidate.",
                "southern_democratic",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(1860, "John Bell", "constitutional_union", _R8, RULE_8_NOTE),
        (
            _cite(
                "ST-TN",
                "1860, May 10",
                "Former senator John Bell of Nashville was nominated for president of "
                "the United States by the Constitutional Union Party",
                "constitutional_union",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(1892, "James B. Weaver", "populist", _R8, RULE_8_NOTE),
        (
            _cite(
                "BDUSC",
                "WEAVER, James Baird, p. 2129",
                "Populist candidate for President in 1892",
                "populist",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(1912, "William H. Taft", "republican", _R8, RULE_8_NOTE),
        (
            _cite(
                "ARCH-1912",
                "Notes",
                "Republican Party candidate Taft, and Vice Presidential running mate "
                "James S. Sherman, received 8 electoral votes each, but Sherman died "
                "just before the election.",
                "republican",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(
            1924,
            "Robert M. La Follette",
            "progressive_1924",
            frozenset(),
            LA_FOLLETTE_1924_NOTE,
        ),
        (
            _cite(
                "BDUSC-1927",
                "LA FOLLETTE, Robert Marion, p. 1197",
                "unsuccessful candidate for President of the United States in 1924 on "
                "the ticket nominated at Cleveland by the conference for progressive "
                "political action",
                "progressive_1924",
            ),
            _cite(
                "SFB-LaFollette",
                "Robert La Follette: A Featured Biography",
                "ran for president on the Progressive Party ticket in 1924",
                "progressive_1924",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(
            1948, "J. Strom Thurmond", "states_rights_democratic", _R8, RULE_8_NOTE
        ),
        (
            _cite(
                "TRIB",
                "tribute by Mr. Craig, p. 55",
                "as the nominee of the States Rights Democratic Party, and won 39 "
                "electoral votes",
                "states_rights_democratic",
            ),
            _cite(
                "SFB-Thurmond",
                "Strom Thurmond: A Featured Biography",
                "He ran as the States’ Rights Democratic (also known as Dixiecrat) "
                "candidate for president in 1948",
                "states_rights_democratic",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(
            1968, "George C. Wallace", "american_independent", _R8, RULE_8_NOTE
        ),
        (
            _cite(
                "ARCH-1968",
                "Notes",
                "American Independent Party candidate Wallace received 9,906,473 "
                "popular votes for President.",
                "american_independent",
            ),
        ),
    ),
    CatalogEntry(
        CuratedPartyRow(1972, "John Hospers", "libertarian", _R8, RULE_8_NOTE),
        (
            _cite(
                "CR-1976",
                "vol. 122, pt. 27, p. 35649, Extensions of Remarks, Oct. 1, 1976, "
                "Hon. Ron Paul",
                "the Libertarian Party held its convention here in Washington. … In "
                "1972, its presidential candidate, Prof. John Hospers of Southern "
                "California University, finished third in electoral votes",
                "libertarian",
            ),
        ),
    ),
    # --- C2: no_nomination (#388, D079). Citations give the votes' origin. ---------
    CatalogEntry(
        CuratedPartyRow(1832, "John Floyd", NO_NOMINATION, note=FLOYD_1832_NOTE),
        (
            _origin(
                "ARCH-1832",
                "Electoral College Votes by State, note 5",
                "South Carolina cast 11 votes for Floyd as President and 11 votes for "
                "Lee as Vice President.",
            ),
            _origin(
                "BDUSC",
                "FLOYD, John, a Representative from Virginia, p. 1065",
                "received the electoral vote of South Carolina for President in 1833",
            ),
        ),
        _SEARCHED_1832,
    ),
    CatalogEntry(
        CuratedPartyRow(
            1872, "Thomas A. Hendricks", NO_NOMINATION, note=HENDRICKS_1872_NOTE
        ),
        (
            _origin(
                "VPB",
                "ch. 21, Thomas A. Hendricks, p. 263",
                "The Democrats instead nominated the eccentric newspaper editor Horace "
                "Greeley for president on a fusion ticket with liberal Republicans",
            ),
            _origin(
                "ARCH-1872",
                "Notes, note 2",
                "Following Greeley's death, electors in several states cast their "
                "votes variously for President or Vice President.",
            ),
            _origin(
                "ARCH-1872",
                "Electoral College Votes by State, note 6",
                "In Maryland, Hendricks received 8 electoral votes for President",
            ),
        ),
        _SEARCHED_1872,
    ),
    CatalogEntry(
        CuratedPartyRow(
            1872, "Benjamin Gratz Brown", NO_NOMINATION, note=BROWN_1872_NOTE
        ),
        (
            _origin(
                "ARCH-1872",
                "Notes, note 2",
                "Following Greeley's death, electors in several states cast their "
                "votes variously for President or Vice President. Benjamin Gratz "
                "Brown, Greeley's running mate, received 18 electoral votes for "
                "President",
            ),
            _origin(
                "BDUSC",
                "BROWN, Benjamin Gratz, p. 718",
                "unsuccessful Democratic candidate for Vice President of the United "
                "States on the ticket with Horace Greeley in 1872",
            ),
        ),
        _SEARCHED_1872,
    ),
    CatalogEntry(
        CuratedPartyRow(
            1872, "Charles J. Jenkins", NO_NOMINATION, note=JENKINS_1872_NOTE
        ),
        (
            _origin(
                "ARCH-1872",
                "Notes, note 2",
                "Following Greeley's death, electors in several states cast their "
                "votes variously for President or Vice President.",
            ),
            _origin(
                "ARCH-1872",
                "Electoral College Votes by State, note 4",
                "In Georgia, Greeley received 3 electoral votes for President, but "
                "these were not counted … Jenkins received 2 electoral votes for "
                "President",
            ),
        ),
        _SEARCHED_1872,
    ),
    CatalogEntry(
        CuratedPartyRow(1956, "Walter B. Jones", NO_NOMINATION, note=JONES_1956_NOTE),
        (
            _origin(
                "ARCH-1956",
                "Notes; Electoral College Votes by State, For President",
                "An Alabama elector voted for Jones and Talmadge.",
            ),
        ),
        _SEARCHED_1956,
    ),
    CatalogEntry(
        CuratedPartyRow(1960, "Harry F. Byrd", NO_NOMINATION, note=BYRD_1960_NOTE),
        (
            _origin(
                "CLERK-1960",
                "Electoral and popular votes, Mississippi, footnote 4, printed pp. "
                "50–51 (PDF pp. 51–52)",
                "Unpledged Democratic elector vote, who later agreed to support "
                "Senator Byrd.",
            ),
            _origin(
                "ARCH-1960",
                "Notes",
                "Byrd received electoral votes for President from Alabama (6), "
                "Mississippi (8) and Oklahoma (1).",
            ),
        ),
        _SEARCHED_1960,
    ),
    CatalogEntry(
        CuratedPartyRow(1976, "Ronald Reagan", NO_NOMINATION, note=REAGAN_1976_NOTE),
        (
            _origin(
                "ARCH-1976",
                "Notes; Electoral College Votes by State, For President",
                "A Washington (State) elector voted for Ronald Reagan.",
            ),
        ),
        _SEARCHED_1976,
    ),
    CatalogEntry(
        CuratedPartyRow(1988, "Lloyd Bentsen", NO_NOMINATION, note=BENTSEN_1988_NOTE),
        (
            _origin(
                "ST-TX",
                "1988, November 8",
                "Senator Lloyd M. Bentsen Jr. ran unsuccessfully for vice president on "
                "the Democratic ticket with presidential candidate Michael Dukakis",
            ),
            _origin(
                "ARCH-1988",
                "Notes",
                "A West Virginia elector voted for Bentsen as President and Dukakis as "
                "Vice President.",
            ),
        ),
        _SEARCHED_VP,
    ),
    CatalogEntry(
        CuratedPartyRow(2004, "John Edwards", NO_NOMINATION, note=EDWARDS_2004_NOTE),
        (
            _origin(
                "ST-NC",
                "2004, July 28",
                "Senator John Edwards of Raleigh was nominated for vice president of "
                "the United States on the Democratic Party ticket headed by another "
                "incumbent senator, John F. Kerry",
            ),
            _origin(
                "ARCH-2004",
                "Notes, below the state table",
                "One Minnesota elector voted for John Edwards for both President and "
                "Vice President.",
            ),
        ),
        _SEARCHED_VP,
    ),
    *(
        CatalogEntry(
            CuratedPartyRow(2016, name, NO_NOMINATION, note=note),
            (_origin("ARCH-2016", f"Notes, below the state table, note {mark}", text),),
            _SEARCHED_2016,
        )
        for name, note, mark, text in (
            ("Bernie Sanders", HAWAII_2016_NOTE, "*", _ARCH_2016_HAWAII),
            ("Ron Paul", TEXAS_2016_NOTE, "***", _ARCH_2016_TEXAS),
            ("John Kasich", TEXAS_2016_NOTE, "***", _ARCH_2016_TEXAS),
            ("Colin Powell", WASHINGTON_2016_NOTE, "****", _ARCH_2016_WASHINGTON),
            (
                "Faith Spotted Eagle",
                WASHINGTON_2016_NOTE,
                "****",
                _ARCH_2016_WASHINGTON,
            ),
        )
    ),
)

#: The curated rows alone: the input :func:`usvote.transform.build_candidate_party`
#: merges by default.
CURATED_PARTY_ROWS: tuple[CuratedPartyRow, ...] = tuple(e.row for e in CATALOG)

#: The curated rows by ``(year, name)``.
CURATED_BY_KEY: Mapping[tuple[int, str], CuratedPartyRow] = {
    (row.year, row.name): row for row in CURATED_PARTY_ROWS
}


# --- the contract --------------------------------------------------------------


def check_curated_catalog(
    catalog: Sequence[CatalogEntry],
    sources: Mapping[str, Source] = SOURCES,
) -> None:
    """Raise unless every catalog row is cited and in the vocabulary.

    Each of these fails it:

    - a row with no citation;
    - a value outside :data:`~usvote.party.NOMINATING_PARTIES`;
    - a key that appears twice, or that is a key of a Table 1 constant (a curated
      row only fills a candidate-year Table 1 does not cover);
    - a citation naming an unregistered source;
    - a passage that is blank or longer than :data:`MAX_PASSAGE_WORDS` words;
    - citations whose ``supports`` do not cover the value: every component of a joint
      code, or the code itself;
    - a citation backing a code that is neither the value nor one of its components;
    - a citation backing nothing, except on a ``no_nomination`` row, whose citations
      give the votes' origin and back no code (D079);
    - a ``no_nomination`` row with a blank note or a blank ``searched`` record;
    - a registered source whose URL is not ``https``, or whose basis is blank.

    Run at import over :data:`CATALOG`. The parameters let a test hand in a broken
    catalog.
    """
    problems: list[str] = []
    for source_key, source in sources.items():
        if not source.url.startswith("https://"):
            problems.append(f"source {source_key!r} has a non-https URL")
        if not source.basis.strip():
            problems.append(f"source {source_key!r} states no public-domain basis")

    table1_keys = set(TABLE1_PARTY_CORRECTIONS) | set(TABLE1_ROW_RULES)
    table1_keys |= set(TABLE1_ROW_NOTES)
    seen: set[tuple[int, str]] = set()
    for entry in catalog:
        row = entry.row
        key = (row.year, row.name)
        if key in seen:
            problems.append(f"{key} appears twice")
        seen.add(key)
        if key in table1_keys:
            problems.append(f"{key} is a Table 1 row")
        if row.party not in NOMINATING_PARTIES:
            problems.append(f"{key} has {row.party!r}, which is not a code")
            continue
        if not entry.citations:
            problems.append(f"{key} has no citation")
            continue
        for citation in entry.citations:
            if citation.source_key not in sources:
                problems.append(
                    f"{key} cites {citation.source_key!r}, which is not registered"
                )
            words = len(citation.passage.split())
            if not citation.passage.strip() or words > MAX_PASSAGE_WORDS:
                problems.append(
                    f"{key} has a passage of {words} words "
                    f"(1 to {MAX_PASSAGE_WORDS} allowed)"
                )
            allowed = set(PARTY_COMPONENTS[row.party]) | {row.party}
            if stray := citation.supports - allowed:
                problems.append(f"{key} has a citation backing {sorted(stray)}")
            if not citation.supports and row.party != NO_NOMINATION:
                problems.append(f"{key} has a citation backing no code")
        if row.party == NO_NOMINATION:
            # The absence is the search record's, not a passage's (research doc §6.1).
            if not (row.note or "").strip():
                problems.append(f"{key} is no_nomination with no note")
            if not (entry.searched or "").strip():
                problems.append(f"{key} is no_nomination with no searched record")
            continue
        needed = set(PARTY_COMPONENTS[row.party]) or {row.party}
        supported = set().union(*(c.supports for c in entry.citations))
        if not needed <= supported:
            problems.append(
                f"{key}: no citation supports {sorted(needed - supported)}"
            )
    if problems:
        raise PartyContractError(
            "the curated nominating-party catalog is malformed: " + "; ".join(problems)
        )


check_curated_catalog(CATALOG)
