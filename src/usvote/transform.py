"""Transform & validate stage — build the three warehouse DataFrames.

Maps to notebook Section 3. Flattens ``parsed_election_years`` into three
DataFrames, each transformed and validated independently before a final join:

- ``candidates_df`` (candidate dimension) — Table 2 states + Table 1 parties,
  joined on candidate name; multi-state/multi-party candidates are aggregated to
  one row with ``_2`` columns (e.g. Bryan D/P, T. Roosevelt R->P).
- ``state_df`` (state dimension) — US state names joined to the geopandas
  shapefile data (region, division, area, lat/lon).
- ``votes_df`` (votes fact) — the melted votes-by-state matrix joined to both
  dimensions.

The notebook's dense inline assertions (grain checks, ``value_counts`` sanity
checks) become explicit, tested validation functions here — they are
load-bearing, so a scrape/parse regression must surface loudly. NaN -> None
conversion at the DB-write boundary is preserved. Name-part parsing
(``get_name_middle_last``: first/middle/last/suffix, ``Jr.`` handling) also lands
here. The hardcoded historical corrections (2016 "Other" candidates, 2000 DC
abstainer, Table 1<->Table 2 name reconciliations, "Faith Spotted Eagle" split)
are catalogued and tested per E2-S4 (#27).

Ported from ``step1_electoral_college_data.ipynb`` in E2-S3 (#26).
"""
