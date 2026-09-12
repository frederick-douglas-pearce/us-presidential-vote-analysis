"""Census record shape + target-table DDL + boundary shape guard (#181).

The census counterpart of :mod:`usvote.pv.schema`, and it exists for the same reason
that module does rather than living in ``transform.py`` or ``load.py``: the enums here
have **two callers that must not depend on each other**. :mod:`usvote.census.transform`
*assigns* ``series`` and ``basis``; :mod:`usvote.census.load` builds the ``CHECK``
constraints *from* them. Parking the tuples in the transform would point the DDL builder
at a pandas module; parking them in the loader would drag psycopg2 into the transform's
import chain. That is the :mod:`usvote.count_status` / :mod:`usvote.pv.status` pattern,
applied inside a subpackage.

**This is not a PV contract.** Census is not a popular-vote source: nothing here
conforms to D018, nothing is written to ``dwh.pv_votes``, and this table takes no part
in the D017 resolution views. The shape is borrowed; the schema is its own.

**On the ``redistributable`` column, and the D017 tension it sits in.** D017
deliberately moved ``redistributable``/license *off* the per-row PV fact and into the
``pv_source`` reference table, on the reasoning that a per-source constant should not
be repeated per row (see :mod:`usvote.pv.schema`'s scope-boundary note). This table
keeps it per-row anyway, which is a **conscious departure, not an oversight**: #181's
acceptance criteria require the S1 licensing verdict to be carried as data rather than
as a comment (the D014 discipline), and building a ``census_source`` reference table
for a single source whose flag is uniformly ``true`` would over-engineer in the other
direction. Recorded in D059 so the next reader meets the reasoning rather than the
inconsistency.

**On the ``note`` column, whose constraint is the opposite of the PV one.**
``pv_state_status.note`` holds UCSB-derived prose and must be kept *off* the public
surface (D022/D030). Census ``note`` is public-domain or repo-authored provenance, so it
**may** reach the public surface. Stated explicitly because the pattern-match from the
PV note points the wrong way.
"""

from __future__ import annotations

import pandas as pd

#: The warehouse schema. Census co-locates with the EC spine exactly as PV does (D021),
#: and for the same reason: the ``state`` FK targets ``{schema}.state``, so this is not
#: an independent location — the EC dimensions must already exist.
CENSUS_SCHEMA = "dwh"

#: The target table.
CENSUS_TABLE = "census_population"

#: The single source token, carried per row as provenance (D014).
SOURCE_CENSUS_BUREAU = "US_CENSUS_BUREAU"

#: The population series. **One value today, and the column exists anyway** — it is the
#: seam a second series would enter through, and it stops a resident figure being read
#: as a generic "population" in the eras where the two genuinely differ (the
#: three-fifths clause pre-1868; "Indians not taxed" excluded 1790-1930, ending at the
#: 1940 census; modern overseas-federal-personnel movements). Admitting a second series
#: later is then a data addition rather than a schema migration.
SERIES_RESIDENT = "resident"
SERIES_VALUES: tuple[str, ...] = (SERIES_RESIDENT,)

#: The boundary basis of a figure — which state borders it was tabulated on.
#:
#: ``present_day`` is what the published source gives: ``tabs15-65.xlsx`` reports every
#: census on **modern** state footprints. ``as_enumerated`` is a figure this project has
#: restated onto the borders in force at that census.
#:
#: The label is the whole point (S1 §4/§10): without it a present-day-footprint Virginia
#: is indistinguishable from an as-enumerated one, and the difference is 12.7%-21.3%
#: across ten elections — a plausible wrong number rather than a load error. Most rows
#: are ``present_day`` and that is an honest claim, not a weak one: it says "this is the
#: published figure and we have not asserted it equals the as-enumerated one". The
#: fifty-state residual sweep is #208.
BASIS_PRESENT_DAY = "present_day"
BASIS_AS_ENUMERATED = "as_enumerated"
BASIS_VALUES: tuple[str, ...] = (BASIS_PRESENT_DAY, BASIS_AS_ENUMERATED)

#: The record shape, in load order.
CENSUS_COLUMNS: tuple[str, ...] = (
    "source",
    "census_year",
    "state",
    "series",
    "basis",
    "population",
    "vintage",
    "source_file",
    "redistributable",
    "note",
)

#: The natural key. ``basis`` is deliberately **not** part of it: one row per
#: ``(source, census_year, state, series)``, with the correction applied in place and
#: the basis recorded as a label.
#:
#: Putting ``basis`` in the key was considered and rejected at design review. It would
#: let the published and corrected Virginia rows coexist, but it recreates the D017
#: fan-out hazard for population — every consumer joining this table to the EC spine
#: (#184 first) would have to remember to filter ``basis`` or silently double-count
#: Virginia. Patching in place with a provenance-carrying constant and a
#: ``docs/corrections.md`` row is also what this repo already does for every historical
#: anomaly; the published figure stays recoverable from the correction constant.
CENSUS_NATURAL_KEY: tuple[str, ...] = ("source", "census_year", "state", "series")

#: Columns that must never be null. ``population`` is **not** among them: a state/census
#: with no published figure loads as NULL with provenance, never a zero or an
#: interpolation (D005).
REQUIRED_NON_NULL: tuple[str, ...] = (
    "source",
    "census_year",
    "state",
    "series",
    "basis",
    "vintage",
    "source_file",
    "redistributable",
)


class CensusShapeError(RuntimeError):
    """Raised when a census frame is not on the shape the loader expects."""


def build_series_check(column: str = "series") -> str:
    """Return the ``series`` CHECK built from :data:`SERIES_VALUES`."""
    values = ", ".join(f"'{value}'" for value in SERIES_VALUES)
    return f"CHECK ({column} IN ({values}))"


def build_basis_check(column: str = "basis") -> str:
    """Return the ``basis`` CHECK built from :data:`BASIS_VALUES`."""
    values = ", ".join(f"'{value}'" for value in BASIS_VALUES)
    return f"CHECK ({column} IN ({values}))"


def build_census_column_defs(
    schema: str = CENSUS_SCHEMA,
) -> list[tuple[str, ...]]:
    """Return the ``census_population`` column defs as ``DBC.create_table`` tuples.

    A function rather than a constant because the ``state`` FK embeds ``schema``, the
    same reason :func:`usvote.pv.schema.build_pv_column_defs` is one.

    **``population`` is ``integer``, never ``smallint``.** The EC fact types its
    electoral-vote measures ``smallint`` because an electoral vote count fits in one;
    copying that reflex here overflows at 32,767 against state populations that reach
    ~39 million. ``integer`` (int32, ~2.1 billion) is ample at state grain and is the
    one column type in this table that is a correctness matter rather than a style one.
    """
    return [
        ("population_id", "integer", "generated always as identity", "primary key"),
        ("source", "varchar", "not null"),
        ("census_year", "smallint", "not null"),
        ("state", "varchar", "not null", f"REFERENCES {schema}.state"),
        ("series", "varchar", "not null", build_series_check()),
        ("basis", "varchar", "not null", build_basis_check()),
        ("population", "integer"),
        ("vintage", "varchar", "not null"),
        ("source_file", "varchar", "not null"),
        ("redistributable", "boolean", "not null"),
        ("note", "text"),
        (
            "CONSTRAINT",
            f"{CENSUS_TABLE}_natural_key",
            "UNIQUE",
            f"({', '.join(CENSUS_NATURAL_KEY)})",
        ),
    ]


def assert_census_shape(
    df: pd.DataFrame, *, error_cls: type[Exception] = CensusShapeError
) -> None:
    """Assert ``df`` is on the census shape before the loader inserts it.

    The single write-boundary guard: wrong column set or order, a null in a required
    column, or a duplicated natural key fails loudly here rather than as an opaque
    psycopg2 error mid-insert.

    ``population`` is checked for *nullable* integer dtype rather than plain ``int``:
    the column carries genuine NULLs (D005), so pandas would widen a plain ``int64``
    column to ``float64`` the moment one appears — silently turning 39,538,223 into a
    float and the NULLs into ``NaN``. Requiring a nullable integer dtype is what keeps
    "no published figure" and "zero" distinguishable all the way to the database.
    """
    if list(df.columns) != list(CENSUS_COLUMNS):
        raise error_cls(
            f"Census frame columns {list(df.columns)} != census shape "
            f"{list(CENSUS_COLUMNS)}"
        )
    for col in REQUIRED_NON_NULL:
        if df[col].isna().any():
            raise error_cls(
                f"Census frame column {col!r} has null value(s) (required non-null)"
            )
    if not pd.api.types.is_integer_dtype(df["population"]):
        raise error_cls(
            f"Census frame column 'population' must be a nullable integer dtype "
            f"(e.g. Int64), got {df['population'].dtype}. A float dtype means the "
            f"NULLs became NaN and the counts became floats."
        )
    duplicated = df.duplicated(subset=list(CENSUS_NATURAL_KEY))
    if duplicated.any():
        offenders = df.loc[duplicated, list(CENSUS_NATURAL_KEY)].head(5)
        raise error_cls(
            f"Census frame has {int(duplicated.sum())} duplicate natural keys "
            f"{CENSUS_NATURAL_KEY}; first few:\n{offenders}"
        )
