"""The unit suite's check on the chart builder's not-drawn log (#467, D095).

``components.chart`` does not draw a figure that ``charts.figure_problems`` refuses: it
logs at error level on the ``explore.components`` logger and returns the chart's title
and caption alone, so its page keeps its tables. A chart that is quietly not drawn is
a bug nobody would see, so ``tests/unit/conftest.py`` collects every such record a
dashboard test leaves and fails the test on one it did not declare with
``@pytest.mark.expected_chart_failure(chart_id, count=1)`` (exactly ``count`` records
for that chart; repeat the marker for another chart). The check runs only in
``tests/unit/test_dashboard_*.py`` (:func:`chart_log_checked`), and ``tests/conftest.py``
refuses the marker anywhere else at collection. Stdlib only.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from pathlib import Path

#: The logger ``components.chart`` writes its not-drawn line to.
LOGGER = "explore.components"


#: Where the marker is honored, and why not in the e2e suite: it renders in a
#: subprocess server whose log no in-process handler sees (its own marker is
#: ``expected_console_error``).
PLACEMENT = (
    "expected_chart_failure is checked only in tests/unit/test_dashboard_*.py "
    "(the e2e server renders in a subprocess; its marker is expected_console_error)"
)


def chart_log_checked(path: Path) -> bool:
    """Whether a test file's not-drawn records are checked: a ``test_dashboard_*``
    file directly under ``tests/unit/``."""
    return (
        path.name.startswith("test_dashboard_")
        and path.parent.name == "unit"
        and path.parent.parent.name == "tests"
    )


class Records(logging.Handler):
    """Every record at error level or above that reaches :data:`LOGGER`, kept whether
    or not a test resets pytest's own log capture."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def chart_log_problems(
    records: Iterable[logging.LogRecord], expected: Mapping[str, int]
) -> list[str]:
    """What is wrong with a test's error records from :data:`LOGGER`: a record for a
    chart the test did not expect, a record naming no chart, and an expected chart
    whose record count differs from the count expected (absent included)."""
    seen: dict[str, int] = {}
    problems = []
    for record in records:
        chart_id = getattr(record, "chart_id", None)
        if not isinstance(chart_id, str):
            problems.append(f"an error record naming no chart: {record.getMessage()}")
            continue
        seen[chart_id] = seen.get(chart_id, 0) + 1
    for chart_id in sorted(seen.keys() | expected.keys()):
        got, want = seen.get(chart_id, 0), expected.get(chart_id, 0)
        if got != want:
            problems.append(f"{chart_id}: {got} not-drawn record(s), expected {want}")
    return problems
