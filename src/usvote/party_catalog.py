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

#387 adds the C1 rows: candidates a party nominated (research doc §5, §8.1). #388 adds
the C2 rows (``no_nomination``) in the same shape.

**Stdlib-only, like** :mod:`usvote.party`. Its only ``usvote`` import is
:mod:`usvote.party`. ``tests/unit/test_layering.py`` enforces this.

**A passage is verbatim** from the fetched source: 40 words or fewer, with "…" marking
an omission. ``verified`` is the date the parent matched it against a fresh download
(AC4). No offline test can re-check that match. The research doc's §15 records it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from usvote.party import (
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
    "SNP": Source(
        "U.S. Senate",
        "Nominating Presidents",
        "https://www.senate.gov/about/parties-leadership/nominating-presidents.htm",
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
}


# --- citations and catalog entries --------------------------------------------

#: The most words a stored passage may have (research doc §6.1).
MAX_PASSAGE_WORDS = 40


@dataclass(frozen=True)
class Citation:
    """One passage from a registered source, and what it supports.

    ``supports`` names the party codes this passage backs. For a single code it is that
    code; for a joint code, the components it backs. Across a row's citations, the union
    must cover the value (:func:`check_curated_catalog`).
    """

    source_key: str
    locator: str
    passage: str
    verified: date
    supports: frozenset[str]


@dataclass(frozen=True)
class CatalogEntry:
    """A curated row and the citations it rests on; a row with none is refused."""

    row: CuratedPartyRow
    citations: tuple[Citation, ...]


# --- the row notes (wording by ``ba``, owner-approved 2026-10-20, #387 plan) -----

#: The note on a row resting on rule 8: its sources name the party but no nominating
#: body. Shared by every such row so that readers learn one marker. The pronoun fits
#: every row today; a future row it does not fit needs its own wording.
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


def _cite(
    source_key: str, locator: str, passage: str, *supports: str
) -> Citation:
    return Citation(source_key, locator, passage, _VERIFIED, frozenset(supports))


#: The date the parent matched every passage below against a fresh download (AC4).
_VERIFIED = date(2026, 10, 20)

_R8 = frozenset({8})

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
                "James S. Sherman, received 8 electoral votes each",
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
