"""Unit tests for ``usvote.party``, the nominating-party contract (#385, D077).

The vocabulary is pinned as a hand-written literal, each code with its component
tuple in order: a code never changes meaning (research doc §2.2), so a component
appended under an old name must fail here. Changing this literal needs a superseding
D-entry (D077) and an API changelog note. The dependency-free property is enforced in
``test_layering.py``; the builder's guards in ``test_candidate_party.py``.
"""

from __future__ import annotations

import pytest

from usvote import party, snapshot_schema
from usvote.party import (
    NO_NOMINATION,
    NOMINATING_PARTIES,
    NOTE_REQUIRED_FLOOR,
    NOTE_REQUIRED_RULES,
    PARTY_COMPONENTS,
    RULE_SET_DOMAIN,
    SOURCE_ARCHIVES,
    SOURCE_CURATED,
    TABLE1_PARTY_CORRECTIONS,
    TABLE1_ROW_NOTES,
    TABLE1_ROW_RULES,
    TABLE1_TOKEN_MAP,
    PartyContractError,
    check_party_components,
)
from usvote.years import ec_ingest_years

# --- the vocabulary ---------------------------------------------------------


def test_the_vocabulary_is_pinned_with_its_component_tuples() -> None:
    """A change here needs a superseding D-entry and an API changelog note (D077)."""
    assert dict(PARTY_COMPONENTS) == {
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
        "no_nomination": (),
    }
    assert frozenset(PARTY_COMPONENTS) == NOMINATING_PARTIES
    assert NO_NOMINATION == "no_nomination"


def test_the_shipped_vocabulary_passes_the_component_check() -> None:
    check_party_components(PARTY_COMPONENTS)  # also runs at import


@pytest.mark.parametrize(
    ("components", "message"),
    [
        ({"a": (), "ab": ("a", "b")}, "'b', which is not a code"),
        ({"a": (), "b": (), "ab": ("a", "b"), "abc": ("ab", "a")}, "joint code 'ab'"),
        ({"a": (), NO_NOMINATION: (), "an": ("a", NO_NOMINATION)}, "no_nomination"),
        ({"a": (), "aa": ("a",)}, "single component"),
    ],
)
def test_a_malformed_joint_code_fails_the_component_check(
    components: dict[str, tuple[str, ...]], message: str
) -> None:
    with pytest.raises(PartyContractError, match=message):
        check_party_components(components)


# --- the token map ----------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "code"),
    [
        ((1824, "Democratic-Republican"), "democratic_republican"),
        ((1824, "D-R"), "democratic_republican"),
        ((1828, "Democratic-Republican"), "democratic_republican"),
        ((1828, "National Republican"), "national_republican"),
        ((1832, "National Republican"), "national_republican"),
        ((1836, "Whig"), "whig"),
        ((1852, "Whig"), "whig"),
        ((1856, "R"), "republican"),
        ((1872, "D"), "democratic"),
        ((1896, "D-P"), "democratic_populist"),
        ((1900, "D-P"), "democratic_populist"),
        ((1912, "P"), "progressive_1912"),
        ((1912, "D"), "democratic"),
        ((2024, "R"), "republican"),
        ((2024, "D"), "democratic"),
    ],
)
def test_token_map_spot_pins(key: tuple[int, str], code: str) -> None:
    assert TABLE1_TOKEN_MAP[key] == code


@pytest.mark.parametrize(
    "key",
    [
        (1896, "D"),  # Bryan prints D-P in 1896 and 1900
        (1900, "D"),
        (1912, "R"),  # Table 1's 1912 rows are Wilson and Roosevelt
        (1896, "P"),  # P is Progressive in 1912 only
        (1856, "Whig"),
        (1828, "D-R"),
    ],
)
def test_token_map_leaves_out_pairs_that_never_print(key: tuple[int, str]) -> None:
    assert key not in TABLE1_TOKEN_MAP


def test_the_same_letter_maps_only_in_its_year() -> None:
    """The year key is load-bearing on the real map: ``P`` maps in 1912 alone."""
    assert {year for year, token in TABLE1_TOKEN_MAP if token == "P"} == {1912}


def test_token_map_has_two_tokens_for_every_ingest_year() -> None:
    """Every built year prints two Table 1 rows; each year's tokens are mapped.

    1824 prints two distinct tokens for the one party, and every other year prints two
    different parties, so each year has exactly two map entries.
    """
    per_year: dict[int, int] = {}
    for year, _token in TABLE1_TOKEN_MAP:
        per_year[year] = per_year.get(year, 0) + 1
    assert per_year == dict.fromkeys(ec_ingest_years(), 2)


def test_every_mapped_and_corrected_value_is_in_the_vocabulary() -> None:
    assert set(TABLE1_TOKEN_MAP.values()) <= NOMINATING_PARTIES
    assert set(TABLE1_PARTY_CORRECTIONS.values()) <= NOMINATING_PARTIES


def test_every_constant_key_is_an_ingest_year() -> None:
    """The builder scopes its stale-key guards to built years, so a key in a year no
    build ever has (a typo such as 1827) would otherwise never be checked."""
    years = ec_ingest_years()
    for name, keys in {
        "token map": TABLE1_TOKEN_MAP,
        "corrections": TABLE1_PARTY_CORRECTIONS,
        "rules": TABLE1_ROW_RULES,
        "notes": TABLE1_ROW_NOTES,
        "floor": NOTE_REQUIRED_FLOOR,
    }.items():
        outside = sorted(key for key in keys if key[0] not in years)
        assert not outside, f"{name} keys outside the ingest years: {outside}"


# --- corrections, rules, notes and the floor --------------------------------


def test_the_greeley_correction_is_the_joint_nomination() -> None:
    assert dict(TABLE1_PARTY_CORRECTIONS) == {
        (1872, "Horace Greeley"): "liberal_republican_democratic"
    }


def test_rule_sets_are_drawn_from_the_domain() -> None:
    assert frozenset({2, 3, 5, 6, 8}) == RULE_SET_DOMAIN
    assert frozenset({3, 5, 8}) == NOTE_REQUIRED_RULES
    for key, rules in TABLE1_ROW_RULES.items():
        assert rules <= RULE_SET_DOMAIN, key


def test_every_note_required_table1_row_has_a_note() -> None:
    for key, rules in TABLE1_ROW_RULES.items():
        if rules & NOTE_REQUIRED_RULES:
            assert TABLE1_ROW_NOTES.get(key, "").strip(), key


def test_the_floor_is_pinned_and_covered_by_the_rule_sets() -> None:
    assert dict(NOTE_REQUIRED_FLOOR) == {(1872, "Horace Greeley"): frozenset({5})}
    for key, required in NOTE_REQUIRED_FLOOR.items():
        assert required <= TABLE1_ROW_RULES[key], key


def test_the_greeley_note_states_the_death_and_its_date() -> None:
    """D077 rule 5: the note carries the death and its date (BDUSC, p. 1150)."""
    note = TABLE1_ROW_NOTES[(1872, "Horace Greeley")]
    assert "died on November 29, 1872" in note
    assert "Liberal Republicans" in note and "Democrats" in note


# --- sources ----------------------------------------------------------------


def test_the_archives_source_code_is_the_one_the_api_serves() -> None:
    assert SOURCE_ARCHIVES == snapshot_schema.EC_SOURCE
    assert (SOURCE_ARCHIVES, SOURCE_CURATED) == ("NARA", "USGOV")
    assert party.PARTY_SOURCES == (SOURCE_ARCHIVES, SOURCE_CURATED)


def test_no_table1_note_carries_a_control_character() -> None:
    # #386: the snapshot serves these notes verbatim and pins every served note to this
    # catalog, so a control character here would reach the content hash (whose field
    # and row separators are control characters) and every CSV. #387/#388 extend this
    # to the curated catalog's notes.
    for key, note in TABLE1_ROW_NOTES.items():
        assert not any(ord(c) < 32 or ord(c) == 127 for c in note), key


def test_the_curated_source_code_is_the_one_the_api_serves() -> None:
    # #386: snapshot_schema holds the code as a literal (the serving side may not
    # import this module), so this pin is what keeps the two from drifting apart.
    assert SOURCE_CURATED == snapshot_schema.CURATED_SOURCE
