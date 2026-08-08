"""Shared PV-absence roster contract + the two-way silent-drop guard (D024).

The sibling of :mod:`usvote.pv.schema`, and source-neutral for the same reason: the
``dwh.pv_state_status`` roster is a **shared** PV structure, not a UCSB one. Three
consumers are known — #37's DDL (whose ``pv_status`` CHECK is built from
:data:`PV_STATUS_VALUES`), the mechanical MIT roster backfill (D024 §6/§Rationale,
landed in #127 via :func:`build_popular_vote_roster`), and #38's re-run of the two-way
assert after it narrows candidates — so the contract lives here and the dependency runs
``source -> pv``, never ``pv -> ucsb`` or, worse, ``mit -> ucsb``.

A fourth consumer joined in #140: :mod:`usvote.pv.absences`, the in-repo pre-1976
absence catalog, which binds :func:`build_roster`'s ``absences`` argument. The
dependency runs ``absences -> status``, and **this module imports nothing from
``usvote``** — pandas (with its own numpy) and the stdlib only. Keeping it that way is
what lets the contract sit underneath every source *and* underneath the catalog that
consumes it.

**What the roster is (D024 §3/§6).** One row per ``(source, year, state)`` for *every*
state in that year's election, including ordinary ones. It is a **complete roster, not
an exceptions table** — that is precisely what makes absence detectable: an
exceptions-only table cannot distinguish "no exception" from "we never looked."

**What it is for (D024 §7).** :func:`assert_roster_covers_facts` is the project's guard
against the inner-join silent-drop hazard, which no sum validator can see: a state that
vanishes between parse and load takes its votes with it, and every total still
reconciles because the total went missing too. The third of its three checks —
every fact row's ``(year, state)`` is *in* the roster — is the one that catches a
phantom state.

**Scoping is explicit, never inferred.** ``dwh.pv_votes`` holds every source's rows
(D021), so the assert takes ``source``; and a partial-year run must not indict years it
never processed, so it takes the in-scope ``years``. Neither is read off whatever
happens to be in the frame — inferring them would make the guard silently weaker
exactly when it is being misused.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

import numpy as np
import pandas as pd

#: The ``dwh.pv_state_status`` columns, in load order. ``note`` is nullable.
ROSTER_COLUMNS: tuple[str, ...] = ("source", "year", "state", "pv_status", "note")

#: The roster's natural key (D024 §3). The loader enforces it as a table ``UNIQUE``.
ROSTER_NATURAL_KEY: tuple[str, ...] = ("source", "year", "state")

#: The three ``pv_status`` values, and deliberately only three (D024 §4).
#: ``popular_vote`` — held and recorded in ``pv_votes``; ``legislature_chosen`` — the
#: state's electors were chosen by its legislature, so no popular vote was ever held;
#: ``not_participating`` — the state took no part in the election at all.
#: There is **no** ``unknown``/``unparsed`` value: anything unclassifiable raises,
#: because an ``unknown`` slot is where parse failures go to die quietly. There is
#: likewise no value for "candidate not on the ballot" — that is a candidate-grain
#: fact and produces no ``pv_votes`` row at all (D024 §2, D018).
PV_STATUS_POPULAR_VOTE = "popular_vote"
PV_STATUS_LEGISLATURE_CHOSEN = "legislature_chosen"
PV_STATUS_NOT_PARTICIPATING = "not_participating"
PV_STATUS_VALUES: tuple[str, ...] = (
    PV_STATUS_POPULAR_VOTE,
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
)

#: The two statuses that assert "no popular vote happened here." Every state carrying
#: one must have **exactly zero** ``pv_votes`` rows; every ``popular_vote`` state must
#: have at least one row. That biconditional is the roster's whole point.
PV_ABSENCE_STATUSES: frozenset[str] = frozenset(
    {PV_STATUS_LEGISLATURE_CHOSEN, PV_STATUS_NOT_PARTICIPATING}
)

#: The warehouse schema and roster table. Shares ``dwh`` with the EC star schema and
#: ``pv_votes``; its ``state`` FK targets ``dwh.state`` (see :mod:`usvote.pv.schema`).
ROSTER_SCHEMA = "dwh"
ROSTER_TABLE = "pv_state_status"


class PVRosterError(RuntimeError):
    """Raised when a PV roster is malformed or disagrees with the PV facts.

    The source-neutral analogue of :class:`usvote.pv.schema.PVShapeError`. Every
    function here accepts an ``error_cls`` so a source can raise its own typed error
    (e.g. ``UCSBRosterError``) from this shared implementation, exactly as
    :func:`usvote.mit.transform.assert_unique_grain` already does.
    """


def build_status_column_defs(schema: str = ROSTER_SCHEMA) -> list[tuple[str, ...]]:
    """Return the ``pv_state_status`` column definitions as ``DBC.create_table`` tuples.

    A function rather than a constant for the same reason as
    :func:`usvote.pv.schema.build_pv_column_defs`: the ``state`` FK embeds ``schema``
    in its ``REFERENCES`` clause. ``schema`` must be the shared warehouse schema that
    already holds the EC ``state`` dimension.

    Mirrors the ``pv_votes`` DDL — identity PK, a ``UNIQUE`` on the natural key, the
    ``state`` FK, and a CHECK built from :data:`PV_STATUS_VALUES` so the enum has one
    definition rather than two. Provided here (rather than in #37) so the shared
    contract and its DDL cannot drift apart.

    ``note`` is nullable and, for ``legislature_chosen`` rows, holds **verbatim UCSB
    prose** — ``redistributable=false`` content per D024/D022/D016. It must be excluded
    from any public API surface and must never reach a committed fixture.
    """
    status_check = (
        "CHECK (pv_status IN (" + ", ".join(f"'{v}'" for v in PV_STATUS_VALUES) + "))"
    )
    return [
        ("status_id", "integer", "generated always as identity", "primary key"),
        ("source", "varchar", "not null"),
        ("year", "smallint", "not null"),
        ("state", "varchar", "not null", f"REFERENCES {schema}.state"),
        ("pv_status", "varchar", "not null", status_check),
        ("note", "text"),
        (
            "CONSTRAINT",
            f"{ROSTER_TABLE}_natural_key",
            "UNIQUE",
            "(source, year, state)",
        ),
    ]


#: The ``read_ec_participation`` columns :func:`build_roster` requires.
#: ``total_electoral_votes`` is deliberately **not** among them — D024 §5 keeps the EC
#: fact the single source of electoral-vote truth, and the roster never loads an EV.
_PARTICIPATION_COLUMNS: tuple[str, ...] = ("year", "state", "is_total")


def assert_participation_shape(
    df: pd.DataFrame,
    *,
    error_cls: type[Exception] = PVRosterError,
    caller: str = "build_roster",
) -> None:
    """Assert the injected EC frame can actually be filtered down to participants.

    The whole roster rests on this frame, and it arrives across a DI seam from a caller
    we do not control — a DB read, where ``state`` may be ``None`` rather than ``NaN``
    and a driver may hand back ``is_total`` as something other than a Python ``bool``.

    The subtle failure is why this is a hard assert rather than a coercion: a driver
    returning ``is_total`` as ``'t'``/``'f'`` **strings** makes ``.astype(bool)`` truthy
    for *every* row (a non-empty string is ``True``), so no row is treated as data and
    the roster comes back **empty, with no error**. Nothing downstream can tell that
    apart from "the EC spine was never loaded" — and for a caller with no PV facts to
    run :func:`assert_roster_covers_facts` against (the #139 snapshot build derives the
    roster in-process), nothing downstream would even look. So require genuine booleans:
    an ``object`` column of real ``bool`` values is fine (what psycopg2 yields for a
    Postgres boolean), strings and 0/1 ints are not.

    The sibling guard in ``usvote/ucsb/transform.py`` predates this one and says the
    same thing; this is the source-neutral home, so every roster derivation gets it.
    """
    missing = [c for c in _PARTICIPATION_COLUMNS if c not in df.columns]
    if missing:
        raise error_cls(
            f"{caller}: EC participation frame is missing column(s) {missing}; the "
            f"roster derives from {list(_PARTICIPATION_COLUMNS)} (totals rows excluded "
            "via `is_total`). Pass usvote.spine.read_ec_participation's frame, not the "
            "source's PV facts."
        )
    is_total = df["is_total"]
    if is_total.isna().any():
        raise error_cls(
            f"{caller}: EC participation frame has null `is_total` value(s); totals "
            "rows could not be excluded, and a totals row's NULL state becomes a "
            "phantom roster entry."
        )
    non_bool = is_total.map(lambda v: not isinstance(v, bool | np.bool_))
    if non_bool.any():
        bad = sorted({repr(v) for v in is_total[non_bool]})[:5]
        raise error_cls(
            f"{caller}: EC participation frame has non-boolean `is_total` value(s) "
            f"{bad}. Strings are the dangerous case — `.astype(bool)` is True for "
            "every non-empty string, so *no* row would be read as data and the roster "
            "would come back silently empty."
        )


def build_roster(
    ec_participation: pd.DataFrame,
    *,
    source: str,
    years: Collection[int],
    absences: Mapping[tuple[int, str], str] | None = None,
    error_cls: type[Exception] = PVRosterError,
    caller: str = "build_roster",
) -> pd.DataFrame:
    """Return a roster over the EC spine's states, with ``absences`` layered on.

    The one roster derivation, shared by every caller. Membership comes from the EC
    spine; ``absences`` maps a ``(year, state)`` key to one of
    :data:`PV_ABSENCE_STATUSES`; and **``popular_vote`` is the residual** — the status a
    state gets by *not* appearing in the map. That residual shape is what makes an
    absence detectable at all (D024 §3): enumerate only the absences, and a state that
    silently vanishes from the spine cannot masquerade as one.

    Two callers bind the map, and the dependency runs one way only:

    - :func:`build_popular_vote_roster` — the empty map, for a source whose whole span
      held a popular vote in every state (MIT, #127).
    - :func:`usvote.pv.absences.build_curated_roster` — the in-repo pre-1976 absence
      catalog (#140). It lives in a sibling module and imports *this* one; this module
      imports nothing from ``usvote``, and must not start.

    **The roster derives from the EC spine, not from the source's own facts — and that
    is the whole point.** ``ec_participation`` is
    :func:`usvote.spine.read_ec_participation`'s frame, the same independent input UCSB
    builds its roster from; D024's clarification names ``dwh.votes`` with totals rows
    excluded for *both* sources. Deriving from the source's own loaded facts instead
    would make :func:`assert_roster_covers_facts` compare a frame against itself —
    checks 1 and 3 holding by construction, check 2 vacuous — so the guard would be
    nominal exactly where D024 §7 needs it to bite. Against the spine it is real: a
    ``(year, state)`` that vanished during transform becomes a ``popular_vote`` roster
    state with no vote rows, and check 1 fails loudly instead of the year quietly
    reporting ``pv_coverage`` below ``1.0``. **Nothing else in the pipeline catches
    that** — the #69 join-side guard (:func:`usvote.join.assert_db_pv_matches_ec`) is a
    PV->EC anti-join that finds *phantom* rows, the opposite direction, and no sum
    validator can see a state that took its votes with it.

    **Totals rows are excluded explicitly** — ``votes.state`` is NULL on them, so a bare
    ``DISTINCT year, state`` yields a NULL roster entry per year, which becomes garbage
    or a NOT NULL violation at load (D024 §6). States with ``total_electoral_votes = 0``
    are **kept**: the Archives carries rows for non-participating states, so the spine
    already is the complete roster. Such a state left out of ``absences`` is marked
    ``popular_vote`` and then fails check 1 for want of vote rows — correctly, in that a
    caller claiming a state which cast no electoral votes has an absence it has not
    catalogued. (``usvote.pv.absences`` closes that loop the other way too, with a
    cross-check that no zero-EV spine state ends up ``popular_vote``.)

    Only ``("year", "state", "is_total")`` are required — **no electoral-vote column**.
    D024 §5 keeps the EC fact the single source of EV truth, and the roster neither
    loads an EV nor branches on one. A caller that wants the zero-EV cross-check reads
    that column itself, outside this function.

    ``years`` is **required and explicit**, never inferred — the module docstring's
    rule.
    A year in ``years`` with no spine rows simply yields no roster rows for it, which
    :func:`assert_roster_covers_facts` reports as the pipeline-sequencing failure it is
    (the EC spine was never loaded for that year).

    ``note`` is null on every row by construction, **including absence rows** (D024 §6,
    #140). The column carries verbatim UCSB prose where UCSB fills it, so it is
    ``redistributable=false`` content; leaving it null here is what keeps "no ``note``
    reaches the public snapshot" a structural property rather than a reviewed one. An
    absence's cause lives in its catalog citation, in code, not in the warehouse.

    ``caller`` is the public entry point named in error messages. It defaults to this
    function's own name, and the two thin wrappers pass their own: an operator handed
    ``build_roster: ...`` from a ``build_popular_vote_roster`` call site would grep for
    a symbol that does not appear anywhere on their code path.

    The returned frame is sorted on ``(year, state)`` so this function has a
    deterministic *return* value for a caller inspecting or asserting on it.
    :func:`usvote.pv.load.load_pv_status` re-sorts on the full
    :data:`ROSTER_NATURAL_KEY` before inserting — the **insert** order is the loader's
    to own, not this function's, and the two are deliberately not coupled.
    """
    assert_participation_shape(
        ec_participation, error_cls=error_cls, caller=f"{caller}({source!r})"
    )
    absence_map = dict(absences or {})
    bad = sorted(
        {status for status in absence_map.values() if status not in PV_ABSENCE_STATUSES}
    )
    if bad:
        raise error_cls(
            f"{caller}({source!r}) got absence status(es) {bad}; an absence map "
            f"may only carry {sorted(PV_ABSENCE_STATUSES)}. Mapping a key to "
            f"'{PV_STATUS_POPULAR_VOTE}' is a silent no-op, since that is already the "
            "residual."
        )
    in_scope = frozenset(years)
    rows = ec_participation[
        (~ec_participation["is_total"].astype(bool))
        & ec_participation["state"].notna()
        & ec_participation["year"].isin(in_scope)
    ]
    keys = (
        rows[["year", "state"]]
        .drop_duplicates()
        .sort_values(["year", "state"], kind="stable")
        .reset_index(drop=True)
    )
    statuses = [
        absence_map.get((int(year), state), PV_STATUS_POPULAR_VOTE)
        for year, state in zip(keys["year"], keys["state"], strict=True)
    ]
    roster = pd.DataFrame(
        {
            "source": source,
            "year": keys["year"].astype("int64"),
            "state": keys["state"],
            "pv_status": pd.Series(statuses, dtype="object"),
            "note": pd.Series([None] * len(keys), dtype="object"),
        },
        columns=list(ROSTER_COLUMNS),
    )
    return roster


def build_popular_vote_roster(
    ec_participation: pd.DataFrame,
    *,
    source: str,
    years: Collection[int],
    error_cls: type[Exception] = PVRosterError,
) -> pd.DataFrame:
    """Return an all-``popular_vote`` roster over the EC spine's participating states.

    :func:`build_roster` with **no absences** — the mechanical derivation D024
    §6/§Rationale anticipated (#127), for a source whose whole span held a popular vote
    in every state. MIT is the first caller: it covers 1976-2024, where no state was
    ever ``legislature_chosen`` or ``not_participating``, so none of the pre-1976
    absence derivation applies and MIT stays "not taxed" by the roster design.

    That MIT precondition is held by a **catalog-integrity test** — no
    :data:`usvote.pv.absences.PV_ABSENCE_CATALOG` key falls in 1976-2024 — rather than a
    runtime assert here, because MIT's path never imports the catalog and this function
    must keep working with no knowledge that one exists.

    Source-neutral and living here rather than under ``usvote/mit/`` for the same reason
    :func:`assert_roster_covers_facts` does: there is no source-specific logic to write,
    and any future whole-span source qualifies on the same terms.
    """
    return build_roster(
        ec_participation,
        source=source,
        years=years,
        error_cls=error_cls,
        caller="build_popular_vote_roster",
    )


def assert_roster_shape(
    df: pd.DataFrame, *, error_cls: type[Exception] = PVRosterError
) -> None:
    """Assert exactly :data:`ROSTER_COLUMNS`, valid statuses, and no null keys.

    ``note`` is exempt from the non-null check — it is null on every ordinary
    ``popular_vote`` row by design.
    """
    if list(df.columns) != list(ROSTER_COLUMNS):
        raise error_cls(
            f"PV roster columns {list(df.columns)} != roster shape "
            f"{list(ROSTER_COLUMNS)}"
        )
    for col in ROSTER_NATURAL_KEY + ("pv_status",):
        if df[col].isna().any():
            raise error_cls(f"PV roster column {col!r} has null value(s)")
    unknown = sorted(set(df["pv_status"].unique()) - set(PV_STATUS_VALUES))
    if unknown:
        raise error_cls(
            f"PV roster has unknown pv_status value(s) {unknown}; the enum is "
            f"{list(PV_STATUS_VALUES)} and D024 §4 admits no others"
        )


def assert_unique_roster_grain(
    df: pd.DataFrame, *, error_cls: type[Exception] = PVRosterError
) -> None:
    """Assert one roster row per ``(source, year, state)``."""
    dupes = df.loc[df.duplicated(list(ROSTER_NATURAL_KEY), keep=False)]
    if not dupes.empty:
        raise error_cls(
            "PV roster grain violated — duplicate (source, year, state): "
            f"{dupes[list(ROSTER_NATURAL_KEY)].values.tolist()}"
        )


def assert_roster_covers_facts(
    pv_df: pd.DataFrame,
    roster_df: pd.DataFrame,
    *,
    source: str,
    years: Collection[int],
    error_cls: type[Exception] = PVRosterError,
    empty_roster_error_cls: type[Exception] | None = None,
) -> None:
    """The two-way roster/fact assert — the guard against silent row loss (D024 §7).

    Three checks, over the rows of ``source`` in the in-scope ``years``:

    1. every ``popular_vote`` roster state has **≥1** ``pv_votes`` row;
    2. every absence-status state (:data:`PV_ABSENCE_STATUSES`) has **exactly 0**;
    3. every ``pv_votes`` ``(year, state)`` is **in** the roster.

    Check 3 is the one no sum validator can replace: a phantom or mis-canonicalized
    state passes every total while being wrong.

    ``source`` and ``years`` are **required and explicit**. ``dwh.pv_votes`` holds
    other sources' rows, and a partial-year run must not report unprocessed years as
    violations — neither is inferred from the frames.

    "The roster is empty for an in-scope year" raises ``empty_roster_error_cls``
    (defaulting to ``error_cls``) rather than being reported as N mismatched states:
    different cause (a mis-sequenced pipeline — the EC spine was never loaded, or was
    loaded for a different year set), different fix. Callers pass a distinct class so
    the two are separable by type, not only by message.
    """
    empty_cls = empty_roster_error_cls or error_cls
    in_scope = frozenset(years)

    roster = roster_df[
        (roster_df["source"] == source) & (roster_df["year"].isin(in_scope))
    ]
    facts = pv_df[(pv_df["source"] == source) & (pv_df["year"].isin(in_scope))]

    missing_years = sorted(in_scope - set(roster["year"].unique()))
    if missing_years:
        raise empty_cls(
            f"{source} roster is empty for in-scope year(s) {missing_years}. This is a "
            f"pipeline-sequencing failure, not a state mismatch: the roster derives "
            f"from the EC spine, so the spine was never loaded for these years (or "
            f"was loaded for a different year set). Run the EC pipeline for them, or "
            f"narrow the PV run's `years` to match."
        )

    fact_keys = set(zip(facts["year"], facts["state"], strict=True))
    roster_keys = set(zip(roster["year"], roster["state"], strict=True))
    is_pv = roster["pv_status"] == PV_STATUS_POPULAR_VOTE

    expected = set(
        zip(roster.loc[is_pv, "year"], roster.loc[is_pv, "state"], strict=True)
    )
    absent = set(
        zip(roster.loc[~is_pv, "year"], roster.loc[~is_pv, "state"], strict=True)
    )

    silent_drops = sorted(expected - fact_keys)
    if silent_drops:
        raise error_cls(
            f"{source}: {len(silent_drops)} roster state(s) marked "
            f"'{PV_STATUS_POPULAR_VOTE}' have no vote rows: {silent_drops[:10]}"
            f"{' ...' if len(silent_drops) > 10 else ''}. Either the rows were dropped "
            f"silently (an unreconciled state label, or a join that lost them), or the "
            f"state genuinely held no popular vote and needs an absence status."
        )

    fabricated = sorted(absent & fact_keys)
    if fabricated:
        raise error_cls(
            f"{source}: {len(fabricated)} state(s) marked as having *no* popular vote "
            f"nevertheless have vote rows: {fabricated[:10]}"
            f"{' ...' if len(fabricated) > 10 else ''}. The roster and the facts "
            f"disagree about whether an election happened."
        )

    phantoms = sorted(fact_keys - roster_keys)
    if phantoms:
        raise error_cls(
            f"{source}: {len(phantoms)} vote-row (year, state) key(s) are absent from "
            f"the roster: {phantoms[:10]}{' ...' if len(phantoms) > 10 else ''}. The "
            f"roster is the complete set of states in each year's election, so these "
            f"are phantom states — most likely an unreconciled or mis-canonicalized "
            f"state label. A sum validator cannot see this."
        )