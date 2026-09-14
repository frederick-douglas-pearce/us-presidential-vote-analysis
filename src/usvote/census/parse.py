"""Parse stage — read the published XLSX workbooks into flat population rows.

Pure and offline: it takes bytes and returns records, so every test here runs without a
network or a database. This is the **first** XLSX parsing in the repo, and it uses
stdlib ``zipfile`` + ``xml.etree`` rather than adding ``openpyxl`` — the same choice S1
made when it verified the source, and the reason the repo's dependency set is unchanged
by this story.

**Faithful, not selective.** Each parser returns everything its file contains, including
census years the other file also covers and area rows that are not states. Deciding
*which* file supplies a census (the stitch) and *which* areas are in scope belongs to
:mod:`usvote.census.transform`, so that both decisions are explicit, tested policy
rather than a side effect of what the parser happened to keep.

The two files are shaped very differently, which is why there are two parsers:

* ``tabs15-65.xlsx`` — one sheet per state, the sheet **name** being the state. Each
  sheet holds a ``NUMBER`` block and a ``PERCENT`` block using the *same* year labels,
  so a parser that ignored the block marker would read percentages as populations.
  Year labels carry dot-leaders and footnote markers (``1940/2 .....``), and the block
  is interleaved with ``.   Sample`` / ``.   15% sample`` sub-rows that repeat a year.
* the population-change table — a single sheet with three page-blocks laid **side by
  side**, each repeating an ``Area`` column, and literal
  ``"This cell is intentionally blank."`` filler cells.

**On stdlib XML and untrusted input.** ``xml.etree`` is used deliberately rather than
``defusedxml``. The bytes parsed here come only from the local corpus
(:mod:`usvote.census.scrape`) — files this project downloaded from ``census.gov`` over
HTTPS and recorded a sha256 for — so they sit at the same trust level as the Archives
HTML the EC spine already parses with BeautifulSoup, and are never attacker-supplied.
``xml.etree`` does not resolve external entities, so the XXE class does not apply;
entity-expansion ("billion laughs") would require a hostile file to have replaced a
hash-recorded one in the operator's own corpus directory. Adding ``defusedxml`` would
put a third-party dependency in the import path of a stage whose no-new-dependency
property is the reason this source was chosen over the OCR'd alternative.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from typing import NamedTuple

#: OOXML namespaces. Spreadsheets written by the Bureau use the standard main/relations
#: namespaces; nothing here depends on a producer-specific extension.
_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

#: A year label in the 1790-1990 workbook: four digits, an optional ``/n`` footnote
#: marker, then dot-leaders. The footnote marker is why this is a regex and not
#: ``int(cell)`` — ``1940/2`` is a real label and the naive read raises on exactly the
#: rows that carry footnotes.
#:
#: **The leader class must include U+2026, and the reason is a real data loss** (#182).
#: The workbook is not consistent about its leaders: almost every sheet uses runs of
#: ASCII ``.``, but South Carolina's 1790 row uses Unicode horizontal ellipses (``1790
#: ……………``). With the class written ``[\s.]*$`` the anchor failed on that one label, the
#: row was skipped, and **South Carolina 1790 = 249,073 was dropped entirely** — not
#: loaded as NULL, absent. Exactly one figure in the whole 51-sheet workbook, which is
#: what made it invisible: the sheet parsed, the suite passed, and the series was
#: silently one census short. Immaterial to the electoral analysis (the 1790 census
#: governs only the 1792 and 1796 elections, below ``EC_SPINE_FLOOR``) and fixed because
#: a silent single-cell loss is the class of defect this source's guards exist for.
_YEAR_LABEL = re.compile(r"^(\d{4})(?:/\d+)?[\s.…]*$")

#: The label column of the **transposed second table** that Alaska's and Hawaii's
#: sheets carry, and nothing else in this workbook does. Their pre-1960 population
#: lives there — race per row, census year across columns — in a block carrying neither
#: the ``NUMBER`` nor the ``PERCENT`` marker :func:`_parse_state_sheet` keys on, so it
#: was unread until #234 and 1960 Alaska/Hawaii persons-per-electoral-vote were NULL.
#:
#: **Measured, not assumed:** across all 51 published sheets, a column-A cell reading
#: exactly ``Race`` selects **exactly two** — Alaska and Hawaii. That measurement is
#: pinned by ``TestRealCorpus.test_exactly_two_sheets_carry_a_column_a_race_label`` in
#: ``tests/unit/test_census_parse.py``, which needs the corpus and skips without it — so
#: it is a merge precondition rather than something CI proves.
#:
#: The label column is preferred over any rule keyed on *cell shape* because
#: :data:`_YEAR_LABEL` matches any bare four-digit string and the race-breakdown columns
#: are full of four-digit *counts* — a population is indistinguishable from a year in
#: isolation. Same reason :func:`_parse_state_sheet` keys on its own label column rather
#: than on cell shapes.
#:
#: **How much weaker the shape rules are is stated by that test and deliberately not
#: paraphrased here.** Two successive attempts to put those counts in prose stated them
#: wrongly — #234 and then its own review — so the test is the statement and this
#: comment does not restate it. See D061 for what each attempt got wrong.
_TRANSPOSED_HEADER_LABEL = "Race"

#: The row within that table carrying the published total. Anchored on its label, never
#: on its position — and the mutant that anchor defeats is narrower than it first looks.
#: On both real sheets a caption row, ``(leading dots indicate sub-parts)``, sits
#: between the header and ``Total``, and its cells are **empty**. So a naive "the row
#: after the header" reads blanks, every population comes back NULL, and the
#: accept-side assertions over the real fixture already kill it. What the real bytes
#: **cannot** catch is "the first row after the header that carries a parseable number"
#: — byte-identical on both sheets, precisely because that caption carries none. That
#: mutant is why ``test_the_total_row_is_found_by_label_not_by_position`` builds a
#: synthetic sheet with the race rows **before** ``Total`` (#234, from #182's
#: surviving-mutant lesson).
_TRANSPOSED_TOTAL_LABEL = "Total"

#: Alaska's two off-cycle censuses, from the sheet's own footnote: *"Censuses of
#: population were taken in 1939 (instead of 1940) and in 1929 (instead of 1930)."*
#:
#: They are **parsed faithfully and emitted**, never relabelled to a decennial year —
#: relabelling would be D005 fabrication, and ``census_year`` is part of the natural
#: key. Excluding them from the warehouse is **not this module's job**: that is a
#: which-censuses-are-in-scope decision, and
#: :data:`usvote.census.transform.SOURCE_SPANS` (``range(1790, 2000, 10)``) already
#: makes it. Keeping the decision there rather than here is what keeps this parser
#: "faithful, not selective" like its sibling, and splits the property into two testable
#: halves: this layer proves 1939 is never read as 1940, and the transform proves 1939
#: never reaches the frame.
_OFF_CYCLE_CENSUSES = frozenset({1929, 1939})

#: A resident-population column header in the population-change table.
_RESIDENT_HEADER = re.compile(r"^Resident Population\s+(\d{4})\s+Census$")

#: Cell values that mean "no published figure". ``(NA)`` and ``(X)`` are the Bureau's
#: own sentinels; the filler string is literal text in the population-change table. They
#: become NULL with provenance downstream (D005) — never zero, never interpolated.
_NULL_SENTINELS = frozenset(
    {"(NA)", "(X)", "(D)", "(S)", "-", "--", "This cell is intentionally blank."}
)

#: The label column header in the population-change table. It repeats once per
#: page-block, which is what makes the side-by-side layout readable at all.
_AREA_HEADER = "Area"


class CensusParseError(RuntimeError):
    """Raised when a workbook does not have the structure this parser expects.

    Always preferred to returning a short result: a silently truncated series is the
    failure mode this whole story is built to avoid.
    """


class PopulationRow(NamedTuple):
    """One published resident-population figure, as read.

    ``population`` is ``None`` where the source prints a sentinel — a state that did not
    exist at that census, or a figure the Bureau does not publish. The distinction
    between "no figure" and "zero" is load-bearing (D005), so it survives as ``None``
    all the way to the database.
    """

    census_year: int
    area: str
    population: int | None
    source_id: str


def _column_index(ref: str) -> int:
    """Return the zero-based column index of a cell reference (``"AB12"`` -> 27)."""
    index = 0
    for char in ref:
        if not char.isalpha():
            break
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """Return the workbook's shared-string table, or an empty list if it has none."""
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{_MAIN}t"))
        for item in root.iter(f"{_MAIN}si")
    ]


def _sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    """Return ``[(sheet name, archive path)]`` in workbook order.

    Resolved through the relationship table rather than assuming
    ``xl/worksheets/sheet<N>.xml`` matches the Nth ``<sheet>`` element. That assumption
    holds for these two files today and is not guaranteed by the format — a workbook
    edited and re-saved can renumber its parts, at which point the naive reader silently
    reads the *wrong state's* sheet under the right state's name.
    """
    rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.get("Id"): rel.get("Target", "")
        for rel in rels_root.iter(f"{_PKG_REL}Relationship")
    }
    sheets: list[tuple[str, str]] = []
    for sheet in ET.fromstring(archive.read("xl/workbook.xml")).iter(f"{_MAIN}sheet"):
        name = sheet.get("name")
        target = targets.get(sheet.get(f"{_REL_NS}id", ""), "")
        if not name or not target:
            raise CensusParseError(
                f"Workbook sheet {name!r} has no resolvable relationship target; the "
                f"file may be corrupt or not an OOXML workbook."
            )
        path = target[1:] if target.startswith("/") else f"xl/{target}"
        sheets.append((name, path.replace("xl/xl/", "xl/")))
    return sheets


def _rows(
    archive: zipfile.ZipFile, path: str, strings: list[str]
) -> Iterator[list[str]]:
    """Yield each sheet row as a list of cell texts, positioned by column.

    Cells absent from the XML (an empty cell is simply not written) are yielded as empty
    strings so a caller can index by column, which is what the side-by-side block layout
    requires.
    """
    for row in ET.fromstring(archive.read(path)).iter(f"{_MAIN}row"):
        cells: list[str] = []
        for cell in row.iter(f"{_MAIN}c"):
            index = _column_index(cell.get("r", ""))
            if index < 0:
                continue
            if index >= len(cells):
                cells.extend([""] * (index - len(cells) + 1))
            cells[index] = _cell_text(cell, strings)
        yield cells


def _cell_text(cell: ET.Element, strings: list[str]) -> str:
    """Return a cell's text, resolving shared and inline strings."""
    kind = cell.get("t")
    if kind == "inlineStr":
        node = cell.find(f"{_MAIN}is")
        if node is None:
            return ""
        return "".join(t.text or "" for t in node.iter(f"{_MAIN}t"))
    value = cell.find(f"{_MAIN}v")
    if value is None or value.text is None:
        return ""
    if kind == "s":
        try:
            return strings[int(value.text)]
        except (ValueError, IndexError):
            return ""
    return value.text


def _to_population(text: str) -> int | None:
    """Return ``text`` as a count, or ``None`` for a sentinel/blank.

    Anything that is neither a sentinel nor a parseable integer raises: an unrecognized
    cell means the layout moved, and guessing would put a wrong number in the warehouse.
    """
    cleaned = text.strip().replace(",", "")
    if not cleaned or cleaned in _NULL_SENTINELS:
        return None
    try:
        return int(cleaned)
    except ValueError as exc:
        raise CensusParseError(
            f"Unrecognized population cell {text!r}: it is neither a published "
            f"sentinel ({', '.join(sorted(_NULL_SENTINELS))}) nor an integer."
        ) from exc


def parse_resident_1790_1990(data: bytes, *, source_id: str) -> list[PopulationRow]:
    """Parse ``tabs15-65.xlsx`` — one sheet per state, 1790-1990.

    Reads the ``Total population`` column (column B) of each sheet's ``NUMBER`` block
    and stops at ``PERCENT``. Three properties of the layout are handled explicitly
    because each one silently corrupts the result if it is not:

    * the ``PERCENT`` block repeats every year label, so percentages would be read as
      populations by a parser that keyed on the year alone;
    * ``.   Sample`` / ``.   15% sample`` sub-rows repeat a year within the ``NUMBER``
      block, so the first row for a year is the published count and the sub-rows are
      alternative tabulations — they are skipped, not summed or overwritten;
    * ``1940/2``-style labels carry footnote markers.
    """
    rows: list[PopulationRow] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        strings = _shared_strings(archive)
        sheets = _sheet_paths(archive)
        if not sheets:
            raise CensusParseError("The workbook contains no sheets.")
        for area, path in sheets:
            rows.extend(
                _parse_state_sheet(archive, path, strings, area=area, source=source_id)
            )
    if not rows:
        raise CensusParseError(
            "No population rows were read from the 1790-1990 workbook. Expected a "
            "'NUMBER' block on each state sheet; the layout may have changed."
        )
    return rows


def _parse_state_sheet(
    archive: zipfile.ZipFile,
    path: str,
    strings: list[str],
    *,
    area: str,
    source: str,
) -> Iterator[PopulationRow]:
    """Yield the ``NUMBER``-block rows of one state sheet, then its transposed table.

    The sheet rows are materialized once and read twice: the ``NUMBER`` walk first, then
    :func:`_parse_transposed_table` for the two sheets that carry one. Order is the
    mechanism — the second pass receives a fully-populated ``seen``, so the ``NUMBER``
    block wins any year both tables publish.
    """
    rows = list(_rows(archive, path, strings))
    in_number_block = False
    seen: set[int] = set()
    for cells in rows:
        if not cells:
            continue
        label = cells[0].strip()
        if label in ("NUMBER", "PERCENT"):
            # PERCENT repeats every year label with percentages in the same column, so
            # the marker is the only thing separating counts from proportions.
            in_number_block = label == "NUMBER"
            continue
        if not in_number_block or not label:
            continue
        if label.startswith("."):
            # ".   Sample" / ".   15% sample" — alternative tabulations of a year that
            # is already recorded. Skipping them is what keeps one row per census.
            continue
        match = _YEAR_LABEL.match(label)
        if match is None:
            continue
        year = int(match.group(1))
        if year in seen:
            continue
        seen.add(year)
        # Column B is 'Total population'; the columns after it break that total down by
        # race, which is not what this source is being read for.
        value = cells[1] if len(cells) > 1 else ""
        yield PopulationRow(
            census_year=year,
            area=area,
            population=_to_population(value),
            source_id=source,
        )

    yield from _parse_transposed_table(rows, area=area, source=source, seen=seen)


def _parse_transposed_table(
    rows: list[list[str]],
    *,
    area: str,
    source: str,
    seen: set[int],
) -> Iterator[PopulationRow]:
    """Yield the rows of a sheet's transposed second table, if it has one.

    Alaska and Hawaii publish their pre-1960 population here and nowhere else. The table
    is laid out the other way up from the ``NUMBER`` block — race per row, census year
    across columns — and the two sheets do not agree on where it starts: **Alaska's year
    header begins in column B, Hawaii's in column C with column B empty.** So the
    column-to-year map is read off the header row and applied positionally to the
    ``Total`` row, which handles both from one path and handles Hawaii's empty column
    for free: an empty header cell yields no year, so nothing is read beneath it.

    **Absent is silent; present-but-unreadable is loud.** The other 49 sheets have no
    such table and yield nothing, quietly. But a sheet that presents the header anchor
    and offers no readable ``Total`` row raises, as :func:`parse_population_change`
    raises when its own headers move. The answer to a re-issued file is to fail loudly,
    never to loosen the anchor until it matches something.
    """
    header_index = next(
        (
            i
            for i, cells in enumerate(rows)
            if cells and cells[0].strip() == _TRANSPOSED_HEADER_LABEL
        ),
        None,
    )
    if header_index is None:
        return

    header = rows[header_index]
    columns: list[tuple[int, int]] = []
    for column, text in enumerate(header):
        if column == 0:
            continue
        match = _YEAR_LABEL.match(text.strip())
        if match is None:
            continue
        year = int(match.group(1))
        if year % 10 and year not in _OFF_CYCLE_CENSUSES:
            # A non-decennial column this parser has not been told about means the
            # published layout moved. Refusing is the same reflex as _to_population's:
            # a silent skip here would drop a real census exactly as the U+2026 leaders
            # once dropped South Carolina 1790.
            raise CensusParseError(
                f"{area}: the transposed table carries an unexpected non-decennial "
                f"census year {year!r}. The allowed off-cycle years are "
                f"{sorted(_OFF_CYCLE_CENSUSES)}, which Alaska took per its own "
                f"footnote; the allow-list is deliberately not scoped by state, so "
                f"another sheet printing one of them would pass here too. Anything "
                f"else means the layout changed and the column-to-year mapping can no "
                f"longer be trusted."
            )
        columns.append((column, year))

    total = next(
        (
            cells
            for cells in rows[header_index + 1 :]
            if cells and _strip_leaders(cells[0]) == _TRANSPOSED_TOTAL_LABEL
        ),
        None,
    )
    if not columns or total is None:
        raise CensusParseError(
            f"{area}: the sheet has a transposed second table (a "
            f"{_TRANSPOSED_HEADER_LABEL!r} label column) but "
            + (
                "no year columns could be read from its header."
                if not columns
                else f"no {_TRANSPOSED_TOTAL_LABEL!r} row beneath it."
            )
            + " The published layout may have changed; refusing to return a short "
            + "series."
        )

    for column, year in columns:
        if year in seen:
            # The NUMBER block is read first and wins. No year is published in both
            # tables today, so this is a safety property rather than a live path.
            continue
        seen.add(year)
        if column >= len(total):
            raise CensusParseError(
                f"{area}: the transposed table's header declares a {year} column "
                f"(index {column}) but its {_TRANSPOSED_TOTAL_LABEL!r} row holds only "
                f"{len(total)} cells, so that census has no cell there at all. A cell "
                f"written empty is an honest NULL; a {_TRANSPOSED_TOTAL_LABEL!r} row "
                f"too short to reach a declared column is a layout change — this "
                f"workbook "
                f"writes its data rows to full width, so a short one is not an "
                f"unpublished figure. Refusing rather than returning a short series "
                f"— the transform would otherwise stamp the row 'No published figure "
                f"in tabs15-65.xlsx for this census', which this header contradicts."
            )
        value = total[column]
        yield PopulationRow(
            census_year=year,
            area=area,
            population=_to_population(value),
            source_id=source,
        )


def _strip_leaders(label: str) -> str:
    """Return a row label without its surrounding space or dot/ellipsis leaders.

    The workbook is not consistent about leaders — ASCII runs on most rows, U+2026 on
    some — and the transposed table indents its ``Total`` row, so both ends need
    trimming before the label can be compared.
    """
    return label.strip().rstrip(".…").strip()


def parse_population_change(data: bytes, *, source_id: str) -> list[PopulationRow]:
    """Parse the population-change table — side-by-side decade blocks, 1910-2020.

    The layout is three page-blocks printed next to each other, each repeating an
    ``Area`` label column, so a column's area is the nearest ``Area`` column at or to
    its left. Both header rows are **located by content** rather than by index: the
    Bureau prints a department/bureau/title preamble above them whose height is a
    formatting choice, and hardcoding "row 4" would break silently the first time it
    changes — reading a title row as data rather than failing.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        strings = _shared_strings(archive)
        sheets = _sheet_paths(archive)
        if not sheets:
            raise CensusParseError("The workbook contains no sheets.")
        table = list(_rows(archive, sheets[0][1], strings))

    area_columns: list[int] = []
    year_columns: list[tuple[int, int]] = []
    header_row = -1
    for index, cells in enumerate(table):
        found_areas = [
            i for i, text in enumerate(cells) if text.strip() == _AREA_HEADER
        ]
        if found_areas:
            area_columns = found_areas
        found_years = [
            (i, int(match.group(1)))
            for i, text in enumerate(cells)
            if (match := _RESIDENT_HEADER.match(text.strip())) is not None
        ]
        if found_years:
            year_columns = found_years
            header_row = index
            break

    if not area_columns or not year_columns:
        raise CensusParseError(
            "The population-change table has no 'Area' column or no 'Resident "
            "Population <year> Census' header; the published layout may have changed."
        )

    rows: list[PopulationRow] = []
    for cells in table[header_row + 1 :]:
        candidates: list[PopulationRow] = []
        for column, year in year_columns:
            label_column = max(
                (c for c in area_columns if c <= column), default=area_columns[0]
            )
            area = cells[label_column].strip() if label_column < len(cells) else ""
            if not area:
                continue
            value = cells[column] if column < len(cells) else ""
            candidates.append(
                PopulationRow(
                    census_year=year,
                    area=area,
                    population=_to_population(value),
                    source_id=source_id,
                )
            )
        # Drop a row carrying no figure in any census column. The table's footer sits
        # inside the same columns as its data — a "Note: ..." paragraph in the Area
        # column and a "Page N of 3" marker in each block — so a purely positional read
        # yields them as areas named after their own text. They are distinguishable
        # structurally rather than by matching their wording, which would break the
        # first time the Bureau renumbers or rewords a footer: an area row always
        # carries at least one published population, and a footer never does.
        if any(row.population is not None for row in candidates):
            rows.extend(candidates)
    if not rows:
        raise CensusParseError(
            "No population rows were read from the population-change table."
        )
    return rows
