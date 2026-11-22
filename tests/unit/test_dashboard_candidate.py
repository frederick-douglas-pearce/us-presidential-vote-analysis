"""The candidate history, T5 (#331), and the candidate links in T2, T3 and T4.

Offline, against the recorded candidate index ``/v1/candidates`` and
``/v1/candidates/andrew-jackson`` (the same snapshot as every other fixture,
``test_every_recorded_response_is_one_snapshot``), through the helpers and the autouse
offline process client of ``test_dashboard_app.py``. The registry-wide checks there
pick the page up (``TestRegistryCoverage``, ``TestValidateBeforeFill`` with
``no-such-candidate`` as the unserved slug, ``TestRegistryContracts``), and the D070(b)
guard renders ``/candidate/andrew-jackson`` and ``/candidate/no-such-candidate``. These
tests cover what is particular to the page.
"""

from __future__ import annotations

import copy
import random
from typing import Any

import dash
import pytest
from dash import no_update

from explore import api, components, election_view, labels
from tests.dashboard_cards import in_one_card
from tests.unit.test_dashboard_app import (
    RECORDED,
    RecordingBucket,
    _offline_process_client,  # noqa: F401  (autouse: no test reaches the network)
    cached_client,
    fake_fetch,
    get,
    offline_client,
    route,
    routed_ids,
    texts,
    url,
)
from tests.unit.test_dashboard_elections import classed, find, of_type, parse

PAGE: dict[str, Any] = dash.page_registry["pages.candidate"]
#: The page module's namespace, reached through its layout (Dash loads it by path).
MOD: dict[str, Any] = PAGE["layout"].__globals__

INDEX: dict[str, Any] = RECORDED[api.ELECTIONS_PATH]
CANDIDATES: dict[str, Any] = RECORDED[api.CANDIDATES_PATH]
SLUG = "andrew-jackson"
JACKSON_PATH = f"/v1/candidates/{SLUG}"
JACKSON_YEARS = [1824, 1828, 1832]
PAGE_ID = MOD["PAGE_ID"]
NOT_FOUND_ID = MOD["NOT_FOUND_ID"]
TABLE = MOD["TABLE_ID"]


def jackson() -> dict[str, Any]:
    return copy.deepcopy(RECORDED[JACKSON_PATH])


def rendered(query: str = "", body: Any = None) -> tuple[Any, str, bool]:
    return MOD["render"](  # type: ignore[no-any-return]
        jackson() if body is None else body,
        copy.deepcopy(INDEX),
        SLUG,
        MOD["parse_filters"](parse(query)),
    )


def render(query: str = "", body: Any = None) -> Any:
    """The page body for ``query``, as the layout builds it."""
    return rendered(query, body)[0]


def table_rows(tree: Any) -> list[list[Any]]:
    table = find(tree, TABLE)
    if table is None:
        return []
    return [list(tr.children) for tr in of_type(of_type(table, "Tbody"), "Tr")]


def row_texts(tree: Any) -> list[list[str]]:
    return [[" ".join(texts(td)) for td in row] for row in table_rows(tree)]


def years_shown(tree: Any) -> list[int]:
    return sorted({int(row[0]) for row in row_texts(tree)})


# --- registration, the recordings and the judge ---------------------------------------


def test_the_page_is_registered_as_planned() -> None:
    assert PAGE["path_template"] == "/candidate/<slug>"
    assert PAGE["prefetch"] == (api.ELECTIONS_PATH,)
    # The index is a miss, not a prefetch: D072's extent is unchanged (#310 owns it).
    assert PAGE["on_miss"] == (api.CANDIDATES_PATH, "/v1/candidates/{slug}")
    assert api.CANDIDATES_PATH == "/v1/candidates"
    assert PAGE["success"] == PAGE_ID
    # The registered judge is the one the layout calls, so the index's 404 and the
    # page's not-found state decide alike.
    assert PAGE["validate"] is MOD["VALIDATE"]
    assert PAGE["validate"] == (api.CANDIDATES_PATH, MOD["on_index"])
    assert PAGE["query"] is MOD["parse_filters"]


def test_the_recordings_agree_with_each_other() -> None:
    """The index's years for the recorded candidate are exactly the years of its rows,
    and each 1824 row is the same row the recorded 1824 election serves, so a
    re-recording of one file but not the others fails here."""
    (item,) = [i for i in CANDIDATES["data"] if i["candidate_slug"] == SLUG]
    rows = RECORDED[JACKSON_PATH]["data"]
    assert item["years"] == sorted({r["year"] for r in rows}) == JACKSON_YEARS
    by_state = {
        (r["state_usps"], r["candidate_slug"]): r
        for r in RECORDED["/v1/elections/1824"]["data"]
    }
    ours = [r for r in rows if r["year"] == 1824]
    assert ours
    for row in ours:
        assert by_state[(row["state_usps"], SLUG)] == row


class TestOnIndex:
    @pytest.mark.parametrize(
        "slug", sorted(i["candidate_slug"] for i in CANDIDATES["data"])
    )
    def test_every_slug_the_index_lists_is_accepted(self, slug: str) -> None:
        assert MOD["on_index"]({"slug": slug}, CANDIDATES) is True

    @pytest.mark.parametrize(
        "slug",
        [
            "Andrew-Jackson",  # another letter case: the slug pattern refuses it
            "ANDREW-JACKSON",
            "no-such-candidate",  # well-formed, unlisted
            "andrew-jackson-",
            "andrew jackson",
            "",
            None,
            7,
            ["andrew-jackson"],
        ],
    )
    def test_anything_else_is_refused(self, slug: Any) -> None:
        assert MOD["on_index"]({"slug": slug}, CANDIDATES) is False

    @pytest.mark.parametrize(
        "change",
        [
            lambda b: b["data"].append({"candidate_slug": 7}),
            lambda b: b["data"].append("andrew-jackson"),
            lambda b: b["data"][-1].pop("candidate_slug"),
            # A listed value is formatted into a path, so one that is no slug refuses
            # the whole index, as one bad roster row does.
            lambda b: b["data"].append({"candidate_slug": "../x"}),
            lambda b: b["data"].append({"candidate_slug": "Andrew-Jackson"}),
            lambda b: b["data"].append({"candidate_slug": "a" * 65}),
            lambda b: b.update(data={"andrew-jackson": {}}),
            lambda b: b.update(data=[]),
            lambda b: b.clear(),
        ],
    )
    def test_a_malformed_index_lists_no_slug_at_all(self, change: Any) -> None:
        body = copy.deepcopy(CANDIDATES)
        change(body)
        assert MOD["listed"](body) == set()
        assert MOD["on_index"]({"slug": SLUG}, body) is False

    @pytest.mark.parametrize("body", [None, "x", 7, []])
    def test_a_body_that_is_no_object_lists_none(self, body: Any) -> None:
        assert MOD["on_index"]({"slug": SLUG}, body) is False


# --- T5 from the recorded rows --------------------------------------------------------


class TestJackson:
    def test_every_row_is_shown_unfiltered_by_year_then_state(self) -> None:
        tree = render()
        rows = table_rows(tree)
        assert len(rows) == len(jackson()["data"]) == 72
        keys = [(int(texts(r[0])[0]), texts(r[1])[0]) for r in rows]
        assert keys == sorted(keys)
        assert years_shown(tree) == JACKSON_YEARS
        assert "Showing 72 of 72 rows" in texts(tree)

    def test_the_columns_are_t5s(self) -> None:
        tree = render()
        headers = [
            th.title
            for th in of_type(find(tree, TABLE), "Th")
            if getattr(th, "title", None)
        ]
        assert tuple(headers) == MOD["FIELDS"]

    def test_the_heading_names_the_candidate_from_the_rows(self) -> None:
        _, heading, several = rendered()
        assert heading == "Andrew Jackson"
        assert several is True

    @pytest.mark.parametrize("name", [None, "", "  ", 7, True])
    def test_a_blank_name_keeps_the_generic_heading(self, name: Any) -> None:
        body = jackson()
        body["data"][0]["candidate"] = name
        assert rendered(body=body)[1] == MOD["HEADING"]

    def test_a_legislature_row_reads_its_label(self) -> None:
        legislature = [
            r
            for r in row_texts(render())
            if labels.PV_STATUS["legislature_chosen"] in r
        ]
        assert len(legislature) == 9

    def test_a_disputed_count_shows_its_reason_verbatim(self) -> None:
        body = jackson()
        reason = "Congress did not count this state's votes."
        body["data"][0].update(
            electoral_count_status="disputed", electoral_count_status_reason=reason
        )
        first = table_rows(render(body=body))[0]
        assert of_type(first[6], "Strong")[0].children == "Disputed"
        assert of_type(first[6], "Span")[0].children == reason

    def test_the_party_reads_its_display_form_or_its_null_label(self) -> None:
        # #389: Jackson's 1824 rows carry the Archives' Democratic-Republican party.
        cell = table_rows(render())[0][2]
        assert texts(cell) == ["Democratic-Republican"]
        body = jackson()
        body["data"][0].update(
            nominating_party=None,
            nominating_party_source=None,
            nominating_party_note=None,
        )
        cell = table_rows(render(body=body))[0][2]
        assert texts(cell) == [labels.NOT_IN_DATASET]
        assert cell.title == labels.PARTY_NULL_NOTE

    def test_the_party_notes_list_lists_each_year_once(self) -> None:
        """T5 (#389): a note per candidate-year, listed once however many state rows
        carry it, one item per year in row order. Jackson's recorded rows carry no
        note, so two years are doctored here."""
        body = jackson()
        years = sorted({r["year"] for r in body["data"]})[:2]
        for row in body["data"]:
            if row["year"] in years:
                row["nominating_party_note"] = f"A note for {row['year']}."
        blocks = [
            d
            for d in of_type(render(body=body), "Div")
            if getattr(d, "className", None) == "party-notes"
        ]
        assert len(blocks) == 1
        assert [li.children for li in of_type(blocks[0], "Li")] == [
            labels.PARTY_NOTE_ITEM.format(
                candidate="Andrew Jackson", year=y, note=f"A note for {y}."
            )
            for y in years
        ]
        assert not [
            d
            for d in of_type(render(), "Div")
            if getattr(d, "className", None) == "party-notes"
        ]

    def test_t5_s_column_name_list_names_the_count_reason_and_the_party_note(
        self,
    ) -> None:
        named = [
            [texts(dd.children)[0] for dd in of_type(g, "Dd")]
            for g in of_type(render(), "Details")
        ]
        assert named == [
            [*MOD["FIELDS"], "electoral_count_status_reason", "nominating_party_note"]
        ]

    def test_each_year_links_to_its_election_and_each_state_to_its_history(
        self,
    ) -> None:
        for row in table_rows(render()):
            (year,) = of_type(row[0], "Link")
            assert year.href == f"/election/{year.children}"
            (state,) = of_type(row[1], "Link")
            assert state.href.startswith("/state/")
        hrefs = {
            link.href
            for row in table_rows(render())
            for link in of_type(row[1], "Link")
        }
        assert hrefs == {f"/state/{r['state_usps']}" for r in jackson()["data"]}

    def test_the_download_names_the_candidate_and_the_applied_filters(self) -> None:
        (link,) = [
            a
            for a in of_type(render("year_from=1828&year_to=1828&state=GA"), "A")
            if getattr(a, "download", None)
        ]
        assert link.download == "candidate-andrew-jackson-history.csv"
        assert "Download this candidate's history (CSV)" in texts(link)


# --- malformed bodies degrade --------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"candidate_slug": "john-quincy-adams"}, "another candidate"),
        ({"year": 1825}, "no served year"),
        ({"year": "1824"}, "no served year"),
        ({"state_usps": "ga"}, "no state code"),
        ({"state_usps": None}, "no state code"),
    ],
    ids=repr,
)
def test_a_row_of_another_candidate_or_no_served_year_or_state_is_malformed(
    change: dict[str, Any], message: str
) -> None:
    body = jackson()
    body["data"][len(body["data"]) // 2].update(change)
    with pytest.raises(TypeError, match=message):
        render(body=body)


@pytest.mark.parametrize("data", [[], None, "rows", {}])
def test_a_body_with_no_rows_is_malformed(data: Any) -> None:
    body = jackson()
    body["data"] = data
    with pytest.raises(TypeError):
        render(body=body)


def test_rows_are_sorted_by_the_page_not_trusted_in_api_order() -> None:
    body = jackson()
    random.Random(331).shuffle(body["data"])
    assert row_texts(render(body=body)) == row_texts(render())


# --- filters --------------------------------------------------------------------------


class TestFilters:
    def test_the_parser_keeps_only_its_own_keys_and_never_the_path_variable(
        self,
    ) -> None:
        pairs = MOD["parse_filters"](
            parse(
                "year_from=1828&year_to=1828&state=GA&slug=henry-clay"
                "&candidate=henry-clay&usps=TX&junk=1"
            )
        )
        assert pairs == [("state", "GA"), ("year_from", "1828"), ("year_to", "1828")]

    @pytest.mark.parametrize(
        "query",
        [
            "state=ga",
            "state=Georgia",
            "state=GA&state=TX",
            "year_from=182",
            # A range or a lone bound names no view this page shows (#331's review).
            "year_from=1824&year_to=1832",
            "year_from=1828",
            "year_to=1828",
            "year_from=1832&year_to=1824",
        ],
    )
    def test_a_bad_parameter_is_dropped(self, query: str) -> None:
        assert MOD["parse_filters"](parse(query)) == []

    @pytest.mark.parametrize("year", JACKSON_YEARS)
    def test_one_of_the_candidates_years_narrows_the_rows(self, year: int) -> None:
        tree = render(f"year_from={year}&year_to={year}")
        assert years_shown(tree) == [year]
        assert find(tree, MOD["YEAR_ID"]).value == str(year)

    @pytest.mark.parametrize(
        "query",
        [
            "year_from=1824&year_to=1828",  # a range: the control picks one year
            "year_from=1828",  # one bound
            "year_to=1828",
            "year_from=1836&year_to=1836",  # served, but not one of his
            "year_from=1700&year_to=1700",
        ],
    )
    def test_anything_but_one_of_the_candidates_years_shows_every_year(
        self, query: str
    ) -> None:
        tree = render(query)
        assert years_shown(tree) == JACKSON_YEARS
        assert find(tree, MOD["YEAR_ID"]).value == components.ALL_YEARS_VALUE

    def test_a_state_from_the_candidates_rows_narrows_them(self) -> None:
        tree = render("state=GA")
        rows = row_texts(tree)
        assert {r[1] for r in rows} == {"Georgia"}
        assert [int(r[0]) for r in rows] == JACKSON_YEARS

    def test_a_state_absent_from_the_rows_falls_back_to_all(self) -> None:
        # Arizona took no part in Jackson's elections.
        assert len(table_rows(render("state=AZ"))) == 72

    def test_a_year_and_a_state_together(self) -> None:
        assert row_texts(render("year_from=1832&year_to=1832&state=GA"))[0][:2] == [
            "1832",
            "Georgia",
        ]
        assert len(table_rows(render("year_from=1832&year_to=1832&state=GA"))) == 1

    def test_the_year_control_offers_all_years_then_the_candidates_own(self) -> None:
        control = find(render(), MOD["YEAR_ID"])
        assert [o["label"] for o in control.options] == [
            MOD["ALL_YEARS"],
            *map(str, JACKSON_YEARS),
        ]
        assert control.options[0]["value"] == components.ALL_YEARS_VALUE
        assert not str(control.options[0]["value"]).isdigit()

    @pytest.mark.parametrize(
        ("years", "shown"),
        [({1832}, False), ({1828, 1832}, True), (set(JACKSON_YEARS), True)],
    )
    def test_the_year_control_shows_only_for_two_or_more_years(
        self, years: set[int], shown: bool
    ) -> None:
        body = jackson()
        body["data"] = [r for r in body["data"] if r["year"] in years]
        tree, _, several = rendered(body=body)
        assert several is shown
        (fieldset,) = of_type(tree, "Fieldset")
        assert find(fieldset, MOD["YEAR_ID"]) is not None
        assert fieldset.hidden is (not shown)
        # Hidden or not, the pills' box keeps its own-row class (#545). That no rule
        # sets a filter's display, so ``hidden`` still hides it in the filter row, is
        # TestLayoutRules.test_no_rule_sets_a_filters_display (test_dashboard_theme.py).
        assert fieldset.className.split() == ["filter", "filter-own-row"]

    def test_the_year_control_is_named_by_its_legend(self) -> None:
        (fieldset,) = of_type(render(), "Fieldset")
        (legend,) = of_type(fieldset, "Legend")
        assert legend.children == labels.LABELS["year"]


class TestCallback:
    def test_a_filter_change_writes_the_normal_form(self) -> None:
        assert (
            MOD["on_filter_change"]("1828", "GA", "")
            == "?state=GA&year_from=1828&year_to=1828"
        )

    def test_every_year_and_a_cleared_state_are_no_query(self) -> None:
        assert MOD["on_filter_change"](components.ALL_YEARS_VALUE, None, "?x") == ""

    def test_hostile_control_values_are_written_in_the_normal_form(self) -> None:
        # A callback payload is client-controlled: everything passes the one parser.
        assert MOD["on_filter_change"]("18x8", "ga", "?x") == ""
        assert MOD["on_filter_change"](1828, ["GA"], "?x") == ""
        assert MOD["on_filter_change"]("1828", "a b", "") == (
            "?year_from=1828&year_to=1828"
        )

    def test_an_unchanged_search_is_left_alone(self) -> None:
        assert MOD["on_filter_change"]("", "GA", "?state=GA") is no_update


# --- the candidate links in T2, T3 and T4 ---------------------------------------------


def _election_tables(year: str = "1824", change: Any = None) -> tuple[Any, Any]:
    """T3 from the election overview and T2 from its states page (#465), rendered
    from one doctored body."""
    overview = dash.page_registry["pages.election"]["layout"].__globals__
    states = dash.page_registry["pages.election_states"]["layout"].__globals__
    body = copy.deepcopy(RECORDED[f"/v1/elections/{year}"])
    if change is not None:
        change(body)
    index_row = election_view.index_row(INDEX, year)
    around = election_view.neighbours(INDEX, int(year))
    t2 = find(states["render"](body, index_row, [], around), states["STATES_TABLE_ID"])
    t3 = find(overview["render"](body, index_row, around), overview["NATION_TABLE_ID"])
    return t2, t3


def _candidate_links(table: Any) -> set[str]:
    return {
        link.href
        for link in of_type(table, "Link")
        if link.href.startswith("/candidate/")
    }


def test_t2_and_t3_link_each_candidate_to_their_history() -> None:
    t2, t3 = _election_tables()
    body = RECORDED["/v1/elections/1824"]
    expected = {f"/candidate/{r['candidate_slug']}" for r in body["summary"]}
    assert f"/candidate/{SLUG}" in expected
    assert _candidate_links(t2) == expected
    assert _candidate_links(t3) == expected


def test_t4_links_each_candidate_to_their_history() -> None:
    state = dash.page_registry["pages.state"]["layout"].__globals__
    body = copy.deepcopy(RECORDED["/v1/states/GA"])
    tree, _ = state["render"](
        body,
        copy.deepcopy(INDEX),
        "GA",
        [],
    )
    assert _candidate_links(find(tree, state["TABLE_ID"])) == {
        f"/candidate/{r['candidate_slug']}" for r in body["data"]
    }


@pytest.mark.parametrize(
    "row",
    [
        {"candidate_slug": "Andrew-Jackson"},
        {"candidate_slug": "../x"},
        {"candidate_slug": None},
        {"candidate_slug": 7},
        {"candidate": ""},
        {"candidate": "  "},
        # Nothing to read (#532): no link, though the cell shows the name as served.
        {"candidate": "\u200b"},
        {"candidate": None},
        # Not text, so not a name to link (PR #390, cr.6; #367's labels.has_text).
        {"candidate": 5},
        {"candidate": True},
    ],
    ids=repr,
)
def test_a_cell_without_a_slug_or_a_name_is_text_and_no_error_in_t2_t3_and_t4(
    row: dict[str, Any],
) -> None:
    cell = components.candidate_cell(
        {"candidate_slug": SLUG, "candidate": "Andrew Jackson", **row}
    )
    assert of_type(cell, "Link") == []
    # T4, which also builds its cells through components.candidate_cell.
    state = dash.page_registry["pages.state"]["layout"].__globals__
    body = copy.deepcopy(RECORDED["/v1/states/GA"])
    for r in body["data"]:
        r.update(row)
    tree, _ = state["render"](  # renders, does not raise
        body,
        copy.deepcopy(INDEX),
        "GA",
        [],
    )
    assert _candidate_links(find(tree, state["TABLE_ID"])) == set()
    if "candidate" in row and row["candidate"] is None:
        # election_states' candidate filter sorts the served names as passed (through
        # components.label_sorted_options), which a null name breaks. No served page
        # reaches that: the API types the name as required text (#367).
        return

    def doctor(body: dict[str, Any]) -> None:
        for r in [*body["data"], *body["summary"]]:
            r.update(row)

    for table in _election_tables(change=doctor):  # renders, does not raise
        assert _candidate_links(table) == set()


def test_a_slug_and_a_name_make_a_link() -> None:
    cell = components.candidate_cell({"candidate_slug": SLUG, "candidate": "Andrew J"})
    (link,) = of_type(cell, "Link")
    assert (link.href, link.children) == (f"/candidate/{SLUG}", "Andrew J")


# --- validation at the index and at render, and the request budget -------------------


def warm_client(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], Any]:
    """A process client serving a snapshot with both indexes cached: the elections
    index (prefetched) and the candidate index (the page's validate source)."""
    fetch, calls = fake_fetch(RECORDED)
    bucket = RecordingBucket()
    client = offline_client(
        fetch,
        bucket=bucket,
        prefetch_paths=lambda: [api.ELECTIONS_PATH, api.CANDIDATES_PATH],
    )
    client.ensure_refresher = lambda: None  # type: ignore[method-assign]
    client.refresh()
    calls.clear()
    bucket.waits.clear()
    monkeypatch.setattr(api, "CLIENT", client)
    return calls, bucket


class TestRequestBudget:
    def test_a_listed_candidate_renders_with_one_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, bucket = warm_client(monkeypatch)
        assert PAGE_ID in routed_ids(route(f"/candidate/{SLUG}"))
        assert calls == [JACKSON_PATH]
        assert len(bucket.waits) == 1
        calls.clear()
        assert PAGE_ID in routed_ids(route(f"/candidate/{SLUG}"))  # cached: none
        assert calls == []

    def test_filter_changes_make_no_api_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, _ = warm_client(monkeypatch)
        route(f"/candidate/{SLUG}")
        calls.clear()
        for search in ("?year_from=1828&year_to=1828", "?state=GA", ""):
            assert PAGE_ID in routed_ids(route(f"/candidate/{SLUG}", search))
        MOD["on_filter_change"]("1828", "GA", "")
        assert calls == []

    @pytest.mark.parametrize("slug", ["no-such-candidate", "Andrew-Jackson"])
    def test_an_unlisted_slug_is_not_found_and_fills_nothing(
        self, monkeypatch: pytest.MonkeyPatch, slug: str
    ) -> None:
        calls, bucket = warm_client(monkeypatch)
        response = route(f"/candidate/{slug}")
        ids = routed_ids(response)
        assert NOT_FOUND_ID in ids
        assert PAGE_ID not in ids
        assert "unavailable" not in ids
        assert calls == [] and bucket.waits == []
        text = response.get_data(as_text=True)
        # The raw path value is never echoed, and no filter is offered with no filters.
        assert slug not in text
        assert MOD["FILTER_SENTENCE"] not in text
        assert MOD["FILTER_SENTENCE_ONE_YEAR"] not in text
        # The not-found heading, and no lede: it describes a page not there (#325).
        assert MOD["NOT_FOUND_HEADING"] in text
        assert MOD["LEDE"] not in text

    def test_cold_an_unlisted_slug_costs_one_fill_of_the_index_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The elections index is cached; the candidate index is not (AC2, cold).
        _, calls, _ = cached_client(monkeypatch)
        assert NOT_FOUND_ID in routed_ids(route("/candidate/no-such-candidate"))
        assert calls == [api.CANDIDATES_PATH]
        calls.clear()
        assert NOT_FOUND_ID in routed_ids(route("/candidate/another-one"))
        assert calls == []  # the index is shared, and now cached

    def test_cold_a_listed_candidate_fills_the_index_then_its_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        assert PAGE_ID in routed_ids(route(f"/candidate/{SLUG}"))
        assert calls == [api.CANDIDATES_PATH, JACKSON_PATH]

    def test_the_lede_names_the_filters_the_page_shows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        warm_client(monkeypatch)
        body = route(f"/candidate/{SLUG}").get_data(as_text=True)
        assert MOD["FILTER_SENTENCE"] in body
        assert MOD["FILTER_SENTENCE_ONE_YEAR"] not in body

    def test_a_one_election_candidate_reads_the_one_state_sentence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bodies = copy.deepcopy(RECORDED)
        rows = bodies[JACKSON_PATH]["data"]
        bodies[JACKSON_PATH]["data"] = [r for r in rows if r["year"] == 1832]
        fetch, _ = fake_fetch(bodies)
        client = offline_client(
            fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH, api.CANDIDATES_PATH]
        )
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        response = route(f"/candidate/{SLUG}")
        assert PAGE_ID in routed_ids(response)
        body = response.get_data(as_text=True)
        assert MOD["FILTER_SENTENCE_ONE_YEAR"] in body
        assert MOD["FILTER_SENTENCE"] not in body

    def test_the_degraded_state_offers_no_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bodies = copy.deepcopy(RECORDED)
        bodies[JACKSON_PATH]["data"] = []  # malformed: the page degrades
        fetch, _ = fake_fetch(bodies)
        client = offline_client(
            fetch, prefetch_paths=lambda: [api.ELECTIONS_PATH, api.CANDIDATES_PATH]
        )
        client.ensure_refresher = lambda: None  # type: ignore[method-assign]
        client.refresh()
        monkeypatch.setattr(api, "CLIENT", client)
        response = route(f"/candidate/{SLUG}")
        ids = routed_ids(response)
        assert "unavailable" in ids and PAGE_ID not in ids
        body = response.get_data(as_text=True)
        assert MOD["LEDE"] in body
        assert MOD["FILTER_SENTENCE"] not in body
        assert MOD["FILTER_SENTENCE_ONE_YEAR"] not in body


class TestIndex:
    def test_a_listed_candidate_is_found_with_its_canonical_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cached_client(monkeypatch, source=api.CANDIDATES_PATH)
        status, head, _ = get(f"/candidate/{SLUG}?state=GA&slug=x&junk=1")
        assert status == 200
        assert head.canonical == url(f"/candidate/{SLUG}")
        assert head.og_url == url(f"/candidate/{SLUG}?state=GA")

    @pytest.mark.parametrize(
        ("search", "named"),
        [
            # A range the page does not apply is never named (#331's review).
            ("?year_from=1824&year_to=1832", ""),
            ("?year_from=1828", ""),
            ("?year_from=1828&year_to=1828", "?year_from=1828&year_to=1828"),
        ],
    )
    def test_og_url_names_only_a_year_the_page_could_apply(
        self, monkeypatch: pytest.MonkeyPatch, search: str, named: str
    ) -> None:
        cached_client(monkeypatch, source=api.CANDIDATES_PATH)
        _, head, _ = get(f"/candidate/{SLUG}{search}")
        assert head.og_url == url(f"/candidate/{SLUG}{named}")

    @pytest.mark.parametrize(
        "path",
        ["/candidate/no-such-candidate", "/candidate/Andrew-Jackson", "/candidate/a_b"],
    )
    def test_with_the_index_cached_an_unlisted_slug_is_a_404(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        _, calls, _ = cached_client(monkeypatch, source=api.CANDIDATES_PATH)
        status, head, _ = get(path)
        assert status == 404
        assert head.noindex and head.canonical is None
        assert calls == []

    @pytest.mark.parametrize(
        "path", ["/candidate/no-such-candidate", "/candidate/Andrew-Jackson"]
    )
    def test_with_the_index_cold_the_index_counts_it_matched_and_reads_nothing(
        self, monkeypatch: pytest.MonkeyPatch, path: str
    ) -> None:
        _, calls, _ = cached_client(monkeypatch)
        status, head, _ = get(path)
        assert status == 200  # D073: the index never waits on the API
        assert head.canonical == url(path)
        assert calls == []


@pytest.mark.parametrize("slug", [SLUG, "Andrew-Jackson", None, ["x"], "<script>", ""])
def test_the_title_is_total_and_names_no_candidate(slug: Any) -> None:
    assert MOD["title"](slug=slug) == f"{MOD['HEADING']} — {MOD['SITE_TITLE']}"


# --- the dropdown filter (#475) -------------------------------------------------------


def test_the_state_filter_shows_its_options_and_value() -> None:
    """The dropdown filter #475 moved onto ``components.dropdown_filter``, which no test
    named before: present by id, unset by default, set by ``state``, and its options
    the candidate's own states by name (written out here, not taken from the page)."""
    pairs = {(r["state_usps"], str(r["state"])) for r in jackson()["data"]}
    expected = [
        {"label": label, "value": value}
        for value, label in sorted(pairs, key=lambda pair: pair[1])
    ]
    dropdown = find(render(), "candidate-state")
    assert dropdown is not None
    assert dropdown.value is None
    assert dropdown.options == expected
    assert find(render("state=GA"), "candidate-state").value == "GA"
    # The label names the field and the placeholder is the page's own: the page passes
    # them to the helper in that order (#475's acceptance gate).
    (label,) = [
        label
        for label in of_type(render(), "Label")
        if label.htmlFor == "candidate-state"
    ]
    assert label.children == labels.LABELS["state"]
    assert dropdown.placeholder == MOD["STATE_PLACEHOLDER"]
    assert dropdown.placeholder != label.children


# --- the wide layout (#545, D102) -------------------------------------------------------


class TestWideLayout:
    """The candidate page's filters at desktop width (#545, the ``/candidate`` fold-in of
    #543): one ``.filters`` box that is a filter row, the year pills first on a row of
    their own, then the state dropdown. Nothing else on the page changes."""

    def test_the_pills_have_their_own_row_and_the_state_follows(self) -> None:
        tree = render()
        (box,) = classed(tree, "filters")
        assert box.className.split() == ["filters", "filter-row"]
        pills, state = box.children
        assert type(pills).__name__ == "Fieldset"
        assert pills.className.split() == ["filter", "filter-own-row"]
        assert find(pills, MOD["YEAR_ID"]) is not None
        assert state.className.split() == ["filter"]
        assert [d.id for d in of_type(state, "Dropdown")] == [MOD["STATE_ID"]]

    def test_year_buttons_take_the_own_row_class_only_when_asked(self) -> None:
        def built(**kw: Any) -> list[str]:
            pills: Any = components.year_buttons("y", "Year", "All", [1824], None, **kw)
            return list(pills.className.split())

        assert built() == ["filter"]
        assert built(own_row=False) == ["filter"]
        assert built(own_row=True) == ["filter", "filter-own-row"]


METRICS_MODULE = MOD["metrics"]

# The candidate's headline figures (#601, D112(f), (g), D115).
FIGURES = MOD["METRICS_ID"]
FIGURE_IDS: dict[str, str] = MOD["METRIC_IDS"]
COUNT = "candidate_elections_count"
CAST = "candidate_ev_cast_total"
COUNTED = "candidate_ev_counted_total"
SUMMARY: dict[str, Any] = RECORDED[api.SUMMARY_PATH]


def figure(tree: Any, key: str) -> str:
    dd = find(tree, FIGURE_IDS[key])
    assert dd is not None, key
    return "".join(texts(dd))


def figures(tree: Any) -> dict[str, str]:
    return {key: figure(tree, key) for key in FIGURE_IDS}


def with_year(year: int, **fields: Any) -> dict[str, Any]:
    """Andrew Jackson's body with ``fields`` set on every row of ``year``."""
    body = jackson()
    for row in body["data"]:
        if row["year"] == year:
            row.update(fields)
    return body


class TestCandidateFigures:
    def test_the_hand_counts(self) -> None:
        # #569's plan recordings: 3 years; cast 99 + 178 + 219 = 496, counted 496,
        # each one value across its year's 24 rows.
        assert figures(render()) == {
            COUNT: "3 elections (1824–1832)",
            CAST: "496, over 3 elections (1824–1832)",
            COUNTED: "496, over 3 elections (1824–1832)",
        }

    def test_the_count_reconciles_to_the_candidate_index(self) -> None:
        # D112(f): checked against the recorded index's ``years`` in tests only.
        (item,) = [c for c in CANDIDATES["data"] if c["candidate_slug"] == SLUG]
        years = item["years"]
        assert figure(render(), COUNT) == (
            f"{len(years)} elections ({years[0]}–{years[-1]})"
        )

    def test_they_follow_the_year_choice(self) -> None:
        assert figures(render("year_from=1828&year_to=1828")) == {
            COUNT: "1 election (1828)",
            CAST: "178, over 1 election (1828)",
            COUNTED: "178, over 1 election (1828)",
        }

    def test_a_year_outside_the_candidate_s_falls_back_to_every_year(self) -> None:
        # The year filter's own fallback; og:url names the year, and reopening it
        # renders the same figures, since the render follows the query alone.
        query = "year_from=1900&year_to=1900"
        assert figures(render(query)) == figures(render())
        assert figures(render(query)) == figures(render(query))

    @pytest.mark.parametrize(
        "query", ["state=GA", "state=GA&year_from=1828&year_to=1828"]
    )
    def test_the_state_filter_never_reaches_them_and_a_note_says_so(
        self, query: str
    ) -> None:
        # #612's review (r1.ge.5): GA's 1832 rows removed, so T5's rows under GA hold
        # 1824 and 1828 only; the figures still read all three years, national values.
        body = jackson()
        body["data"] = [
            r for r in body["data"] if not (r["year"] == 1832 and r["state_usps"] == "GA")
        ]
        unfiltered = query.replace("state=GA", "").strip("&")
        tree = render(query, body=copy.deepcopy(body))
        assert figures(tree) == figures(render(unfiltered, body=copy.deepcopy(body)))
        if "year_from" not in query:
            assert figures(tree) == figures(render())
        note = find(tree, MOD["METRICS_NOTE_ID"])
        assert " ".join(texts(note)) == labels.METRIC_ALL_STATES_NOTE
        assert find(render(unfiltered), MOD["METRICS_NOTE_ID"]) is None

    def test_og_url_reopens_the_same_figures(self) -> None:
        query = "year_from=1828&year_to=1828&state=GA"
        rows = jackson()["data"]
        chosen = MOD["filters"](MOD["parse_filters"](parse(query)), rows, JACKSON_YEARS)
        reopened = MOD["applied_search"](chosen).lstrip("?")
        assert figures(render(reopened)) == figures(render(query))

    def test_cast_and_counted_differ_as_n1_serves_them(self) -> None:
        # No recording shows cast and counted apart (#601's plan: the fixtures' one
        # snapshot), so 1828's national values become Grant's 1872 ones as N1 records
        # them; the totals reconcile to those served figures.
        (grant,) = [
            r
            for r in SUMMARY["data"]
            if r["year"] == 1872 and r["candidate_slug"] == "ulysses-s-grant"
        ]
        cast, counted = (
            grant["national_electoral_votes"],
            grant["national_electoral_votes_counted"],
        )
        assert (cast, counted) == (300, 286)
        body = with_year(
            1828,
            national_electoral_votes=cast,
            national_electoral_votes_counted=counted,
        )
        tree = render(body=body)
        assert figure(tree, CAST) == f"{99 + cast + 219}, over 3 elections (1824–1832)"
        assert figure(tree, COUNTED) == (
            f"{99 + counted + 219}, over 3 elections (1824–1832)"
        )

    @pytest.mark.parametrize("value", [177, None, 178.0])
    def test_a_year_s_rows_disagreeing_make_that_total_alone_unrecognized(
        self, value: Any
    ) -> None:
        # Architect I2: per field and per year; a null beside a value is two values.
        body = jackson()
        row = next(r for r in body["data"] if r["year"] == 1828)
        row["national_electoral_votes_counted"] = value
        tree = render(body=body)
        assert figure(tree, COUNTED) == labels.UNRECOGNIZED
        assert find(tree, FIGURE_IDS[COUNTED]).title == labels.UNRECOGNIZED_NOTE
        assert figure(tree, CAST) == "496, over 3 elections (1824–1832)"
        assert find(tree, TABLE) is not None and tree.id == PAGE_ID

    def test_a_row_without_the_field_makes_that_total_unrecognized(self) -> None:
        body = jackson()
        del body["data"][5]["national_electoral_votes"]
        tree = render(body=body)
        assert figure(tree, CAST) == labels.UNRECOGNIZED
        assert figure(tree, COUNTED) == "496, over 3 elections (1824–1832)"

    def test_a_field_missing_on_every_row_of_a_year_is_unrecognized(self) -> None:
        # #612's acceptance gate (Class B survivor): a missing field is no null, so a
        # year whose every row lacks it reads Unrecognized, never No figure (D115(e)).
        body = jackson()
        for row in body["data"]:
            if row["year"] == 1828:
                del row["national_electoral_votes"]
        tree = render(body=body)
        assert figure(tree, CAST) == labels.UNRECOGNIZED
        assert figure(tree, COUNTED) == "496, over 3 elections (1824–1832)"

    @pytest.mark.parametrize("value", [None, ""])
    def test_a_year_null_on_every_row_reads_no_figure(self, value: Any) -> None:
        # D097: a sum with any null reads no figure; the other total stays.
        tree = render(body=with_year(1828, national_electoral_votes=value))
        assert figure(tree, CAST) == labels.METRIC_NO_FIGURE[CAST]
        assert figure(tree, COUNTED) == "496, over 3 elections (1824–1832)"

    def test_a_null_beside_a_blank_in_one_year_is_one_null(self) -> None:
        # Owner, option A at #612's review (r1.cr.3, D115 amendment): ``is_blank`` is
        # the rule of what is null, so the year holds a null and the total no figure.
        body = with_year(1828, national_electoral_votes=None)
        next(r for r in body["data"] if r["year"] == 1828)["national_electoral_votes"] = ""
        tree = render(body=body)
        assert figure(tree, CAST) == labels.METRIC_NO_FIGURE[CAST]
        assert figure(tree, COUNTED) == "496, over 3 elections (1824–1832)"

    @pytest.mark.parametrize("value", [True, 1.5, -3, "x"])
    def test_a_value_no_total_can_hold_is_unrecognized(self, value: Any) -> None:
        tree = render(body=with_year(1828, national_electoral_votes=value))
        assert figure(tree, CAST) == labels.UNRECOGNIZED

    def test_the_count_is_metrics_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # #612's review (r2.recheck.1, D097, D115 amendment): the count is computed in
        # ``metrics``, over the distinct years, and ``labels`` only words it.
        seen: list[Any] = []

        def count(rows: Any) -> int:
            seen.append(rows)
            return 7

        monkeypatch.setattr(METRICS_MODULE, "count", count)
        assert figure(render(), COUNT) == "7 elections (1824–1832)"
        assert seen == [{1824, 1828, 1832}]

    def test_they_sit_in_the_card_after_the_controls_and_before_the_count(
        self,
    ) -> None:
        tree = render()
        card = in_one_card(tree, FIGURES)
        order = [
            getattr(n, "id", None) or getattr(n, "className", None)
            for n in components._within(card.children)
        ]
        assert order.index(MOD["YEAR_ID"]) < order.index(FIGURES) < order.index("count")

    def test_the_page_still_makes_one_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls, _ = warm_client(monkeypatch)
        ids = routed_ids(route(f"/candidate/{SLUG}"))
        assert FIGURES in ids and all(i in ids for i in FIGURE_IDS.values())
        assert calls == [JACKSON_PATH]
