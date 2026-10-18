"""#384 — candidate-party population, the derived half of the #384 research doc.

The doc is `research-candidate-party-source.md`, beside this script.

Runs fully **offline** against the Archives corpus and the TIGER shapefile, with no
network and no database credentials:

    USVOTE_EC_HTML_DIR/<year>.html        (the Archives corpus, #89)
    USVOTE_SHAPEFILE_PATH                 (TIGER2019 states, as the EC pipeline uses)
    USVOTE_API_SNAPSHOT_PATH (optional)   (the served snapshot, opened read-only)

    uv run python .claude/specs/research-candidate-party-source.py

It builds the warehouse's EC frames with the warehouse's **own** composition,
`transform.transform_parsed_years` (the call `pipeline.run_ec_pipeline` makes), so the
candidate-years it lists are the ones `dwh.votes` and `dwh.candidate` hold. SQL over
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

With the snapshot present it also prints the MIT `party` values on each 1976+ Table 1
row, for the doc's crosswalk, and checks the snapshot's candidate-year set against the
script's.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from usvote import parse, scrape, transform
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
MIT_FLOOR = 1976


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


def read_snapshot() -> tuple[set[tuple[int, str]], pd.DataFrame, str] | None:
    """The served (year, slug) set with cast votes, the MIT parties, and the version.

    Opened through a `mode=ro` URI so the read cannot write. Returns None when the
    file is absent, and the caller says so.
    """
    if not SNAPSHOT.exists():
        return None
    con = sqlite3.connect(f"file:{SNAPSHOT}?mode=ro", uri=True)
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
    cast = served.loc[served["national_electoral_votes"] > 0]
    pairs = zip(cast["year"], cast["candidate_slug"], strict=True)
    keys = {(int(y), str(s)) for y, s in pairs}
    return keys, served, f"{version} (schema {schema})"


def markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for rec in df.itertuples(index=False):
        cells = ("" if pd.isna(v) else str(v) for v in rec)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> int:
    parsed, state_geo = load_parsed_years()
    candidates, _state, votes = transform.transform_parsed_years(parsed, state_geo)
    totals = national_totals(votes, candidates)
    t1 = table1_rows(parsed)
    years = ec_ingest_years()

    # 1. The years covered are exactly the EC ingest years.
    check(set(t1["year"]) == years, "Table 1 years differ from ec_ingest_years()")
    check(set(totals["year"]) == years, "fact years differ from ec_ingest_years()")
    check(
        (t1.groupby("year").size() == len(parse.T1_ROW_INDS)).all(),
        f"a year has other than {len(parse.T1_ROW_INDS)} Table 1 rows",
    )

    # 2. Each Table 1 row resolves to exactly one candidate with cast votes that year.
    cast = totals.loc[totals["cast"] > 0]
    joined = t1.merge(cast, on=["year", "name"], how="left", indicator=True)
    unresolved = joined.loc[joined["_merge"] != "both"]
    check(
        unresolved.empty,
        "Table 1 rows with no cast-vote candidate that year: "
        + ", ".join(f"{r.year} {r.printed_name}" for r in unresolved.itertuples()),
    )
    check(len(joined) == len(t1), "a Table 1 row matched more than one candidate")

    # 3. The two Table 1 rows in a year are different candidates.
    check(
        not t1.duplicated(["year", "name"]).any(),
        "a year's two Table 1 rows name the same candidate",
    )

    # 4. A served candidate-year with no cast vote would need its own null cause.
    zero_cast = totals.loc[totals["cast"] <= 0]
    check(
        zero_cast.empty,
        "served candidate-years with no cast vote (each needs a stated cause): "
        + ", ".join(f"{r.year} {r.name}" for r in zero_cast.itertuples()),
    )

    # (b) The population: cast-vote candidate-years minus Table 1's.
    t1_keys = set(zip(t1["year"], t1["name"], strict=True))
    remainder = cast.loc[
        [(y, n) not in t1_keys for y, n in zip(cast["year"], cast["name"], strict=True)]
    ].sort_values(["year", "cast"], ascending=[True, False])
    remainder = remainder.assign(
        era=["pre-1976" if y < MIT_FLOOR else "1976+" for y in remainder["year"]]
    )
    check(
        len(remainder) + len(t1) == len(cast),
        "population + Table 1 rows != cast-vote candidate-years",
    )

    # (c) Cast and counted differ.
    differ = totals.loc[totals["cast"] != totals["counted"]].sort_values(
        ["year", "name"]
    )
    check(
        (differ["counted"] <= differ["cast"]).all(),
        "a candidate-year has more votes counted than cast",
    )

    # 5. The served snapshot holds the same cast-vote candidate-years.
    snapshot = read_snapshot()
    if snapshot is None:
        print(f"> snapshot cross-check skipped: {SNAPSHOT} is absent\n")
        version = "absent"
        mit = None
        mit_population = None
    else:
        served_keys, served, version = snapshot
        script_keys = {
            (int(y), candidate_slug(n))
            for y, n in zip(cast["year"], cast["name"], strict=True)
        }
        check(
            served_keys == script_keys,
            "snapshot vs script cast-vote set: only served "
            f"{sorted(served_keys - script_keys)}, only script "
            f"{sorted(script_keys - served_keys)}",
        )
        mit_party = served[["year", "candidate_slug", "party"]].rename(
            columns={"party": "mit_party"}
        )
        t1_slugs = t1.assign(candidate_slug=t1["name"].map(candidate_slug))
        mit = t1_slugs.loc[t1_slugs["year"] >= MIT_FLOOR].merge(
            mit_party, on=["year", "candidate_slug"], how="left"
        )[["year", "name", "token", "mit_party"]]
        # The 1976+ population rows too: a non-null MIT party on one of them would
        # meet the MIT check against a curated value, not a Table 1 one.
        late = remainder.loc[remainder["year"] >= MIT_FLOOR]
        mit_population = late.assign(
            candidate_slug=late["name"].map(candidate_slug)
        ).merge(mit_party, on=["year", "candidate_slug"], how="left")[
            ["year", "name", "mit_party"]
        ]

    # 7. Nothing here touched UCSB (D022).
    check("usvote.ucsb" not in sys.modules, "usvote.ucsb was imported")

    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print("## Run metadata\n")
    print(f"- commit: {sha}")
    print(f"- corpus: {EC_DIR}")
    print(f"- snapshot: {SNAPSHOT} — {version}")
    print(f"- elections: {len(years)} ({min(years)}–{max(years)})")
    print(f"- cast-vote candidate-years: {len(cast)}")
    print(f"- Table 1 rows: {len(t1)}")
    era_counts = remainder["era"].value_counts()
    print(
        f"- population (cast minus Table 1): {len(remainder)} "
        f"(pre-1976 {era_counts.get('pre-1976', 0)}, "
        f"1976+ {era_counts.get('1976+', 0)})"
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
        print("\n## MIT party on the 1976+ Table 1 rows (snapshot)\n")
        print(markdown(mit))
        mit_values = sorted(mit["mit_party"].dropna().unique())
        print(f"\nDistinct MIT values: {', '.join(mit_values)}")
    if mit_population is not None:
        print("\n## MIT party on the 1976+ population rows (snapshot)\n")
        print(markdown(mit_population))
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckFailed as exc:
        print(f"CHECK FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
