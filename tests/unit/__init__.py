"""Unit tests — no network, no database.

Home for new unit tests as the package grows (E4/E5 ``usvote/ucsb`` and
``usvote/mit`` ports). The existing suite still lives flat in ``tests/`` and
is being migrated here separately; see the tracking issue for the full split.

Selection is by **marker**, not directory: the default ``-m 'not integration'``
(see ``[tool.pytest.ini_options]``) is the single source of truth for what runs
where. A test placed here must still stay offline; one needing a live Postgres
belongs in ``tests/integration/`` and must carry ``@pytest.mark.integration``.

Shared fixtures/helpers live in ``tests/conftest.py`` (auto-discovered up the
tree); import module-level helpers with ``from ..conftest import ...``.
"""
