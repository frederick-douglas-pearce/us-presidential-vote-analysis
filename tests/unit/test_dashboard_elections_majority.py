"""The Electoral College majority page, ``/elections/majority``: chart C2 and its
companion table (#434, D096), on their own page since #562 (D107).

Offline, against the recorded ``/v1/elections`` and N1 fixtures, through the helpers
and the autouse offline process client of ``test_dashboard_app.py``.
"""

from __future__ import annotations

import copy
import re
import urllib.parse
from typing import Any

import dash
import pytest

from explore import api, charts, components, labels, over_time
from tests.unit.test_dashboard_app import (
    RECORDED,
    VERSION,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    cached_client,
    route,
    routed_ids,
    texts,
)
from tests.unit.test_dashboard_elections import (
    BODY,
    SUMMARY,
    YEARS,
    _second_item,
    _second_leader,
    _without,
    c2_figure,
    find,
    in_order,
    n1_client,
    of_type,
)

PAGE: dict[str, Any] = dash.page_registry["pages.elections_majority"]
#: The page module's namespace, reached through its layout (``pages.elections``' rule).
MOD: dict[str, Any] = PAGE["layout"].__globals__
PAGE_ID = MOD["PAGE_ID"]


def test_the_page_is_registered_as_planned() -> None:
    assert PAGE["path"] == "/elections/majority"
    assert PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    # N1, chart C2's source: a literal filled on a miss (#434, D074(ii)).
    assert PAGE["on_miss"] == (api.SUMMARY_PATH,)
    assert PAGE["success"] == PAGE_ID
    assert PAGE.get("query") is None  # no filter reaches C2 (D096(b))
    assert PAGE["nav"] == "elections"


# --- chart C2 (#434, D096) ------------------------------------------------------------

C2 = charts.dom_id("C2")
LEADERS = MOD["LEADER_TABLE_ID"]
#: The years with a recorded ``/v1/elections/{year}``: T3's rows to reconcile against.
RECONCILED = (1824, 1860, 1868, 1872, 1896, 2016, 2024)
#: T3's worded cells, from the overview's own function (one source for T3 and C1).
NATION_CELLS = dash.page_registry["pages.election"]["layout"].__globals__[
    "_nation_cells"
]


def render_c2(summary: Any = None, index: Any = None) -> Any:
    """The page for the index and an N1 body (the recording unless given)."""
    return MOD["render"](
        copy.deepcopy(BODY if index is None else index),
        copy.deepcopy(SUMMARY if summary is None else summary),
    )


#: The hover's share line, whose cell is what a point's text label carried before
#: #558 (D104): the companion table's cell for the share.
C2_SHARE_LINE = re.compile(r"<br>Electoral share \(counted ÷ appointed\): (.*?)<br>")


def hover_share(hover: str) -> str:
    """The share cell a C2 hover writes (:data:`C2_SHARE_LINE`), its note dropped."""
    match = C2_SHARE_LINE.search(hover)
    assert match is not None, hover
    return match.group(1).split("<br>")[0]


def named(figure: dict[str, Any], name: str) -> dict[str, Any]:
    """C2's one trace of that name (#564: the circle's is no longer the first)."""
    (trace,) = [t for t in figure["data"] if t["name"] == name and "marker" in t]
    found: dict[str, Any] = trace
    return found


#: The marker series' names, whose traces are not marks at a value.
MARKER_NAMES = (labels.C2_NO_FIGURE, labels.UNRECOGNIZED)


def markers(figure: dict[str, Any]) -> list[dict[str, Any]]:
    return [t for t in figure["data"] if t["name"] in MARKER_NAMES]


def points(tree: Any) -> dict[str, tuple[Any, str, str]]:
    """Each year's circle: its share (y), the share cell its hover writes, and the
    hover, by the year (the trace's ids). Each point sits at its year (x), which the
    ids repeat as text (#558, D104)."""
    trace = named(c2_figure(tree), labels.LABELS["ec_share_full"])
    assert "text" not in trace and trace["mode"] == "markers"
    assert trace["ids"] == [str(x) for x in trace["x"]]
    assert all(type(x) is int for x in trace["x"])
    return {
        year: (y, hover_share(hover), hover)
        for year, y, hover in zip(
            trace["ids"], trace["y"], trace["hovertext"], strict=True
        )
    }


def leader_rows(tree: Any) -> list[list[str]]:
    table = find(tree, LEADERS)
    return [texts(tr.children) for tr in of_type(of_type(table, "Tbody"), "Tr")]


def rank1(year: int) -> dict[str, Any]:
    summary: list[dict[str, Any]] = RECORDED[f"/v1/elections/{year}"]["summary"]
    (row,) = [r for r in summary if r["electoral_rank"] == 1]
    return row


class TestC2:
    def test_registered_on_its_own_page_with_its_own_companion_table(self) -> None:
        assert charts.CHARTS["C2"] == charts.Chart("/elections/majority", LEADERS)
        assert MOD["C2_ID"] == "C2" and C2 == "c2"
        tree = render_c2()
        assert type(find(tree, C2)).__name__ == "Figure"  # the #c2 fragment's target
        assert PAGE_ID not in [n.id for n in of_type(find(tree, C2), "Div") if n.id]

    def test_the_page_order_puts_the_chart_first(self) -> None:
        """The page's heading is C2's (#562): then the lede, the chart, the companion
        table's heading and the table."""
        tree = render_c2()
        assert of_type(tree, "H1")[0].children == MOD["HEADING"]
        assert of_type(tree, "H2")[0].children == MOD["C2_TABLE_HEADING"]
        assert of_type(tree, "P")[0].children == MOD["LEDE"]
        order = in_order(tree)
        assert order.index(find(tree, C2)) < order.index(find(tree, LEADERS))

    def test_one_point_for_every_served_year_oldest_first(self) -> None:
        tree = render_c2()
        figure = c2_figure(tree)
        circles = named(figure, labels.LABELS["ec_share_full"])
        assert [str(y) for y in YEARS] == circles["ids"]
        # Each point at its year on the numeric year axis along the bottom (#558, D104),
        # oldest at the left.
        assert circles["x"] == list(YEARS)
        assert figure["layout"]["xaxis"] == components.year_axis(YEARS)
        assert figure["layout"]["xaxis"]["type"] == "linear"
        coverage = BODY["meta"]["provenance"]["coverage"]
        assert (YEARS[0], YEARS[-1]) == (coverage["year_min"], coverage["year_max"])
        assert markers(figure) == []  # no marker: every leader has a share
        assert charts.figure_problems(figure) == []

    def test_one_point_per_year_however_the_index_is_cut(self) -> None:
        """No literal span: an index serving fewer years gets that many points."""
        index = copy.deepcopy(BODY)
        index["data"] = [r for r in index["data"] if r["year"] <= 1900]
        index["meta"]["provenance"]["coverage"]["year_max"] = 1900
        summary = copy.deepcopy(SUMMARY)
        for key in ("data", "elections"):
            summary[key] = [r for r in summary[key] if r["year"] <= 1900]
        ids = points(render_c2(summary, index))
        assert list(ids) == [str(r["year"]) for r in index["data"]]

    @pytest.mark.parametrize("year", RECONCILED)
    def test_each_recorded_year_reconciles_with_t3_s_leader(self, year: int) -> None:
        x, text, hover = points(render_c2())[str(year)]  # x: the share, up the side
        row = rank1(year)
        has_pv = (
            year
            >= RECORDED[api.ELECTIONS_PATH]["meta"]["provenance"]["coverage"][
                "pv_year_min"
            ]
        )
        cell = NATION_CELLS(row, has_pv)
        assert x == row["ec_share_full"]
        assert text == cell["ec_share_full"]
        assert cell["national_electoral_votes_counted"] in hover
        assert cell["national_electoral_denominator"] in hover
        assert hover.startswith(f"{year}: {row['candidate']}<br>")

    def test_1824_sits_below_the_line_and_reads_as_no_majority(self) -> None:
        x, text, hover = points(render_c2())["1824"]
        assert x < 0.5 and text == "37.9%"
        assert hover.endswith(f"<br>{labels.NO_EC_MAJORITY}")
        assert "Andrew Jackson" in hover

    @pytest.mark.parametrize(("year", "text"), [("1876", "50.1%"), ("2000", "50.4%")])
    def test_1876_and_2000_sit_just_above_the_line(self, year: str, text: str) -> None:
        x, shown, hover = points(render_c2())[year]
        assert 0.5 < x < 0.51 and shown == text
        assert hover.endswith(f"<br>{labels.EC_MAJORITY}")

    @pytest.mark.parametrize(
        ("year", "counted", "appointed"),
        [("2016", "304", "538"), ("1868", "214", "294"), ("1872", "286", "366")],
    )
    def test_the_counted_basis(self, year: str, counted: str, appointed: str) -> None:
        _, _, hover = points(render_c2())[year]
        assert f"Electoral votes counted: {counted}<br>" in hover
        assert f"Electors appointed: {appointed}<br>" in hover

    def test_every_hover_carries_a_majority_line(self) -> None:
        for year, (_, _, hover) in points(render_c2()).items():
            assert hover.rsplit("<br>", 1)[1] in (
                labels.EC_MAJORITY,
                labels.NO_EC_MAJORITY,
            ), year

    def test_a_null_majority_is_named_by_its_field(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        summary["elections"][1]["ec_determinative"] = None
        _, _, hover = points(render_c2(summary))[str(summary["elections"][1]["year"])]
        assert hover.endswith(
            f"<br>{labels.LABELS['ec_determinative']}: {labels.NOT_IN_DATASET}"
        )

    def test_the_point_is_the_served_ec_share_full(self) -> None:
        """Not a sibling or a derived value: 1860's leader's ``ec_share_full`` alone is
        doctored (deliberately inconsistent with its counts and ``ec_share_hybrid``), and
        the point, its text and the table's cell all follow it."""
        summary = copy.deepcopy(SUMMARY)
        (row,) = [
            r for r in summary["data"] if r["year"] == 1860 and r["electoral_rank"] == 1
        ]
        assert row["ec_share_hybrid"] != 0.25  # the premise
        row["ec_share_full"] = 0.25
        tree = render_c2(summary)
        x, text, hover = points(tree)["1860"]
        assert (x, text) == (0.25, "25.0%")
        assert "(counted ÷ appointed): 25.0%<br>" in hover
        (shown,) = [r for r in leader_rows(tree) if r[0] == "1860"]
        assert shown[4] == "25.0%"

    def test_the_candidate_is_escaped_in_the_hover(self) -> None:
        summary = copy.deepcopy(SUMMARY)
        name = "A <b>&</b> B"
        summary["data"][0]["candidate"] = name  # 1824's leader
        figure = c2_figure(render_c2(summary))
        _, _, hover = points(render_c2(summary))["1824"]
        assert hover.startswith(f"1824: {charts.escaped(name)}<br>")
        assert charts.escaped(name) != name  # the premise
        assert charts.figure_problems(figure) == []

    def test_an_index_listing_a_year_twice_draws_it_once(self) -> None:
        index = copy.deepcopy(BODY)
        index["data"].append(copy.deepcopy(index["data"][0]))
        assert list(points(render_c2(index=index))) == [str(y) for y in YEARS]

    @pytest.mark.parametrize(
        ("value", "label"),
        [
            (None, labels.C2_NO_FIGURE),
            ("zz", labels.UNRECOGNIZED),
            # Finite, but its percentage overflows, so its cell reads UNRECOGNIZED.
            (1e308, labels.UNRECOGNIZED),
        ],
    )
    def test_a_share_with_no_figure_is_a_labeled_marker(
        self, value: Any, label: str
    ) -> None:
        summary = copy.deepcopy(SUMMARY)
        (row,) = [
            r for r in summary["data"] if r["year"] == 1860 and r["electoral_rank"] == 1
        ]
        row["ec_share_full"] = value
        tree = render_c2(summary)
        figure = c2_figure(tree)
        assert "1860" not in points(tree)
        (marks,) = markers(figure)
        # Labeled by the chart's key, one series per label (#558, D104), never a text.
        assert marks["name"] == label and marks["showlegend"] is True
        assert "text" not in marks and marks["mode"] == "markers"
        assert marks["ids"] == ["1860"] and marks["x"] == [1860] and marks["y"] == [0]
        assert marks["marker"]["symbol"] == MOD["_C2_SYMBOLS"][label]
        assert figure["layout"]["showlegend"] is True
        assert figure["layout"]["legend"] == components.TIME_SERIES_LEGEND
        (caption,) = of_type(find(tree, C2), "Figcaption")
        assert caption.children[0].endswith(labels.C2_NO_SHARE_NOTE)
        if label == labels.UNRECOGNIZED:
            note = f"{labels.UNRECOGNIZED}<br>{labels.UNRECOGNIZED_NOTE}"
            assert note in marks["hovertext"][0]
        assert charts.figure_problems(figure) == []

    def test_the_marker_note_shows_only_with_a_marker(self) -> None:
        """The caption names the marker only when one is drawn (#558, D104): with every
        leader's share served, there is no marker, no key and no note (Class B
        survivor: the note added unconditionally)."""
        tree = render_c2()
        (caption,) = of_type(find(tree, C2), "Figcaption")
        assert labels.C2_NO_SHARE_NOTE not in caption.children[0]
        assert caption.children[0].endswith(labels.C2_PV_DIFFERENT_NOTE)
        assert markers(c2_figure(tree)) == []  # the premise: no marker drawn

    def test_the_majority_line_is_a_dashed_shape_at_half(self) -> None:
        layout = c2_figure(render_c2())["layout"]
        (line,) = [s for s in layout["shapes"] if s["type"] == "line"]
        # Horizontal across the plot at half (#558, D104).
        assert (line["yref"], line["y0"], line["y1"]) == ("y", 0.5, 0.5)
        assert (line["xref"], line["x0"], line["x1"]) == ("paper", 0, 1)
        assert line["line"]["dash"] == "dash"
        # One label, just below the line at the left (owner, #564's plan gate, D108).
        (note,) = [a for a in layout["annotations"] if a["yref"] == "y"]
        assert note["text"] == labels.C2_MAJORITY_LINE
        # From the second served year, clear of 1824's point below the line (#564).
        assert (note["xref"], note["x"], note["xanchor"]) == ("x", YEARS[1], "left")
        assert (note["yref"], note["y"], note["yanchor"]) == ("y", 0.5, "top")
        assert note["yshift"] < 0
        # The axis runs past 100% for the strip; its ticks stop at 100% (#564).
        assert layout["yaxis"]["range"] == [0, MOD["_C2_Y_TOP"]]
        assert layout["yaxis"]["tickvals"][-1] == 1
        assert 1 < MOD["_C2_STRIP_Y"] < MOD["_C2_Y_TOP"]
        assert layout["showlegend"] is True  # three series at least, always keyed

    def test_the_title_is_page_text(self) -> None:
        assert find(render_c2(), f"{C2}-title").children == labels.C2_TITLE

    def test_the_companion_table_holds_the_points_values(self) -> None:
        tree = render_c2()
        rows = leader_rows(tree)
        shown = points(tree)
        assert [r[0] for r in rows] == [str(y) for y in YEARS]
        for row in rows:
            year, candidate, counted, appointed, share, majority, took = row[:7]
            if year not in shown:
                # A marker, at zero, exactly where the table shows no share (#558, I-5).
                assert share in (labels.NOT_IN_DATASET, labels.UNRECOGNIZED), year
                continue
            y, text, hover = shown[year]
            assert share == text
            # Drawn where its cell says, now that no text sits beside it (I-5).
            assert labels.share(y) == share, year
            assert hover == labels.C2_HOVER.format(
                year=year,
                candidate=candidate,
                share=share,
                counted=counted,
                appointed=appointed,
                majority=majority,
            )
            assert took in ("Yes", "No")
        assert rows[0][1] == "Andrew Jackson" and rows[0][6] == "No"
        table = find(tree, LEADERS)
        links = {a.href for a in of_type(table, "Link")}
        assert {f"/election/{y}" for y in YEARS} <= links

    @pytest.mark.parametrize(
        "query", ["year_from=1900", "pv=1", "year_to=1880", "state=GA"]
    )
    def test_no_filter_reaches_the_page(
        self, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        """The page has no ``query=`` parser (D096(b)): a routed render under any old
        key equals the unfiltered one."""
        cached_client(monkeypatch)
        assert routed_ids(route("/elections/majority", f"?{query}")) == routed_ids(
            route("/elections/majority", "")
        )

    def test_the_download_names_the_leaders(self) -> None:
        (link,) = [
            a
            for a in of_type(render_c2(), "A")
            if getattr(a, "id", None) == f"{LEADERS}-csv"
        ]
        assert link.download == "elections-electoral-college-leaders.csv"
        assert link.children == "Download the Electoral College leaders (CSV)"


def _leader_before(year: int) -> dict[str, Any]:
    """A second rank-1 row in ``year``, placed BEFORE the real leader (#564's Class B
    survivor): a later row would overwrite it, so only the tie refusal catches it."""
    summary = copy.deepcopy(SUMMARY)
    i = next(
        k
        for k, r in enumerate(summary["data"])
        if r["year"] == year and r["electoral_rank"] == 1
    )
    extra = copy.deepcopy(summary["data"][i])
    extra["candidate_slug"] = "someone-else"
    summary["data"].insert(i, extra)
    return summary


def _leader_twice(year: int) -> dict[str, Any]:
    """The leader's own row twice (#564's Class B survivor)."""
    summary = copy.deepcopy(SUMMARY)
    row = next(
        r for r in summary["data"] if r["year"] == year and r["electoral_rank"] == 1
    )
    summary["data"].append(copy.deepcopy(row))
    return summary


# --- the three methods (#564, D108) ----------------------------------------------------

OVER_TIME_MOD: dict[str, Any] = dash.page_registry["pages.elections_over_time"][
    "layout"
].__globals__
COVERAGE = BODY["meta"]["provenance"]["coverage"]
WINDOW = (COVERAGE["pv_year_min"], COVERAGE["pv_year_max"])
#: Each year's ``has_popular_vote``, from the index, T3's year rule.
HAS_PV = {row["year"]: row["has_popular_vote"] for row in BODY["data"]}
ITEMS = {item["year"]: item for item in SUMMARY["elections"]}
LEADER = {row["year"]: row for row in SUMMARY["data"] if row["electoral_rank"] == 1}


def _named_or_none(figure: dict[str, Any], name: str) -> dict[str, Any] | None:
    found = [t for t in figure["data"] if t["name"] == name and "marker" in t]
    return found[0] if found else None


def _caption(tree: Any) -> str:
    (caption,) = of_type(find(tree, C2), "Figcaption")
    text: str = caption.children[0]
    return text


def _cell_of(tree: Any, year: int, field: str) -> str:
    (row,) = [r for r in leader_rows(tree) if r[0] == str(year)]
    cell: str = row[MOD["LEADER_FIELDS"].index(field)]
    return cell


def _with(**changes: Any) -> dict[str, Any]:
    """N1 with ``changes`` (``"<year>.<field>"``: value) applied to that year's item."""
    summary = copy.deepcopy(SUMMARY)
    for key, value in changes.items():
        year, field = key.split(".", 1)
        (item,) = [i for i in summary["elections"] if i["year"] == int(year)]
        item[field] = value
    return summary


class TestC2Methods:
    def test_one_meaning_per_symbol_across_the_time_series(self) -> None:
        """D104(d), extended by D108 (#564, B1): every C2 symbol, written out, and none
        that C4, C5 or C7 use for another meaning (C7 draws C4's)."""
        c2 = {
            MOD["_C2_EC_SYMBOL"]: "electoral share",
            MOD["_C2_PV_SYMBOL"]: "popular-vote share",
            MOD["_C2_HYBRID_SYMBOL"]: "hybrid score",
            MOD["_C2_PV_DIFFERENT_SYMBOL"]: "popular-vote winner differs",
            MOD["_C2_HYBRID_DIFFERENT_SYMBOL"]: "hybrid winner differs",
            **{symbol: label for label, symbol in MOD["_C2_SYMBOLS"].items()},
        }
        assert c2 == {
            "circle": "electoral share",
            "triangle-up": "popular-vote share",
            "star": "hybrid score",
            "hexagon": "popular-vote winner differs",
            "pentagon": "hybrid winner differs",
            "circle-open": labels.C2_NO_FIGURE,
            "square-open": labels.UNRECOGNIZED,
        }
        others = {**over_time.C4_SYMBOLS, **OVER_TIME_MOD["_C5_SYMBOLS"]}
        shared = {"circle-open", "square-open"}  # no figure, unrecognized: one meaning
        for label, symbol in others.items():
            assert symbol not in set(c2) - shared, (label, symbol)
            if symbol == "square-open":
                assert label == labels.UNRECOGNIZED
            if symbol == "circle-open":
                assert label in (labels.NOT_IN_DATASET, labels.C5_NO_TOTAL)

    def test_the_drawing_order_puts_the_circle_on_top(self) -> None:
        """M1: the connector under the triangles, then the stars, then the circles."""
        names = [t["name"] for t in c2_figure(render_c2())["data"]]
        order = [
            labels.LABELS["pv_share"],  # the connector, no marker
            labels.LABELS["pv_share"],
            labels.C2_HYBRID_KEY,
            labels.LABELS["ec_share_full"],
        ]
        assert names[:4] == order
        assert "marker" not in c2_figure(render_c2())["data"][0]

    def test_the_triangle_and_star_stand_at_the_served_values(self) -> None:
        """T2: each mark's y is the served value whose table cell its hover writes, in
        every year T3's rule treats as having a popular vote, and in no other."""
        tree = render_c2()
        figure = c2_figure(tree)
        drawn = sorted(y for y, has in HAS_PV.items() if has)
        assert drawn  # the premise
        for name, field, template, key in (
            (labels.LABELS["pv_share"], "pv_share", labels.C2_PV_HOVER, "share"),
            (labels.C2_HYBRID_KEY, "hybrid_score", labels.C2_HYBRID_HOVER, "score"),
        ):
            trace = named(figure, name)
            assert trace["x"] == drawn
            for year, y, hover in zip(
                trace["x"], trace["y"], trace["hovertext"], strict=True
            ):
                assert y == LEADER[year][field]
                cell = _cell_of(tree, year, field)
                assert labels.share(y) == cell
                assert hover == template.format(
                    year=year, candidate=LEADER[year]["candidate"], **{key: cell}
                )
        for year, has in HAS_PV.items():
            if not has:
                assert _cell_of(tree, year, "pv_share") == labels.NOT_APPLICABLE
                assert _cell_of(tree, year, "hybrid_score") == labels.NOT_APPLICABLE

    def test_the_connector_joins_each_year_s_circle_to_its_triangle(self) -> None:
        """T1: no hover, no text, so only this ties it to the marks."""
        figure = c2_figure(render_c2())
        line = figure["data"][0]
        assert line["mode"] == "lines" and line["hoverinfo"] == "skip"
        assert line["showlegend"] is False and line["line"]["width"] == 1
        circles = named(figure, labels.LABELS["ec_share_full"])
        triangles = named(figure, labels.LABELS["pv_share"])
        ec = dict(zip(circles["x"], circles["y"], strict=True))
        pv = dict(zip(triangles["x"], triangles["y"], strict=True))
        xs, ys = line["x"], line["y"]
        segments = [(xs[i : i + 3], ys[i : i + 3]) for i in range(0, len(xs), 3)]
        assert [x[0] for x, _ in segments] == triangles["x"]
        for (x0, x1, gap), (y0, y1, ygap) in segments:
            assert x0 == x1 and gap is None and ygap is None
            assert (y0, y1) == (ec[x0], pv[x0])

    def test_the_strip_marks_the_served_disagreements(self) -> None:
        """AC3: the marked years equal those whose served winner slug differs from the
        Electoral College's, an oracle independent of the flags the chart reads."""
        figure = c2_figure(render_c2())
        for name, winner in (
            (labels.C2_PV_DIFFERENT_KEY, "pv_winner_slug"),
            (labels.C2_HYBRID_DIFFERENT_KEY, "hybrid_winner_slug"),
        ):
            expected = sorted(
                year
                for year, item in ITEMS.items()
                if item[winner] is not None and item[winner] != item["ec_winner_slug"]
            )
            trace = _named_or_none(figure, name)
            if not expected:
                assert trace is None, name
                continue
            assert trace is not None and trace["x"] == expected
            assert trace["y"] == [MOD["_C2_STRIP_Y"]] * len(expected)
        assert named(figure, labels.C2_PV_DIFFERENT_KEY)["x"] == [2000, 2016]

    def test_the_strip_follows_the_flag(self) -> None:
        """T4 (#564's review, g.2): with a flag and its winner doctored together, so the
        two still agree, the strip moves with them; for the hybrid too, which the
        recording never marks."""
        moved = _with(
            **{
                "2000.pv_flip": False,
                "2000.pv_winner": ITEMS[2000]["ec_winner"],
                "2000.pv_winner_slug": ITEMS[2000]["ec_winner_slug"],
            }
        )
        trace = named(c2_figure(render_c2(moved)), labels.C2_PV_DIFFERENT_KEY)
        assert trace["x"] == [2016]
        hybrid = _with(
            **{
                "2016.hybrid_flip": True,
                "2016.hybrid_winner": "Doctored Winner",
                "2016.hybrid_winner_slug": "doctored-winner",
            }
        )
        tree = render_c2(hybrid)
        strip = named(c2_figure(tree), labels.C2_HYBRID_DIFFERENT_KEY)
        assert strip["x"] == [2016]
        # Its hover names the table's hybrid winner, not the popular vote's, and carries
        # the proposal label (#564's review, r2.recheck.2).
        winner = _cell_of(tree, 2016, "hybrid_winner")
        assert winner == "Doctored Winner" != _cell_of(tree, 2016, "pv_winner")
        assert strip["hovertext"] == [
            labels.C2_HYBRID_DIFFERENT_HOVER.format(year=2016, winner=winner)
        ]
        assert "proposal" in strip["hovertext"][0]
        assert (
            _named_or_none(c2_figure(render_c2()), labels.C2_HYBRID_DIFFERENT_KEY)
            is None
        )

    def test_the_strip_hover_names_the_table_s_winner(self) -> None:
        tree = render_c2()
        trace = named(c2_figure(tree), labels.C2_PV_DIFFERENT_KEY)
        for year, hover in zip(trace["x"], trace["hovertext"], strict=True):
            assert hover == labels.C2_PV_DIFFERENT_HOVER.format(
                year=year, winner=_cell_of(tree, year, "pv_winner")
            )
            assert _cell_of(tree, year, "pv_winner") == ITEMS[year]["pv_winner"]

    def test_both_strips_drawn_keep_the_chart_drawn(self) -> None:
        """B2, T3: with a hybrid disagreement too, both strip series draw, each its own
        symbol, and the figure passes the chart rules."""
        summary = _with(
            **{
                "2016.hybrid_flip": True,
                "2016.hybrid_winner": "Hillary Clinton",
                "2016.hybrid_winner_slug": "hillary-clinton",
            }
        )
        tree = render_c2(summary)
        figure = c2_figure(tree)
        pv = named(figure, labels.C2_PV_DIFFERENT_KEY)
        hybrid = named(figure, labels.C2_HYBRID_DIFFERENT_KEY)
        assert hybrid["x"] == [2016]
        assert pv["marker"]["symbol"] != hybrid["marker"]["symbol"]
        assert charts.figure_problems(figure) == []
        caption = _caption(tree)
        assert labels.C2_PV_DIFFERENT_NOTE in caption
        assert labels.C2_HYBRID_DIFFERENT_NOTE in caption
        assert labels.C2_HYBRID_DIFFERENT_NOTE not in _caption(render_c2())

    @pytest.mark.parametrize(
        "changes",
        [
            {"2000.pv_flip": 1},
            {"2000.pv_flip": "yes"},
            {"2016.hybrid_flip": 0},
            # A True flag naming the leader as the different candidate (C4), both methods.
            {"2004.pv_flip": True},
            {"2004.hybrid_flip": True},
            # A flag that disagrees with its winner (#564's review, cr.2): False with
            # another winner, null with a winner, True with no winner.
            {"2000.pv_flip": False},
            {"2000.pv_flip": None},
            {"2016.pv_winner_slug": None},
            {"2016.pv_winner_slug": "  "},
            {"2016.hybrid_flip": None},
            {"1972.pv_winner_slug": "richard-m-nixon"},
            # The leader is not the flags' baseline (C4).
            {"2016.ec_winner_slug": "hillary-clinton"},
        ],
    )
    def test_a_flag_c2_cannot_read_degrades_the_section(
        self, changes: dict[str, Any]
    ) -> None:
        tree = render_c2(_with(**changes))
        assert tree.id == PAGE_ID
        assert find(tree, C2) is None and find(tree, LEADERS) is None
        assert find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is not None

    def test_a_missing_year_level_field_degrades_the_section(self) -> None:
        """g.5: 2016's item, chosen by its year, without ``hybrid_winner``."""
        summary = copy.deepcopy(SUMMARY)
        (item,) = [i for i in summary["elections"] if i["year"] == 2016]
        del item["hybrid_winner"]
        tree = render_c2(summary)
        assert tree.id == PAGE_ID
        assert find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is not None

    def test_the_recording_s_flags_agree_with_its_winners(self) -> None:
        """The premise of the strict rule (cr.2): every recorded year passes it."""
        for year, item in ITEMS.items():
            for flip, winner in MOD["FLIP_WINNERS"]:
                assert MOD["_agrees"](
                    item[flip], item[winner], LEADER[year]["candidate_slug"]
                ), (year, flip)

    @pytest.mark.parametrize(
        ("value", "label", "symbol"),
        [
            (None, labels.C2_NO_FIGURE, "circle-open"),
            ("zz", labels.UNRECOGNIZED, "square-open"),
        ],
    )
    @pytest.mark.parametrize("field", ["pv_share", "hybrid_score"])
    def test_an_in_window_share_with_no_figure_is_a_marker(
        self, field: str, value: Any, label: str, symbol: str
    ) -> None:
        summary = copy.deepcopy(SUMMARY)
        (row,) = [
            r for r in summary["data"] if r["year"] == 1992 and r["electoral_rank"] == 1
        ]
        row[field] = value
        tree = render_c2(summary)
        figure = c2_figure(tree)
        (marks,) = markers(figure)
        assert (marks["name"], marks["marker"]["symbol"]) == (label, symbol)
        assert marks["x"] == [1992] and marks["y"] == [0]
        cell = _cell_of(tree, 1992, field)
        assert cell in marks["hovertext"][0]
        name = (
            labels.LABELS["pv_share"] if field == "pv_share" else labels.C2_HYBRID_KEY
        )
        assert 1992 not in named(figure, name)["x"]
        if field == "pv_share":  # no triangle, so no connector that year
            assert 1992 not in figure["data"][0]["x"]
        assert labels.C2_NO_SHARE_NOTE in _caption(tree)
        assert charts.figure_problems(figure) == []

    def test_the_bands_come_from_coverage(self) -> None:
        """T5, g.4: the band before the window, its label and caption sentence on the
        recording; with the index's window doctored to 1980–2016 (and its flags with it,
        which the page requires, cr.8), the band before moves, a band after appears with
        its label, its caption sentence and the raised top margin, and 1976's cells and
        marks follow the same rule."""

        def bands(tree: Any) -> list[dict[str, Any]]:
            return [
                s for s in c2_figure(tree)["layout"]["shapes"] if s["type"] == "rect"
            ]

        def notes(tree: Any) -> list[str]:
            return [a["text"] for a in c2_figure(tree)["layout"]["annotations"]]

        served = render_c2()
        before = [y for y in YEARS if y < WINDOW[0]]
        low, high = components.year_edges(list(YEARS), before[0], before[-1])
        (band,) = bands(served)
        assert (band["x0"], band["x1"]) == (low, high)
        assert band["fillcolor"] == "var(--chart-grid)"
        assert labels.C5_BEFORE_BAND.format(pv_year_min=WINDOW[0]) in notes(served)
        assert labels.C2_BEFORE_NOTE.format(pv_year_min=WINDOW[0]) in _caption(served)
        assert labels.C5_AFTER_NOTE.format(pv_year_max=WINDOW[1]) not in _caption(
            served
        )
        top = over_time.TOP_PX + over_time.BAND_LABEL_PX
        assert c2_figure(served)["layout"]["margin"] == {"t": top}
        index = copy.deepcopy(BODY)
        index["meta"]["provenance"]["coverage"].update(
            pv_year_min=1980, pv_year_max=2016
        )
        for row in index["data"]:
            row["has_popular_vote"] = 1980 <= row["year"] <= 2016
        moved = render_c2(index=index)
        first, last = bands(moved)
        early = [y for y in YEARS if y < 1980]
        late = [y for y in YEARS if y > 2016]
        assert (first["x0"], first["x1"]) == components.year_edges(
            list(YEARS), early[0], early[-1]
        )
        assert (last["x0"], last["x1"]) == components.year_edges(
            list(YEARS), late[0], late[-1]
        )
        assert labels.C5_AFTER_BAND.format(pv_year_max=2016) in notes(moved)
        assert labels.C2_BEFORE_NOTE.format(pv_year_min=1980) in _caption(moved)
        assert labels.C5_AFTER_NOTE.format(pv_year_max=2016) in _caption(moved)
        assert c2_figure(moved)["layout"]["margin"] == {
            "t": over_time.TOP_PX + 2 * over_time.BAND_LABEL_PX
        }
        assert _cell_of(moved, 1976, "pv_share") == labels.NOT_APPLICABLE
        triangles = named(c2_figure(moved), labels.LABELS["pv_share"])["x"]
        assert 1976 not in triangles and 2020 not in triangles and 1980 in triangles

    @pytest.mark.parametrize(
        "body", [_leader_before(1860), _leader_twice(1860), _second_leader()]
    )
    def test_a_tie_at_rank_1_is_refused_as_a_tie(self, body: dict[str, Any]) -> None:
        """Class B (#564): the tie refusal itself, not a later check that a row placed
        last happens to trip."""
        with pytest.raises(TypeError, match="two leaders"):
            MOD["leaders"](copy.deepcopy(BODY), body, HAS_PV)

    def test_each_series_draws_at_its_size(self) -> None:
        """Class B (#564): a star and a triangle drawn larger than the circle show
        around it where they coincide; a hand-written literal, not the page's table."""
        figure = c2_figure(render_c2())
        sizes = {
            t["name"]: t["marker"]["size"] for t in figure["data"] if "marker" in t
        }
        assert sizes == {
            labels.LABELS["ec_share_full"]: 7,
            labels.LABELS["pv_share"]: 8,
            labels.C2_HYBRID_KEY: 9,
            labels.C2_PV_DIFFERENT_KEY: 9,
        }

    def test_the_drawn_symbols_are_the_table_s_and_distinct(self) -> None:
        """g.1: read off the drawn traces, not the module's constants."""
        figure = c2_figure(
            render_c2(
                _with(
                    **{
                        "2016.hybrid_flip": True,
                        "2016.hybrid_winner": "Doctored Winner",
                        "2016.hybrid_winner_slug": "doctored-winner",
                    }
                )
            )
        )
        drawn = {
            t["name"]: t["marker"]["symbol"] for t in figure["data"] if "marker" in t
        }
        assert drawn == {
            labels.LABELS["ec_share_full"]: "circle",
            labels.LABELS["pv_share"]: "triangle-up",
            labels.C2_HYBRID_KEY: "star",
            labels.C2_PV_DIFFERENT_KEY: "hexagon",
            labels.C2_HYBRID_DIFFERENT_KEY: "pentagon",
        }
        assert len(set(drawn.values())) == len(drawn)

    def test_an_unrecognized_winner_s_strip_hover_keeps_its_line_break(self) -> None:
        """cr.1: the note's ``<br>`` is added after escaping, never escaped itself."""
        tree = render_c2(_with(**{"2016.pv_winner": 5}))
        trace = named(c2_figure(tree), labels.C2_PV_DIFFERENT_KEY)
        (hover,) = [
            h for x, h in zip(trace["x"], trace["hovertext"], strict=True) if x == 2016
        ]
        assert f"{labels.UNRECOGNIZED}<br>{labels.UNRECOGNIZED_NOTE}" in hover
        assert "&lt;" not in hover

    def test_a_year_missing_two_marks_is_one_marker_with_both_hovers(self) -> None:
        """cr.5: one point per label and year, so each hover is reachable."""
        summary = copy.deepcopy(SUMMARY)
        (row,) = [
            r for r in summary["data"] if r["year"] == 1992 and r["electoral_rank"] == 1
        ]
        row["pv_share"] = None
        row["hybrid_score"] = None
        figure = c2_figure(render_c2(summary))
        (marks,) = markers(figure)
        assert marks["x"] == [1992] and marks["ids"] == ["1992"]
        (hover,) = marks["hovertext"]
        assert "Popular-vote share: " in hover and "Hybrid score: " in hover
        assert charts.figure_problems(figure) == []

    def test_the_majority_label_sits_over_no_mark_left_of_the_window(self) -> None:
        """cr.4's tripwire (D108 residual): the label starts at the second served year
        and runs about a century to its right at 360 px; no mark but a circle may sit
        below the line there. A wider popular-vote window (#565, #566) that puts one
        there fails this, which re-placing the label must answer."""
        span = 100  # years: the three-line label's width at 360 px, generously
        figure = c2_figure(render_c2())
        (note,) = [
            a
            for a in figure["layout"]["annotations"]
            if a["text"] == labels.C2_MAJORITY_LINE
        ]
        start = note["x"]
        for t in figure["data"]:
            if "marker" not in t or t["name"] == labels.LABELS["ec_share_full"]:
                continue
            for x, y in zip(t["x"], t["y"], strict=True):
                assert not (start <= x <= start + span and y < 0.5), (t["name"], x)

    def test_c2_paints_only_measured_tokens(self) -> None:
        """g.8: every color C2's figure paints is one the theme tests hold to its ratio
        on the page and on the band's fill; the majority label is in the text color."""
        from tests.unit.test_dashboard_theme import CHART_MARKS

        figure = c2_figure(
            render_c2(
                _with(
                    **{
                        "2016.hybrid_flip": True,
                        "2016.hybrid_winner": "Doctored Winner",
                        "2016.hybrid_winner_slug": "doctored-winner",
                    }
                )
            )
        )
        painted: set[str] = set()
        for t in figure["data"]:
            for part in ("marker", "line"):
                if part in t:
                    painted.add(t[part]["color"])
        for shape in figure["layout"]["shapes"]:
            painted.add(shape["line"]["color"])
        for note in figure["layout"]["annotations"]:
            assert note["font"]["color"] == "var(--text)"
        tokens = {c.removeprefix("var(").removesuffix(")") for c in painted}
        assert tokens <= {*CHART_MARKS, "--text"}, tokens
        fills = {s.get("fillcolor") for s in figure["layout"]["shapes"]} - {None}
        assert fills == {"var(--chart-grid)"}

    def test_c2_s_shares_read_as_t3_s(self) -> None:
        """g.7: C2's leader cells for the popular-vote share and hybrid score are T3's
        own for the same row and year (one rule, ``labels.national_pv``)."""
        tree = render_c2()
        for year in RECONCILED:
            cells = NATION_CELLS(rank1(year), HAS_PV[year])
            for field in ("pv_share", "hybrid_score"):
                assert _cell_of(tree, year, field) == cells[field], (year, field)

    def test_the_hybrid_is_labeled_the_project_s_proposal(self) -> None:
        """AC5: its trace name and key, its hover, the caption and the table note."""
        tree = render_c2()
        figure = c2_figure(tree)
        star = named(figure, labels.C2_HYBRID_KEY)
        assert star["showlegend"] is True and "proposal" in star["name"]
        assert all("proposal" in hover for hover in star["hovertext"])
        assert labels.C2_HYBRID_MARK in _caption(tree)
        assert "proposal" in labels.C2_HYBRID_MARK
        assert labels.C2_HYBRID_TABLE_NOTE in texts(tree)

    def test_the_caption_s_plurality_example_is_the_served_1992_leader(self) -> None:
        """AC6, M3: the example is the leader (who also won the popular vote) and its
        figure the table's cell for the served share."""
        item, leader = ITEMS[1992], LEADER[1992]
        assert (
            item["pv_winner_slug"] == item["ec_winner_slug"] == leader["candidate_slug"]
        )
        assert leader["pv_share"] < 0.5
        text = labels.C2_PLURALITY_NOTE
        assert f"{leader['candidate']} did in 1992 with" in text
        assert f"with {labels.share(leader['pv_share'])}." in text
        assert text in _caption(render_c2())

    def test_the_caption_s_shape_words_name_the_traces_symbols(self) -> None:
        words = {
            labels.C2_EC_MARK: ("circle", MOD["_C2_EC_SYMBOL"]),
            labels.C2_PV_MARK: ("solid triangle", MOD["_C2_PV_SYMBOL"]),
            labels.C2_HYBRID_MARK: ("star", MOD["_C2_HYBRID_SYMBOL"]),
            labels.C2_PV_DIFFERENT_NOTE: ("hexagon", MOD["_C2_PV_DIFFERENT_SYMBOL"]),
            labels.C2_HYBRID_DIFFERENT_NOTE: (
                "pentagon",
                MOD["_C2_HYBRID_DIFFERENT_SYMBOL"],
            ),
        }
        plotly = {
            "circle": "circle",
            "solid triangle": "triangle-up",
            "star": "star",
            "hexagon": "hexagon",
            "pentagon": "pentagon",
        }
        for sentence, (word, symbol) in words.items():
            assert f" {word} " in sentence, sentence
            assert plotly[word] == symbol

    def test_the_new_columns_reconcile_to_n1_on_every_year(self) -> None:
        """AC4: appended at the end, each cell from the served value by T3's rule (the
        shares) or the panel's (the winners)."""
        assert MOD["LEADER_FIELDS"][-4:] == (
            "pv_share",
            "hybrid_score",
            "pv_winner",
            "hybrid_winner",
        )
        tree = render_c2()
        for year in YEARS:
            row, item = LEADER[year], ITEMS[year]
            for field in ("pv_share", "hybrid_score"):
                assert _cell_of(tree, year, field) == labels.national_pv(
                    row[field], HAS_PV[year], True
                ), (year, field)
            applicable = labels.in_pv_window(year, COVERAGE)
            for field in ("pv_winner", "hybrid_winner"):
                assert _cell_of(tree, year, field) == labels.winner(
                    item[field], applicable
                ), (year, field)

    def test_the_table_notes_name_the_methods_and_the_proposal(self) -> None:
        shown = texts(render_c2())
        for note in (
            labels.C2_LEADER_ROW,
            labels.C2_TOOK_OFFICE,
            labels.C2_TABLE_METHODS_NOTE,
            labels.HYBRID_NOTE,
            labels.C2_HYBRID_TABLE_NOTE,
        ):
            assert note in shown


def _unserved() -> dict[str, Any]:
    # A rank-2 row (1824's Adams), so only the unserved-year check refuses it.
    summary = copy.deepcopy(SUMMARY)
    assert summary["data"][1]["electoral_rank"] == 2  # the premise
    summary["data"].append({**summary["data"][1], "year": 1826})
    return summary


def _bool_rank() -> dict[str, Any]:
    summary = copy.deepcopy(SUMMARY)
    for row in summary["data"]:
        if row["year"] == 1824 and row["electoral_rank"] == 1:
            row["electoral_rank"] = True
    return summary


MALFORMED = {
    "a served year with no elections item": _without(1876),
    "two rank-1 rows in a year": _second_leader(),
    "a second rank-1 row before the leader": _leader_before(1860),
    "the leader's row twice": _leader_twice(1860),
    "a row for a year not served": _unserved(),
    "a served year with two elections items": _second_item(),
    "a rank that is a bool": _bool_rank(),
    "data that is not a list": {**SUMMARY, "data": {}},
    "no elections key": {k: v for k, v in SUMMARY.items() if k != "elections"},
    "a year that is a string": {
        **SUMMARY,
        "elections": [{**SUMMARY["elections"][0], "year": "1824"}]
        + SUMMARY["elections"][1:],
    },
    "not an object": [],
}


def _shape_defects() -> dict[str, Any]:
    """#487's scope ruling: every key of N1's body itself, its ``meta``, its first row,
    first ``elections`` item, ``meta.provenance`` and its ``coverage``, deleted and set
    to a wrong type, so no N1 defect the section can raise on is left untested,
    whichever piece reads the key (the top level and ``meta``: round 2's finding)."""
    cases: dict[str, Any] = {}
    places = {
        "N1": lambda b: b,
        "meta": lambda b: b["meta"],
        "data[0]": lambda b: b["data"][0],
        "elections[0]": lambda b: b["elections"][0],
        "meta.provenance": lambda b: b["meta"]["provenance"],
        "meta.provenance.coverage": lambda b: b["meta"]["provenance"]["coverage"],
    }
    for where, at in places.items():
        for key in at(SUMMARY):
            for change, value in (("deleted", None), ("None", None), ("[]", [])):
                body = copy.deepcopy(SUMMARY)
                if change == "deleted":
                    del at(body)[key]
                else:
                    at(body)[key] = value
                cases[f"{where}.{key} {change}"] = body
    return cases


SHAPE_DEFECTS = _shape_defects()


class TestC2Validation:
    def test_a_row_for_a_year_not_served_is_refused_by_its_own_check(self) -> None:
        with pytest.raises(TypeError, match="not served"):
            MOD["leaders"](copy.deepcopy(BODY), _unserved(), HAS_PV)

    @pytest.mark.parametrize("name", SHAPE_DEFECTS)
    def test_no_n1_defect_reaches_the_page(self, name: str) -> None:
        """The page's success marker and heading always render; C2's section is whole
        (a key the section never reads) or shows only its own sentence."""
        tree = render_c2(SHAPE_DEFECTS[name])
        assert tree.id == PAGE_ID
        assert of_type(tree, "H1")[0].children == MOD["HEADING"]
        whole = find(tree, C2) is not None and find(tree, LEADERS) is not None
        degraded = find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is not None
        assert whole != degraded, name
        if degraded:
            assert find(tree, C2) is None and find(tree, LEADERS) is None

    def test_the_shape_defects_reach_the_table_s_own_reads(self) -> None:
        """Non-vacuity: the cases include the two the table alone reads (#487, cr.1)."""
        for name in (
            "data[0].candidate_slug deleted",
            "meta.provenance.coverage deleted",
        ):
            tree = render_c2(SHAPE_DEFECTS[name])
            assert find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is not None, name

    @pytest.mark.parametrize("name", MALFORMED)
    def test_a_malformed_body_is_refused(self, name: str) -> None:
        with pytest.raises((TypeError, KeyError)):
            MOD["leaders"](copy.deepcopy(BODY), copy.deepcopy(MALFORMED[name]), HAS_PV)

    def test_the_recording_is_accepted(self) -> None:
        leaders = MOD["leaders"](copy.deepcopy(BODY), copy.deepcopy(SUMMARY), HAS_PV)
        assert [r["year"] for r in leaders] == YEARS
        assert all(r["electoral_rank"] == 1 for r in leaders)
        assert leaders[0]["ec_determinative"] is False

    def test_an_index_year_outside_its_span_is_refused(self) -> None:
        index = copy.deepcopy(BODY)
        index["meta"]["provenance"]["coverage"]["year_max"] = 2020
        with pytest.raises(TypeError):
            MOD["leaders"](index, copy.deepcopy(SUMMARY), HAS_PV)

    @pytest.mark.parametrize("name", MALFORMED)
    def test_a_malformed_body_degrades_only_the_section(self, name: str) -> None:
        tree = render_c2(MALFORMED[name])
        assert tree.id == PAGE_ID  # the page's success marker, outside C2's try
        assert of_type(tree, "H1")[0].children == MOD["HEADING"]
        assert find(tree, C2) is None and find(tree, LEADERS) is None
        unavailable = find(tree, MOD["LEADER_UNAVAILABLE_ID"])
        assert unavailable.children == MOD["C2_UNAVAILABLE"]
        assert components.UNAVAILABLE_MESSAGE not in texts(tree)
        assert "isn't responding" not in MOD["C2_UNAVAILABLE"]


class TestC2Degraded:
    def test_an_unavailable_n1_leaves_the_page_and_retries_once_per_render(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def down(path: str) -> api.Response:
            raise api.ApiUnavailable("down")

        calls, bucket = n1_client(monkeypatch, down)
        for _ in range(2):
            calls.clear()
            ids = routed_ids(route("/elections/majority", ""))
            assert PAGE_ID in ids
            assert MOD["LEADER_UNAVAILABLE_ID"] in ids
            assert C2 not in ids and LEADERS not in ids
            # One fill per render: N1, which failed, and nothing else (D096(d)).
            assert calls == [api.SUMMARY_PATH]

    def test_a_malformed_n1_from_the_api_leaves_the_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        n1_client(
            monkeypatch,
            lambda path: api.Response(body=_second_leader(), version=VERSION),
        )
        tree = PAGE["layout"]()
        assert tree.id == PAGE_ID
        assert find(tree, MOD["LEADER_UNAVAILABLE_ID"]) is not None
        assert find(tree, C2) is None

    def test_the_index_down_degrades_the_whole_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Down:
            def view(self) -> Any:
                raise api.ApiUnavailable("down")

        monkeypatch.setattr(api, "CLIENT", Down())
        tree = PAGE["layout"]()
        assert components.UNAVAILABLE_MESSAGE in texts(tree)
        assert find(tree, C2) is None and find(tree, PAGE_ID) is None
        assert of_type(tree, "H1")[0].children == MOD["HEADING"]
        assert MOD["LEDE"] in texts(tree)


class TestN1Fixture:
    """The N1 recording agrees with the per-year recordings of the same snapshot."""

    def test_same_snapshot_as_the_index(self) -> None:
        assert SUMMARY["meta"]["provenance"] == BODY["meta"]["provenance"]

    @pytest.mark.parametrize("year", RECONCILED)
    def test_each_recorded_year_matches(self, year: int) -> None:
        body = RECORDED[f"/v1/elections/{year}"]
        (item,) = [e for e in SUMMARY["elections"] if e["year"] == year]
        assert item == body["election"]
        rows = [r for r in SUMMARY["data"] if r["year"] == year]

        def key(r: dict[str, Any]) -> tuple[int, str]:
            return r["electoral_rank"], r["candidate_slug"]

        # Order-insensitive: the year recordings predate 0.8.0's order within ties, and
        # this checks content; C2 reads only each year's rank-1 row.
        assert sorted(rows, key=key) == sorted(body["summary"], key=key)


#: Malformed popular-vote windows and flags in ``/v1/elections`` (#564's review, cr.3,
#: cr.8, g.3): C2's page checks them as the page's, so each degrades the whole page.
BAD_MAJORITY_INDEXES = {
    "window bound missing": lambda b: b["meta"]["provenance"]["coverage"].pop(
        "pv_year_min"
    ),
    "window bound null": lambda b: b["meta"]["provenance"]["coverage"].update(
        pv_year_max=None
    ),
    "window bound a bool": lambda b: b["meta"]["provenance"]["coverage"].update(
        pv_year_min=True
    ),
    "window bound a string": lambda b: b["meta"]["provenance"]["coverage"].update(
        pv_year_min="1976"
    ),
    "window reversed": lambda b: b["meta"]["provenance"]["coverage"].update(
        pv_year_min=2024, pv_year_max=1976
    ),
    "has_popular_vote not a bool": lambda b: b["data"][-1].update(has_popular_vote=1),
    "has_popular_vote outside the window": lambda b: b["data"][0].update(
        has_popular_vote=True
    ),
    "no popular vote inside the window": lambda b: b["data"][-1].update(
        has_popular_vote=False
    ),
}


@pytest.mark.parametrize("name", list(BAD_MAJORITY_INDEXES))
def test_a_bad_popular_vote_window_is_the_page_s_defect(name: str) -> None:
    index = copy.deepcopy(BODY)
    BAD_MAJORITY_INDEXES[name](index)
    with pytest.raises((KeyError, TypeError)):
        MOD["render"](index, copy.deepcopy(SUMMARY))


#: Malformed ``/v1/elections`` bodies (#562's review, cr.1): the index's own defect.
BAD_INDEXES = {
    "data empty": lambda b: b.update(data=[]),
    "data null": lambda b: b.update(data=None),
    "a string year": lambda b: b["data"][0].update(year="1824"),
}


@pytest.mark.parametrize(
    "module", ["pages.elections_majority", "pages.elections_over_time"]
)
@pytest.mark.parametrize("name", list(BAD_INDEXES))
def test_a_malformed_index_degrades_the_whole_subpage(
    monkeypatch: pytest.MonkeyPatch, module: str, name: str
) -> None:
    """An index defect is the page's, never a section's (cr.1): the layout shows the
    degraded state, with no success marker and no section links."""
    page = dash.page_registry[module]
    index = copy.deepcopy(BODY)
    BAD_INDEXES[name](index)

    class View:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

        def get(self, path: str) -> Any:
            return index if path == api.ELECTIONS_PATH else copy.deepcopy(SUMMARY)

    class Client:
        def view(self) -> Any:
            return View()

    monkeypatch.setattr(api, "CLIENT", Client())
    tree = page["layout"]()
    assert components.UNAVAILABLE_MESSAGE in texts(tree), name
    assert find(tree, page["success"]) is None, name
    assert find(tree, "elections-sections") is None, name


def test_the_download_names_this_page_as_its_view() -> None:
    """Class B at #562's acceptance gate: the CSV's view URL is this page's."""
    link = find(render_c2(), f"{LEADERS}-csv")
    text = urllib.parse.unquote(link.href)
    assert "explore.us-presidential-election-center.org/elections/majority" in text
