"""Unit tests for :mod:`usvote.census.parse` (#181).

Offline throughout: the parsers take bytes, and the fixtures are real published Census
workbooks committed to the repo (public domain, S1 §3 — see ``tests/_helpers``).

The tests are written against the **hazards S1 measured**, not against a happy path.
Each of the four layout features below silently corrupts the result rather than raising
if it is mishandled, so each gets a test that would fail on the corrupted reading:
the ``PERCENT`` block that repeats every year label, the ``.  Sample`` sub-rows that
repeat a year inside the ``NUMBER`` block, the ``1940/2`` footnote markers, and the
footer rows that sit inside the data columns of the population-change table.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from tests._helpers import CENSUS_POPCHANGE_XLSX, CENSUS_TABS_TRIMMED_XLSX
from usvote.census.parse import (
    CensusParseError,
    parse_population_change,
    parse_resident_1790_1990,
)


def _tabs() -> list:
    return parse_resident_1790_1990(
        CENSUS_TABS_TRIMMED_XLSX.read_bytes(), source_id="resident_1790_1990"
    )


def _popchange() -> list:
    return parse_population_change(
        CENSUS_POPCHANGE_XLSX.read_bytes(), source_id="resident_1910_2020"
    )


def _lookup(rows: list) -> dict[tuple[str, int], int | None]:
    return {(row.area, row.census_year): row.population for row in rows}


class TestResident1790To1990:
    def test_the_sheet_name_is_the_state_and_every_sheet_is_read(self) -> None:
        assert {row.area for row in _tabs()} == {
            "Virginia",
            "West Virginia",
            "Connecticut",
            "Alaska",
        }

    def test_it_reads_the_published_totals_verified_by_the_research_pass(self) -> None:
        # The exact figures S1 read out of this file when it verified the source
        # (research-census-source.md §4). If the column offset or the block detection
        # moves, these are what catch it.
        values = _lookup(_tabs())
        assert values[("Virginia", 1790)] == 691_737
        assert values[("West Virginia", 1790)] == 55_873
        assert values[("Connecticut", 1790)] == 237_946
        assert values[("Virginia", 1850)] == 1_119_348
        assert values[("West Virginia", 1850)] == 302_313

    def test_the_percent_block_is_not_read_as_population(self) -> None:
        """The sharpest silent-corruption case in this file.

        The ``PERCENT`` block repeats **every** year label the ``NUMBER`` block uses, in
        the same column. A parser keying on the year alone reads each year twice and the
        second — a percentage — wins. The check that catches it is not "no duplicates":
        it is that every value is a population-sized count, since a percentage is a
        small number that looks perfectly plausible on its own.
        """
        rows = _tabs()
        keys = [(row.area, row.census_year) for row in rows]
        assert len(keys) == len(set(keys)), "a year was read from both blocks"
        virginia = [
            r for r in rows if r.area == "Virginia" and r.population is not None
        ]
        assert all(r.population > 1_000 for r in virginia), (
            "a percentage was read as a population"
        )

    def test_sample_sub_rows_do_not_displace_the_published_count(self) -> None:
        # ".   Sample" / ".   15% sample" repeat a year *inside* the NUMBER block with
        # an alternative tabulation. 1970 Virginia is 4,648,494 published against
        # 4,648,479 in the 15% sample — close enough that reading the wrong one looks
        # entirely reasonable, which is exactly why it needs pinning.
        assert _lookup(_tabs())[("Virginia", 1970)] == 4_648_494

    def test_a_year_label_carrying_a_footnote_marker_is_read(self) -> None:
        # "1940/2 ....." — a naive int() on the label raises on precisely the rows that
        # carry footnotes, so the absence of 1940 would be the symptom.
        assert _lookup(_tabs())[("Virginia", 1940)] == 2_677_773

    def test_a_state_that_is_not_backfilled_simply_starts_later(self) -> None:
        # Alaska is not backfilled to 1790 the way West Virginia is; it starts at 1960.
        # The rows are absent, NOT present-with-null — #182 conforms what exists.
        alaska = sorted(r.census_year for r in _tabs() if r.area == "Alaska")
        assert min(alaska) == 1960

    def test_a_workbook_with_no_sheets_raises_rather_than_returning_nothing(
        self,
    ) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main"><sheets/></workbook>',
            )
            z.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/'
                'package/2006/relationships"/>',
            )
        with pytest.raises(CensusParseError):
            parse_resident_1790_1990(buf.getvalue(), source_id="x")


class TestPopulationChange:
    def test_it_reads_every_census_column_across_the_side_by_side_blocks(self) -> None:
        # The three page-blocks are laid out horizontally; reading only the first would
        # silently yield 1990-2020 and drop everything older.
        assert sorted({row.census_year for row in _popchange()}) == [
            1910,
            1920,
            1930,
            1940,
            1950,
            1960,
            1970,
            1980,
            1990,
            2000,
            2010,
            2020,
        ]

    def test_a_column_takes_the_area_from_its_own_block(self) -> None:
        # Each block repeats the Area column. If a later block's values were paired with
        # the *first* block's labels the rows would still look well-formed — same
        # states, plausible numbers — so this pins a value from the second block.
        values = _lookup(_popchange())
        assert values[("Alabama", 2020)] == 5_024_279
        assert values[("California", 2020)] == 39_538_223
        assert values[("Alabama", 1910)] == 2_138_093

    def test_the_footer_rows_are_not_read_as_areas(self) -> None:
        """The footer sits inside the data columns, so position alone does not exclude it.

        A "Note: ..." paragraph occupies the Area column and a "Page N of 3" marker sits
        in each block, so a purely positional read yields three or four areas named
        after their own text. They are dropped structurally — an area row carries at
        least one published population and a footer never does — rather than by matching
        their wording, which would break the first time the Bureau rewords one.
        """
        areas = {row.area for row in _popchange()}
        assert not [area for area in areas if area.startswith(("Note:", "Page "))]

    def test_both_spellings_of_the_national_row_survive_the_parse(self) -> None:
        # The parser is faithful: it does not drop the aggregates (scope is the
        # transform's job). What matters here is that BOTH spellings appear, because
        # the first block glues the footnote marker onto the label and an exclusion
        # written as == "United States" would miss it downstream.
        areas = {row.area for row in _popchange()}
        assert "United States1" in areas
        assert "United States" in areas

    def test_puerto_rico_and_the_regions_are_returned_not_silently_dropped(
        self,
    ) -> None:
        areas = {row.area for row in _popchange()}
        assert "Puerto Rico" in areas
        assert {
            "Northeast Region",
            "Midwest Region",
            "South Region",
            "West Region",
        } <= (areas)
