"""Unit tests for the three CLI entry points (#84b).

Drives ``main(argv)`` for ``usvote.__main__``, ``usvote.mit.__main__`` and
``usvote.ucsb.__main__`` with the pipelines/orchestrator and config resolvers
monkeypatched, asserting subcommand dispatch, the bare-default paths (``usvote`` -> EC,
``usvote.ucsb`` -> snapshot, ``usvote.mit`` -> load), the ``--replace`` mapping, and the
loud/explicit UCSB gating for ``usvote all``. No DB, no network.
"""

from __future__ import annotations

import argparse
from typing import Any

import pytest

import usvote.__main__ as top
import usvote.mit.__main__ as mit_main
import usvote.ucsb.__main__ as ucsb_main
from usvote.config import ConfigError
from usvote.warehouse import (
    SOURCE_EC,
    SOURCE_MIT,
    SOURCE_UCSB,
    WarehouseResult,
)

_DB = {"user": "u", "host": "h", "password": "p"}  # password present -> no getpass


@pytest.fixture
def top_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Patch the top-level entry point's config + steps; record what dispatched."""
    calls: dict[str, list] = {"ec": [], "warehouse": []}
    monkeypatch.setattr(top.config, "shapefile_path_from_env", lambda *a, **k: "s.shp")
    monkeypatch.setattr(top.config, "db_config_from_env", lambda *a, **k: dict(_DB))
    monkeypatch.setattr(top, "mit_csv_path_from_env", lambda *a, **k: "mit.csv")
    monkeypatch.setattr(top, "DBC", lambda cfg: "DBC")
    # Hermetic: without this, anyone who exports USVOTE_EC_HTML_DIR — which this
    # feature's own TestRealCorpus REQUIRES — fails these tests, because main() resolves
    # the corpus from the real os.environ. Corpus-specific behavior is asserted in the
    # dedicated tests below, which set the variable explicitly.
    monkeypatch.delenv(top.config.EC_HTML_DIR_VAR, raising=False)

    def ec(
        dbc: object,
        shapefile_path: str,
        *,
        replace: bool = False,
        fetch: Any = None,
        close: bool = False,
    ) -> None:
        # ``fetch`` recorded so the corpus-vs-live choice (#89) is observable here.
        calls["ec"].append({"replace": replace, "fetch": fetch})

    def wh(
        dbc: object,
        shapefile_path: str,
        mit_csv_path: Any,
        *,
        ucsb_html_dir: Any,
        replace: bool,
        validate_overlap: bool,
        fetch: Any,
        environ: Any,
        close: bool,
    ) -> WarehouseResult:
        # No default on `fetch`, matching its siblings: if _run_all stopped forwarding
        # it, this double must fail rather than silently accept None.
        calls["warehouse"].append(
            {
                "ucsb_html_dir": ucsb_html_dir,
                "replace": replace,
                "validate_overlap": validate_overlap,
                "fetch": fetch,
            }
        )
        loaded = {SOURCE_EC, SOURCE_MIT} | (
            {SOURCE_UCSB} if ucsb_html_dir is not None else set()
        )
        return WarehouseResult(
            ec_rows=5,
            mit_rows=3,
            mit_roster_rows=6,
            ucsb_pv_rows=None,
            ucsb_roster_rows=None,
            sources_loaded=frozenset(loaded),
            views_built=True,
        )

    monkeypatch.setattr(top, "run_ec_pipeline", ec)
    monkeypatch.setattr(top, "run_warehouse", wh)
    return calls


@pytest.mark.parametrize(
    "argv,replace",
    [([], False), (["--replace"], True), (["ec"], False), (["ec", "--replace"], True)],
)
def test_bare_and_ec_run_the_ec_pipeline(
    top_env: dict[str, list], argv: list[str], replace: bool
) -> None:
    # Bare ``python -m usvote`` stays EC (backward compat), and ``--replace`` still works
    # bare (top-level) as well as on the explicit ``ec`` subcommand.
    assert top.main(argv) == 0
    assert top_env["ec"] == [{"replace": replace, "fetch": top.scrape.fetch_url}]
    assert top_env["warehouse"] == []


def test_all_autodetects_ucsb_when_snapshot_present(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(top, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    assert top.main(["all", "--replace"]) == 0
    assert top_env["warehouse"] == [
        {
            "ucsb_html_dir": "snap/",
            "replace": True,
            "validate_overlap": True,
            "fetch": top.scrape.fetch_url,
        }
    ]


def test_all_skips_ucsb_loudly_when_snapshot_absent(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    def absent(*a: Any, **k: Any) -> str:
        raise ConfigError("USVOTE_UCSB_HTML_DIR unset")

    monkeypatch.setattr(top, "ucsb_html_dir_from_env", absent)
    assert top.main(["all"]) == 0
    assert top_env["warehouse"] == [
        {
            "ucsb_html_dir": None,
            "replace": False,
            "validate_overlap": True,
            "fetch": top.scrape.fetch_url,
        }
    ]
    # The skip must be loud (D024): a prominent notice on stderr.
    assert "WITHOUT UCSB" in capsys.readouterr().err


def test_all_no_ucsb_skips_without_probing_env(
    top_env: dict[str, list],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    # ``--no-ucsb`` must skip even if a snapshot exists, and must not consult the env.
    def boom(*a: Any, **k: Any) -> str:
        raise AssertionError("ucsb_html_dir_from_env must not be called for --no-ucsb")

    monkeypatch.setattr(top, "ucsb_html_dir_from_env", boom)
    assert top.main(["all", "--no-ucsb"]) == 0
    assert top_env["warehouse"] == [
        {
            "ucsb_html_dir": None,
            "replace": False,
            "validate_overlap": True,
            "fetch": top.scrape.fetch_url,
        }
    ]
    # Still loud (D024), but the remedy acknowledges the deliberate choice rather than
    # suggesting --require-ucsb / USVOTE_UCSB_HTML_DIR as if UCSB were missing by accident.
    err = capsys.readouterr().err
    assert "WITHOUT UCSB" in err
    assert "--no-ucsb" in err
    assert "--require-ucsb" not in err


def test_all_require_ucsb_fails_when_snapshot_absent(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    def absent(*a: Any, **k: Any) -> str:
        raise ConfigError("USVOTE_UCSB_HTML_DIR unset")

    monkeypatch.setattr(top, "ucsb_html_dir_from_env", absent)
    # --require-ucsb turns an absent snapshot into a hard config failure (exit 2), never
    # a silent EC+MIT build.
    assert top.main(["all", "--require-ucsb"]) == 2
    assert top_env["warehouse"] == []


def test_config_error_returns_2(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    def absent(*a: Any, **k: Any) -> str:
        raise ConfigError("USVOTE_SHAPEFILE_PATH unset")

    monkeypatch.setattr(top.config, "shapefile_path_from_env", absent)
    assert top.main(["ec"]) == 2
    assert top_env["ec"] == []


# --- usvote.ucsb -----------------------------------------------------------------


@pytest.fixture
def ucsb_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    calls: dict[str, list] = {"snapshot": [], "load": []}
    monkeypatch.setattr(ucsb_main, "snapshot_elections", lambda: calls["snapshot"].append({}))
    monkeypatch.setattr(ucsb_main.config, "db_config_from_env", lambda *a, **k: dict(_DB))
    monkeypatch.setattr(ucsb_main, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    monkeypatch.setattr(ucsb_main, "DBC", lambda cfg: "DBC")
    monkeypatch.setattr(
        ucsb_main,
        "run_ucsb_pipeline",
        lambda dbc, html_dir, *, replace=False, close=False: calls["load"].append(
            {"html_dir": html_dir, "replace": replace}
        ),
    )
    return calls


@pytest.mark.parametrize("argv", [[], ["snapshot"]])
def test_ucsb_bare_and_snapshot_snapshot(
    ucsb_env: dict[str, list], argv: list[str]
) -> None:
    # Bare ``python -m usvote.ucsb`` keeps its D023 meaning: snapshot, not load.
    assert ucsb_main.main(argv) == 0
    assert ucsb_env["snapshot"] == [{}]
    assert ucsb_env["load"] == []


@pytest.mark.parametrize("argv,replace", [(["load"], False), (["load", "--replace"], True)])
def test_ucsb_load_runs_pipeline(
    ucsb_env: dict[str, list], argv: list[str], replace: bool
) -> None:
    assert ucsb_main.main(argv) == 0
    assert ucsb_env["load"] == [{"html_dir": "snap/", "replace": replace}]
    assert ucsb_env["snapshot"] == []


# --- usvote.mit ------------------------------------------------------------------


def _recording_mit_pipeline(calls: list[dict]) -> Any:
    """A ``run_mit_pipeline`` double returning the ``(pv_votes, roster)`` pair (#127).

    A named function rather than a lambda because the double must both record *and*
    return the pair — ``__main__`` unpacks it to report each table's row count.
    """

    def _fake(
        dbc: object, path: Any, *, replace: bool = False, close: bool = False
    ) -> tuple[list[int], list[int]]:
        calls.append({"path": path, "replace": replace})
        return ([0] * 2, [0] * 3)

    return _fake


@pytest.fixture
def mit_env(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(mit_main.config, "db_config_from_env", lambda *a, **k: dict(_DB))
    monkeypatch.setattr(mit_main, "mit_csv_path_from_env", lambda *a, **k: "mit.csv")
    monkeypatch.setattr(mit_main, "DBC", lambda cfg: "DBC")
    monkeypatch.setattr(
        mit_main,
        "run_mit_pipeline",
        _recording_mit_pipeline(calls),
    )
    return calls


@pytest.mark.parametrize(
    "argv,replace", [([], False), (["load"], False), (["load", "--replace"], True)]
)
def test_mit_bare_and_load_run_pipeline(
    mit_env: list[dict], argv: list[str], replace: bool
) -> None:
    # Bare ``python -m usvote.mit`` loads (the single subcommand's default).
    assert mit_main.main(argv) == 0
    assert mit_env == [{"path": "mit.csv", "replace": replace}]


# --- corpus resolution at the CLI (#89) -------------------------------------
# The tests the top_env fixture's comment claimed existed but did not. Without them
# three separate mutations disabled the offline-rebuild feature with a green suite:
# main() never calling _resolve_ec_fetch, _resolve_ec_fetch returning fetch_url
# immediately, and the `corpus` subcommand falling through to the DB load path. Each
# was invisible because the fixture unsets USVOTE_EC_HTML_DIR, so every other
# entry-point test exercises only the live branch — where the expected fetch is
# fetch_url either way, i.e. identical in the working and broken states.


def _valid_corpus(tmp_path: Any) -> str:
    """A corpus that satisfies assert_corpus_covers_years for the years it holds."""
    from usvote import scrape as ec_scrape
    from usvote.years import ec_ingest_years

    years = sorted(ec_ingest_years())

    def fetch(url: str) -> tuple[int, bytes]:
        if url.endswith("/results"):
            links = "".join(
                f'<a href="/electoral-college/{y}">{y}</a>' for y in years
            )
            return 200, f'<div id="main-col"><table>{links}</table></div>'.encode()
        return 200, b'<div id="main-col"><table><tr><td>x</td></tr></table></div>'

    ec_scrape.snapshot_election_years(tmp_path, fetch=fetch, sleep=lambda s: None)
    return str(tmp_path)


def test_ec_uses_the_corpus_when_the_env_var_points_at_a_complete_one(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, _valid_corpus(tmp_path))
    assert top.main([]) == 0
    # Assert what the resolved fetch actually READS, not merely that it differs from
    # fetch_url. The negative identity check this replaces was satisfied by any other
    # callable — and a wrong reader (fetch_from_dir, which resolves to the fixtures
    # naming) once shipped on this branch and went green through the whole suite.
    fetch = top_env["ec"][0]["fetch"]
    body = fetch("https://www.archives.gov/electoral-college/2020")
    assert b"main-col" in body


def test_no_corpus_forces_the_live_fetch_even_with_a_corpus_present(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, _valid_corpus(tmp_path))
    assert top.main(["--no-corpus", "ec"]) == 0
    assert top_env["ec"][0]["fetch"] is top.scrape.fetch_url


def test_all_uses_the_corpus_too(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setattr(top, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, _valid_corpus(tmp_path))
    assert top.main(["all"]) == 0
    fetch = top_env["warehouse"][0]["fetch"]
    assert b"main-col" in fetch("https://www.archives.gov/electoral-college/2020")


def test_a_stale_corpus_exits_cleanly_without_running_the_pipeline(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    # Set-but-incomplete must be a hard error, never a silent fall back to ~50 live
    # requests, and never a raw traceback. The pipeline must not run at all.
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, str(tmp_path / "empty"))
    assert top.main([]) == 2
    assert top_env["ec"] == []


def test_corpus_subcommand_dispatches_to_the_corpus_runner(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    def fake_corpus(args: Any) -> int:
        called.append("ran")
        return 0

    monkeypatch.setattr(top, "_run_corpus", fake_corpus)
    assert top.main(["corpus"]) == 0
    assert called == ["ran"]


# --- _run_corpus: the runner itself, not just its dispatch (#89) ------------
# Round 3 pinned that `corpus` DISPATCHES; the runner it dispatches to stayed 0%
# covered — poisoning its whole body with `raise AssertionError` left the suite green.
# These cover the exit codes, the fresh-machine path, and the page count.


def test_corpus_runner_reports_pages_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture
) -> None:
    corpus = _valid_corpus(tmp_path)
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, corpus)
    # MUST stub the snapshot. Without it this test hit archives.gov for real: _run_corpus
    # calls snapshot_election_years with its default live fetch, and the index is
    # force-refetched every run by design, so the "offline unit suite" invariant broke and
    # the live index silently overwrote the synthetic one under test.
    monkeypatch.setattr(top.scrape, "snapshot_election_years", lambda d: None)
    assert top._run_corpus(argparse.Namespace()) == 0
    out = capsys.readouterr().out
    # Counted from files on disk, so a stale manifest key cannot inflate it.
    assert "51 year page(s)" in out


def test_corpus_runner_resolves_a_directory_that_does_not_exist_yet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    # must_exist=False on this path only: the corpus dir is an OUTPUT here. Requiring
    # it to pre-exist made a fresh machine fail with advice to run this very command.
    target = tmp_path / "not-yet"
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, str(target))
    monkeypatch.setattr(
        top.scrape, "snapshot_election_years", lambda d: {"2020": {"http_status": 200}}
    )
    assert top._run_corpus(argparse.Namespace()) == 0


def test_corpus_runner_exits_2_when_the_variable_is_unset(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.delenv(top.config.EC_HTML_DIR_VAR, raising=False)
    assert top._run_corpus(argparse.Namespace()) == 2
    assert "Configuration error" in capsys.readouterr().err


def test_corpus_runner_exits_1_on_a_scrape_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, str(tmp_path))

    def boom(_d: Any) -> None:
        raise top.scrape.ScrapeError("archives returned 503")

    monkeypatch.setattr(top.scrape, "snapshot_election_years", boom)
    assert top._run_corpus(argparse.Namespace()) == 1
    assert "503" in capsys.readouterr().err


def test_corpus_runner_reports_progress_on_interrupt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture
) -> None:
    # Ctrl-C is likely on a ~8.5-minute crawl; saved pages persist, so the message must
    # be the accurate reassuring one rather than a traceback.
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, str(tmp_path))

    def interrupted(_d: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(top.scrape, "snapshot_election_years", interrupted)
    assert top._run_corpus(argparse.Namespace()) == 1
    assert "are kept" in capsys.readouterr().err


def test_corpus_banner_reports_the_corpus_age(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch, tmp_path: Any,
    capsys: pytest.CaptureFixture,
) -> None:
    # The cheapest mitigation for the D036 content-divergence residual: a stale corpus
    # is otherwise indistinguishable from "nothing changed upstream", all the way
    # through to the deployed snapshot hash.
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, _valid_corpus(tmp_path))
    assert top.main([]) == 0
    assert "51 year pages, fetched" in capsys.readouterr().out


# --- PipelineError must reach the operator as a message, not a traceback ----
# _assert_years_scraped is reachable in normal operation (a stale saved index passes
# assert_corpus_covers_years, which never reads _index_results.html), but neither
# _run_ec nor _run_all handled it — so its carefully-worded refusal arrived as an
# uncaught traceback, and the connection leaked because close=True is never reached.


class _RecordingDBC:
    """A DBC double that records whether the CLI closed it."""

    def __init__(self, _cfg: Any) -> None:
        self.closed = False

    def close_connection(self) -> None:
        self.closed = True


@pytest.fixture
def recording_dbc(monkeypatch: pytest.MonkeyPatch) -> list[_RecordingDBC]:
    made: list[_RecordingDBC] = []

    def make(cfg: Any) -> _RecordingDBC:
        made.append(_RecordingDBC(cfg))
        return made[-1]

    monkeypatch.setattr(top, "DBC", make)
    return made


def _raise_incomplete(*a: Any, **k: Any) -> None:
    raise top.PipelineError("Scrape returned no tables for 1 requested year(s): [2024].")


def test_ec_reports_an_incomplete_scrape_without_a_traceback(
    top_env: dict[str, list],
    recording_dbc: list[_RecordingDBC],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr(top, "run_ec_pipeline", _raise_incomplete)
    assert top.main([]) == 1
    err = capsys.readouterr().err
    # The guard's own wording must survive to the operator — it is the only place the
    # remedy (stale corpus / changed index) is stated.
    assert "2024" in err
    assert "Incomplete scrape" in err


def test_ec_closes_the_connection_when_the_scrape_is_incomplete(
    top_env: dict[str, list],
    recording_dbc: list[_RecordingDBC],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # close=True never fires: the pipeline raises before its own close. Without an
    # explicit close here the error path leaks a connection the success path does not.
    monkeypatch.setattr(top, "run_ec_pipeline", _raise_incomplete)
    assert top.main([]) == 1
    assert [d.closed for d in recording_dbc] == [True]


def test_all_reports_an_incomplete_scrape_without_a_traceback(
    top_env: dict[str, list],
    recording_dbc: list[_RecordingDBC],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    # run_warehouse sequences run_ec_pipeline, so the same guard fires on this path;
    # `all` needs its own handler because _run_all's try covers only config resolution.
    monkeypatch.setattr(top, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    monkeypatch.setattr(top, "run_warehouse", _raise_incomplete)
    assert top.main(["all"]) == 1
    assert "Incomplete scrape" in capsys.readouterr().err
    assert [d.closed for d in recording_dbc] == [True]


def test_corpus_page_count_ignores_a_stale_out_of_scope_manifest_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture
) -> None:
    """The count must come from the in-scope years, not from manifest keys.

    A stale out-of-scope key exists *because* the page was once fetched, so its file is
    on disk too — and-ing a file-existence check onto a manifest iteration therefore
    does not stop it inflating the count.

    The stale key is now **1820**, a pre-``EC_SPINE_FLOOR`` year. It was 1868 until #143
    ingested that year and 1872 until #144 ingested this one, at which point
    ``UNSUPPORTED_EC_YEARS`` became empty and there was no gated year left to stand in.
    Each swap keeps the test honest about which years are genuinely out of scope rather
    than weakening it — and 1820 is the realistic case now, since a corpus built under a
    lower floor (the deferred pre-1824 era, D010) would carry exactly this.
    """
    corpus = _valid_corpus(tmp_path)
    (tmp_path / "1820.html").write_bytes(b"<html></html>")
    manifest = top.scrape.read_manifest(corpus)
    manifest["1820"] = {"http_status": 200, "file": "1820.html"}
    top.scrape.write_manifest(corpus, manifest)
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, corpus)
    monkeypatch.setattr(top.scrape, "snapshot_election_years", lambda d: None)
    assert top._run_corpus(argparse.Namespace()) == 0
    assert "51 year page(s)" in capsys.readouterr().out


# --- AC-verify round 5: the `all` corpus branch, unguarded until now --------
# `all` is the front door the API-snapshot refresh runs through (D034), yet only the
# bare/`ec` path had corpus tests. Three mutations survived: `all` returning 0 on a
# broken corpus, the resolve-before-connect ordering, and `--no-corpus` on its parser.


def test_all_exits_2_on_a_stale_corpus_without_building(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    # The whole ScrapeError branch of _run_all was untested: returning 0 here left the
    # suite green while `python -m usvote all` reported SUCCESS having built nothing.
    monkeypatch.setattr(top, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, str(tmp_path / "empty"))
    assert top.main(["all"]) == 2
    assert top_env["warehouse"] == []


def test_all_resolves_the_corpus_before_connecting(
    top_env: dict[str, list],
    recording_dbc: list[_RecordingDBC],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Pin the ordering the code claims but nothing enforced.

    ``_run_all`` resolves the fetch inside the same try as the config, *before*
    ``_connect``, so a stale corpus aborts before the operator types a DB password —
    otherwise the run dies holding an open connection that ``close=True`` never reaches.
    Moving the resolve after ``_connect`` left the whole suite green.
    """
    monkeypatch.setattr(top, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, str(tmp_path / "empty"))
    assert top.main(["all"]) == 2
    assert recording_dbc == []


def test_all_accepts_no_corpus(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    # --no-corpus was only ever exercised on `ec`; dropping it from the `all` subparser
    # turned `usvote all --no-corpus` into an argparse error with the suite still green.
    monkeypatch.setattr(top, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    monkeypatch.setenv(top.config.EC_HTML_DIR_VAR, _valid_corpus(tmp_path))
    assert top.main(["all", "--no-corpus"]) == 0
    assert top_env["warehouse"][0]["fetch"] is top.scrape.fetch_url


def test_an_unset_corpus_variable_is_announced(
    top_env: dict[str, list], capsys: pytest.CaptureFixture
) -> None:
    # A *misspelled* variable name is indistinguishable from an unset one, and the two
    # differ by ~50 live requests — so the fallback to live scraping must say so. The
    # top_env fixture unsets the variable, which is exactly this case.
    assert top.main([]) == 0
    out = capsys.readouterr().out
    assert top.config.EC_HTML_DIR_VAR in out
    assert "scraping archives.gov live" in out


# --- the D017 layer-3 overlap gates on the CLI (#167) -------------------------


def test_all_forwards_no_validate_overlap(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--no-validate-overlap`` must reach ``run_warehouse``, not just parse.

    The flag is the only escape hatch from a gate whose thresholds D051 expects to
    retune, and the failure it exists for happens after a multi-minute build — so a flag
    that parses and is then dropped is worse than no flag at all.
    """
    monkeypatch.setattr(top, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    assert top.main(["all", "--no-validate-overlap"]) == 0
    assert top_env["warehouse"][0]["validate_overlap"] is False


def test_a_breached_overlap_gate_reports_instead_of_raising(
    top_env: dict[str, list],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """A gate breach exits 1 with guidance, not a traceback.

    ``PVOverlapError`` is a ``RuntimeError`` sibling of ``PipelineError``, not a
    subclass, so it needs its own arm — and this path is on the deploy runbook
    (``docs/deploy-cloud-run.md`` runs ``python -m usvote all`` before the snapshot).
    The message must say the warehouse *did* build, because that is what decides the
    operator's next move.
    """
    from usvote.pv.overlap import PVOverlapError

    def boom(*_a: Any, **_k: Any) -> None:
        raise PVOverlapError("gate 1 (overall): 12.00% of 100 overlap cells")

    monkeypatch.setattr(top, "ucsb_html_dir_from_env", lambda *a, **k: "snap/")
    monkeypatch.setattr(top, "run_warehouse", boom)

    assert top.main(["all"]) == 1
    err = capsys.readouterr().err
    assert "Overlap validation failed" in err
    assert "--no-validate-overlap" in err
    assert "were built before this check ran" in err


class TestTheOverlapNote:
    """The completion line must distinguish all three gate outcomes."""

    def test_a_switched_off_gate_never_reads_as_clean(self) -> None:
        """The failure this line exists to prevent: silence meaning two things."""
        note = top._overlap_note(None)
        assert "SKIPPED" in note and "nothing checked" in note
        assert "passed" not in note

    def test_a_skipped_gate_reports_its_reason_and_not_a_pass(self) -> None:
        from usvote.pv.overlap import SKIP_UCSB_ABSENT, OverlapReport

        note = top._overlap_note(
            OverlapReport(skipped=True, skip_reason=SKIP_UCSB_ABSENT)
        )
        assert "not applicable" in note and "UCSB is not loaded" in note
        assert "passed" not in note

    def test_a_skip_that_excluded_years_names_them(self) -> None:
        """The one skip path that populates ``uncovered_years`` must print them.

        Its sibling above covers only the *empty* arm — ``SKIP_UCSB_ABSENT`` excludes
        nothing — so without this the whole ``(excluded: ...)`` clause could be deleted
        and the suite would stay green. Verified: reverting the clause reddens this test
        and nothing else. An operator told only "no comparable years" cannot tell which
        years stopped being compared, which is the one thing this skip needs to say.
        """
        from usvote.pv.overlap import SKIP_ALL_YEARS_AT_FRONTIER, OverlapReport

        note = top._overlap_note(
            OverlapReport(
                skipped=True,
                skip_reason=SKIP_ALL_YEARS_AT_FRONTIER,
                uncovered_years=(2024, 2028),
            )
        )
        assert "not applicable" in note and "no comparable years" in note
        assert "excluded: 2024, 2028" in note
        assert "passed" not in note

    def test_a_clean_run_names_the_flagged_keys_and_no_magnitudes(self) -> None:
        """AC-4: the D005 list is only "produced" if an operator can see it.

        Keys only — the same D030/D022 constraint that shapes ``OverlapKey`` governs
        anything printed from one.
        """
        from usvote.pv.overlap import OverlapKey, OverlapReport

        note = top._overlap_note(
            OverlapReport(
                cells=1326,
                exact=1239,
                exact_pct=93.44,
                flagged=(
                    OverlapKey(
                        year=1976, state="State0", candidate="Nominee", party="D"
                    ),
                ),
                one_sided=(),
                uncovered_years=(2028,),
            )
        )
        assert "93.44%" in note and "1326" in note
        assert "1 flagged" in note and "1976 State0 Nominee" in note
        assert "2028" in note and "excluded" in note
        assert "1239" not in note  # a count of exact cells is not per-cell data
