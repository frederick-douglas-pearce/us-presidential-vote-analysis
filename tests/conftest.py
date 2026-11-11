"""Shared pytest fixtures, and one collection check.

The fixtures here are discovered automatically for every test under ``tests/``
(including ``tests/unit/`` and ``tests/integration/``), so no import is needed at
the call site. The one hook, :func:`pytest_collection_modifyitems`, refuses the
``expected_chart_failure`` marker outside ``tests/unit/test_dashboard_*.py`` (#467),
where nothing would check it. Plain, importable helpers (the recording
fake connection, ``make_dbc``, ``fake_state_geo``, ``STATE_NAMES``,
``FIXTURES_DIR``) live in ``tests/_helpers.py`` and are imported explicitly.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from tests._helpers import RecordingConnection
from tests.chart_log import PLACEMENT, chart_log_checked


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Refuse ``expected_chart_failure`` where its check never runs (#467, D095(d)).

    ``tryfirst`` runs this before ``-m`` deselects the e2e and integration items, so
    the default run sees a misplaced marker on them too."""
    misplaced = [
        item.nodeid
        for item in items
        if item.get_closest_marker("expected_chart_failure") is not None
        and not chart_log_checked(item.path)
    ]
    if misplaced:
        raise pytest.UsageError(f"{PLACEMENT}: {misplaced}")


@pytest.fixture
def recording_conn() -> RecordingConnection:
    """A fresh fake connection whose ``.executed`` list captures SQL strings."""
    return RecordingConnection()


@pytest.fixture
def integration_db_config() -> dict[str, Any]:
    """Live-Postgres connection config from ``USVOTE_TEST_DB_*`` env vars.

    Skips the test if ``USVOTE_TEST_DB_NAME`` is unset, so the ``integration``
    marker can run locally without hard-coded credentials. Shared by every
    live-database test.
    """
    dbname = os.environ.get("USVOTE_TEST_DB_NAME")
    if not dbname:
        pytest.skip("USVOTE_TEST_DB_NAME not set; skipping live-Postgres test")
    return {
        "host": os.environ.get("USVOTE_TEST_DB_HOST", "localhost"),
        "port": int(os.environ.get("USVOTE_TEST_DB_PORT", "5432")),
        "dbname": dbname,
        "user": os.environ.get("USVOTE_TEST_DB_USER", "postgres"),
        "password": os.environ.get("USVOTE_TEST_DB_PASSWORD", ""),
    }
