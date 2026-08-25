"""Live-Postgres integration test for the full EC load path.

Excluded by default via the ``integration`` marker; run with
``pytest -m integration`` against a real database. Drives the *whole pipeline*
over the 2016 + 2020 Archives fixtures into Postgres and asserts row counts +
grain (PK uniqueness, FK containment). It lives with ``load`` rather than
``pipeline`` because the load into a real database is what it verifies; see
``run_ec_pipeline`` for the wiring. Config and the skip-if-unset guard come from
the shared ``integration_db_config`` fixture in ``tests/conftest.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests._helpers import FIXTURES_DIR, fake_state_geo
from usvote.db import DBC
from usvote.load import SCHEMA, TABLE_NAMES


@pytest.mark.integration
def test_fixture_slice_loads_into_real_postgres(
    integration_db_config: dict[str, Any],
) -> None:
    """Drive the 2016 + 2020 fixture slice through the whole pipeline into Postgres.

    Replays the Archives fixtures offline (``fetch_from_dir``) and injects the fake
    state-geo frame (``load_geo``), so no network or TIGER shapefile is needed —
    only a live database (config + skip from the shared ``integration_db_config``
    fixture).
    """
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbc = DBC(integration_db_config)
    try:
        # The fixture dir names pages by year; a link-index fixture drives the two
        # snapshotted years (2016, 2020) through the real scrape->load spine.
        candidates_df, state_df, votes_df = run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={2016, 2020},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )

        counts = {
            t: dbc.select_query_to_df(
                f"SELECT count(*) AS n FROM {SCHEMA}.{t}"
            )["n"].iloc[0]
            for t in TABLE_NAMES
        }
        # Every built frame lands in full.
        assert counts["state"] == len(state_df) == 51
        assert counts["candidate"] == len(candidates_df)
        assert counts["votes"] == len(votes_df)

        # Grain: primary keys are unique (a broken grain would have raised on the
        # PK constraint at insert, but assert explicitly for a clear signal).
        for table, pk in (("candidate", "candidate_id"), ("votes", "votes_id")):
            dup = dbc.select_query_to_df(
                f"SELECT {pk} FROM {SCHEMA}.{table} "
                f"GROUP BY {pk} HAVING count(*) > 1"
            )
            assert dup.empty, f"{table}.{pk} not unique"

        # FK containment: every votes.candidate_id resolves to a candidate, and
        # every non-null votes.state resolves to a state.
        orphan_cand = dbc.select_query_to_df(
            f"SELECT v.candidate_id FROM {SCHEMA}.votes v "
            f"LEFT JOIN {SCHEMA}.candidate c USING (candidate_id) "
            f"WHERE c.candidate_id IS NULL"
        )
        assert orphan_cand.empty
        orphan_state = dbc.select_query_to_df(
            f"SELECT v.state FROM {SCHEMA}.votes v "
            f"LEFT JOIN {SCHEMA}.state s USING (state) "
            f"WHERE v.state IS NOT NULL AND s.state IS NULL"
        )
        assert orphan_state.empty
    finally:
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()


@pytest.mark.integration
def test_1868_count_status_survives_a_real_postgres_round_trip(
    integration_db_config: dict[str, Any],
) -> None:
    """The #143 DDL change, exercised against a real database rather than a fake.

    ``count_status`` is the first schema change to the EC fact since the spine was built,
    and the two things that can only fail on live Postgres are exactly the two this
    covers: the ``CHECK`` constraint built from :data:`usvote.count_status.
    COUNT_STATUS_VALUES` actually accepting the value the transform writes, and the
    ``NOT NULL`` holding for every row when the transform supplies no default.

    1868 is the year that makes it non-vacuous — every other year would write ``counted``
    on every row, so a broken CHECK enumerating the wrong values could still pass.
    """
    from usvote.count_status import (
        COUNT_STATUS_COUNTED,
        COUNT_STATUS_DISPUTED,
        COUNT_STATUS_VALUES,
    )
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_dir

    dbc = DBC(integration_db_config)
    try:
        run_ec_pipeline(
            dbc,
            "unused.shp",
            replace=True,
            years={1868},
            fetch=fetch_from_dir(FIXTURES_DIR),
            load_geo=lambda _p: fake_state_geo(),
        )

        # NOT NULL holds with no DEFAULT: the transform states a status on every row.
        nulls = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.votes WHERE count_status IS NULL"
        )["n"].iloc[0]
        assert nulls == 0

        by_status = dbc.select_query_to_df(
            f"SELECT count_status, count(*) AS n FROM {SCHEMA}.votes "
            "GROUP BY count_status"
        ).set_index("count_status")["n"].to_dict()
        # Exactly one flagged row in 1868 — Georgia's nine for Seymour.
        assert by_status[COUNT_STATUS_DISPUTED] == 1
        assert by_status[COUNT_STATUS_COUNTED] > 1
        assert set(by_status) <= set(COUNT_STATUS_VALUES)

        flagged = dbc.select_query_to_df(
            f"SELECT year, state, president_electoral_votes, count_status_reason "
            f"FROM {SCHEMA}.votes WHERE count_status = '{COUNT_STATUS_DISPUTED}'"
        )
        assert flagged["state"].iloc[0] == "Georgia"
        assert int(flagged["president_electoral_votes"].iloc[0]) == 9
        # The Archives' sentence round-trips intact, en-dashes and all.
        assert "could not agree whether to accept" in flagged[
            "count_status_reason"
        ].iloc[0]

        # ...and the reason is null on every row that was plainly counted.
        stray = dbc.select_query_to_df(
            f"SELECT count(*) AS n FROM {SCHEMA}.votes "
            f"WHERE count_status = '{COUNT_STATUS_COUNTED}' "
            "AND count_status_reason IS NOT NULL"
        )["n"].iloc[0]
        assert stray == 0

        # The CHECK is live: a value outside the enum must be rejected by the database,
        # not merely by the transform. Without this, the constraint could be absent and
        # every assertion above would still pass.
        with (
            pytest.raises(Exception, match="count_status"),
            dbc.conn,
            dbc.conn.cursor() as cur,
        ):
            cur.execute(
                f"UPDATE {SCHEMA}.votes SET count_status = 'invented' "
                f"WHERE votes_id = (SELECT min(votes_id) FROM {SCHEMA}.votes)"
            )
    finally:
        dbc.conn.rollback()
        dbc.delete_schema(SCHEMA, option="Cascade")
        dbc.close_connection()
