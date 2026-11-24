"""Page section cards (#567, D111): the helper, and every registered page's cards.

``components.card`` frames one page section in a plain ``div``. These tests pin the
helper (no id, role, landmark or tab stop, so reading and tab order are unchanged; no
card in a card, and none in a pair's column) and, on every registered page rendered
from recorded responses, how many cards it shows, that every section heading outside
the provenance footer is in one, and that each chart shares its card with its companion
table. The section-level degraded and empty branches are checked beside their pages'
own tests (``in_one_card``); the whole-page not-found and degraded states, which have
no sections, are checked here to have none. What a browser draws is the e2e suite's
(``tests/e2e/``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import dash
import pytest
from dash import html

from explore import api, charts, components
from tests.dashboard_cards import CARD, every_card, is_card
from tests.unit.test_dashboard_export import all_pages, page_key, page_of

#: Each registered page's card count on its default success render: one per page
#: section (#567's plan inventory). The custom-404 page has none.
CARD_COUNTS = {
    "/": 1,
    "/states": 1,
    "/elections": 1,
    "/elections/majority": 1,
    "/elections/over-time": 1,
    "/election/<year>": 1,
    "/election/<year>/states": 1,
    "/election/<year>/per-capita": 1,
    "/state/<usps>": 1,  # C7 and C10 with their one table (#618); T4 left (#619)
    "/state/<usps>/elections": 1,  # T4 with its filters (#619)
    "/state/<usps>/per-capita": 1,
    "/candidate/<slug>": 1,
    "/not-found-404": 0,
}


def card_parent_id(key: str) -> str | None:
    """The id of the ``Div`` whose children a page's cards are: the page's success
    marker, or ``None`` on home, whose marker is the coverage list inside its card, so
    its card sits in the render's unnamed body (pinned by position in the test)."""
    return None if key == "/" else str(page_of(key)["success"])


#: Everything a page body may hold beside its cards, by component type and class (D111
#: (b)): the page's own chrome, never a section's content. A section's table, chart,
#: filters, notes or column-name list found here is outside its card.
CHROME: frozenset[tuple[str, str | None]] = frozenset(
    {
        ("H1", None),
        ("P", "lede"),
        ("P", "next"),  # home's two browse links: navigation
        ("Location", None),
        ("Nav", "section-links"),
        ("Nav", "neighbor-nav"),
        ("Footer", "provenance-footer"),
    }
)

#: A path value each templated page refuses, so it renders its not-found state.
NOT_FOUND_VALUES = {"year": "1825", "usps": "ZZ", "slug": "no-such-candidate"}


def with_ancestors(node: Any, above: tuple[Any, ...] = ()) -> Iterator[tuple[Any, tuple[Any, ...]]]:
    """Every component under ``node``, depth first, with the components above it."""
    if isinstance(node, (list, tuple)):
        for kid in node:
            yield from with_ancestors(kid, above)
    elif hasattr(node, "to_plotly_json"):
        yield node, above
        yield from with_ancestors(getattr(node, "children", None), (*above, node))


def the_card_of(tree: Any, ident: str) -> Any:
    """The one card above the element ``ident``; fails if it is in none."""
    (found,) = [
        [a for a in above if is_card(a)]
        for node, above in with_ancestors(tree)
        if getattr(node, "id", None) == ident
    ]
    (card,) = found
    return card


class TestCard:
    def test_a_card_is_a_plain_div_with_no_name_role_or_tab_stop(self) -> None:
        card = components.card([html.H2("A section"), html.P("Its text")])
        assert type(card) is html.Div
        props = card.to_plotly_json()["props"]
        assert props["className"] == CARD == "card"
        # Nothing a reader's assistive technology or the Tab key would meet: the card
        # adds no landmark, name, role or tab stop (#567's tab-order criterion).
        assert set(props) == {"children", "className"}
        assert [type(kid).__name__ for kid in card.children] == ["H2", "P"]

    def test_a_card_refuses_one_component_for_its_children(self) -> None:
        # A component iterates over its descendants' ids, so it is refused rather
        # than turned into a card of id strings (#567's review).
        with pytest.raises(TypeError, match="not one component"):
            components.card(html.Div([html.P("x", id="x")]))  # type: ignore[arg-type]

    @pytest.mark.parametrize("table_first", [True, False])
    def test_a_card_refuses_a_card_beside_a_table(self, table_first: bool) -> None:
        # The refusal skips a table's cells, never the elements around the table: it
        # steps over the table and goes on, in whichever order the walk meets the two
        # (a walk that stopped at the first table would pass one order and not the
        # other; #567's acceptance gate, Class B).
        scroll = html.Div(html.Table([]), className="table-scroll")
        nested = html.Div([components.card([html.P("x")])])
        children = [scroll, nested] if table_first else [nested, scroll]
        with pytest.raises(ValueError, match="a card holds a card"):
            components.card(children)

    def test_a_card_keeps_its_children_in_source_order(self) -> None:
        kids = [html.H2("a", id="a"), html.P("b", id="b"), html.Div(id="c")]
        assert components.card(kids).children == kids

    @pytest.mark.parametrize("depth", [0, 1, 3])
    def test_a_card_refuses_a_card_at_any_depth(self, depth: int) -> None:
        inner: Any = components.card([html.P("inner")])
        for _ in range(depth):
            inner = html.Div([inner])
        with pytest.raises(ValueError, match="a card holds a card"):
            components.card([html.H2("outer"), inner])

    @pytest.mark.parametrize("side", ["left", "right"])
    def test_a_pair_refuses_a_card_in_either_column(self, side: str) -> None:
        card = components.card([html.P("framed")])
        held: dict[str, list[Any]] = {"left": [html.P("x")], "right": [html.P("y")]}
        held[side] = [html.Div([card])]
        with pytest.raises(ValueError, match="holds a card"):
            components.pair(held["left"], held["right"], "test-pair")

    def test_a_card_holds_a_pair(self) -> None:
        pair = components.pair([html.P("x")], [html.P("y")], "test-pair")
        assert components.card([pair]).children == [pair]


class TestEveryPageCards:
    def test_the_counts_name_every_registered_page(self) -> None:
        assert set(CARD_COUNTS) == {page_key(p) for p in dash.page_registry.values()}

    def test_each_page_shows_one_card_per_section(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key, tree in all_pages(monkeypatch).items():
            assert len(every_card(tree)) == CARD_COUNTS[key], key

    def test_every_card_is_a_child_of_the_page_body_itself(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A card frames a run of the page body's own children, so its parent is the
        # page's success Div (home: its render's body), never a wrapper, a section's
        # box or a pair's column, and never another card.
        for key, tree in all_pages(monkeypatch).items():
            for node, above in with_ancestors(tree):
                if is_card(node):
                    parent = above[-1]
                    assert not any(is_card(a) for a in above), key
                    assert type(parent) is html.Div, key
                    assert getattr(parent, "id", None) == card_parent_id(key), key
                    if key == "/":
                        # Home's layout is its heading, its lede and the render's
                        # body, so the card's parent is that body itself and not a
                        # wrapper inside it (#567's review, round 2).
                        assert above == (tree, list(tree.children)[-1]), key
                    assert node in parent.children, key

    def test_beside_its_cards_a_page_body_holds_only_chrome(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Every section's whole content is in its card (#567's review): whatever
        # else sits in the body that holds the cards is page chrome from a closed
        # set, so a table, chart, filter, note or list left outside a card fails.
        for key, tree in all_pages(monkeypatch).items():
            bodies = {
                id(above[-1]): above[-1]
                for node, above in with_ancestors(tree)
                if is_card(node)
            }
            assert len(bodies) == (0 if CARD_COUNTS[key] == 0 else 1), key
            for body in bodies.values():
                for kid in body.children:
                    if is_card(kid):
                        continue
                    kind = (type(kid).__name__, getattr(kid, "className", None))
                    assert kind in CHROME, (key, kind)

    def test_every_section_heading_outside_the_footer_is_in_a_card(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key, tree in all_pages(monkeypatch).items():
            for node, above in with_ancestors(tree):
                if type(node).__name__ != "H2":
                    continue
                footer = any(type(a).__name__ == "Footer" for a in above)
                carded = any(is_card(a) for a in above)
                # The provenance footer is page chrome with its own edge (D111).
                assert carded != footer, (key, node.children)

    def test_the_page_heading_lede_and_section_links_stay_outside(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key, tree in all_pages(monkeypatch).items():
            for node, above in with_ancestors(tree):
                name = type(node).__name__
                classes = str(getattr(node, "className", "") or "").split()
                if name in ("H1", "Footer") or {
                    "lede",
                    "section-links",
                    "neighbor-nav",
                } & set(classes):
                    assert not any(is_card(a) for a in above), (key, name, classes)

    def test_each_chart_shares_its_card_with_its_companion_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        trees = all_pages(monkeypatch)
        live = {k: c for k, c in charts.CHARTS.items() if not c.retired}
        assert live
        for chart_id, chart in live.items():
            tree = trees[chart.page]
            assert the_card_of(tree, charts.dom_id(chart_id)) is the_card_of(
                tree, chart.table
            ), chart_id


class _DownClient:
    """A client whose every view fails, as when the API is down: each page shows its
    whole-page degraded state."""

    def view(self) -> Any:
        raise api.ApiUnavailable("GET: HTTP 503")


class TestNoSectionNoCard:
    @pytest.mark.parametrize(
        "key", [k for k in CARD_COUNTS if k != "/not-found-404"]
    )
    def test_the_degraded_page_has_no_card(
        self, key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(api, "CLIENT", _DownClient())
        page = page_of(key)
        values = {
            name: NOT_FOUND_VALUES[name]
            for name in NOT_FOUND_VALUES
            if f"<{name}>" in key
        }
        tree = page["layout"](**values)
        assert components.UNAVAILABLE_MESSAGE in str(tree.to_plotly_json())
        assert every_card(tree) == []

    @pytest.mark.parametrize(
        "key", [k for k in CARD_COUNTS if "<" in k]
    )
    def test_the_not_found_page_has_no_card(
        self, key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        trees = all_pages(monkeypatch)  # installs the recorded client
        assert trees[key] is not None
        page = page_of(key)
        values = {
            name: value for name, value in NOT_FOUND_VALUES.items() if f"<{name}>" in key
        }
        tree = page["layout"](**values)
        ids = {getattr(node, "id", None) for node, _ in with_ancestors(tree)}
        assert page["success"] not in ids and any(
            str(i).endswith("not-found") for i in ids
        ), ids
        assert every_card(tree) == []
