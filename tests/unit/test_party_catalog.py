"""The curated nominating-party catalog's contract (#387, #388, D077, D078, D079).

``check_curated_catalog`` runs at import over the real catalog. These tests hand it a
broken copy, one defect at a time, and pin the real catalog's content with a hand-written
literal: a curated value changes only by review, never as a side effect.
"""

from __future__ import annotations

import dataclasses
import json
import re
from datetime import date
from pathlib import Path

import pytest

from tests.unit.test_candidate_party import _build, _inputs
from usvote.party import (
    NO_NOMINATION,
    NOTE_REQUIRED_RULES,
    PARTY_COMPONENTS,
    TABLE1_PARTY_CORRECTIONS,
    TABLE1_ROW_NOTES,
    TABLE1_ROW_RULES,
    CuratedPartyRow,
    PartyContractError,
)
from usvote.party_catalog import (
    BENTSEN_1988_NOTE,
    BROWN_1872_NOTE,
    BYRD_1960_NOTE,
    CATALOG,
    CURATED_BY_KEY,
    CURATED_PARTY_ROWS,
    EDWARDS_2004_NOTE,
    FILLMORE_1856_NOTE,
    FLOYD_1832_NOTE,
    HAWAII_2016_NOTE,
    HENDRICKS_1872_NOTE,
    JENKINS_1872_NOTE,
    JONES_1956_NOTE,
    LA_FOLLETTE_1924_NOTE,
    MAX_PASSAGE_WORDS,
    REAGAN_1976_NOTE,
    RULE_8_NOTE,
    SOURCES,
    TEXAS_2016_NOTE,
    WASHINGTON_2016_NOTE,
    WHIG_1836_NOTE,
    CatalogEntry,
    Citation,
    Source,
    check_curated_catalog,
)
from usvote.transform import TransformError


def _entry(
    row: CuratedPartyRow | None = None, *citations: Citation
) -> CatalogEntry:
    row = row or CuratedPartyRow(1860, "John Bell", "constitutional_union")
    return CatalogEntry(row, citations or (_citation(),))


def _citation(
    passage: str = "nominated for president by the Constitutional Union Party",
    source_key: str = "ST-TN",
    supports: frozenset[str] = frozenset({"constitutional_union"}),
) -> Citation:
    return Citation(source_key, "1860", passage, date(2026, 10, 20), supports)


# --- AC2: each defect fails the catalog check ---------------------------------


def test_a_well_formed_catalog_passes() -> None:
    check_curated_catalog([_entry()])


def test_the_real_catalog_passes() -> None:
    check_curated_catalog(CATALOG)


def test_a_row_with_no_citation_fails() -> None:
    entry = CatalogEntry(_entry().row, ())
    with pytest.raises(PartyContractError, match=r"\(1860, 'John Bell'\) has no citation"):
        check_curated_catalog([entry])


def test_an_out_of_vocabulary_value_fails() -> None:
    row = CuratedPartyRow(1860, "John Bell", "constitutional_unionist")
    with pytest.raises(PartyContractError, match="which is not a code"):
        check_curated_catalog([_entry(row)])


@pytest.mark.parametrize(
    ("year", "name", "party"),
    [
        # A key of TABLE1_PARTY_CORRECTIONS (and of the other two constants).
        (1872, "Horace Greeley", "liberal_republican_democratic"),
        # A key of TABLE1_ROW_RULES alone, so a check narrowed to the corrections
        # misses it.
        (1824, "Andrew Jackson", "democratic_republican"),
    ],
)
def test_a_table1_key_fails(year: int, name: str, party: str) -> None:
    """A curated row may only fill a candidate-year Table 1 does not cover."""
    supports = frozenset(PARTY_COMPONENTS[party]) or frozenset({party})
    entry = _entry(CuratedPartyRow(year, name, party), _citation(supports=supports))
    with pytest.raises(PartyContractError, match="is a Table 1 row"):
        check_curated_catalog([entry])


def test_the_table1_key_cases_cover_each_constant() -> None:
    """Keeps the cases above honest: one key is the corrections' and one is only a
    rule set's. TABLE1_ROW_NOTES has no key the other two lack today."""
    assert (1872, "Horace Greeley") in TABLE1_PARTY_CORRECTIONS
    jackson = (1824, "Andrew Jackson")
    assert jackson in TABLE1_ROW_RULES
    assert jackson not in TABLE1_PARTY_CORRECTIONS
    assert jackson not in TABLE1_ROW_NOTES
    assert set(TABLE1_ROW_NOTES) <= set(TABLE1_PARTY_CORRECTIONS) | set(TABLE1_ROW_RULES)


def test_a_catalog_row_on_a_table1_candidate_year_fails_the_build() -> None:
    """The build's own guard, reached by a row from the catalog's shape: Cal Cole is a
    Table 1 row in the synthetic 1904 (``test_candidate_party``)."""
    row = CuratedPartyRow(1904, "Cal Cole", "democratic")
    entry = _entry(row, _citation(supports=frozenset({"democratic"})))
    check_curated_catalog([entry])  # the static check cannot see a synthetic Table 1
    with pytest.raises(TransformError, match="both a NARA and a USGOV row"):
        _build(inputs=_inputs(), curated=[entry.row])


def test_a_duplicate_key_fails() -> None:
    with pytest.raises(PartyContractError, match="appears twice"):
        check_curated_catalog([_entry(), _entry()])


def test_an_unregistered_source_fails() -> None:
    with pytest.raises(PartyContractError, match="'WIKI', which is not registered"):
        check_curated_catalog([_entry(None, _citation(source_key="WIKI"))])


@pytest.mark.parametrize(
    "passage", ["", "   ", " ".join(["word"] * (MAX_PASSAGE_WORDS + 1))]
)
def test_a_blank_or_long_passage_fails(passage: str) -> None:
    with pytest.raises(PartyContractError, match="has a passage of"):
        check_curated_catalog([_entry(None, _citation(passage))])


def test_a_passage_of_the_maximum_length_passes() -> None:
    passage = " ".join(["word"] * MAX_PASSAGE_WORDS)
    check_curated_catalog([_entry(None, _citation(passage))])


def test_a_citation_that_supports_another_party_fails() -> None:
    citation = _citation(supports=frozenset({"whig"}))
    with pytest.raises(PartyContractError, match=r"supports \['constitutional_union'\]"):
        check_curated_catalog([_entry(None, citation)])


def test_a_joint_code_needs_every_component_supported() -> None:
    """Two citations backing the same component do not cover a joint code."""
    row = CuratedPartyRow(1856, "Millard Fillmore", "american_whig")
    american = _citation(supports=frozenset({"american"}))
    with pytest.raises(PartyContractError, match=r"supports \['whig'\]"):
        check_curated_catalog([_entry(row, american, american)])
    whig = _citation(supports=frozenset({"whig"}))
    check_curated_catalog([_entry(row, american, whig)])


# --- C2: no_nomination rows (#388, D079) ---------------------------------------


def _c2_entry(
    note: str | None = "One Washington elector voted for him for President.",
    searched: str | None = "ARCH-1976, for a presidential nomination: none found.",
    supports: frozenset[str] = frozenset(),
) -> CatalogEntry:
    row = CuratedPartyRow(1976, "Ronald Reagan", NO_NOMINATION, note=note)
    origin = _citation("A Washington (State) elector voted for Ronald Reagan.",
                       "ARCH-1976", supports)
    return CatalogEntry(row, (origin,), searched)


def test_a_well_formed_no_nomination_row_passes() -> None:
    """Its citation gives the votes' origin and backs no code (D079)."""
    check_curated_catalog([_c2_entry()])


def test_a_no_nomination_row_may_cite_a_passage_stating_the_absence() -> None:
    """Reserved for a passage that states the absence or a withdrawal (D079)."""
    check_curated_catalog([_c2_entry(supports=frozenset({NO_NOMINATION}))])


@pytest.mark.parametrize("note", [None, "", "  "])
def test_a_no_nomination_row_with_no_note_fails(note: str | None) -> None:
    with pytest.raises(PartyContractError, match="is no_nomination with no note"):
        check_curated_catalog([_c2_entry(note=note)])


@pytest.mark.parametrize("searched", [None, "", "  "])
def test_a_no_nomination_row_with_no_searched_record_fails(
    searched: str | None,
) -> None:
    with pytest.raises(
        PartyContractError, match="is no_nomination with no searched record"
    ):
        check_curated_catalog([_c2_entry(searched=searched)])


def test_a_no_nomination_row_with_no_citation_fails() -> None:
    entry = dataclasses.replace(_c2_entry(), citations=())
    with pytest.raises(PartyContractError, match="has no citation"):
        check_curated_catalog([entry])


def test_a_citation_backing_no_code_fails_on_a_nominated_row() -> None:
    """A ``_cite`` that forgot its codes: empty ``supports`` is the C2 shape only. The
    second citation covers the value, so only this rule can fail it."""
    entry = _entry(None, _citation(), _citation(supports=frozenset()))
    with pytest.raises(PartyContractError, match="has a citation backing no code"):
        check_curated_catalog([entry])


@pytest.mark.parametrize(
    ("entry", "stray"),
    [
        # A nominated row's citation backing a code besides its own value.
        (
            _entry(None, _citation(supports=frozenset({"constitutional_union", "whig"}))),
            "['whig']",
        ),
        # A C2 citation backing a party: it would claim the origin passage names one.
        (_c2_entry(supports=frozenset({"republican"})), "['republican']"),
    ],
)
def test_a_citation_backing_a_code_outside_the_value_fails(
    entry: CatalogEntry, stray: str
) -> None:
    with pytest.raises(PartyContractError, match=re.escape(f"citation backing {stray}")):
        check_curated_catalog([entry])


def test_a_source_with_no_basis_or_a_plain_http_url_fails() -> None:
    bad = {
        "ST-TN": dataclasses.replace(SOURCES["ST-TN"], basis=" "),
        "DOJ": dataclasses.replace(SOURCES["DOJ"], url="http://www.justice.gov/"),
    }
    with pytest.raises(PartyContractError) as excinfo:
        check_curated_catalog([_entry()], sources=bad)
    assert "'ST-TN' states no public-domain basis" in str(excinfo.value)
    assert "'DOJ' has a non-https URL" in str(excinfo.value)


# --- the real catalog's content ----------------------------------------------


def test_the_catalog_rows_are_pinned() -> None:
    """Every key, value, rule set and note, hand-written (#387's C1 rows, D078; #388's
    C2 rows, D079). A change needs review. Notes are named by constant; their wording is
    the owner's. 1836 Mangum and 1872 Davis are absent on purpose (research doc §16)."""
    s8, w36, nn = RULE_8_NOTE, WHIG_1836_NOTE, NO_NOMINATION
    assert {
        key: (row.party, set(row.rules), row.note)
        for key, row in CURATED_BY_KEY.items()
    } == {
        (1824, "William H. Crawford"): ("democratic_republican", set(), None),
        (1824, "Henry Clay"): ("democratic_republican", {2, 8}, s8),
        (1832, "William Wirt"): ("anti_masonic", {8}, s8),
        (1836, "Hugh L. White"): ("whig", {2, 8}, w36),
        (1836, "Daniel Webster"): ("whig", {2, 8}, w36),
        (1856, "Millard Fillmore"): ("american_whig", {3, 8}, FILLMORE_1856_NOTE),
        (1860, "John C. Breckinridge"): ("southern_democratic", {6}, None),
        (1860, "John Bell"): ("constitutional_union", {8}, s8),
        (1892, "James B. Weaver"): ("populist", {8}, s8),
        (1912, "William H. Taft"): ("republican", {8}, s8),
        (1924, "Robert M. La Follette"): (
            "progressive_1924",
            set(),
            LA_FOLLETTE_1924_NOTE,
        ),
        (1948, "J. Strom Thurmond"): ("states_rights_democratic", {8}, s8),
        (1968, "George C. Wallace"): ("american_independent", {8}, s8),
        (1972, "John Hospers"): ("libertarian", {8}, s8),
        (1832, "John Floyd"): (nn, set(), FLOYD_1832_NOTE),
        (1872, "Thomas A. Hendricks"): (nn, set(), HENDRICKS_1872_NOTE),
        (1872, "Benjamin Gratz Brown"): (nn, set(), BROWN_1872_NOTE),
        (1872, "Charles J. Jenkins"): (nn, set(), JENKINS_1872_NOTE),
        (1956, "Walter B. Jones"): (nn, set(), JONES_1956_NOTE),
        (1960, "Harry F. Byrd"): (nn, set(), BYRD_1960_NOTE),
        (1976, "Ronald Reagan"): (nn, set(), REAGAN_1976_NOTE),
        (1988, "Lloyd Bentsen"): (nn, set(), BENTSEN_1988_NOTE),
        (2004, "John Edwards"): (nn, set(), EDWARDS_2004_NOTE),
        (2016, "Bernie Sanders"): (nn, set(), HAWAII_2016_NOTE),
        (2016, "Ron Paul"): (nn, set(), TEXAS_2016_NOTE),
        (2016, "John Kasich"): (nn, set(), TEXAS_2016_NOTE),
        (2016, "Colin Powell"): (nn, set(), WASHINGTON_2016_NOTE),
        (2016, "Faith Spotted Eagle"): (nn, set(), WASHINGTON_2016_NOTE),
    }
    assert len(CURATED_BY_KEY) == len(CATALOG) == len(CURATED_PARTY_ROWS)


def test_la_follette_s_note_names_the_body_that_nominated_him() -> None:
    """D078(b): the body's name differs from the party the value names."""
    assert "Conference for Progressive Political Action" in LA_FOLLETTE_1924_NOTE


def test_every_note_required_row_has_a_note() -> None:
    for (year, name), row in CURATED_BY_KEY.items():
        if row.rules & NOTE_REQUIRED_RULES:
            assert (row.note or "").strip(), (year, name)


def test_every_value_is_a_single_code_or_its_components_are_cited() -> None:
    """A nominated row's citations cover its value. A ``no_nomination`` row's give the
    votes' origin and back no code, and its absence rests on a note and a search record
    (D079)."""
    for entry in CATALOG:
        key = (entry.row.year, entry.row.name)
        supported = set().union(*(c.supports for c in entry.citations))
        if entry.row.party == NO_NOMINATION:
            assert supported == set(), key
            assert (entry.row.note or "").strip(), key
            assert (entry.searched or "").strip(), key
            continue
        needed = set(PARTY_COMPONENTS[entry.row.party]) or {entry.row.party}
        assert needed <= supported, key
        assert all(c.supports for c in entry.citations), key
        assert entry.searched is None, key


def test_each_citation_carries_the_date_its_passage_was_matched() -> None:
    """#387's passages were matched on 2026-10-20 and #388's on 2026-10-21 (research doc
    §15, §16): a C2 citation never inherits the C1 date."""
    for entry in CATALOG:
        expected = (
            date(2026, 10, 21) if entry.row.party == NO_NOMINATION else date(2026, 10, 20)
        )
        for citation in entry.citations:
            assert citation.verified == expected, (entry.row.year, entry.row.name)


def test_every_catalog_key_is_spelled_as_the_archives_spell_it() -> None:
    """Offline: each key names an electoral-vote recipient in that year, spelled as the
    committed Archives witness spells it, so a misspelled key fails here rather than only
    in the gated corpus test or a full build."""
    witness = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "ec_getters_by_year.json").read_text()
    )["years"]
    for year, name in CURATED_BY_KEY:
        assert name in witness[str(year)], (year, name)


def test_no_note_or_passage_carries_a_control_character() -> None:
    """The snapshot serves the notes verbatim, and a control character would reach the
    content hash and every CSV. Passages are held to the same rule."""
    texts = [
        (entry.row.year, entry.row.name, text)
        for entry in CATALOG
        for text in (entry.row.note or "", *(c.passage for c in entry.citations))
    ]
    for year, name, text in texts:
        assert not any(ord(c) < 32 or ord(c) == 127 for c in text), (year, name)


def test_every_citation_names_a_registered_source_with_a_basis() -> None:
    for entry in CATALOG:
        for citation in entry.citations:
            source: Source = SOURCES[citation.source_key]
            assert source.url.startswith("https://")
            assert "17 U.S.C. §105" in source.basis
