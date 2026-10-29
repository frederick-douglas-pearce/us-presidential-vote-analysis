"""Browser tests of the dashboard — Playwright, against recorded API responses (#321).

Every test here carries ``@pytest.mark.e2e``, which the default selection excludes (see
``[tool.pytest.ini_options]``); run them with ``uv run pytest -m e2e`` after a one-time
``uv run playwright install chromium``. ``conftest.py`` serves the dashboard from
``tests/fixtures/dashboard/`` through ``serve.py``, so no test reaches the network.

pytest imports this package's modules on every run, the default one included, when it
collects them. So nothing here may start a process or touch the network at import;
reading the recorded responses, as ``dashboard_pages.py`` does, is the most an import
does.
"""
