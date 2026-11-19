"""The Electoral College majority page, ``/elections/majority``: chart C2 and its
companion table (#434, D096), on their own page since #562 (D107).

Offline, against the recorded ``/v1/elections`` and N1 fixtures, through the helpers
and the autouse offline process client of ``test_dashboard_app.py``.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import dash
import pytest

from explore import api, charts, components, labels
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


def render_c2(
    summary: Any = None, index: Any = None, query: dict[str, Any] | None = None
) -> Any:
    """The page for the index and an N1 body (the recording unless given). ``query``
    is ignored: the page has no filter (D096(b))."""
    return MOD["render"](
        copy.deepcopy(BODY if index is None else index),
        copy.deepcopy(SUMMARY if summary is None else summary),
    )


def c2_figure(tree: Any) -> dict[str, Any]:
    (store,) = [
        node
        for node in of_type(tree, "Store")
        if isinstance(getattr(node, "id", None), dict) and node.id.get("chart") == C2
    ]
    figure: dict[str, Any] = store.data
    return figure


#: The hover's share line, whose cell is what a point's text label carried before
#: #558 (D104): the companion table's cell for the share.
C2_SHARE_LINE = re.compile(r"<br>Electoral share \(counted ÷ appointed\): (.*?)<br>")


def hover_share(hover: str) -> str:
    """The share cell a C2 hover writes (:data:`C2_SHARE_LINE`), its note dropped."""
    match = C2_SHARE_LINE.search(hover)
    assert match is not None, hover
    return match.group(1).split("<br>")[0]


def points(tree: Any) -> dict[str, tuple[Any, str, str]]:
    """Each year's main point: its share (y), the share cell its hover writes, and the
    hover, by the year (the trace's ids). Each point sits at its year (x), which the
    ids repeat as text (#558, D104)."""
    trace = c2_figure(tree)["data"][0]
    assert trace["name"] == labels.LABELS["ec_share_full"]
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
        assert [str(y) for y in YEARS] == figure["data"][0]["ids"]
        # Each point at its year on the numeric year axis along the bottom (#558, D104),
        # oldest at the left.
        assert figure["data"][0]["x"] == list(YEARS)
        assert figure["layout"]["xaxis"] == components.year_axis(YEARS)
        assert figure["layout"]["xaxis"]["type"] == "linear"
        coverage = BODY["meta"]["provenance"]["coverage"]
        assert (YEARS[0], YEARS[-1]) == (coverage["year_min"], coverage["year_max"])
        assert len(figure["data"]) == 1  # no marker: every leader has a share
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
            (None, labels.C1_NO_SHARE),
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
        (marks,) = figure["data"][1:]
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
        assert caption.children[0].endswith(labels.C2_TOOK_OFFICE)
        assert len(c2_figure(tree)["data"]) == 1  # the premise: no marker drawn

    def test_the_majority_line_is_a_dashed_shape_at_half(self) -> None:
        layout = c2_figure(render_c2())["layout"]
        (line,) = layout["shapes"]
        # Horizontal across the plot at half (#558, D104).
        assert (line["yref"], line["y0"], line["y1"]) == ("y", 0.5, 0.5)
        assert (line["xref"], line["x0"], line["x1"]) == ("paper", 0, 1)
        assert line["line"]["dash"] == "dash"
        # One label, just below the line at the right (owner, #558's plan gate).
        (note,) = layout["annotations"]
        assert note["text"] == labels.C2_MAJORITY_LINE
        assert (note["xref"], note["x"], note["xanchor"]) == ("paper", 1, "right")
        assert (note["yref"], note["y"], note["yanchor"]) == ("y", 0.5, "top")
        assert layout["yaxis"]["range"] == [0, 1]
        assert layout["showlegend"] is False  # no marker, so no key

    def test_the_title_is_page_text(self) -> None:
        assert find(render_c2(), f"{C2}-title").children == labels.C2_TITLE

    def test_the_companion_table_holds_the_points_values(self) -> None:
        tree = render_c2()
        rows = leader_rows(tree)
        shown = points(tree)
        assert [r[0] for r in rows] == [str(y) for y in YEARS]
        for row in rows:
            year, candidate, counted, appointed, share, majority, took = row
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
            MOD["leaders"](copy.deepcopy(BODY), _unserved())

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
            MOD["leaders"](copy.deepcopy(BODY), copy.deepcopy(MALFORMED[name]))

    def test_the_recording_is_accepted(self) -> None:
        leaders = MOD["leaders"](copy.deepcopy(BODY), copy.deepcopy(SUMMARY))
        assert [r["year"] for r in leaders] == YEARS
        assert all(r["electoral_rank"] == 1 for r in leaders)
        assert leaders[0]["ec_determinative"] is False

    def test_an_index_year_outside_its_span_is_refused(self) -> None:
        index = copy.deepcopy(BODY)
        index["meta"]["provenance"]["coverage"]["year_max"] = 2020
        with pytest.raises(TypeError):
            MOD["leaders"](index, copy.deepcopy(SUMMARY))

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
