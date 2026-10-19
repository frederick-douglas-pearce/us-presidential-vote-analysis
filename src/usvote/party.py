"""The nominating-party contract for ``dwh.candidate_party`` (#385, D077).

The **nominating party** of a candidate-year is the national body that nominated the
candidate for President that year (D077 §1). Archives Table 1 prints a party token for
each election's President and Main Opponent; this module holds what turns those tokens
into values, and the rules every value obeys:

- :data:`PARTY_COMPONENTS` — the **closed vocabulary**, each code with its component
  parties (a single code maps to ``()``, a joint nomination to its components in order).
- :data:`TABLE1_TOKEN_MAP` — the **year-scoped** map from a printed Table 1 token to a
  code (research doc §4.1). Keyed by ``(year, token)`` because the same letter means
  different parties in different years: ``P`` is the 1912 Progressive party, while in
  1896 and 1900 the Populists print inside ``D-P``.
- :data:`TABLE1_PARTY_CORRECTIONS` — Table 1 rows whose printed token is incomplete, by
  the house correction pattern (a constant, a test and a ``docs/corrections.md`` row).
- :data:`TABLE1_ROW_RULES` / :data:`TABLE1_ROW_NOTES` — the D077 rules each Table 1
  row's value rests on (build metadata, not stored) and the row's note (stored and,
  from #386, served).
- The ``CHECK`` builders :mod:`usvote.load` uses, so the vocabulary and the two source
  values have one definition each.

**Why a module of its own, stdlib-only.** The same shape as :mod:`usvote.count_status`:
:mod:`usvote.transform` *assigns* the values and :mod:`usvote.load` builds the DDL
``CHECK`` from them, and neither may depend on the other. Nothing here imports pandas,
psycopg2 or the network stack, and nothing here imports another ``usvote`` module —
year ranges are written out with :func:`range` rather than read from
:mod:`usvote.years`. ``tests/unit/test_layering.py`` enforces both
(``test_the_party_module_is_dependency_free``,
``test_the_party_module_imports_with_the_heavy_stack_blocked``).

**What is not here.** The curated catalog for candidates outside Table 1 is #387/#388's
authority; :func:`usvote.transform.build_candidate_party` takes it as a parameter, and
:class:`CuratedPartyRow` is the shape it takes. The MIT agreement check (D077 amends
D018: MIT's party is a check, not a source) lives in :mod:`usvote.party_check`.

**A code never changes meaning** (research doc §2.2). Adding a component, merging codes
or adding a value makes a new code, which needs a superseding D-entry and an API
changelog note. ``tests/unit/test_party.py`` pins every code with its component tuple as
a hand-written literal, so a component appended under an old name fails it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# --- the closed vocabulary (research doc §2.1, §2.2) -------------------------

#: The value a candidate-year takes when no qualifying national body nominated them for
#: President, or the nomination did not stand when the electors voted (D077 rule 5). A
#: served value, never a null. Never a component of a joint code.
NO_NOMINATION = "no_nomination"

#: Every vocabulary code, mapped to its component parties in order of nomination. A
#: single code maps to ``()``; a joint nomination maps to the single codes it joins
#: (research doc §2.2: joint codes are enumerated, never split at a separator, because
#: era tokens such as ``D-R`` already contain hyphens).
PARTY_COMPONENTS: Mapping[str, tuple[str, ...]] = {
    "democratic_republican": (),
    "national_republican": (),
    "democratic": (),
    "anti_masonic": (),
    "whig": (),
    "american": (),
    "republican": (),
    "southern_democratic": (),
    "constitutional_union": (),
    "liberal_republican": (),
    "populist": (),
    "progressive_1912": (),
    "progressive_1924": (),
    "states_rights_democratic": (),
    "american_independent": (),
    "libertarian": (),
    "liberal_republican_democratic": ("liberal_republican", "democratic"),
    "democratic_populist": ("democratic", "populist"),
    "american_whig": ("american", "whig"),
    NO_NOMINATION: (),
}

#: The vocabulary as a set: the values ``dwh.candidate_party.nominating_party`` may
#: hold.
NOMINATING_PARTIES: frozenset[str] = frozenset(PARTY_COMPONENTS)


class PartyContractError(ValueError):
    """Raised when this module's own constants break the contract they define."""


def check_party_components(components: Mapping[str, tuple[str, ...]]) -> None:
    """Raise unless every joint code's components are single codes of the vocabulary.

    A component must itself be a code, must be a *single* code (its own tuple is
    ``()``, so joint codes never nest), and must never be :data:`NO_NOMINATION`, which
    says no body nominated and cannot be one of two nominating bodies. A joint code has
    at least two components. Run at import over :data:`PARTY_COMPONENTS`; the parameter
    lets a test hand it a broken mapping.
    """
    problems: list[str] = []
    for code, parts in components.items():
        if not parts:
            continue
        if len(parts) < 2:
            problems.append(f"{code!r} has a single component {parts!r}")
        for part in parts:
            if part not in components:
                problems.append(f"{code!r} names {part!r}, which is not a code")
            elif components[part]:
                problems.append(f"{code!r} names the joint code {part!r}")
            elif part == NO_NOMINATION:
                problems.append(f"{code!r} names {NO_NOMINATION!r}")
    if problems:
        raise PartyContractError(
            "the nominating-party vocabulary is malformed: " + "; ".join(problems)
        )


check_party_components(PARTY_COMPONENTS)


# --- the year-scoped Table 1 token map (research doc §4.1) -------------------

#: The map from a **printed** Table 1 ``(year, token)`` to a code. Keyed on the raw
#: parse, before :data:`usvote.transform.PARTY_CODE_FIXES` (which folds
#: ``Democratic-Republican`` into ``D-R`` for ``dwh.candidate.party``), because
#: ``dwh.candidate_party.archives_party_code`` stores the token as printed.
#:
#: **Total and exact.** The ranges leave out the years a token does not print, and
#: :func:`usvote.transform.build_candidate_party` fails the build on a printed pair
#: missing here *and* on a pair here that never prints. A new election needs its two
#: pairs added before it builds.
#:
#: **A map entry translates; it never renames** (research doc §4.1). Each entry gives
#: the code for the party the Archives name. A party the token does not name (1872
#: Greeley's Liberal Republican nomination) is a correction, in
#: :data:`TABLE1_PARTY_CORRECTIONS`.
#:
#: Open questions, no change without a source (research doc §4.2; filed as #394): did a
#: further national body endorse 1896 and 1900 Bryan (``D-P``; BDUSC says "endorsed by
#: the Populist and Silver Republican Parties"), 1916 Hughes (``R``), or 1840 Harrison,
#: 1848 Taylor and 1856 Frémont (``Whig``, ``Whig``, ``R``)? Their entries below stand
#: until a source says otherwise.
TABLE1_TOKEN_MAP: Mapping[tuple[int, str], str] = {
    # 1824 Jackson and 1828 Jackson: the Archives token stands (research doc §6.1).
    (1824, "Democratic-Republican"): "democratic_republican",
    (1828, "Democratic-Republican"): "democratic_republican",
    # 1824 Adams.
    (1824, "D-R"): "democratic_republican",
    # 1828 Adams and 1832 Clay.
    **{(year, "National Republican"): "national_republican" for year in (1828, 1832)},
    # No D prints in 1896 or 1900, where Bryan's token is D-P.
    **{(year, "D"): "democratic" for year in range(1832, 1893, 4)},
    **{(year, "D"): "democratic" for year in range(1904, 2025, 4)},
    # Open (#394): 1840 Harrison, 1848 Taylor.
    **{(year, "Whig"): "whig" for year in range(1836, 1853, 4)},
    # No R prints in 1912, when Table 1's two rows are Wilson (D) and Roosevelt (P).
    # 1864 is the Republicans' "National Union" name (NPS-1864). Open (#394): 1856
    # Frémont, 1916 Hughes.
    **{(year, "R"): "republican" for year in range(1856, 1909, 4)},
    **{(year, "R"): "republican" for year in range(1916, 2025, 4)},
    # P = Populist here (LOC-1896; VPB, Stevenson chapter). Open (#394): a third
    # component for Bryan.
    **{(year, "D-P"): "democratic_populist" for year in (1896, 1900)},
    # P = Progressive here (VPB, Roosevelt chapter).
    (1912, "P"): "progressive_1912",
}


# --- corrections, rule sets and notes for Table 1 rows -----------------------

#: Table 1 rows whose printed token is incomplete, keyed by ``(year, name)`` with the
#: name as the candidate dimension spells it (``candidate_id`` is a row-order
#: surrogate, so it cannot key a constant). Each entry replaces the mapped value and
#: carries a ``docs/corrections.md`` row.
#:
#: - **1872 Horace Greeley**, printed ``D``: he was nominated by two national
#:   conventions. BDUSC (*Biographical Directory of the United States Congress
#:   1774–2005*, H. Doc. 108-222, p. 1150): "nominated by the Liberal Republicans in
#:   Cincinnati in 1872 and by the Democrats in Baltimore for the Presidency".
#:   https://www.govinfo.gov/content/pkg/GPO-CDOC-108hdoc222/pdf/GPO-CDOC-108hdoc222.pdf
#:   Research doc §4.2; D077.
TABLE1_PARTY_CORRECTIONS: Mapping[tuple[int, str], str] = {
    (1872, "Horace Greeley"): "liberal_republican_democratic",
}

#: The D077 rules a value may rest on, recorded per row (research doc §2.4).
RULE_SET_DOMAIN: frozenset[int] = frozenset({2, 3, 5, 6, 8})

#: The rules the owner accepted as a call, so a row resting on one must carry a note
#: (rule 3, an endorsement as a component; rule 5, a withdrawn or dead nominee; rule 8,
#: a party named but not its nominating body).
NOTE_REQUIRED_RULES: frozenset[int] = frozenset({3, 5, 8})

#: The rule set of every Table 1 row that rests on more than a plain nomination. Build
#: metadata: it decides which rows need a note, and is not stored.
#:
#: - Rule 2, no national nomination (D077 rule 2's closed list: 1824 candidates outside
#:   the caucus, 1828, and the 1836 Whigs): 1824 Jackson and Adams, 1828 Jackson and
#:   Adams, 1836 Harrison. 1828 Adams is here on rule 2's "1828", though the research
#:   doc's §2.4 list names only Jackson for that year (owner, #385 plan gate).
#: - Rule 5, a nominee who died before the electors voted: 1872 Greeley.
#: - Rule 6, the two 1860 Democratic nominations: 1860 Douglas.
TABLE1_ROW_RULES: Mapping[tuple[int, str], frozenset[int]] = {
    (1824, "Andrew Jackson"): frozenset({2}),
    (1824, "John Quincy Adams"): frozenset({2}),
    (1828, "Andrew Jackson"): frozenset({2}),
    (1828, "John Quincy Adams"): frozenset({2}),
    (1836, "William H. Harrison"): frozenset({2}),
    (1860, "Stephen A. Douglas"): frozenset({6}),
    (1872, "Horace Greeley"): frozenset({5}),
}

#: Each Table 1 row's note: a short statement of fact about how its value arose, stated
#: only from the row's own citations (research doc §2.4). Wording by ``ba`` (#385 plan,
#: owner-approved 2026-10-18). Greeley's facts: the joint nomination and the date of
#: death are BDUSC's ("nominated by the Liberal Republicans … and by the Democrats …";
#: "died near New York City November 29, 1872"); the vote split is ARCH-1872's
#: ("Following Greeley's death, electors in several states cast their votes
#: variously"). Notes on rows resting only on rules 2 or 6 are allowed and not yet
#: written.
TABLE1_ROW_NOTES: Mapping[tuple[int, str], str] = {
    (1872, "Horace Greeley"): (
        "Greeley was nominated for President by both the Liberal Republicans and the "
        "Democrats. He died on November 29, 1872, before the electors met. After his "
        "death, electors in several states split their votes."
    ),
}

#: The keys whose rule sets must cover the given rules: a hand-written floor, so a row
#: cannot drop its rule set (and with it its note) silently (research doc §2.4). #387
#: and #388 add their curated keys (1856 Fillmore, the twelve rule-8 rows, 1872 Davis
#: once confirmed).
NOTE_REQUIRED_FLOOR: Mapping[tuple[int, str], frozenset[int]] = {
    (1872, "Horace Greeley"): frozenset({5}),
}


# --- curated rows: the input contract only ----------------------------------


@dataclass(frozen=True)
class CuratedPartyRow:
    """One curated (non-Table-1) candidate-year's value — #387/#388's catalog shape.

    Keyed like the Table 1 constants, by ``(year, name)`` with the candidate
    dimension's spelling. ``rules`` and ``note`` obey the same rules as a Table 1 row's.
    Citations are #387's to shape and are not modeled here.
    """

    year: int
    name: str
    party: str
    rules: frozenset[int] = field(default_factory=frozenset)
    note: str | None = None


# --- the table's columns, source values and CHECKs ---------------------------

#: The publisher codes of the two places a value comes from: the National Archives'
#: Table 1, and the curated catalog of US-government works (D077, Provenance).
#: ``SOURCE_ARCHIVES`` is the same code the API already serves as ``ec_source``.
SOURCE_ARCHIVES = "NARA"
SOURCE_CURATED = "USGOV"
PARTY_SOURCES: tuple[str, ...] = (SOURCE_ARCHIVES, SOURCE_CURATED)

PARTY_COLUMN = "nominating_party"
SOURCE_COLUMN = "nominating_party_source"
ARCHIVES_CODE_COLUMN = "archives_party_code"
NOTE_COLUMN = "nominating_party_note"

#: ``dwh.candidate_party``'s columns in load order.
CANDIDATE_PARTY_COLUMNS: tuple[str, ...] = (
    "year",
    "candidate_id",
    PARTY_COLUMN,
    SOURCE_COLUMN,
    ARCHIVES_CODE_COLUMN,
    NOTE_COLUMN,
)


def _in_check(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"CHECK ({column} IN ({quoted}))"


def build_party_value_check(column: str = PARTY_COLUMN) -> str:
    """Return the ``CHECK`` restricting ``column`` to :data:`NOMINATING_PARTIES`."""
    return _in_check(column, tuple(PARTY_COMPONENTS))


def build_party_source_check(column: str = SOURCE_COLUMN) -> str:
    """Return the ``CHECK`` restricting ``column`` to :data:`PARTY_SOURCES`."""
    return _in_check(column, PARTY_SOURCES)


def build_party_source_code_check(
    source: str = SOURCE_COLUMN, code: str = ARCHIVES_CODE_COLUMN
) -> str:
    """Return the ``CHECK`` that an Archives code appears exactly on Archives rows.

    A Table 1 row always carries the token it was printed with, and a curated row has
    none to carry, so a code on a curated row or a missing code on an Archives row is
    unrepresentable.
    """
    return f"CHECK (({source} = '{SOURCE_ARCHIVES}') = ({code} IS NOT NULL))"
