# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Analyzes historical US Presidential Election data (**1824–present, complete** — `UNSUPPORTED_EC_YEARS` is now empty. The two contested Reconstruction elections were the last holdouts: 1868 landed in #143/D044 with Georgia's contested nine votes flagged `count_status='disputed'` rather than resolved by picking one of the page's two totals rows, and 1872 in #144/D045-D046, which synthesizes the 17 cast-then-rejected votes the Archives table omits entirely, restores Arkansas's and Louisiana's allotments to reach the 366 denominator Congress announced, and adds a second electoral-vote measure so the fact can state both what electors **cast** and what Congress **counted**) to compare Electoral College vs. Popular Vote outcomes, plus a proposed hybrid (average of the two). The work is a multi-step data pipeline that scrapes, transforms, validates, and loads data into an `elections` PostgreSQL database. Step 1 originated as a Jupyter notebook and is being migrated into the installable `usvote` package (see [`src/usvote/` package](#srcusvote-package-in-progress-migration)); steps 2–3 remain planned.

- `step1_electoral_college_data.ipynb` — **implemented.** Scrapes Electoral College vote data from the [National Archives](https://www.archives.gov/electoral-college/results) and loads it into the `dwh` (data warehouse) schema.
- `step2_popular_vote_data.ipynb` — planned. Popular vote data from UC Santa Barbara, added to the same warehouse tables.
- `step3_voting_data_analysis.ipynb` — planned. Analysis and visualizations. The three-method computation core that this step's analysis rests on is **already built** outside the notebook, in `usvote/hybrid.py` (see below). Its old third deliverable, a data mart schema for dashboards, is **deferred under YAGNI** ([D070](.claude/specs/decisions.md)): the public dashboard reads the API instead (below).

**The public dashboard (E9, #275)** is the front end of D001's what-if explorer, **live at `https://explore.us-presidential-election-center.org`**: a Plotly Dash app on App Engine (D071) in its own GCP project, under `dashboard/`. It reads the live public `/v1` API, bundles no copy of the data, and imports nothing from `usvote` (D070). Detail: [`dashboard/CLAUDE.md`](dashboard/CLAUDE.md).

Alongside the pipeline the repo carries a **publishing workstream** — the "Counted, Not Assumed" blog series in [`posts/`](posts/), its drafts in the git-ignored `social/`, and the scripts and CI gates that ship them. It shares no code with the pipeline; see [Publishing](#publishing-posts-social-tooling).

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

Two fixture caveats specific to UCSB (D014/D016/D022): the Archives fixtures are real
saved bytes, but **every `ucsb_synthetic_*.html` fixture is hand-written** — UCSB grants
no reuse rights and this repo is public, so no UCSB bytes are committed and
`test_no_fixture_ships_real_ucsb_bytes` guards that. The real 60-page snapshot is the
acceptance corpus for the UCSB parser and lives outside the tree; `TestRealCorpus` in
`tests/unit/test_ucsb_parse.py` runs against it and **skips when `USVOTE_UCSB_HTML_DIR`
is unset**, so CI stays green and never touches UCSB. Run it locally with that env var
set — it is the only check that exercises all six header layouts against real markup, and
(via `test_ucsb_transform.py`) the only one that runs the D024 two-way roster assert over
all 51 in-scope years.

One fixture runs the other way: `tests/fixtures/ec_state_roster_by_year.json` is a
committed snapshot of the **Electoral College** participation roster (public-domain
Archives data, so D022 does not apply), which lets the UCSB roster logic be tested offline
against real 1824/1864/1876 shapes. It is **test input only** — a test asserts nothing
under `src/` reads it, so it cannot become a second source of participation truth (D006) —
and it deliberately carries no electoral-vote counts (D024 §5).

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

The API also ships as a slim, cloud-agnostic container (D032/D033) with the snapshot baked in, deployed to Cloud Run behind a Cloudflare Worker (D034/D035) and **live at `https://api.us-presidential-election-center.org`**. Build, deploy and caching detail: [`src/usvote/api/CLAUDE.md`](src/usvote/api/CLAUDE.md) and the runbook [`docs/deploy-cloud-run.md`](docs/deploy-cloud-run.md). The dashboard deploys separately: [`dashboard/CLAUDE.md`](dashboard/CLAUDE.md) and [`docs/deploy-dashboard.md`](docs/deploy-dashboard.md).

Python >=3.11 (developed on 3.14). Dependencies are pinned in `pyproject.toml` + `uv.lock` (`beautifulsoup4`, `requests`, `pandas`, `geopandas`, `matplotlib`, `psycopg2`, plus the dev/notebook tools). Two dependency groups sit beside the base: `serve`, the API image's closure (D033), and `dashboard` (`dash[compress]` and `gunicorn`, D071). `[tool.uv] default-groups` is `dev` + `dashboard`, so a bare `uv sync` installs the dashboard's dependencies and `uv run pytest` collects its tests. `dev` carries `pyyaml` (+ `types-pyyaml`) because a dashboard guard parses `app.yaml`.

Prerequisites before running step 1 (both the package and the notebook read these from the environment — see the README "Configuration" section; externalized in #31):
- **PostgreSQL** (>12.9) with a database named `elections` and create-schema/table permissions. Connection params come from the standard libpq `PG*` env vars (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`); `PGPASSWORD` is prompted at runtime via `getpass` when unset.
- **US States shapefile** (TIGER2019 from census.gov), located via the `USVOTE_SHAPEFILE_PATH` env var. `geopandas` reads state geography (region, area, lat/lon) from it.
- Internet access for scraping — **unless a local Archives corpus is present** (#89). `python -m usvote corpus` fetches every in-scope year page plus the results index into `USVOTE_EC_HTML_DIR` (stored outside the repo, alongside `ucsb_raw/`, and mirroring that corpus's layout: `<year>.html` + `_index_results.html` + a `manifest.json` carrying per-page sha256/bytes/status/timestamp/url). When the variable is set, `python -m usvote [ec|all]` **auto-detects the corpus and rebuilds with zero network requests** — the path that feeds the API snapshot (D034), which otherwise re-scraped ~50 pages on every warehouse refresh. The corpus is verified complete before use (`assert_corpus_covers_years`): a stale corpus missing a year fails loud rather than silently building a warehouse short that year. `--no-corpus` forces the live scrape. The snapshot honors archives.gov's `Crawl-delay: 10` and sends a truthful User-Agent, so a first run takes ~8.5 min; the live scrape path does **not** yet do either (tracked separately).

Both `python -m usvote --replace` and running the notebook top-to-bottom scrape all election years, build the three DataFrames, and **drop and recreate** the `dwh` schema (`create_tables_from_dfs(..., replace=True)` cascades a schema drop). Be deliberate about executing the write path.

## Architecture

### Pipeline shape (step 1 notebook)

The notebook follows a strict Scrape → Transform/Validate → Load structure that mirrors its section numbering:

1. **Section 2 — Scrape.** `scrape_election_links` → `scrape_raw_election_tables` → `parse_election_years` walk the Archives site. Each election year page has two HTML tables: **Table 1** (top-2 candidates + party) and **Table 2** (candidate home states + a votes-by-state matrix). Parsing produces `parsed_election_years`, a list of per-year dicts with keys `t1`, `t2.candidate_state`, `t2.votes_by_state`.
2. **Section 3 — Transform & validate.** `pd.json_normalize` flattens the parsed structure into three DataFrames, each transformed and validated independently before a final join:
   - `candidates_df` (Candidate dimension) — built from Table 2 states + Table 1 parties, joined on candidate name.
   - `state_df` (State dimension) — US state names joined to the geopandas shapefile data.
   - `votes_df` (Votes fact) — the melted votes-by-state matrix, joined to both dimensions to attach `candidate_id` and `state`.
3. **Section 4 — Load.** `DBC` (from `db_tools.py`) writes all three DataFrames into the `dwh` schema.

### `src/usvote/` package (in-progress migration)

The notebook is being migrated **incrementally** into an installable `usvote` package (D003). The E2 refactor is complete: every module below is ported and runnable (the `python -m usvote` entry point wires scrape → parse → transform → load). The notebook is **retained** while the migration proceeds — the "keep the notebook vs. fully migrate off it" decision (D003) is still open. The layout mirrors the notebook's own section numbering:

| Module | Notebook origin | Responsibility | Ported in |
|--------|-----------------|----------------|-----------|
| `usvote/scrape.py` | §2 (network) | Fetch the Archives index + per-year HTML tables (`get_html_tables`, `scrape_election_links`, `scrape_raw_election_tables`) | E2-S1 (#23) |
| `usvote/parse.py` | §2 (pure) | Parse raw HTML → `parsed_election_years` (`parse_election_years` + the `parse_table1`/`parse_table2` families) | E2-S2 (#25) |
| `usvote/transform.py` | §3 | Build + validate the candidate/state/votes DataFrames | E2-S3 (#26) |
| `usvote/load.py` | §4 | Orchestrate DataFrame → Postgres `dwh` load (`create_tables_from_dfs`) | E2-S5 (#28) |
| `usvote/db.py` | `db_tools.py` | The `DBC` psycopg2 wrapper | E1-S3 (#21) |
| `usvote/pipeline.py` | top-level | Wire scrape → parse → transform → load | E2-S5 (#28) |

The notebook's display/viz helpers (`make_map_usa`, `pprint_list_of_dicts`, `print_election_year_results`) are **not** part of this spine and stay in the notebook (the public presentation layer is the E9 dashboard, which reads the API rather than this package — D070). Config (DB params, shapefile path) is externalized in E2-S6 (#31), not carried into the skeleton.

**Source-namespacing convention.** The top-level `usvote/` modules are the **Electoral College / National Archives** pipeline — the source-of-truth spine (D006). The two popular-vote sources land as sibling subpackages, `usvote/ucsb/` (E4) and `usvote/mit/` (E5), each with its own scrape/parse/transform/load and a `pipeline.py` wiring the stages (`run_mit_pipeline`, `run_ucsb_pipeline`). EC stays flat by design; PV sources nest.

Because D006 makes EC authoritative, a PV source importing domain facts *from* the spine is expected (UCSB derives its year scope from `usvote/years.py`, and its state roster + candidate reconciliation from `usvote/spine.py`); what must never happen is the reverse.

### Module map — nested `CLAUDE.md` files

Module-specific detail lives beside the code it describes. Claude Code loads a nested `CLAUDE.md` only after a file in that subtree is read, and tests live in `tests/unit/` and `tests/integration/` rather than beside their source, so a test-only change does not load it. **Read the nested file before changing a module or its tests.**

| File | Covers | Tests |
|---|---|---|
| [`src/usvote/CLAUDE.md`](src/usvote/CLAUDE.md) | Entry points and subcommands; `warehouse.py` (the composition root and view rebuild order); the dependency-free `years.py`, `count_status.py`, `apportionment.py`; `spine.py`; `join.py`; `hybrid.py`; `snapshot.py` | `test_entry_points.py`, `test_warehouse.py`, `test_apportionment.py`, `test_spine.py`, `test_join.py`, `test_hybrid.py`, `test_snapshot.py`, `test_layering.py` |
| [`src/usvote/pv/CLAUDE.md`](src/usvote/pv/CLAUDE.md) | The shared popular-vote contracts; `overlap.py` (D017 layer-3 gates, D051/D052); `absences.py` (the curated absence catalog) | `test_pv_*.py` |
| [`src/usvote/census/CLAUDE.md`](src/usvote/census/CLAUDE.md) | The census source (#181–#184, D059–D067): boundary corrections, the conform guards, seat reconciliation, the per-capita denominator; the `census_population` and `election_population` tables | `test_census_*.py` |
| [`src/usvote/api/CLAUDE.md`](src/usvote/api/CLAUDE.md) | The serving layer and `/v1` endpoints; the slim container (D033); the Cloud Run + Cloudflare deployment (D034/D035) | `test_api_*.py` |
| [`dashboard/CLAUDE.md`](dashboard/CLAUDE.md) | The E9 dashboard: platform, deploy, its tests and structural guards | `test_dashboard_*.py` |
| [`tooling/CLAUDE.md`](tooling/CLAUDE.md) | The publishing workstream (`posts/`, `social/`, `tooling/`) | `test_check_*.py`, `test_publish_to_pages.py`, `test_og_card_render.py` |

The UCSB and MIT subpackages have no nested file; their conventions are in this one.

### Cross-cutting invariants

Each of these can be broken from outside the module that owns it, so it is stated here. The detail is in the nested file.

- **Layering (D015/D027).** Dependencies run source → shared, never source → source. No top-level module except the composition roots `warehouse.py` and `__main__.py` imports `usvote.mit`, `usvote.ucsb` or `usvote.census` (`test_no_top_level_module_imports_a_source_subpackage`). Nothing under `usvote/{mit,ucsb,pv,census}/` imports `usvote.warehouse` or `usvote.hybrid` (`test_warehouse.py`, `test_layering.py`), and nothing under `usvote/{pv,census}/` names `dwh.votes` in code. That last guard is an AST scan that strips docstrings and comments, not a grep. `usvote/api/` never imports `usvote.db`, psycopg2, pandas or `usvote.snapshot` (`test_api_import_graph.py`, D028). `dashboard/` never imports `usvote` (`test_dashboard_guards.py`, D070(b)).
- **UCSB firewall (D022/D030).** No UCSB bytes are committed, and nothing UCSB-derived reaches the public path: the snapshot derives `pv_status` from the in-repo absence catalog (`usvote/pv/absences.py`), never from `dwh.pv_state_status`.
- **Append-only column contracts.** `EC_PV_COLUMNS`, `HYBRID_CANDIDATE_COLUMNS`, `HYBRID_SUMMARY_COLUMNS` and `ELECTION_POPULATION_COLUMNS` take new columns at the end only, because their views are rebuilt with `CREATE OR REPLACE VIEW`, which cannot insert or reorder. Each order is pinned by a hand-written literal. The snapshot's projections (`snapshot_schema.DATA_COLUMNS` and its own `HYBRID_SUMMARY_COLUMNS`) are independent explicit lists contained by those tuples, never derived from them (D047 §3).
- **Appointed ≥ cast ≥ counted.** `total_electoral_votes` is the appointed allotment, `president_electoral_votes` the votes cast, and `president_electoral_votes_counted` the votes Congress counted (see `votes` under Data model). EC shares divide counted votes by the appointed denominator, so they sum to ≤ 1.0 (D041/D046).

### Data model (`dwh` schema)

Loose star schema. The EC core is two dimension tables + one fact table (`state`, `candidate`, `votes`), and the census source (#181/#184) hangs two more tables off the `state` dimension without touching that core. Column definitions and FK relations for the EC core live in the notebook's Section 4.1 `table_column_defs`. Tables must be created in FK-dependency order (`state`, then `candidate`, then `votes`; both census tables need `state` first).

- **`state`** — PK `state` (full name); USPS code, census region/division, geoid, land/water area, lat/lon.
- **`candidate`** — PK `candidate_id`; parsed name parts, up to two home states (FK → `state`), up to two parties. A candidate spanning multiple states/parties is aggregated to one row with `_2` columns (e.g., Bryan D/P, T. Roosevelt R→P).
- **`census_population`**, **`election_population`** — the census source's two tables (#181/#184), hung off `state`. Their columns and the per-capita view are described in [`src/usvote/census/CLAUDE.md`](src/usvote/census/CLAUDE.md).
- **`votes`** — PK `votes_id`; `year`, `state` (FK, null for totals rows), `is_total` flag, `candidate_id` (FK), `total_electoral_votes`, `president_electoral_votes`, `president_electoral_rank`, `took_office` (the candidate who assumed the presidency — the EC winner (`president_electoral_rank == 1`) except in contingent elections like 1824, where the House chose someone other than the EC leader; see `CONTINGENT_OFFICE_HOLDERS` and `docs/corrections.md`), `count_status` + `count_status_reason` (D043 §3 / D044 — were these cast votes actually **counted**? `counted` / `not_counted` / `disputed`, with the source's own sentence as the reason. The enum has one definition, in the stdlib-only `usvote/count_status.py`, which `transform.py` assigns from and `load.py` builds the `CHECK` from. Deliberately disjoint from `ELECTORAL_VOTE_SHORTFALLS`, which records votes **never cast**; aggregate `is_total` rows are never flagged), and `president_electoral_votes_counted` (#144 / D046 — the **counted** twin of `president_electoral_votes`, which means **cast**. Three measures form a ladder, **appointed ≥ cast ≥ counted**: `total_electoral_votes` is the appointed allotment, `ELECTORAL_VOTE_SHORTFALLS` opens the first gap and `count_status` the second. The counted rule is strict — `disputed` is excluded alongside `not_counted` — which is what makes *both* of the Archives' printed 1868 totals rows reproducible, 294 as cast and 285 as counted, where D044 could only pick one. It is derived by **two rules**: state rows take the row rule, while an `is_total` row takes the sum over its year's state rows, since aggregates are never flagged and the row rule would hand back the cast value. `president_electoral_rank` and `took_office` are computed from the counted measure, because who won is settled by the votes Congress counted. Both measures, the status and its reason reach the **public API** as of #139/D048 — `count_status` and `count_status_reason` were appended to `EC_PV_COLUMNS` there, joining the pair D047 had already added).

### `db_tools.py` — `DBC` class

Thin psycopg2 wrapper (schema/table create/drop, `insert_df_into_table` via `execute_values`, `select_query_to_df`). Constructor exits the process on connection failure. This is the only importable module; the notebooks depend on it.

### Publishing (`posts/`, `social/`, `tooling/`)

A second, non-pipeline workstream: the **"Counted, Not Assumed"** blog series, live at <https://frederick-douglas-pearce.github.io/blog/>. [`posts/README.md`](posts/README.md) is the authoritative spec; [`tooling/CLAUDE.md`](tooling/CLAUDE.md) holds the rest (the git-ignored `social/` working state, verified research in `.claude/specs/`, the publishing scripts, the CI gates and the required humanizer pass). Two editorial guardrails are absolute: nothing critical of a data source is ever published, and every historical claim is checked before publishing. The `marketer` agent drafts public-facing copy; the parent agent writes anything that lands in the repo itself.

## Working conventions

- **Validation is inline and load-bearing.** The notebook is dense with assertion-style checks (`Q: ... A: {len(x) == len(y)}`, `value_counts`, grain checks like "one row per candidate"). When editing transform logic, preserve or update these — they are how the pipeline catches scrape/parse regressions.
- **Hardcoded data corrections.** Real historical anomalies are patched by name: 2016 "Other" candidates (electoral votes and names collected manually from the Archives Notes section), 2000 DC abstainer, name mismatches between Table 1 and Table 2 (e.g. "Bob Dole"→"Robert Dole", Donald Trump's middle initial, "Faith Spotted Eagle" name split). In the `usvote` package each lives as a provenance-carrying constant in `src/usvote/transform.py` paired with an `apply_*`/reconcile function and a test in `tests/test_transform.py`; [`docs/corrections.md`](docs/corrections.md) is the browsable catalog. Expect similar per-election special-casing when extending coverage; add a new anomaly the same way (constant + test + catalog row), documenting its source as existing entries do.
- **NaN → None** is handled at the DB write boundary (`usvote.db.insert_df_into_table` via `_df_to_sql_rows`), which maps any null-like value to SQL `NULL` and unboxes numpy scalars. Transform frames may carry pandas NA (esp. `StringDtype`, whose NA is `NaN`); do **not** rely on an upstream `applymap`/`.map` NaN→None pass — it silently no-ops on `StringDtype` columns (the notebook's approach), which is why the conversion lives at the single write chokepoint.
- **The repo's own license is dual, split by path ([D065](.claude/specs/decisions.md)).** This rule covers what the repo's code and prose ship *under*. It is a separate subject from what the repo may redistribute *from* its sources (D014/D022/D030, MIT Election Lab's CC0). Everything committed under `posts/` and `docs/` is **CC-BY-4.0** ([`LICENSE-prose.md`](LICENSE-prose.md)), **whatever its format**, so a `.csv` or `.json` added there is CC-BY too. Everything else is **MIT**, including `.claude/specs/`, `social/images/` and this file. The `Scope` block at the end of `LICENSE` is what makes the split bind, so never add an unscoped MIT header or SPDX tag over prose. Third-party material quoted in the repo is excluded from both grants, so verbatim source expression (above all UCSB, which grants no reuse) does not belong in a fenced block under `docs/`. Write it schematically, as D065(c) did for `docs/ucsb-html-formats.md`.
- Git workflow is PR-per-feature-branch merged to `main` (`feature/<topic>` naming).
