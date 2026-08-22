"""Unit tests for the whole-warehouse orchestrator (``usvote.warehouse``).

Drives :func:`run_warehouse` with the four wired steps (EC / MIT / UCSB pipelines +
:func:`rebuild_views`) monkeypatched to recorders, so the test asserts the *composition*
— call order, the ``replace`` mapping (EC destructive, PV additive), the explicit UCSB
skip, and the :class:`WarehouseResult` receipt — without touching a real DB or the stage
internals (those have their own tests). Also enforces the D015/D027 composition-root
invariant: nothing under ``usvote/{mit,ucsb,pv}/`` imports ``usvote.warehouse``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

import usvote.warehouse as warehouse
from tests._helpers import RecordingConnection, make_dbc
from usvote.db import DBC
from usvote.warehouse import (
    SOURCE_EC,
    SOURCE_MIT,
    SOURCE_UCSB,
    WarehouseResult,
    run_warehouse,
)


@pytest.fixture
def dbc() -> DBC:
    """A real ``DBC`` over a recording fake — inert here (the pipelines are patched)."""
    return make_dbc(RecordingConnection())


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Patch the four steps to record ``(name, kwargs)`` in call order.

    Return values match each real step's shape so ``run_warehouse`` can measure row
    counts: EC -> ``(candidates, state, votes)``, MIT -> loaded frame, UCSB ->
    ``(pv_votes, roster)``. Lists stand in for frames (only ``len`` is read).
    """
    calls: list[tuple[str, dict[str, Any]]] = []

    def ec(
        dbc: object, shapefile_path: str, *, replace: bool = False,
        years: Any = None, **_: Any,
    ) -> tuple[list[int], list[int], list[int]]:
        calls.append(("ec", {"replace": replace, "years": years}))
        return ([], [], [0] * 5)  # 5 votes rows

    def mit(
        dbc: object, path: Any = None, *, years: Any = None,
        environ: Any = None, replace: bool = False, **_: Any,
    ) -> tuple[list[int], list[int]]:
        calls.append(("mit", {"path": path, "replace": replace, "years": years}))
        return ([0] * 3, [0] * 6)  # 3 pv_votes, 6 roster (#127)

    def ucsb(
        dbc: object, html_dir: Any = None, *, years: Any = None,
        environ: Any = None, replace: bool = False, **_: Any,
    ) -> tuple[list[int], list[int]]:
        calls.append(
            ("ucsb", {"html_dir": html_dir, "replace": replace, "years": years})
        )
        return ([0] * 2, [0] * 4)  # 2 pv_votes, 4 roster

    def views(dbc: object) -> None:
        calls.append(("views", {}))

    monkeypatch.setattr(warehouse, "run_ec_pipeline", ec)
    monkeypatch.setattr(warehouse, "run_mit_pipeline", mit)
    monkeypatch.setattr(warehouse, "run_ucsb_pipeline", ucsb)
    monkeypatch.setattr(warehouse, "rebuild_views", views)
    return calls


def test_full_build_sequences_ec_mit_ucsb_views(
    dbc: DBC, recorder: list[tuple[str, dict[str, Any]]]
) -> None:
    result = run_warehouse(
        dbc, "states.shp", "mit.csv", ucsb_html_dir="snap/", years={2016, 2020}
    )

    assert [name for name, _ in recorder] == ["ec", "mit", "ucsb", "views"]
    assert result == WarehouseResult(
        ec_rows=5,
        mit_rows=3,
        mit_roster_rows=6,
        ucsb_pv_rows=2,
        ucsb_roster_rows=4,
        sources_loaded=frozenset({SOURCE_EC, SOURCE_MIT, SOURCE_UCSB}),
        views_built=True,
    )


def test_replace_maps_destructive_to_ec_additive_to_pv(
    dbc: DBC, recorder: list[tuple[str, dict[str, Any]]]
) -> None:
    # ``replace=True`` is the EC-schema rebuild (which cascades the PV tables/views); the
    # PV sources must load ``replace=False`` onto the fresh schema. The views always
    # rebuild regardless, so a ``--replace`` build is not left view-less.
    run_warehouse(dbc, "states.shp", "mit.csv", ucsb_html_dir="snap/", replace=True)

    by_name = dict(recorder)
    assert by_name["ec"]["replace"] is True
    assert by_name["mit"]["replace"] is False
    assert by_name["ucsb"]["replace"] is False
    assert "views" in {name for name, _ in recorder}


def test_ucsb_skipped_when_dir_is_none(
    dbc: DBC, recorder: list[tuple[str, dict[str, Any]]]
) -> None:
    # The explicit D024 seam: ``ucsb_html_dir=None`` skips UCSB (no env magic here), and
    # the receipt says so — UCSB counts are None, UCSB absent from ``sources_loaded`` —
    # while the views still build over the EC + MIT core.
    result = run_warehouse(dbc, "states.shp", "mit.csv")

    assert [name for name, _ in recorder] == ["ec", "mit", "views"]
    assert result.ucsb_pv_rows is None
    assert result.ucsb_roster_rows is None
    assert result.sources_loaded == frozenset({SOURCE_EC, SOURCE_MIT})
    assert result.views_built is True


def test_years_threads_to_every_source(
    dbc: DBC, recorder: list[tuple[str, dict[str, Any]]]
) -> None:
    run_warehouse(dbc, "states.shp", "mit.csv", ucsb_html_dir="snap/", years={1976})

    for name, kwargs in recorder:
        if name != "views":
            assert kwargs["years"] == {1976}, f"{name} did not receive years"


def test_close_forwarded_only_after_views(monkeypatch: pytest.MonkeyPatch) -> None:
    # ``close`` is the orchestrator's — it closes ``dbc`` after the whole build, never
    # threaded into the per-source pipelines (each is called with its default
    # close=False), so no pipeline closes the shared connection mid-build. ``rebuild_views``
    # records "views" and must land before the connection close.
    order: list[str] = []

    def ec(*a: Any, **k: Any) -> tuple[list[int], list[int], list[int]]:
        return ([], [], [])

    def views(dbc: object) -> None:
        order.append("views")

    monkeypatch.setattr(warehouse, "run_ec_pipeline", ec)
    monkeypatch.setattr(warehouse, "run_mit_pipeline", lambda *a, **k: ([], []))
    monkeypatch.setattr(warehouse, "rebuild_views", views)

    conn = RecordingConnection()
    run_warehouse(make_dbc(conn), "states.shp", "mit.csv", close=True)

    assert order == ["views"]
    assert conn.closed  # the connection was closed after the views were built


def test_no_pv_source_imports_the_warehouse_composition_root() -> None:
    """D015/D027: ``warehouse`` imports from every source; a back-import inverts D015.

    ``warehouse.py`` is a composition root (allowed to import EC + both PV subpackages),
    but the exemption only stays honest if the dependency never runs the other way. Mirror
    the greppable ``dwh.votes`` invariant with an enforced test: no module under
    ``usvote/{mit,ucsb,pv}/`` may import ``usvote.warehouse``.
    """
    pkg_root = Path(warehouse.__file__).parent
    pattern = re.compile(r"(^|\W)(import\s+usvote\.warehouse|from\s+usvote\.warehouse)")
    offenders = [
        py.relative_to(pkg_root).as_posix()
        for sub in ("mit", "ucsb", "pv")
        for py in (pkg_root / sub).rglob("*.py")
        if pattern.search(py.read_text())
    ]
    assert not offenders, f"these must not import usvote.warehouse: {offenders}"


# --- #124: the hybrid views join the rebuild chain --------------------------


def test_rebuild_views_sequences_union_then_join_then_hybrid(
    dbc: DBC, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The order is a dependency chain, so **order** is what this asserts, not presence.

    ``create_ec_pv_views`` reads the resolved PV views and ``create_hybrid_views`` reads
    the join views, so a rebuild that ran them in any other order would fail against a
    fresh schema — and would fail *silently* against a warehouse whose views already
    exist from a previous build, which is the case a presence-only assert would miss.
    """
    calls: list[str] = []
    monkeypatch.setattr(
        warehouse, "build_pv_union", lambda _dbc: calls.append("union")
    )
    monkeypatch.setattr(
        warehouse, "create_ec_pv_views", lambda _dbc: calls.append("join")
    )
    monkeypatch.setattr(
        warehouse, "create_hybrid_views", lambda _dbc: calls.append("hybrid")
    )

    warehouse.rebuild_views(dbc)

    assert calls == ["union", "join", "hybrid"]


def test_a_replace_build_still_rebuilds_the_hybrid_views(
    dbc: DBC, recorder: list[tuple[str, dict[str, Any]]]
) -> None:
    """``replace=True`` drops the schema (and every view with it), so the rebuild must
    still be the final step — otherwise E7's analysis surface and #102's read seam
    (D039) would be missing after a full rebuild.
    """
    run_warehouse(dbc, "states.shp", "mit.csv", replace=True)

    assert [name for name, _ in recorder] == ["ec", "mit", "views"]
    assert recorder[0][1]["replace"] is True, "EC is the destructive step"
