"""Unit tests for the whole-warehouse orchestrator (``usvote.warehouse``).

Drives :func:`run_warehouse` with the four wired steps (EC / MIT / UCSB pipelines +
:func:`rebuild_views`) monkeypatched to recorders, so the test asserts the *composition*
— call order, the ``replace`` mapping (EC destructive, PV additive), the explicit UCSB
skip, and the :class:`WarehouseResult` receipt — without touching a real DB or the stage
internals (those have their own tests). Also enforces the D015/D027 composition-root
invariant: nothing under ``usvote/{mit,ucsb,pv}/`` imports ``usvote.warehouse``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import usvote.warehouse as warehouse
from tests._helpers import RecordingConnection, make_dbc
from tests.unit.test_layering import imports
from usvote.db import DBC
from usvote.pv.overlap import OverlapKey, OverlapReport
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


#: A clean gate verdict for the stubs below — the #167 gates read the live views, which
#: a stub ``DBC`` cannot serve, so every ``run_warehouse`` test substitutes this.
_CLEAN_REPORT = OverlapReport(cells=2, exact=2, exact_pct=100.0)


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
    # The two #167 gates read the live views, so they are stubbed clean here rather
    # than recorded -- every test using this fixture drives the default
    # ``validate_overlap=True``
    # against a stub DBC. The tests that care about them re-patch to record.
    monkeypatch.setattr(
        warehouse, "assert_db_overlap_within_tolerance", lambda _dbc: _CLEAN_REPORT
    )
    monkeypatch.setattr(warehouse, "assert_db_margin_agreement", lambda _dbc: None)
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
        # The #167 gates ran and found nothing. A populated report and ``None`` are
        # distinct on the receipt: "ran" versus "did not run".
        overlap=_CLEAN_REPORT,
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
    # The #167 gates read the live views, which a RecordingConnection cannot serve.
    def overlap(_dbc: object) -> OverlapReport:
        order.append("overlap")
        return _CLEAN_REPORT

    monkeypatch.setattr(warehouse, "assert_db_overlap_within_tolerance", overlap)
    monkeypatch.setattr(warehouse, "assert_db_margin_agreement", lambda _dbc: None)

    conn = RecordingConnection()
    run_warehouse(make_dbc(conn), "states.shp", "mit.csv", close=True)

    assert order == ["views", "overlap"]
    assert conn.closed  # the connection was closed after the views were built


def test_no_pv_source_imports_the_warehouse_composition_root() -> None:
    """D015/D027: ``warehouse`` imports from every source; a back-import inverts D015.

    ``warehouse.py`` is a composition root (allowed to import EC + both PV subpackages),
    but the exemption only stays honest if the dependency never runs the other way. Mirror
    the greppable ``dwh.votes`` invariant with an enforced test: no module under
    ``usvote/{mit,ucsb,pv}/`` may import ``usvote.warehouse``.

    **Parsed, not grepped** — via ``test_layering.imports``, whose own docstring makes
    the argument: a regex over ``import usvote.warehouse|from usvote.warehouse`` misses
    ``from usvote import warehouse``, which is the prevailing spelling in this repo
    *including inside the subpackages being guarded*, and it false-positives on a
    docstring quoting an import line. This test used such a regex until #167 added
    ``usvote/pv/overlap.py`` to the scanned set; a guard blind to the common spelling
    reads as enforcement while providing none.
    """
    pkg_root = Path(warehouse.__file__).parent
    offenders = [
        py.relative_to(pkg_root).as_posix()
        for sub in ("mit", "ucsb", "pv")
        for py in (pkg_root / sub).rglob("*.py")
        if imports(py.read_text(), "usvote.warehouse")
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


def _also_record_the_gates(
    monkeypatch: pytest.MonkeyPatch, calls: list[tuple[str, dict[str, Any]]]
) -> None:
    """Re-patch the two #167 gates so they append to the ``recorder`` call log."""
    def cells(_dbc: object) -> OverlapReport:
        calls.append(("overlap-cells", {}))
        return _CLEAN_REPORT

    monkeypatch.setattr(warehouse, "assert_db_overlap_within_tolerance", cells)
    monkeypatch.setattr(
        warehouse,
        "assert_db_margin_agreement",
        lambda _dbc: calls.append(("margin", {})),
    )


def test_run_warehouse_validates_the_overlap_after_the_views_are_built(
    dbc: DBC,
    recorder: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#167 / D051: the two raising gates run **last**, and that is load-bearing.

    They are not the only step that can raise — ``create_ec_pv_views`` and
    ``create_hybrid_views`` run raising preconditions of their own — but they are the
    only raising step whose threshold is *expected to move* (D051 says gate 1's per-year
    floor is the first to need review). Anywhere earlier, a breach of a movable
    threshold would leave a warehouse holding facts but no join/hybrid views — and its
    only documented recovery, ``replace=True``, rebuilds and re-hits the same breach, so
    retuning could brick the build. Last means a breach reports loudly over a *complete*
    warehouse.

    Asserting the whole ordered list rather than membership is the point: a gate moved
    one step earlier still runs, still passes a presence check, and re-opens exactly the
    failure mode above.
    """
    _also_record_the_gates(monkeypatch, recorder)

    run_warehouse(dbc, "states.shp", "mit.csv", ucsb_html_dir="snap/")

    assert [name for name, _ in recorder] == [
        "ec",
        "mit",
        "ucsb",
        "views",
        "overlap-cells",
        "margin",
    ]


def test_validate_overlap_false_skips_both_gates(
    dbc: DBC,
    recorder: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flag is explicit and caller-supplied, in the ``ucsb_html_dir`` spirit.

    A build whose sources are deliberately partial — a state-scoped MIT extract against
    a full UCSB corpus, which ``test_ec_pv_join.py::test_join_over_a_real_two_source_load``
    does, and it is the only such caller in the tree — has too few paired cells for an
    agreement *rate* to mean anything, so such a caller opts out rather than the gate
    guessing from the data whether it was handed a sample.
    """
    _also_record_the_gates(monkeypatch, recorder)

    result = run_warehouse(
        dbc, "states.shp", "mit.csv", ucsb_html_dir="snap/", validate_overlap=False
    )

    assert [name for name, _ in recorder] == ["ec", "mit", "ucsb", "views"]
    assert result.overlap is None


def test_the_flag_list_reaches_the_build_receipt(
    dbc: DBC,
    recorder: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: gate 2's D005 list is *produced*, so it must be reachable, not discarded.

    ``None`` and ``()`` are kept distinct on the receipt — "the gate did not run" versus
    "it ran and flagged nothing" — the same three-state discipline the ledger's own
    slots use.
    """
    flagged = (OverlapKey(year=1976, state="State0", candidate="Nominee", party="D"),)
    monkeypatch.setattr(
        warehouse,
        "assert_db_overlap_within_tolerance",
        lambda _dbc: OverlapReport(cells=1, exact=0, flagged=flagged),
    )

    result = run_warehouse(dbc, "states.shp", "mit.csv", ucsb_html_dir="snap/")

    assert result.overlap is not None
    assert result.overlap.flagged == flagged


def test_a_skipped_gate_is_distinguishable_from_a_clean_one(
    dbc: DBC,
    recorder: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A UCSB-less build skips (AC-3), and the receipt says *skipped*, not clean.

    Three states stay distinguishable on the receipt — ``None`` (the gates did not
    run), a ``skipped`` report (they ran and had nothing to measure), and a populated
    report with empty lists (they ran and found nothing). Collapsing the middle one
    into either neighbour is how a build that never checked reads as a build that
    checked and was clean.
    """
    monkeypatch.setattr(
        warehouse,
        "assert_db_overlap_within_tolerance",
        lambda _dbc: OverlapReport(skipped=True, skip_reason="no UCSB"),
    )

    result = run_warehouse(dbc, "states.shp", "mit.csv")

    assert result.overlap is not None
    assert result.overlap.skipped
    assert result.overlap.flagged == ()


# NOTE: there is deliberately no "a --replace build still rebuilds the hybrid views"
# test here. The ``recorder`` fixture monkeypatches ``rebuild_views`` wholesale, so such
# a test structurally *cannot* observe ``create_hybrid_views`` — it would be a near-exact
# duplicate of ``test_replace_maps_destructive_to_ec_additive_to_pv`` wearing a name that
# claims more than it checks. The property is covered by composition:
# ``test_replace_maps_destructive_to_ec_additive_to_pv`` pins that a ``replace`` build
# still records ``views``, and ``test_rebuild_views_sequences_union_then_join_then_hybrid``
# pins that ``rebuild_views`` calls ``create_hybrid_views``. The live end-to-end check is
# ``tests/integration/test_hybrid_views.py``. (Architect ruling, #124 code review.)
