"""Integration tests — require a live Postgres (excluded by default).

Home for tests that exercise the real load path against a database. Every test
here must carry ``@pytest.mark.integration`` so the default
``-m 'not integration'`` selection (see ``[tool.pytest.ini_options]``) skips it;
CI runs them in a dedicated job with a Postgres service container
(``uv run pytest -m integration``).

Two such tests currently live inline in ``tests/test_db.py`` and
``tests/test_load.py``; porting them here needs coordinated CI changes and is
tracked as a follow-up issue. The live-DB config comes from the
``integration_db_config`` fixture in ``tests/conftest.py`` (``USVOTE_TEST_DB_*``
env vars); import module-level helpers with ``from ..conftest import ...``.
"""
