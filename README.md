US Presidential Election Analysis: Electoral College, Popular Vote, or Both?
======
This project analyzes historical US Presidential Election data to better understand the relationship between the Electoral College Vote results and the Popular Vote results. Debate frequently flares up as to whether the Electoral College approach for determining the winner of US Presidential Elections should be changed so that the Popular Vote decides who wins instead. Reviewing the actual data of past Presidential Elections will show just how different these two approaches are for past elections. 

In the spirit of checks and balances &#151; a pillar of our democratic republic &#151; I propose a third option: how about using the average of the Electoral College Vote and Popular Vote? Exploring this balanced approach for determining the US President will be the focus of the final portion of the historical voting analysis.

The project is broken down into several steps, each contained within a jupyter notebook, with the first two steps focused on data collection and validation, while the third step performs the voting analysis:
  1. [X] **step1_electoral_college_data.ipynb**: This notebook scrapes electoral college vote data for each US Presidential Election from 1892 to the present from the National Archives website, and then writes the data to a data warehouse schema in a Postgres database.
  2. [ ] **step2_popular_vote_data.ipynb**: This notebook scrapes the popular vote data for each US Presidential Election from University of California, Santa Barbara, adding this data to the tables created in the data warehouse schema built in Step 1 above.
  3. [ ] **step3_voting_data_analysis.ipynb**: This notebook performs analysis, develops visualizations, and creates objects within a data mart schema to support dashboard development

The data model for the data warehouse loosely follows a star schema design &#151; appropriate for historical data of moderate size &#151; with dimension tables that organize data for the Presidential Candidates and for the US States, and a fact table that contains the Votes by State data for each Presidential Election.

The data collected, transformed, validated, and written to a postgres database for this project may be used to back an API, and to power dashboards that surface key findings from the voting analysis. More on that later...

## Usage
1. Fork this repo and then clone it to your local environment

```
$ git clone https://github.com/frederick-douglas-pearce/us-presidential-election-analysis
```

2. Install/Data Requirements
  * **Python3** (>3.6) with the following packages installed: jupyterlab, BeautifulSoup, requests, pandas, geopandas, and matplotlib. You can use pip to install them directly, but I'd recommend using a virtual environment.
  * I used pipenv, a virtual environment and package management tool for python, to install the packages listed above. This repo includes Pipfiles that list the required packages, version constraints, dependencies, etc. The Pipfiles can be used to generate a pipenv environment with `pipenv install` ([pipenv link](https://pipenv.pypa.io/en/latest/)).
  * **PostgreSQL** (>12.9) containing a database with permissions for creating a schema and tables from the notebook. Typical defaults should suffice: `host=localhost`, `port=5432`, `dbname=postgres`, `user=postgres`, and whatever `password` you choose. These connection parameters must be modified to whatever you choose in Section 4 of the notebook prior to running it. The password value is obfuscated using `getpass`.
  * **US States Shapefile** is required to obtain state data, such as name, region id, land area, lat/lon of state's center, etc. Download the required file from [here](https://www2.census.gov/geo/tiger/TIGER2019/STATE/), place it on your file system somewhere accessible, specify that location in the notebook in Section 1.3, and `geopandas` will take care of the rest.

3. Run jupyter lab to open a notebook

```
$ (pipenv run) jupyter lab
```
  * Once a JuypterLab session is running in your browser, find the notebook you want to work on using the File Browser in the left panel, then double click on the notebook to open it.
  * The notebooks generally require an internet connection for scraping data, plus you'll need to download the occasional file (e.g. shapefile for US States)


## License
* Copyright 2021 Frederick D. Pearce
* Licensed under the Apache License, Version 2.0 (the "License")
* You may obtain a copy of the License from
[LICENSE](https://github.com/frederick-douglas-pearce/us-presidential-election-analysis) or
[here](http://www.apache.org/licenses/LICENSE-2.0)
 