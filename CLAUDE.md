# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Analyzes historical US Presidential Election data (1824–present, excluding the contested 1868 and 1872 Reconstruction elections — see `UNSUPPORTED_EC_YEARS`) to compare Electoral College vs. Popular Vote outcomes, plus a proposed hybrid (average of the two). The work is a multi-step data pipeline that scrapes, transforms, validates, and loads data into an `elections` PostgreSQL database. Step 1 originated as a Jupyter notebook and is being migrated into the installable `usvote` package (see [`src/usvote/` package](#srcusvote-package-in-progress-migration)); steps 2–3 remain planned.

- `step1_electoral_college_data.ipynb` — **implemented.** Scrapes Electoral College vote data from the [National Archives](https://www.archives.gov/electoral-college/results) and loads it into the `dwh` (data warehouse) schema.
- `step2_popular_vote_data.ipynb` — planned. Popular vote data from UC Santa Barbara, added to the same warehouse tables.
- `step3_voting_data_analysis.ipynb` — planned. Analysis, visualizations, and a data mart schema for dashboards.

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
all 49 in-scope years.

One fixture runs the other way: `tests/fixtures/ec_state_roster_by_year.json` is a
committed snapshot of the **Electoral College** participation roster (public-domain
Archives data, so D022 does not apply), which lets the UCSB roster logic be tested offline
against real 1824/1864/1876 shapes. It is **test input only** — a test asserts nothing
under `src/` reads it, so it cannot become a second source of participation truth (D006) —
and it deliberately carries no electoral-vote counts (D024 §5).

```
uv sync                          # create the venv + install deps from pyproject.toml + uv.lock
python -m usvote                 # run the packaged EC pipeline (create-if-absent load)
python -m usvote --replace       # destructive: drop and recreate the dwh schema first
uv run jupyter lab               # or open the step-1 notebook interactively
```

Python >=3.11 (developed on 3.14). Dependencies are pinned in `pyproject.toml` + `uv.lock` (`beautifulsoup4`, `requests`, `pandas`, `geopandas`, `matplotlib`, `psycopg2`, plus the dev/notebook tools).

Prerequisites before running step 1 (both the package and the notebook read these from the environment — see the README "Configuration" section; externalized in #31):
- **PostgreSQL** (>12.9) with a database named `elections` and create-schema/table permissions. Connection params come from the standard libpq `PG*` env vars (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`); `PGPASSWORD` is prompted at runtime via `getpass` when unset.
- **US States shapefile** (TIGER2019 from census.gov), located via the `USVOTE_SHAPEFILE_PATH` env var. `geopandas` reads state geography (region, area, lat/lon) from it.
- Internet access for scraping.

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

The notebook's display/viz helpers (`make_map_usa`, `pprint_list_of_dicts`, `print_election_year_results`) are **not** part of this spine and stay in the notebook (the presentation layer is deferred per D001). Config (DB params, shapefile path) is externalized in E2-S6 (#31), not carried into the skeleton.

**Source-namespacing convention.** The top-level `usvote/` modules are the **Electoral College / National Archives** pipeline — the source-of-truth spine (D006). The two popular-vote sources land as sibling subpackages, `usvote/ucsb/` (E4) and `usvote/mit/` (E5), each with its own scrape/parse/transform/load and a `pipeline.py` wiring the stages (`run_mit_pipeline`, `run_ucsb_pipeline`). EC stays flat by design; PV sources nest.

`python -m usvote` runs the whole EC pipeline, but the PV subpackages do **not** mirror that: neither MIT nor UCSB exposes a pipeline `__main__` (their `run_*_pipeline` is driven directly, e.g. by the integration test — the user-facing entry point is deferred). UCSB additionally has a `__main__.py`, but it means **snapshot** (`python -m usvote.ucsb` fetches the raw HTML into `USVOTE_UCSB_HTML_DIR`, the D023 network refresh), *not* "run the pipeline". The asymmetry is principled — MIT reads a local CSV and so has no network stage to snapshot; only UCSB does. (Unifying the entry points into subcommands is a filed follow-up, #84.)

Two shared, **source-neutral** modules sit between them, and the dependency always runs `source -> shared`, never source-to-source: `usvote/pv/` holds the contracts both PV sources conform to — `schema.py` (the D018 record shape + `dwh.pv_votes` DDL), `status.py` (the D024 `pv_state_status` roster shape, the `pv_status` enum, and the two-way roster/fact assert), and `load.py` (the two write seams, `load_pv_records` for the fact and `load_pv_status` for the roster). `usvote/years.py` holds the election-year domain constants (`ec_ingest_years`, `UNSUPPORTED_EC_YEARS`) and is deliberately dependency-free, so a pure transform can derive its year scope from the EC spine without importing the orchestrator (and its DB/network stack). `usvote/pipeline.py` re-exports those names.

`usvote/spine.py` is a fourth kind of thing: **EC-spine readers** (`read_ec_participation`, `read_ec_getters`) that a PV source uses to pull EC facts back out of `dwh.votes`/`dwh.candidate` across a DI seam. It lives at the top level (not under `usvote/pv/`) because it embeds EC-star-schema knowledge — nothing under `usvote/pv/` names `dwh.votes`. Its precedent is `usvote/years.py`: an EC-domain module a PV stage reads *from*.

`usvote/join.py` is the **EC<->PV join seam** (E6-S2, #69 / D026) — another top-level EC-domain module in the `spine.py`/`years.py` family (it names `dwh.votes`/`dwh.candidate`, so the same greppable invariant keeps it out of `usvote/pv/`). It joins a **resolved** PV series onto the EC spine — `pv_preferred` (analysis/E7) or `pv_redistributable` (API/E8), never the raw `dwh.pv_votes` union (D017, else the 1976–2024 overlap fans out 2×) — as a **FULL OUTER participant view** at the canonical `(year, state, candidate)` grain, exposed as `ec_pv_preferred`/`ec_pv_redistributable`. Full-outer, not EC-left, because the EC `votes` fact is *sparse* (winners only), so an EC-left join would drop every loser's per-state row — exactly the "lost the EC, won the PV" rows the project's thesis needs (D026). A loser-in-state's electoral votes read **0** (a winner-take-all fact) only when the state ran an EC contest that year, else NULL; a getter with no PV keeps NULL PV (an honest D005 gap, never a fabricated value). This is also where the reciprocal candidate/state dim-coverage guard (`docs/canonical-keys.md`) runs, as a view-creation precondition.

Because D006 makes EC authoritative, a PV source importing domain facts *from* the spine is expected (UCSB derives its year scope from `usvote/years.py`, and its state roster + candidate reconciliation from `usvote/spine.py`); what must never happen is the reverse.

### Data model (`dwh` schema)

Loose star schema: two dimension tables + one fact table. Column definitions and FK relations live in the notebook's Section 4.1 `table_column_defs`. Tables must be created in FK-dependency order (`state`, then `candidate`, then `votes`).

- **`state`** — PK `state` (full name); USPS code, census region/division, geoid, land/water area, lat/lon.
- **`candidate`** — PK `candidate_id`; parsed name parts, up to two home states (FK → `state`), up to two parties. A candidate spanning multiple states/parties is aggregated to one row with `_2` columns (e.g., Bryan D/P, T. Roosevelt R→P).
- **`votes`** — PK `votes_id`; `year`, `state` (FK, null for totals rows), `is_total` flag, `candidate_id` (FK), `total_electoral_votes`, `president_electoral_votes`, `president_electoral_rank`, `took_office` (the candidate who assumed the presidency — the EC winner (`president_electoral_rank == 1`) except in contingent elections like 1824, where the House chose someone other than the EC leader; see `CONTINGENT_OFFICE_HOLDERS` and `docs/corrections.md`).

### `db_tools.py` — `DBC` class

Thin psycopg2 wrapper (schema/table create/drop, `insert_df_into_table` via `execute_values`, `select_query_to_df`). Constructor exits the process on connection failure. This is the only importable module; the notebooks depend on it.

## Working conventions

- **Validation is inline and load-bearing.** The notebook is dense with assertion-style checks (`Q: ... A: {len(x) == len(y)}`, `value_counts`, grain checks like "one row per candidate"). When editing transform logic, preserve or update these — they are how the pipeline catches scrape/parse regressions.
- **Hardcoded data corrections.** Real historical anomalies are patched by name: 2016 "Other" candidates (electoral votes and names collected manually from the Archives Notes section), 2000 DC abstainer, name mismatches between Table 1 and Table 2 (e.g. "Bob Dole"→"Robert Dole", Donald Trump's middle initial, "Faith Spotted Eagle" name split). In the `usvote` package each lives as a provenance-carrying constant in `src/usvote/transform.py` paired with an `apply_*`/reconcile function and a test in `tests/test_transform.py`; [`docs/corrections.md`](docs/corrections.md) is the browsable catalog. Expect similar per-election special-casing when extending coverage; add a new anomaly the same way (constant + test + catalog row), documenting its source as existing entries do.
- **NaN → None** is handled at the DB write boundary (`usvote.db.insert_df_into_table` via `_df_to_sql_rows`), which maps any null-like value to SQL `NULL` and unboxes numpy scalars. Transform frames may carry pandas NA (esp. `StringDtype`, whose NA is `NaN`); do **not** rely on an upstream `applymap`/`.map` NaN→None pass — it silently no-ops on `StringDtype` columns (the notebook's approach), which is why the conversion lives at the single write chokepoint.
- Git workflow is PR-per-feature-branch merged to `main` (`feature/<topic>` naming).
