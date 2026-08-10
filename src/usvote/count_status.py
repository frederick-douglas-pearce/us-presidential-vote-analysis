"""The ``dwh.votes`` count-status enum contract (D043 §3, D044).

A *counting* status carried by each vote row: were these electoral votes, once
cast, actually **counted** by Congress? It is deliberately a separate fact from
:data:`usvote.transform.ELECTORAL_VOTE_SHORTFALLS`, which records votes that were
**never cast** (appointed > cast: 1832 Maryland's two electors in ill health,
2000 DC's protest abstention). This column is the other failure — *cast, then not
counted* (cast > counted: 1868, 1872). D043 §6 keeps the two mechanisms disjoint
on purpose, and they are disjoint **by construction**: a row whose votes were cast
still sums to its allotment, so ``assert_row_votes_sum_to_total`` would reject a
spurious shortfall entry for one of these years.

**Why a module of its own** (D044). The enum has exactly one definition, and two
callers that must not depend on each other: :mod:`usvote.transform` *assigns* the
values, and :mod:`usvote.load` builds the ``CHECK`` constraint from them. Putting
the tuple in ``transform`` would point the DDL builder at the pandas transform
module; putting it in ``load`` would drag psycopg2 into the transform import
chain. This is the same shape :mod:`usvote.years` and :mod:`usvote.pv.status`
already have — a pure module underneath both — and the
CHECK-built-from-a-value-tuple pattern is lifted directly from
:func:`usvote.pv.status.build_status_column_defs` (D024 §4).

Everything here is **stdlib only**: no pandas, no DB, no network. That is what
lets both sides import it.

**The grain is ``(year, state, candidate)``** — a column on the fact, not a
sibling roster (D043 §4). 1872 Georgia is the proof: of its 11 votes, Greeley's 3
were rejected while B. Gratz Brown's 6 and Jenkins's 2 were counted, so the status
varies *within* a state and the ``pv_state_status`` shape (a ``(year, state)``
roster) cannot express it. Because ``dwh.votes`` is already dense and rectangular
(:func:`usvote.transform.assert_rectangular_state_grain`), "complete rather than
exceptions-only" (D024 §3) comes free: every row carries a status and there is no
second table to keep in sync.

**Aggregate rows are not flagged** (D044). A year's national totals row is
``counted`` even when it aggregates a disputed state row — 1868 Seymour's 80
includes Georgia's 9, and one enum value cannot say "80, of which 9 disputed". The
state grain carries the truth and the aggregate's disputed-ness is derivable from
it.
"""

from __future__ import annotations

#: Votes that were cast **and counted** by Congress. The default for every row: the
#: overwhelmingly normal case, and the value the column carries when nothing went
#: wrong.
COUNT_STATUS_COUNTED = "counted"

#: Cast, and Congress decided **not** to count them — a settled outcome. 1872:
#: Georgia's 3 Greeley votes, rejected by House resolution; Arkansas's and
#: Louisiana's returns, never accepted into the count (#144).
COUNT_STATUS_NOT_COUNTED = "not_counted"

#: Cast, and Congress decided **nothing** — the question was never resolved. 1868
#: Georgia is the only instance in the corpus: the Senate and House could not agree
#: whether to accept the state's nine votes, so the Archives prints two totals rows
#: and marks neither authoritative.
#:
#: This is **not** the ``unknown`` bucket :mod:`usvote.pv.status` forbids (D043 §5).
#: ``unknown`` would mean *we do not know what happened*; ``disputed`` means *we
#: know exactly what happened — the two chambers deadlocked and never resolved it*.
#: That is a recorded fact about the world, not a gap in our knowledge, and every
#: such row carries the Archives' own sentence saying so in ``count_status_reason``.
COUNT_STATUS_DISPUTED = "disputed"

#: The three values, and deliberately only three (D043 §3). A boolean ``contested``
#: was the first proposal and is not enough: it cannot distinguish *Congress decided
#: no* (1872) from *Congress never decided* (1868), which is precisely the
#: distinction these two years exist to teach.
COUNT_STATUS_VALUES: tuple[str, ...] = (
    COUNT_STATUS_COUNTED,
    COUNT_STATUS_NOT_COUNTED,
    COUNT_STATUS_DISPUTED,
)

#: The two values that assert "these votes did not enter the final count." Every row
#: carrying one must also carry a non-null ``count_status_reason`` — a status without
#: its grounds is how a catalog rots silently (the same argument
#: :class:`usvote.pv.absences.PVAbsence` makes for its citation).
COUNT_STATUS_UNCOUNTED: frozenset[str] = frozenset(
    {COUNT_STATUS_NOT_COUNTED, COUNT_STATUS_DISPUTED}
)

#: The two ``dwh.votes`` columns this contract owns, in load order.
COUNT_STATUS_COLUMN = "count_status"
COUNT_STATUS_REASON_COLUMN = "count_status_reason"

#: The **cast** electoral-vote measure: votes the electors actually cast, whatever
#: Congress later did with them. The original ``dwh.votes`` measure, unchanged.
CAST_VOTES_COLUMN = "president_electoral_votes"

#: The **counted** electoral-vote measure (#144): the votes that entered the final
#: national count. Named here rather than in :mod:`usvote.transform` for exactly the
#: reason this module exists — it has the same two mutually-independent callers as the
#: enum itself (``transform`` derives it, ``load`` builds its DDL and ``CHECK``), plus a
#: third in :mod:`usvote.join`, which sums it into ``national_counted_electoral_votes``.
#:
#: **Its definition is this module's enum**, which is why it is not merely a second
#: number: a row's counted value is its cast value when :data:`COUNT_STATUS_COUNTED`,
#: and ``0`` otherwise. The rule is **strict** — ``disputed`` is excluded alongside
#: ``not_counted``, because Georgia's nine votes in 1868 were never counted by anyone;
#: the two chambers deadlocked. That strictness is what makes *both* of the Archives'
#: printed 1868 totals rows reproducible: 294 as cast, 285 as counted, where D044 could
#: only select one of them.
#:
#: **The row rule does not apply to aggregates.** A year's ``is_total`` row is always
#: ``counted`` (D044 — one enum value cannot say "80, of which 9 disputed"), so the row
#: rule would return its cast value. Its counted value is instead the sum over that
#: year's state rows, which is precisely the fact the aggregate could not previously
#: express. See :func:`usvote.transform.assert_counted_totals_equal_state_sum`.
#:
#: The three measures form a ladder — **appointed >= cast >= counted** — where
#: ``total_electoral_votes`` is the appointed allotment (the D041 denominator),
#: :data:`ELECTORAL_VOTE_SHORTFALLS <usvote.transform.ELECTORAL_VOTE_SHORTFALLS>` opens
#: the first gap (appointed but never cast) and this column's status opens the second
#: (cast but never counted).
COUNTED_VOTES_COLUMN = "president_electoral_votes_counted"


def build_count_status_check(column: str = COUNT_STATUS_COLUMN) -> str:
    """Return the ``CHECK`` restricting ``column`` to :data:`COUNT_STATUS_VALUES`.

    Built from the value tuple rather than spelled out in the DDL, so the enum has
    one definition and a new value cannot be added in code while the database keeps
    rejecting it. Mirrors :func:`usvote.pv.status.build_status_column_defs`, which
    does the same for ``pv_status`` (D024 §4).
    """
    values = ", ".join(f"'{value}'" for value in COUNT_STATUS_VALUES)
    return f"CHECK ({column} IN ({values}))"


def build_counted_votes_check(
    counted: str = COUNTED_VOTES_COLUMN, cast: str = CAST_VOTES_COLUMN
) -> str:
    """Return the ``CHECK`` enforcing ``counted <= cast`` at the write boundary.

    Defense in depth for the one invariant the two measures must never violate: votes
    can be cast and not counted, never counted without being cast. The transform already
    asserts the exact biconditional on state rows and the aggregate identity on totals
    rows; this makes the weaker-but-universal half **unrepresentable** in the database,
    the same way :func:`build_count_status_check` does for the enum.
    """
    return f"CHECK ({counted} <= {cast})"
