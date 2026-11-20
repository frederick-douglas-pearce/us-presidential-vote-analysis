"""Reading a page's section cards in a unit test (#567, D111).

A page's sections sit in ``components.card`` divs, direct children of the page's
success ``Div``. A test that pins where an element sits names the card that holds it:
:func:`card_children` checks that the page's child at a position *is* a card and
returns what that card holds, so a test indexes the page, then the card, and an
element in the wrong card, or in none, fails. Nothing here flattens a card away.
"""

from __future__ import annotations

from typing import Any

from explore import components

#: The card class, written out: ``components`` keeps its constant private, so no
#: page can import it round the card lint (#567's review); ``TestCard`` pins the value.
CARD = "card"


def is_card(node: Any) -> bool:
    """Whether ``node`` carries the card class, as one class word among its classes:
    the same reading ``components.card``'s refusal makes, so the tests and the runtime
    agree on what a card is."""
    return CARD in str(getattr(node, "className", None) or "").split()


def cards(page: Any) -> list[Any]:
    """The cards among ``page``'s direct children, in source order."""
    return [kid for kid in page.children if is_card(kid)]


def card_children(page: Any, position: int) -> list[Any]:
    """What the card at ``page.children[position]`` holds; fails if that child is not
    a card."""
    kid = list(page.children)[position]
    assert is_card(kid), (position, kid)
    return list(kid.children)


def card_holding(page: Any, node: Any) -> Any:
    """The one direct-child card of ``page`` whose children include ``node``."""
    (held,) = [card for card in cards(page) if node in card.children]
    return held


def every_card(tree: Any) -> list[Any]:
    """Every card anywhere in ``tree``, depth first (the runtime's own walk,
    ``components._within``): a degraded state's layout wraps its body, so this reaches
    cards below the success ``Div`` too."""
    return [node for node in components._within(tree) if is_card(node)]


def in_one_card(tree: Any, ident: str, *, total: int = 1) -> Any:
    """Asserts ``tree`` holds ``total`` cards and exactly one of them holds the element
    ``ident``, and returns that card."""
    held = every_card(tree)
    assert len(held) == total, (ident, len(held))
    holding = []
    for card in held:
        inside = components._within(card.children)
        if any(getattr(node, "id", None) == ident for node in inside):
            holding.append(card)
    assert len(holding) == 1, (ident, len(holding))
    return holding[0]
