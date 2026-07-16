"""Live-Postgres integration test for the MIT PV load into the shared table.

Excluded by default via the ``integration`` marker; run with ``pytest -m integration``
against a real database. Proves the payoff of #66: the EC spine and MIT popular-vote
rows **coexist in one ``dwh`` schema**, and MIT's canonical-key reconciliation (#67)
makes the ``pv_votes.state`` FK resolve.

The test first drives the EC pipeline over the 2016 + 2020 Archives fixtures to seed
``dwh.state``/``dwh.candidate``/``dwh.votes`` (the FK targets), then runs the MIT
pipeline over the fusion fixture scoped to 2016 (so its states/candidates are a subset
of what the EC spine loaded). It asserts row counts, grain (unique ``pv_id`` and unique
natural key), FK/containment (every ``pv_votes.state`` resolves into ``dwh.state``;
every ``pv_votes.candidate`` resolves into ``dwh.candidate.name`` — the reciprocal
guard #69 will own), and the MIT provenance tagging. The 2016 New York fixture rows are
a fusion case, so aggregation is exercised end-to-end into Postgres, not only in the
#65 unit tests. Config + skip-if-unset come from the shared ``integration_db_config``
fixture in ``tests/conftest.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests._helpers import FIXTURES_DIR, MIT_FUSION_SAMPLE_CSV, fake_state_geo
from usvote.db import DBC
from usvote.load import SCHEMA
from usvote.pv.schema import PV_TABLE


@pytest.mark.integration
def test_mit_pv_loads_alongside_ec_spine(
    integration_db_config: dict[str, Any],
) -> None:
    """Seed the EC spine (2016+2020), then load MIT PV (2016) into the same schema."""
    from usvote.mit.pipeline import run_mit_pipeline
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbc = DBC(integration_db_config)
    try:
        # 1. Seed the EC spine — creates dwh.state / dwh.candidate / dwh.votes, the
        #    FK targets the PV load needs, via the offline 2016+2020 fixtures.
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={2016, 2020},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )

        # 2. Load MIT PV scoped to 2016 (a subset of the seeded years), reconciled
        #    onto the canonical keys — non-destructively, alongside the EC spine.
        pv = run_mit_pipeline(
            dbc, path=MIT_FUSION_SAMPLE_CSV, years={2016}, replace=False
        )

        # The whole loaded frame lands (2016 NY: Clinton + Trump).
        n = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.{PV_TABLE}"
        )["n"].iloc[0]
        assert n == len(pv) == 2

        # The EC spine survived the PV load (guard against a schema-level replace).
        for ec_table in ("state", "candidate", "votes"):
            cnt = dbc.select_query_to_df(
                f"SELECT count(*) AS n FROM {SCHEMA}.{ec_table}"
            )["n"].iloc[0]
            assert cnt > 0, f"EC {ec_table} was wiped by the PV load"

        # Grain: pv_id unique, and the (source, year, state, candidate) natural key
        # unique (a broken grain would have raised on the constraint at insert).
        dup_pk = dbc.select_query_to_df(
            f"SELECT pv_id FROM {SCHEMA}.{PV_TABLE} "
            f"GROUP BY pv_id HAVING count(*) > 1"
        )
        assert dup_pk.empty
        dup_key = dbc.select_query_to_df(
            f"SELECT source, year, state, candidate FROM {SCHEMA}.{PV_TABLE} "
            f"GROUP BY source, year, state, candidate HAVING count(*) > 1"
        )
        assert dup_key.empty

        # FK/containment: every pv_votes.state resolves into dwh.state, and every
        # pv_votes.candidate resolves into dwh.candidate.name (the #67 reconciliation
        # guarantee, verified end-to-end against the real EC dims).
        orphan_state = dbc.select_query_to_df(
            f"SELECT p.state FROM {SCHEMA}.{PV_TABLE} p "
            f"LEFT JOIN {SCHEMA}.state s USING (state) WHERE s.state IS NULL"
        )
        assert orphan_state.empty
        orphan_cand = dbc.select_query_to_df(
            f"SELECT p.candidate FROM {SCHEMA}.{PV_TABLE} p "
            f"LEFT JOIN {SCHEMA}.candidate c ON p.candidate = c.name "
            f"WHERE c.name IS NULL"
        )
        assert orphan_cand.empty

        # Provenance tagging: every row is source=MIT, reliability=exact.
        tags = dbc.select_query_to_df(
            f"SELECT DISTINCT source, reliability FROM {SCHEMA}.{PV_TABLE}"
        )
        assert tags.values.tolist() == [["MIT", "exact"]]
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
