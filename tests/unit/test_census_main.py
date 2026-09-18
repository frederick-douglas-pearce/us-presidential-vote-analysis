"""Unit tests for ``python -m usvote.census`` (#181, added by the round-1 review).

The census `__main__` shipped with **no tests at all** — a `main()` dispatching bare to
`snapshot` (hitting the network instead of loading) would have passed the whole suite,
and the acceptance criterion is specifically "a `__main__.py` dispatching a `load`
subcommand (the D027 convention)".

The error handling gets the most attention here, because an untested arm is exactly how
it came to be wrong twice: first it caught only two of the three sibling error types its
own module defines, so a `CensusParseError` — the one a layout change raises — escaped
uncaught; then the fix for *that* widened it to the whole `psycopg2.Error` tree in order
to close the connection, and printed advice fitting only one of them.

The arrangement those two rounds arrived at separates the concerns: the arm **reports**,
naming each error it can give useful advice about, and a `finally` **closes** on every
path including the ones nobody named.
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
    state: dict[str, Any] = {
        "calls": [],
        "dbc": _FakeDBC(),
        "snapshots": [],
        "view_rebuilds": [],
    }

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

    # #184: `_run_load` rebuilds the per-capita view after the pipeline returns. Record
    # it rather than letting it reach the fake connection -- the CASCADE regression it
    # repairs is what `tests/integration/test_census_per_capita.py` proves against a
    # real database; here we only need to know the CLI still calls it.
    def rebuild_view(dbc: Any) -> bool:
        state["view_rebuilds"].append(dbc)
        return True

    monkeypatch.setattr(census_main, "create_per_capita_view", rebuild_view)
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

    def test_the_cli_owns_the_close_not_the_pipeline(
        self, census_env: dict[str, Any]
    ) -> None:
        """One owner, one exit.

        The CLI no longer passes ``close=True`` — it closes in a ``finally``. That is
        the stronger arrangement: ``run_census_pipeline`` has no ``try/finally``, so its
        own ``close=True`` never fires on a raise, and a DB error the CLI does not
        *name* would leak the connection just as surely as one it fails to catch.
        """
        assert census_main.main([]) == 0
        assert census_env["calls"][0].get("close") is not True
        assert census_env["dbc"].closed


class TestErrorArm:
    """Two separable properties, and the split is the point.

    ``run_census_pipeline`` has no ``try/finally``, so its own ``close=True`` never fires
    on a raise. **Closing** is therefore the CLI's job on every path — which a ``finally``
    does, without the catch having to be wide. **Reporting** is a separate question: each
    error the CLI names gets advice that fits it, and an error it does not name simply
    propagates with the connection already closed.
    """

    @pytest.mark.parametrize(
        "error",
        [
            census_main.CensusScrapeError("corpus incomplete"),
            census_main.CensusTransformError("unknown jurisdiction"),
            census_main.CensusParseError("layout changed"),
        ],
        ids=["scrape", "transform", "parse"],
    )
    def test_each_ingest_error_is_caught_and_reported_as_nothing_loaded(
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
        err = capsys.readouterr().err
        assert "Census load failed" in err
        assert "Nothing was loaded" in err

    @pytest.mark.parametrize(
        "error",
        [
            psycopg2.errors.ForeignKeyViolation("orphan state"),
            psycopg2.OperationalError("server closed the connection"),
            RuntimeError("something nobody anticipated"),
        ],
        ids=["fk-violation", "operational", "unanticipated"],
    )
    def test_an_unnamed_error_still_closes_the_connection(
        self,
        census_env: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        error: Exception,
    ) -> None:
        """The property the ``finally`` exists for, and the reason the catch is narrow.

        An earlier version caught the whole ``psycopg2.Error`` tree *in order to* close
        the connection, and paid for it by printing UniqueViolation advice at a
        ForeignKeyViolation. Closing in a ``finally`` instead means the catch can be
        narrow and honest while the connection is still safe on paths nobody named —
        including a non-psycopg2 error, which the broad catch never covered either.
        """

        def boom(*a: Any, **k: Any) -> None:
            raise error

        monkeypatch.setattr(census_main, "run_census_pipeline", boom)
        with pytest.raises(type(error)):
            census_main.main([])
        assert census_env["dbc"].closed, "the connection leaked on an unnamed error"

    def test_a_unique_violation_is_explained_as_the_non_destructive_guard(
        self,
        census_env: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # A second bare run hitting the natural-key UNIQUE is the *documented* behaviour,
        # not a crash — so the message has to say so and name --replace, or the operator
        # reads a working guard as a bug. It must NOT say "nothing was loaded": rows are
        # exactly what is already there.
        def boom(*a: Any, **k: Any) -> None:
            raise psycopg2.errors.UniqueViolation("duplicate key")

        monkeypatch.setattr(census_main, "run_census_pipeline", boom)
        assert census_main.main([]) == 1
        err = capsys.readouterr().err
        assert "--replace" in err
        assert "already holds these rows" in err
        assert "Nothing was loaded" not in err
        assert census_env["dbc"].closed


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


class TestTheViewRebuild:
    """#184: a `census load` rebuilds `dwh.election_per_capita` after the pipeline.

    Without it, `--replace` drops the view via `DROP TABLE ... CASCADE` and leaves it
    dropped while exiting 0, and a plain load never creates it at all — both reproduced
    against a live database during #184's review. The behaviour is proved end-to-end in
    `tests/integration/test_census_per_capita.py`; these pin that the CLI still makes
    the call, on both spellings and after the load rather than before it.
    """

    def test_a_plain_load_rebuilds_the_view(self, census_env: dict[str, Any]) -> None:
        assert census_main.main(["load"]) == 0
        assert census_env["view_rebuilds"] == [census_env["dbc"]]

    def test_a_replace_load_rebuilds_the_view(self, census_env: dict[str, Any]) -> None:
        assert census_main.main(["load", "--replace"]) == 0
        assert census_env["view_rebuilds"] == [census_env["dbc"]]

    def test_the_rebuild_is_not_attempted_when_the_load_failed(
        self, census_env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed load leaves nothing written, so there is nothing to build a view over.

        It shares the pipeline's `try`, so this is really a statement about the ordering:
        rebuilding after a raise would either fail again or build a view over a table the
        failed load did not touch.
        """

        def boom(dbc: Any, corpus_dir: Any, **kwargs: Any) -> Any:
            raise census_main.CensusParseError("a sheet the parser cannot read")

        monkeypatch.setattr(census_main, "run_census_pipeline", boom)
        assert census_main.main(["load"]) == 1
        assert census_env["view_rebuilds"] == []

    def test_a_snapshot_does_not_touch_the_view(
        self, census_env: dict[str, Any]
    ) -> None:
        assert census_main.main(["snapshot"]) == 0
        assert census_env["view_rebuilds"] == []

    def test_the_completion_line_reports_the_rebuild(
        self, census_env: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert census_main.main(["load"]) == 0
        out = capsys.readouterr().out
        assert "dwh.election_per_capita view is rebuilt" in out
        assert "SKIPPED" not in out

    def test_the_completion_line_reports_a_skip_rather_than_claiming_a_rebuild(
        self,
        census_env: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """`create_per_capita_view` returns False when its input table is absent.

        That branch is unreachable from `_run_load` today — the load immediately above
        writes `dwh.election_population`, so the probe always finds it. The message was
        still asserting the rebuild while discarding the one value that exists to report
        a skip, which is a claim that cannot be wrong today and would quietly become
        wrong the first time the two are decoupled. Found by #184's round-2 re-check.
        """

        def skipped(dbc: Any) -> bool:
            census_env["view_rebuilds"].append(dbc)
            return False

        monkeypatch.setattr(census_main, "create_per_capita_view", skipped)
        assert census_main.main(["load"]) == 0
        out = capsys.readouterr().out
        assert "SKIPPED" in out
        assert "view is rebuilt" not in out
        # The census half of the line is unaffected -- only the view clause branches.
        assert "dwh.election_population is rebuilt" in out
