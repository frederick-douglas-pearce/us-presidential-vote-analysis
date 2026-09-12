"""Unit tests for :mod:`usvote.census.pipeline` and :mod:`usvote.census.config` (#181).

Asserts the *composition* — stage order, the transaction contract, the spine-read seam,
and the connection-lifetime rules — with the stages patched, so nothing here touches a
database or the network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tests._helpers import RecordingConnection, ec_participation_frame, make_dbc
from usvote.census import pipeline as census_pipeline
from usvote.census.config import (
    CENSUS_CORPUS_DIR_VAR,
    census_corpus_dir_from_env,
)
from usvote.census.pipeline import run_census_pipeline
from usvote.config import ConfigError


@pytest.fixture
def stages(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Patch every stage to record its name, keeping the real call order."""
    calls: list[str] = []

    def read(corpus_dir: Any, *, source_ids: Any = None, environ: Any = None) -> dict:
        calls.append("read")
        return {"resident_1790_1990": b"a", "resident_1910_2020": b"b"}

    def spine(dbc: Any, **_: Any) -> pd.DataFrame:
        calls.append("spine")
        return ec_participation_frame(years=[2020])

    def transform(rows: Any, ec: pd.DataFrame) -> pd.DataFrame:
        calls.append("transform")
        return pd.DataFrame({"x": [1, 2, 3]})

    def load(dbc: Any, frame: pd.DataFrame, *, replace: bool = False) -> pd.DataFrame:
        calls.append(f"load(replace={replace})")
        return frame

    monkeypatch.setattr(census_pipeline, "read_snapshot_sources", read)
    monkeypatch.setattr(census_pipeline, "read_ec_participation", spine)
    monkeypatch.setattr(census_pipeline, "transform_census", transform)
    monkeypatch.setattr(census_pipeline, "load_census_population", load)
    monkeypatch.setattr(
        census_pipeline,
        "_PARSERS",
        {
            "resident_1790_1990": lambda data, *, source_id: [],
            "resident_1910_2020": lambda data, *, source_id: [],
        },
    )
    return calls


def test_the_stages_run_in_order(stages: list[str]) -> None:
    run_census_pipeline(make_dbc(RecordingConnection()), "corpus/")
    assert stages == ["read", "spine", "transform", "load(replace=False)"]


def test_the_corpus_is_read_before_the_database_is_touched(stages: list[str]) -> None:
    # The completeness guard lives in the read seam, so a short corpus must fail before
    # the pipeline opens a transaction — "nothing was loaded" has to be true.
    run_census_pipeline(make_dbc(RecordingConnection()), "corpus/")
    assert stages.index("read") < stages.index("spine")


def test_the_write_happens_in_exactly_one_transaction(stages: list[str]) -> None:
    """Per-source atomicity, matching both PV pipelines.

    A partial census load is worse than none: the natural-key constraint means the
    retry then fails on the rows that did land, so the recovery would be a manual
    delete rather than a re-run.
    """
    conn = RecordingConnection()
    run_census_pipeline(make_dbc(conn), "corpus/")
    assert conn.commits == 1
    assert conn.rollbacks == 0


def test_the_spine_read_happens_outside_the_transaction(
    monkeypatch: pytest.MonkeyPatch, stages: list[str]
) -> None:
    # Holding a transaction open across a read buys nothing and lengthens the window in
    # which the census table is locked.
    conn = RecordingConnection()
    commits_at_spine: list[int] = []

    real_spine = census_pipeline.read_ec_participation

    def watching(dbc: Any, **kwargs: Any) -> pd.DataFrame:
        commits_at_spine.append(conn.commits)
        return real_spine(dbc, **kwargs)

    monkeypatch.setattr(census_pipeline, "read_ec_participation", watching)
    run_census_pipeline(make_dbc(conn), "corpus/")
    assert commits_at_spine == [0], "the spine read ran inside the write transaction"


def test_replace_is_forwarded_to_the_loader(stages: list[str]) -> None:
    run_census_pipeline(make_dbc(RecordingConnection()), "corpus/", replace=True)
    assert "load(replace=True)" in stages


def test_the_connection_is_left_open_by_default(stages: list[str]) -> None:
    # The caller owns the dbc it passed in — the warehouse orchestrator reuses it for
    # the stages that follow.
    conn = RecordingConnection()
    run_census_pipeline(make_dbc(conn), "corpus/")
    assert not conn.closed


def test_close_is_honoured_when_asked(stages: list[str]) -> None:
    conn = RecordingConnection()
    run_census_pipeline(make_dbc(conn), "corpus/", close=True)
    assert conn.closed


def test_there_is_no_years_parameter(stages: list[str]) -> None:
    """``years`` means *election* years everywhere else in this package.

    Census rows are keyed by *decennial* years, and one name meaning two domains is how
    #182's conformance work would come to conflate them. The whole series is ~1,000
    rows, so there is nothing to scope for either.
    """
    import inspect

    assert "years" not in inspect.signature(run_census_pipeline).parameters


class TestConfig:
    def test_it_resolves_the_directory_from_the_environment(
        self, tmp_path: Path
    ) -> None:
        assert census_corpus_dir_from_env(
            {CENSUS_CORPUS_DIR_VAR: str(tmp_path)}
        ) == str(tmp_path)

    def test_an_unset_variable_names_the_command_that_populates_it(self) -> None:
        with pytest.raises(ConfigError, match="python -m usvote.census snapshot"):
            census_corpus_dir_from_env({})

    def test_a_missing_directory_is_refused_on_the_read_path(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ConfigError, match="does not exist"):
            census_corpus_dir_from_env({CENSUS_CORPUS_DIR_VAR: str(tmp_path / "nope")})

    def test_the_write_path_accepts_a_directory_that_does_not_exist_yet(
        self, tmp_path: Path
    ) -> None:
        """``must_exist=False`` is the snapshot side, and it is not laxness.

        The snapshot *creates* this directory. Requiring it to pre-exist would fail a
        fresh machine with advice to run the very command that just failed.
        """
        target = tmp_path / "not-yet"
        assert census_corpus_dir_from_env(
            {CENSUS_CORPUS_DIR_VAR: str(target)}, must_exist=False
        ) == str(target)

    def test_an_unset_variable_is_refused_even_on_the_write_path(self) -> None:
        # must_exist=False relaxes the *directory* requirement, never the variable one —
        # there is no sensible default for a machine-local data directory.
        with pytest.raises(ConfigError, match="is not set"):
            census_corpus_dir_from_env({}, must_exist=False)
