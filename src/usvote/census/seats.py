"""Published House seats per state and census — the curated authority for #183.

The seat counts Congress apportioned, as **published by the Census Bureau**, for every
census that governs an in-scope presidential election. This module is *data*: it holds
no derivation, and the reconciliation that reads it lives in
:mod:`usvote.census.reconcile`.

**Why the data is curated here rather than parsed at runtime** (#183 architect review,
Q1). The full-span published source is a **text-layer PDF**
(``cph-2-1-1-table-3.pdf``, 1789-2010), and every parser this package ships is
stdlib-only -- :mod:`usvote.census.parse` reads XLSX with ``zipfile`` + ``xml.etree``
precisely so that no dependency is added. Reading the PDF at runtime would put
``poppler-utils`` -- a **system** binary, unpinnable in ``uv.lock`` -- on the CI
critical path of a package built to avoid exactly that. So the seats are curated into
the repo as a provenance-carrying constant, which the source's public-domain status
permits (a US government work; contrast UCSB under D022, where no byte may be
committed).

Two properties follow, and the second is the one that matters:

* **No new dependency, and the reconciliation is offline.**
* **It runs on every warehouse build**, with no corpus present -- strictly stronger than
  a gate that fires only when someone has snapshotted a corpus first. That property is
  the wiring's, not this module's: :func:`usvote.warehouse.run_warehouse` calls
  :func:`usvote.census.reconcile.assert_seats_reconcile` **outside** its
  ``census_corpus_dir`` branch. Curating the seats is what *allows* that; it does not by
  itself achieve it, and #183 shipped a first version that claimed the property while
  wiring the gate only inside the census pipeline.

**How it stays honest.** ``scripts/extract_census_seats.py`` regenerates this constant
from the published file, and ``tests/unit/test_census_seats.py::TestRealCorpus``
re-extracts and compares cell by cell, **skipping when ``USVOTE_CENSUS_CORPUS_DIR`` is
unset** (the #234 pattern, so CI never needs ``pdftotext``). Running it is a merge
precondition, exactly as the UCSB cross-source control test is.

**Read the ``None`` carefully.** ``None`` is the source's own ``(X)``: *this state had
no apportioned seats under this census*. It is **not** "we do not know" and **not**
zero, and above all it is not the same thing as a state **missing from a census's dict**
-- that would be a curation omission, and
:func:`usvote.census.reconcile.assert_seats_series_complete` exists to make the two
distinguishable. Collapsing them is how a forgotten cell would come to read as a
legitimate not-applicable and pass as a declared exception.

**Two source characteristics that look like defects and are not.**

* **The 1950 column totals 437, not the 435 Congress apportioned.** Alaska and Hawaii
  are included retroactively at one seat each. That is load-bearing rather than noise:
  the 1950 census governs the **1960** election, in which both states cast electoral
  votes, and it is what makes that year's 537 electors reconcile. A different published
  Bureau file (``apportionment.csv``) reports the same year as 435 with both blank --
  also correct, of the apportionment *as enacted*. Only this table's basis reconciles
  against electoral votes, which is why this module has exactly one source per span and
  does not stitch the two.
* **Mid-decade admissions are filled in inconsistently by the source.** Nevada and
  Nebraska carry one seat in the 1860 column; West Virginia, admitted in the same
  decade, carries ``(X)``. The table cannot be read as a uniform statement of "seats as
  of that census", and :mod:`usvote.census.reconcile` carries the resulting exceptions
  rather than smoothing them.

**1920 is absent by construction, not by omission.** Congress passed no apportionment
act after the 1920 census, so it governs no election and
:data:`usvote.apportionment.NO_APPORTIONMENT_CENSUSES` routes 1924/1928 to 1910. The
published table's 1920 column is fully populated -- it repeats 1910 verbatim -- so a
guard written for a *missing* 1920 row would never fire. It is simply never read.

Sources, both US government works in the public domain:

* **1820-2010** -- Census Bureau, *CPH-2-1, Table 3: Apportionment of Membership of the
  U.S. House of Representatives: 1789 to 2010*,
  ``https://www2.census.gov/programs-surveys/decennial/1990/data/apportionment/
  cph-2-1-1-table-3.pdf``
* **2020** -- Census Bureau, *Apportionment of Seats in the U.S. House of
  Representatives: 1910 to 2020* (2020 apportionment release, ``apportionment.csv``),
  ``https://www2.census.gov/programs-surveys/decennial/2020/data/apportionment/
  apportionment.csv``
"""

from __future__ import annotations

#: ``{census_year: {state: seats | None}}`` for the **20** censuses that govern an
#: in-scope election (1820-1910 and 1930-2020; 1920 governs none).
#:
#: **Every census carries all 51 jurisdictions** -- the 50 states plus the District of
#: Columbia -- with ``None`` where the source says ``(X)``. The completeness is the
#: point: a state is never absent from a census's dict, so an absent key is always a
#: defect and never a statement. Puerto Rico appears in the 2020 source and is
#: deliberately excluded here: it is not a state and appoints no electors.
SEATS_BY_CENSUS: dict[int, dict[str, int | None]] = {
    1820: {
        "Alabama": 3, "Alaska": None, "Arizona": None, "Arkansas": None,
        "California": None, "Colorado": None, "Connecticut": 6, "Delaware": 1,
        "District of Columbia": None, "Florida": None, "Georgia": 7, "Hawaii": None,
        "Idaho": None, "Illinois": 1, "Indiana": 3, "Iowa": None, "Kansas": None,
        "Kentucky": 12, "Louisiana": 3, "Maine": 7, "Maryland": 9, "Massachusetts": 13,
        "Michigan": None, "Minnesota": None, "Mississippi": 1, "Missouri": 1,
        "Montana": None, "Nebraska": None, "Nevada": None, "New Hampshire": 6,
        "New Jersey": 6, "New Mexico": None, "New York": 34, "North Carolina": 13,
        "North Dakota": None, "Ohio": 14, "Oklahoma": None, "Oregon": None,
        "Pennsylvania": 26, "Rhode Island": 2, "South Carolina": 9,
        "South Dakota": None, "Tennessee": 9, "Texas": None, "Utah": None, "Vermont": 5,
        "Virginia": 22, "Washington": None, "West Virginia": None, "Wisconsin": None,
        "Wyoming": None,
    },
    1830: {
        "Alabama": 5, "Alaska": None, "Arizona": None, "Arkansas": 1,
        "California": None, "Colorado": None, "Connecticut": 6, "Delaware": 1,
        "District of Columbia": None, "Florida": None, "Georgia": 9, "Hawaii": None,
        "Idaho": None, "Illinois": 3, "Indiana": 7, "Iowa": None, "Kansas": None,
        "Kentucky": 13, "Louisiana": 3, "Maine": 8, "Maryland": 8, "Massachusetts": 12,
        "Michigan": 1, "Minnesota": None, "Mississippi": 2, "Missouri": 2,
        "Montana": None, "Nebraska": None, "Nevada": None, "New Hampshire": 5,
        "New Jersey": 6, "New Mexico": None, "New York": 40, "North Carolina": 13,
        "North Dakota": None, "Ohio": 19, "Oklahoma": None, "Oregon": None,
        "Pennsylvania": 28, "Rhode Island": 2, "South Carolina": 9,
        "South Dakota": None, "Tennessee": 13, "Texas": None, "Utah": None,
        "Vermont": 5, "Virginia": 21, "Washington": None, "West Virginia": None,
        "Wisconsin": None, "Wyoming": None,
    },
    1840: {
        "Alabama": 7, "Alaska": None, "Arizona": None, "Arkansas": 1, "California": 2,
        "Colorado": None, "Connecticut": 4, "Delaware": 1, "District of Columbia": None,
        "Florida": 1, "Georgia": 8, "Hawaii": None, "Idaho": None, "Illinois": 7,
        "Indiana": 10, "Iowa": 2, "Kansas": None, "Kentucky": 10, "Louisiana": 4,
        "Maine": 7, "Maryland": 6, "Massachusetts": 10, "Michigan": 3,
        "Minnesota": None, "Mississippi": 4, "Missouri": 5, "Montana": None,
        "Nebraska": None, "Nevada": None, "New Hampshire": 4, "New Jersey": 5,
        "New Mexico": None, "New York": 34, "North Carolina": 9, "North Dakota": None,
        "Ohio": 21, "Oklahoma": None, "Oregon": None, "Pennsylvania": 24,
        "Rhode Island": 2, "South Carolina": 7, "South Dakota": None, "Tennessee": 11,
        "Texas": 2, "Utah": None, "Vermont": 4, "Virginia": 15, "Washington": None,
        "West Virginia": None, "Wisconsin": 2, "Wyoming": None,
    },
    1850: {
        "Alabama": 7, "Alaska": None, "Arizona": None, "Arkansas": 2, "California": 2,
        "Colorado": None, "Connecticut": 4, "Delaware": 1, "District of Columbia": None,
        "Florida": 1, "Georgia": 8, "Hawaii": None, "Idaho": None, "Illinois": 9,
        "Indiana": 11, "Iowa": 2, "Kansas": None, "Kentucky": 10, "Louisiana": 4,
        "Maine": 6, "Maryland": 6, "Massachusetts": 11, "Michigan": 4, "Minnesota": 2,
        "Mississippi": 5, "Missouri": 7, "Montana": None, "Nebraska": None,
        "Nevada": None, "New Hampshire": 3, "New Jersey": 5, "New Mexico": None,
        "New York": 33, "North Carolina": 8, "North Dakota": None, "Ohio": 21,
        "Oklahoma": None, "Oregon": 1, "Pennsylvania": 25, "Rhode Island": 2,
        "South Carolina": 6, "South Dakota": None, "Tennessee": 10, "Texas": 2,
        "Utah": None, "Vermont": 3, "Virginia": 13, "Washington": None,
        "West Virginia": None, "Wisconsin": 3, "Wyoming": None,
    },
    1860: {
        "Alabama": 6, "Alaska": None, "Arizona": None, "Arkansas": 3, "California": 3,
        "Colorado": None, "Connecticut": 4, "Delaware": 1, "District of Columbia": None,
        "Florida": 1, "Georgia": 7, "Hawaii": None, "Idaho": None, "Illinois": 14,
        "Indiana": 11, "Iowa": 6, "Kansas": 1, "Kentucky": 9, "Louisiana": 5,
        "Maine": 5, "Maryland": 5, "Massachusetts": 10, "Michigan": 6, "Minnesota": 2,
        "Mississippi": 5, "Missouri": 9, "Montana": None, "Nebraska": 1, "Nevada": 1,
        "New Hampshire": 3, "New Jersey": 5, "New Mexico": None, "New York": 31,
        "North Carolina": 7, "North Dakota": None, "Ohio": 19, "Oklahoma": None,
        "Oregon": 1, "Pennsylvania": 24, "Rhode Island": 2, "South Carolina": 4,
        "South Dakota": None, "Tennessee": 8, "Texas": 4, "Utah": None, "Vermont": 3,
        "Virginia": 11, "Washington": None, "West Virginia": None, "Wisconsin": 6,
        "Wyoming": None,
    },
    1870: {
        "Alabama": 8, "Alaska": None, "Arizona": None, "Arkansas": 4, "California": 4,
        "Colorado": 1, "Connecticut": 4, "Delaware": 1, "District of Columbia": None,
        "Florida": 2, "Georgia": 9, "Hawaii": None, "Idaho": None, "Illinois": 19,
        "Indiana": 13, "Iowa": 9, "Kansas": 3, "Kentucky": 10, "Louisiana": 6,
        "Maine": 5, "Maryland": 6, "Massachusetts": 11, "Michigan": 9, "Minnesota": 3,
        "Mississippi": 6, "Missouri": 13, "Montana": None, "Nebraska": 1, "Nevada": 1,
        "New Hampshire": 3, "New Jersey": 7, "New Mexico": None, "New York": 33,
        "North Carolina": 8, "North Dakota": None, "Ohio": 20, "Oklahoma": None,
        "Oregon": 1, "Pennsylvania": 27, "Rhode Island": 2, "South Carolina": 5,
        "South Dakota": None, "Tennessee": 10, "Texas": 6, "Utah": None, "Vermont": 3,
        "Virginia": 9, "Washington": None, "West Virginia": 3, "Wisconsin": 8,
        "Wyoming": None,
    },
    1880: {
        "Alabama": 8, "Alaska": None, "Arizona": None, "Arkansas": 5, "California": 6,
        "Colorado": 1, "Connecticut": 4, "Delaware": 1, "District of Columbia": None,
        "Florida": 2, "Georgia": 10, "Hawaii": None, "Idaho": 1, "Illinois": 20,
        "Indiana": 13, "Iowa": 11, "Kansas": 7, "Kentucky": 11, "Louisiana": 6,
        "Maine": 4, "Maryland": 6, "Massachusetts": 12, "Michigan": 11, "Minnesota": 5,
        "Mississippi": 7, "Missouri": 14, "Montana": 1, "Nebraska": 3, "Nevada": 1,
        "New Hampshire": 2, "New Jersey": 7, "New Mexico": None, "New York": 34,
        "North Carolina": 9, "North Dakota": 1, "Ohio": 21, "Oklahoma": None,
        "Oregon": 1, "Pennsylvania": 28, "Rhode Island": 2, "South Carolina": 7,
        "South Dakota": 2, "Tennessee": 10, "Texas": 11, "Utah": None, "Vermont": 2,
        "Virginia": 10, "Washington": 1, "West Virginia": 4, "Wisconsin": 9,
        "Wyoming": 1,
    },
    1890: {
        "Alabama": 9, "Alaska": None, "Arizona": None, "Arkansas": 6, "California": 7,
        "Colorado": 2, "Connecticut": 4, "Delaware": 1, "District of Columbia": None,
        "Florida": 2, "Georgia": 11, "Hawaii": None, "Idaho": 1, "Illinois": 22,
        "Indiana": 13, "Iowa": 11, "Kansas": 8, "Kentucky": 11, "Louisiana": 6,
        "Maine": 4, "Maryland": 6, "Massachusetts": 13, "Michigan": 12, "Minnesota": 7,
        "Mississippi": 7, "Missouri": 15, "Montana": 1, "Nebraska": 6, "Nevada": 1,
        "New Hampshire": 2, "New Jersey": 8, "New Mexico": None, "New York": 34,
        "North Carolina": 9, "North Dakota": 1, "Ohio": 21, "Oklahoma": None,
        "Oregon": 2, "Pennsylvania": 30, "Rhode Island": 2, "South Carolina": 7,
        "South Dakota": 2, "Tennessee": 10, "Texas": 13, "Utah": 1, "Vermont": 2,
        "Virginia": 10, "Washington": 2, "West Virginia": 4, "Wisconsin": 10,
        "Wyoming": 1,
    },
    1900: {
        "Alabama": 9, "Alaska": None, "Arizona": None, "Arkansas": 7, "California": 8,
        "Colorado": 3, "Connecticut": 5, "Delaware": 1, "District of Columbia": None,
        "Florida": 3, "Georgia": 11, "Hawaii": None, "Idaho": 1, "Illinois": 25,
        "Indiana": 13, "Iowa": 11, "Kansas": 8, "Kentucky": 11, "Louisiana": 7,
        "Maine": 4, "Maryland": 6, "Massachusetts": 14, "Michigan": 12, "Minnesota": 9,
        "Mississippi": 8, "Missouri": 16, "Montana": 1, "Nebraska": 6, "Nevada": 1,
        "New Hampshire": 2, "New Jersey": 10, "New Mexico": None, "New York": 37,
        "North Carolina": 10, "North Dakota": 2, "Ohio": 21, "Oklahoma": 5, "Oregon": 2,
        "Pennsylvania": 32, "Rhode Island": 2, "South Carolina": 7, "South Dakota": 2,
        "Tennessee": 10, "Texas": 16, "Utah": 1, "Vermont": 2, "Virginia": 10,
        "Washington": 3, "West Virginia": 5, "Wisconsin": 11, "Wyoming": 1,
    },
    1910: {
        "Alabama": 10, "Alaska": None, "Arizona": 1, "Arkansas": 7, "California": 11,
        "Colorado": 4, "Connecticut": 5, "Delaware": 1, "District of Columbia": None,
        "Florida": 4, "Georgia": 12, "Hawaii": None, "Idaho": 2, "Illinois": 27,
        "Indiana": 13, "Iowa": 11, "Kansas": 8, "Kentucky": 11, "Louisiana": 8,
        "Maine": 4, "Maryland": 6, "Massachusetts": 16, "Michigan": 13, "Minnesota": 10,
        "Mississippi": 8, "Missouri": 16, "Montana": 2, "Nebraska": 6, "Nevada": 1,
        "New Hampshire": 2, "New Jersey": 12, "New Mexico": 1, "New York": 43,
        "North Carolina": 10, "North Dakota": 3, "Ohio": 22, "Oklahoma": 8, "Oregon": 3,
        "Pennsylvania": 36, "Rhode Island": 3, "South Carolina": 7, "South Dakota": 3,
        "Tennessee": 10, "Texas": 18, "Utah": 2, "Vermont": 2, "Virginia": 10,
        "Washington": 5, "West Virginia": 6, "Wisconsin": 11, "Wyoming": 1,
    },
    1930: {
        "Alabama": 9, "Alaska": None, "Arizona": 1, "Arkansas": 7, "California": 20,
        "Colorado": 4, "Connecticut": 6, "Delaware": 1, "District of Columbia": None,
        "Florida": 5, "Georgia": 10, "Hawaii": None, "Idaho": 2, "Illinois": 27,
        "Indiana": 12, "Iowa": 9, "Kansas": 7, "Kentucky": 9, "Louisiana": 8,
        "Maine": 3, "Maryland": 6, "Massachusetts": 15, "Michigan": 17, "Minnesota": 9,
        "Mississippi": 7, "Missouri": 13, "Montana": 2, "Nebraska": 5, "Nevada": 1,
        "New Hampshire": 2, "New Jersey": 14, "New Mexico": 1, "New York": 45,
        "North Carolina": 11, "North Dakota": 2, "Ohio": 24, "Oklahoma": 9, "Oregon": 3,
        "Pennsylvania": 34, "Rhode Island": 2, "South Carolina": 6, "South Dakota": 2,
        "Tennessee": 9, "Texas": 21, "Utah": 2, "Vermont": 1, "Virginia": 9,
        "Washington": 6, "West Virginia": 6, "Wisconsin": 10, "Wyoming": 1,
    },
    1940: {
        "Alabama": 9, "Alaska": None, "Arizona": 2, "Arkansas": 7, "California": 23,
        "Colorado": 4, "Connecticut": 6, "Delaware": 1, "District of Columbia": None,
        "Florida": 6, "Georgia": 10, "Hawaii": None, "Idaho": 2, "Illinois": 26,
        "Indiana": 11, "Iowa": 8, "Kansas": 6, "Kentucky": 9, "Louisiana": 8,
        "Maine": 3, "Maryland": 6, "Massachusetts": 14, "Michigan": 17, "Minnesota": 9,
        "Mississippi": 7, "Missouri": 13, "Montana": 2, "Nebraska": 4, "Nevada": 1,
        "New Hampshire": 2, "New Jersey": 14, "New Mexico": 2, "New York": 45,
        "North Carolina": 12, "North Dakota": 2, "Ohio": 23, "Oklahoma": 8, "Oregon": 4,
        "Pennsylvania": 33, "Rhode Island": 2, "South Carolina": 6, "South Dakota": 2,
        "Tennessee": 10, "Texas": 21, "Utah": 2, "Vermont": 1, "Virginia": 9,
        "Washington": 6, "West Virginia": 6, "Wisconsin": 10, "Wyoming": 1,
    },
    1950: {
        "Alabama": 9, "Alaska": 1, "Arizona": 2, "Arkansas": 6, "California": 30,
        "Colorado": 4, "Connecticut": 6, "Delaware": 1, "District of Columbia": None,
        "Florida": 8, "Georgia": 10, "Hawaii": 1, "Idaho": 2, "Illinois": 25,
        "Indiana": 11, "Iowa": 8, "Kansas": 6, "Kentucky": 8, "Louisiana": 8,
        "Maine": 3, "Maryland": 7, "Massachusetts": 14, "Michigan": 18, "Minnesota": 9,
        "Mississippi": 6, "Missouri": 11, "Montana": 2, "Nebraska": 4, "Nevada": 1,
        "New Hampshire": 2, "New Jersey": 14, "New Mexico": 2, "New York": 43,
        "North Carolina": 12, "North Dakota": 2, "Ohio": 23, "Oklahoma": 6, "Oregon": 4,
        "Pennsylvania": 30, "Rhode Island": 2, "South Carolina": 6, "South Dakota": 2,
        "Tennessee": 9, "Texas": 22, "Utah": 2, "Vermont": 1, "Virginia": 10,
        "Washington": 7, "West Virginia": 6, "Wisconsin": 10, "Wyoming": 1,
    },
    1960: {
        "Alabama": 8, "Alaska": 1, "Arizona": 3, "Arkansas": 4, "California": 38,
        "Colorado": 4, "Connecticut": 6, "Delaware": 1, "District of Columbia": None,
        "Florida": 12, "Georgia": 10, "Hawaii": 2, "Idaho": 2, "Illinois": 24,
        "Indiana": 11, "Iowa": 7, "Kansas": 5, "Kentucky": 7, "Louisiana": 8,
        "Maine": 2, "Maryland": 8, "Massachusetts": 12, "Michigan": 19, "Minnesota": 8,
        "Mississippi": 5, "Missouri": 10, "Montana": 2, "Nebraska": 3, "Nevada": 1,
        "New Hampshire": 2, "New Jersey": 15, "New Mexico": 2, "New York": 41,
        "North Carolina": 11, "North Dakota": 2, "Ohio": 24, "Oklahoma": 6, "Oregon": 4,
        "Pennsylvania": 27, "Rhode Island": 2, "South Carolina": 6, "South Dakota": 2,
        "Tennessee": 9, "Texas": 23, "Utah": 2, "Vermont": 1, "Virginia": 10,
        "Washington": 7, "West Virginia": 5, "Wisconsin": 10, "Wyoming": 1,
    },
    1970: {
        "Alabama": 7, "Alaska": 1, "Arizona": 4, "Arkansas": 4, "California": 43,
        "Colorado": 5, "Connecticut": 6, "Delaware": 1, "District of Columbia": None,
        "Florida": 15, "Georgia": 10, "Hawaii": 2, "Idaho": 2, "Illinois": 24,
        "Indiana": 11, "Iowa": 6, "Kansas": 5, "Kentucky": 7, "Louisiana": 8,
        "Maine": 2, "Maryland": 8, "Massachusetts": 12, "Michigan": 19, "Minnesota": 8,
        "Mississippi": 5, "Missouri": 10, "Montana": 2, "Nebraska": 3, "Nevada": 1,
        "New Hampshire": 2, "New Jersey": 15, "New Mexico": 2, "New York": 39,
        "North Carolina": 11, "North Dakota": 1, "Ohio": 23, "Oklahoma": 6, "Oregon": 4,
        "Pennsylvania": 25, "Rhode Island": 2, "South Carolina": 6, "South Dakota": 2,
        "Tennessee": 8, "Texas": 24, "Utah": 2, "Vermont": 1, "Virginia": 10,
        "Washington": 7, "West Virginia": 4, "Wisconsin": 9, "Wyoming": 1,
    },
    1980: {
        "Alabama": 7, "Alaska": 1, "Arizona": 5, "Arkansas": 4, "California": 45,
        "Colorado": 6, "Connecticut": 6, "Delaware": 1, "District of Columbia": None,
        "Florida": 19, "Georgia": 10, "Hawaii": 2, "Idaho": 2, "Illinois": 22,
        "Indiana": 10, "Iowa": 6, "Kansas": 5, "Kentucky": 7, "Louisiana": 8,
        "Maine": 2, "Maryland": 8, "Massachusetts": 11, "Michigan": 18, "Minnesota": 8,
        "Mississippi": 5, "Missouri": 9, "Montana": 2, "Nebraska": 3, "Nevada": 2,
        "New Hampshire": 2, "New Jersey": 14, "New Mexico": 3, "New York": 34,
        "North Carolina": 11, "North Dakota": 1, "Ohio": 21, "Oklahoma": 6, "Oregon": 5,
        "Pennsylvania": 23, "Rhode Island": 2, "South Carolina": 6, "South Dakota": 1,
        "Tennessee": 9, "Texas": 27, "Utah": 3, "Vermont": 1, "Virginia": 10,
        "Washington": 8, "West Virginia": 4, "Wisconsin": 9, "Wyoming": 1,
    },
    1990: {
        "Alabama": 7, "Alaska": 1, "Arizona": 6, "Arkansas": 4, "California": 52,
        "Colorado": 6, "Connecticut": 6, "Delaware": 1, "District of Columbia": None,
        "Florida": 23, "Georgia": 11, "Hawaii": 2, "Idaho": 2, "Illinois": 20,
        "Indiana": 10, "Iowa": 5, "Kansas": 4, "Kentucky": 6, "Louisiana": 7,
        "Maine": 2, "Maryland": 8, "Massachusetts": 10, "Michigan": 16, "Minnesota": 8,
        "Mississippi": 5, "Missouri": 9, "Montana": 1, "Nebraska": 3, "Nevada": 2,
        "New Hampshire": 2, "New Jersey": 13, "New Mexico": 3, "New York": 31,
        "North Carolina": 12, "North Dakota": 1, "Ohio": 19, "Oklahoma": 6, "Oregon": 5,
        "Pennsylvania": 21, "Rhode Island": 2, "South Carolina": 6, "South Dakota": 1,
        "Tennessee": 9, "Texas": 30, "Utah": 3, "Vermont": 1, "Virginia": 11,
        "Washington": 9, "West Virginia": 3, "Wisconsin": 9, "Wyoming": 1,
    },
    2000: {
        "Alabama": 7, "Alaska": 1, "Arizona": 8, "Arkansas": 4, "California": 53,
        "Colorado": 7, "Connecticut": 5, "Delaware": 1, "District of Columbia": None,
        "Florida": 25, "Georgia": 13, "Hawaii": 2, "Idaho": 2, "Illinois": 19,
        "Indiana": 9, "Iowa": 5, "Kansas": 4, "Kentucky": 6, "Louisiana": 7, "Maine": 2,
        "Maryland": 8, "Massachusetts": 10, "Michigan": 15, "Minnesota": 8,
        "Mississippi": 4, "Missouri": 9, "Montana": 1, "Nebraska": 3, "Nevada": 3,
        "New Hampshire": 2, "New Jersey": 13, "New Mexico": 3, "New York": 29,
        "North Carolina": 13, "North Dakota": 1, "Ohio": 18, "Oklahoma": 5, "Oregon": 5,
        "Pennsylvania": 19, "Rhode Island": 2, "South Carolina": 6, "South Dakota": 1,
        "Tennessee": 9, "Texas": 32, "Utah": 3, "Vermont": 1, "Virginia": 11,
        "Washington": 9, "West Virginia": 3, "Wisconsin": 8, "Wyoming": 1,
    },
    2010: {
        "Alabama": 7, "Alaska": 1, "Arizona": 9, "Arkansas": 4, "California": 53,
        "Colorado": 7, "Connecticut": 5, "Delaware": 1, "District of Columbia": None,
        "Florida": 27, "Georgia": 14, "Hawaii": 2, "Idaho": 2, "Illinois": 18,
        "Indiana": 9, "Iowa": 4, "Kansas": 4, "Kentucky": 6, "Louisiana": 6, "Maine": 2,
        "Maryland": 8, "Massachusetts": 9, "Michigan": 14, "Minnesota": 8,
        "Mississippi": 4, "Missouri": 8, "Montana": 1, "Nebraska": 3, "Nevada": 4,
        "New Hampshire": 2, "New Jersey": 12, "New Mexico": 3, "New York": 27,
        "North Carolina": 13, "North Dakota": 1, "Ohio": 16, "Oklahoma": 5, "Oregon": 5,
        "Pennsylvania": 18, "Rhode Island": 2, "South Carolina": 7, "South Dakota": 1,
        "Tennessee": 9, "Texas": 36, "Utah": 4, "Vermont": 1, "Virginia": 11,
        "Washington": 10, "West Virginia": 3, "Wisconsin": 8, "Wyoming": 1,
    },
    2020: {
        "Alabama": 7, "Alaska": 1, "Arizona": 9, "Arkansas": 4, "California": 52,
        "Colorado": 8, "Connecticut": 5, "Delaware": 1, "District of Columbia": None,
        "Florida": 28, "Georgia": 14, "Hawaii": 2, "Idaho": 2, "Illinois": 17,
        "Indiana": 9, "Iowa": 4, "Kansas": 4, "Kentucky": 6, "Louisiana": 6, "Maine": 2,
        "Maryland": 8, "Massachusetts": 9, "Michigan": 13, "Minnesota": 8,
        "Mississippi": 4, "Missouri": 8, "Montana": 2, "Nebraska": 3, "Nevada": 4,
        "New Hampshire": 2, "New Jersey": 12, "New Mexico": 3, "New York": 26,
        "North Carolina": 14, "North Dakota": 1, "Ohio": 15, "Oklahoma": 5, "Oregon": 6,
        "Pennsylvania": 17, "Rhode Island": 2, "South Carolina": 7, "South Dakota": 1,
        "Tennessee": 9, "Texas": 38, "Utah": 4, "Vermont": 1, "Virginia": 11,
        "Washington": 10, "West Virginia": 2, "Wisconsin": 8, "Wyoming": 1,
    },
}

#: The censuses this module covers, derived rather than restated.
CURATED_CENSUS_YEARS: tuple[int, ...] = tuple(sorted(SEATS_BY_CENSUS))

#: Every jurisdiction each census carries. Derived, so it cannot drift from the data.
CURATED_JURISDICTIONS: frozenset[str] = frozenset(
    state for by_state in SEATS_BY_CENSUS.values() for state in by_state
)
