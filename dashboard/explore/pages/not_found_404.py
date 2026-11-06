"""The page for a link that matches no page (#325, D083).

Dash's custom-404 convention: its router renders the page whose module is named
``not_found_404`` for a path no page matches, and app.py's index answers that path 404
with ``noindex``, taking the title from :data:`NOT_FOUND` here, so the page, the browser
tab and a link preview say one thing. Its own registered path answers 404 too: it is
never served as a page of its own (D073). It reads no data, so it has no degraded state
and no success marker.
"""

from __future__ import annotations

from typing import Any

import dash
from dash import dcc, html

from explore import api

#: The wrapper of this page's one state.
NOT_FOUND_ID = "page-not-found"

#: Its heading, sentence and link. "Link" is the project's word for what was not found.
NOT_FOUND_HEADING = "Page not found"
NOT_FOUND_SENTENCE = "This link does not match any page on this site."
NOT_FOUND_LINK = "Go to the home page"
NOT_FOUND = api.NotFound(NOT_FOUND_HEADING, NOT_FOUND_SENTENCE)

dash.register_page(
    __name__,
    title=NOT_FOUND.title,
    description=NOT_FOUND_SENTENCE,
    prefetch=(),
    on_miss=(),
    not_found=NOT_FOUND,
    # The site navigation link this page marks (#448):
    # a link that matches no page marks nothing.
    nav=None,
)


def layout(**_params: Any) -> html.Div:
    return html.Div(
        [
            html.H1(NOT_FOUND_HEADING),
            html.Div(
                [html.P(NOT_FOUND_SENTENCE), dcc.Link(NOT_FOUND_LINK, href="/")],
                id=NOT_FOUND_ID,
            ),
        ]
    )
