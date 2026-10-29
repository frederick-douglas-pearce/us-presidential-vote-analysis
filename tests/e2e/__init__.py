"""Browser tests of the dashboard — Playwright, against recorded API responses (#321).

Every test here carries ``@pytest.mark.e2e``, which the default selection excludes (see
``[tool.pytest.ini_options]``); run them with ``uv run pytest -m e2e`` after a one-time
``uv run playwright install chromium``. ``conftest.py`` serves the dashboard from
``tests/fixtures/dashboard/`` through ``serve.py``, so no test reaches the network.

Nothing in this package may do work at import: pytest imports ``conftest.py`` on every
run, the default one included.
"""
