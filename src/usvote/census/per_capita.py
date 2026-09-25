"""Persons per electoral vote by ``(election_year, state)`` — the warehouse view (#184).

The derived series E10 exists to produce: how many people each of a state's electoral
votes stands for, for every participating ``(election_year, state)`` across the 51
elections 1824-2024. It is the denominator side of the apportionment-drift question the
"Counted, Not Assumed" series asks, and it is a *warehouse* surface only — the public
API exposure is **#245**, deliberately a separate story (D064).

**Module placement, and the guard that settled it.** This follows the *shape* of
:mod:`usvote.join` and :mod:`usvote.hybrid` — the dual-expression family, where a SQL
builder drives the live view and a pure-pandas builder is the oracle a differential
integration test re-runs against it — but it lives **under** ``usvote/census/`` rather
than beside them at the top level. #184 planned the opposite, on cohesion grounds, and
implementation found the top-level placement is not actually available: a view over
``dwh.election_population`` must name that table and its column contract, both of which
are census's (:mod:`usvote.census.conform`), and
``test_no_top_level_module_imports_a_source_subpackage`` forbids exactly that import
from every top-level module but the two composition roots (D006/D015). The alternatives
were to copy the contract into a second place, which is the drift this repo refuses
everywhere else, or to exempt a module from a layering invariant to keep a filename.
The design gate had already ruled census placement **permitted** — the layering guard
that keeps EC-star-schema knowledge out of the source subpackages is a literal scan for
``dwh.votes``, and nothing here names it: the allotment arrives as a *column* on
``election_population``, which is what makes this legal here at all — so this is that
ruling's own fallback rather than a new decision.

:func:`usvote.warehouse.rebuild_views` still composes it beside the join and hybrid
builders; a composition root sits above every source and imports from all of them by
design (D027).

**What the view is over.** :data:`~usvote.census.conform.ELECTION_POPULATION_TABLE`, the
frame :mod:`usvote.census.conform` assembles behind its guards and #184 persists. It is
deliberately **not** a join of ``dwh.census_population`` against the EC fact: that would
be a second expression of the governing-census calendar and of the Virginia boundary
restatement, and the second of those is not recoverable from the warehouse at all (D059
keeps ``basis`` out of the census natural key). See that table's own note.

**The ratio is the only thing this module computes**, which is what keeps the SQL/oracle
pair small enough to trust — and it still has two ways to go quietly wrong, both
answered in the SQL itself:

* **integer division.** Postgres integer-divides two integers, so
  ``population / total_electoral_votes`` would return a floor-divided count rather than
  a ratio. Every numerator is cast to ``double precision`` first, exactly as
  :func:`usvote.hybrid.build_hybrid_candidate_sql` does and for the same reason.
* **a zero denominator.** Fourteen ``(election_year, state)`` cells hold an allotment of
  **zero** — eleven states in 1864 and three in 1868, whose electoral votes were
  withheld under the 1864 Joint Resolution and the 1868 non-readmission; #183 catalogued
  them as ``electoral_votes_withheld`` in ``docs/corrections.md`` with statutory
  citations. Postgres **raises** ``division by zero`` on those rows rather than yielding
  infinity — and, measured rather than assumed, ``CREATE VIEW`` over such a row
  *succeeds* while the ``SELECT`` is what fails. An unguarded view therefore builds
  green and breaks at read time, in the snapshot build or in any consumer's query.
  ``NULLIF`` is what makes the ratio NULL instead.

**What enforces the two guarantees, stated precisely — because the obvious reading is
wrong.** :func:`assert_no_fan_out` and :func:`assert_ratio_null_only_where_explained`
below are **offline oracles for the test suite, not preconditions this builder runs**,
and that is deliberate rather than an omission (#184 review; the human's call, recorded
in D064(c)). On the live view both properties hold *structurally*: the view is a
projection of a table carrying ``UNIQUE (election_year, state)``, so a fan-out is not
expressible; and the ratio's NULL set is exactly ``population IS NULL OR
total_electoral_votes = 0`` by SQL's own NULL semantics plus ``NULLIF``, so
"null only where the row explains it" is true by construction in both directions.

That is the opposite of the cases :func:`usvote.join.create_ec_pv_views` and
:func:`usvote.hybrid.create_hybrid_views` run preconditions for —
``assert_db_pv_matches_ec`` and ``assert_no_winner_tie`` guard *data-dependent* facts
that genuinely can fail and cannot be expressed in a view. Wiring these two in would
cost a full 2,204-row read on every ``rebuild_views`` to check something the schema has
already made impossible. Where they earn their place is the dual-expression oracle: a
hand-built frame in a test, where nothing enforces the key.

**Two kinds of NULL ratio, and neither carries a status column.** A NULL here means
either no governing-census population (one cell today: ``(1848, Texas)``, the Republic
of Texas being unenumerated by the US in 1840) or a zero allotment (the fourteen). Both
causes are readable **off the operands already in the row** — ``coverage`` says which
population case a row is in, and ``total_electoral_votes`` is right there — so a status
column would be derived from two of its own neighbours and carry no information beyond
them. That was a deliberate call at the #184 plan gate, against a proposed
``per_capita_status`` vocabulary.
"""

from __future__ import annotations

import pandas as pd

from usvote.census.conform import (
    ELECTION_POPULATION_COLUMNS,
    ELECTION_POPULATION_TABLE,
)
from usvote.census.schema import CENSUS_SCHEMA
from usvote.db import DBC

#: The materialized view. One per warehouse — there is no ``preferred`` /
#: ``redistributable`` split here, because there is only one population source and it is
#: public domain (17 U.S.C. §105), so the D016/D030 two-surface split the PV views carry
#: has nothing to separate.
PER_CAPITA_VIEW = "election_per_capita"

#: The grain the view is unique on — inherited from
#: :data:`~usvote.census.conform.ELECTION_POPULATION_NATURAL_KEY`, which the table's own
#: UNIQUE constraint already enforces. :func:`assert_no_fan_out` re-checks it on the
#: frame because the oracle is built by hand, where nothing enforces it.
PER_CAPITA_GRAIN: tuple[str, ...] = ("election_year", "state")

#: The ratio column: the state's governing-census population divided by the electoral
#: votes it was appointed. **Appointed**, not cast or counted — the question is what one
#: of a state's electoral votes was *worth*, which is a property of the apportionment,
#: so the denominator is the allotment the EC fact records
#: (``total_electoral_votes``; D041's appointed measure).
PER_CAPITA_COLUMN = "persons_per_electoral_vote"

#: The view's column order: every column of the table it reads, in that order, then the
#: ratio. **Append, never insert** — ``CREATE OR REPLACE VIEW`` can only add trailing
#: columns, so a mid-list insert makes :func:`usvote.warehouse.rebuild_views` fail
#: against any warehouse whose view already exists (the rule
#: :data:`usvote.join.EC_PV_COLUMNS` carries, one view over).
#:
#: This tuple *is* built from
#: :data:`~usvote.census.conform.ELECTION_POPULATION_COLUMNS` below — so **the pin must
#: not be**. ``tests/unit/test_census_per_capita.py`` spells the whole order out as a
#: hand-written literal, because an assert comparing this tuple against the constant it
#: is built from is circular: it passes under a reorder of either.
PER_CAPITA_COLUMNS: tuple[str, ...] = (
    *ELECTION_POPULATION_COLUMNS,
    PER_CAPITA_COLUMN,
)


class PerCapitaError(RuntimeError):
    """Raised when the per-capita series violates a #184 invariant."""


# --- SQL builder (drives the live view) -------------------------------------


def _relation_exists(dbc: DBC, schema: str, name: str) -> bool:
    """Return whether ``schema.name`` exists, via ``to_regclass`` (NULL when absent).

    The same cheap non-raising probe :func:`usvote.join._relation_exists` uses, kept
    local for the same reason it is: so this module does not reach into another one's
    private helper.
    """
    got = dbc.select_query_to_df(f"SELECT to_regclass('{schema}.{name}') AS relation")
    return got["relation"].iloc[0] is not None


def build_per_capita_sql(*, schema: str = CENSUS_SCHEMA) -> str:
    """Return the SELECT behind :data:`PER_CAPITA_VIEW`, emitting
    :data:`PER_CAPITA_COLUMNS`.

    The whole derivation is one ratio, and both halves of it are load-bearing
    (the module docstring says why each is): the numerator is cast to ``double
    precision`` so Postgres does not integer-divide, and the denominator goes through
    ``NULLIF`` so a zero allotment yields NULL instead of raising at read time.

    A NULL ``population`` propagates to a NULL ratio on its own, with no second guard —
    that is SQL's own NULL semantics and the pandas oracle matches it.
    """
    carried = ", ".join(ELECTION_POPULATION_COLUMNS)
    ratio = (
        f"population::double precision / NULLIF(total_electoral_votes, 0)"
        f" AS {PER_CAPITA_COLUMN}"
    )
    return f"SELECT {carried}, {ratio} FROM {schema}.{ELECTION_POPULATION_TABLE}"


def create_per_capita_view(
    dbc: DBC,
    *,
    schema: str = CENSUS_SCHEMA,
    replace: bool = True,
    close: bool = False,
) -> bool:
    """Create :data:`PER_CAPITA_VIEW`, or **skip** when its input table is absent.

    Returns whether the view was created, so a caller can report the skip rather than
    infer it.

    **Skip-if-absent, not raise — and the asymmetry with the PV views is the point.**
    :func:`usvote.join.create_ec_pv_views` raises when its input is missing because the
    PV sources are **not optional**: every warehouse has them, so a missing resolved
    view is a broken build. The census source *is* optional (``python -m usvote all``
    auto-detects ``USVOTE_CENSUS_CORPUS_DIR`` and skips census with a NOTICE when it is
    unset), so on a public EC + MIT clone — which is every clone without the private
    census corpus — ``dwh.election_population`` legitimately does not exist. Raising
    here would crash that build, and :func:`usvote.warehouse.rebuild_views`' contract is
    to make the views consistent with *whatever facts are present*.

    **The #183 argument for calling a guard unconditionally does not transfer**, and the
    discriminator is what the thing reads. ``assert_seats_reconcile`` was moved out of
    the census branch precisely because it reads always-present inputs — the spine and a
    curated in-repo constant — so gating it made it fire only when a corpus happened to
    exist. A *view* reads a relation that exists only when census loaded, and one over
    an absent table is not a weaker guarantee, it is an error.

    ``replace`` defaults to ``True`` (``CREATE OR REPLACE VIEW`` — idempotent and
    non-destructive), matching the other view builders.
    """
    if not _relation_exists(dbc, schema, ELECTION_POPULATION_TABLE):
        if close:
            dbc.close_connection()
        return False
    dbc.create_view(
        schema, PER_CAPITA_VIEW, build_per_capita_sql(schema=schema), replace=replace
    )
    if close:
        dbc.close_connection()
    return True


# --- pure oracle (offline mirror of the live view) --------------------------


def build_per_capita_frame(election_population_df: pd.DataFrame) -> pd.DataFrame:
    """Pure-pandas mirror of :func:`build_per_capita_sql` — the oracle (D064).

    Takes the :data:`~usvote.census.conform.ELECTION_POPULATION_COLUMNS` frame and
    returns :data:`PER_CAPITA_COLUMNS`.

    **The zero mask is explicit and is not a matter of taste.** numpy divides
    ``x / 0`` to ``inf`` and ``0 / 0`` to ``nan``; SQL's ``NULLIF`` yields NULL. Only
    ``nan`` compares equal to a SQL NULL once both are read back into pandas, so an
    oracle that let the division run would disagree with the live view on exactly the
    fourteen zero-allotment cells the guard exists for — and would disagree by producing
    ``inf``, a number, where the view produces an absence.
    """
    frame = election_population_df.copy()
    population = pd.to_numeric(frame["population"], errors="raise").astype("Float64")
    allotment = pd.to_numeric(
        frame["total_electoral_votes"], errors="raise"
    ).astype("Float64")
    ratio = population / allotment.where(allotment != 0)
    frame[PER_CAPITA_COLUMN] = ratio.astype("Float64")
    return (
        frame[list(PER_CAPITA_COLUMNS)]
        .sort_values(list(PER_CAPITA_GRAIN), kind="stable")
        .reset_index(drop=True)
    )


def read_per_capita(dbc: DBC, *, schema: str = CENSUS_SCHEMA) -> pd.DataFrame:
    """Read :data:`PER_CAPITA_VIEW` back, ordered on :data:`PER_CAPITA_GRAIN`.

    The read side of the differential integration test, and the one place the ORDER BY
    is written, so the live frame and the oracle are comparable row-for-row without the
    test re-deriving a sort the view does not guarantee.
    """
    order = ", ".join(PER_CAPITA_GRAIN)
    return dbc.select_query_to_df(
        f"SELECT * FROM {schema}.{PER_CAPITA_VIEW} ORDER BY {order}"
    )


# --- guards -----------------------------------------------------------------


def assert_no_fan_out(
    frame: pd.DataFrame, *, error_cls: type[Exception] = PerCapitaError
) -> None:
    """Assert one row per ``(election_year, state)`` — the acceptance criterion's own
    fan-out guard.

    The view is a projection of a table whose UNIQUE constraint already enforces this,
    so against the live view it is a contract check rather than a live tripwire. Against
    the **oracle** it is neither: that frame is built by hand from whatever a caller
    passes, and a duplicated key there is how a test would silently compare a fanned-out
    frame against a clean view and call them equal.
    """
    duplicated = frame.duplicated(list(PER_CAPITA_GRAIN), keep=False)
    if duplicated.any():
        offenders = frame.loc[duplicated, list(PER_CAPITA_GRAIN)].values.tolist()
        raise error_cls(
            f"per-capita series fanned out (>1 row per {list(PER_CAPITA_GRAIN)}): "
            f"{offenders[:5]}"
        )


def assert_ratio_null_only_where_explained(
    frame: pd.DataFrame, *, error_cls: type[Exception] = PerCapitaError
) -> None:
    """Assert every NULL ratio is explained by the row it sits in (D005, AC-3).

    The acceptance criterion says a state with no computable figure must read NULL
    rather than zero, **paired with enough metadata to say why**. There is no status
    column, so the property is: a NULL ratio must come with either a NULL population or
    a zero allotment, and a row with both a population and a non-zero allotment must
    have a ratio.

    **On the live view that holds by construction, so this is an oracle and not a
    precondition** — ``NULLIF`` plus SQL's NULL semantics make the ratio's NULL set
    exactly those two cases, in both directions. What it is *for* is a frame nothing
    else constrains: a hand-built fixture in a test, or a future second producer of the
    election-grain frame. :func:`create_per_capita_view` deliberately does not call it;
    the module docstring carries the argument.

    Both directions matter and they fail differently. A NULL nobody can explain is the
    honest-gap promise broken. A **non**-NULL where an operand is missing is worse: it
    means something synthesized a number, which is the D005 line itself.
    """
    population_missing = frame["population"].isna()
    allotment_zero = pd.to_numeric(frame["total_electoral_votes"], errors="raise") == 0
    explained = population_missing | allotment_zero
    ratio_missing = frame[PER_CAPITA_COLUMN].isna()

    unexplained = ratio_missing & ~explained
    if unexplained.any():
        offenders = frame.loc[
            unexplained, [*PER_CAPITA_GRAIN, "population", "total_electoral_votes"]
        ].head(5)
        raise error_cls(
            f"{int(unexplained.sum())} row(s) have a NULL persons-per-electoral-vote "
            f"that nothing in the row explains — the AC requires a null to be readable "
            f"off its own operands (a missing population, or a zero allotment). First "
            f"few:\n{offenders}"
        )

    fabricated = explained & ~ratio_missing
    if fabricated.any():
        offenders = frame.loc[
            fabricated, [*PER_CAPITA_GRAIN, "population", "total_electoral_votes"]
        ].head(5)
        raise error_cls(
            f"{int(fabricated.sum())} row(s) carry a persons-per-electoral-vote figure "
            f"with no population or a zero allotment to compute it from; a value that "
            f"is neither published nor derivable is synthesized, which D005 forbids. "
            f"First few:\n{offenders}"
        )
