-- Query script behind `research-pv-overlap.md` (E7-S1, issue #70).
--
-- Measures MIT-vs-UCSB popular-vote agreement across the 1976-2024 overlap.
-- Reads ONLY the two shipped D017 single-source views -- no re-extract:
--   dwh.pv_redistributable  = the redistributable series (MIT today)
--   dwh.pv_ucsb             = the UCSB single-source control
--
-- NOTE ON NAMING: the aliases below call pv_redistributable "mit". That is true
-- today because MIT is the only redistributable source. D017 makes a UCSB
-- redistribution grant a one-row `pv_source` edit -- after which this script would
-- silently compare UCSB against UCSB. Re-check the alias before reusing it then.
--
-- RELATIVE-DELTA BASIS: every `relpct` below is |MIT - UCSB| / UCSB * 100, i.e.
-- UCSB is the denominator. The measure is asymmetric; #167 must implement gate 2
-- against this definition.
--
-- This script is committed deliberately: it contains no UCSB values, only the
-- queries that derive aggregates from them. Running it requires the UCSB snapshot,
-- which is NOT redistributable and lives outside the repository (D022).
\set ON_ERROR_STOP on
\pset footer off

CREATE TEMP VIEW pair AS
SELECT coalesce(m.year,u.year) AS year, coalesce(m.state,u.state) AS state,
       coalesce(m.candidate,u.candidate) AS candidate, m.party,
       m.candidate_votes AS mit, u.candidate_votes AS ucsb,
       m.state_total_votes AS mit_tot, u.state_total_votes AS ucsb_tot
FROM dwh.pv_redistributable m
FULL OUTER JOIN dwh.pv_ucsb u ON m.year=u.year AND m.state=u.state AND m.candidate=u.candidate
WHERE coalesce(m.year,u.year) BETWEEN 1976 AND 2024;

-- KNOWN LIMITATION of the absolute floor below, for #167 to resolve rather than inherit:
-- `band_hi` is the band's UPPER edge, and the top band is open-ended, so its `band_hi`
-- of 1.0 makes the floor predicate `mit*band_hi < 500` degenerate to `mit < 500` there.
-- Inert on this corpus -- the smallest published >1% cell has MIT 77,798, giving an
-- implied interval ~778 votes, and nothing published sits under the floor -- but a
-- future small-magnitude >1% cell would be published with too narrow an interval.
-- Deliberately NOT redesigned here: changing the predicate changes the published
-- counts, which the review round that found it had no budget left to re-certify.
-- NULL HANDLING: `pair` is a FULL OUTER join, so a one-sided row would carry NULL
-- `mit` or `ucsb`; `relpct` is then NULL, the band CASE falls through to '>1%', and
-- every `WHERE mit<>ucsb` filter below silently drops it (NULL is not true). Inert on
-- this corpus -- query 1 reports mit_missing = ucsb_missing = 0 -- and query 1 is the
-- guard that would catch it, since it counts the NULLs directly rather than filtering.
-- Worth knowing now that this script is a committed, re-runnable artifact.
CREATE TEMP VIEW d AS
SELECT *, abs(mit-ucsb)::numeric/greatest(ucsb,1)*100 AS relpct,
  CASE WHEN abs(mit-ucsb)::numeric/greatest(ucsb,1)*100 < 0.1 THEN 0.001
       WHEN abs(mit-ucsb)::numeric/greatest(ucsb,1)*100 < 1.0 THEN 0.01 ELSE 1.0 END AS band_hi,
  CASE WHEN abs(mit-ucsb)::numeric/greatest(ucsb,1)*100 < 0.1 THEN '<0.1%'
       WHEN abs(mit-ucsb)::numeric/greatest(ucsb,1)*100 < 1.0 THEN '0.1-1%' ELSE '>1%' END AS band
FROM pair;

\echo '### 1. Population + measured zero-drop (AC-1, AC-2a)'
SELECT count(*) AS pairs, count(*) FILTER (WHERE mit IS NULL) AS mit_missing,
       count(*) FILTER (WHERE ucsb IS NULL) AS ucsb_missing,
       count(*) FILTER (WHERE mit=ucsb) AS exact_equal,
       count(*) FILTER (WHERE mit<>ucsb) AS divergent,
       round(100.0*count(*) FILTER (WHERE mit=ucsb)/count(*),2) AS exact_pct FROM d;

\echo ''
\echo '### 2. Relative-delta percentiles + bucketed tail (divergent cells only)'
SELECT count(*) AS n,
  round(percentile_cont(0.50) WITHIN GROUP (ORDER BY relpct)::numeric,4) AS p50,
  round(percentile_cont(0.90) WITHIN GROUP (ORDER BY relpct)::numeric,4) AS p90,
  round(percentile_cont(0.95) WITHIN GROUP (ORDER BY relpct)::numeric,4) AS p95,
  count(*) FILTER (WHERE relpct>1) AS over_1pct, count(*) FILTER (WHERE relpct>2) AS over_2pct,
  count(*) FILTER (WHERE relpct>5) AS over_5pct, count(*) FILTER (WHERE relpct>10) AS over_10pct
FROM d WHERE mit<>ucsb;

\echo ''
\echo '### 3. Per-year band table, WITH the 500-vote absolute floor (AC-3 listing shape)'
WITH f AS (SELECT *, (mit*band_hi < 500) AS withheld FROM d WHERE mit<>ucsb)
SELECT year,
  count(*) FILTER (WHERE band='<0.1%'  AND NOT withheld) AS lt_0_1,
  count(*) FILTER (WHERE band='0.1-1%' AND NOT withheld) AS b0_1_to_1,
  count(*) FILTER (WHERE band='>1%'    AND NOT withheld) AS gt_1,
  count(*) FILTER (WHERE withheld) AS withheld, count(*) AS total
FROM f GROUP BY year ORDER BY year;

\echo ''
\echo '### 3b. Per-year exact-match rate'
SELECT year, count(*) AS cells, round(100.0*count(*) FILTER (WHERE mit=ucsb)/count(*),2) AS exact_pct
FROM d GROUP BY year ORDER BY year;

\echo ''
\echo '### 4. The >1% cells -- keys + band only (the D005 reliability list, AC-3)'
SELECT year, state, candidate, party FROM d WHERE relpct >= 1.0 ORDER BY year, state;

\echo ''
\echo '### 5. Is divergence paired within a state-year? (AC-4, structure)'
WITH s AS (SELECT year, state, count(*) FILTER (WHERE mit<>ucsb) AS diverging FROM d GROUP BY year,state)
SELECT diverging AS candidates_diverging, count(*) AS state_years FROM s GROUP BY 1 ORDER BY 1;

\echo ''
\echo '### 6. 2x2: divergent cell present? x provided state totals differ? (AC-4)'
WITH s AS (SELECT year, state, bool_or(mit<>ucsb) AS has_div, (max(mit_tot)<>max(ucsb_tot)) AS tot_diff
           FROM d GROUP BY year,state)
SELECT has_div, tot_diff, count(*) FROM s GROUP BY 1,2 ORDER BY 1,2;

\echo ''
\echo '### 7. Denominator -- CROSS-SOURCE provided state_total_votes (AC-4, primary)'
WITH s AS (SELECT DISTINCT year, state, mit_tot, ucsb_tot FROM d)
SELECT count(*) AS state_years, count(*) FILTER (WHERE mit_tot=ucsb_tot) AS equal_totals,
  round(100.0*count(*) FILTER (WHERE mit_tot=ucsb_tot)/count(*),2) AS equal_pct,
  round(percentile_cont(0.95) WITHIN GROUP (ORDER BY abs(mit_tot-ucsb_tot)::numeric/greatest(ucsb_tot,1)*100)::numeric,4) AS p95_relpct,
  round(max(abs(mit_tot-ucsb_tot)::numeric/greatest(ucsb_tot,1)*100)::numeric,4) AS max_relpct FROM s;

\echo ''
\echo '### 8. Other/write-in -- PAIRED provided-vs-resum residual difference (AC-4)'
-- Paired per state-year, then aggregated: a difference of two independent means would
-- let opposite-signed per-state differences cancel, which is not what the claim needs.
WITH s AS (SELECT year, state, max(mit_tot) AS mt, max(ucsb_tot) AS ut,
                  sum(mit) AS ms, sum(ucsb) AS us FROM d GROUP BY year,state),
p AS (SELECT 100.0*(mt-ms)/greatest(mt,1) AS mr, 100.0*(ut-us)/greatest(ut,1) AS ur FROM s)
SELECT round(avg(mr)::numeric,3) AS mit_mean_residual_pct,
       round(avg(ur)::numeric,3) AS ucsb_mean_residual_pct,
       round(avg(abs(mr-ur))::numeric,4) AS mean_abs_paired_diff_pp,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY abs(mr-ur))::numeric,4) AS p95_paired_diff_pp,
       round(max(abs(mr-ur))::numeric,4) AS max_paired_diff_pp FROM p;

\echo ''
\echo '### 9. National roll-up per election, per candidate (AC-2b)'
-- Counts by band ONLY -- deliberately no per-year maximum. A per-year max relative
-- deviation at 4dp is a reconstruction vector: MIT nationals are CC0 and exactly
-- reproducible from this script, so UCSB_national = MIT_national / (1 +/- worst/100)
-- inverts it to within tens of votes, and national per-candidate UCSB totals are on
-- the finding's own withhold list. Caught in review; do not re-add the column.
WITH n AS (SELECT year, candidate, sum(mit) AS mn, sum(ucsb) AS un FROM d GROUP BY year, candidate),
b AS (SELECT year, abs(mn-un)::numeric/greatest(un,1)*100 AS rel FROM n)
SELECT year, count(*) AS candidates, count(*) FILTER (WHERE rel=0) AS exact,
  count(*) FILTER (WHERE rel>0 AND rel<0.05) AS lt_0_05pct,
  count(*) FILTER (WHERE rel>=0.05) AS ge_0_05pct
FROM b GROUP BY year ORDER BY year;

\echo ''
\echo '### 9b. Roll-up tail as threshold counts, over all 26 rows'
WITH n AS (SELECT year, candidate, sum(mit) AS mn, sum(ucsb) AS un FROM d GROUP BY year, candidate),
b AS (SELECT abs(mn-un)::numeric/greatest(un,1)*100 AS rel FROM n)
SELECT count(*) AS rows, count(*) FILTER (WHERE rel=0) AS exact,
  count(*) FILTER (WHERE rel>=0.05) AS ge_0_05, count(*) FILTER (WHERE rel>=0.10) AS ge_0_10,
  count(*) FILTER (WHERE rel>=0.15) AS ge_0_15 FROM b;

\echo ''
\echo '### 10. DECISIVE -- national PV winner agreement (AC-5b)'
WITH n AS (SELECT year, candidate, sum(mit) AS mn, sum(ucsb) AS un FROM d GROUP BY year, candidate),
w AS (SELECT year, (array_agg(candidate ORDER BY mn DESC))[1] AS mit_w,
                   (array_agg(candidate ORDER BY un DESC))[1] AS ucsb_w FROM n GROUP BY year)
SELECT count(*) AS years, count(*) FILTER (WHERE mit_w=ucsb_w) AS winner_agrees,
       count(*) FILTER (WHERE mit_w<>ucsb_w) AS winner_differs FROM w;

\echo ''
\echo '### 11. DECISIVE -- national margin on each source PROVIDED denominator (AC-5b)'
-- D017 pins the margin denominator to each source own provided state-total column,
-- NEVER a re-sum of candidate rows (D007 scopes candidates to EC-getters, so a
-- re-sum differs systematically between sources). This mirrors usvote/hybrid.py
-- roll_up_national: national_pv_denominator = sum over states of max(state_total_votes).
WITH n AS (SELECT year, candidate, sum(mit) AS mn, sum(ucsb) AS un FROM d GROUP BY year, candidate),
den AS (SELECT year, sum(mt) AS mden, sum(ut) AS uden FROM
        (SELECT year, state, max(mit_tot) AS mt, max(ucsb_tot) AS ut FROM d GROUP BY year,state) s
        GROUP BY year),
r AS (SELECT n.*, row_number() OVER (PARTITION BY year ORDER BY mn DESC) AS mrk,
                  row_number() OVER (PARTITION BY year ORDER BY un DESC) AS urk FROM n),
m AS (SELECT den.year,
   100.0*(max(CASE WHEN mrk=1 THEN mn END)-max(CASE WHEN mrk=2 THEN mn END))/den.mden AS mit_margin,
   100.0*(max(CASE WHEN urk=1 THEN un END)-max(CASE WHEN urk=2 THEN un END))/den.uden AS ucsb_margin
   FROM r JOIN den USING (year) GROUP BY den.year, den.mden, den.uden)
SELECT year, round(mit_margin::numeric,4) AS mit_margin_pp,
       round(ucsb_margin::numeric,4) AS ucsb_margin_pp,
       round(abs(mit_margin-ucsb_margin)::numeric,4) AS diff_pp   -- computed at full precision
FROM m ORDER BY year;
