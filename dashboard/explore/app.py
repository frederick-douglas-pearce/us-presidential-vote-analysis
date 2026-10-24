"""The Dash app and its WSGI entry point (``explore.app:server``, per ``app.yaml``).

Beyond Dash itself this module adds five things, all host-level:

- **The canonical host.** A request to the App Engine default host (``*.appspot.com``)
  301s to :data:`~explore.config.CANONICAL_HOST`, so the vendor domain never stays in
  the address bar. Two exemptions: ``/_ah/*`` (App Engine's own warmup) and any
  ``-dot-`` host (``<version>-dot-…``, which the deploy workflow probes before moving
  traffic, and ``default-dot-…``, which only someone who typed it reaches; the
  canonical link names ``explore.`` on both).
- **A canonical link and ``og:url`` from the page Dash matches, and a 404 for the
  rest** (#312, D073). :func:`resolve` asks Dash's own router matcher which page a path
  is. A matched path gets a canonical link built from the page's path template and its
  variables, with no query string, and an ``og:url`` that adds the query normalized by
  the page's own ``query=`` parser, so a shared filtered card reopens the filtered view.
  A path no page matches, one a page's ``validate=`` rejects from the already-cached
  source it names (a template source resolved from the cached index, #279), one whose
  percent-escapes change it when decoded, or Dash's custom 404 page, answers 404 with
  ``noindex`` and neither tag. A source not cached yet counts as matched: the index
  never waits on the API (D071(g)). Dash's own page meta tags are rebuilt here
  without its ``twitter:url``, which is the raw request URL.
  The index never decides what a render may fetch: a templated page validates what
  its layout receives, through ``api.accepted``.
- **The path's value wins** (#326, D081). Dash's router merges the query string over a
  page's path variables, so ``/election/1824?year=1872`` would render 1872 under a
  canonical link naming 1824. Before the router runs, :func:`strip_path_variables`
  drops from its routing request every query key named after a path variable of the
  page the path matches, so the render always matches the canonical link.
- **The refresher.** ``/_ah/warmup`` refreshes the cache synchronously, on the request
  thread, and only then starts the refresher, so the instance takes traffic with a
  filled cache and one ``/v1/meta`` call. Every other request makes sure the refresher
  is running. Neither happens at import, so importing this module makes no network
  call.
- **No validation layout.** ``suppress_callback_exceptions=True`` stops Dash from
  calling every page's ``layout()`` on the first request and embedding the result in
  every index page. The index HTML therefore carries no data and never waits on the
  API, which is what keeps a link preview's time to first byte short (D071(g)).
"""

from __future__ import annotations

import html as html_escaping
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote_plus, urlsplit

import dash
import flask
import werkzeug
from dash import html

# Dash privates, each pinned by name and behavior in test_dashboard_app.py
# (TestDashPrivates), so an upgrade that moves one fails the build: the router's own
# matcher, the query parser whose dict the router hands a layout, the card tags, and
# the ids of the Pages router's two outputs, which name its routing request.
from dash._pages import _page_meta_tags, _parse_query_string, _path_to_page
from dash.dash import _ID_CONTENT, _ID_STORE

from explore import api
from explore import query as query_syntax  # `query` is resolve's parameter
from explore.config import CANONICAL_HOST, SITE_TITLE

log = logging.getLogger(__name__)

# App Engine collects stdout/stderr; INFO carries the cache's "serving snapshot" and
# "api fetch" lines, which is how API calls are counted (runbook §12). A no-op when the
# host process (a test runner, say) has configured logging already.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

VENDOR_HOST_SUFFIX = ".appspot.com"
VERSION_HOST_MARKER = "-dot-"
WARMUP_PATH = "/_ah/warmup"


def canonical_url(path: str) -> str:
    """The canonical URL for a request path, re-quoted.

    ``flask.request.path`` is percent-decoded, and Dash answers every path, so the path
    is attacker-controlled text: quoting it keeps ``"``, ``<``, ``?``, ``#`` and line
    breaks out of both the HTML this URL is written into and the redirect built from it.
    """
    return f"https://{CANONICAL_HOST}{quote(path, safe='/')}"


@dataclass(frozen=True)
class Resolution:
    """What a request path is: its canonical URL and ``og:url``, or neither (a 404)."""

    canonical: str | None
    og_url: str | None

    @property
    def found(self) -> bool:
        return self.canonical is not None


NOT_FOUND = Resolution(canonical=None, og_url=None)

_VARIABLE_RE = re.compile("<(.*?)>")


def raw_path(environ: dict[str, Any]) -> str | None:
    """The request path as the client sent it, before percent-decoding, if known.

    gunicorn (``app.yaml``'s entrypoint) keeps the request target in ``RAW_URI``;
    other servers may set ``REQUEST_URI``. Either carries the query string, and may be
    in absolute form. A fragment is dropped, as gunicorn drops it from ``PATH_INFO``,
    and the result is normalized as Werkzeug normalizes ``request.path`` (one leading
    slash), so only a percent-escape can make the two differ.
    """
    sent = environ.get("RAW_URI") or environ.get("REQUEST_URI")
    if not isinstance(sent, str) or not sent:
        return None
    target = sent.partition("#")[0].partition("?")[0]
    if not target.startswith("/"):
        target = urlsplit(target).path
    return "/" + target.lstrip("/")


def resolve(
    path: str, query: str, snapshot: api.Snapshot | None, raw: str | None = None
) -> Resolution:
    """Resolve a request path against the page registry, with Dash's router matcher.

    ``path`` is the decoded request path and ``raw`` the path as sent, when known.
    Dash's router matches the browser's still-encoded ``location.pathname``, so a path
    that decoding changes would match differently there; no page path needs an escape,
    so such a path is junk and is not found. ``snapshot`` is read once by the caller
    and never waited on: a page's ``validate`` source missing from it counts as
    matched, never as rejected.
    """
    if raw is not None and raw != path:
        return NOT_FOUND
    page, path_vars = _path_to_page(path.strip("/"))
    # Dash's own custom-404 convention: its router renders this module for a path no
    # page matches, and it must not be served as a page of its own.
    if not page or page["module"].split(".")[-1] == "not_found_404":
        return NOT_FOUND
    path_vars = path_vars or {}
    validate: api.Validate | None = page.get("validate")
    if validate is not None:
        if not api.well_formed(path_vars):
            return NOT_FOUND
        body = (
            api.cached_source(validate[0], snapshot.responses)
            if snapshot is not None
            else None
        )
        if body is not None and not api.judge(validate, path_vars, body):
            return NOT_FOUND
    template = page.get("path_template")
    concrete = (
        _VARIABLE_RE.sub(lambda m: path_vars[m.group(1)], template)
        if template
        else page["path"]
    )
    canonical = canonical_url("/" + concrete.strip("/"))
    og_url = canonical
    parser = page.get("query")
    if parser is not None:
        pairs = parser(_parse_query_string(f"?{query}") if query else {})
        # De-duplicated, so a repeated filter names the same URL as a single one.
        og_url += query_syntax.encode_search(pairs)
    return Resolution(canonical=canonical, og_url=og_url)


def _tag(name: str, attributes: dict[str, Any]) -> str:
    # Escaped, quotes included: every value here can carry request text.
    attrs = " ".join(
        f'{key}="{html_escaping.escape(str(value), quote=True)}"'
        for key, value in attributes.items()
    )
    return f"<{name} {attrs}>"


#: The ``flask.g`` attribute carrying one index request's resolved tags.
_G_TAGS = "explore_head_tags"


class ExploreDash(dash.Dash):
    """Dash with a canonical link and ``og:url`` from the matched page, and 404s."""

    def index(self, *args: Any, **kwargs: Any) -> Any:
        # Resolved once, against one read of the snapshot: the status and the tags
        # below come from the same answer even if the refresher swaps meanwhile.
        resolution = resolve(
            flask.request.path,
            flask.request.query_string.decode("utf-8", "replace"),
            api.CLIENT.snapshot,
            raw_path(flask.request.environ),
        )
        cards = [
            meta
            for meta in _page_meta_tags(self, self.backend.request_adapter())
            if meta.get("property") != "twitter:url"  # the raw request URL
        ]
        if resolution.found:
            own = [
                _tag("meta", {"property": "og:url", "content": resolution.og_url}),
                _tag("link", {"rel": "canonical", "href": resolution.canonical}),
            ]
        else:
            own = [_tag("meta", {"name": "robots", "content": "noindex"})]
        # Dash's card tags lead and ours follow its own metas, as Dash orders them.
        setattr(flask.g, _G_TAGS, ([_tag("meta", meta) for meta in cards], own))
        page = super().index(*args, **kwargs)
        if not resolution.found:
            return flask.make_response(page, 404)
        return page

    def interpolate_index(
        self,
        metas: Any = "",
        title: Any = "",
        css: Any = "",
        config: Any = "",
        scripts: Any = "",
        app_entry: Any = "",
        favicon: Any = "",
        renderer: Any = "",
    ) -> Any:
        tags = getattr(flask.g, _G_TAGS, None)
        if tags is None:  # never recompute: the status was decided from these
            raise RuntimeError("interpolate_index outside ExploreDash.index")
        cards, own = tags
        metas = "\n      ".join([*cards, f"{metas}", *own])
        return super().interpolate_index(
            metas=metas,
            title=title,
            css=css,
            config=config,
            scripts=scripts,
            app_entry=app_entry,
            favicon=favicon,
            renderer=renderer,
        )


app = ExploreDash(
    __name__,
    use_pages=True,
    compress=True,
    suppress_callback_exceptions=True,
    include_pages_meta=False,  # rebuilt in ExploreDash.index, without twitter:url
    title=SITE_TITLE,
    update_title=None,  # type: ignore[arg-type]  # Dash documents None: no "Updating…"
)
server = app.server
app.layout = html.Main(dash.page_container, className="explore")


#: The Pages router's callback as a routing request names it in ``output`` and Dash
#: keys it in ``callback_map``: its two outputs, in Dash's multi-output form.
ROUTER_OUTPUT = f"..{_ID_CONTENT}.children...{_ID_STORE}.data.."

#: The Flask endpoint Dash dispatches every callback request through.
DISPATCH_ENDPOINT = app.config.routes_pathname_prefix + "_dash-update-component"


def strip_path_variables(pathname: str, search: str) -> str:
    """``search`` without any key named after a path variable of ``pathname``'s page.

    The page is the one Dash's router matches, by its own matcher and strip. Keys are
    read as the router's ``parse_qs(keep_blank_values=True)`` reads them: the text
    after ``?``, split on ``&`` only, each part's key everything before its first
    ``=`` (all of it, with no ``=``), ``+`` and percent-escapes decoded. So
    ``ye%61r=1`` and a bare ``year`` are dropped, and ``year%3Dx=1`` (key ``year=x``)
    is kept. Every other part is kept byte for byte, in order, empty ones included.
    """
    if not search.startswith("?"):
        return search
    _, path_vars = _path_to_page(app.strip_relative_path(pathname))
    if not path_vars:
        return search
    kept = [
        part
        for part in search[1:].split("&")
        if unquote_plus(part.partition("=")[0]) not in path_vars
    ]
    return "?" + "&".join(kept)


def _strip_routing_request() -> None:
    """Make the path's value win in a Pages routing request, before Dash reads it.

    Gated as Dash dispatches: the callback endpoint, and the router's ``output``, which
    is what Dash looks the callback up by. ``pathname`` and ``search`` are read by
    position, as Dash hands them to the router, never by input id. The filtered
    ``search`` is written into the parsed body Werkzeug caches, which is the object
    Dash's own ``get_json()`` returns. Anything malformed is left for Dash to refuse.
    """
    request = flask.request
    if request.method != "POST" or request.endpoint != DISPATCH_ENDPOINT:
        return
    # Never force=True: that would cache a parse Dash refuses for a non-JSON type.
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or body.get("output") != ROUTER_OUTPUT:
        return
    inputs = body.get("inputs")
    if not isinstance(inputs, list) or len(inputs) < 2:
        return
    location, query = inputs[0], inputs[1]
    if not isinstance(location, dict) or not isinstance(query, dict):
        return
    pathname, search = location.get("value"), query.get("value")
    if isinstance(pathname, str) and isinstance(search, str):
        query["value"] = strip_path_variables(pathname, search)


def redirect_target(host: str, path: str, query: str) -> str | None:
    """Where a request should be sent instead, or ``None`` to serve it here."""
    name = host.split(":", 1)[0].lower().rstrip(".")
    if not name.endswith(VENDOR_HOST_SUFFIX):
        return None
    if VERSION_HOST_MARKER in name or path.startswith("/_ah/"):
        return None
    return canonical_url(path) + (f"?{query}" if query else "")


@server.before_request
def _before_request() -> werkzeug.Response | None:
    target = redirect_target(
        flask.request.host,
        flask.request.path,
        flask.request.query_string.decode("latin-1"),
    )
    if target is not None:
        return flask.redirect(target, code=301)
    if flask.request.path != WARMUP_PATH:  # warmup starts it after its own refresh
        api.CLIENT.ensure_refresher()
    _strip_routing_request()
    return None


@server.route(WARMUP_PATH)
def _warmup() -> tuple[str, int]:
    """App Engine's warmup request: fill the cache before the instance takes traffic.

    Always 200. A failure is logged and the refresher retries; failing warmup would only
    make App Engine start the instance without it.
    """
    try:
        api.CLIENT.refresh()
    except Exception:
        log.exception("warmup refresh failed; the refresher will retry")
    api.CLIENT.ensure_refresher()
    return "", 200
