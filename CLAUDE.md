# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Analyzes historical US Presidential Election data (1892–present) to compare Electoral College vs. Popular Vote outcomes, plus a proposed hybrid (average of the two). The work is a multi-step data pipeline where each step is a Jupyter notebook that scrapes, transforms, validates, and loads data into an `elections` PostgreSQL database.

- `step1_electoral_college_data.ipynb` — **implemented.** Scrapes Electoral College vote data from the [National Archives](https://www.archives.gov/electoral-college/results) and loads it into the `dwh` (data warehouse) schema.
- `step2_popular_vote_data.ipynb` — planned. Popular vote data from UC Santa Barbara, added to the same warehouse tables.
- `step3_voting_data_analysis.ipynb` — planned. Analysis, visualizations, and a data mart schema for dashboards.

## Environment & Running

There is no test suite, linter, or build step — this is notebook-driven analysis.

```
pipenv install          # README references Pipfiles, but none are committed yet; install deps manually if absent
pipenv run jupyter lab  # open and run notebooks interactively
```

Python >3.6. Dependencies: `jupyterlab`, `beautifulsoup4`, `requests`, `pandas`, `geopandas`, `matplotlib`, `psycopg2`.

Prerequisites before running step 1:
- **PostgreSQL** (>12.9) with a database named `elections` and create-schema/table permissions. Connection params are hardcoded in the notebook's Section 4.1 (`host=localhost`, `port=5432`, `dbname=elections`, `user=postgres`); the password is prompted at runtime via `getpass`.
- **US States shapefile** (TIGER2019 from census.gov). The path is hardcoded in Section 1.3 (`usa_state_shp`) and **must be edited** to a local path before running. `geopandas` reads state geography (region, area, lat/lon) from it.
- Internet access for scraping.

Running the notebook top-to-bottom scrapes all election years, builds the three DataFrames, and (final cell) **drops and recreates** the `dwh` schema — `create_tables_from_dfs(..., replace=True)` cascades a schema drop. Be deliberate about executing the write cells.

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

The notebook is being migrated **incrementally** into an installable `usvote` package (D003). The module skeleton exists now (issue #17); each module is a docstring-only stub until the E2 refactor ports the notebook code into it. The layout mirrors the notebook's own section numbering:

| Module | Notebook origin | Responsibility | Ported in |
|--------|-----------------|----------------|-----------|
| `usvote/scrape.py` | §2 (network) | Fetch the Archives index + per-year HTML tables (`get_html_tables`, `scrape_election_links`, `scrape_raw_election_tables`) | E2-S1 (#23) |
| `usvote/parse.py` | §2 (pure) | Parse raw HTML → `parsed_election_years` (`parse_election_years` + the `parse_table1`/`parse_table2` families) | E2-S2 (#25) |
| `usvote/transform.py` | §3 | Build + validate the candidate/state/votes DataFrames | E2-S3 (#26) |
| `usvote/load.py` | §4 | Orchestrate DataFrame → Postgres `dwh` load (`create_tables_from_dfs`) | E2-S5 (#28) |
| `usvote/db.py` | `db_tools.py` | The `DBC` psycopg2 wrapper | E1-S3 (#21) |
| `usvote/pipeline.py` | top-level | Wire scrape → parse → transform → load | E2-S5 (#28) |

The notebook's display/viz helpers (`make_map_usa`, `pprint_list_of_dicts`, `print_election_year_results`) are **not** part of this spine and stay in the notebook (the presentation layer is deferred per D001). Config (DB params, shapefile path) is externalized in E2-S6 (#31), not carried into the skeleton.

**Source-namespacing convention.** The top-level `usvote/` modules are the **Electoral College / National Archives** pipeline — the source-of-truth spine (D006). The two popular-vote sources land as sibling subpackages, `usvote/ucsb/` (E4) and `usvote/mit/` (E5), each with its own scrape/parse/transform/load. EC stays flat by design; PV sources nest.

### Data model (`dwh` schema)

Loose star schema: two dimension tables + one fact table. Column definitions and FK relations live in the notebook's Section 4.1 `table_column_defs`. Tables must be created in FK-dependency order (`state`, then `candidate`, then `votes`).

- **`state`** — PK `state` (full name); USPS code, census region/division, geoid, land/water area, lat/lon.
- **`candidate`** — PK `candidate_id`; parsed name parts, up to two home states (FK → `state`), up to two parties. A candidate spanning multiple states/parties is aggregated to one row with `_2` columns (e.g., Bryan D/P, T. Roosevelt R→P).
- **`votes`** — PK `votes_id`; `year`, `state` (FK, null for totals rows), `is_total` flag, `candidate_id` (FK), `total_electoral_votes`, `president_electoral_votes`, `president_electoral_rank`.

### `db_tools.py` — `DBC` class

Thin psycopg2 wrapper (schema/table create/drop, `insert_df_into_table` via `execute_values`, `select_query_to_df`). Constructor exits the process on connection failure. This is the only importable module; the notebooks depend on it.

## Working conventions

- **Validation is inline and load-bearing.** The notebook is dense with assertion-style checks (`Q: ... A: {len(x) == len(y)}`, `value_counts`, grain checks like "one row per candidate"). When editing transform logic, preserve or update these — they are how the pipeline catches scrape/parse regressions.
- **Hardcoded data corrections.** Real historical anomalies are patched by name at specific cells: 2016 "Other" candidates (electoral votes and names collected manually from the Archives Notes section), 2000 DC abstainer, name mismatches between Table 1 and Table 2 (e.g. "Bob Dole"→"Robert Dole", Donald Trump's middle initial, "Faith Spotted Eagle" name split). Expect similar per-election special-casing when extending coverage; document the source of any manually-entered value in a comment as existing cells do.
- **NaN → None** before DB writes (`applymap` conversion) so Postgres receives proper nulls.
- Git workflow is PR-per-feature-branch merged to `main` (`feature/<topic>` naming).
