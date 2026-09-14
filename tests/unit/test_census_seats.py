"""Unit tests for :mod:`usvote.census.seats` — the curated seat authority (#183).

The module is *data*, so most of these check shape and the handful of values that carry
an argument: the cells where the published source is surprising, and the cells a
careless regeneration would quietly change.

``TestRealCorpus`` is the one that establishes the data is **right** rather than merely
well-formed: it re-extracts the published PDF and compares cell by cell. It **skips when
``USVOTE_CENSUS_CORPUS_DIR`` is unset**, so CI never needs ``pdftotext`` — which is the
whole point of curating the seats instead of parsing them at runtime. Running it is a
merge precondition, exactly as the UCSB cross-source control test is (#234 precedent).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from usvote.apportionment import GOVERNING_CENSUS_BY_ELECTION
from usvote.census.scrape import SEATS_1789_2010, SEATS_2020, SEATS_SOURCE_IDS
from usvote.census.seats import (
    CURATED_CENSUS_YEARS,
    CURATED_JURISDICTIONS,
    SEATS_BY_CENSUS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACTOR = REPO_ROOT / "scripts" / "extract_census_seats.py"


def _load_extractor() -> Any:
    spec = importlib.util.spec_from_file_location("extract_census_seats", EXTRACTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestShape:
    def test_it_covers_exactly_the_governing_censuses(self) -> None:
        """Twenty, not twenty-one.

        Elections 1824-2024 resolve to 1820-1910 and 1930-2020. The off-by-one is easy
        to make because there are 21 decades in that span and 1920 is one of them.
        """
        governing = tuple(sorted(set(GOVERNING_CENSUS_BY_ELECTION.values())))
        assert governing == CURATED_CENSUS_YEARS
        assert len(CURATED_CENSUS_YEARS) == 20

    def test_1920_is_absent_because_it_governs_nothing(self) -> None:
        """Congress passed no apportionment act after it, so it governs no election.

        The published table's 1920 column is **fully populated** — it repeats 1910
        verbatim — so a guard written for a *missing* 1920 row would never fire. It is
        excluded by scope instead.
        """
        assert 1920 not in SEATS_BY_CENSUS

    def test_every_census_carries_every_jurisdiction(self) -> None:
        """Completeness is the property the reconciliation's absent-key rule rests on.

        A state present in one census and missing from another would make an absent key
        ambiguous again, which is exactly what that rule exists to prevent.
        """
        assert len(CURATED_JURISDICTIONS) == 51
        for census_year, by_state in SEATS_BY_CENSUS.items():
            assert set(by_state) == CURATED_JURISDICTIONS, census_year

    def test_puerto_rico_is_excluded(self) -> None:
        """It appears in the 2020 source and appoints no electors."""
        assert "Puerto Rico" not in CURATED_JURISDICTIONS

    def test_seats_are_positive_integers_or_none(self) -> None:
        for census_year, by_state in SEATS_BY_CENSUS.items():
            for state, seats in by_state.items():
                assert seats is None or (isinstance(seats, int) and seats >= 1), (
                    census_year,
                    state,
                )


class TestTheCellsThatCarryAnArgument:
    """Values a regeneration could change without anything else noticing."""

    def test_the_1950_column_totals_437_not_435(self) -> None:
        """The source's own basis, and it is load-bearing rather than a defect.

        Alaska and Hawaii are included retroactively at one seat each. The 1950 census
        governs the **1960** election, in which both cast electoral votes, so this is
        what makes that year's 537 electors reconcile. A different published Bureau file
        reports the same year as 435 with both blank — also correct, of the
        apportionment as enacted — and only this basis reconciles against the
        electoral record.
        """
        assert sum(v for v in SEATS_BY_CENSUS[1950].values() if v) == 437
        assert SEATS_BY_CENSUS[1950]["Alaska"] == 1
        assert SEATS_BY_CENSUS[1950]["Hawaii"] == 1

    def test_michigan_1980_is_18_not_8(self) -> None:
        """The published PDF renders this cell as ``l8`` — lowercase L, then 8.

        The hazard runs opposite to the obvious one: a strict ``int()`` raises, which is
        safe, while a permissive digit scavenge silently yields **8** — an 11-seat error
        wearing a plausible number. The extractor rejects the malformed cell and
        resolves it only through a declared defect entry, whose value is confirmed from
        a different published Bureau file.
        """
        assert SEATS_BY_CENSUS[1980]["Michigan"] == 18

    def test_west_virginia_has_no_seats_under_the_1860_census(self) -> None:
        """``(X)``, and the state still cast electoral votes in 1864 and 1868.

        Distinct from zero: reading it as 0 would expect 2 electoral votes and turn a
        catalogued discrepancy into an off-by-three that looks like arithmetic.
        """
        assert SEATS_BY_CENSUS[1860]["West Virginia"] is None

    def test_nevada_and_nebraska_are_filled_in_for_1860_but_west_virginia_is_not(
        self,
    ) -> None:
        """The source is inconsistent about mid-decade admissions, and this pins it.

        All three were admitted in the 1860s. Two are retroactively given a seat in the
        1860 column and one is not, so the table cannot be read as a uniform statement
        of "seats as of that census".
        """
        assert SEATS_BY_CENSUS[1860]["Nevada"] == 1
        assert SEATS_BY_CENSUS[1860]["Nebraska"] == 1
        assert SEATS_BY_CENSUS[1860]["West Virginia"] is None

    def test_dc_has_no_apportioned_seats_in_any_census(self) -> None:
        """``(X)`` in every apportionment table; its three votes are the 23rd Am."""
        for census_year, by_state in SEATS_BY_CENSUS.items():
            assert by_state["District of Columbia"] is None, census_year

    def test_the_modern_house_is_435(self) -> None:
        for census_year in (1910, 1930, 1960, 1990, 2010, 2020):
            assert sum(v for v in SEATS_BY_CENSUS[census_year].values() if v) == 435


class TestTheSourceCatalog:
    def test_both_seats_sources_are_registered_and_kept_off_the_resident_path(
        self,
    ) -> None:
        """A warehouse build must never *require* the seats corpus.

        The seats are curated, so the runtime path reads no seats file at all; these
        entries exist for the cross-check below.
        """
        assert (SEATS_1789_2010.source_id, SEATS_2020.source_id) == SEATS_SOURCE_IDS

    def test_the_pdf_source_is_not_in_the_runtime_parser_map(self) -> None:
        """The structural form of "no PDF reader ships"."""
        from usvote.census.pipeline import _PARSERS

        for source_id in SEATS_SOURCE_IDS:
            assert source_id not in _PARSERS


class TestTheExtractorGuards:
    """The hazards live in the local tool; these are their unit tests."""

    def test_a_malformed_cell_is_rejected_rather_than_scavenged(self) -> None:
        extractor = _load_extractor()
        with pytest.raises(extractor.SeatsExtractionError, match="Refusing to guess"):
            extractor._read_cell("l8", year=1970, state="Michigan")

    def test_the_one_declared_defect_resolves_to_its_confirmed_value(self) -> None:
        extractor = _load_extractor()
        assert extractor._read_cell("l8", year=1980, state="Michigan") == 18

    def test_the_defect_declaration_is_pinned_to_its_own_cell(self) -> None:
        """A blanket ``l8 -> 18`` rule would silently repair a *new* corruption."""
        extractor = _load_extractor()
        with pytest.raises(extractor.SeatsExtractionError):
            extractor._read_cell("l8", year=1980, state="Ohio")

    def test_not_applicable_is_none_and_zero_is_not(self) -> None:
        extractor = _load_extractor()
        assert extractor._read_cell("(X)", year=1860, state="West Virginia") is None
        assert extractor._read_cell("0", year=1860, state="West Virginia") == 0

    def test_an_unreadable_header_refuses_to_assume_an_orientation(self) -> None:
        """Mirrored pages: a guessed orientation reads the wrong column."""
        extractor = _load_extractor()
        text = (
            "  1890 1880 1870 1860 1850 1840 1830 1820 Nonsense\n"
            "  1 2 3 4 5 6 7 8 Maine\n"
        )
        with pytest.raises(extractor.SeatsExtractionError, match="orientation"):
            extractor.parse_seats_text(text)


def _corpus_pdf() -> Path | None:
    corpus_dir = os.environ.get("USVOTE_CENSUS_CORPUS_DIR")
    if not corpus_dir:
        return None
    path = Path(corpus_dir) / SEATS_1789_2010.filename
    return path if path.is_file() else None


class TestRealCorpus:
    """The published PDF; skips when the corpus is absent.

    This is the only check that can establish the curated constant actually matches what
    the Census Bureau published. It skips in CI by design, so running it locally is a
    merge precondition rather than something the pipeline proves.
    """

    @pytest.fixture(autouse=True)
    def _requires_corpus(self) -> None:
        if shutil.which("pdftotext") is None:
            pytest.skip("pdftotext is not installed (needed only by this cross-check)")
        if _corpus_pdf() is None:
            pytest.skip(
                f"set USVOTE_CENSUS_CORPUS_DIR and snapshot "
                f"{SEATS_1789_2010.filename} to run the seats cross-check"
            )

    def test_every_curated_pdf_cell_matches_a_fresh_extraction(self) -> None:
        """Cell by cell, for the 19 censuses Table 3 covers.

        2020 is excluded because it comes from the other published file; the extraction
        cannot speak to it.
        """
        extractor = _load_extractor()
        pdf = _corpus_pdf()
        assert pdf is not None
        extracted = extractor.parse_seats_text(extractor.extract_seats_text(pdf))
        checked = 0
        for census_year, by_state in SEATS_BY_CENSUS.items():
            if census_year == 2020:
                continue
            assert census_year in extracted, census_year
            for state, seats in by_state.items():
                assert extracted[census_year][state] == seats, (census_year, state)
                checked += 1
        assert checked == 19 * 51

    def test_the_extraction_covers_both_mirrored_pages(self) -> None:
        """Page 2 puts the label on the right; a one-page read loses 1789-1890."""
        extractor = _load_extractor()
        pdf = _corpus_pdf()
        assert pdf is not None
        extracted = extractor.parse_seats_text(extractor.extract_seats_text(pdf))
        assert 1820 in extracted and 2010 in extracted
        assert extracted[1820]["Virginia"] is not None
        assert extracted[2010]["Virginia"] is not None

    def test_the_l8_defect_is_still_present_in_the_published_file(self) -> None:
        """If the Bureau ever reissues the file, the declaration becomes stale.

        A defect declaration that no longer describes the source is the same class of
        false claim as a stale exception in the corrections catalog.
        """
        extractor = _load_extractor()
        pdf = _corpus_pdf()
        assert pdf is not None
        text = extractor.extract_seats_text(pdf)
        assert "l8" in text, (
            "the published PDF no longer renders Michigan 1980 as 'l8' — remove the "
            "PUBLISHED_CELL_DEFECTS entry rather than leaving a declaration that "
            "describes nothing"
        )
