"""Unit tests for ``transform.build_candidate_party`` (#385, D077).

Each guard has a test that makes it fire and a twin that passes. The synthetic cases
build the three inputs by hand (a parse, a candidate dimension, a votes fact) and pass
every constant explicitly, so each test exercises one guard. The real-data cases replay
every committed Archives fixture year, and the whole local corpus when
``USVOTE_EC_HTML_DIR`` is set.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import pytest

from tests._helpers import FIXTURES_DIR, fake_state_geo
from usvote import parse, scrape, transform
from usvote.party import (
    CANDIDATE_PARTY_COLUMNS,
    TABLE1_TOKEN_MAP,
    CuratedPartyRow,
)
from usvote.party_catalog import CURATED_BY_KEY, CURATED_PARTY_ROWS
from usvote.transform import TransformError, build_candidate_party
from usvote.years import ec_ingest_years

# --- synthetic inputs -------------------------------------------------------

#: A small map for the synthetic cases: two years, two tokens each.
MAP: dict[tuple[int, str], str] = {
    (1900, "D"): "democratic",
    (1900, "R"): "republican",
    (1904, "D"): "democratic",
    (1904, "R"): "republican",
}

#: (year, name, printed token, votes cast) per Table 1 row.
ROWS: tuple[tuple[int, str, str, int], ...] = (
    (1900, "Ann Able", "R", 292),
    (1900, "Ben Baker", "D", 155),
    (1904, "Ann Able", "R", 336),
    (1904, "Cal Cole", "D", 140),
)


def _inputs(
    rows: Sequence[tuple[int, str, str, int]] = ROWS,
    *,
    extra_candidates: Mapping[str, int] | None = None,
    extra_totals: Sequence[tuple[int, str, int]] = (),
) -> tuple[list[dict[str, Any]], pd.DataFrame, pd.DataFrame]:
    """Build a parse, a candidate dimension and a votes fact from Table 1 rows.

    ``extra_candidates`` adds candidate-dimension names (with their votes added by
    ``extra_totals`` as ``(year, name, cast)``), for candidates outside Table 1.
    """
    years = sorted({year for year, *_ in rows} | {y for y, _n, _c in extra_totals})
    parsed = [
        {
            "year": year,
            "t1": [
                {"president_candidate_name": n, "president_candidate_party": t}
                for y, n, t, _c in rows
                if y == year
            ],
            "t2": [],
        }
        for year in years
    ]
    names = list(dict.fromkeys([n for _y, n, _t, _c in rows]))
    ids = {name: i for i, name in enumerate(names, start=1)}
    for name, candidate_id in (extra_candidates or {}).items():
        ids[name] = candidate_id
    candidates = pd.DataFrame({"candidate_id": list(ids.values()), "name": list(ids)})
    totals = [(y, n, c) for y, n, _t, c in rows] + list(extra_totals)
    votes = pd.DataFrame({
        "year": [y for y, _n, _c in totals],
        "candidate_id": [ids[n] for _y, n, _c in totals],
        "is_total": True,
        "president_electoral_votes": [c for _y, _n, c in totals],
        "president_electoral_votes_counted": [c for _y, _n, c in totals],
    })
    return parsed, candidates, votes


def _build(
    rows: Sequence[tuple[int, str, str, int]] = ROWS,
    *,
    inputs: tuple[list[dict[str, Any]], pd.DataFrame, pd.DataFrame] | None = None,
    **constants: Any,
) -> pd.DataFrame:
    parsed, candidates, votes = inputs or _inputs(rows)
    kwargs: dict[str, Any] = {
        "token_map": MAP,
        "corrections": {},
        "rules": {},
        "notes": {},
        "floor": {},
        "curated": (),
    }
    kwargs.update(constants)
    return build_candidate_party(parsed, candidates, votes, **kwargs)


def test_a_clean_build_has_one_archives_row_per_table1_row() -> None:
    party = _build()
    assert tuple(party.columns) == CANDIDATE_PARTY_COLUMNS
    assert party.to_dict("records") == [
        {"year": 1900, "candidate_id": 1, "nominating_party": "republican",
         "nominating_party_source": "NARA", "archives_party_code": "R",
         "nominating_party_note": None},
        {"year": 1900, "candidate_id": 2, "nominating_party": "democratic",
         "nominating_party_source": "NARA", "archives_party_code": "D",
         "nominating_party_note": None},
        {"year": 1904, "candidate_id": 1, "nominating_party": "republican",
         "nominating_party_source": "NARA", "archives_party_code": "R",
         "nominating_party_note": None},
        {"year": 1904, "candidate_id": 3, "nominating_party": "democratic",
         "nominating_party_source": "NARA", "archives_party_code": "D",
         "nominating_party_note": None},
    ]


def test_table1_names_are_reconciled_like_the_candidate_dimension() -> None:
    """``Bob Dole`` (Table 1) resolves to ``Robert Dole`` (Table 2), as it does for
    ``dwh.candidate`` — one shared helper, so the two cannot drift apart."""
    parsed, candidates, votes = _inputs(
        [(1996, "Bill Clinton", "D", 379), (1996, "Robert Dole", "R", 159)]
    )
    parsed[0]["t1"][1]["president_candidate_name"] = "Bob Dole"
    party = _build(
        inputs=(parsed, candidates, votes),
        token_map={(1996, "D"): "democratic", (1996, "R"): "republican"},
    )
    assert list(party["candidate_id"]) == [1, 2]


def test_both_table1_readers_reconcile_names_through_the_one_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mechanism behind the test above: ``dwh.candidate``'s party columns and
    ``dwh.candidate_party`` both call ``reconcile_table1_names``.

    A sentinel replaces it, mapping a name no fix list holds. If either reader applied
    :data:`~usvote.transform.PARTY_NAME_FIXES` itself instead, it would not see the
    sentinel, and that reader's result below would differ.
    """
    calls: list[str] = []

    def sentinel(names: pd.Series) -> pd.Series:
        calls.append("called")
        return names.replace({"Zed": "Robert Dole"})

    monkeypatch.setattr(transform, "reconcile_table1_names", sentinel)
    parsed, candidates, votes = _inputs(
        [(1996, "Bill Clinton", "D", 379), (1996, "Robert Dole", "R", 159)]
    )
    parsed[0]["t1"][1]["president_candidate_name"] = "Zed"

    party = _build(
        inputs=(parsed, candidates, votes),
        token_map={(1996, "D"): "democratic", (1996, "R"): "republican"},
    )
    assert list(party["candidate_id"]) == [1, 2]
    assert len(calls) == 1

    parties = transform._candidate_parties(transform.normalize_candidate_parties(parsed))
    assert set(parties["name"]) == {"Bill Clinton", "Robert Dole"}
    assert len(calls) == 2


# --- AC3: the map is keyed by (year, token) ---------------------------------


def test_the_same_token_maps_to_different_values_in_different_years() -> None:
    """AC3 (a): over an injected map, one token gives two codes in two years."""
    rows = [
        (1900, "Ann Able", "R", 292), (1900, "Ben Baker", "X", 155),
        (1904, "Ann Able", "R", 336), (1904, "Cal Cole", "X", 140),
    ]
    token_map = {
        (1900, "R"): "republican", (1900, "X"): "populist",
        (1904, "R"): "republican", (1904, "X"): "progressive_1912",
    }
    party = _build(rows, token_map=token_map)
    by_year = dict(zip(
        party.loc[party["archives_party_code"] == "X", "year"],
        party.loc[party["archives_party_code"] == "X", "nominating_party"],
        strict=True,
    ))
    assert by_year == {1900: "populist", 1904: "progressive_1912"}


def test_the_real_map_maps_p_in_1912() -> None:
    """AC3 (b), first half: on the real map, (1912, "P") is the 1912 Progressives."""
    rows = [(1912, "Woodrow Wilson", "D", 435), (1912, "Theodore Roosevelt", "P", 88)]
    party = _build(rows, token_map=TABLE1_TOKEN_MAP)
    assert list(party["nominating_party"]) == ["democratic", "progressive_1912"]


def test_the_real_map_fails_the_build_on_p_in_1896() -> None:
    """AC3 (b), second half: the same token in 1896 is unmapped, so the build fails."""
    rows = [(1896, "William McKinley", "R", 271), (1896, "William J. Bryan", "P", 176)]
    with pytest.raises(TransformError, match=r"printed but unmapped \[\(1896, 'P'\)\]"):
        _build(rows, token_map=TABLE1_TOKEN_MAP)


# --- G1: (year, candidate_id) unique ----------------------------------------


def test_two_rows_resolving_to_one_candidate_year_fail() -> None:
    rows = [(1900, "Ann Able", "R", 292), (1900, "Ben Baker", "D", 155)]
    parsed, _candidates, _votes = _inputs(rows)
    # Two names for one candidate_id: each name resolves, and the key collides.
    candidates = pd.DataFrame({"candidate_id": [1, 1], "name": ["Ann Able", "Ben Baker"]})
    votes = pd.DataFrame({
        "year": [1900], "candidate_id": [1], "is_total": [True],
        "president_electoral_votes": [447],
    })
    with pytest.raises(TransformError, match=r"not one row per \(year, candidate_id\)"):
        _build(inputs=(parsed, candidates, votes))


def test_one_row_per_candidate_year_passes() -> None:
    party = _build()
    assert not party.duplicated(["year", "candidate_id"]).any()


# --- G2: the vocabulary -----------------------------------------------------


def test_a_mapped_value_outside_the_vocabulary_fails() -> None:
    with pytest.raises(TransformError, match="outside the vocabulary"):
        _build(token_map={**MAP, (1904, "D"): "invented"})


def test_a_corrected_value_outside_the_vocabulary_fails() -> None:
    with pytest.raises(TransformError, match="outside the vocabulary"):
        _build(corrections={(1900, "Ben Baker"): "invented"})


def test_a_curated_value_outside_the_vocabulary_fails() -> None:
    inputs = _inputs(extra_candidates={"Dee Dunn": 9}, extra_totals=[(1904, "Dee Dunn", 1)])
    with pytest.raises(TransformError, match="outside the vocabulary"):
        _build(inputs=inputs, curated=[CuratedPartyRow(1904, "Dee Dunn", "invented")])


def test_vocabulary_values_from_every_source_pass() -> None:
    inputs = _inputs(extra_candidates={"Dee Dunn": 9}, extra_totals=[(1904, "Dee Dunn", 1)])
    party = _build(
        inputs=inputs,
        corrections={(1900, "Ben Baker"): "democratic_populist"},
        curated=[CuratedPartyRow(1904, "Dee Dunn", "no_nomination")],
    )
    assert set(party["nominating_party"]) == {
        "republican", "democratic", "democratic_populist", "no_nomination"
    }


# --- G3: the token map is total, both ways ----------------------------------


def test_a_printed_pair_missing_from_the_map_fails() -> None:
    token_map = {k: v for k, v in MAP.items() if k != (1904, "D")}
    with pytest.raises(TransformError, match=r"printed but unmapped \[\(1904, 'D'\)\]"):
        _build(token_map=token_map)


def test_a_mapped_pair_that_never_prints_fails() -> None:
    with pytest.raises(TransformError, match=r"never printed \[\(1904, 'W'\)\]"):
        _build(token_map={**MAP, (1904, "W"): "whig"})


def test_map_entries_for_unbuilt_years_are_not_checked() -> None:
    """Scoped to the build: a two-year slice does not fail on the other years."""
    party = _build(token_map={**MAP, (1908, "W"): "whig"})
    assert len(party) == 4


# --- G4: Archives and curated never overlap ---------------------------------


def test_a_curated_row_for_a_table1_candidate_year_fails() -> None:
    with pytest.raises(TransformError, match="both a NARA and a USGOV row"):
        _build(curated=[CuratedPartyRow(1904, "Cal Cole", "democratic")])


def test_a_curated_row_for_another_candidate_year_passes() -> None:
    inputs = _inputs(extra_candidates={"Dee Dunn": 9}, extra_totals=[(1904, "Dee Dunn", 1)])
    party = _build(inputs=inputs, curated=[CuratedPartyRow(1904, "Dee Dunn", "populist")])
    (row,) = party[party["nominating_party_source"] == "USGOV"].to_dict("records")
    # A curated row carries no Archives code: missing, which the write boundary turns
    # into SQL NULL (usvote.db.insert_df_into_table), as the DDL's source/code CHECK
    # requires.
    assert pd.isna(row.pop("archives_party_code"))
    assert pd.isna(row.pop("nominating_party_note"))
    assert row == {
        "year": 1904, "candidate_id": 9, "nominating_party": "populist",
        "nominating_party_source": "USGOV",
    }


# --- G5: no stale constant ---------------------------------------------------


@pytest.mark.parametrize(
    ("constant", "value"),
    [
        ("corrections", "democratic"),
        ("rules", frozenset({2})),
        ("notes", "A note."),
    ],
)
def test_a_constant_key_matching_no_table1_row_fails(constant: str, value: Any) -> None:
    stale: dict[str, Any] = {constant: {(1904, "Ben Baker"): value}}
    with pytest.raises(TransformError, match=r"\(1904, 'Ben Baker'\)"):
        _build(**stale)


def test_constant_keys_in_unbuilt_years_and_on_real_rows_pass() -> None:
    party = _build(
        corrections={(1904, "Cal Cole"): "democratic_populist", (1908, "X"): "whig"},
        rules={(1900, "Ben Baker"): frozenset({2})},
        notes={(1900, "Ben Baker"): "A note.", (1872, "Horace Greeley"): "Elsewhere."},
    )
    assert party.loc[3, "nominating_party"] == "democratic_populist"
    assert party.loc[1, "nominating_party_note"] == "A note."


def test_the_correction_replaces_the_mapped_value_and_keeps_the_token() -> None:
    party = _build(corrections={(1900, "Ben Baker"): "liberal_republican_democratic"})
    row = party.loc[1]
    assert (row["nominating_party"], row["archives_party_code"]) == (
        "liberal_republican_democratic", "D"
    )


# --- G6: null guard part 1 (each Table 1 row resolves) ----------------------


def test_a_table1_name_missing_from_the_candidate_dimension_fails() -> None:
    parsed, candidates, votes = _inputs()
    parsed[1]["t1"][1]["president_candidate_name"] = "Cal Colee"
    with pytest.raises(TransformError, match="no candidate named 'Cal Colee'"):
        _build(inputs=(parsed, candidates, votes))


def test_a_table1_row_with_no_totals_row_fails() -> None:
    parsed, candidates, votes = _inputs()
    votes = votes[~((votes["year"] == 1904) & (votes["candidate_id"] == 3))]
    with pytest.raises(TransformError, match="0 national totals rows"):
        _build(inputs=(parsed, candidates, votes))


def test_a_table1_row_with_two_totals_rows_fails() -> None:
    parsed, candidates, votes = _inputs()
    votes = pd.concat([votes, votes.iloc[[3]]], ignore_index=True)
    with pytest.raises(TransformError, match="2 national totals rows"):
        _build(inputs=(parsed, candidates, votes))


def test_a_table1_key_printed_twice_fails() -> None:
    rows = [*ROWS, (1904, "Cal Cole", "D", 140)]
    parsed, candidates, votes = _inputs(rows)
    votes = votes.drop_duplicates()
    with pytest.raises(TransformError, match="appears twice"):
        _build(inputs=(parsed, candidates, votes))


def test_a_table1_row_with_no_votes_cast_fails() -> None:
    parsed, candidates, votes = _inputs()
    votes.loc[3, "president_electoral_votes"] = 0
    with pytest.raises(
        TransformError,
        match=r"Table 1 rows that do not resolve.*\(1904, 'Cal Cole'\): no electoral",
    ):
        _build(inputs=(parsed, candidates, votes))


# --- G7: null guard part 2 (each curated row resolves) ----------------------


def test_a_curated_name_missing_from_the_candidate_dimension_fails() -> None:
    with pytest.raises(
        TransformError,
        match=r"curated rows that do not resolve.*no candidate named 'Nobody'",
    ):
        _build(curated=[CuratedPartyRow(1904, "Nobody", "populist")])


def test_a_curated_row_with_no_totals_row_fails() -> None:
    inputs = _inputs(extra_candidates={"Dee Dunn": 9})
    with pytest.raises(TransformError, match="0 national totals rows"):
        _build(inputs=inputs, curated=[CuratedPartyRow(1904, "Dee Dunn", "populist")])


def test_a_curated_row_outside_the_ingest_years_fails() -> None:
    with pytest.raises(TransformError, match="outside the EC ingest years"):
        _build(curated=[CuratedPartyRow(1827, "Ann Able", "whig")])


def test_a_curated_row_in_an_unbuilt_ingest_year_is_left_out() -> None:
    party = _build(curated=[CuratedPartyRow(1908, "Nobody", "populist")])
    assert set(party["nominating_party_source"]) == {"NARA"}


# --- G8: null guard part 3 (every candidate-year has votes cast) ------------


def test_a_candidate_year_with_no_votes_cast_fails() -> None:
    inputs = _inputs(extra_candidates={"Dee Dunn": 9}, extra_totals=[(1904, "Dee Dunn", 0)])
    with pytest.raises(TransformError, match=r"no electoral votes cast .*\(1904, 9\)"):
        _build(inputs=inputs)


def test_votes_cast_and_not_counted_pass() -> None:
    """1872 Greeley: 3 cast, 0 counted (D044). Part 3 reads the cast measure."""
    inputs = _inputs(extra_candidates={"Dee Dunn": 9}, extra_totals=[(1904, "Dee Dunn", 3)])
    votes = inputs[2]
    votes.loc[votes["candidate_id"] == 9, "president_electoral_votes_counted"] = 0
    assert len(_build(inputs=inputs)) == 4


# --- G9: rule sets and notes ------------------------------------------------


def test_a_rule_outside_the_domain_fails() -> None:
    with pytest.raises(TransformError, match=r"rule sets outside .*\[7\]"):
        _build(rules={(1900, "Ben Baker"): frozenset({7})})


@pytest.mark.parametrize("note", [None, "", "   \n"])
def test_a_note_required_rule_without_a_real_note_fails(note: str | None) -> None:
    notes = {} if note is None else {(1900, "Ben Baker"): note}
    with pytest.raises(TransformError, match=r"blank note: \[\(1900, 'Ben Baker'\)\]"):
        _build(rules={(1900, "Ben Baker"): frozenset({5})}, notes=notes)


def test_a_curated_note_required_rule_without_a_note_fails() -> None:
    inputs = _inputs(extra_candidates={"Dee Dunn": 9}, extra_totals=[(1904, "Dee Dunn", 1)])
    row = CuratedPartyRow(1904, "Dee Dunn", "populist", rules=frozenset({8}))
    with pytest.raises(TransformError, match=r"blank note: \[\(1904, 'Dee Dunn'\)\]"):
        _build(inputs=inputs, curated=[row])


def test_note_required_rules_with_notes_and_optional_rules_without_pass() -> None:
    inputs = _inputs(extra_candidates={"Dee Dunn": 9}, extra_totals=[(1904, "Dee Dunn", 1)])
    party = _build(
        inputs=inputs,
        rules={(1900, "Ben Baker"): frozenset({5}), (1904, "Cal Cole"): frozenset({2, 6})},
        notes={(1900, "Ben Baker"): "He died before the electors met."},
        curated=[CuratedPartyRow(1904, "Dee Dunn", "populist", frozenset({3}), "Endorsed.")],
    )
    assert len(party) == 5


# --- G10: the note floor ----------------------------------------------------


def test_a_floor_key_whose_row_lost_its_rule_set_fails() -> None:
    with pytest.raises(TransformError, match=r"note-floor .*\(1900, 'Ben Baker'\)"):
        _build(floor={(1900, "Ben Baker"): frozenset({5})})


def test_a_floor_key_with_no_row_fails() -> None:
    with pytest.raises(TransformError, match=r"note-floor .*\(1904, 'Dee Dunn'\)"):
        _build(floor={(1904, "Dee Dunn"): frozenset({8})})


def test_floor_keys_covered_or_unbuilt_pass() -> None:
    party = _build(
        rules={(1900, "Ben Baker"): frozenset({2, 5})},
        notes={(1900, "Ben Baker"): "A note."},
        floor={(1900, "Ben Baker"): frozenset({5}), (1872, "X"): frozenset({5})},
    )
    assert len(party) == 4


# --- the real data ----------------------------------------------------------

#: Every committed Archives fixture year.
FIXTURE_YEARS = frozenset(
    {1824, 1832, 1836, 1856, 1860, 1864, 1868, 1872, 2016, 2020, 2024}
)


def _real_build(fetch: scrape.Fetch, years: frozenset[int] | set[int]) -> pd.DataFrame:
    state_geo = fake_state_geo()
    links = scrape.scrape_election_links(fetch=fetch)
    raw = scrape.scrape_raw_election_tables(links, years, fetch=fetch)
    parsed = parse.parse_election_years(raw, set(state_geo["NAME"]))
    candidates, _state, votes = transform.transform_parsed_years(parsed, state_geo)
    party = build_candidate_party(parsed, candidates, votes)
    return party.merge(candidates[["candidate_id", "name"]], on="candidate_id")


def test_every_committed_fixture_year_has_the_file_glob_years() -> None:
    """The fixture list above is every committed Archives year page, no fewer."""
    on_disk = {
        int(p.stem.rsplit("_", 1)[1])
        for p in FIXTURES_DIR.glob("www_archives_gov_electoral_college_[0-9]*.html")
    }
    assert on_disk == FIXTURE_YEARS


def test_the_real_fixtures_build_two_archives_rows_per_year() -> None:
    party = _real_build(scrape.fetch_from_dir(FIXTURES_DIR), FIXTURE_YEARS)

    archives = party[party["nominating_party_source"] == "NARA"]
    assert archives.groupby("year").size().to_dict() == dict.fromkeys(FIXTURE_YEARS, 2)
    assert set(party["nominating_party_source"]) == {"NARA", "USGOV"}
    value = {(int(r.year), r.name): r.nominating_party for r in party.itertuples()}
    code = {(int(r.year), r.name): r.archives_party_code for r in party.itertuples()}
    assert value[(1872, "Horace Greeley")] == "liberal_republican_democratic"
    assert code[(1872, "Horace Greeley")] == "D"
    assert value[(1824, "Andrew Jackson")] == "democratic_republican"
    assert code[(1824, "Andrew Jackson")] == "Democratic-Republican"
    assert value[(1824, "John Quincy Adams")] == "democratic_republican"
    assert code[(1824, "John Quincy Adams")] == "D-R"
    assert value[(1832, "Henry Clay")] == "national_republican"
    assert value[(1836, "William H. Harrison")] == "whig"
    assert value[(1860, "Stephen A. Douglas")] == "democratic"
    assert value[(1864, "Abraham Lincoln")] == "republican"
    assert value[(2024, "Kamala D. Harris")] == "democratic"

    notes = archives.dropna(subset=["nominating_party_note"])
    assert [(int(r.year), r.name) for r in notes.itertuples()] == [
        (1872, "Horace Greeley")
    ]


def test_the_real_fixtures_build_the_catalog_rows_in_their_years() -> None:
    """The default catalog (#387, #388) resolves against real Archives bytes in CI.

    Seventeen of its twenty-eight rows fall in a committed fixture year (eight C1 rows
    and nine ``no_nomination`` rows), so their names must match the candidate dimension
    the real parse builds, and each must arrive once with source ``USGOV``, its value
    and its note, and no Archives code.
    """
    party = _real_build(scrape.fetch_from_dir(FIXTURES_DIR), FIXTURE_YEARS)
    curated = party[party["nominating_party_source"] == "USGOV"]
    built = {
        (int(r.year), r.name): (
            r.nominating_party,
            None if pd.isna(r.nominating_party_note) else r.nominating_party_note,
        )
        for r in curated.itertuples()
    }
    assert sorted(built) == [
        (1824, "Henry Clay"),
        (1824, "William H. Crawford"),
        (1832, "John Floyd"),
        (1832, "William Wirt"),
        (1836, "Daniel Webster"),
        (1836, "Hugh L. White"),
        (1856, "Millard Fillmore"),
        (1860, "John Bell"),
        (1860, "John C. Breckinridge"),
        (1872, "Benjamin Gratz Brown"),
        (1872, "Charles J. Jenkins"),
        (1872, "Thomas A. Hendricks"),
        (2016, "Bernie Sanders"),
        (2016, "Colin Powell"),
        (2016, "Faith Spotted Eagle"),
        (2016, "John Kasich"),
        (2016, "Ron Paul"),
    ]
    assert len(curated) == len(built)
    for key, (value, note) in built.items():
        assert (value, note) == (CURATED_BY_KEY[key].party, CURATED_BY_KEY[key].note)
    assert curated["archives_party_code"].isna().all()


def test_the_build_merges_the_catalog_by_default() -> None:
    import inspect

    default = inspect.signature(build_candidate_party).parameters["curated"].default
    assert default is CURATED_PARTY_ROWS


@pytest.mark.skipif(
    not os.environ.get("USVOTE_EC_HTML_DIR"),
    reason="USVOTE_EC_HTML_DIR unset — the Archives corpus lives outside the repo",
)
def test_the_real_corpus_builds_every_year_with_the_full_map() -> None:
    """Full strength: every ingest year, so every guard's scope is the whole map."""
    years = ec_ingest_years()
    party = _real_build(scrape.fetch_from_corpus(os.environ["USVOTE_EC_HTML_DIR"]), years)

    archives = party[party["nominating_party_source"] == "NARA"]
    assert len(archives) == 2 * len(years)
    assert set(archives["year"]) == years
    assert set(party["nominating_party_source"]) == {"NARA", "USGOV"}
    value = {(int(r.year), r.name): r.nominating_party for r in party.itertuples()}
    assert value[(1828, "John Quincy Adams")] == "national_republican"
    assert value[(1896, "William J. Bryan")] == "democratic_populist"
    assert value[(1912, "Theodore Roosevelt")] == "progressive_1912"


#: The candidate-years with electoral votes cast that hold no party row after #388, each
#: for its own reason (research doc §16): 1836 Mangum, because a U.S. Government work
#: (VPB, Tyler chapter) places him among the Whigs' regional candidates "nominated at the
#: state and local level", which bars ``no_nomination`` and names no body (§6.1); 1872
#: Davis, because no U.S. Government work names his Labor Reform nomination or its
#: withdrawal (rule 5). Hand-written, not derived: deriving it as "cast minus Table 1
#: minus the catalog" would restate what the build does.
_NOT_YET_COLLECTED = frozenset({
    (1836, "Willie P. Mangum"),
    (1872, "David Davis"),
})


@pytest.mark.skipif(
    not os.environ.get("USVOTE_EC_HTML_DIR"),
    reason="USVOTE_EC_HTML_DIR unset — the Archives corpus lives outside the repo",
)
def test_the_real_corpus_builds_every_catalog_row_and_leaves_the_known_remainder() -> (
    None
):
    """Every catalog row arrives once as ``USGOV`` with its value and note, no other
    ``USGOV`` row exists, and what stays uncollected is exactly the hand-written list."""
    fetch = scrape.fetch_from_corpus(os.environ["USVOTE_EC_HTML_DIR"])
    state_geo = fake_state_geo()
    links = scrape.scrape_election_links(fetch=fetch)
    raw = scrape.scrape_raw_election_tables(links, ec_ingest_years(), fetch=fetch)
    parsed = parse.parse_election_years(raw, set(state_geo["NAME"]))
    candidates, _state, votes = transform.transform_parsed_years(parsed, state_geo)
    party = build_candidate_party(parsed, candidates, votes)
    names = dict(zip(candidates["candidate_id"], candidates["name"], strict=True))

    curated = party[party["nominating_party_source"] == "USGOV"]
    built = {
        (int(r.year), names[r.candidate_id]): (
            r.nominating_party,
            None if pd.isna(r.nominating_party_note) else r.nominating_party_note,
        )
        for r in curated.itertuples()
    }
    assert len(curated) == len(built)
    assert built == {
        key: (row.party, row.note) for key, row in CURATED_BY_KEY.items()
    }

    totals = votes[votes["is_total"] & (votes["president_electoral_votes"] > 0)]
    cast = {
        (int(y), names[c])
        for y, c in zip(totals["year"], totals["candidate_id"], strict=True)
    }
    keyed = {
        (int(y), names[c])
        for y, c in zip(party["year"], party["candidate_id"], strict=True)
    }
    assert cast - keyed == _NOT_YET_COLLECTED
