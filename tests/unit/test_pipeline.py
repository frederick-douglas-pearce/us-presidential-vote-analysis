"""Unit tests for ``usvote.pipeline``.

Covers the year-set derivation and the full scrape -> parse -> transform -> load
wiring, run offline: the 2016 + 2020 Archives fixtures replay through
``fetch_from_dir``, a fake state-geo frame is injected via ``load_geo``, and the
load lands on the recording fake connection — so the end-to-end wiring #28 adds is
exercised with no network, no TIGER shapefile, and no live Postgres. The
real-database load is covered by the integration test in
``tests/integration/test_load.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from tests._helpers import (
    FIXTURES_DIR,
    RecordingConnection,
    fake_state_geo,
    make_dbc,
    record_inserts,
)
from usvote import scrape
from usvote.count_status import (
    COUNT_STATUS_COLUMN,
    COUNT_STATUS_COUNTED,
    COUNT_STATUS_DISPUTED,
    COUNT_STATUS_NOT_COUNTED,
    COUNT_STATUS_REASON_COLUMN,
    COUNTED_VOTES_COLUMN,
)
from usvote.load import SCHEMA
from usvote.pipeline import (
    EC_SPINE_FLOOR,
    LATEST_ELECTION_YEAR,
    UNSUPPORTED_EC_YEARS,
    PipelineError,
    ec_ingest_years,
    election_years,
    run_ec_pipeline,
)
from usvote.scrape import Fetch, fetch_from_dir
from usvote.transform import (
    ELECTORAL_VOTE_SHORTFALLS,
    OTHER_CANDIDATES,
    OTHER_VOTES,
    TransformError,
    apply_other_candidates,
)

# --- election_years --------------------------------------------------------


def test_election_years_spans_1789_to_latest() -> None:
    years = election_years(2024)
    assert 1789 in years  # the lone off-cycle first election
    assert 1792 in years  # first of the every-four-years cadence
    assert 2024 in years
    assert 2021 not in years  # not an election year
    assert 1790 not in years


def test_election_years_does_not_overshoot_non_election_latest() -> None:
    # A non-election `latest` must not pull in the next cycle: the 4-year cadence
    # from 1792 stops at the last election year <= latest.
    years = election_years(2025)
    assert 2024 in years
    assert 2028 not in years
    assert max(years) == 2024


def test_election_years_defaults_to_module_latest() -> None:
    assert election_years() == election_years(LATEST_ELECTION_YEAR)
    assert max(election_years()) == LATEST_ELECTION_YEAR


def test_ec_ingest_years_applies_the_floor_and_the_now_empty_gate() -> None:
    years = ec_ingest_years(2024)
    # The default ingest starts at the 1824 comparison floor (D009) ...
    assert min(years) == EC_SPINE_FLOOR == 1824
    assert 1820 not in years  # post-12A but below the floor (deferred)
    assert 1800 not in years  # pre-12th-Amendment (out of scope, D010)
    # ... the Reconstruction gate is now EMPTY — 1868 was ingested by #143 and 1872 by
    # #144, so the spine is unbroken from the floor to the latest year ...
    assert frozenset() == UNSUPPORTED_EC_YEARS
    assert {1868, 1872} <= years
    assert years == set(range(1824, 2025, 4))
    # ... and the gate mechanism itself is retained (not deleted) for a future era, so
    # its contract still holds vacuously: every gated year is a real election year.
    assert election_years(2024) >= UNSUPPORTED_EC_YEARS
    assert not (UNSUPPORTED_EC_YEARS & years)
    # ... and the modern spine through the latest year is retained.
    assert {1824, 1864, 1876, 1892, 2024} <= years


# --- full pipeline wiring (offline) ----------------------------------------


def test_run_ec_pipeline_wires_all_stages_offline(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Capture inserts (insert_df_into_table routes through execute_values, which
    # the recording cursor never sees) so we can assert every table was loaded.
    inserts = record_inserts(monkeypatch)

    candidates_df, state_df, votes_df = run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )

    # The three warehouse frames were built and are non-empty.
    assert list(candidates_df.columns[:2]) == ["candidate_id", "name"]
    assert len(state_df) == 51
    assert {"votes_id", "year", "candidate_id"}.issubset(votes_df.columns)
    assert not votes_df.empty

    # Both fixture years flowed through to the votes fact.
    assert set(votes_df["year"]) == {2016, 2020}

    # All three tables were created and inserted, in FK order.
    assert [sql.split()[2] for sql, _ in inserts] == [
        f"{SCHEMA}.state",
        f"{SCHEMA}.candidate",
        f"{SCHEMA}.votes",
    ]


def test_run_ec_pipeline_loads_the_star_schema_in_one_transaction(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The three-table star-schema load is atomic (#84a): drop/create-schema, three
    # create-tables and three inserts all land in ONE transaction, so an interrupted
    # ``replace`` rebuild rolls back to the previous warehouse rather than a
    # dropped/half-built one. The recording connection commits once per statement's
    # ``with self.conn`` block and once per explicit ``transaction()`` commit, so a
    # wrapped load is exactly ONE commit; removing the wrapper would push it well above 1.
    record_inserts(monkeypatch)
    run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )

    assert recording_conn.commits == 1
    assert recording_conn.rollbacks == 0


def test_run_ec_pipeline_pre1892_spine_offline(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # End-to-end over the corrected pre-1892 spine years, exercising every #32 drift
    # together: <sup> footnotes, the plural <th>Totals> row, and each "Others" split
    # into named minor candidates — plus 1856 as a clean 3-way baseline.
    record_inserts(monkeypatch)
    candidates_df, _state_df, votes_df = run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={1824, 1832, 1836, 1856, 1860},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )
    tot = votes_df[votes_df["is_total"]].merge(
        candidates_df[["candidate_id", "name"]], on="candidate_id"
    )
    ev = {
        (int(r["year"]), r["name"]): int(r["president_electoral_votes"])
        for _, r in tot.iterrows()
    }
    # Winner electoral totals per year match the historical record.
    assert ev[(1824, "Andrew Jackson")] == 99
    assert ev[(1832, "Andrew Jackson")] == 219
    assert ev[(1836, "Martin Van Buren")] == 170
    assert ev[(1856, "James Buchanan")] == 174
    assert ev[(1860, "Abraham Lincoln")] == 180
    # Every "Others" split candidate loaded with its correct total (both sides of the
    # split reconciled — a silent inner-join drop would fail assert_totals_equal_state_sum).
    assert (ev[(1824, "William H. Crawford")], ev[(1824, "Henry Clay")]) == (41, 37)
    assert (ev[(1832, "John Floyd")], ev[(1832, "William Wirt")]) == (11, 7)
    assert ev[(1836, "Hugh L. White")] == 26
    assert ev[(1836, "Willie P. Mangum")] == 11
    assert (ev[(1860, "John C. Breckinridge")], ev[(1860, "John Bell")]) == (72, 39)
    # Party label drift normalized: Jackson reads "D-R" (1824 D-R + 1832 D -> party_2),
    # not the verbose "Democratic-Republican" the 1824 page prints.
    jackson = candidates_df.set_index("name").loc["Andrew Jackson"]
    assert (jackson["party"], jackson["party_2"]) == ("D-R", "D")


def test_an_unregistered_others_column_still_fails_loud() -> None:
    """The gate is empty, but the guard that made it necessary must not have rotted.

    Until #144 this was a *parametrized* test over ``UNSUPPORTED_EC_YEARS``: an explicit
    ``years={1872}`` had to raise ``TransformError`` rather than silently load wrong
    data. That year is now ingested and the gate is empty, so there is no year left to
    parametrize over — and deleting the test outright would retire the guarantee along
    with the year.

    What actually protected 1872 was :func:`apply_other_candidates` refusing an
    "Other(s)" placeholder column with no registered correction, and that guarantee is
    permanent: it is what will catch the *next* wide year (a re-scrape, an Archives edit,
    or the deferred pre-1824 era, D010). So the test moves down a level and exercises the
    guard directly, on a synthetic year no correction registers.
    """
    unregistered = pd.DataFrame([
        {
            "year": 1796,
            "president_candidate_name": "Others",
            "col_ind": 3,
            "president_candidate_state": None,
        }
    ])
    with pytest.raises(TransformError, match="no registered correction"):
        apply_other_candidates(unregistered)
    # And the corrected years are exactly the ones that carry a registered split, so a
    # year cannot be quietly dropped from the registry while a placeholder still parses.
    assert set(OTHER_CANDIDATES) == set(OTHER_VOTES)
    assert 1872 in OTHER_CANDIDATES


def test_run_ec_pipeline_1868_contested_count_offline(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1868 end-to-end (#143): the year the gate used to exclude now loads clean.

    Exercises the whole slice at once — the dual-totals selection, the parenthesized
    ``(9)``, the three dash-allotment states, and ``count_status`` reaching the fact —
    against the real saved Archives page.
    """
    record_inserts(monkeypatch)
    candidates_df, _state_df, votes_df = run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={1868},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )
    by_id = candidates_df.set_index("candidate_id")["name"].to_dict()
    tot = votes_df[votes_df["is_total"]]
    ev = {
        by_id[int(r["candidate_id"])]: int(r["president_electoral_votes"])
        for _, r in tot.iterrows()
    }
    # The *including-Georgia* totals: 294 appointed, Grant 214, Seymour 80. The 285/71
    # reading is the one the source also prints and this pipeline must not adopt (D044).
    assert ev == {"Ulysses S. Grant": 214, "Horatio Seymour": 80}
    assert int(tot["total_electoral_votes"].iloc[0]) == 294

    # #144: the counted basis reproduces the *other* row the same page prints — the one
    # D044 had to reject as the cast total. Both readings now exist, one per measure,
    # and neither is a curated literal: 285 = 294 - Georgia's 9, derived by
    # _add_counted_votes summing the state rows.
    counted = {
        by_id[int(r["candidate_id"])]: int(r[COUNTED_VOTES_COLUMN])
        for _, r in tot.iterrows()
    }
    assert counted == {"Ulysses S. Grant": 214, "Horatio Seymour": 71}
    assert sum(counted.values()) == 285

    state_rows = votes_df[votes_df["state"].notna()]
    # Mississippi/Texas/Virginia appointed no electors: real 0-EV rows, not missing ones.
    unreadmitted = state_rows[
        state_rows["state"].isin(["Mississippi", "Texas", "Virginia"])
    ]
    assert len(unreadmitted) == 6  # 3 states x 2 candidates — dense, per D026
    assert set(unreadmitted["total_electoral_votes"]) == {0}
    assert set(unreadmitted["president_electoral_votes"]) == {0}

    # Georgia's nine are Seymour's, and they are flagged `disputed` with the Archives'
    # own sentence — the row exists and carries its votes; only their counting is open.
    georgia = state_rows[state_rows["state"] == "Georgia"]
    seymour_id = next(cid for cid, name in by_id.items() if name == "Horatio Seymour")
    seymour_ga = georgia[georgia["candidate_id"] == seymour_id].iloc[0]
    assert int(seymour_ga["president_electoral_votes"]) == 9
    assert seymour_ga[COUNT_STATUS_COLUMN] == COUNT_STATUS_DISPUTED
    assert "could not agree whether to accept" in seymour_ga[COUNT_STATUS_REASON_COLUMN]

    # Exactly one row in the year is flagged; everything else is plainly `counted`,
    # including the national totals row that aggregates the disputed nine (D044).
    flagged = votes_df[votes_df[COUNT_STATUS_COLUMN] != COUNT_STATUS_COUNTED]
    assert len(flagged) == 1
    assert set(tot[COUNT_STATUS_COLUMN]) == {COUNT_STATUS_COUNTED}
    # 1868 must NOT acquire a shortfall entry: its votes were cast, then contested —
    # the other mechanism entirely (D043 §6).
    assert not [key for key in ELECTORAL_VOTE_SHORTFALLS if key[0] == 1868]


def test_run_ec_pipeline_1872_rejected_votes_offline(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1872 end-to-end (#144): the last gated year, and the hardest.

    Exercises the whole slice against the real saved Archives page — the four-way
    "Others" split, the 17 votes the table omits entirely, the AR/LA allotments printed
    as "-", and both electoral-vote measures reaching the fact.

    The three totals it pins are three different true statements about 1872:
    **366 appointed** (what Congress announced, against the page's own 352),
    **366 cast**, and **349 counted**.
    """
    record_inserts(monkeypatch)
    candidates_df, _state_df, votes_df = run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={1872},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )
    by_id = candidates_df.set_index("candidate_id")["name"].to_dict()
    tot = votes_df[votes_df["is_total"]]
    cast = {
        by_id[int(r["candidate_id"])]: int(r["president_electoral_votes"])
        for _, r in tot.iterrows()
    }
    counted = {
        by_id[int(r["candidate_id"])]: int(r[COUNTED_VOTES_COLUMN])
        for _, r in tot.iterrows()
    }
    # Greeley's four scattered recipients, each reconciled against the page's own note
    # 10 ("Gratz Brown received 18 votes; Hendricks 42; Jenkins 2; Davis 1").
    assert cast == {
        "Ulysses S. Grant": 300,
        "Thomas A. Hendricks": 42,
        "Benjamin Gratz Brown": 18,
        "Charles J. Jenkins": 2,
        "David Davis": 1,
        "Horace Greeley": 3,
    }
    # Grant loses AR's 6 + LA's 8, Greeley all 3: 17 rejected, 349 counted.
    assert counted["Ulysses S. Grant"] == 286
    assert counted["Horace Greeley"] == 0
    assert sum(cast.values()) == 366
    assert sum(counted.values()) == 349
    # The appointed denominator is 366 — NOT the 352 the Archives totals row prints,
    # which omits the two states whose returns were refused (D045).
    assert int(tot["total_electoral_votes"].iloc[0]) == 366

    state_rows = votes_df[votes_df["state"].notna()]
    ev = {
        (r["state"], by_id[int(r["candidate_id"])]): int(r["president_electoral_votes"])
        for _, r in state_rows.iterrows()
    }
    # Georgia only reconciles because the 3 Greeley votes were synthesized from note 4:
    # the page prints 8 of its 11.
    assert ev[("Georgia", "Horace Greeley")] == 3
    assert ev[("Georgia", "Benjamin Gratz Brown")] == 6
    assert ev[("Georgia", "Charles J. Jenkins")] == 2
    assert (
        sum(v for (state, _c), v in ev.items() if state == "Georgia")
        == int(state_rows.loc[state_rows["state"] == "Georgia",
                              "total_electoral_votes"].iloc[0])
        == 11
    )
    # Arkansas and Louisiana appointed their full complement and cast for Grant; only
    # the returns were refused. Contrast 1868's Mississippi/Texas/Virginia, which
    # appointed nobody and are genuine 0-EV rows (D043 s2) — the distinction this year
    # exists to keep.
    for state, appointed in (("Arkansas", 6), ("Louisiana", 8)):
        assert ev[(state, "Ulysses S. Grant")] == appointed
        assert int(state_rows.loc[state_rows["state"] == state,
                                  "total_electoral_votes"].iloc[0]) == appointed

    # Exactly three flagged rows, all `not_counted`, each carrying the Archives' own
    # sentence; the national totals row stays plainly `counted` (D044).
    flagged = votes_df[votes_df[COUNT_STATUS_COLUMN] != COUNT_STATUS_COUNTED]
    assert len(flagged) == 3
    assert set(flagged[COUNT_STATUS_COLUMN]) == {COUNT_STATUS_NOT_COUNTED}
    assert set(flagged["state"]) == {"Georgia", "Arkansas", "Louisiana"}
    assert flagged[COUNT_STATUS_REASON_COLUMN].str.strip().astype(bool).all()
    assert set(tot[COUNT_STATUS_COLUMN]) == {COUNT_STATUS_COUNTED}
    # Cast-then-refused is the count_status mechanism, never the shortfall one: these
    # votes WERE cast, so every row still sums to its allotment (D043 s6).
    assert not [key for key in ELECTORAL_VOTE_SHORTFALLS if key[0] == 1872]

    # Rank is on the counted basis, so Greeley's 3 rejected votes put him last rather
    # than fourth — and Grant, whose 286 all counted, is still unambiguously rank 1.
    rank = {
        by_id[int(r["candidate_id"])]: int(r["president_electoral_rank"])
        for _, r in tot.iterrows()
    }
    assert rank["Ulysses S. Grant"] == 1
    assert rank["Horace Greeley"] == max(rank.values())
    assert set(tot.loc[tot["took_office"], "candidate_id"].map(by_id)) == {
        "Ulysses S. Grant"
    }


def test_run_ec_pipeline_2024_footnoted_state_offline(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 2024 exercises the modern footnote format (a non-breaking space between a state
    # label and its <sup> marker, e.g. Oregon) plus Maine/Nebraska district splits.
    # All 538 electoral votes must reconcile: Trump 312, Harris 226 (Oregon's 8 for
    # Harris are only present if the footnoted label was not dropped).
    record_inserts(monkeypatch)
    candidates_df, _state_df, votes_df = run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        replace=True,
        years={2024},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )
    tot = votes_df[votes_df["is_total"]].merge(
        candidates_df[["candidate_id", "name"]], on="candidate_id"
    )
    ev = {r["name"]: int(r["president_electoral_votes"]) for _, r in tot.iterrows()}
    assert ev == {"Donald J. Trump": 312, "Kamala D. Harris": 226}


def test_run_ec_pipeline_leaves_connection_open_by_default(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_inserts(monkeypatch)
    run_ec_pipeline(
        make_dbc(recording_conn),
        "unused.shp",
        years={2016, 2020},
        fetch=fetch_from_dir(FIXTURES_DIR),
        load_geo=lambda _p: fake_state_geo(),
    )
    # The caller owns the dbc; the pipeline must not close it by default.
    assert recording_conn.closed is False


def _fetch_with_stale_index(years: tuple[int, ...]) -> Fetch:
    """Serve the real fixture pages, but an index linking only ``years``.

    The shape of a stale corpus (or a restructured Archives index): the year pages are
    fine, the *index* is what has fallen behind, so a requested year is never
    enumerated and therefore never fetched.
    """
    real = fetch_from_dir(FIXTURES_DIR)
    index_url = scrape.ARCHIVE_URL_DOMAIN + scrape.ARCHIVE_URL_BASE

    def fetch(url: str) -> bytes:
        if url == index_url:
            links = "".join(
                f'<a href="/electoral-college/{y}">{y}</a>' for y in years
            )
            return f'<div id="main-col"><table>{links}</table></div>'.encode()
        return real(url)

    return fetch


def test_run_ec_pipeline_refuses_a_scrape_missing_a_requested_year(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pipeline must *invoke* the completeness guard, not merely define it.

    ``_assert_years_scraped`` had unit tests calling it directly, but nothing pinned
    that ``run_ec_pipeline`` calls it — deleting the call site left the whole suite
    green. That is the guard whose entire job is to stop a silently-partial warehouse
    reaching the public API snapshot, so its call site matters as much as its logic.

    2024 is requested but the fixture index does not link it, so the scrape returns
    nothing for it: exactly the stale-corpus / restructured-index shape.
    """
    record_inserts(monkeypatch)

    with pytest.raises(PipelineError, match=r"2024"):
        run_ec_pipeline(
            make_dbc(recording_conn),
            "unused.shp",
            years={2016, 2020, 2024},
            fetch=_fetch_with_stale_index((2016, 2020)),
            load_geo=lambda _p: fake_state_geo(),
        )


def test_run_ec_pipeline_fails_before_touching_the_database(
    recording_conn: RecordingConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An incomplete scrape must abort *before* the transaction, not during it.

    On the ``replace=True`` path the load opens with ``DROP SCHEMA dwh CASCADE``. If
    the guard ran after that, a stale corpus would leave the operator with **no**
    warehouse rather than the previous good one. Ordering is the safety property here.
    """
    inserts = record_inserts(monkeypatch)

    with pytest.raises(PipelineError):
        run_ec_pipeline(
            make_dbc(recording_conn),
            "unused.shp",
            replace=True,
            years={2016, 2020, 2024},
            fetch=_fetch_with_stale_index((2016, 2020)),
            load_geo=lambda _p: fake_state_geo(),
        )

    assert inserts == []
    assert not any("DROP SCHEMA" in q.upper() for q in recording_conn.executed)
