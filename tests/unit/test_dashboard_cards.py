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
from tests.dashboard_cards import every_card, is_card
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
    "/state/<usps>": 2,
    "/state/<usps>/per-capita": 1,
    "/candidate/<slug>": 1,
    "/not-found-404": 0,
}

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
        assert props["className"] == components.CARD_CLASS == "card"
        # Nothing a reader's assistive technology or the Tab key would meet: the card
        # adds no landmark, name, role or tab stop (#567's tab-order criterion).
        assert set(props) == {"children", "className"}
        assert [type(kid).__name__ for kid in card.children] == ["H2", "P"]

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

    def test_every_card_is_a_direct_child_of_the_page_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A card frames a run of the page's own content, never something nested in
        # another element (a pair's column, a section's box).
        for key, tree in all_pages(monkeypatch).items():
            for node, above in with_ancestors(tree):
                if is_card(node):
                    assert not any(is_card(a) for a in above), key
                    assert type(above[-1]) is html.Div, key
                    assert node in above[-1].children, key

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
                if name in ("H1", "Footer") or {"lede", "section-links"} & set(
                    classes
                ):
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
