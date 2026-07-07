"""Scrape stage — walk the National Archives site and fetch raw HTML.

Maps to notebook Section 2 (the network-facing half). This module is the *only*
place live network access belongs: it fetches the Archives results index and the
two HTML tables published per election year, so every downstream stage (parse,
transform, load) can run offline against saved HTML.

Ported from ``step1_electoral_college_data.ipynb`` in E2-S1 (#23). Functions to
land here:

- ``get_html_tables`` — fetch a page and return its ``<table>`` element(s).
- ``scrape_election_links`` — from the results index, return the per-year
  Archives page links.
- ``scrape_raw_election_tables`` — fetch the raw HTML tables for each election
  year (Table 1: top-2 candidates + party; Table 2: home states + votes-by-state
  matrix).

E2-S1 also adds a save-to-disk / snapshot seam so parser tests read fixture HTML
instead of hitting the network.
"""
