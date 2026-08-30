"""Shared, non-fixture test helpers.

Plain helpers (fake connections, ``DBC`` builders, the state-name set, the
fixtures-dir path) live here rather than in ``conftest.py`` so tests at any
depth — ``tests/unit/`` and ``tests/integration/`` alike — can import them via
a stable absolute path (``from tests._helpers import ...``) without importing
from a conftest module (a pytest anti-pattern). ``conftest.py`` is reserved for
fixtures, which pytest discovers automatically.

The recording fake connection lets unit tests assert on the SQL strings ``DBC``
builds without a live Postgres; the EC and future ``usvote/ucsb`` /
``usvote/mit`` load stages all construct a ``DBC`` and will want the same seam.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import pytest

import usvote.db as db_module
from usvote.db import DBC

# Saved Archives HTML replayed offline; centralized here so tests at any depth
# reference the one path instead of recomputing ``Path(__file__).parent`` per
# file (which shifts under ``tests/integration/``).
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# A small sample of real rows from the MIT Election Lab ``1976-2024-president.csv``
# (CC0 1.0). 13 rows across 1976/2000/2016/2024 covering DC, a minor/OTHER
# candidate, an EC/PV-split year, and a ``writein=True`` row with NaN candidate/
# party — enough to seed the MIT read (#64) and later transform tests offline.
MIT_SAMPLE_CSV = FIXTURES_DIR / "mit_1976-2024-president_sample.csv"

# A small, deliberately *self-consistent* MIT sample for the transform tests
# (#65): unlike ``MIT_SAMPLE_CSV`` (a candidate-subset, so its per-state votes do
# not sum to ``totalvotes``), every (year, state) here carries its complete
# candidate set so ``sum(candidatevotes) == totalvotes`` holds — required to
# exercise the pre-filter reconciliation. Covers 2000 FL (a minor GREEN/OTHER
# candidate to drop) and 2016 NY (Clinton/Trump fusion lines coded OTHER on their
# secondary rows, a LIBERTARIAN to drop, and a write-in) — the cases that prove
# fusion-aggregation-before-filter and the D019 {DEMOCRAT, REPUBLICAN} scope.
MIT_FUSION_SAMPLE_CSV = FIXTURES_DIR / "mit_fusion_sample.csv"

# The synthetic UCSB fixtures that carry a state table, mapped to the year each is
# parsed as and the header layout it pins. Excludes the L0 (summary-only) fixture,
# which by design has no popular-vote grid.
#
# Single source of truth on purpose: test_ucsb_parse.py (layout, absence, and sum
# assertions) and test_ucsb_fixtures.py (the fixture-realism identity) each held their
# own copy, so adding a fixture to one and not the other silently shrank coverage with
# nothing failing — the same "a fixture bug and a parser bug look identical" trap the
# #34 integrity suite exists to close.
UCSB_PV_FIXTURES: dict[str, tuple[int, str]] = {
    "2group": (1876, "L1"),
    "4group": (1824, "L1"),
    "nocolspan": (1836, "L1b"),
    "dashdash": (1948, "L2"),
    "missing_states": (1864, "L1"),
    "inline_cd": (2020, "L3"),
    "1976": (1976, "L1c"),
}


def ucsb_fixture_html(stem: str) -> str:
    """Read a synthetic UCSB fixture by its stem (e.g. ``"dashdash"``)."""
    return (FIXTURES_DIR / f"ucsb_synthetic_{stem}.html").read_text(encoding="utf-8")


# A regenerable snapshot of the EC participation roster — ``{year: {"states": [...],
# "zero_ev_states": [...]}}`` for every in-scope UCSB year — so the #36 two-way roster
# assert can be exercised against REAL 1824/1864/1876 shapes offline. Unlike the UCSB
# corpus this is National Archives data (public domain), so committing it is fine under
# D022; and unlike ``UCSB_NONPARTICIPATING_STATES`` it is **test input only** — a test
# asserts nothing under ``src/`` reads it, so it cannot become a second source of
# participation truth (D006). Carries no electoral-vote *counts*, only the zero/non-zero
# split the D024 §5 cross-check needs, for the same reason.
EC_ROSTER_FIXTURE = FIXTURES_DIR / "ec_state_roster_by_year.json"


def ec_participation_frame(years: Iterable[int] | None = None) -> pd.DataFrame:
    """Build a ``dwh.votes``-shaped participation frame from the roster fixture.

    Shaped like the frame :func:`usvote.transform.transform_parsed_years` returns and
    like a ``SELECT`` of ``dwh.votes`` — including a **totals row per year** (``state``
    NULL, ``is_total`` True), because excluding those is exactly what the roster
    derivation must get right (D024 §6).

    ``total_electoral_votes`` is synthesized as 0 for the fixture's zero-EV states and a
    nonzero placeholder otherwise: only the zero/non-zero distinction is meaningful, and
    committing real counts would edge toward a second source of EV truth (D024 §5).
    """
    entries = json.loads(EC_ROSTER_FIXTURE.read_text(encoding="utf-8"))["years"]
    wanted = None if years is None else {int(y) for y in years}
    rows: list[dict[str, Any]] = []
    for raw_year, entry in entries.items():
        year = int(raw_year)
        if wanted is not None and year not in wanted:
            continue
        zero_ev = set(entry["zero_ev_states"])
        for state in entry["states"]:
            rows.append({
                "year": year,
                "state": state,
                "is_total": False,
                "total_electoral_votes": 0 if state in zero_ev else 5,
            })
        rows.append({
            "year": year,
            "state": None,
            "is_total": True,
            "total_electoral_votes": 99,
        })
    return pd.DataFrame(rows)


# A regenerable snapshot of the EC president-EV getters — ``{year: [canonical name, ...]}``
# for every in-scope UCSB year — so the #38 reciprocal completeness guard can be exercised
# against the REAL Archives getter set offline. Like ``EC_ROSTER_FIXTURE`` it is National
# Archives data (public domain, fine under D022) and **test input only** — a test asserts
# nothing under ``src/`` reads it, so it cannot become the reconcile map's own witness (that
# would make the completeness guard circular, D006). Carries no electoral-vote *counts*
# (D024 §5); the frame synthesizes a nonzero placeholder, since only getter identity matters.
EC_GETTERS_FIXTURE = FIXTURES_DIR / "ec_getters_by_year.json"


def ec_getters_frame(years: Iterable[int] | None = None) -> pd.DataFrame:
    """Build an ``ec_getters``-shaped frame (the #38 reconcile DI seam) from the fixture.

    Shaped like ``dwh.votes`` joined to ``dwh.candidate`` filtered to president-EV getters:
    ``year``, ``candidate`` (canonical name), ``president_electoral_votes``. The EV value is
    a nonzero placeholder — the fixture stores only identity (D024 §5), and the completeness
    guard needs only ``> 0`` — so it must not be read as a real electoral-vote count.
    """
    entries = json.loads(EC_GETTERS_FIXTURE.read_text(encoding="utf-8"))["years"]
    wanted = None if years is None else {int(y) for y in years}
    rows: list[dict[str, Any]] = [
        {"year": int(raw_year), "candidate": name, "president_electoral_votes": 1}
        for raw_year, names in entries.items()
        if wanted is None or int(raw_year) in wanted
        for name in names
    ]
    return pd.DataFrame(rows)


# The valid US state names Table 2 rows are matched against — the package
# equivalent of the notebook's geopandas ``NAME`` set (50 states + DC). Shared by
# the parse tests (the state-name filter) and the transform tests (the geo
# dimension set), so the two stay in lockstep — the SSOT coupling #31 externalizes.
STATE_NAMES = frozenset({
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "District of Columbia", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
    "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
    "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
    "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
})


class RecordingCursor:
    """Cursor that appends every executed query to a shared log.

    Implements the context-manager protocol so it works inside
    ``with conn.cursor() as curs:``.
    """

    def __init__(self, executed: list[str]) -> None:
        self._executed = executed

    def __enter__(self) -> RecordingCursor:
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        return False

    def execute(self, query: str, vars: object = None) -> None:
        self._executed.append(query)


class RecordingConnection:
    """Fake psycopg2 connection that records SQL and its own close state.

    Supports the context-manager protocol (``with self.conn as conn``) the way psycopg2
    connections do — yielding the connection itself and, on exit, committing on a clean
    block or rolling back on an exception. ``commit``/``rollback`` are counted (and the
    ``with``-exit routes through them) so a test can assert how a load transacts:
    ``DBC.transaction`` calls them explicitly, and the per-statement ``with self.conn``
    path in :meth:`usvote.db.DBC._execute` records one commit per statement. ``autocommit``
    defaults to ``False`` (as a fresh psycopg2 connection does) and is readable/settable so
    the ``transaction()`` autocommit guard can be exercised.
    """

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.closed = False
        self.commits = 0
        self.rollbacks = 0
        self.autocommit = False

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self.executed)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def __enter__(self) -> RecordingConnection:
        return self

    def __exit__(self, exc_type: object, *rest: object) -> Literal[False]:
        # Mirror psycopg2: a ``with connection`` block commits on clean exit, rolls back
        # on exception. Neither closes the connection. Never suppress the exception.
        if exc_type is None:
            self.commits += 1
        else:
            self.rollbacks += 1
        return False

    def close(self) -> None:
        self.closed = True


def make_dbc(conn: RecordingConnection) -> DBC:
    """Build a :class:`DBC` wired to a fake connection instead of a real Postgres.

    Shared by every load-path test (db / load / pipeline), which all construct a
    ``DBC`` over the recording connection to assert on the SQL it builds.
    """
    return DBC({"dbname": "test"}, connect=lambda **_: conn)


class QueryDispatchDBC:
    """A read-only ``DBC`` stand-in that answers by matching a relation in the query.

    Deliberately not a mock: the callers under test are expected to *issue the reads
    they claim*, so this serves real frames and records every query for the caller to
    assert on (``pv_votes`` never appearing is a real assertion in the #167 tests).

    ``routes`` maps a substring of the SQL — normally a relation name — to the frame to
    return; the first match in insertion order wins, and ``default`` answers anything
    unmatched. It implements only ``select_query_to_df``, which is all a read-only seam
    uses, so a caller that takes a ``DBC`` casts at the call site — and keeps the stub
    itself, since ``.queries`` is usually the point.
    """

    def __init__(
        self, routes: dict[str, pd.DataFrame], default: pd.DataFrame
    ) -> None:
        self.routes = routes
        self.default = default
        self.queries: list[str] = []

    def select_query_to_df(self, query: str) -> pd.DataFrame:
        self.queries.append(query)
        for needle, frame in self.routes.items():
            if needle in query:
                return frame.copy()
        return self.default.copy()


def record_inserts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Patch ``usvote.db.execute_values`` to capture ``(sql, argslist)``; return the log.

    ``insert_df_into_table`` routes through the module-level ``execute_values``
    rather than ``cursor.execute``, so the recording cursor never sees the INSERTs
    — patch at the ``usvote.db`` lookup site to record them.
    """
    calls: list[tuple[str, Any]] = []

    def fake_execute_values(cur: object, sql: str, argslist: Any, **_: object) -> None:
        calls.append((sql, argslist))

    monkeypatch.setattr(db_module, "execute_values", fake_execute_values)
    return calls


def fake_state_geo() -> pd.DataFrame:
    """A plain-pandas stand-in for ``transform.load_state_geo`` output.

    All 50 states + DC, plus Puerto Rico to prove territories are dropped, with
    REGION/DIVISION as strings (TIGER ships them so) to prove the astype-to-int in
    ``build_state_dim``. Shared by the transform, load, and pipeline tests so none
    of them needs the real TIGER shapefile.
    """
    rows = []
    for i, name in enumerate(sorted(STATE_NAMES)):
        rows.append({
            "NAME": name, "REGION": str(i % 4 + 1), "DIVISION": str(i % 9 + 1),
            "STATENS": f"{i:08d}", "GEOID": f"{i:02d}", "STUSPS": name[:2].upper(),
            "ALAND": 1000 + i, "AWATER": i,
            "INTPTLAT": f"+{30 + i % 20}.0", "INTPTLON": f"-{70 + i % 40}.0",
        })
    rows.append({
        "NAME": "Puerto Rico", "REGION": "9", "DIVISION": "9", "STATENS": "72000000",
        "GEOID": "72", "STUSPS": "PR", "ALAND": 1, "AWATER": 1,
        "INTPTLAT": "+18.0", "INTPTLON": "-66.0",
    })
    return pd.DataFrame(rows)


def non_null_flag(value: object, *, label: str) -> bool:
    """A boolean cell normalized to a Python ``bool``, rejecting every NULL shape loudly.

    Exists because neither ``is`` nor ``bool(...)`` is correct on its own for a nullable
    boolean, and which one is wrong depends on data the assert cannot see (#165):

    - **From a live view.** ``pd.read_sql`` types a boolean column as ``object`` (cells are
      Python ``bool``/``None``) when it carries a NULL, and as ``bool`` (cells are
      ``numpy.bool_``) when it does not. So ``cell is False`` passes on the first and fails
      on the second **against a correct value**, while ``bool(cell)`` maps ``None`` to
      ``False`` — silently turning a ``NULL`` into a passing false. That laundering is what
      #165 was filed for.
    - **From the pandas builders.** :func:`usvote.hybrid.build_hybrid_summary` nulls as
      ``pd.NA``, where ``bool(pd.NA)`` raises ``TypeError`` — loud, but an exception rather
      than a diagnosis. A null *float* materializes as ``np.nan`` instead, which is the
      fourth spelling and the one that defeats ``is not None``.

    Rejecting all four and returning the Python singleton lets a call site keep the readable
    ``is True`` / ``is False`` spelling and have it mean what it says, on either path and
    under either dtype::

        assert non_null_flag(summary.loc[2000, "hybrid_flip"], label="2000 hybrid_flip") is False

    ``label`` is required and names the cell in every failure message: the value alone
    cannot say where it was read, and a helper whose whole job is a good diagnosis should
    not be callable without one.

    **The message deliberately does not name a producing function.** This guards flips
    (:func:`usvote.hybrid._flip`) *and* ``ec_determinative``, whose NULL comes from
    ``build_hybrid_summary``'s own ``pd.NA`` branch and, in SQL, from a filtered
    ``bool_or`` — so a hardcoded pointer would send half its callers to the wrong place.
    ``label`` carries the specifics instead.
    """
    _non_null_scalar(value, label=label)
    assert isinstance(value, bool | np.bool_), (
        f"{label} is not a boolean cell: {value!r} ({type(value).__name__}). "
        f"bool() would coerce it silently, which is the class of bug this guards."
    )
    return bool(value)


def non_null_sqlite_flag(value: object, *, label: str) -> bool:
    """The :func:`non_null_flag` of the **SQLite tier**, where a boolean is an ``int``.

    The API snapshot stores every boolean as ``INTEGER`` (``usvote/snapshot.py``'s
    ``_create_tables``: ``ec_determinative INTEGER``, ``pv_flip INTEGER``,
    ``hybrid_flip INTEGER``, ``took_office INTEGER``), and ``sqlite3`` is opened without
    ``detect_types``, so a read hands back a Python ``int`` — ``1``, ``0``, or ``None`` for
    NULL. Neither half of that is what :func:`non_null_flag` accepts: it rejects an ``int``
    on purpose, because from a *pandas* cell an int is a dtype defect. Hence two helpers
    rather than one widened one — each strict about the dtype its own tier actually
    produces, which catches more than a union-permissive helper would (#172).

    The laundering it removes is the same one #165 named, and it is **live** in this tier:
    ``bool(None) is False`` evaluates to ``True``, so an unguarded False-leg over a SQLite
    read passes on a NULL. ``bool(None) is True`` fails, which is why only the False legs
    were ever silent.

    **Returns the Python singleton**, never the raw ``int``: ``1 is True`` is ``False``, so
    a call site keeping the readable spelling would flip from green to red if this handed
    back what SQLite gave it::

        assert non_null_sqlite_flag(row["pv_flip"], label="2016 pv_flip") is True

    **Accepts a plain ``int`` valued 0 or 1 and nothing else** — not ``None``, not any other
    ``int``, not floats or strings, and **not a Python ``bool`` or a ``numpy.bool_``**. The
    type check is ``type(value) is int``, not ``isinstance``, and the difference is the whole
    of the split: ``isinstance(True, int)`` is ``True``, so an ``isinstance`` check would
    accept a Python ``bool`` — which is precisely what ``pd.read_sql`` yields for a boolean
    column **that carries a NULL** (an ``object`` column of Python ``bool``/``None`` cells,
    the #165 case). A helper meant to be un-confusable with the pandas one that silently
    accepts the pandas tier's nullable spelling is not un-confusable at all; it just fails to
    say so. ``type(value) is int`` refuses every pandas spelling, which is what makes "each
    rejects the other tier's dtype" a property rather than a wish.

    SQLite gives up nothing by this: without ``detect_types`` it returns an ``int`` for an
    ``INTEGER`` column, never a ``bool``, so no real call site is narrowed by the stricter
    check. ``test_the_two_helpers_are_not_interchangeable`` pins both directions, including
    the object-dtype Python ``bool`` that motivated the change.

    ``label`` is required, for the reason :func:`non_null_flag` gives.
    """
    _non_null_scalar(value, label=label)
    # ``type(value) is int`` and not ``isinstance``: bool is an int subclass, so isinstance
    # would accept the Python ``bool`` that pd.read_sql yields for a NULL-carrying boolean
    # column — the one pandas spelling this helper most needs to refuse. See the docstring.
    assert type(value) is int, (
        f"{label} is not a SQLite boolean cell: {value!r} "
        f"({type(value).__module__}.{type(value).__name__}). SQLite hands back a plain int "
        f"for an INTEGER column; anything else — a bool, a float, a numpy scalar — means "
        f"this was read from pandas, and non_null_flag is the helper for that tier. "
        f"(The type name carries its module because numpy.bool's bare __name__ is 'bool', "
        f"identical to Python's, so an unqualified name cannot say which was passed.)"
    )
    assert value in (0, 1), (
        f"{label} is not a 0/1 flag: {value!r}. An INTEGER column storing a boolean holds "
        f"only 0 or 1, so any other value means the column is not the flag it was read as."
    )
    return bool(value)


def _non_null_scalar(value: object, *, label: str) -> None:
    """The half :func:`non_null_flag` and :func:`non_null_sqlite_flag` share.

    Single-sourced because it is the half that is identical between the two tiers — a cell
    must be one scalar and must not be NULL, whatever dtype it arrives as. Each public
    helper keeps its own dtype assert inline rather than parameterizing it here.
    """
    assert pd.api.types.is_scalar(value), (
        f"{label} is not a scalar cell: {value!r} ({type(value).__name__}). Pass a single "
        f"cell — a Series or array would make the null check below ambiguous, and a "
        f"one-element sequence would slip past it entirely."
    )
    assert not pd.isna(value), (
        f"{label} came back NULL — a NULL boolean here is the 'no value derived' "
        f"encoding, which means the derivation broke. It is never a legitimate false."
    )


def narrow_mit_spine_to_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scope MIT's D024 roster read to the states its fusion sample actually covers.

    Since #127 ``run_mit_pipeline`` derives its roster from the **EC spine** — the
    independence that makes ``assert_roster_covers_facts`` a real silent-drop guard
    rather than a frame compared against itself. That guard is strict by design: every
    ``popular_vote`` roster state must have vote rows.

    ``MIT_FUSION_SAMPLE_CSV`` is a deliberate **two-state extract** (2000 Florida, 2016
    New York) chosen to exercise fusion aggregation, while the EC fixtures seed the
    *real* Archives spine — all 51 jurisdictions per year. Run together, the guard
    correctly reports the other 50 states as missing: the pair models an MIT load that
    could not exist, and before #127 nothing could see that.

    Rather than weaken the guard or grow the sample to 51 states x 2 years, these
    integration tests narrow the participation read to the sample's own states. The
    shipped path is otherwise untouched, and the derivation itself is covered
    exhaustively offline in ``tests/unit/test_pv_status.py`` — including the case this
    narrowing suppresses (a spine state the source lost must raise).
    """
    from usvote.mit import pipeline as mit_pipeline

    real = mit_pipeline.read_ec_participation

    def narrowed(dbc: Any, *, years: Any = None) -> pd.DataFrame:
        frame = real(dbc, years=years)
        sample = pd.read_csv(MIT_FUSION_SAMPLE_CSV)
        # Narrow per ``(year, state)``, not per state: the sample carries Florida in
        # 2000 and New York in 2016, so a state-only filter would leave Florida in the
        # 2016 roster with no 2016 vote rows — and the guard would (correctly) fire.
        pairs = {(int(y), str(s).title()) for y, s in zip(sample["year"], sample["state"], strict=True)}
        keep = [
            bool(pd.isna(s)) or (int(y), str(s)) in pairs
            for y, s in zip(frame["year"], frame["state"], strict=True)
        ]
        return frame[keep]

    monkeypatch.setattr(mit_pipeline, "read_ec_participation", narrowed)
