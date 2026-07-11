US Presidential Election Analysis: Electoral College, Popular Vote, or Both?
======
This project analyzes historical US Presidential Election data to better understand the relationship between the Electoral College Vote results and the Popular Vote results. Debate frequently flares up as to whether the Electoral College approach for determining the winner of US Presidential Elections should be changed so that the Popular Vote decides who wins instead. Reviewing the actual data of past Presidential Elections shows the differences between these two approaches for past elections. For example, how many times would a different outcome have occurred if the Popular Vote decided the presidential election outcome, and how would the margin of victory be different?

In the spirit of checks and balances &mdash; a pillar of our democratic republic &mdash; I propose a third option: what about using the average of the Electoral College Vote and Popular Vote? Exploring a more balanced approach for determining the US President is the focus of the final portion of this historical voting analysis.

The project is broken down into several steps, with the first two focused on data collection and validation, while the third focuses on analyzing the historical data under different approaches to determining the election outcome:
  1. [X] **Electoral College data** &mdash; scrapes electoral college vote data for each US Presidential Election from 1892 to the present from the [National Archives website](https://www.archives.gov/electoral-college/results), and writes the data to a data warehouse schema in an `elections` Postgres database. Originally the `step1_electoral_college_data.ipynb` notebook; now also runnable as the installable `usvote` package (see [Configuration](#configuration)).
  2. [ ] **Popular vote data** &mdash; scrapes the popular vote data for each US Presidential Election, adding it to the tables created in the data warehouse schema built in Step 1 above.
  3. [ ] **Voting data analysis** &mdash; performs the voting analysis, develops visualizations, and creates objects within a data mart schema to support dashboard development.

> **Migration in progress.** Step 1 is being ported incrementally from its notebook into an installable `usvote` Python package under `src/` (decision D003). The notebook is retained while the migration proceeds &mdash; the "keep the notebook vs. fully migrate off it" decision is still open. See [CLAUDE.md](CLAUDE.md) for the module-to-notebook-section map and the `uv`/pytest tooling.

The data model for the data warehouse loosely follows a star schema design &mdash; appropriate for historical data of moderate size &mdash; with dimension tables that organize data for the Presidential Candidates and for the US States, and a fact table that contains the Votes by State data for each Presidential Election.

The data collected, transformed, validated, and written to the `elections` Postgres database for this project may be used to back an API, and/or to power dashboards that surface key findings from the voting analysis. More on that later...

## Usage
1. Fork this repo and then clone it to your local environment

```
$ git clone https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis
```

2. Install/Data Requirements
  * **Python** (>=3.11; developed on 3.14) and [**uv**](https://docs.astral.sh/uv/) for dependency and environment management. From a fresh clone, `uv sync` reads `pyproject.toml` + `uv.lock` to create a virtual environment and install all dependencies (BeautifulSoup, requests, pandas, geopandas, matplotlib, psycopg2, and the dev/notebook tools):

```
$ uv sync
```
  * **PostgreSQL** (>12.9) containing a database with permissions for creating a schema and tables. Typical defaults suffice: `host=localhost`, `port=5432`, `dbname=elections`, `user=postgres`, and whatever `password` you choose. The `usvote` package reads these from the environment (the standard libpq `PG*` variables) &mdash; see [Configuration](#configuration) below; the password is prompted securely at runtime via `getpass` when unset. The step&nbsp;1 notebook reads the same values from the environment.
  * **US States Shapefile** is required to obtain state data, such as name, region id, land area, lat/lon of state's center, etc. Download the required file from [here](https://www2.census.gov/geo/tiger/TIGER2019/STATE/), place it on your file system somewhere accessible, and point the `USVOTE_SHAPEFILE_PATH` environment variable at the unzipped `.shp` (see [Configuration](#configuration)); `geopandas` will take care of the rest.

3. Run the Electoral College ingestion. With the environment configured (see [Configuration](#configuration)), the packaged pipeline is the primary path:

```
$ python -m usvote            # create-if-absent load
$ python -m usvote --replace  # destructive: drop and recreate the dwh schema first
```

  Alternatively, open the original notebook in JupyterLab to run or explore step 1 interactively:

```
$ uv run jupyter lab
```
  * Once a JupyterLab session is running in your browser, find the notebook you want to work with using the File Browser in the left panel, then double click on the notebook to open it.
  * Both paths require an internet connection for scraping data, plus the US States shapefile downloaded and pointed to via `USVOTE_SHAPEFILE_PATH`.


## Configuration

The `usvote` package reads all configuration from the environment &mdash; no source
edits are needed to run it on a fresh machine (issue #31). Copy the template and edit
the values:

```
$ cp .env.example .env          # .env is git-ignored; never commit real secrets
$ # ...edit .env...
$ set -a; source .env; set +a   # load into the shell (quote any path with spaces)
```

No dotenv library is required &mdash; the variables are read from the process
environment, so exporting them by hand or using `direnv` works equally well.

| Variable | Purpose | Default |
|---|---|---|
| `PGHOST` | Postgres host | `localhost` |
| `PGPORT` | Postgres port | `5432` |
| `PGDATABASE` | database name | `elections` |
| `PGUSER` | database user | `postgres` |
| `PGPASSWORD` | database password | *(unset &rarr; prompted securely at runtime)* |
| `USVOTE_SHAPEFILE_PATH` | path to the unzipped TIGER2019 STATE shapefile (`.shp`) | *(required)* |

Database settings use the standard libpq `PG*` names, so the same values are shared
with `psql`, `pg_dump`, and other Postgres tools. The TIGER2019 STATE shapefile is a
free download from the [Census Bureau](https://www2.census.gov/geo/tiger/TIGER2019/STATE/).

Once configured, run the Electoral College ingestion pipeline from the package (an
alternative to executing the step&nbsp;1 notebook cells):

```
$ python -m usvote            # create-if-absent load
$ python -m usvote --replace  # destructive: drop and recreate the dwh schema first
```

You are prompted for `PGPASSWORD` at runtime unless it is already set in the
environment.


## License
* Copyright 2021 Frederick D. Pearce
* Licensed under the Apache License, Version 2.0 (the "License")
* You may obtain a copy of the License from
[LICENSE](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/blob/main/LICENSE) or
[here](http://www.apache.org/licenses/LICENSE-2.0)
 
