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
from typing import Any

import pytest

from explore import api, export, labels, metrics, state_view
from tests.dashboard_cards import every_card
from tests.unit.test_dashboard_app import (
    RECORDED,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    cached_client,
    component_ids,
    route,
    routed_ids,
    texts,
)
from tests.unit.test_dashboard_elections import find, of_type
from tests.unit.test_dashboard_export import body_rows, download
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


def page(n2_body: Any = None, roster: Any = None) -> Any:
    """The page body for the recorded roster and ``n2_body`` (the recording unless
    given; pass ``False`` for an unread N2)."""
    body = n2() if n2_body is None else (None if n2_body is False else n2_body)
    return PICKER_MOD["render"](
        copy.deepcopy(ROSTER) if roster is None else roster,
        2024,
        body,
        copy.deepcopy(INDEX),
    )


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
        # cells go through history_cell, in display order, with that state's figures.
        calls: list[tuple[Any, str]] = []
        real = state_view.history_cell

        def spy(figures: Any, key: str) -> Any:
            calls.append((figures, key))
            return real(figures, key)

        monkeypatch.setattr(state_view, "history_cell", spy)
        page()
        found = history(n2())
        assert [key for _f, key in calls] == list(state_view.HISTORY_KEYS) * 51
        assert [f for f, _key in calls] == [
            found[usps] for usps in ROSTER_STATES for _ in state_view.HISTORY_KEYS
        ]

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
