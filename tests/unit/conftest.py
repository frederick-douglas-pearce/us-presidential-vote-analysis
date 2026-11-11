"""Shared pytest fixtures for the unit suite — the API snapshot scaffolding (#99).

These consolidate the ``snapshot_path`` / ``settings`` / ``client`` fixtures that
``test_api_app`` (#96), ``test_api_endpoints`` (#97), and ``test_api_openapi`` (#98)
each used to define identically. The snapshot is **built at test time** from the shared
synthetic frame (:func:`tests.fixtures.api_snapshot.synthetic_ec_pv_frame`) through the
real :func:`usvote.snapshot.build_snapshot` writer, so it needs **no live Postgres**
(D028) and cannot drift from the snapshot schema.

A test that needs a bespoke frame can override the ``synthetic_frame`` fixture locally;
the ``snapshot_path`` / ``settings`` / ``client`` chain then rebuilds from it.

It also holds the dashboard tests' check on charts that were not drawn (#467, D095):
:func:`no_undeclared_chart_failure`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tests.chart_log import LOGGER, Records, chart_log_problems
from tests.fixtures.api_snapshot import (
    SNAPSHOT_TS,
    synthetic_ec_pv_frame,
    synthetic_party_keys_frame,
    synthetic_per_capita_frame,
    synthetic_pv_status_frame,
)
from usvote.api import create_app
from usvote.api.config import ApiSettings
from usvote.snapshot import build_snapshot


@pytest.fixture
def synthetic_frame() -> pd.DataFrame:
    """The canonical synthetic ``ec_pv_redistributable`` frame (override to customize)."""
    return synthetic_ec_pv_frame()


@pytest.fixture
def synthetic_status_frame() -> pd.DataFrame:
    """The ``(year, state, pv_status)`` roster the build requires (override to customize)."""
    return synthetic_pv_status_frame()


@pytest.fixture
def synthetic_per_capita() -> pd.DataFrame:
    """The per-capita frame the build requires (#245; override to customize).

    Keyed to the canonical ``synthetic_frame``'s ``(year, state)`` pairs. A test that
    overrides ``synthetic_frame`` with a different key set must override this too — the
    build asserts the two sets are equal.
    """
    return synthetic_per_capita_frame()


@pytest.fixture
def snapshot_path(
    tmp_path: Path,
    synthetic_frame: pd.DataFrame,
    synthetic_status_frame: pd.DataFrame,
    synthetic_per_capita: pd.DataFrame,
) -> str:
    """A real SQLite snapshot built from ``synthetic_frame`` — no live DB."""
    out = str(tmp_path / "snapshot.sqlite")
    build_snapshot(
        synthetic_frame,
        out,
        pv_status_df=synthetic_status_frame,
        per_capita_df=synthetic_per_capita,
        party_keys_df=synthetic_party_keys_frame(synthetic_frame),
        build_timestamp=SNAPSHOT_TS,
    )
    return out


@pytest.fixture
def settings(snapshot_path: str) -> ApiSettings:
    return ApiSettings(snapshot_path=snapshot_path, cors_origins=["http://localhost:5173"])


@pytest.fixture
def client(settings: ApiSettings) -> Iterator[TestClient]:
    # ``with`` runs the lifespan, so app.state.repository is opened (no live DB).
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture(autouse=True)
def no_undeclared_chart_failure(request: pytest.FixtureRequest) -> Iterator[None]:
    """Fail a dashboard test that leaves a chart not drawn it did not declare (#467).

    ``components.chart`` logs a figure that breaks the chart rules at error level and
    renders the chart's title and caption alone, so the page keeps its tables (D095).
    This collects every such record during a ``test_dashboard_*`` test and fails it on
    any the test did not declare with ``@pytest.mark.expected_chart_failure(chart_id,
    count=1)``, exactly that many per chart (:func:`tests.chart_log.chart_log_problems`).
    ``TestEveryChart.test_every_rendered_page`` renders every registered page's default
    view, so a shipped chart that is not drawn there fails the suite.
    """
    if not request.node.path.name.startswith("test_dashboard_"):
        yield
        return
    expected: dict[str, int] = {}
    for marker in request.node.iter_markers("expected_chart_failure"):
        chart_id = marker.args[0]
        expected[chart_id] = expected.get(chart_id, 0) + marker.kwargs.get("count", 1)
    handler = Records()
    logger = logging.getLogger(LOGGER)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)
    problems = chart_log_problems(handler.records, expected)
    if problems:
        pytest.fail(f"chart not-drawn log: {problems}", pytrace=False)
