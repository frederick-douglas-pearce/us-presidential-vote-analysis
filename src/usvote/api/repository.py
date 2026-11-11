"""The ``SnapshotRepository`` seam — the API's only data-access path (E8-S2, #96).

A deliberately thin wrapper over the read-only SQLite snapshot. It isolates the SQLite
specifics (D028's chosen store) from the route handlers so that (a) E8-S3 endpoints read
through this interface, never raw SQL, and (b) a future mart/live backend (E9) could
satisfy the same shape without rewriting routes.

**No live DB, structurally.** This module imports only :mod:`usvote.snapshot_schema`
(stdlib-only: table/column names + the :class:`~usvote.snapshot_schema.SnapshotMeta`
shape) and stdlib :mod:`sqlite3`. It must **never** import :mod:`usvote.db`, psycopg2,
:mod:`usvote.snapshot` (which drags pandas + the DB stack), or pandas — the D028
import-graph invariant, enforced by ``tests/unit/test_api_import_graph.py``.

**Connection model.** The file is opened **read-only + immutable**
(``file:…?mode=ro&immutable=1``), a fresh connection per read: independent connections
over an immutable file are safe across uvicorn's threadpool (a single shared connection
is not merely by setting ``check_same_thread=False``), microsecond-cheap, and pick up a
dev-time ``os.replace`` rebuild without a pinned stale handle. The immutable
``snapshot_meta`` row is read **once at open** and cached in memory, so ``meta()`` /
``/health`` need no connection at all.
"""

from __future__ import annotations

import sqlite3
from dataclasses import fields
from pathlib import Path
from typing import cast

from usvote.snapshot_schema import (
    DATA_COLUMNS,
    DATA_TABLE,
    HYBRID_SUMMARY_COLUMNS,
    HYBRID_SUMMARY_TABLE,
    META_TABLE,
    PER_CAPITA_COLUMNS,
    PER_CAPITA_TABLE,
    ROLLUP_COLUMNS,
    ROLLUP_TABLE,
    SNAPSHOT_SCHEMA_VERSION,
    SnapshotMeta,
)

#: Server-side row cap (D031 / #97). We fetch ``LIMIT MAX_ROWS + 1`` and **fail loud**
#: on overflow (:class:`SnapshotError`) rather than silently truncate: silent truncation
#: is exactly the drop this codebase forbids.
#:
#: **The cap sits below the fact table's size, and that is correct.** The 1824–2024
#: ``ec_pv`` surface is ~5,600 rows, so an unscoped read of it would trip the cap, and
#: none exists: every fact read goes through :meth:`_data_rows`, which always carries a
#: ``WHERE``. **Unscoped reads are allowed only on a bounded derived table whose grain
#: is its primary key** (D094, amending D031's "every endpoint is scoped" premise):
#: :meth:`national_summary_all` reads ``national_rollup`` (PK ``(year,
#: candidate_slug)``, 132 rows) and ``hybrid_summary`` (PK ``year``, one row per
#: election, 51) whole (counts measured on snapshot ``37af4064``, 2026-11-10).
#: :meth:`list_years` and :meth:`list_candidates` read whole tables too, but aggregate
#: or deduplicate to at most one row per ``(candidate, year)``. Such a read is bounded
#: by the number of elections times a small per-election count, so the cap still means
#: what it did: a read returning thousands of rows is a grain/fan-out regression (a join
#: that multiplied rows), not a large-but-valid result, and the grain tests on each
#: unscoped route are what catch it first. Headroom: the widest scoped reads are one
#: year (~357 rows), one candidate (~200) and one state (~150), the widest unscoped one
#: 132; a whole read of the ``(year, state)``-keyed ``per_capita`` table (#428) would be
#: 2,204, still under the cap.
MAX_ROWS = 5000


class SnapshotError(RuntimeError):
    """Raised when the snapshot is unusable: at startup, or when a read finds it broken.

    At startup (missing file, empty/corrupt ``snapshot_meta``, a ``schema_version`` the
    server was not built for) it fails loud at boot rather than mis-serve a stale-shape
    snapshot (D028). A read raises it too when the data breaks a guarantee the build
    should have kept — the row cap, a slug with two names, the roll-up and hybrid
    summary covering different years — and the request becomes a 500 rather than a
    silently wrong answer.
    """


class SnapshotRepository:
    """Read-only access to the SQLite snapshot behind a thin, swappable interface.

    Construct via :meth:`open`, which validates the snapshot at startup (meta row
    present, ``schema_version`` compatible) and caches the immutable provenance row. The
    data-read methods (by year / state / candidate) arrive in E8-S3; E8-S2 needs only
    :meth:`meta`.
    """

    def __init__(self, path: str, meta: SnapshotMeta) -> None:
        self._path = path
        self._meta = meta

    @classmethod
    def open(cls, snapshot_path: str) -> SnapshotRepository:
        """Open the snapshot read-only, validate it, and cache its ``snapshot_meta``.

        Fails loud (:class:`SnapshotError`) when the file has no ``snapshot_meta`` row
        or its ``schema_version`` differs from the :data:`SNAPSHOT_SCHEMA_VERSION` this
        server was built for — a mismatched snapshot would silently mis-serve.
        """
        if not Path(snapshot_path).exists():
            # The config layer already guards this (must_exist=True); belt-and-braces so
            # a repository opened directly (tests, a future caller) also fails clearly.
            raise SnapshotError(
                f"snapshot file {snapshot_path!r} does not exist — build it with "
                "`python -m usvote.snapshot` (needs the local warehouse)."
            )
        # The version is read and compared **before** the full row, and the order is
        # the point: the full read names every current ``SnapshotMeta`` field, so on a
        # snapshot of another schema it fails on a missing column and would report "not
        # a valid usvote snapshot" instead of the version mismatch — at exactly the
        # snapshot↔image cutover (D034) where the mismatch is the thing to say (#245).
        version = cls._read_schema_version(snapshot_path)
        if version != SNAPSHOT_SCHEMA_VERSION:
            raise SnapshotError(
                f"snapshot schema_version {version} != this server's "
                f"{SNAPSHOT_SCHEMA_VERSION}; rebuild the snapshot against the current "
                "code (`python -m usvote.snapshot`) or deploy a matching server."
            )
        meta = cls._read_meta(snapshot_path)
        return cls(snapshot_path, meta)

    @staticmethod
    def _connect(snapshot_path: str) -> sqlite3.Connection:
        """Open a fresh read-only, immutable connection to the snapshot file."""
        # ``as_uri`` percent-encodes the path (spaces, ``?``, ``#``, ``%``); a raw
        # f-string would let a ``?`` in the path start the query component early and
        # drop ``mode=ro``/``immutable=1``. Append our params to the encoded base.
        base = Path(snapshot_path).resolve().as_uri()
        conn = sqlite3.connect(
            f"{base}?mode=ro&immutable=1", uri=True, check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def _read_schema_version(cls, snapshot_path: str) -> object:
        """Read ``snapshot_meta.schema_version`` alone — a column every schema has."""
        conn = cls._connect(snapshot_path)
        try:
            try:
                row = conn.execute(
                    f"SELECT schema_version FROM {META_TABLE}"  # noqa: S608 — constant
                ).fetchone()
            except sqlite3.OperationalError as e:  # missing table / malformed file
                raise SnapshotError(
                    f"snapshot {snapshot_path!r} is missing the {META_TABLE} table — "
                    f"it is not a valid usvote snapshot ({e})."
                ) from e
        finally:
            conn.close()
        if row is None:
            raise SnapshotError(
                f"snapshot {snapshot_path!r} has an empty {META_TABLE} table."
            )
        return row["schema_version"]

    @classmethod
    def _read_meta(cls, snapshot_path: str) -> SnapshotMeta:
        """Read the single ``snapshot_meta`` row into a :class:`SnapshotMeta`."""
        cols = [f.name for f in fields(SnapshotMeta)]
        conn = cls._connect(snapshot_path)
        try:
            try:
                row = conn.execute(
                    f"SELECT {','.join(cols)} FROM {META_TABLE}"  # noqa: S608 — names are constants
                ).fetchone()
            except sqlite3.OperationalError as e:  # missing table / malformed file
                raise SnapshotError(
                    f"snapshot {snapshot_path!r} is missing the {META_TABLE} table — "
                    f"it is not a valid usvote snapshot ({e})."
                ) from e
        finally:
            conn.close()
        if row is None:
            raise SnapshotError(
                f"snapshot {snapshot_path!r} has an empty {META_TABLE} table."
            )
        return SnapshotMeta(**{c: row[c] for c in cols})

    def meta(self) -> SnapshotMeta:
        """Return the cached snapshot provenance (version, coverage, source/license)."""
        return self._meta

    @property
    def snapshot_version(self) -> str:
        """The content-hash version — the ETag value and the freshness key (D028)."""
        return self._meta.snapshot_version

    # --- data reads (E8-S3, #97) --------------------------------------------
    #
    # Each returns plain ``dict`` rows keyed by snapshot column (the route layer maps
    # them to public Pydantic models) — except :meth:`list_candidates`, whose ``years``
    # key is derived by grouping. Column lists are module constants, never user input,
    # so the f-string interpolation is safe (the S608 noqa).

    def _select(self, sql: str, params: tuple[object, ...]) -> list[dict[str, object]]:
        """Run a capped SELECT; fail loud if it would exceed :data:`MAX_ROWS`.

        Fetches ``LIMIT MAX_ROWS + 1`` and raises :class:`SnapshotError` on overflow — a
        grain/fan-out regression, never a silent truncation (see :data:`MAX_ROWS`).
        """
        conn = self._connect(self._path)
        try:
            rows = conn.execute(f"{sql} LIMIT ?", (*params, MAX_ROWS + 1)).fetchall()
        finally:
            conn.close()
        if len(rows) > MAX_ROWS:
            raise SnapshotError(
                f"query returned more than the {MAX_ROWS}-row cap "
                f"({sql!r}, params={params!r}) — a grain/fan-out regression; no "
                "legitimate read is this large (scoped reads, and unscoped reads of a "
                "derived table keyed by its grain, D094)."
            )
        return [dict(r) for r in rows]

    def _exists(self, column: str, value: object) -> bool:
        """Whether any ``ec_pv`` row has ``column == value`` (for clean 404s)."""
        conn = self._connect(self._path)
        try:
            row = conn.execute(
                f"SELECT 1 FROM {DATA_TABLE} WHERE {column} = ? LIMIT 1",  # noqa: S608
                (value,),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    def list_years(
        self, year_from: int | None = None, year_to: int | None = None
    ) -> list[dict[str, object]]:
        """Covered years with a distinct-candidate count and a popular-vote flag.

        ``has_popular_vote`` is ``COUNT(national_pv_votes) > 0`` — SQLite's ``COUNT`` of
        a nullable column skips nulls, so a year whose candidates all have NULL national
        popular votes counts 0. It comes back as 0/1 and pydantic coerces it to a bool.
        The flag exists so "which years can I compare popular votes for" is answerable
        from the index, without fetching a year and inspecting its nulls (#139).
        """
        clauses, params = _year_range_clauses(year_from, year_to)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._select(
            "SELECT year, COUNT(*) AS candidate_count,"  # noqa: S608
            " COUNT(national_pv_votes) > 0 AS has_popular_vote"
            f" FROM {ROLLUP_TABLE}{where} GROUP BY year ORDER BY year",
            tuple(params),
        )

    def year_exists(self, year: int) -> bool:
        """Whether the snapshot contains this year (an unknown year → 404).

        Since #139 the snapshot spans 1824–2024, so a pre-1976 year now *exists* and
        returns 200 with its EC facts and null popular votes. Only a year that was never
        an election in scope (1800, 1837) is a 404 — a genuine nonexistence, not a
        coverage gap rendered as one.
        """
        return self._exists("year", year)

    def _data_rows(
        self, clauses: list[str], params: list[object], order_by: str
    ) -> list[dict[str, object]]:
        """Capped SELECT of the full ``ec_pv`` projection under a WHERE + ORDER BY.

        The one shared seam for the by-year / by-state / by-candidate fact reads, so the
        column projection and the cap live in one place. ``clauses`` and ``order_by``
        come only from module constants, never user input (the S608 noqa).
        """
        cols = ", ".join(DATA_COLUMNS)
        return self._select(
            f"SELECT {cols} FROM {DATA_TABLE} "  # noqa: S608
            f"WHERE {' AND '.join(clauses)} ORDER BY {order_by}",
            tuple(params),
        )

    def rows_by_year(
        self, year: int, state: str | None = None, candidate: str | None = None
    ) -> list[dict[str, object]]:
        """All ``ec_pv`` state rows for a year, optionally narrowed by state/cand."""
        clauses = ["year = ?"]
        params: list[object] = [year]
        if state is not None:
            clauses.append("state_usps = ?")
            params.append(state.upper())
        if candidate is not None:
            clauses.append("candidate_slug = ?")
            params.append(candidate.lower())
        return self._data_rows(clauses, params, "state, candidate_slug")

    def rollup_by_year(self, year: int) -> list[dict[str, object]]:
        """The precomputed national roll-up rows for a year (no handler computation).

        Ordered by rank, then ``candidate_slug``: ``president_electoral_rank`` is a
        dense rank, so two candidates can share one, and without the tiebreaker their
        order would be whatever SQLite's plan gave. :meth:`national_summary_all` uses
        the same order, so the two routes agree row for row (#431).
        """
        cols = ", ".join(ROLLUP_COLUMNS)
        return self._select(
            f"SELECT {cols} FROM {ROLLUP_TABLE} WHERE year = ? "  # noqa: S608
            "ORDER BY president_electoral_rank, candidate_slug",
            (year,),
        )

    def national_summary_all(
        self,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """Every year's roll-up rows and every year's hybrid summary, whole (#431).

        Two unscoped reads, allowed because each table is a bounded derived table keyed
        by its grain (see :data:`MAX_ROWS`, D094). Rows come oldest year first, then by
        rank and ``candidate_slug`` (the per-year order); summaries oldest year first.

        **Fails loud when the two tables cover different years**, in either direction.
        The per-year route renders a missing summary as ``election: null``, because
        failing there would withhold that year's good rows. Here a missing year would
        simply be absent from a list — a gap a client can only find by cross-checking
        ``/v1/elections`` — so a mismatch raises :class:`SnapshotError` (a 500) instead.
        The snapshot build refuses the same mismatch
        (``assert_rollup_and_hybrid_summary_cover_the_same_years``); this is the serve-
        time half, for a snapshot that reached the server some other way.
        """
        rows = self._select(
            f"SELECT {', '.join(ROLLUP_COLUMNS)} FROM {ROLLUP_TABLE} "  # noqa: S608
            "ORDER BY year, president_electoral_rank, candidate_slug",
            (),
        )
        summaries = self._select(
            f"SELECT {', '.join(HYBRID_SUMMARY_COLUMNS)} "  # noqa: S608
            f"FROM {HYBRID_SUMMARY_TABLE} ORDER BY year",
            (),
        )
        # ``year`` is an INTEGER column; rows are typed as plain objects.
        row_years = {cast(int, r["year"]) for r in rows}
        summary_years = {cast(int, s["year"]) for s in summaries}
        if row_years != summary_years:
            raise SnapshotError(
                "national_rollup and hybrid_summary cover different years: roll-up "
                f"only {sorted(row_years - summary_years)}, summary only "
                f"{sorted(summary_years - row_years)}; the build should have refused "
                "this snapshot (D094)."
            )
        return rows, summaries

    def hybrid_summary_by_year(self, year: int) -> dict[str, object] | None:
        """The per-election hybrid summary for a year, or ``None`` if absent (#102).

        Returns a **single row or None**, not a list, because the table's grain is
        ``year`` alone — the three winners, two flips and three margins are properties
        of the election. Returning a one-element list would invite a caller to iterate
        and quietly tolerate the two-row case that the table's PRIMARY KEY makes
        impossible.

        ``None`` is a real answer rather than an error: it means the snapshot has no
        summary for that year. Callers gate on the year's existence separately (the
        routes already 404 on an unknown year before reading this), so ``None`` here
        signals a build gap, and the route renders it as a null ``election`` key rather
        than failing the whole response — the fact rows are still good.
        """
        cols = ", ".join(HYBRID_SUMMARY_COLUMNS)
        rows = self._select(
            f"SELECT {cols} FROM {HYBRID_SUMMARY_TABLE} WHERE year = ?",  # noqa: S608
            (year,),
        )
        return rows[0] if rows else None

    def per_capita_by_year(
        self, year: int, state: str | None = None
    ) -> list[dict[str, object]]:
        """The ``per_capita`` rows for a year, optionally one state (#245)."""
        clauses = ["year = ?"]
        params: list[object] = [year]
        if state is not None:
            clauses.append("state_usps = ?")
            params.append(state.upper())
        return self._per_capita_rows(clauses, params, "state")

    def per_capita_by_state(
        self, usps: str, year_from: int | None = None, year_to: int | None = None
    ) -> list[dict[str, object]]:
        """The ``per_capita`` rows for one state across years (#245)."""
        clauses = ["state_usps = ?"]
        params: list[object] = [usps.upper()]
        extra, extra_params = _year_range_clauses(year_from, year_to)
        clauses += extra
        params += extra_params
        return self._per_capita_rows(clauses, params, "year")

    def _per_capita_rows(
        self, clauses: list[str], params: list[object], order_by: str
    ) -> list[dict[str, object]]:
        """Capped SELECT of the ``per_capita`` projection — :meth:`_data_rows`' twin."""
        cols = ", ".join(PER_CAPITA_COLUMNS)
        return self._select(
            f"SELECT {cols} FROM {PER_CAPITA_TABLE} "  # noqa: S608
            f"WHERE {' AND '.join(clauses)} ORDER BY {order_by}",
            tuple(params),
        )

    def state_exists(self, usps: str) -> bool:
        """Whether the snapshot contains this USPS state code (else 404)."""
        return self._exists("state_usps", usps.upper())

    def rows_by_state(
        self, usps: str, year_from: int | None = None, year_to: int | None = None
    ) -> list[dict[str, object]]:
        """All ``ec_pv`` rows for one state across years (optional year window)."""
        clauses = ["state_usps = ?"]
        params: list[object] = [usps.upper()]
        extra, extra_params = _year_range_clauses(year_from, year_to)
        clauses += extra
        params += extra_params
        return self._data_rows(clauses, params, "year, candidate_slug")

    def candidate_exists(self, slug: str) -> bool:
        """Whether the snapshot contains this candidate slug (else 404)."""
        return self._exists("candidate_slug", slug.lower())

    def rows_by_candidate(
        self, slug: str, year_from: int | None = None, year_to: int | None = None
    ) -> list[dict[str, object]]:
        """All ``ec_pv`` rows for one candidate across years (optional year window)."""
        clauses = ["candidate_slug = ?"]
        params: list[object] = [slug.lower()]
        extra, extra_params = _year_range_clauses(year_from, year_to)
        clauses += extra
        params += extra_params
        return self._data_rows(clauses, params, "year, state")

    def list_candidates(self) -> list[dict[str, object]]:
        """Every candidate in ``ec_pv``: slug, display name and sorted years (#330).

        Read from ``ec_pv``, the table :meth:`candidate_exists` keys on, so the index
        and the by-slug 404 can never disagree about which slugs exist.
        ``national_rollup`` would spare the ``DISTINCT`` but split listing and
        existence across two tables.

        The ``(slug, name, year)`` triples are deduplicated in SQL and grouped here, not
        in the handler (routes stay free of aggregation). A slug arriving with a second
        display name raises :class:`SnapshotError`: the build's slug-collision guard
        (``snapshot.add_candidate_slug``) makes that unreachable through the real
        writer, and the alternatives — a duplicate slug, or one name chosen silently —
        would break "one item per candidate" without a sound.
        """
        rows = self._select(
            f"SELECT DISTINCT candidate_slug, candidate, year FROM {DATA_TABLE} "  # noqa: S608
            "ORDER BY candidate_slug, year",
            (),
        )
        grouped: list[tuple[object, object, list[object]]] = []
        for row in rows:
            slug, name, year = row["candidate_slug"], row["candidate"], row["year"]
            if grouped and grouped[-1][0] == slug:
                if grouped[-1][1] != name:
                    raise SnapshotError(
                        f"candidate slug {slug!r} carries two display names "
                        f"({grouped[-1][1]!r}, {name!r}) — a slug collision the "
                        "build should have refused."
                    )
                grouped[-1][2].append(year)
            else:
                grouped.append((slug, name, [year]))
        return [
            {"candidate_slug": slug, "candidate": name, "years": years}
            for slug, name, years in grouped
        ]


def _year_range_clauses(
    year_from: int | None, year_to: int | None
) -> tuple[list[str], list[object]]:
    """Build ``year >= ?`` / ``year <= ?`` SQL fragments for an optional window."""
    clauses: list[str] = []
    params: list[object] = []
    if year_from is not None:
        clauses.append("year >= ?")
        params.append(year_from)
    if year_to is not None:
        clauses.append("year <= ?")
        params.append(year_to)
    return clauses, params
