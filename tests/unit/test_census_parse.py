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


def _state_sheet_workbook(name: str, rows: list[list[str]]) -> bytes:
    """Return a minimal OOXML workbook holding one state sheet of ``rows``.

    Real published bytes are the right fixture for a *layout* (``CENSUS_TABS_TRIMMED_XLSX``
    is exactly that, and is what the rest of this class reads). This builder exists for the
    narrower job of pinning one **label form** whose sheet is not in that fixture, and the
    label strings the callers pass are copied verbatim from the published file — so what is
    synthetic here is the container, never the thing under test. Cells are written as
    ``inlineStr``/``n`` so no shared-string table is needed.
    """
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"

    def cell(ref: str, text: str) -> str:
        if text == "":
            return ""
        if text.lstrip("-").isdigit():
            return f'<c r="{ref}"><v>{text}</v></c>'
        escaped = text.replace("&", "&amp;").replace("<", "&lt;")
        return f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'

    body = "".join(
        f'<row r="{i}">'
        + "".join(cell(f"{chr(ord('A') + j)}{i}", value) for j, value in enumerate(row))
        + "</row>"
        for i, row in enumerate(rows, start=1)
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
            f'<sheet name="{name}" sheetId="1" r:id="rId1"/>'
            f"</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{pkg}"><Relationship Id="rId1" '
            f'Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{main}"><sheetData>{body}</sheetData></worksheet>',
        )
    return buf.getvalue()


class TestResident1790To1990:
    def test_the_sheet_name_is_the_state_and_every_sheet_is_read(self) -> None:
        assert {row.area for row in _tabs()} == {
            "Virginia",
            "West Virginia",
            "Connecticut",
            "Alaska",
            # Added in #234. Hawaii is the ONLY offline witness to the transposed
            # table's year header sitting somewhere other than column B (its is column
            # C, with B empty), so without this sheet a "hardcode column B" reading is
            # correct for Alaska, wrong for Hawaii, and green in CI.
            "Hawaii",
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
        second — a percentage — wins.

        **What this test does and does not establish.** It pins the *outcome* on the
        committed fixture: no year appears twice, and Virginia's values are all
        population-sized rather than percentages. It does **not** pin the
        ``NUMBER``/``PERCENT`` marker itself. On this fixture the marker is redundant —
        ``NUMBER`` always precedes ``PERCENT``, so the parser's ``seen`` set already
        drops the repeat — and deleting the marker handling entirely leaves the output
        byte-identical and this test green. An earlier version of this docstring claimed
        the opposite. Pinning the marker needs a sheet where ``PERCENT`` comes first or
        carries a year ``NUMBER`` does not; that fixture is deferred test-hardening work,
        and until it exists the marker is documented behaviour, not guarded behaviour.
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

    def test_the_transposed_second_table_is_read_for_both_sheets_that_have_one(
        self,
    ) -> None:
        """#234. Alaska and Hawaii publish their pre-1960 population here and nowhere else.

        Before this, the parsed series for both started at 1960 while the file itself went
        back to 1880/1900, because the second table carries neither the ``NUMBER`` nor the
        ``PERCENT`` marker the first reader keys on. 1960 Alaska and Hawaii
        persons-per-electoral-vote were NULL as a direct result.

        **Exact year-sets, not `min()`.** The extent alone would pass under a reading that
        dropped an interior column, mapped every column to the wrong year by a constant
        offset, or invented a year; the full set catches all three. Both figures below are
        measured from the published workbook.
        """
        figures = _lookup(_tabs())
        assert figures[("Alaska", 1950)] == 128_643
        assert figures[("Hawaii", 1950)] == 499_794

        alaska = {year for area, year in figures if area == "Alaska"}
        hawaii = {year for area, year in figures if area == "Hawaii"}
        # Alaska reaches 1880 and carries two off-cycle censuses; Hawaii reaches only
        # 1900 and is entirely on-cycle. Asserted separately because the two extents
        # genuinely differ -- Hawaii was an independent kingdom in 1880 -- so deriving
        # either from the other would be an assumption the source does not support.
        assert alaska == {
            1880, 1890, 1900, 1910, 1920, 1929, 1939, 1950, 1960, 1970, 1980, 1990,
        }
        assert hawaii == {1900, 1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990}

    def test_alaskas_off_cycle_censuses_are_emitted_never_relabelled(self) -> None:
        """AC-3, the half that lives at this layer.

        Alaska's censuses were taken in 1939 and 1929 "instead of" 1940 and 1930 -- the
        sheet's own footnote says so. ``census_year`` is part of the natural key and is
        decennial, so relabelling 1939 to 1940 would be D005 fabrication: a figure filed
        under a census that never happened.

        The parser is **faithful** and emits them as published. Dropping them is a
        which-censuses-are-in-scope decision, which belongs to ``transform.SOURCE_SPANS``
        and is asserted there -- the split is what makes "skipped" and
        "relabelled-then-deduped" distinguishable, which asserting absence here could
        never be.
        """
        alaska = {
            year: population
            for (area, year), population in _lookup(_tabs()).items()
            if area == "Alaska"
        }
        assert alaska[1939] == 72_524
        assert alaska[1929] == 59_278
        # The decennial years they are NOT to be filed under. Hawaii genuinely has 1940
        # and 1930; Alaska must not acquire them by relabelling.
        assert 1940 not in alaska
        assert 1930 not in alaska

    def test_the_total_row_is_found_by_label_not_by_position(self) -> None:
        """The reject side of the `Total` anchor -- and it needs a synthetic sheet.

        On BOTH real sheets ``Total`` happens to be the first data row under the header,
        so replacing the label anchor with "the first row after the header" is
        **byte-identical** over the whole fixture and over the real 51-sheet corpus. A
        test that only reads published bytes cannot tell the two apart, and a reject-side
        test that puts the race rows *after* ``Total`` cannot either.

        This is #182's surviving-mutant lesson applied before the fact: there, every
        assertion around a regex was an acceptance one, so loosening the reject half left
        every output byte-identical. Here the race rows come FIRST.
        """
        workbook = _state_sheet_workbook(
            "Alaska",
            [
                ["NUMBER", ""],
                ["1990 ................", "550043"],
                ["Race", "1950", "1940"],
                ["White................", "92808", "39170"],
                [".   Japanese.........", "1000", "263"],
                ["            Total....", "128643", "72524"],
            ],
        )
        figures = {
            row.census_year: row.population
            for row in parse_resident_1790_1990(workbook, source_id="x")
        }
        assert figures == {1990: 550_043, 1950: 128_643, 1940: 72_524}
        # The race rows sit between the header and the total; reading either as the
        # total is the mutation this test exists to kill.
        assert 92_808 not in figures.values()
        assert 1_000 not in figures.values()

    def test_the_number_block_wins_a_year_both_tables_publish(self) -> None:
        """The reject side of the NUMBER-first precedence.

        No year is published in both tables on either real sheet, so the ``seen`` guard
        can be deleted with byte-identical output over every published byte -- an
        untestable safety property unless the overlap is constructed. The two values
        differ so the assertion names which table won.
        """
        workbook = _state_sheet_workbook(
            "Alaska",
            [
                ["NUMBER", ""],
                ["1950 ................", "999999"],
                ["Race", "1950"],
                ["            Total....", "111111"],
            ],
        )
        figures = {
            row.census_year: row.population
            for row in parse_resident_1790_1990(workbook, source_id="x")
        }
        assert figures == {1950: 999_999}
        assert 111_111 not in figures.values()

    def test_an_unknown_off_cycle_census_raises_rather_than_being_dropped(self) -> None:
        """The reject side of the off-cycle rule -- the rule, not its outcome.

        On the real data, ``year % 10 == 0``, ``year % 5 == 0`` and
        ``year not in {1939, 1929}`` are indistinguishable: only 1939 and 1929 are
        off-cycle and all three reject exactly those. So an outcome test pins nothing
        about the rule.

        What separates them is a year nobody has seen. A silent skip would drop a
        re-issued column without a word -- the same shape as the U+2026 leaders dropping
        South Carolina 1790. Refusing is the reflex ``_to_population`` already applies to
        a cell it does not recognize.
        """
        workbook = _state_sheet_workbook(
            "Alaska",
            [
                ["NUMBER", ""],
                ["1990 ................", "550043"],
                ["Race", "1935"],
                ["            Total....", "50000"],
            ],
        )
        with pytest.raises(CensusParseError, match="1935"):
            parse_resident_1790_1990(workbook, source_id="x")

    def test_a_sheet_with_no_transposed_table_gains_nothing(self) -> None:
        """Absent is silent: 49 of the 51 sheets have no second table.

        Connecticut is the untouched control in the fixture -- its whole series comes
        from the ``NUMBER`` block, and a detector that over-fired would show up here as
        a phantom year or a changed figure.
        """
        connecticut = {
            year: population
            for (area, year), population in _lookup(_tabs()).items()
            if area == "Connecticut"
        }
        assert min(connecticut) == 1790
        assert connecticut[1790] == 237_946
        # Every year is decennial: no off-cycle column leaked in from anywhere.
        assert all(year % 10 == 0 for year in connecticut)

    def test_a_header_with_no_readable_total_row_raises(self) -> None:
        """...but present-but-unreadable is LOUD, which is the other half of the design.

        A sheet that presents the anchor and then offers nothing readable beneath it
        means the published layout moved. Returning a short series there is exactly the
        silent truncation this module refuses; the answer to a re-issued file is to fail
        loudly, never to loosen the anchor until it matches something again.
        """
        workbook = _state_sheet_workbook(
            "Alaska",
            [
                ["NUMBER", ""],
                ["1990 ................", "550043"],
                ["Race", "1950"],
                ["White................", "92808"],
            ],
        )
        with pytest.raises(CensusParseError, match="Total"):
            parse_resident_1790_1990(workbook, source_id="x")

    def test_a_year_label_with_unicode_ellipsis_leaders_is_read(self) -> None:
        # The regression for the one figure this parser used to drop silently (#182):
        # South Carolina's 1790 row uses U+2026 ellipsis leaders where every other sheet
        # in the workbook uses ASCII dots, so ``[\s.]*$`` failed its anchor and the row
        # was skipped ENTIRELY — no row at all, not a NULL — losing
        # South Carolina 1790 = 249,073.
        #
        # Both labels below are copied verbatim from the published workbook, including
        # the trailing ASCII dot after the ellipses and the ASCII-leader PERCENT twin
        # that must NOT be read as a count.
        workbook = _state_sheet_workbook(
            "South Carolina",
            [
                ["NUMBER", ""],
                ["1800  ...........", "345591"],
                ["1790  …………………………………….", "249073"],
                ["PERCENT", ""],
                ["1790  .....................", "100"],
            ],
        )
        rows = parse_resident_1790_1990(workbook, source_id="x")
        figures = {row.census_year: row.population for row in rows}
        assert figures == {1800: 345_591, 1790: 249_073}
        # 100 is the PERCENT-block twin; reading it would be the other half of the bug.
        assert 100 not in figures.values()

    def test_a_label_that_merely_starts_with_four_digits_is_not_a_year_label(
        self,
    ) -> None:
        """Survivor 4 (#182 Class B): dropping `_YEAR_LABEL`'s `$` anchor survived the suite.

        Unanchored, any cell beginning with four digits reads as a year label and column B is
        taken as that year's population — and because the first match for a year wins, a
        heading placed above the real row silently displaces it.

        Every existing assertion around this regex is an **acceptance** one: the ellipsis
        regression, the `1940/2` footnote marker, the PERCENT block, the `.  Sample` sub-rows.
        Each checks that the right figures come *out*. Not one asserted a label is **rejected**,
        so loosening only the reject half left every output byte-identical. #182 widened this
        regex's accept side and added a regression for that; the reject side had nothing.

        The three labels below are real shapes this workbook family contains.
        """
        workbook = _state_sheet_workbook(
            "Ohio",
            [
                ["NUMBER", ""],
                ["1960 to 1970 change", "999999"],
                ["1960 ...........", "9706397"],
                ["1890 census of population", "888888"],
                ["1890/3 .........", "3672329"],
            ],
        )
        rows = parse_resident_1790_1990(workbook, source_id="x")
        figures = {row.census_year: row.population for row in rows}
        # The published rows win; neither heading is read as a year at all.
        assert figures == {1960: 9_706_397, 1890: 3_672_329}
        assert 999_999 not in figures.values()
        assert 888_888 not in figures.values()

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
