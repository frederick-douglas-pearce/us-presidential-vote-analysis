"""Unit tests for ``python -m usvote.census`` (#181, added by the round-1 review).

The census `__main__` shipped with **no tests at all** — a `main()` dispatching bare to
`snapshot` (hitting the network instead of loading) would have passed the whole suite,
and the acceptance criterion is specifically "a `__main__.py` dispatching a `load`
subcommand (the D027 convention)".

The `except` arm gets the most attention here, because an untested arm is exactly how it
came to be too narrow: it caught only two of the three sibling error types its own module
defines, so a `CensusParseError` — the one a layout change raises — escaped uncaught and
leaked the connection the arm exists to close.
"""

from __future__ import annotations

from typing import Any

import psycopg2
import pytest

import usvote.census.__main__ as census_main

_DB = {"host": "h", "user": "u", "dbname": "d", "password": "p"}


class _FakeDBC:
    def __init__(self) -> None:
        self.closed = False

    def close_connection(self) -> None:
        self.closed = True


@pytest.fixture
def census_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch the CLI's seams; record what `run_census_pipeline` was called with."""
    state: dict[str, Any] = {"calls": [], "dbc": _FakeDBC(), "snapshots": []}

    monkeypatch.setattr(
        census_main.config, "db_config_from_env", lambda *a, **k: dict(_DB)
    )
    monkeypatch.setattr(
        census_main, "census_corpus_dir_from_env", lambda *a, **k: "corpus/"
    )
    monkeypatch.setattr(census_main, "DBC", lambda cfg: state["dbc"])

    import pandas as pd

    def pipeline(dbc: Any, corpus_dir: Any, **kwargs: Any) -> pd.DataFrame:
        state["calls"].append({"corpus_dir": corpus_dir, **kwargs})
        return pd.DataFrame(
            {"census_year": [1850, 2020], "state": ["Connecticut", "Virginia"]}
        )

    monkeypatch.setattr(census_main, "run_census_pipeline", pipeline)
    monkeypatch.setattr(
        census_main,
        "snapshot_census_sources",
        lambda d: state["snapshots"].append(d),
    )
    monkeypatch.setattr(census_main, "describe_corpus", lambda d: "2 files, fetched x")
    return state


class TestDispatch:
    def test_bare_runs_load_not_snapshot(self, census_env: dict[str, Any]) -> None:
        """The D027 default, and the one that silently matters.

        UCSB's bare command means `snapshot`; census deliberately takes MIT's `load`
        default instead. Nothing else in the suite would notice the two being swapped —
        and swapped, the shipped bare command hits the network rather than the database.
        """
        assert census_main.main([]) == 0
        assert len(census_env["calls"]) == 1
        assert census_env["snapshots"] == []

    def test_explicit_load_matches_bare(self, census_env: dict[str, Any]) -> None:
        assert census_main.main(["load"]) == 0
        assert census_env["calls"][0]["replace"] is False

    def test_snapshot_runs_the_snapshot_and_touches_no_database(
        self, census_env: dict[str, Any]
    ) -> None:
        assert census_main.main(["snapshot"]) == 0
        assert census_env["snapshots"] == ["corpus/"]
        assert census_env["calls"] == []

    def test_replace_is_forwarded(self, census_env: dict[str, Any]) -> None:
        assert census_main.main(["load", "--replace"]) == 0
        assert census_env["calls"][0]["replace"] is True

    def test_the_connection_is_closed_by_the_pipeline_on_the_happy_path(
        self, census_env: dict[str, Any]
    ) -> None:
        assert census_main.main([]) == 0
        assert census_env["calls"][0]["close"] is True


class TestErrorArm:
    """`run_census_pipeline` has no try/finally, so its `close=True` never fires on a
    raise. Every error the CLI can meet must therefore be caught *here* or the
    connection leaks — which is what the arm's own comment claims it prevents."""

    @pytest.mark.parametrize(
        "error",
        [
            census_main.CensusScrapeError("corpus incomplete"),
            census_main.CensusTransformError("unknown jurisdiction"),
            census_main.CensusParseError("layout changed"),
            psycopg2.errors.UniqueViolation("already loaded"),
        ],
        ids=["scrape", "transform", "parse", "unique-violation"],
    )
    def test_every_reachable_error_is_caught_and_closes_the_connection(
        self,
        census_env: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        error: Exception,
    ) -> None:
        def boom(*a: Any, **k: Any) -> None:
            raise error

        monkeypatch.setattr(census_main, "run_census_pipeline", boom)
        assert census_main.main([]) == 1
        assert census_env["dbc"].closed, "the connection leaked"
        assert "Census load failed" in capsys.readouterr().err

    def test_a_unique_violation_is_explained_as_the_non_destructive_guard(
        self,
        census_env: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # A second bare run hitting the natural-key UNIQUE is the *documented* behaviour,
        # not a crash — so the message has to say so and name --replace, or the operator
        # reads a working guard as a bug.
        def boom(*a: Any, **k: Any) -> None:
            raise psycopg2.errors.UniqueViolation("duplicate key")

        monkeypatch.setattr(census_main, "run_census_pipeline", boom)
        census_main.main([])
        assert "--replace" in capsys.readouterr().err


class TestConfigErrors:
    def test_an_unresolvable_corpus_returns_the_config_exit_code(
        self, census_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from usvote.config import ConfigError

        def unset(*a: Any, **k: Any) -> str:
            raise ConfigError("USVOTE_CENSUS_CORPUS_DIR is not set.")

        monkeypatch.setattr(census_main, "census_corpus_dir_from_env", unset)
        # 2, not 1: a misconfiguration is distinct from a failed run, and the sibling
        # entry points use the same code for it.
        assert census_main.main([]) == 2
        assert census_env["calls"] == []
