"""Top-level orchestration — scrape -> parse -> transform -> load.

Wires the four stage modules into a single end-to-end Electoral College
ingestion entry point, so the pipeline runs from the package instead of by
executing notebook cells top-to-bottom.

Assembled in E2-S5 (#28), once the stage modules are populated. Configuration
(DB connection params, the TIGER shapefile path) is externalized in E2-S6 (#31);
until then those values remain hardcoded as in the notebook.
"""
