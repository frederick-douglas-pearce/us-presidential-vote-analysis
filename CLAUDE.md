# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Analyzes historical US Presidential Election data, **1824–present** (`UNSUPPORTED_EC_YEARS` is empty; the contested 1868 and 1872 elections are handled by D044–D046), to compare Electoral College vs. Popular Vote outcomes, plus a proposed hybrid (average of the two). The work is a multi-step data pipeline that scrapes, transforms, validates, and loads data into an `elections` PostgreSQL database. Step 1 originated as a Jupyter notebook and is being migrated into the installable `usvote` package (see [`src/usvote/` package](#srcusvote-package-in-progress-migration)); steps 2–3 remain planned.

- `step1_electoral_college_data.ipynb` — **implemented.** Scrapes Electoral College vote data from the [National Archives](https://www.archives.gov/electoral-college/results) and loads it into the `dwh` (data warehouse) schema.
- `step2_popular_vote_data.ipynb` — planned. Popular vote data from UC Santa Barbara, added to the same warehouse tables.
- `step3_voting_data_analysis.ipynb` — planned. Analysis and visualizations. Its computation core is already built in `usvote/hybrid.py`; its data-mart deliverable is **deferred under YAGNI** ([D070](.claude/specs/decisions.md)), because the dashboard reads the API.

**The public dashboard (E9, #275)** is the front end of D001's what-if explorer, **live at `https://explore.us-presidential-election-center.org`**: a Plotly Dash app on App Engine (D071) in its own GCP project, under `dashboard/`. It reads the live public `/v1` API, bundles no copy of the data, and imports nothing from `usvote` (D070). Detail: [`dashboard/CLAUDE.md`](dashboard/CLAUDE.md).

Alongside the pipeline sits a **publishing workstream**, the "Counted, Not Assumed" blog series, which shares no code with it; see [Publishing](#publishing-posts-social-tooling).

## Environment & Running

The original step-1 analysis is notebook-driven, but the `src/usvote/` package now
has quality gates (run via `uv`, enforced in CI):

```
uv run pytest                    # unit suite (live-Postgres integration excluded)
uv run pytest -m integration     # live-DB tests (needs USVOTE_TEST_DB_*)
uv run pytest --cov=usvote       # branch coverage report
uv run ruff check                # lint: E,F,I,UP,B,SIM,C4 @ line-length 88
uv run mypy                      # type check: src + tests
```

Test layout: unit tests are offline (no network/DB); the two live-Postgres tests
carry `@pytest.mark.integration` (the marker, not the directory, is what selects
them). `tests/unit/` and `tests/integration/` are the documented homes for new
tests; `tests/fixtures/` holds saved Archives HTML replayed offline.

**UCSB fixtures (D014/D016/D022).** Every `ucsb_synthetic_*.html` fixture is hand-written: UCSB grants no reuse rights and this repo is public, so no UCSB bytes are committed (`test_no_fixture_ships_real_ucsb_bytes`). The Archives fixtures are real saved bytes. The real UCSB corpus lives outside the tree; `TestRealCorpus` in `tests/unit/test_ucsb_parse.py` (and the roster checks in `test_ucsb_transform.py`) run against it only when `USVOTE_UCSB_HTML_DIR` is set, so CI never touches UCSB. They are the only checks of the parser against real markup, so run them locally with that variable set.

`tests/fixtures/ec_state_roster_by_year.json` is a committed snapshot of the **Electoral College** participation roster (public-domain Archives data), for testing UCSB roster logic offline. It is **test input only**: a test asserts nothing under `src/` reads it (D006), and it carries no electoral-vote counts (D024 §5).

```
uv sync                          # create the venv + install deps from pyproject.toml + uv.lock
python -m usvote corpus          # fetch the Archives HTML corpus to USVOTE_EC_HTML_DIR (#89)
python -m usvote                 # run the packaged EC pipeline (create-if-absent load)
python -m usvote --replace       # destructive: drop and recreate the dwh schema first
python -m usvote all             # build the whole warehouse (EC + MIT + optional UCSB/census + views)
python -m usvote.census snapshot # fetch the published Census tables to USVOTE_CENSUS_CORPUS_DIR (#181)
python -m usvote.census          # load both census tables + rebuild the per-capita view (bare = load)
python -m usvote.snapshot        # build the read-only API SQLite snapshot (E8; needs the warehouse incl. census)
python -m usvote.api             # serve the snapshot over HTTP (E8-S2; no live DB — reads the snapshot)
uv run jupyter lab               # or open the step-1 notebook interactively
```

The API ships as a slim container (D032/D033) on Cloud Run behind a Cloudflare Worker (D034/D035), **live at `https://api.us-presidential-election-center.org`**; see [`src/usvote/api/CLAUDE.md`](src/usvote/api/CLAUDE.md) and [`docs/deploy-cloud-run.md`](docs/deploy-cloud-run.md). The dashboard deploys separately: [`dashboard/CLAUDE.md`](dashboard/CLAUDE.md), [`docs/deploy-dashboard.md`](docs/deploy-dashboard.md).

Python >=3.11 (developed on 3.14); dependencies are pinned in `pyproject.toml` + `uv.lock`. Beside the base sit two dependency groups, `serve` (the API image's closure, D033) and `dashboard` (D071). `[tool.uv] default-groups` is `dev` + `dashboard`, so a bare `uv sync` installs the dashboard's dependencies and `uv run pytest` collects its tests.

Prerequisites, read from the environment (see the README "Configuration" section):
- **PostgreSQL** (>12.9) with a database named `elections` and create-schema/table permissions, via the libpq `PG*` env vars; `PGPASSWORD` is prompted via `getpass` when unset.
- **US States shapefile** (TIGER2019 from census.gov), via `USVOTE_SHAPEFILE_PATH`.
- **Network access** for scraping, unless a local Archives corpus is present (#89). With `USVOTE_EC_HTML_DIR` set, `python -m usvote [ec|all]` rebuilds from the corpus with zero network requests, after `assert_corpus_covers_years` confirms it holds every year; `--no-corpus` forces the live scrape. `python -m usvote corpus` fetches it, honoring archives.gov's `Crawl-delay: 10`; the live scrape path does **not** yet honor it.

Both `python -m usvote --replace` and running the notebook top-to-bottom scrape all election years, build the three DataFrames, and **drop and recreate** the `dwh` schema (`create_tables_from_dfs(..., replace=True)` cascades a schema drop). Be deliberate about executing the write path.

## Architecture

### Pipeline shape (step 1 notebook)

The notebook, and the package after it, follow a strict Scrape → Transform/Validate → Load structure:

1. **Section 2 — Scrape.** Walk the Archives index and each year's page. A page has two tables: **Table 1** (top-2 candidates + party) and **Table 2** (candidate home states + a votes-by-state matrix).
2. **Section 3 — Transform & validate.** Flatten into three DataFrames, each validated before the final join: `candidates_df` (Table 2 states + Table 1 parties, joined on name), `state_df` (state names joined to the shapefile) and `votes_df` (the melted matrix, joined to both).
3. **Section 4 — Load.** `DBC` writes all three into the `dwh` schema.

### `src/usvote/` package (in-progress migration)

The notebook is being migrated **incrementally** into an installable `usvote` package (D003). The E2 refactor is complete: `python -m usvote` wires scrape → parse → transform → load. The notebook is retained while D003's keep-or-migrate decision is open.

| Module | Notebook origin | Responsibility |
|--------|-----------------|----------------|
| `usvote/scrape.py` | §2 (network) | Fetch the Archives index + per-year HTML tables |
| `usvote/parse.py` | §2 (pure) | Parse raw HTML → `parsed_election_years` |
| `usvote/transform.py` | §3 | Build + validate the candidate/state/votes DataFrames; the correction constants |
| `usvote/load.py` | §4 | Orchestrate DataFrame → Postgres `dwh` load (`create_tables_from_dfs`) |
| `usvote/db.py` | `db_tools.py` | The `DBC` psycopg2 wrapper |
| `usvote/pipeline.py` | top-level | Wire scrape → parse → transform → load |

The notebook's display/viz helpers stay in the notebook; the public presentation layer is the E9 dashboard (D070).

**Source-namespacing convention.** The top-level `usvote/` modules are the **Electoral College / National Archives** pipeline — the source-of-truth spine (D006). The two popular-vote sources land as sibling subpackages, `usvote/ucsb/` (E4) and `usvote/mit/` (E5), each with its own scrape/parse/transform/load and a `pipeline.py` wiring the stages (`run_mit_pipeline`, `run_ucsb_pipeline`). EC stays flat by design; PV sources nest.

Because D006 makes EC authoritative, a PV source importing domain facts *from* the spine is expected (UCSB derives its year scope from `usvote/years.py`, and its state roster + candidate reconciliation from `usvote/spine.py`); what must never happen is the reverse.

### Module map — nested `CLAUDE.md` files

Module-specific detail lives beside the code it describes. Claude Code loads a nested `CLAUDE.md` only after a file in that subtree is read, and tests live in `tests/unit/` and `tests/integration/` rather than beside their source, so a test-only change does not load it. **Read the nested file before changing a module or its tests.**

| File | Covers | Tests |
|---|---|---|
| [`src/usvote/CLAUDE.md`](src/usvote/CLAUDE.md) | Entry points; `warehouse.py`; `years`, `count_status`, `apportionment`; `spine`, `join`; `hybrid`; `snapshot`; the `votes` fact | `test_entry_points`, `test_warehouse`, `test_apportionment`, `test_spine`, `test_join`, `test_hybrid`, `test_snapshot`, `test_layering` |
| [`src/usvote/pv/CLAUDE.md`](src/usvote/pv/CLAUDE.md) | Shared popular-vote contracts; `overlap.py` (D051/D052); `absences.py` | `test_pv_*` |
| [`src/usvote/census/CLAUDE.md`](src/usvote/census/CLAUDE.md) | The census source (D059–D067) and its two tables | `test_census_*` |
| [`src/usvote/api/CLAUDE.md`](src/usvote/api/CLAUDE.md) | Serving layer, `/v1` endpoints, container, Cloud Run + Cloudflare | `test_api_*` |
| [`dashboard/CLAUDE.md`](dashboard/CLAUDE.md) | The E9 dashboard, its deploy and guards | `test_dashboard_*` |
| [`tooling/CLAUDE.md`](tooling/CLAUDE.md) | The publishing workstream | `test_check_*`, `test_publish_to_pages`, `test_og_card_render` |

The UCSB and MIT subpackages have no nested file; their conventions are in this one.

### Cross-cutting invariants

Each of these can be broken from outside the module that owns it, so it is stated here. The detail is in the nested file.

- **Layering (D015/D027).** Dependencies run source → shared, never source → source. No top-level module except the composition roots `warehouse.py` and `__main__.py` imports `usvote.mit`, `usvote.ucsb` or `usvote.census` (`test_no_top_level_module_imports_a_source_subpackage`). Nothing under `usvote/{mit,ucsb,pv,census}/` imports `usvote.warehouse` or `usvote.hybrid` (`test_warehouse.py`, `test_layering.py`), and nothing under `usvote/{pv,census}/` names `dwh.votes` in code. That last guard is an AST scan that strips docstrings and comments, not a grep. `usvote/api/` never imports `usvote.db`, psycopg2, pandas or `usvote.snapshot` (`test_api_import_graph.py`, D028). `dashboard/` never imports `usvote` (`test_dashboard_guards.py`, D070(b)).
- **UCSB firewall (D022/D030).** No UCSB bytes are committed, and nothing UCSB-derived reaches the public path: the snapshot derives `pv_status` from the in-repo absence catalog (`usvote/pv/absences.py`), never from `dwh.pv_state_status`.
- **Append-only column contracts.** `EC_PV_COLUMNS`, `HYBRID_CANDIDATE_COLUMNS`, `HYBRID_SUMMARY_COLUMNS` and `ELECTION_POPULATION_COLUMNS` take new columns at the end only, because their views are rebuilt with `CREATE OR REPLACE VIEW`, which cannot insert or reorder. Each order is pinned by a hand-written literal. The snapshot's projections (`snapshot_schema.DATA_COLUMNS` and its own `HYBRID_SUMMARY_COLUMNS`) are independent explicit lists contained by those tuples, never derived from them (D047 §3).
- **Appointed ≥ cast ≥ counted.** `total_electoral_votes` is the appointed allotment, `president_electoral_votes` the votes cast, and `president_electoral_votes_counted` the votes Congress counted (see `votes` under Data model). EC shares divide counted votes by the appointed denominator, so they sum to ≤ 1.0 (D041/D046).

### Data model (`dwh` schema)

Loose star schema: two dimension tables + one fact table (`state`, `candidate`, `votes`), plus two census tables hung off `state`. Create tables in FK-dependency order (`state`, then `candidate`, then `votes`; the census tables need `state`).

- **`state`** — PK `state` (full name); USPS code, census region/division, geoid, land/water area, lat/lon.
- **`candidate`** — PK `candidate_id`; parsed name parts, up to two home states (FK → `state`), up to two parties. A candidate spanning multiple states/parties is aggregated to one row with `_2` columns (e.g., Bryan D/P, T. Roosevelt R→P).
- **`votes`** — PK `votes_id`; `year`, `state` (FK, null for totals rows), `is_total`, `candidate_id` (FK), `total_electoral_votes` (appointed), `president_electoral_votes` (cast), `president_electoral_votes_counted` (counted), `president_electoral_rank` and `took_office` (both from the counted measure), `count_status` + `count_status_reason` (D043/D044). Semantics: [`src/usvote/CLAUDE.md`](src/usvote/CLAUDE.md#the-votes-fact-dwhvotes).
- **`census_population`**, **`election_population`** — see [`src/usvote/census/CLAUDE.md`](src/usvote/census/CLAUDE.md).

### `db_tools.py` — `DBC` class

Thin psycopg2 wrapper (schema/table create/drop, `insert_df_into_table` via `execute_values`, `select_query_to_df`) that the notebooks depend on. Its constructor exits the process on connection failure.

### Publishing (`posts/`, `social/`, `tooling/`)

The **"Counted, Not Assumed"** blog series, live at <https://frederick-douglas-pearce.github.io/blog/>. [`posts/README.md`](posts/README.md) is the authoritative spec and [`tooling/CLAUDE.md`](tooling/CLAUDE.md) holds the rest. Two editorial guardrails are absolute: nothing critical of a data source is ever published, and every historical claim is checked before publishing. The `marketer` agent drafts public-facing copy; the parent agent writes anything that lands in the repo itself.

## Working conventions

- **Validation is inline and load-bearing.** The notebook and package are dense with assertion-style checks (grain checks, row-count equalities, `value_counts`). When editing transform logic, preserve or update them: they are how the pipeline catches scrape/parse regressions.
- **Hardcoded data corrections.** Real historical anomalies (the 2016 "Other" candidates, the 2000 DC abstainer, Table 1/Table 2 name mismatches, …) are patched by name: each is a provenance-carrying constant in `src/usvote/transform.py` with an `apply_*`/reconcile function, a test in `tests/unit/test_transform.py`, and a row in [`docs/corrections.md`](docs/corrections.md). Add a new anomaly the same way (constant + test + catalog row), documenting its source.
- **NaN → None** happens only at the DB write boundary (`usvote.db.insert_df_into_table` via `_df_to_sql_rows`), which also unboxes numpy scalars. Do **not** rely on an upstream `.map` NaN→None pass: it silently no-ops on `StringDtype` columns.
- **The repo's own license is split by path ([D065](.claude/specs/decisions.md)).** Everything under `posts/` and `docs/` is **CC-BY-4.0** ([`LICENSE-prose.md`](LICENSE-prose.md)), whatever its format; everything else is **MIT**, including `.claude/specs/` and this file. The `Scope` block at the end of `LICENSE` makes the split bind, so never add an unscoped MIT header or SPDX tag over prose. This is separate from what the repo may redistribute *from* its sources (D014/D022/D030). Quoted third-party material is excluded from both grants, so verbatim UCSB expression does not belong in a fenced block under `docs/`; write it schematically, as D065(c) did.
- Git workflow is PR-per-feature-branch merged to `main` (`feature/<topic>`, or `docs/<topic>` for docs-only).