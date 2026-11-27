"""The history table on ``/states`` (#641, D123): every state's four history figures
from N2 (``/v1/elections/states``), read on a miss, through
``state_view.states_history`` and worded by ``state_view.history_cell``, the path
and the wording each state's own page uses.

Offline, against the recorded N2, the roster ``/v1/elections/2024`` and the state
histories ``/v1/states/{GA,TX}`` (one snapshot). The registry-wide checks
(``TestRegistryCoverage``, ``TestEveryTable``, ``TestNoRawValues`` with its doctored
N2, the cards) and the D070(b) guard pick the page up; these tests cover what is
particular to the table.
"""

from __future__ import annotations

import copy
import html as html_lib
import json
from pathlib import Path
from typing import Any

import dash
import pytest

from explore import api, charts, export, labels, metrics, state_view
from tests.dashboard_cards import every_card
from tests.unit.test_dashboard_app import (
    RECORDED,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    cached_client,
    component_ids,
    get,
    route,
    routed_ids,
    texts,
    url,
)
from tests.unit.test_dashboard_elections import find, of_type
from tests.unit.test_dashboard_export import body_rows, download, links
from tests.unit.test_dashboard_state import (
    INDEX,
    MOD,
    N2,
    PICKER,
    PICKER_MOD,
    ROSTER,
    SERVED,
    render_all,
)

TABLE_ID = PICKER_MOD["HISTORY_TABLE_ID"]
UNAVAILABLE_ID = PICKER_MOD["HISTORY_UNAVAILABLE_ID"]
GLOSSARY_ID = PICKER_MOD["HISTORY_GLOSSARY_ID"]
N2_PATH = api.ELECTION_STATES_PATH
#: The roster's states (one row per candidate and state) in the page's order: by what
#: each link shows (the name, or the code where the name is blank).
ROSTER_STATES = [
    usps
    for usps, _ in sorted(
        state_view.roster(ROSTER)[1].items(),
        key=lambda kv: PICKER_MOD["link_text"](*kv),
    )
]


def n2() -> dict[str, Any]:
    return copy.deepcopy(RECORDED[N2_PATH])


def page(n2_body: Any = None, roster: Any = None, metric: str | None = None) -> Any:
    """The page body for the recorded roster and ``n2_body`` (the recording unless
    given; pass ``False`` for an unread N2), C11 showing ``metric`` (the default
    unless given)."""
    body = n2() if n2_body is None else (None if n2_body is False else n2_body)
    content, _chooser = PICKER_MOD["render"](
        copy.deepcopy(ROSTER) if roster is None else roster,
        2024,
        body,
        copy.deepcopy(INDEX),
        metric or PICKER_MOD["DEFAULT_METRIC"],
    )
    return content


def table_rows(tree: Any) -> dict[str, list[str]]:
    """The table's rows as ``{usps: [state cell, four figure cells]}``, each cell's
    text joined."""
    found: dict[str, list[str]] = {}
    for tr in body_rows(tree, TABLE_ID):
        (link,) = of_type(tr.children[0], "Link")
        usps = link.href.removeprefix("/state/")
        found[usps] = ["".join(texts(td)) for td in tr.children]
    return found


def figures_of(usps: str) -> dict[str, str]:
    """The state page's four history figures for ``usps``, by metric key, as text."""
    content, _, _ = render_all(usps=usps)
    return {
        key: "".join(texts(find(content, MOD["METRIC_IDS"][key])))
        for key in state_view.HISTORY_KEYS
    }


def history(body: Any) -> dict[str, Any]:
    return state_view.states_history(body, list(ROSTER_STATES), set(SERVED), N2_PATH)


def drop(body: dict[str, Any], usps: str, year: int | None = None) -> None:
    """Remove ``usps``' N2 rows, or its row of ``year``."""
    body["data"] = [
        r
        for r in body["data"]
        if not (r["state_usps"] == usps and (year is None or r["year"] == year))
    ]


def first_row(body: dict[str, Any], usps: str) -> dict[str, Any]:
    return min(
        (r for r in body["data"] if r["state_usps"] == usps), key=lambda r: r["year"]
    )


def middle_year(usps: str) -> int:
    years: list[int] = sorted(r["year"] for r in N2["data"] if r["state_usps"] == usps)
    return years[len(years) // 2]


# --- the table ------------------------------------------------------------------------


class TestStatesTable:
    def test_every_state_and_dc_has_a_row_of_four_figures_linked_by_name(self) -> None:
        tree = page()
        rows = table_rows(tree)
        names = {r["state_usps"]: r["state"] for r in ROSTER["data"]}
        assert len(rows) == 51
        assert set(rows) == set(names)
        # In the roster's order by name, each linked to its history.
        assert list(rows) == ROSTER_STATES
        for usps, cells in rows.items():
            assert len(cells) == 5
            assert cells[0] == names[usps]
            assert labels.UNRECOGNIZED not in cells
            assert labels.UNAVAILABLE_CELL not in cells
        assert PICKER["success"] in component_ids(tree)

    def test_the_headers_are_the_spec_s(self) -> None:
        table = find(page(), TABLE_ID)
        headers = ["".join(texts(th)) for th in of_type(table, "Th")]
        assert headers == [
            labels.LABELS["state"],
            *(labels.STATES_HISTORY_HEADERS[k] for k in state_view.HISTORY_KEYS),
        ]

    @pytest.mark.parametrize("usps", ["GA", "TX"])
    def test_a_state_s_cells_equal_its_own_page_s_figures(self, usps: str) -> None:
        # AC2: the table's cells, from N2, against the state page's figures, from
        # /v1/states/{usps}, compared as rendered text.
        cells = dict(
            zip(state_view.HISTORY_KEYS, table_rows(page())[usps][1:], strict=True)
        )
        figures = figures_of(usps)
        for key in state_view.HISTORY_KEYS:
            assert figures[key].startswith(cells[key]), (key, cells[key], figures[key])
        # The value half exactly: the elections count, the first year and the change
        # are the page's value; the popular-vote cell adds its N.
        content, _, _ = render_all(usps=usps)
        for key in (
            "state_elections_count",
            "state_first_election",
            "state_electors_change",
        ):
            (value,) = [
                s
                for s in of_type(find(content, MOD["METRIC_IDS"][key]), "Span")
                if getattr(s, "className", None) == "metric-value"
            ]
            assert cells[key] == value.children
        pv = state_view.history_figures(
            state_view.electors(
                state_view.rows(
                    {"data": [r for r in N2["data"] if r["state_usps"] == usps]},
                    usps,
                    set(SERVED),
                    N2_PATH,
                ),
                set(SERVED),
                usps,
                N2_PATH,
            )
        ).popular_vote
        assert cells["state_pv_elections_count"] == f"{pv.count} of {pv.n}"

    def test_georgia_s_figures_by_value(self) -> None:
        # Hand values from the recording (TestHistoryFiguresOnN2's): 50 elections, the
        # first in 1824, a popular vote in 49 of them.
        cells = table_rows(page())["GA"]
        assert cells[1] == "50"
        assert cells[2] == "1824"
        assert cells[3] == "49 of 50"

    def test_a_refused_state_reads_not_available_alone_with_its_note(self) -> None:
        body = n2()
        drop(body, "GA", middle_year("GA"))  # a gap after its first election
        tree = page(body)
        rows = table_rows(tree)
        assert rows["GA"][1:] == [labels.UNAVAILABLE_CELL] * 4
        clean = table_rows(page())
        assert {u: c for u, c in rows.items() if u != "GA"} == {
            u: c for u, c in clean.items() if u != "GA"
        }
        notes = [
            "".join(texts(p))
            for p in of_type(tree, "P")
            if getattr(p, "className", None) == "note"
        ]
        assert notes[:2] == [
            PICKER_MOD["STATES_HISTORY_UNAVAILABLE_NOTE"],
            PICKER_MOD["STATES_HISTORY_DOWNLOAD_NOTE"],
        ]
        # The row stays in the download, every figure blank.
        file = download(tree, TABLE_ID)
        (ga,) = [r for r in file.rows if r["state_usps"] == "GA"]
        assert [ga[k] for k in state_view.HISTORY_VALUE_KEYS] == [""] * 5

    def test_with_no_refused_state_only_the_download_note_shows(self) -> None:
        notes = [
            "".join(texts(p))
            for p in of_type(page(), "P")
            if getattr(p, "className", None) == "note"
        ]
        assert PICKER_MOD["STATES_HISTORY_UNAVAILABLE_NOTE"] not in notes
        assert PICKER_MOD["STATES_HISTORY_DOWNLOAD_NOTE"] in notes

    def test_the_download_carries_the_figures_as_raw_values(self) -> None:
        file = download(page(), TABLE_ID)
        assert file.header == ["state", "state_usps", *state_view.HISTORY_VALUE_KEYS]
        assert len(file.rows) == 51
        (ga,) = [r for r in file.rows if r["state_usps"] == "GA"]
        assert ga["state_elections_count"] == "50"
        assert ga["state_first_election"] == "1824"
        assert (ga["state_pv_elections_count"], ga["state_pv_elections_n"]) == (
            "49",
            "50",
        )
        assert ga["state_electors_change"] == str(
            state_view.history_values(history(n2())["GA"])["state_electors_change"]
        )
        # A fall is a plain "-", never the page's minus sign (D123).
        changes = [int(r["state_electors_change"]) for r in file.rows]
        assert min(changes) < 0
        assert labels.MINUS_SIGN not in file.raw.decode("utf-8")
        # Its own last line in place of NULL_LINE (owner, #641).
        assert file.lines[-1] == PICKER_MOD["STATES_HISTORY_EMPTY_CELL_LINE"]
        assert export.NULL_LINE not in file.lines
        assert PICKER_MOD["STATES_HISTORY_DOWNLOAD_NOTE"] in file.lines

    def test_the_column_name_list_names_the_download_columns(self) -> None:
        glossary = find(page(), GLOSSARY_ID)
        text = " ".join(texts(glossary))
        for key in state_view.HISTORY_VALUE_KEYS:
            assert key in text
        assert "state_usps" not in text

    def test_a_blank_roster_name_links_by_its_code(self) -> None:
        roster = copy.deepcopy(ROSTER)
        for row in roster["data"]:  # one row per candidate in the state
            if row["state_usps"] == "GA":
                row["state"] = "  "
        tree = page(roster=roster)
        assert table_rows(tree)["GA"][0] == "GA"
        # Sorted by what its link shows, the code (#647's review, r1.code-review.10):
        # between Florida and Hawaii, never first.
        order = list(table_rows(tree))
        assert order.index("GA") == order.index("FL") + 1
        assert order[0] == "AL"
        listed = {
            link.href: link.children
            for link in of_type(find(tree, PICKER_MOD["LIST_ID"]), "Link")
        }
        assert listed["/state/GA"] == "GA"

    def test_the_history_card_comes_first_then_the_list(self) -> None:
        tree = page()
        first, second = every_card(tree)
        assert find(first, TABLE_ID) is not None
        assert find(second, PICKER_MOD["LIST_ID"]) is not None


# --- the section degrades alone (AC3) -------------------------------------------------


def _not_a_list(body: dict[str, Any]) -> None:
    body["data"] = "rows"


def _no_rows(body: dict[str, Any]) -> None:
    body["data"] = []


def _not_an_object(body: dict[str, Any]) -> None:
    body["data"][3] = ["GA", 1824]


def _off_roster(body: dict[str, Any]) -> None:
    body["data"][3]["state_usps"] = "ZZ"


def _no_code(body: dict[str, Any]) -> None:
    body["data"][3]["state_usps"] = None


def _no_provenance(body: dict[str, Any]) -> None:
    del body["meta"]["provenance"]


def _every_state_refused(body: dict[str, Any]) -> None:
    for row in body["data"]:
        del row["pv_status"]


BODY_FAULTS = {
    "not a list": _not_a_list,
    "no rows": _no_rows,
    "a row that is not an object": _not_an_object,
    "a code off the roster": _off_roster,
    "no code": _no_code,
    "no provenance": _no_provenance,
    "every state refused": _every_state_refused,
}


class TestStatesTableDegraded:
    def assert_section_degraded(self, tree: Any) -> None:
        ids = component_ids(tree)
        assert UNAVAILABLE_ID in ids
        assert TABLE_ID not in ids
        assert GLOSSARY_ID not in ids
        assert f"{TABLE_ID}-csv" not in ids
        # The rest of the page stays: the list, the success marker, both cards.
        assert PICKER_MOD["LIST_ID"] in ids
        assert PICKER["success"] in ids
        assert "unavailable" not in ids
        assert len(every_card(tree)) == 2
        (sentence,) = [
            p for p in of_type(tree, "P") if getattr(p, "id", None) == UNAVAILABLE_ID
        ]
        assert sentence.children == PICKER_MOD["STATES_HISTORY_UNAVAILABLE"]
        heading = [h.children for h in of_type(every_card(tree)[0], "H2")]
        assert heading == [PICKER_MOD["STATES_HISTORY_HEADING"]]

    def test_an_unread_n2_degrades_only_its_section(self) -> None:
        self.assert_section_degraded(page(False))

    @pytest.mark.parametrize("fault", sorted(BODY_FAULTS))
    def test_a_malformed_n2_degrades_only_its_section(self, fault: str) -> None:
        body = n2()
        BODY_FAULTS[fault](body)
        self.assert_section_degraded(page(body))

    def test_a_failed_n2_fill_degrades_only_its_section_when_routed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Through the layout: the roster is served and N2 answers an error, so the
        # view raises for N2 alone and the inner try keeps the page.
        client, calls, _ = cached_client(monkeypatch)
        real = client._fetch

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            if path == N2_PATH:
                raise api.ApiUnavailable("GET n2: HTTP 503")
            return real(path, timeout)

        monkeypatch.setattr(client, "_fetch", fetch)
        ids = routed_ids(route("/states"))
        assert PICKER["success"] in ids
        assert UNAVAILABLE_ID in ids
        assert TABLE_ID not in ids
        assert PICKER_MOD["LIST_ID"] in ids


# --- the shared function --------------------------------------------------------------


class TestStatesHistory:
    def test_every_roster_state_in_order_with_figures(self) -> None:
        found = history(n2())
        assert list(found) == ROSTER_STATES
        assert all(isinstance(f, state_view.HistoryFigures) for f in found.values())

    # Provenance is the page's read, not the function's (it reads rows only).
    @pytest.mark.parametrize("fault", sorted(set(BODY_FAULTS) - {"no provenance"}))
    def test_a_body_fault_raises(self, fault: str) -> None:
        body = n2()
        BODY_FAULTS[fault](body)
        with pytest.raises(TypeError):
            history(body)

    @pytest.mark.parametrize(
        "fault",
        [
            "a gap",
            "no rows",
            "an unserved year",
            "two statuses in a year",
            "a bad year",
        ],
    )
    def test_a_state_fault_refuses_that_state_alone(self, fault: str) -> None:
        body = n2()
        if fault == "a gap":
            drop(body, "GA", middle_year("GA"))
        elif fault == "no rows":
            drop(body, "GA")
        elif fault == "an unserved year":
            first_row(body, "GA")["year"] = 1825
        elif fault == "a bad year":
            first_row(body, "GA")["year"] = "1824"
        else:
            twin = copy.deepcopy(first_row(body, "GA"))
            twin["pv_status"] = (
                "legislature" if twin["pv_status"] != "legislature" else "popular_vote"
            )
            body["data"].append(twin)
        found = history(body)
        assert found["GA"] is None
        clean = history(n2())
        assert {u: f for u, f in found.items() if u != "GA"} == {
            u: f for u, f in clean.items() if u != "GA"
        }

    def test_an_unrecognized_allotment_is_figures_not_a_refusal(self) -> None:
        body = n2()
        first_row(body, "GA")["state_electoral_votes"] = "many"
        figures = history(body)["GA"]
        assert figures is not None and figures.unrecognized

    @pytest.mark.parametrize("error", [ValueError, AttributeError])
    def test_any_other_exception_propagates(
        self, error: type[Exception], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def rows(*_args: Any) -> Any:
            raise error("x")

        monkeypatch.setattr(state_view, "rows", rows)
        with pytest.raises(error):
            history(n2())

    def test_the_render_reads_the_shared_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # D120's residual (3): the /states render goes through states_history, and
        # that through the page's row check, its collapse and its figures, each
        # state's checked rows into the collapse and its result into the figures.
        real = {
            name: getattr(state_view, name)
            for name in (
                "states_history",
                "rows",
                "electors",
                "collapsed",
                "history_figures",
            )
        }
        seen: dict[str, list[Any]] = {name: [] for name in real}

        def spy(name: str) -> Any:
            def wrapped(*args: Any) -> Any:
                result = real[name](*args)
                seen[name].append((args, result))
                return result

            return wrapped

        for name in real:
            monkeypatch.setattr(state_view, name, spy(name))
        page()
        assert len(seen["states_history"]) == 1
        assert len(seen["rows"]) == 51
        checked = [result for _args, result in seen["rows"]]
        assert [args[0] for args, _ in seen["electors"]] == checked
        assert [args[0] for args, _ in seen["collapsed"]] == [state_view.electors] * 51
        collapsed = [result for _args, result in seen["collapsed"]]
        assert [args[0] for args, _ in seen["history_figures"]] == collapsed
        assert [r for _a, r in seen["history_figures"]] == list(
            seen["states_history"][0][1].values()
        )


class TestHistoryValues:
    def test_a_refused_or_unrecognized_state_is_all_blank(self) -> None:
        blank = dict.fromkeys(state_view.HISTORY_VALUE_KEYS)
        assert state_view.history_values(None) == blank
        assert state_view.history_values(state_view.UNRECOGNIZED_HISTORY) == blank

    def test_a_state_with_no_electors_appointed_is_all_blank(self) -> None:
        # Recognized figures with no year of electors (an allotment of 0 only): the
        # page shows no-electors wording for every figure, so the download writes no
        # number, never a count of 0 (#641's acceptance gate, Class B survivor
        # history-values-zero-elections).
        figures = state_view.history_figures(
            [{"year": 1864, "state_electoral_votes": 0, "pv_status": "not_participating"}]
        )
        assert not figures.unrecognized and figures.elections == 0
        assert state_view.history_values(figures) == dict.fromkeys(
            state_view.HISTORY_VALUE_KEYS
        )

    def test_a_count_with_no_n_leaves_both_popular_vote_columns_blank(self) -> None:
        records = [
            {"year": 1824, "state_electoral_votes": 9, "pv_status": None},
            {"year": 1828, "state_electoral_votes": 11, "pv_status": None},
        ]
        values = state_view.history_values(state_view.history_figures(records))
        assert values["state_pv_elections_count"] is None
        assert values["state_pv_elections_n"] is None
        assert values["state_elections_count"] == 2
        assert values["state_first_election"] == 1824
        assert values["state_electors_change"] == 2


# --- the one wording of a figure (architect I-1) --------------------------------------


class TestHistoryCell:
    def test_unrecognized_reads_unrecognized_for_every_key(self) -> None:
        for key in state_view.HISTORY_KEYS:
            assert state_view.history_cell(state_view.UNRECOGNIZED_HISTORY, key) == (
                labels.UNRECOGNIZED,
                None,
            )

    def test_no_year_with_electors_words_every_figure_as_no_electors(self) -> None:
        figures = state_view.history_figures(
            [
                {
                    "year": 1824,
                    "state_electoral_votes": 0,
                    "pv_status": "not_participating",
                }
            ]
        )
        for key in state_view.HISTORY_KEYS:
            assert state_view.history_cell(figures, key) == (
                labels.METRIC_NO_FIGURE_NO_ELECTORS,
                None,
            )

    def test_a_figure_with_nothing_to_show_words_its_own_case(self) -> None:
        # One year with electors and a null status: no change and no popular-vote N.
        figures = state_view.history_figures(
            [{"year": 1824, "state_electoral_votes": 9, "pv_status": None}]
        )
        assert state_view.history_cell(figures, "state_electors_change") == (
            labels.METRIC_NO_FIGURE["state_electors_change"],
            None,
        )
        assert state_view.history_cell(figures, "state_pv_elections_count") == (
            labels.METRIC_NO_FIGURE["state_pv_elections_count"],
            None,
        )
        assert state_view.history_cell(figures, "state_elections_count")[0] == "1"
        assert state_view.history_cell(figures, "state_first_election")[0] == "1824"

    @pytest.mark.parametrize("key", ["state_took_office_count", "nonsense"])
    def test_another_key_is_refused_whatever_the_figures(self, key: str) -> None:
        # The key is checked before any lookup by key (#647's review,
        # r1.code-review.1): figures with years reach the no-figure lookup, where a
        # key ``METRIC_NO_FIGURE`` lacks ("nonsense") would raise ``KeyError``.
        with_years = state_view.history_figures(
            [{"year": 1824, "state_electoral_votes": 9, "pv_status": None}]
        )
        assert with_years.years
        for figures in (with_years, state_view.UNRECOGNIZED_HISTORY):
            with pytest.raises(TypeError):
                state_view.history_cell(figures, key)

    def test_the_states_table_words_its_cells_through_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # D123(e) on /states (#647's review, r1.guard-efficacy.1): every state's four
        # cells go through history_cell, in display order, with that state's figures;
        # then C11's hovers (#623), one per drawn state for the figure the map shows.
        calls: list[tuple[Any, str]] = []
        real = state_view.history_cell

        def spy(figures: Any, key: str) -> Any:
            calls.append((figures, key))
            return real(figures, key)

        monkeypatch.setattr(state_view, "history_cell", spy)
        page()
        found = history(n2())
        table, hovers = calls[: 4 * 51], calls[4 * 51 :]
        assert [key for _f, key in table] == list(state_view.HISTORY_KEYS) * 51
        assert [f for f, _key in table] == [
            found[usps] for usps in ROSTER_STATES for _ in state_view.HISTORY_KEYS
        ]
        default = PICKER_MOD["DEFAULT_METRIC"]
        assert hovers == [(found[usps], default) for usps in ROSTER_STATES]

    def test_the_state_page_words_its_four_figures_through_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        keys: list[str] = []
        real = state_view.history_cell

        def spy(figures: Any, key: str) -> Any:
            keys.append(key)
            return real(figures, key)

        monkeypatch.setattr(state_view, "history_cell", spy)
        render_all()
        assert keys == list(state_view.HISTORY_KEYS)

    def test_the_popular_vote_cell_matches_the_page_s_count_wording(self) -> None:
        # STATES_COUNT_OF is the start of the page's METRIC_COUNT_OF.
        count = metrics.flag_count([(1824, True), (1828, False)], True)
        value, rest = labels.metric_count(count, [1824, 1828], "x")
        assert (value + (rest or "")).startswith(
            labels.STATES_COUNT_OF.format(count=count.count, n=count.n)
        )


# --- the route ------------------------------------------------------------------------


def test_the_page_routes_with_its_table(monkeypatch: pytest.MonkeyPatch) -> None:
    _, calls, _ = cached_client(monkeypatch)
    ids = routed_ids(route("/states"))
    assert {PICKER["success"], TABLE_ID, PICKER_MOD["LIST_ID"]} <= ids
    assert UNAVAILABLE_ID not in ids
    assert calls == ["/v1/elections/2024", N2_PATH]


# --- chart C11, the map (#623, D121 as amended by D124) ------------------------------

#: The four figures C11 can show, the default first.
METRICS = list(state_view.HISTORY_KEYS)
DEFAULT = PICKER_MOD["DEFAULT_METRIC"]
C11_DOM = charts.dom_id("C11")
#: The state outlines the dashboard serves (D121(i)): the ids of their ``subunits``.
OUTLINE_IDS = {
    geometry["id"]
    for geometry in json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "dashboard"
            / "explore"
            / "assets"
            / "usa_110m.json"
        ).read_text(encoding="utf-8")
    )["objects"]["subunits"]["geometries"]
}


def c11_store(tree: Any) -> dict[str, Any] | None:
    """C11's unresolved figure in ``tree`` (its source store's), or ``None``."""
    found = [
        s.data
        for s in of_type(tree, "Store")
        if getattr(s, "id", None) == {"type": charts.SOURCE_TYPE, "chart": C11_DOM}
    ]
    assert len(found) <= 1
    return found[0] if found else None


def c11_trace(metric: str = DEFAULT, n2_body: Any = None) -> dict[str, Any]:
    figure = c11_store(page(n2_body, metric=metric))
    assert figure is not None
    trace: dict[str, Any] = figure["data"][0]
    return trace


def built(metric: str = DEFAULT, body: Any = None) -> dict[str, Any] | None:
    """:func:`c11_figure`'s whole figure, title included, over the recorded roster."""
    states = PICKER_MOD["roster"](copy.deepcopy(ROSTER), 2024)
    figures = history(n2() if body is None else body)
    result: dict[str, Any] | None = PICKER_MOD["c11_figure"](metric, states, figures)
    return result


def c11_element(tree: Any) -> Any:
    (figure,) = [f for f in of_type(tree, "Figure") if getattr(f, "id", None) == C11_DOM]
    return figure


def key_texts(tree: Any) -> list[str]:
    """The page key's sentences, inside C11's figure."""
    (key,) = [
        d
        for d in of_type(c11_element(tree), "Div")
        if getattr(d, "className", None) == "chart-key"
    ]
    return ["".join(texts(p)) for p in of_type(key, "P")]


def hover_values(trace: dict[str, Any], metric: str) -> dict[str, str]:
    """Each drawn state's hover value, unescaped, by USPS code: the text after the
    figure's header."""
    header = labels.STATES_HISTORY_HEADERS[metric]
    found = {}
    for usps, text in zip(trace["locations"], trace["hovertext"], strict=True):
        _state, line = html_lib.unescape(text).split("<br>")
        assert line.startswith(f"{header}: "), line
        found[usps] = line.removeprefix(f"{header}: ")
    return found


def key_paths(value: Any, path: str = "") -> set[str]:
    """Every key path under ``value``, a list's items as ``[i]``."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            here = f"{path}.{key}" if path else key
            found |= {here, *key_paths(inner, here)}
    elif isinstance(value, list):
        for inner in value:
            found |= key_paths(inner, f"{path}[i]")
    return found


def figure_number(text: str, metric: str) -> int:
    """The number a state page's figure text leads with, read independently of the
    map's path: the count before " of " for the popular-vote count, the signed change
    ("+", U+2212 or an unsigned "0") for the change, and the leading integer of the
    other two (its count of elections, its first election's year)."""
    head = text.split(",")[0].split(" ")[0]
    if metric == "state_pv_elections_count":
        head = text.split(" of ")[0]
    if metric == "state_electors_change":
        if head.startswith("+"):
            return int(head[1:])
        if head.startswith("\u2212"):
            return -int(head[1:])
    return int(head)


def change_of(delta: int) -> state_view.HistoryFigures:
    """A state's history figures whose change in electors is ``delta``: two elections,
    from 100 electors in 1824 to ``100 + delta`` in 2024."""
    return state_view.history_figures(
        [
            {"year": y, "state_electoral_votes": v, "pv_status": "popular_vote"}
            for y, v in ((1824, 100), (2024, 100 + delta))
        ]
    )


class TestC11:
    def test_the_default_view_draws_every_state_s_elections_count(self) -> None:
        trace = c11_trace()
        assert DEFAULT == "state_elections_count"
        assert trace["locations"] == ROSTER_STATES
        assert len(trace["locations"]) == 51

    @pytest.mark.parametrize("metric", METRICS)
    def test_the_title_names_the_figure(self, metric: str) -> None:
        # The figure's ``layout.title``, which ``components.chart`` writes as the
        # chart's page title, in a render of ``?metric=<metric>``.
        figure = built(metric)
        assert figure is not None
        assert figure["layout"]["title"] == {"text": labels.C11_TITLES[metric]}
        tree = page(metric=metric)
        (title,) = [
            p.children
            for p in of_type(c11_element(tree), "P")
            if getattr(p, "className", None) == "chart-title"
        ]
        assert title == labels.C11_TITLES[metric]

    @pytest.mark.parametrize("metric", METRICS)
    def test_each_figure_draws_in_its_measure_s_ramp(self, metric: str) -> None:
        # D109: the allotment's three figures red, popular votes held blue.
        ramp = charts.MAP_RAMPS[1 if metric == "state_pv_elections_count" else 0]
        assert c11_trace(metric)["colorscale"] == charts.map_colorscale(ramp)

    @pytest.mark.parametrize("metric", METRICS)
    def test_z_is_each_state_s_own_figure(self, metric: str) -> None:
        """``z`` is the table's path for every drawn state (one value per location, an
        ``int``). This is the map against the table's own function; the check against
        an independent oracle, each state page's figure text, is
        ``TestC11Reconciliation.test_z_equals_the_state_page_s_figure``."""
        trace = c11_trace(metric)
        figures = history(n2())
        assert trace["z"] == [
            state_view.history_values(figures[usps])[metric]
            for usps in trace["locations"]
        ]
        assert all(type(v) is int for v in trace["z"])

    @pytest.mark.parametrize("metric", METRICS)
    def test_the_bounds_are_the_drawn_values_lowest_and_highest(
        self, metric: str
    ) -> None:
        trace = c11_trace(metric)
        assert (trace["zmin"], trace["zmax"]) == (min(trace["z"]), max(trace["z"]))
        assert trace["zmin"] < trace["zmax"]

    @pytest.mark.parametrize(
        ("metric", "ticks", "texts_"),
        [
            ("state_elections_count", [16, 51], ["16", "51"]),
            ("state_first_election", [1824, 1964], ["1824", "1964"]),
            ("state_pv_elections_count", [16, 51], ["16", "51"]),
            ("state_electors_change", [-11, 0, 50], ["−11", "0", "+50"]),
        ],
    )
    def test_the_ticks_are_numbered_in_the_table_s_value_format(
        self, metric: str, ticks: list[int], texts_: list[str]
    ) -> None:
        """Hand values from the recording: the ends, and 0 for the change, written as
        the table writes a value (a year with no separator, a signed change with
        U+2212), never "{count} of {n}" (ba, #623)."""
        colorbar = c11_trace(metric)["colorbar"]
        assert colorbar["tickvals"] == ticks
        assert colorbar["ticktext"] == texts_
        assert colorbar["orientation"] == "h"
        assert "title" not in colorbar
        assert not any(" of " in t for t in colorbar["ticktext"])

    @pytest.mark.parametrize("metric", METRICS)
    def test_the_figure_passes_the_map_s_rules_and_sets_no_geo(
        self, metric: str
    ) -> None:
        figure = built(metric)
        assert figure is not None
        assert "geo" not in figure["layout"]
        assert charts.figure_problems(figure, map_ramp=True) == []
        assert charts.CHARTS["C11"].map_ramp is True
        assert figure["layout"]["height"] == PICKER_MOD["C11_HEIGHT_PX"]

    @pytest.mark.parametrize("metric", METRICS)
    def test_every_key_path_is_one_the_map_s_base_holds(self, metric: str) -> None:
        """[A-C7]: the totality sweeps over ``MAP_BASE`` cover C11's real figure, since
        every key path C11 sets is one ``MAP_BASE`` holds."""
        from tests.unit.test_dashboard_charts import MAP_BASE

        figure = built(metric)
        assert key_paths(figure) <= key_paths(MAP_BASE), key_paths(figure) - key_paths(
            MAP_BASE
        )

    def test_the_hover_writes_the_state_the_header_and_the_cell(self) -> None:
        trace = c11_trace()
        assert trace["hovertemplate"] == "%{hovertext}<extra></extra>"
        georgia = trace["hovertext"][trace["locations"].index("GA")]
        assert georgia == labels.C11_HOVER.format(
            state="Georgia",
            figure=labels.STATES_HISTORY_HEADERS[DEFAULT],
            value="50",
        )

    @pytest.mark.parametrize("metric", METRICS)
    def test_the_caption_then_the_pointer(self, metric: str) -> None:
        figure = c11_element(page(metric=metric))
        (caption,) = [
            p
            for p in of_type(figure, "P")
            if getattr(p, "className", None) == "chart-caption-text"
        ]
        assert caption.children == " ".join(
            (labels.C11_CAPTION, labels.C11_BASIS[metric], labels.C11_OUTLINES_CREDIT)
        )
        (pointer,) = of_type(figure, "A")
        assert pointer.children == labels.CHART_TABLE_POINTER
        assert pointer.href == f"#{TABLE_ID}"

    def test_the_key_is_inside_the_figure_with_no_outline_entry(self) -> None:
        assert key_texts(page()) == [labels.C11_COLOR_NOTE, labels.C11_PHONE_NOTE]

    def test_the_figure_takes_the_map_s_class(self) -> None:
        assert c11_element(page()).className == "chart chart-map"

    @pytest.mark.parametrize("metric", METRICS)
    def test_the_control_lists_the_four_headers_in_order(self, metric: str) -> None:
        (control,) = [
            d
            for d in of_type(page(metric=metric), "Dropdown")
            if d.id == PICKER_MOD["METRIC_ID"]
        ]
        assert control.options == [
            {"label": labels.STATES_HISTORY_HEADERS[k], "value": k} for k in METRICS
        ]
        assert control.value == metric
        assert control.clearable is False
        assert control.placeholder == PICKER_MOD["METRIC_PLACEHOLDER"]
        (label,) = [
            lab
            for lab in of_type(page(), "Label")
            if lab.htmlFor == PICKER_MOD["METRIC_ID"]
        ]
        assert label.children == PICKER_MOD["METRIC_LABEL"]

    def test_the_card_holds_heading_intro_control_map_then_the_table(self) -> None:
        card = every_card(page())[0]
        kinds = [type(c).__name__ for c in card.children]
        assert kinds[:4] == ["H2", "P", "Div", "Figure"]
        assert card.children[2].className == "filters wrapped-choice"
        assert card.children[3].id == C11_DOM
        ids = [getattr(c, "id", None) for c in card.children]
        assert ids[-1] == GLOSSARY_ID
        table_at = next(
            i for i, c in enumerate(card.children) if TABLE_ID in component_ids(c)
        )
        assert table_at > 3


class TestC11Reconciliation:
    @pytest.mark.parametrize("metric", METRICS)
    @pytest.mark.parametrize("usps", ["GA", "TX"])
    def test_the_hover_equals_the_cell_and_the_state_page(
        self, usps: str, metric: str
    ) -> None:
        # AC3's hover half: the map's hover, the table's cell (both from N2) and the
        # state page's figure (from /v1/states/{usps}), as rendered text.
        tree = page(metric=metric)
        trace = c11_store(tree)["data"][0]  # type: ignore[index]
        hover = hover_values(trace, metric)[usps]
        cell = dict(zip(METRICS, table_rows(tree)[usps][1:], strict=True))[metric]
        assert hover == cell
        assert figures_of(usps)[metric].startswith(hover), (metric, hover)

    @pytest.mark.parametrize("metric", METRICS)
    @pytest.mark.parametrize("usps", ["GA", "TX"])
    def test_z_equals_the_state_page_s_figure(self, usps: str, metric: str) -> None:
        # AC3's value half: the number the map shades by, against the state page's
        # figure text (from /v1/states/{usps}), never the table's path.
        trace = c11_trace(metric)
        drawn = trace["z"][trace["locations"].index(usps)]
        assert drawn == figure_number(figures_of(usps)[metric], metric)

    @pytest.mark.parametrize(
        ("text", "metric", "number"),
        [
            ("50 elections (1824\u20132024)", "state_elections_count", 50),
            ("1848, with 4 electors appointed", "state_first_election", 1848),
            ("49 of 50 elections (1824\u20132024)", "state_pv_elections_count", 49),
            ("+7, from 9 in 1824 to 16 in 2024", "state_electors_change", 7),
            ("\u22123, from 9 in 1824 to 6 in 2024", "state_electors_change", -3),
            ("0, from 9 in 1824 to 9 in 2024", "state_electors_change", 0),
        ],
    )
    def test_the_oracle_reads_each_figure_s_number(
        self, text: str, metric: str, number: int
    ) -> None:
        assert figure_number(text, metric) == number

    @pytest.mark.parametrize("metric", METRICS)
    def test_the_locations_are_the_states_with_a_figure_and_have_outlines(
        self, metric: str
    ) -> None:
        tree = page(metric=metric)
        locations = set(c11_store(tree)["data"][0]["locations"])  # type: ignore[index]
        figures = history(n2())
        with_figure = {
            usps
            for usps in ROSTER_STATES
            if state_view.history_values(figures[usps])[metric] is not None
        }
        assert locations == with_figure
        assert locations <= OUTLINE_IDS

    @pytest.mark.parametrize(
        ("fault", "doctor"),
        [
            # An allotment no figure can read: every figure unrecognized.
            (
                "unrecognized",
                lambda body: first_row(body, "GA").__setitem__(
                    "state_electoral_votes", "x"
                ),
            ),
            # A gap after its first election: the state is refused (D123(c)).
            ("refused", lambda body: drop(body, "GA", middle_year("GA"))),
        ],
    )
    @pytest.mark.parametrize("metric", METRICS)
    def test_a_state_with_no_number_is_left_out_with_the_key_entry(
        self, metric: str, fault: str, doctor: Any
    ) -> None:
        body = n2()
        doctor(body)
        tree = page(body, metric=metric)
        locations = c11_store(tree)["data"][0]["locations"]  # type: ignore[index]
        assert "GA" not in locations
        assert len(locations) == 50
        assert key_texts(tree) == [
            labels.C11_COLOR_NOTE,
            labels.C11_NO_FIGURE_KEY,
            labels.C11_PHONE_NOTE,
        ]

    def test_a_one_election_state_has_no_change_on_the_map(self) -> None:
        # D121(f): one election with electors appointed reads No figure for the
        # change, so the state is left out of the change's map alone.
        body = n2()
        first = first_row(body, "GA")["year"]
        for row in body["data"]:
            if row["state_usps"] == "GA" and row["year"] != first:
                row["state_electoral_votes"] = 0
        change = c11_store(page(body, metric="state_electors_change"))
        assert "GA" not in change["data"][0]["locations"]  # type: ignore[index]
        count = c11_store(page(body))
        assert "GA" in count["data"][0]["locations"]  # type: ignore[index]

    def test_the_zero_tick_s_least_share_is_a_tenth(self) -> None:
        assert PICKER_MOD["C11_ZERO_TICK_MIN_FRACTION"] == 0.1

    @pytest.mark.parametrize(
        ("low", "high", "ticks"),
        [
            # 0 a fifty-first of the bar from its low end: the ends only.
            (-1, 50, [-1, 50]),
            # The recording's change: 0 well inside.
            (-11, 50, [-11, 0, 50]),
            # 0 at exactly a tenth from the low end (0.1 and 0.9): kept.
            (-10, 90, [-10, 0, 90]),
            # 0 at exactly a tenth from the high end: kept.
            (-90, 10, [-90, 0, 10]),
            # Just under a tenth from either end: dropped.
            (-10, 91, [-10, 91]),
            (-91, 10, [-91, 10]),
            # 0 at an end or off the scale: the ends only.
            (0, 50, [0, 50]),
            (-50, 0, [-50, 0]),
            (3, 50, [3, 50]),
        ],
    )
    def test_the_change_keeps_its_zero_tick_only_a_tenth_from_each_end(
        self, low: int, high: int, ticks: list[int]
    ) -> None:
        """D124(e) as amended (owner, PR #652's code review): the change map's 0 tick
        only where 0 sits at least ``C11_ZERO_TICK_MIN_FRACTION`` of the bar from each
        end, so it never crowds an end label."""
        metric = "state_electors_change"
        states = [("GA", "Georgia"), ("TX", "Texas")]
        values = {"GA": change_of(low), "TX": change_of(high)}
        figure = PICKER_MOD["c11_figure"](metric, states, values)
        assert figure["data"][0]["z"] == [low, high]
        colorbar = figure["data"][0]["colorbar"]
        assert colorbar["tickvals"] == ticks
        assert colorbar["ticktext"] == [labels.signed(t) for t in ticks]
        assert charts.figure_problems(figure, map_ramp=True) == []

    def test_one_value_puts_the_top_one_above_it(self) -> None:
        """D124: where every drawn value is equal, ``zmax`` is one above ``zmin``,
        so the scale is never empty; the last tick names that number."""
        states = [("GA", "Georgia"), ("TX", "Texas")]
        figures = history(n2())
        same = {"GA": figures["GA"], "TX": figures["GA"]}
        figure = PICKER_MOD["c11_figure"]("state_first_election", states, same)
        trace = figure["data"][0]
        assert (trace["zmin"], trace["zmax"]) == (1824, 1825)
        assert trace["colorbar"]["tickvals"] == [1824, 1825]
        assert trace["colorbar"]["ticktext"] == ["1824", "1825"]
        assert charts.figure_problems(figure, map_ramp=True) == []

    def test_no_state_with_a_number_shows_the_sentence_in_its_place(self) -> None:
        states = PICKER_MOD["roster"](copy.deepcopy(ROSTER), 2024)
        figures = dict.fromkeys((usps for usps, _ in states), None)
        (note,) = PICKER_MOD["c11"](DEFAULT, states, figures)
        assert note.id == PICKER_MOD["C11_NO_FIGURES_ID"]
        assert note.children == labels.C11_NO_FIGURES
        assert PICKER_MOD["c11_figure"](DEFAULT, states, figures) is None


class TestMetricQuery:
    @pytest.mark.parametrize(
        ("params", "kept"),
        [
            ({}, []),
            ({"metric": "state_first_election"}, [("metric", "state_first_election")]),
            (
                {"metric": ["state_electors_change", "state_electors_change"]},
                [("metric", "state_electors_change")],
            ),
            # The default is never named (D073); a value off the vocabulary, two
            # values, a non-string or another key is dropped.
            ({"metric": DEFAULT}, []),
            ({"metric": "STATE_FIRST_ELECTION"}, []),
            ({"metric": "state_pv_elections_n"}, []),
            ({"metric": ["state_first_election", "state_electors_change"]}, []),
            ({"metric": 7}, []),
            ({"year": "2016"}, []),
            (None, []),
        ],
    )
    def test_the_parser_keeps_a_known_non_default_figure_only(
        self, params: Any, kept: list[tuple[str, str]]
    ) -> None:
        assert PICKER_MOD["parse_metric"](params) == kept

    @pytest.mark.parametrize(
        ("value", "current", "written"),
        [
            ("state_first_election", "", "?metric=state_first_election"),
            (DEFAULT, "?metric=state_first_election", ""),
            ("state_first_election", "?metric=state_first_election", None),
            (DEFAULT, "", None),
            (DEFAULT, None, None),
            (None, "?metric=state_electors_change", ""),
        ],
    )
    def test_a_change_writes_the_normalized_query(
        self, value: Any, current: Any, written: str | None
    ) -> None:
        result = PICKER_MOD["on_metric_change"](value, current)
        if written is None:
            assert result is dash.no_update
        else:
            assert result == written

    def test_og_url_names_the_chosen_figure_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch)
        status, head, _ = get("/states?metric=state_first_election&junk=1")
        assert status == 200
        assert head.canonical == url("/states")
        assert head.og_url == url("/states?metric=state_first_election")
        for search in (f"?metric={DEFAULT}", "?metric=zz", ""):
            _, head, _ = get(f"/states{search}")
            assert head.og_url == url("/states"), search

    @pytest.mark.parametrize("metric", METRICS[1:])
    def test_a_change_of_figure_reads_nothing_and_leaves_the_table(
        self, monkeypatch: pytest.MonkeyPatch, metric: str
    ) -> None:
        """AC2: the routed render for another figure redraws the map, makes no
        request (the cache holds both reads), and leaves the table and its download
        byte for byte."""
        _, calls, _ = cached_client(monkeypatch)
        first = route("/states")
        assert calls == ["/v1/elections/2024", N2_PATH]
        calls.clear()
        second = route("/states", f"?metric={metric}")
        assert calls == []
        assert {TABLE_ID, C11_DOM} <= routed_ids(second)
        assert first.get_json() != second.get_json()
        default, chosen = page(), page(metric=metric)
        assert table_rows(default) == table_rows(chosen)
        assert links(default)[export.link_id(TABLE_ID)].href == (
            links(chosen)[export.link_id(TABLE_ID)].href
        )
        assert c11_store(default) != c11_store(chosen)

    @pytest.mark.parametrize("metric", METRICS)
    def test_the_layout_draws_the_query_s_figure_and_the_filter_sentence(
        self, monkeypatch: pytest.MonkeyPatch, metric: str
    ) -> None:
        cached_client(monkeypatch)
        tree = PICKER_MOD["layout"](metric=metric)
        trace = c11_store(tree)["data"][0]  # type: ignore[index]
        assert trace["colorbar"] == c11_trace(metric)["colorbar"]
        (lede,) = [
            p for p in of_type(tree, "P") if getattr(p, "className", None) == "lede"
        ]
        assert lede.children == (
            f"{PICKER_MOD['LEDE']} {PICKER_MOD['FILTER_SENTENCE']}"
        )


class TestC11Degraded:
    def assert_no_map(self, tree: Any) -> None:
        ids = component_ids(tree)
        assert C11_DOM not in ids
        assert PICKER_MOD["METRIC_ID"] not in ids
        assert PICKER_MOD["URL_ID"] not in ids
        assert c11_store(tree) is None
        assert UNAVAILABLE_ID in ids
        assert PICKER_MOD["LIST_ID"] in ids

    def test_an_unread_n2_removes_the_map_and_its_control(self) -> None:
        self.assert_no_map(page(False))

    @pytest.mark.parametrize("fault", sorted(BODY_FAULTS))
    def test_a_malformed_n2_removes_the_map_and_its_control(self, fault: str) -> None:
        body = n2()
        BODY_FAULTS[fault](body)
        self.assert_no_map(page(body))

    def test_the_degraded_lede_has_no_filter_sentence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, _, _ = cached_client(monkeypatch)
        real = client._fetch

        def fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
            if path == N2_PATH:
                raise api.ApiUnavailable("GET n2: HTTP 503")
            return real(path, timeout)

        monkeypatch.setattr(client, "_fetch", fetch)
        tree = PICKER_MOD["layout"](metric="state_first_election")
        self.assert_no_map(tree)
        (lede,) = [
            p for p in of_type(tree, "P") if getattr(p, "className", None) == "lede"
        ]
        assert lede.children == PICKER_MOD["LEDE"]
