US Presidential Election Analysis: Electoral College, Popular Vote, or Both?
======
This project aims to analyze historical US Presidential Election data to better understand the relationship between the Electoral College Vote results and the Popular Vote results.

The project is broken down into several steps, each contained within a jupyter notebook:
  1. **step1_electoral_college_data.ipynb**: This notebook scrapes electoral college vote data for each US Presidential Election from 1892 to the present, and then writes the data to a Postgres database where the data from different sources will be aggregated together.


## Usage
1. Fork this repo and then clone it to your local environment

```
$ git clone https://github.com/frederick-douglas-pearce/us-presidential-election-analysis
```

2. Install Requirements
  * **python3** (>3.6) with the following packages installed: jupyterlab, BeautifulSoup, requests, pandas, geopandas, and matplotlib. You can use pip to install them directly, but I'd recommend using a virtual environment.
  * I used pipenv, a virtual environment and package management tool for python, to install the packages listed above. This repo includes Pipfiles that list the required packages, version constraints, dependencies, etc. The Pipfiles can be used to generate a pipenv environment with `pipenv install` ([pipenv link](https://pipenv.pypa.io/en/latest/)).

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
 