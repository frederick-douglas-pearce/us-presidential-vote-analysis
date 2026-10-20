"""The curated nominating-party catalog's contract (#387, D077, D078).

``check_curated_catalog`` runs at import over the real catalog. These tests hand it a
broken copy, one defect at a time, and pin the real catalog's content with a hand-written
literal: a curated value changes only by review, never as a side effect.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from tests.unit.test_candidate_party import _build, _inputs
from usvote.party import (
    NOTE_REQUIRED_RULES,
    PARTY_COMPONENTS,
    CuratedPartyRow,
    PartyContractError,
)
from usvote.party_catalog import (
    CATALOG,
    CURATED_BY_KEY,
    CURATED_PARTY_ROWS,
    FILLMORE_1856_NOTE,
    LA_FOLLETTE_1924_NOTE,
    MAX_PASSAGE_WORDS,
    RULE_8_NOTE,
    SOURCES,
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


def test_a_table1_key_fails() -> None:
    """A curated row may only fill a candidate-year Table 1 does not cover."""
    row = CuratedPartyRow(1872, "Horace Greeley", "liberal_republican_democratic")
    citation = _citation(supports=frozenset({"liberal_republican", "democratic"}))
    with pytest.raises(PartyContractError, match="is a Table 1 row"):
        check_curated_catalog([_entry(row, citation)])


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
    """Every key, value, rule set and note, hand-written (#387's C1 rows, D078). A
    change needs review. Notes are named by constant; their wording is the owner's."""
    s8, w36 = RULE_8_NOTE, WHIG_1836_NOTE
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
    for entry in CATALOG:
        needed = set(PARTY_COMPONENTS[entry.row.party]) or {entry.row.party}
        assert needed <= set().union(*(c.supports for c in entry.citations))


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
