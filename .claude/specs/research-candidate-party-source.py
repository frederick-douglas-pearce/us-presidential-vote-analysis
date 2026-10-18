"""#384 — candidate-party population, the derived half of the #384 research doc.

The doc is `research-candidate-party-source.md`, beside this script.

Runs fully **offline** against the Archives corpus and the TIGER shapefile, with no
network and no database credentials:

    USVOTE_EC_HTML_DIR/<year>.html        (the Archives corpus, #89)
    USVOTE_SHAPEFILE_PATH                 (TIGER2019 states, as the EC pipeline uses)
    USVOTE_API_SNAPSHOT_PATH              (the served snapshot, opened read-only)

    uv run python .claude/specs/research-candidate-party-source.py

The snapshot is required: checks 5 and 8 read it. `--allow-no-snapshot` skips them, and
the run then says so in its last line.

It builds the warehouse's EC frames with the warehouse's **own** composition,
`transform.transform_parsed_years` (the call `pipeline.run_ec_pipeline` makes), so the
candidate-years it lists are the ones that composition loads into `dwh.votes` and
`dwh.candidate`. The script never reads `dwh` itself; check 5 compares its set with the
served snapshot's. SQL over
`dwh` cannot produce the list: `dwh.candidate.party`/`party_2` is aggregated per
candidate across years (`transform._candidate_parties`), so it cannot say whether
Table 1 covered a given *year*.

**Every headline is asserted, and the script exits non-zero on failure**, as
`research-boundary-sweep.py` does: a degraded input must raise, not print a plausible
table. Outputs, as Markdown the research doc embeds:

(a) every (year, printed token) Table 1 carries, with the candidate it labels, read from
    the **raw** parse, before `PARTY_CODE_FIXES`, because that token is what #385 keys
    its map on;
(b) the candidate-years with electoral votes **cast** (`president_electoral_votes > 0`)
    that Table 1 does not cover, by era: the population #387/#388 curate;
(c) the candidate-years whose cast and counted national totals differ.

It also prints the MIT `party` values on the 1976+ Table 1 rows and population rows,
which check 8 asserts. Progress output from the scrape and parse goes to stderr, so
stdout is only the Markdown.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sqlite3
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from usvote import parse, scrape, transform
from usvote.pv.source import MIT_PV_YEAR_MIN
from usvote.slug import candidate_slug
from usvote.years import ec_ingest_years

_DATA = Path.home() / "Documents/Projects/data"
EC_DIR = os.environ.get(
    "USVOTE_EC_HTML_DIR", str(_DATA / "presidential_vote_analysis/ec_raw")
)
SHAPEFILE = os.environ.get(
    "USVOTE_SHAPEFILE_PATH",
    str(_DATA / "Maps/State_Shapes/tl_2019_us_state/tl_2019_us_state.shp"),
)
SNAPSHOT = Path(
    os.environ.get(
        "USVOTE_API_SNAPSHOT_PATH",
        str(_DATA / "presidential_vote_analysis/snapshot.sqlite"),
    )
)

#: MIT's coverage starts here, so the population is reported in two eras.
MIT_FLOOR = MIT_PV_YEAR_MIN
EARLY_ERA = f"pre-{MIT_FLOOR}"
MIT_ERA = f"{MIT_FLOOR}+"

#: The doc's two-entry crosswalk (§9): the Table 1 token, its code, and MIT's value.
MIT_CROSSWALK = {"D": "DEMOCRAT", "R": "REPUBLICAN"}


class CheckFailed(AssertionError):
    """A headline did not hold; the message names it."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def load_parsed_years() -> tuple[list[parse.ParsedYear], pd.DataFrame]:
    """The corpus parsed exactly as `pipeline.run_ec_pipeline` parses it."""
    years = ec_ingest_years()
    scrape.assert_corpus_covers_years(EC_DIR, years)
    fetch = scrape.fetch_from_corpus(EC_DIR)
    links = scrape.scrape_election_links(fetch=fetch)
    raw = scrape.scrape_raw_election_tables(links, years, fetch=fetch)
    state_geo = transform.load_state_geo(SHAPEFILE)
    parsed = parse.parse_election_years(raw, set(state_geo["NAME"]))
    return parsed, state_geo


def table1_name(raw: str) -> str:
    """A Table 1 name as the candidate dimension spells it.

    The transform's own two steps, imported rather than re-implemented: the footnote
    strip `normalize_candidate_parties` applies, then `PARTY_NAME_FIXES`, which
    `_candidate_parties` applies before `build_candidate_dim` checks every Table 1
    name against the Table 2 names.
    """
    stripped = transform.strip_name_footnote_markers(raw)
    return str(transform.PARTY_NAME_FIXES.get(stripped, stripped))


def national_totals(votes: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    """One row per (year, candidate) from the fact's national totals rows."""
    totals = votes.loc[votes["is_total"]]
    named = totals.merge(
        candidates[["candidate_id", "name"]], on="candidate_id", how="left"
    )
    check(named["name"].notna().all(), "a totals row joins to no candidate")
    measures = ["president_electoral_votes", "president_electoral_votes_counted"]
    out = named[["year", "name", *measures]].rename(
        columns={
            "president_electoral_votes": "cast",
            "president_electoral_votes_counted": "counted",
        }
    )
    check(
        not out.duplicated(["year", "name"]).any(),
        "more than one national totals row for a (year, candidate)",
    )
    return out.reset_index(drop=True)


def table1_rows(parsed: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """Every Table 1 row: year, row, printed name, resolved name, printed token."""
    rows = [
        {
            "year": py["year"],
            "row": ri,
            "printed_name": rec["president_candidate_name"],
            "name": table1_name(rec["president_candidate_name"]),
            "token": rec["president_candidate_party"],
        }
        for py in parsed
        for ri, rec in enumerate(py["t1"])
    ]
    return pd.DataFrame(rows)


def read_snapshot() -> tuple[pd.DataFrame, str] | None:
    """Every served `national_rollup` row, unfiltered, and the snapshot version.

    Opened through a `mode=ro` URI so the read cannot write. Returns None when the
    file is absent, and the caller decides whether that fails the run.
    """
    if not SNAPSHOT.exists():
        return None
    con = sqlite3.connect(SNAPSHOT.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        version, schema = con.execute(
            "SELECT snapshot_version, schema_version FROM snapshot_meta"
        ).fetchone()
        served = pd.read_sql_query(
            "SELECT year, candidate, candidate_slug, party, national_electoral_votes "
            "FROM national_rollup",
            con,
        )
    finally:
        con.close()
    return served, f"{version} (schema {schema})"


def merge_all(left: pd.DataFrame, right: pd.DataFrame, what: str) -> pd.DataFrame:
    """A left merge on (year, slug) in which every left row must find a served row.

    Without this, a failed join and a genuine null MIT party print the same empty cell.
    """
    out = left.merge(right, on=["year", "candidate_slug"], how="left", indicator=True)
    missed = out.loc[out["_merge"] != "both"]
    check(
        missed.empty,
        f"{what}: rows with no served row: "
        + ", ".join(f"{r.year} {r.candidate_slug}" for r in missed.itertuples()),
    )
    return out.drop(columns="_merge")


def run_id() -> str:
    """The commit the run is on, marked `-dirty` when the tree has changes."""
    done = subprocess.run(
        ["git", "describe", "--always", "--dirty"],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parent,
    )
    return done.stdout.strip() if done.returncode == 0 else "unknown (git failed)"


def markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for rec in df.itertuples(index=False):
        cells = ("" if pd.isna(v) else str(v) for v in rec)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--allow-no-snapshot",
        action="store_true",
        help="skip checks 5 and 8 when the snapshot is absent",
    )
    args = parser.parse_args(argv)

    with contextlib.redirect_stdout(sys.stderr):
        parsed, state_geo = load_parsed_years()
        candidates, _state, votes = transform.transform_parsed_years(parsed, state_geo)
    totals = national_totals(votes, candidates)
    t1 = table1_rows(parsed)
    years = ec_ingest_years()

    # 1. The years covered are exactly the EC ingest years. A skipped year would
    # otherwise pass: `scrape_raw_election_tables` can drop one, and this script does
    # not call `pipeline._assert_years_scraped`.
    check(set(t1["year"]) == years, "Table 1 years differ from ec_ingest_years()")
    check(set(totals["year"]) == years, "fact years differ from ec_ingest_years()")

    # 2. Each Table 1 row resolves to a candidate with cast votes that year. That it
    # is only one follows from national_totals' no-duplicate check.
    cast = totals.loc[totals["cast"] > 0]
    joined = t1.merge(cast, on=["year", "name"], how="left", indicator=True)
    unresolved = joined.loc[joined["_merge"] != "both"]
    check(
        unresolved.empty,
        "Table 1 rows with no cast-vote candidate that year: "
        + ", ".join(f"{r.year} {r.printed_name}" for r in unresolved.itertuples()),
    )

    # 3. The two Table 1 rows in a year are different candidates.
    check(
        not t1.duplicated(["year", "name"]).any(),
        "a year's two Table 1 rows name the same candidate",
    )

    # 4. No candidate-year in the transform's national totals has zero votes cast.
    # This reads the transform frame; check 5 carries it to the served set.
    zero_cast = totals.loc[~(totals["cast"] > 0)]
    check(
        zero_cast.empty,
        "candidate-years with no cast vote (each needs a stated cause): "
        + ", ".join(f"{r.year} {r.name}" for r in zero_cast.itertuples()),
    )

    # Consequence tripwires: these follow from parse_table1 (which zips the fixed
    # T1_ROW_INDS) and from national_totals' no-duplicate check, so they cannot fail
    # on their own. They stay so that a change to either fails here, by name.
    check(
        (t1.groupby("year").size() == len(parse.T1_ROW_INDS)).all(),
        f"a year has other than {len(parse.T1_ROW_INDS)} Table 1 rows",
    )
    check(len(joined) == len(t1), "a Table 1 row matched more than one candidate")

    # (b) The population: cast-vote candidate-years minus Table 1's.
    t1_keys = set(zip(t1["year"], t1["name"], strict=True))
    remainder = cast.loc[
        [(y, n) not in t1_keys for y, n in zip(cast["year"], cast["name"], strict=True)]
    ].sort_values(["year", "cast"], ascending=[True, False])
    remainder = remainder.assign(
        era=[EARLY_ERA if y < MIT_FLOOR else MIT_ERA for y in remainder["year"]]
    )
    # Consequence tripwire of checks 2 and 3 and national_totals' no-duplicate check.
    check(
        len(remainder) + len(t1) == len(cast),
        "population + Table 1 rows != cast-vote candidate-years",
    )

    # 6. No candidate-year has more votes counted than cast (appointed >= cast >=
    # counted).
    check(
        (totals["counted"] <= totals["cast"]).all(),
        "a candidate-year has more votes counted than cast",
    )
    # (c) Cast and counted differ.
    differ = totals.loc[totals["cast"] != totals["counted"]].sort_values(
        ["year", "name"]
    )

    snapshot = read_snapshot()
    skipped = ""
    mit = mit_population = None
    if snapshot is None:
        check(
            args.allow_no_snapshot,
            f"the snapshot is absent ({SNAPSHOT}); checks 5 and 8 need it "
            "(--allow-no-snapshot skips them)",
        )
        version = "absent"
        skipped = " (checks 5 and 8 skipped: no snapshot)"
    else:
        served, version = snapshot
        # 5. The served snapshot holds exactly the transform's candidate-years, with
        # neither side filtered first, and every served one has votes cast. A served
        # zero-cast or null row would be a second cause of a null party (doc §2.3).
        served_keys = {
            (int(y), str(sl))
            for y, sl in zip(served["year"], served["candidate_slug"], strict=True)
        }
        script_keys = {
            (int(y), candidate_slug(n))
            for y, n in zip(totals["year"], totals["name"], strict=True)
        }
        check(
            served_keys == script_keys,
            "snapshot vs script candidate-year set: only served "
            f"{sorted(served_keys - script_keys)}, only script "
            f"{sorted(script_keys - served_keys)}",
        )
        check(
            bool((served["national_electoral_votes"] > 0).all()),
            "a served candidate-year has no electoral vote cast",
        )

        # 8. MIT's party, as the doc's §9 records it. Every join must find its served
        # row, so a failed join cannot read as a null party.
        mit_party = served[["year", "candidate_slug", "party"]].rename(
            columns={"party": "mit_party"}
        )
        t1_slugs = t1.assign(candidate_slug=t1["name"].map(candidate_slug))
        mit = merge_all(
            t1_slugs.loc[t1_slugs["year"] >= MIT_FLOOR], mit_party, "MIT, Table 1"
        )[["year", "name", "token", "mit_party"]]
        check(
            set(mit["token"]) <= set(MIT_CROSSWALK),
            f"a {MIT_ERA} Table 1 token outside the crosswalk: "
            f"{sorted(set(mit['token']))}",
        )
        disagree = mit.loc[mit["mit_party"] != mit["token"].map(MIT_CROSSWALK)]
        check(
            disagree.empty,
            f"{MIT_ERA} Table 1 rows whose MIT party disagrees with the token: "
            + ", ".join(f"{r.year} {r.name}" for r in disagree.itertuples()),
        )
        # A dated headline: the 1976+ population rows have no MIT party. If a later
        # snapshot breaks this, re-check the doc's §9 rather than the data.
        late = remainder.loc[remainder["year"] >= MIT_FLOOR]
        mit_population = merge_all(
            late.assign(candidate_slug=late["name"].map(candidate_slug)),
            mit_party,
            "MIT, population",
        )[["year", "name", "mit_party"]]
        check(
            mit_population["mit_party"].isna().all(),
            f"a {MIT_ERA} population row has an MIT party; re-check the doc's §9",
        )

    # 7. Nothing here touched UCSB (D022).
    check("usvote.ucsb" not in sys.modules, "usvote.ucsb was imported")

    print("## Run metadata\n")
    print(f"- commit: {run_id()}")
    print(f"- corpus: {EC_DIR}")
    print(f"- snapshot: {SNAPSHOT} — {version}")
    print(f"- elections: {len(years)} ({min(years)}–{max(years)})")
    print(f"- cast-vote candidate-years: {len(cast)}")
    print(f"- Table 1 rows: {len(t1)}")
    era_counts = remainder["era"].value_counts()
    print(
        f"- population (cast minus Table 1): {len(remainder)} "
        f"({EARLY_ERA} {era_counts.get(EARLY_ERA, 0)}, "
        f"{MIT_ERA} {era_counts.get(MIT_ERA, 0)})"
    )
    print("\n## (a) Table 1 printed tokens\n")
    print(markdown(t1[["year", "row", "printed_name", "token"]]))
    tokens = (
        t1.groupby("token")["year"]
        .agg(lambda ys: ", ".join(str(y) for y in sorted(ys)))
        .reset_index()
        .rename(columns={"year": "years"})
    )
    print("\n### Distinct tokens\n")
    print(markdown(tokens))
    print("\n## (b) Population: cast-vote candidate-years outside Table 1\n")
    print(markdown(remainder[["era", "year", "name", "cast", "counted"]]))
    print("\n## (c) Cast and counted differ\n")
    print(markdown(differ[["year", "name", "cast", "counted"]]))
    if mit is not None:
        print(f"\n## MIT party on the {MIT_ERA} Table 1 rows (snapshot)\n")
        print(markdown(mit))
        mit_values = sorted(mit["mit_party"].dropna().unique())
        print(f"\nDistinct MIT values: {', '.join(mit_values)}")
    if mit_population is not None:
        print(f"\n## MIT party on the {MIT_ERA} population rows (snapshot)\n")
        print(markdown(mit_population))
    print(f"\nAll checks passed{skipped}.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckFailed as exc:
        print(f"CHECK FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
