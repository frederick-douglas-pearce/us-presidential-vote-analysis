"""The census source catalog — one authority for what this corpus holds.

Dependency-free by contract (stdlib only, no ``requests``, no pandas, no DB), which is
the whole reason it is its own module rather than living in
:mod:`usvote.census.scrape`. Two stages need these facts and they must not depend on
each other: the fetch stage needs the URLs, and the **pure, offline** transform needs
each row's ``source_file`` and ``vintage`` provenance. Deriving the transform's copy
from the scrape module would drag ``requests`` into a transform whose offline-ness is
the point — the same reasoning that puts :mod:`usvote.count_status` and
:mod:`usvote.years` at the top level rather than inside a stage.

**Why this module exists at all** (#181 review, F10/F2): the filename and the vintage
were previously spelled *twice* — authoritatively here-in-`scrape.py`, and again as
literal maps in ``transform.py`` — with nothing tying the two. A rename would have
updated the fetch and silently falsified every loaded row's ``source_file`` provenance,
and the vintage had no authority at all. Both are now single-sourced on
:data:`CENSUS_SOURCES`, so the duplication cannot be reintroduced without deleting a
field.
"""

from __future__ import annotations

from typing import NamedTuple


class SourceFile(NamedTuple):
    """One published file in the corpus, and everything downstream needs to know of it.

    ``source_id`` is the manifest key and the stable name every other stage refers to;
    ``filename`` is what lands on disk, kept as the Bureau's own filename so a human
    browsing the directory can match it against the published page; ``vintage`` is the
    published tabulation this file represents, carried onto every row it supplies.
    """

    source_id: str
    url: str
    filename: str
    span: str
    vintage: str
    description: str


#: Table 15-65 of POP-twps0056: one sheet per state (50 + DC), resident population by
#: census 1790-1990. S1 verified the bytes (329,123 B) and read values out of it.
RESIDENT_1790_1990 = SourceFile(
    source_id="resident_1790_1990",
    url=(
        "https://www2.census.gov/library/working-papers/2002/demo/"
        "pop-twps0056/tabs15-65.xlsx"
    ),
    filename="tabs15-65.xlsx",
    span="1790-1990",
    vintage="census-bureau-pop-twps0056-2002",
    description=(
        "Census Bureau working paper POP-twps0056, tables 15-65 — resident population "
        "by state and census year, one sheet per state (50 states + DC)."
    ),
)

#: The 2020 population-change table: resident population by state for 1910-2020, laid
#: out as side-by-side decade blocks. Only its 2000/2010/2020 columns are read (the
#: stitch rule in :mod:`usvote.census.transform` gives 1910-1990 to the file above).
RESIDENT_1910_2020 = SourceFile(
    source_id="resident_1910_2020",
    url=(
        "https://www2.census.gov/programs-surveys/decennial/2020/data/"
        "apportionment/population-change-data-table.xlsx"
    ),
    filename="population-change-data-table.xlsx",
    span="1910-2020",
    vintage="census-bureau-apportionment-2020",
    description=(
        "Change in Resident Population of the 50 States, the District of Columbia, "
        "and Puerto Rico: 1910 to 2020 — the 2020 apportionment release."
    ),
)

#: Every file this corpus holds. #183 appends the seats sources here; nothing else needs
#: to change for them to be snapshotted, guarded, read, and attributed.
CENSUS_SOURCES: tuple[SourceFile, ...] = (RESIDENT_1790_1990, RESIDENT_1910_2020)

#: The sources the population load requires. Kept separate from :data:`CENSUS_SOURCES`
#: so a corpus that has grown #183's seats files is not *required* to have them before
#: this pipeline will run, and vice versa.
RESIDENT_SOURCE_IDS: tuple[str, ...] = (
    RESIDENT_1790_1990.source_id,
    RESIDENT_1910_2020.source_id,
)

#: ``{source_id: filename}`` and ``{source_id: vintage}``, **derived** rather than
#: restated. The derivation is the fix: a second literal map is what let a rename
#: falsify provenance while every test stayed green.
SOURCE_FILENAMES: dict[str, str] = {s.source_id: s.filename for s in CENSUS_SOURCES}
SOURCE_VINTAGES: dict[str, str] = {s.source_id: s.vintage for s in CENSUS_SOURCES}
