"""Parse stage — turn raw Archives HTML into structured per-year records.

Maps to notebook Section 2 (the pure half). These functions are pure given HTML
input (no network), which makes them the natural first fixture-based unit-test
target. Output is ``parsed_election_years``: a list of per-year dicts with keys
``t1``, ``t2.candidate_state``, and ``t2.votes_by_state``.

Ported from ``step1_electoral_college_data.ipynb`` in E2-S2 (#25). Functions to
land here:

- ``parse_election_years`` — top-level walk over all election years.
- ``parse_election_year_tables`` — per-year dispatch to the Table 1 / Table 2
  parsers.
- ``parse_table1`` / ``parse_t1_candidate_party`` — Table 1: the top-2
  candidates and their parties.
- ``parse_table2`` / ``parse_t2_num_candidates`` / ``parse_t2_candidate_state``
  / ``parse_t2_votes_by_state`` — Table 2: candidate home states and the
  variable-width votes-by-state matrix.
"""
