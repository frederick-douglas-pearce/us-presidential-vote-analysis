"""The ``pv_source`` reference table — the SSOT for per-source PV attributes (D017).

The union of the two PV sources keeps **both** rows for every overlapping
``(year, state, candidate)`` (D017 §1, encoded in :mod:`usvote.pv.schema` by putting
``source`` in the natural key). Which source *wins* where both exist, whether a source
may be redistributed, and under what license are **per-source** attributes — one fact
per source, not per fact row — so they live in a tiny reference table keyed on
``source``, not as columns on ``dwh.pv_votes``. Storing them here (data, not code) is
what keeps D017's forward-compat guarantee literally true: a UCSB redistribution grant,
or adding a third source, is a **one-row edit** with no view or DDL change.

This module is also the home of the two **source-name literals** ``SOURCE_MIT`` /
``SOURCE_UCSB``. They were defined inside ``usvote.mit.transform`` / ``usvote.ucsb.
transform``; they move here so ``usvote.pv`` (which must key ``pv_source`` and the
resolution views on them) can name them without importing a source subpackage — that
would invert the D006 ``source -> pv`` dependency. Both transforms now import them from
here (the allowed direction), so the string ``"UCSB"`` has exactly one definition.

Consumed by :mod:`usvote.pv.views` (``precedence_rank`` drives ``pv_preferred``'s
``DISTINCT ON``; ``redistributable`` defines ``pv_redistributable``) and loaded by
:func:`usvote.pv.load.load_pv_source`.
"""

from __future__ import annotations

from collections.abc import Collection

import pandas as pd

from usvote.pv.schema import PV_SCHEMA

#: Source-name literals — the SSOT both source transforms stamp on their rows and the
#: ``pv_source`` reference table keys on. ``usvote.mit.transform`` and
#: ``usvote.ucsb.transform`` import these from here (direction is always ``source ->
#: pv``), so a source's ``"MIT"``/``"UCSB"`` tag and this table can never disagree.
SOURCE_MIT = "MIT"
SOURCE_UCSB = "UCSB"

#: The first election MIT's file covers — the floor of the **redistributable** popular
#: vote. Provenance is the filename itself: ``1976-2024-president.csv``.
#:
#: **It is a constant on purpose, and the reason is subtle** (#139 / D048). The public
#: snapshot must guarantee no popular-vote aggregate appears below this year, and the
#: obvious spelling of that guard — "the lowest year that has any PV" — is *vacuous
#: under exactly the failure it exists to catch*: repoint the snapshot build at
#: ``ec_pv_preferred`` and pre-1976 suddenly has (UCSB) PV, so the observed floor slides
#: to 1824 and the assert passes over everything it was meant to stop. An external
#: invariant cannot slide.
#:
#: Its home is here rather than in :mod:`usvote.snapshot` because #102/E8-S8 inherits
#: the same guard for ``pv_share`` / ``hybrid_score``, and an inheritance that is a
#: re-typed ``1976`` is not an inheritance. Deliberately **not** a ``year_min`` column
#: on the ``pv_source`` table: that implies a per-source generality — the right upgrade
#: if a second *redistributable* source ever predates 1976 — which nothing needs yet.
#:
#: Cross-checked one-directionally against the loaded data (see
#: :func:`assert_mit_year_floor`): a MIT frame starting *earlier* than this means the
#: constant is stale and must fail loud; starting *later* is an ordinary scoped build.
MIT_PV_YEAR_MIN = 1976

#: The most recent election MIT's file covers — the **high-water mark** of the
#: redistributable popular vote, and the twin of :data:`MIT_PV_YEAR_MIN`. Provenance is
#: the same filename: ``1976-2024-president.csv``.
#:
#: **Why an explicit constant rather than an observed maximum** (#177). The failure this
#: guards is a MIT file that silently stops reaching the newest election it used to
#: reach — one malformed or truncated CSV does it. Every *observed* spelling of that
#: check is vacuous under exactly that failure: an observed max slides down with the
#: truncation, and "MIT reaches the spine frontier" (``max(ec_ingest_years())``) is
#: false for every legitimate mid-cycle build, which is the same circularity the #167
#: overlap gate removed from the other side — letting the data define the boundary meant
#: to detect the data being wrong. Only something that *remembers* 2024 can decide it,
#: and an explicit constant is the cheapest such memory.
#:
#: **Bumping it each cycle is a documented maintenance step, not one the code forces**,
#: and the gap is worth knowing: the ``>`` branch below fires only once the *newer* CSV
#: is in place, so bumping ``LATEST_ELECTION_YEAR`` for the spine while leaving a stale
#: CSV here passes silently. Nothing in this repo can tell "MIT has not published yet"
#: from "MIT published and nobody downloaded it", and the check that would look
#: obvious — requiring this to reach ``LATEST_ELECTION_YEAR`` — is false for every
#: legitimate mid-cycle build. D052 states the limit in full.
#:
#: Cross-checked by :func:`usvote.mit.validate.assert_mit_year_coverage`, and — unlike
#: the floor — as an **equality**, raising in both directions. The asymmetry is not an
#: oversight: a scoped build only ever *lowers* the observed maximum, so there is no
#: benign "ordinary scoped build" reading of ``max(election) > MIT_PV_YEAR_MAX`` the
#: way there is for ``min(observed) > MIT_PV_YEAR_MIN``. The two spellings differ on
#: purpose: the coverage guard screens non-election years out before taking its
#: maximum, while the floor guard below reads the raw minimum. Above means MIT
#: published a newer cycle and this constant is stale — every guard keyed on it is now
#: silently one election too weak — and below is the truncation itself.
MIT_PV_YEAR_MAX = 2024

#: The warehouse schema and reference-table name. ``pv_source`` co-locates in the same
#: schema as ``pv_votes`` and the EC spine (D021), and the resolution views join the two
#: on ``source`` **within one schema** — so this is *aliased* to
#: :data:`usvote.pv.schema.PV_SCHEMA` rather than a second ``"dwh"`` literal, and the
#: view's ``JOIN {schema}.pv_source`` and this loader's target can never drift apart.
PV_SOURCE_SCHEMA = PV_SCHEMA
PV_SOURCE_TABLE = "pv_source"

#: The ``pv_source`` columns, in load order. ``precedence_rank`` orders
#: ``pv_preferred``'s ``DISTINCT ON`` (lower rank wins); ``redistributable`` defines the
#: public API surface (``pv_redistributable``); ``license`` records provenance.
PV_SOURCE_COLUMNS: tuple[str, ...] = (
    "source",
    "precedence_rank",
    "redistributable",
    "license",
)

_MIT_LICENSE = "CC0-1.0"
_UCSB_LICENSE = (
    "UCSB American Presidency Project — analysis-only; redistribution requires "
    "permission (D022)"
)

#: The per-source attribute rows — **data, not code** (D017). ``precedence_rank`` = 1
#: for MIT means MIT wins the 1976–2024 overlap; UCSB = 2 supplies everything earlier
#: (and loses the overlap). ``redistributable`` is ``True`` only for MIT (CC0, D016);
#: UCSB is analysis-only pending a license answer (D022), so it never reaches the
#: ``pv_redistributable`` public surface. Adding a source (e.g. ICPSR) is one more row
#: here — no view or DDL change (that is the whole point of a reference table).
PV_SOURCE_ROWS: tuple[dict[str, object], ...] = (
    {
        "source": SOURCE_MIT,
        "precedence_rank": 1,
        "redistributable": True,
        "license": _MIT_LICENSE,
    },
    {
        "source": SOURCE_UCSB,
        "precedence_rank": 2,
        "redistributable": False,
        "license": _UCSB_LICENSE,
    },
)


class PVSourceError(RuntimeError):
    """Raised when the ``pv_source`` reference frame is off its shape/invariants.

    The reference-table analogue of :class:`usvote.pv.schema.PVShapeError`; fires at
    the :func:`usvote.pv.load.load_pv_source` write boundary so a malformed seed (wrong
    columns, a null attribute, or a duplicated ``precedence_rank`` that would make
    ``pv_preferred``'s tie-break non-deterministic) fails loudly rather than silently
    corrupting the resolved series.
    """


def assert_mit_year_floor(
    observed_years: Collection[int],
    *,
    error_cls: type[Exception] = PVSourceError,
    caller: str = "assert_mit_year_floor",
) -> None:
    """Assert no observed redistributable-PV year falls below :data:`MIT_PV_YEAR_MIN`.

    The cross-check that keeps the constant honest without letting it slide. It is
    **one-directional by design**:

    - ``min(observed) < MIT_PV_YEAR_MIN`` → **raise.** MIT has published earlier years,
      so the constant is stale and every guard built on it is now silently too weak.
      Forcing a deliberate constant update is the whole point.
    - ``min(observed) > MIT_PV_YEAR_MIN`` → **pass.** That is an ordinary scoped build
      (a partial load, a year-filtered run). The guard is merely stricter than it needs
      to be there, which costs nothing.

    An *equality* check would look tighter and be worse: it would fail every scoped
    build, for a reason unrelated to the invariant.

    An empty ``observed_years`` passes — "no redistributable PV at all" is a different
    failure, and the callers that care about it say so themselves with a clearer message
    (:func:`usvote.snapshot.build_snapshot`'s empty-PV guard) rather than having it
    reported here as a year-floor problem.
    """
    years = [int(y) for y in observed_years]
    if not years:
        return
    floor = min(years)
    if floor < MIT_PV_YEAR_MIN:
        raise error_cls(
            f"{caller}: redistributable popular-vote data was found for {floor}, "
            f"earlier than MIT_PV_YEAR_MIN={MIT_PV_YEAR_MIN}. Either {SOURCE_MIT} now "
            "publishes earlier elections — in which case update the constant in "
            "usvote/pv/source.py deliberately, and re-read every guard that keys on it "
            "— or a non-redistributable source has leaked into a redistributable view."
        )


def build_pv_source_frame() -> pd.DataFrame:
    """Return :data:`PV_SOURCE_ROWS` as a frame on :data:`PV_SOURCE_COLUMNS`."""
    return pd.DataFrame(list(PV_SOURCE_ROWS))[list(PV_SOURCE_COLUMNS)]


def build_pv_source_column_defs() -> list[tuple[str, ...]]:
    """Return the ``pv_source`` column definitions as :meth:`DBC.create_table` tuples.

    Unlike :func:`usvote.pv.schema.build_pv_column_defs` this takes no ``schema`` — the
    table has **no FK** (it is the reference side that ``pv_votes`` joins *to*), so
    nothing embeds the schema name. ``source`` is the PK; ``precedence_rank`` is
    ``UNIQUE`` so the ``pv_preferred`` ``DISTINCT ON ... ORDER BY precedence_rank``
    tie-break is deterministic (two sources sharing a rank would resolve arbitrarily).
    """
    return [
        ("source", "varchar", "primary key"),
        ("precedence_rank", "smallint", "not null", "unique"),
        ("redistributable", "boolean", "not null"),
        ("license", "varchar", "not null"),
    ]


def assert_pv_source_shape(
    df: pd.DataFrame, *, error_cls: type[Exception] = PVSourceError
) -> None:
    """Assert ``df`` is a well-formed ``pv_source`` reference frame.

    Checks the columns are exactly :data:`PV_SOURCE_COLUMNS` in order, that no value is
    null, and that ``precedence_rank`` is unique (the DB ``UNIQUE`` would catch the last
    at insert, but a duplicate is a resolution bug worth failing on before any DDL).
    """
    if list(df.columns) != list(PV_SOURCE_COLUMNS):
        raise error_cls(
            f"pv_source columns {list(df.columns)} != {list(PV_SOURCE_COLUMNS)}"
        )
    if df.isna().any().any():
        raise error_cls("pv_source has null value(s); every attribute is required")
    dup_ranks = df.loc[df["precedence_rank"].duplicated(keep=False), "precedence_rank"]
    if not dup_ranks.empty:
        raise error_cls(
            f"pv_source precedence_rank must be unique — duplicates "
            f"{sorted(dup_ranks.unique().tolist())} make pv_preferred non-deterministic"
        )
