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

from usvote.snapshot_schema import (
    META_TABLE,
    SNAPSHOT_SCHEMA_VERSION,
    SnapshotMeta,
)


class SnapshotError(RuntimeError):
    """Raised when the snapshot cannot be opened or is incompatible at startup.

    A startup-time failure (missing file, empty/corrupt ``snapshot_meta``, a
    ``schema_version`` the server was not built for) — fail loud at boot rather than
    mis-serve a stale-shape snapshot or 500 per request (D028).
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
        meta = cls._read_meta(snapshot_path)
        if meta.schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise SnapshotError(
                f"snapshot schema_version {meta.schema_version} != this server's "
                f"{SNAPSHOT_SCHEMA_VERSION}; rebuild the snapshot against the current "
                "code (`python -m usvote.snapshot`) or deploy a matching server."
            )
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
