"""EC<->PV join — the full-outer *participant* view that powers E7/E8 (#69, D026).

This is the seam the analysis (E7 hybrid) and the API (E8) build on. It joins the
**resolved** popular-vote series (``pv_preferred`` for analysis, ``pv_redistributable``
for the API — never the raw ``dwh.pv_votes`` union, which would fan the 1976–2024
overlap out 2× and double-count every downstream sum/margin, D017) onto the Electoral
College spine, producing one row per ``(year, state, candidate)`` — the **canonical
grain** (D006 / :mod:`usvote.transform` canonical keys).

**Why a FULL OUTER join, not EC-left (D026).** The EC ``votes`` fact is *sparse*:
:func:`usvote.transform.build_votes_fact` drops candidate/state cells with no electoral
votes, so it holds only winners' state rows + the national ``is_total`` rows. A losing
candidate's per-state popular vote (Biden in Texas 2020) has **no** EC row. An EC-left
join would therefore drop every loser — making the view useless for this project's
primary thesis (*where does a candidate lose the EC but win the PV, and by what
margin?*), which needs both majors' per-state popular votes. The full outer keeps three
row types:

- **winner + PV** — an EC winner state row matched to its PV (EC votes + PV both real);
- **loser-in-state** — a PV participant with no EC row in that state: electoral votes
  are **0** (a *fact* under winner-take-all, not a fabrication) *when the state ran an
  EC contest that year*, else NULL. These are the rows an EC-left join drops;
- **getter-without-PV** — an EC getter with no PV (pre-1976, or a faithless/unpledged
  getter): PV columns are **NULL** — an honest gap, never a fabricated value (D005).

**Scope is per-year EC-getters, for free.** ``pv_preferred`` is already D007/D019-scoped
to per-year EC-getters (D025) and ``dwh.votes`` only holds getters, so the participant
universe per year is exactly "candidates who received ≥1 electoral vote that year" — the
popular-vote-only minors were dropped upstream at reconcile. Because every PV candidate
is thus an EC getter present in ``dwh.candidate``, a loser row resolves its
``candidate_id`` by canonical ``name`` (the EC-side row lacks it), and national context
(national electoral votes, rank, ``took_office``) is carried on **every** participant
row — including losers — from the ``is_total`` rows, so flip detection reads one view.

**Module placement.** This lives at the top level (a sibling of :mod:`usvote.spine`),
**not** under ``usvote/pv/``: it names ``dwh.votes``/``dwh.candidate`` (EC star-schema
knowledge), and the greppable invariant *nothing under ``src/usvote/pv/`` mentions
``dwh.votes``* forbids ``pv/``. Its precedent is :mod:`usvote.spine` — an EC-domain
module a PV/consumer stage reads *from* (D006 makes EC authoritative), not the reverse.

Two testable expressions of the same policy, mirroring :mod:`usvote.pv.views`: the SQL
builder (unit-tested as a string, drives the live views) and the pure-pandas oracle
:func:`join_ec_pv` (run on small fixtures offline and re-run against the live view).
"""

from __future__ import annotations

from collections.abc import Collection

import pandas as pd

from usvote.db import DBC
from usvote.load import SCHEMA
from usvote.pv.schema import PV_SCHEMA
from usvote.pv.source import PV_SOURCE_TABLE
from usvote.pv.views import PV_PREFERRED_VIEW, PV_REDISTRIBUTABLE_VIEW

#: The two joined participant views, one per resolved PV series (D026). Named to mirror
#: the PV views they wrap (:data:`usvote.pv.views.PV_PREFERRED_VIEW` etc.) with an
#: ``ec_pv_`` prefix so a joined view is never confused with the resolved PV view it
#: reads. ``ec_pv_preferred`` is the analysis surface (E7); ``ec_pv_redistributable`` is
#: the public API surface (E8) and — because it wraps ``pv_redistributable`` — can never
#: carry a ``redistributable=false`` (UCSB) row (D002/D014/D016).
EC_PV_PREFERRED_VIEW = "ec_pv_preferred"
EC_PV_REDISTRIBUTABLE_VIEW = "ec_pv_redistributable"

#: The canonical grain the joined view is unique on — one participant row per this key
#: (:func:`assert_no_fan_out`). The same key ``pv_preferred`` resolves to (D017), now
#: spanning EC winners *and* PV participants.
JOIN_KEY: tuple[str, ...] = ("year", "state", "candidate")

#: The joined participant view's column order. EC-spine columns first (identity + the
#: state's EC context + this candidate's electoral votes there + national context), then
#: the PV columns carried through from the resolved series (+ ``redistributable`` from
#: the ``pv_source`` reference table). ``state_total_votes`` is carried so margins pin
#: to each source's *provided* denominator, never a re-sum of candidate rows (D017).
EC_PV_COLUMNS: tuple[str, ...] = (
    "year",
    "state",
    "candidate_id",
    "candidate",
    "total_electoral_votes",
    "president_electoral_votes",
    "has_ec_state_row",
    "national_electoral_votes",
    "president_electoral_rank",
    "took_office",
    "source",
    "party",
    "candidate_votes",
    "state_total_votes",
    "reliability",
    "redistributable",
)


class JoinError(RuntimeError):
    """Raised when the EC<->PV join violates a #69 invariant.

    Covers the pure-frame guards here — a reconciled PV ``candidate``/``state`` value
    absent from the EC dims (the reciprocal coverage gap the join owns, per
    ``docs/canonical-keys.md``), a fan-out beyond one row per ``(year, state,
    candidate)``, a fabricated EC 0 in a state that ran no EC contest that year (the one
    real D005 fabrication seam), or an EC winner silently missing PV inside the window.
    """


# --- SQL builder (drives the live views) ------------------------------------


def build_ec_pv_join_sql(
    pv_view: str,
    *,
    schema: str = SCHEMA,
    pv_schema: str = PV_SCHEMA,
) -> str:
    """Return the FULL OUTER participant SELECT joining ``pv_view`` onto the EC spine.

    One builder for both views (``pv_view`` is ``pv_preferred`` or
    ``pv_redistributable``), mirroring the shared shape of
    :func:`usvote.pv.views.build_pv_preferred_sql` /
    :func:`~usvote.pv.views.build_pv_redistributable_sql`. Three CTEs shape the EC side:

    - ``ec_state`` — the per-candidate **state** EC rows (``state IS NOT NULL``), joined
      to ``candidate`` for the canonical ``name`` the PV series keys on. The national
      ``is_total`` rows are excluded here — they have no PV counterpart and would muddy
      the participant grain (D026); their content returns as per-row *context* via
      ``getter`` below.
    - ``state_ctx`` — the state's EC allotment per ``(year, state)`` (constant across a
      state's candidates). Its **absence** for a ``(year, state)`` is the free
      discriminator for "this state ran no EC contest that year", gating the 0-fill.
    - ``getter`` — the national electoral votes / rank / ``took_office`` per
      ``(year, candidate_id)``, carried onto **every** participant row (winners *and*
      losers) so flip detection reads off one view.

    ``president_electoral_votes`` is: the actual state EC votes when the candidate has
    an EC row here (so a split-vote state — ME/NE — keeps each candidate's real count);
    else **0** when the state ran an EC contest that year (a winner-take-all *fact*);
    else **NULL** (no EC contest — never a fabricated 0). ``candidate_id`` for a
    PV-only loser row (whose EC side is absent) is resolved by ``name`` against
    ``dwh.candidate`` (hence its ``UNIQUE(name)``). ``redistributable`` is read from the
    ``pv_source`` reference table (trivially true for the redistributable view; how a
    consumer of the preferred view flags a UCSB row).
    """
    key = " AND ".join(f"p.{c} = e.{c}" for c in JOIN_KEY)
    return (
        "WITH ec_state AS ("
        " SELECT v.year, v.state, v.candidate_id, c.name AS candidate,"
        " v.president_electoral_votes AS ec_state_ev"
        f" FROM {schema}.votes v"
        f" JOIN {schema}.candidate c ON v.candidate_id = c.candidate_id"
        " WHERE v.state IS NOT NULL"
        "), state_ctx AS ("
        " SELECT year, state, max(total_electoral_votes) AS total_electoral_votes"
        f" FROM {schema}.votes WHERE state IS NOT NULL GROUP BY year, state"
        "), getter AS ("
        " SELECT year, candidate_id,"
        " president_electoral_votes AS national_electoral_votes,"
        " president_electoral_rank, took_office"
        f" FROM {schema}.votes WHERE state IS NULL"
        ") SELECT"
        " COALESCE(e.year, p.year) AS year,"
        " COALESCE(e.state, p.state) AS state,"
        " COALESCE(e.candidate_id, cd.candidate_id) AS candidate_id,"
        " COALESCE(e.candidate, p.candidate) AS candidate,"
        " ctx.total_electoral_votes,"
        " CASE WHEN e.candidate_id IS NOT NULL THEN e.ec_state_ev"
        " WHEN ctx.total_electoral_votes IS NOT NULL THEN 0"
        " ELSE NULL END AS president_electoral_votes,"
        " (e.candidate_id IS NOT NULL) AS has_ec_state_row,"
        " g.national_electoral_votes, g.president_electoral_rank, g.took_office,"
        " p.source, p.party, p.candidate_votes, p.state_total_votes, p.reliability,"
        " s.redistributable"
        " FROM ec_state e"
        f" FULL OUTER JOIN {pv_schema}.{pv_view} p ON {key}"
        f" LEFT JOIN {schema}.candidate cd"
        " ON cd.name = COALESCE(e.candidate, p.candidate)"
        " LEFT JOIN state_ctx ctx"
        " ON ctx.year = COALESCE(e.year, p.year)"
        " AND ctx.state = COALESCE(e.state, p.state)"
        " LEFT JOIN getter g"
        " ON g.year = COALESCE(e.year, p.year)"
        " AND g.candidate_id = COALESCE(e.candidate_id, cd.candidate_id)"
        f" LEFT JOIN {pv_schema}.{PV_SOURCE_TABLE} s ON s.source = p.source"
    )


def create_ec_pv_views(
    dbc: DBC,
    *,
    schema: str = SCHEMA,
    pv_schema: str = PV_SCHEMA,
    replace: bool = True,
    close: bool = False,
) -> None:
    """Create both participant views, after the reciprocal DIM guard passes.

    The reciprocal DIM guard (:func:`assert_db_ec_dims_cover_pv`) runs **first, as a
    precondition** (per the architect): a reconciled PV ``candidate``/``state`` absent
    from the EC dims would be silently swallowed by the ``candidate_id``-by-name
    resolution (losing that row's national context), so it must fail loud *before* the
    view is built rather than surface as a mystery NULL later. It is checked against the
    ``pv_preferred`` series (the widest resolved surface — ``pv_redistributable`` is a
    subset), so both views are covered by the one check.

    Both ``dwh.pv_votes`` + ``dwh.pv_source`` and the resolved PV views must already
    exist (run after :func:`usvote.pv.load.build_pv_union`) and the EC spine must be
    loaded. ``replace`` defaults to ``True`` — ``CREATE OR REPLACE VIEW`` is
    non-destructive and idempotent (see :meth:`usvote.db.DBC.create_view`).
    """
    assert_db_ec_dims_cover_pv(
        dbc, PV_PREFERRED_VIEW, schema=schema, pv_schema=pv_schema
    )
    dbc.create_view(
        schema,
        EC_PV_PREFERRED_VIEW,
        build_ec_pv_join_sql(PV_PREFERRED_VIEW, schema=schema, pv_schema=pv_schema),
        replace=replace,
    )
    dbc.create_view(
        schema,
        EC_PV_REDISTRIBUTABLE_VIEW,
        build_ec_pv_join_sql(
            PV_REDISTRIBUTABLE_VIEW, schema=schema, pv_schema=pv_schema
        ),
        replace=replace,
    )
    if close:
        dbc.close_connection()


# --- reciprocal DIM guard (the coverage gap #69 owns) -----------------------


def assert_ec_dims_cover_pv(
    pv_df: pd.DataFrame,
    candidate_names: Collection[str],
    state_names: Collection[str],
    *,
    error_cls: type[Exception] = JoinError,
) -> None:
    """Assert every reconciled PV ``candidate``/``state`` is present in the EC dims.

    The guard #69 owns (``docs/canonical-keys.md``): reconcile (#38/#67) produces
    canonical *values* offline; here we prove every one actually lands on a real EC
    ``dwh.candidate.name`` / ``dwh.state`` — an unmatched value fails loud rather than
    vanishing in the inner ``candidate_id``-by-name resolution (the classic inner-join
    silent-drop). Run as a **precondition** to view creation.
    """
    missing_cand = sorted(set(pv_df["candidate"]) - set(candidate_names))
    missing_state = sorted(set(pv_df["state"].dropna()) - set(state_names))
    if missing_cand or missing_state:
        raise error_cls(
            "PV values absent from the EC dims (they would be silently dropped by the "
            f"join): candidates={missing_cand}, states={missing_state}"
        )


def assert_db_ec_dims_cover_pv(
    dbc: DBC,
    pv_view: str,
    *,
    schema: str = SCHEMA,
    pv_schema: str = PV_SCHEMA,
) -> None:
    """Live-DB form of :func:`assert_ec_dims_cover_pv` over the resolved ``pv_view``.

    Reads the distinct ``candidate``/``state`` from the resolved PV view and the EC dim
    key sets, then runs the pure guard — the dual-use precedent of
    :func:`usvote.pv.status.assert_roster_covers_facts`. Assumes the PV view + EC dims
    exist (the caller, :func:`create_ec_pv_views`, sequences this after the union build
    and EC load).
    """
    pv_df = dbc.select_query_to_df(
        f"SELECT DISTINCT candidate, state FROM {pv_schema}.{pv_view}"
    )
    candidate_names = dbc.select_query_to_df(
        f"SELECT name FROM {schema}.candidate"
    )["name"]
    state_names = dbc.select_query_to_df(f"SELECT state FROM {schema}.state")["state"]
    assert_ec_dims_cover_pv(pv_df, set(candidate_names), set(state_names))


# --- pure oracle (offline mirror of the live view) --------------------------


def join_ec_pv(
    votes_df: pd.DataFrame,
    candidate_df: pd.DataFrame,
    pv_df: pd.DataFrame,
    pv_source_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Pure-pandas mirror of :func:`build_ec_pv_join_sql` — the join oracle (D026).

    ``votes_df`` is ``dwh.votes`` shape (incl. the ``is_total`` national rows);
    ``candidate_df`` carries ``candidate_id``/``name``; ``pv_df`` is the resolved PV
    series (:data:`usvote.pv.schema.SHARED_PV_COLUMNS`); ``pv_source_df`` (optional)
    supplies ``redistributable``. Produces :data:`EC_PV_COLUMNS`, one row per
    ``(year, state, candidate)``. Used in unit tests to prove the three row types and
    the guarded 0-fill resolve the same way the live view does, on small fixtures.
    """
    id_to_name = candidate_df.set_index("candidate_id")["name"]
    name_to_id = candidate_df.set_index("name")["candidate_id"]

    state_rows = votes_df[votes_df["state"].notna()]
    ec_state = pd.DataFrame({
        "year": state_rows["year"],
        "state": state_rows["state"],
        "candidate_id": state_rows["candidate_id"],
        "candidate": state_rows["candidate_id"].map(id_to_name),
        "ec_state_ev": state_rows["president_electoral_votes"],
    })

    state_ctx = (
        state_rows.groupby(["year", "state"], as_index=False)["total_electoral_votes"]
        .max()
    )
    getter = votes_df[votes_df["state"].isna()][
        ["year", "candidate_id", "president_electoral_votes",
         "president_electoral_rank", "took_office"]
    ].rename(columns={"president_electoral_votes": "national_electoral_votes"})

    merged = ec_state.merge(
        pv_df, on=list(JOIN_KEY), how="outer", indicator=True
    )
    merged["has_ec_state_row"] = merged["_merge"].ne("right_only")
    # Resolve candidate_id for PV-only (right_only) rows by canonical name. The outer
    # merge upcast candidate_id to float (NaN for right_only rows); cast to nullable
    # Int64 after the fill so the getter merge keys match its int candidate_id.
    merged["candidate_id"] = (
        merged["candidate_id"].fillna(merged["candidate"].map(name_to_id)).astype("Int64")
    )

    merged = merged.merge(state_ctx, on=["year", "state"], how="left")
    merged = merged.merge(
        getter.astype({"candidate_id": "Int64"}),
        on=["year", "candidate_id"],
        how="left",
        validate="m:1",
    )

    # Guarded EC-votes fill: actual when there is an EC row here; else 0 iff the state
    # ran an EC contest that year (total_electoral_votes present); else NULL.
    pev = pd.Series(pd.NA, index=merged.index, dtype="Int64")
    has_ec = merged["has_ec_state_row"]
    pev[has_ec] = merged.loc[has_ec, "ec_state_ev"].astype("Int64")
    fill_zero = ~has_ec & merged["total_electoral_votes"].notna()
    pev[fill_zero] = 0
    merged["president_electoral_votes"] = pev

    if pv_source_df is not None:
        merged = merged.merge(
            pv_source_df[["source", "redistributable"]], on="source", how="left"
        )
    else:
        merged["redistributable"] = pd.NA

    return (
        merged[list(EC_PV_COLUMNS)]
        .sort_values(list(JOIN_KEY), kind="stable", na_position="last")
        .reset_index(drop=True)
    )


# --- guards & coverage (run as automated tests) -----------------------------


def assert_no_fan_out(
    joined_df: pd.DataFrame, *, error_cls: type[Exception] = JoinError
) -> None:
    """Assert one joined row per ``(year, state, candidate)`` — the canonical grain.

    Because the resolved PV series is unique on the key and the EC-side CTE is one row
    per ``(year, state, candidate)``, the FULL OUTER cannot fan out — this proves it,
    and would catch a regression letting the raw union (2 rows per overlap key) leak in.
    """
    dupes = joined_df.loc[joined_df.duplicated(list(JOIN_KEY), keep=False)]
    if not dupes.empty:
        raise error_cls(
            "EC<->PV join fanned out (>1 row per (year, state, candidate)): "
            f"{dupes[list(JOIN_KEY)].values.tolist()}"
        )


def assert_no_fabricated_ec_zero(
    joined_df: pd.DataFrame, *, error_cls: type[Exception] = JoinError
) -> None:
    """Assert no row carries PV while its state ran no EC contest that year.

    The one real D005 fabrication seam: the 0-fill is a *fact* only inside a contested
    ``(year, state)``. A row with ``candidate_votes`` present but no
    ``total_electoral_votes`` means PV exists where the EC state is absent — a D024
    roster leak (PV must never cover a non-participating ``(year, state)``). Fail loud.
    """
    bad = joined_df.loc[
        joined_df["candidate_votes"].notna()
        & joined_df["total_electoral_votes"].isna()
    ]
    if not bad.empty:
        raise error_cls(
            "PV present for a (year, state) with no EC contest (D024 roster leak / "
            f"would fabricate an EC 0): {bad[list(JOIN_KEY)].values.tolist()}"
        )


def assert_winners_have_pv(
    joined_df: pd.DataFrame,
    *,
    exemptions: Collection[tuple[int, str]] = (),
    error_cls: type[Exception] = JoinError,
) -> int:
    """Assert every EC winner **inside the PV window** has PV, bar known exemptions.

    The asymmetric, one-directional coverage guard (the architect's crux): an EC winner
    state row (``has_ec_state_row``) in a year the PV series covers that carries **no**
    PV is a reconciliation miss (a major winner silently failing to match PV on a name
    nit), so it fails loud. The reverse direction — a PV loser with no EC row — is
    expected structural bulk and is only *reported* (:func:`coverage_report`), never
    asserted, so the guard stays quiet on the thousands of legitimate losers.

    The window is derived from the frame itself (years with any PV present), so a year
    the series does not cover (pre-1976 for ``pv_redistributable``) is out of scope
    automatically. ``exemptions`` is the set of ``(year, candidate)`` getters that
    legitimately held no popular vote (faithless/unpledged/legislature-chosen — see
    :data:`usvote.getters.EC_GETTERS_WITHOUT_POPULAR_VOTE`) — and for the
    ``pv_redistributable`` view, the non-D/R getters MIT does not cover; it differs per
    view, so it is injected rather than hardcoded here.

    **Returns the number of in-window EC-winner rows it inspected** — the population the
    guard evaluated, so a caller can assert a **vacuity floor** (``>= N``): a guard that
    silently inspected zero winners — an empty frame, a window that excluded everything,
    or a wrong-typed ``year`` — would otherwise pass vacuously, defeating its purpose.
    """
    exempt = set(exemptions)
    pv_years = set(joined_df.loc[joined_df["candidate_votes"].notna(), "year"])
    in_window_winner = joined_df["has_ec_state_row"] & joined_df["year"].isin(pv_years)
    suspects = joined_df.loc[in_window_winner & joined_df["candidate_votes"].isna()]
    missing = [
        (int(r.year), r.candidate)
        for r in suspects.itertuples()
        if (int(r.year), r.candidate) not in exempt
    ]
    if missing:
        raise error_cls(
            "EC winner(s) inside the PV window with no matching PV (likely a name "
            f"reconciliation miss; exempt it if legitimately PV-less): {missing}"
        )
    return int(in_window_winner.sum())


def coverage_report(joined_df: pd.DataFrame) -> dict[str, object]:
    """Surface both unmatched-key directions explicitly (never a silent drop).

    Returns a small structured report: ``ec_only`` (EC rows with no PV — pre-PV years or
    faithless getters; an honest D005 gap) as a frame on the join key, and ``pv_only_n``
    (the count of PV losers with no EC row — expected bulk, counted not listed). Used
    by tests and useful for eyeballing coverage; the load-bearing failures are the three
    ``assert_*`` guards above.
    """
    ec_only = joined_df.loc[
        joined_df["has_ec_state_row"] & joined_df["candidate_votes"].isna(),
        list(JOIN_KEY),
    ].reset_index(drop=True)
    pv_only_n = int(
        (~joined_df["has_ec_state_row"] & joined_df["candidate_votes"].notna()).sum()
    )
    return {"ec_only": ec_only, "pv_only_n": pv_only_n}
