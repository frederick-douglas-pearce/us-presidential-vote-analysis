"""Live-Postgres integration tests for the #183 seat reconciliation.

Excluded by default via the ``integration`` marker; run with ``pytest -m integration``.

**What only this can establish.** The offline suite reconciles ten elections, because
ten Archives pages are committed as fixtures. It cannot reconcile the other forty-one,
and it cannot check the *membership* claim the exception catalog makes — that every
declared disagreement names a state which actually participated in that election —
because that claim is only meaningful against a complete spine.
``assert_seats_reconcile`` deliberately does not check it on an arbitrary frame (a
partial frame cannot tell "did not participate" from "not loaded"), so this is where it
is checked.

Needs the **local Archives corpus** (``USVOTE_EC_HTML_DIR``) to seed the full 51-year
spine, and skips cleanly without it. So it does not run in CI, and running it locally is
a merge precondition — the posture the UCSB cross-source control test already has.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tests._helpers import fake_state_geo
from usvote.census.reconcile import (
    KIND_ELECTORAL_VOTES_WITHHELD,
    KIND_RECORD_UNDERSTATES_ALLOTMENT,
    KIND_SEATS_NOT_APPORTIONED,
    SEAT_RECONCILIATION_EXCEPTIONS,
    assert_seats_reconcile,
    build_seat_reconciliation,
)
from usvote.db import DBC
from usvote.spine import read_ec_participation
from usvote.years import ec_ingest_years


def _ec_corpus() -> Path:
    corpus = os.environ.get("USVOTE_EC_HTML_DIR")
    if not corpus:
        pytest.skip("USVOTE_EC_HTML_DIR not set; the full spine needs the local corpus")
    path = Path(corpus)
    missing = [
        y for y in sorted(ec_ingest_years()) if not (path / f"{y}.html").is_file()
    ]
    if missing:
        pytest.skip(f"EC corpus is missing {len(missing)} year(s): {missing[:5]}")
    return path


def _seed_full_spine(dbc: DBC) -> None:
    from usvote.pipeline import run_ec_pipeline
    from usvote.scrape import fetch_from_corpus

    run_ec_pipeline(
        dbc,
        "unused.shp",
        replace=True,
        years=set(ec_ingest_years()),
        fetch=fetch_from_corpus(_ec_corpus()),
        load_geo=lambda _p: fake_state_geo(),
    )


@pytest.mark.integration
def test_the_whole_series_reconciles(integration_db_config: dict[str, Any]) -> None:
    """All 51 elections, against the real recorded allotments.

    This is the acceptance criterion in one line: every ``(election_year, state)``
    allotment is the published apportionment's seats plus two, DC's Twenty-third
    Amendment three, or a catalogued disagreement.
    """
    dbc = DBC(integration_db_config)
    try:
        _seed_full_spine(dbc)
        participation = read_ec_participation(dbc)
        assert_seats_reconcile(participation)

        frame = build_seat_reconciliation(participation)
        assert frame["election_year"].nunique() == len(ec_ingest_years())
        disagreeing = {
            (int(row.election_year), str(row.state))
            for row in frame.itertuples(index=False)
            if not row.reconciles
        }
        declared = {
            (e.election_year, e.state) for e in SEAT_RECONCILIATION_EXCEPTIONS
        }
        assert disagreeing == declared, (
            "the set of real disagreements and the catalog must be identical; "
            f"undeclared={sorted(disagreeing - declared)} "
            f"stale={sorted(declared - disagreeing)}"
        )
    finally:
        dbc.close_connection()


@pytest.mark.integration
def test_every_declared_exception_names_a_participating_state(
    integration_db_config: dict[str, Any],
) -> None:
    """The membership claim the offline guard cannot soundly make.

    A declaration for a state that did not participate in that election is a false entry
    in ``docs/corrections.md`` and nothing else would read it. Only a complete spine can
    tell that from a frame that simply does not reach the row.
    """
    dbc = DBC(integration_db_config)
    try:
        _seed_full_spine(dbc)
        participation = read_ec_participation(dbc)
        states = participation.loc[~participation["is_total"].astype(bool)]
        pairs = {
            (int(row.year), str(row.state))
            for row in states.itertuples(index=False)
            if row.state is not None and not pd.isna(row.state)
        }
        for exception in SEAT_RECONCILIATION_EXCEPTIONS:
            assert (exception.election_year, exception.state) in pairs, (
                f"{exception.state} is declared for {exception.election_year} but did "
                f"not participate in that election"
            )
    finally:
        dbc.close_connection()


@pytest.mark.integration
def test_the_two_exception_kinds_behave_oppositely_in_the_record(
    integration_db_config: dict[str, Any],
) -> None:
    """The asymmetry the catalog's two kinds exist to name.

    ``electoral_votes_withheld`` rows hold seats and cast nothing;
    ``seats_not_apportioned`` rows cast votes with no seats. A one-sided rule passes the
    second in silence, which is why both are catalogued rather than lumped together.
    """
    dbc = DBC(integration_db_config)
    try:
        _seed_full_spine(dbc)
        frame = build_seat_reconciliation(read_ec_participation(dbc))
        indexed = {
            (int(row.election_year), str(row.state)): row
            for row in frame.itertuples(index=False)
        }
        for exception in SEAT_RECONCILIATION_EXCEPTIONS:
            row = indexed[(exception.election_year, exception.state)]
            if exception.kind == KIND_ELECTORAL_VOTES_WITHHELD:
                assert not pd.isna(row.seats) and int(row.seats) > 0
                assert int(row.total_electoral_votes) == 0
            elif exception.kind == KIND_SEATS_NOT_APPORTIONED:
                assert pd.isna(row.seats)
                assert int(row.total_electoral_votes) > 0
            elif exception.kind == KIND_RECORD_UNDERSTATES_ALLOTMENT:
                # The third kind is the asymmetry's odd one out: seats exist AND votes
                # were cast, but fewer than the apportionment implies. Both other kinds
                # have a zero on one side; this one has neither, which is why a rule
                # written from those two would not have caught it.
                assert not pd.isna(row.seats) and int(row.seats) > 0
                assert 0 < int(row.total_electoral_votes) < int(
                    row.expected_electoral_votes
                )
    finally:
        dbc.close_connection()
