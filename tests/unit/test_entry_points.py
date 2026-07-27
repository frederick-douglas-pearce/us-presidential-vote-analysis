"""Unit tests for the three CLI entry points (#84b).

Drives ``main(argv)`` for ``usvote.__main__``, ``usvote.mit.__main__`` and
``usvote.ucsb.__main__`` with the pipelines/orchestrator and config resolvers
monkeypatched, asserting subcommand dispatch, the bare-default paths (``usvote`` -> EC,
``usvote.ucsb`` -> snapshot, ``usvote.mit`` -> load), the ``--replace`` mapping, and the
loud/explicit UCSB gating for ``usvote all``. No DB, no network.
"""

from __future__ import annotations

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
        fetch: Any,
        environ: Any,
        close: bool,
    ) -> WarehouseResult:
        # No default on `fetch`, matching its siblings: if _run_all stopped forwarding
        # it, this double must fail rather than silently accept None.
        calls["warehouse"].append(
            {"ucsb_html_dir": ucsb_html_dir, "replace": replace, "fetch": fetch}
        )
        loaded = {SOURCE_EC, SOURCE_MIT} | (
            {SOURCE_UCSB} if ucsb_html_dir is not None else set()
        )
        return WarehouseResult(5, 3, None, None, frozenset(loaded), True)

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
        {"ucsb_html_dir": "snap/", "replace": True, "fetch": top.scrape.fetch_url}
    ]


def test_all_skips_ucsb_loudly_when_snapshot_absent(
    top_env: dict[str, list], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    def absent(*a: Any, **k: Any) -> str:
        raise ConfigError("USVOTE_UCSB_HTML_DIR unset")

    monkeypatch.setattr(top, "ucsb_html_dir_from_env", absent)
    assert top.main(["all"]) == 0
    assert top_env["warehouse"] == [
        {"ucsb_html_dir": None, "replace": False, "fetch": top.scrape.fetch_url}
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
        {"ucsb_html_dir": None, "replace": False, "fetch": top.scrape.fetch_url}
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


@pytest.fixture
def mit_env(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(mit_main.config, "db_config_from_env", lambda *a, **k: dict(_DB))
    monkeypatch.setattr(mit_main, "mit_csv_path_from_env", lambda *a, **k: "mit.csv")
    monkeypatch.setattr(mit_main, "DBC", lambda cfg: "DBC")
    monkeypatch.setattr(
        mit_main,
        "run_mit_pipeline",
        lambda dbc, path, *, replace=False, close=False: calls.append(
            {"path": path, "replace": replace}
        ),
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
    # The whole point of the feature: a corpus-backed fetch, NOT the live one.
    assert top_env["ec"][0]["fetch"] is not top.scrape.fetch_url


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
    assert top_env["warehouse"][0]["fetch"] is not top.scrape.fetch_url


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
