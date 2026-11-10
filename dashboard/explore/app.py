"""The Dash app and its WSGI entry point (``explore.app:server``, per ``app.yaml``).

Beyond Dash itself this module adds nine things: seven host-level, and two that live
in the browser, the theme choice and the site navigation's current-page marker:

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
  A path is matched decoded once, as Dash's router matches it (:func:`router_key`,
  D089), so a percent-encoded path resolves as the path it spells. A path no page
  matches, one a page's ``validate=`` rejects from the already-cached source it names
  (a template source resolved from the cached index, #279), or Dash's custom 404 page,
  answers 404 with ``noindex`` and neither tag. A source not cached yet counts as
  matched: the index never waits on the API (D071(g)). The page's card tags are built
  here, without Dash's ``twitter:url``, which is the raw request URL.
  The index never decides what a render may fetch: a templated page validates what
  its layout receives, through ``api.accepted``.
- **A title that names only what the index has checked** (#325, D083). :func:`resolve`
  also decides the title and description, which the index writes as ``<title>`` and
  the card tags. A not-found path's are its page's ``not_found=`` heading and
  sentence (:class:`~explore.api.NotFound`), or the custom-404 page's; a path whose
  ``validate`` source is not cached yet gets the page's title called with no
  variables, which names no year or code. Dash's client router sets the browser tab
  from the registry's ``title`` after the layout ran, so :func:`follow_validation`
  wraps each validated page's ``title`` to follow the same rule from the snapshot in
  memory.
- **The path's value wins** (#326, D081). Dash's router merges the query string over a
  page's path variables, so ``/election/1824?year=1872`` would render 1872 under a
  canonical link naming 1824. Before the router runs, :func:`strip_path_variables`
  drops from its routing request every query key named after a path variable of the
  page the path matches, so the render always matches the canonical link. Two ways
  around it are closed (D089): :func:`refuse_encoded_dispatch` answers 415 to a
  content-encoded callback request, whose body the strip cannot read, and the app
  turns Dash's MCP server off (``enable_mcp=False``), which would run callbacks through
  a route of its own.
- **The refresher.** ``/_ah/warmup`` refreshes the cache synchronously, on the request
  thread, and only then starts the refresher, so the instance takes traffic with a
  filled cache and one ``/v1/meta`` call. Every other request makes sure the refresher
  is running. Neither happens at import, so importing this module makes no network
  call.
- **No validation layout.** ``suppress_callback_exceptions=True`` stops Dash from
  calling every page's ``layout()`` on the first request and embedding the result in
  every index page. The index HTML therefore carries no data and never waits on the
  API, which is what keeps a link preview's time to first byte short (D071(g)).
- **No local plotly.js** (#430). :meth:`ExploreDash._setup_plotlyjs` registers dcc's
  plotly.js by its CDN address only, so the app never serves the 4.8 MB file, which
  no page uses yet; and a component-suite path Dash never registered answers 404
  (Flask's default body) rather than 500.
- **The theme choice** (#359, #447). A head script applies a saved Dark or Light
  choice to ``<html>`` before first paint, so a reload never flashes the other
  palette; the shared layout carries the toggle
  (:func:`~explore.components.theme_control`) above every page and the store holding
  the theme in effect, which one inline clientside callback keeps current. Nothing
  about it reaches the server, the URL or ``og:url``.
- **The site navigation** (#448). The header holds the site navigation
  (:func:`~explore.components.site_nav`) before the toggle. Each page names the link
  it marks with ``nav=`` in ``dash.register_page``; :data:`NAV_TABLE` gathers them
  from the registry, and :data:`NAV_CALLBACK`, an inline clientside callback on the
  Pages router's own Location, matches the pathname as the router does with the app
  at the root (the only prefix it is served under, checked at import) and writes
  ``aria-current`` onto the marked link, with no server round trip.
"""

from __future__ import annotations

import enum
import html as html_escaping
import json
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, unquote_plus

import dash
import flask
import werkzeug
import werkzeug.exceptions
from dash import MATCH, Input, Output, State, clientside_callback, dcc, html

# Dash privates, each pinned by name and behavior in test_dashboard_app.py
# (TestDashPrivates), so an upgrade that moves one fails the build: the router's own
# matcher, the query parser whose dict the router hands a layout, the ids of the
# Pages router's two outputs, which name its routing request, and the id of its
# Location, whose pathname the site navigation's marker follows (#448).
from dash._pages import _parse_query_string, _path_to_page
from dash.dash import _ID_CONTENT, _ID_LOCATION, _ID_STORE

from explore import api, charts, components, labels
from explore import query as query_syntax  # `query` is resolve's parameter
from explore.config import API_BASE, CANONICAL_HOST, SITE_TITLE

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
    """What a request path is: its canonical URL and ``og:url``, or neither (a 404);
    its title and description; the page whose card it shows (#325); and the path
    variables the page's ``validate`` accepted, ``None`` unless it did (#465: only an
    accepted value may build a redirect)."""

    canonical: str | None
    og_url: str | None
    title: str
    description: str
    page: Mapping[str, Any]
    path_vars: Mapping[str, str] | None = None

    @property
    def found(self) -> bool:
        return self.canonical is not None


_VARIABLE_RE = re.compile("<(.*?)>")

#: The module name, last segment, of Dash's custom-404 page: its router renders that
#: page for a path no page matches (``pages/not_found_404.py``).
NOT_FOUND_MODULE = "not_found_404"


def is_not_found_page(page: Mapping[str, Any]) -> bool:
    """Whether ``page`` is Dash's custom-404 page, by the test Dash's router uses."""
    return str(page.get("module", "")).split(".")[-1] == NOT_FOUND_MODULE


class Check(enum.Enum):
    """A page's verdict on path variables, from the snapshot already in memory."""

    ACCEPTED = "accepted"
    REFUSED = "refused"
    UNCHECKED = "unchecked"


def checked(
    page: Mapping[str, Any], path_vars: dict[str, Any], snapshot: api.Snapshot | None
) -> Check:
    """``page``'s ``validate`` verdict on ``path_vars``, never filling or waiting.

    A page with no ``validate`` accepts. Malformed variables are refused even with the
    source cold; a cached source the judge rejects refuses; a source not cached yet
    (or no snapshot at all) leaves the value unchecked, which the index counts as
    matched (D073).
    """
    validate: api.Validate | None = page.get("validate")
    if validate is None:
        return Check.ACCEPTED
    if not api.well_formed(path_vars):
        return Check.REFUSED
    body = (
        api.cached_source(validate[0], snapshot.responses)
        if snapshot is not None
        else None
    )
    if body is None:
        return Check.UNCHECKED
    return Check.ACCEPTED if api.judge(validate, path_vars, body) else Check.REFUSED


#: The page dict key holding a validated page's own ``title``, once
#: :func:`follow_validation` has put its wrapper in ``title``.
_OWN_TITLE = "explore_own_title"


def _call(value: Any, path_vars: dict[str, Any] | None) -> str:
    """A page's title or description, called as Dash calls one when it is callable."""
    if callable(value):
        return str(value(**path_vars) if path_vars else value())
    return str(value)


def page_text(
    page: Mapping[str, Any], key: str, path_vars: dict[str, Any] | None
) -> str:
    """``page``'s own ``title`` or ``description``, given only checked variables.

    ``path_vars`` are passed only once :func:`checked` accepted them; ``None`` calls a
    callable with no variables, which every templated page makes name no value.
    """
    if key == "title":
        value = page.get(_OWN_TITLE, page.get("title", SITE_TITLE))
    else:
        value = page.get(key, "")
    return _call(value, path_vars)


def follow_validation(page: dict[str, Any]) -> None:
    """Make a validated page's registry ``title`` follow its ``validate`` (#325, D083).

    Dash's Pages router calls ``page["title"]`` with the path variables after the
    layout, in the same request, and its client sets the browser tab from the result.
    The wrapper reads the snapshot in memory once: a refused value gets the page's
    not-found title, an unchecked one the page's own title with no variables, an
    accepted one its own title. The layout fills a cold source on a miss before the
    router calls this, so a refused value reads as not found from a cold start too.
    Called with no variables, it is the page's own. Idempotent; a page with a
    ``validate`` and no :class:`~explore.api.NotFound` fails here, at import.
    """
    if page.get("validate") is None or _OWN_TITLE in page:
        return
    not_found = page.get("not_found")
    if not isinstance(not_found, api.NotFound):
        raise RuntimeError(f"{page.get('module')} has a validate and no not_found")
    page[_OWN_TITLE] = page["title"]

    def title(**path_vars: Any) -> str:
        if not path_vars:
            return page_text(page, "title", None)
        verdict = checked(page, path_vars, api.CLIENT.snapshot)
        if verdict is Check.REFUSED:
            return not_found.title
        return page_text(
            page, "title", path_vars if verdict is Check.ACCEPTED else None
        )

    page["title"] = title


def _not_found(page: Mapping[str, Any] | None) -> Resolution:
    """A 404's resolution: ``page``'s not-found state, else the custom-404 page's."""
    shown: Mapping[str, Any] = NOT_FOUND_PAGE
    if page and isinstance(page.get("not_found"), api.NotFound):
        shown = page
    not_found: api.NotFound = shown["not_found"]
    return Resolution(
        canonical=None,
        og_url=None,
        title=not_found.title,
        description=not_found.sentence,
        page=shown,
    )


def resolve(path: str, query: str, snapshot: api.Snapshot | None) -> Resolution:
    """Resolve a request path against the page registry, with Dash's router matcher.

    ``path`` is the request path as Werkzeug decodes it (``request.path``), and is
    never decoded again: Dash's router matches the browser's ``location.pathname``
    decoded once (:func:`router_key`), which with leading and trailing slashes
    stripped is the same string, so a percent-encoded path resolves as the path it
    spells (D089). ``snapshot`` is read once by the caller and never waited on: a
    page's ``validate`` source missing from it counts as matched, never as rejected,
    and the title then names no value.
    """
    page, path_vars = _path_to_page(path.strip("/"))
    # Dash's own custom-404 convention: its router renders this module for a path no
    # page matches, and it must not be served as a page of its own.
    if not page or is_not_found_page(page):
        return _not_found(None)
    path_vars = path_vars or {}
    verdict = checked(page, path_vars, snapshot)
    if verdict is Check.REFUSED:
        return _not_found(page)
    shown_vars = path_vars if verdict is Check.ACCEPTED else None
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
    return Resolution(
        canonical=canonical,
        og_url=og_url,
        title=page_text(page, "title", shown_vars),
        description=page_text(page, "description", shown_vars),
        page=page,
        path_vars=shown_vars,
    )


@dataclass(frozen=True)
class Move:
    """Query keys a page no longer reads and the page that reads them now (#465): the
    target's path template, over the same path variables, and its ``query=`` parser,
    which normalizes the query the redirect carries."""

    keys: tuple[str, ...]
    template: str
    parser: Callable[[Any], list[tuple[str, str]]]


def page_move(page: Mapping[str, Any], registry: Mapping[str, Any]) -> Move | None:
    """A page's ``moved=(keys, target_template)`` (#465) as a :class:`Move`, or ``None``
    for a page without one; ``RuntimeError`` unless the target is a registered page
    over the same path variables, with a ``query=`` parser and the same ``validate``,
    so a redirect never leads to a page that would refuse the value just accepted, and
    unless ``moved`` is a pair whose keys are a tuple of names (a bare string would
    read as its letters)."""
    moved = page.get("moved")
    if moved is None:
        return None
    if not (isinstance(moved, tuple) and len(moved) == 2):
        raise RuntimeError(f"{page['module']} moved= is not (keys, target_template)")
    keys, template = moved
    if not isinstance(keys, tuple):
        raise RuntimeError(f"{page['module']} moves keys that are not a tuple of names")
    target = next(
        (p for p in registry.values() if p.get("path_template") == template), None
    )
    own = page.get("path_template") or ""
    if target is None:
        raise RuntimeError(f"{page['module']} moves keys to unregistered {template!r}")
    if sorted(_VARIABLE_RE.findall(template)) != sorted(_VARIABLE_RE.findall(own)):
        raise RuntimeError(f"{page['module']} moves keys across path variables")
    if target.get("query") is None:
        raise RuntimeError(f"{target['module']} has no query= for the keys it takes")
    if target.get("validate") != page.get("validate"):
        raise RuntimeError(f"{target['module']} validates otherwise than {own!r}")
    if not keys or not all(isinstance(key, str) and key for key in keys):
        raise RuntimeError(f"{page['module']} moves no keys")
    return Move(tuple(keys), template, target["query"])


def moved_location(resolution: Resolution, move: Move | None, query: str) -> str | None:
    """Where a document request for a page whose filters moved is redirected (#465),
    or ``None`` to serve the page.

    Only when the page's ``validate`` accepted the path variables against the snapshot
    in memory (never an unchecked or refused value), and the query, parsed as the
    router parses it, names any of the moved keys (a blank value counts; a value the
    target's parser drops still redirects, to no query). The ``Location`` is relative
    and built only from the accepted variables, each percent-quoted, and the target
    parser's output, never from the raw path or query, so it cannot name another
    host or carry a key the target does not read (D081: never the path variable).
    """
    if move is None or resolution.path_vars is None or not query:
        return None
    params = _parse_query_string(f"?{query}")
    if not any(key in params for key in move.keys):
        return None
    path_vars = resolution.path_vars
    path = _VARIABLE_RE.sub(
        lambda m: quote(path_vars[m.group(1)], safe=""), move.template
    )
    return path + query_syntax.encode_search(move.parser(params))


def card_tags(resolution: Resolution, root: str) -> list[dict[str, str]]:
    """The page's card tags, as Dash's ``_page_meta_tags`` builds them for a page but
    from the resolution's title and description, and without its ``twitter:url`` (the
    raw request URL). ``root`` is the request's URL root, for an assets image. Checked
    against Dash 4.5.0, whose ``image`` may also be an http(s) URL and which falls back
    to the app's own ``description`` and ``image``: no page and not the app sets
    either, so the tags are the same (#456)."""
    page = resolution.page
    image = page.get("image", "")
    if image:
        image = app.get_asset_url(image)
    assets_image_url = "".join([root, image.lstrip("/")]) if image else None
    image_url = page.get("image_url") or assets_image_url or ""
    title, description = resolution.title, resolution.description
    return [
        {"name": "description", "content": description},
        {"property": "twitter:card", "content": "summary_large_image"},
        {"property": "twitter:title", "content": title},
        {"property": "twitter:description", "content": description},
        {"property": "twitter:image", "content": image_url},
        {"property": "og:title", "content": title},
        {"property": "og:type", "content": "website"},
        {"property": "og:description", "content": description},
        {"property": "og:image", "content": image_url},
    ]


def _tag(name: str, attributes: dict[str, Any]) -> str:
    # Escaped, quotes included: every value here can carry request text.
    attrs = " ".join(
        f'{key}="{html_escaping.escape(str(value), quote=True)}"'
        for key, value in attributes.items()
    )
    return f"<{name} {attrs}>"


#: The ``flask.g`` attribute carrying one index request's resolved tags.
_G_TAGS = "explore_head_tags"


#: The ``localStorage`` key holding the reader's theme choice (#359). Only an explicit
#: choice is stored; Auto is the key's absence.
THEME_STORAGE_KEY = "explore-theme"

#: The choices that set ``data-theme`` on ``<html>``: every theme choice but Auto, in
#: the toggle's order (Dark, Light).
THEME_EXPLICIT: tuple[str, ...] = tuple(
    value for value in labels.THEME_CHOICES if value != labels.THEME_AUTO
)

#: The inline head script (#359): a saved explicit choice becomes ``data-theme`` on
#: ``<html>`` before the stylesheet applies, so a reload never flashes the other
#: palette. Any other stored value is Auto, and storage that throws (a browser
#: refusing ``localStorage``) leaves Auto. The e2e test
#: ``test_refused_storage_keeps_the_choice_for_the_document`` makes the storage getter
#: throw, and the e2e suite's browser guard fails on any page error, so the ``try`` is
#: pinned there. A constant built from constants: it carries no request
#: text. No CSP exists today; if one arrives, this script's hash must be computed from
#: this constant, since ``app.csp_hashes()`` covers only Dash's own inline scripts.
THEME_HEAD_SCRIPT = (
    "<script>(function () {"
    f" var explicit = {json.dumps(list(THEME_EXPLICIT))};"
    f" try {{ var saved = window.localStorage.getItem({json.dumps(THEME_STORAGE_KEY)});"
    " if (explicit.indexOf(saved) >= 0) {"
    ' document.documentElement.setAttribute("data-theme", saved); }'
    " } catch (error) {}"
    " })();</script>"
)

#: The theme buttons' ids, in the toggle's order: the theme callback's inputs and
#: ``aria-pressed`` outputs (#447).
THEME_BUTTONS: tuple[str, ...] = tuple(components.THEME_BUTTON_IDS.values())

#: Each theme button's id, mapped to its choice, for the theme callback (#447).
_THEME_BY_BUTTON = {
    button: value for value, button in components.THEME_BUTTON_IDS.items()
}

#: The theme callback (#359, #447), run in the browser. Its inputs are the three
#: buttons' ``n_clicks`` (in the toggle's order, and never read: a button's starts at
#: 0) and its state the store. Its first call per document registers one listener for
#: the device's light or dark setting. A later call is the reader's choice, the button
#: ``callback_context.triggered_id`` names: it sets or removes ``data-theme`` and
#: saves or clears the stored choice (where storage is refused, the choice lasts until
#: a reload). A later call whose trigger names no theme button returns ``no_update``
#: for every output and touches nothing: it fails closed, since treating an unknown
#: trigger as a choice would read as Auto and clear the saved choice (a defense against
#: a Dash change to ``triggered_id``; no call reaches it today). Every other call
#: derives the three buttons' ``aria-pressed`` from ``<html data-theme>``, the
#: attribute the stylesheet draws the selected position from, never from the theme in
#: effect (under Auto on a dark device, Auto is pressed). React owns ``aria-pressed``:
#: the callback returns it and never sets an attribute on a button. Every other call
#: also reports the theme in effect as the palette the stylesheet applied,
#: ``color-scheme`` on ``<html>``, so the selector logic lives only in ``style.css``;
#: and the store is written only after the palette changed, and only when the theme in
#: effect differs from what it holds.
#: The listener pushes the theme in effect with ``set_props`` whenever the device's
#: setting changes it, which under an explicit choice it never does.
THEME_CALLBACK = (
    "function () {"
    " var clientside = window.dash_clientside;"
    " var current = arguments[arguments.length - 1];"
    " var root = document.documentElement;"
    f" var explicit = {json.dumps(list(THEME_EXPLICIT))};"
    f" var choices = {json.dumps(list(labels.THEME_CHOICES))};"
    f" var byButton = {json.dumps(_THEME_BY_BUTTON)};"
    f" var key = {json.dumps(THEME_STORAGE_KEY)};"
    f" var store = {json.dumps(components.THEME_STORE_ID)};"
    f" var auto = {json.dumps(labels.THEME_AUTO)};"
    " function inEffect() {"
    ' return window.getComputedStyle(root).colorScheme === "dark" ? "dark" : "light"; }'
    " if (!window.exploreThemeReady) {"
    " window.exploreThemeReady = true;"
    ' window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change",'
    " function () { var now = inEffect();"
    " if (now !== window.exploreThemeInEffect) {"
    " window.exploreThemeInEffect = now;"
    " clientside.set_props(store, {data: now}); } });"
    " } else {"
    " var choice = byButton[clientside.callback_context.triggered_id];"
    " if (choice === undefined) {"
    " return choices.map(function () { return clientside.no_update; })"
    ".concat([clientside.no_update]); }"
    " var chosen = explicit.indexOf(choice) >= 0;"
    ' if (chosen) { root.setAttribute("data-theme", choice); }'
    ' else { root.removeAttribute("data-theme"); }'
    " try { if (chosen) { window.localStorage.setItem(key, choice); }"
    " else { window.localStorage.removeItem(key); } } catch (error) {}"
    " }"
    ' var applied = root.getAttribute("data-theme");'
    " var selected = explicit.indexOf(applied) >= 0 ? applied : auto;"
    " var now = inEffect();"
    " window.exploreThemeInEffect = now;"
    " return [now === current ? clientside.no_update : now].concat("
    ' choices.map(function (value) { return value === selected ? "true" : "false"; }));'
    " }"
)

#: The API's ``/docs`` page, the site navigation's one link off this site (#448): built
#: from the one API base, never a second host literal, and only ever an ``href``.
API_DOCS_URL = f"{API_BASE}/docs"


@dataclass(frozen=True)
class NavEntry:
    """One registered page in the site navigation's current-page table (#448).

    ``path`` and ``pattern`` are what Dash's router matches the page by
    (``_path_to_page``): its path and, for a templated page, its template as an
    anchored regex, each with the leading and trailing slashes stripped. ``link`` is
    the ``components.NAV_LINKS`` key the page marks, or ``None``; ``current`` is the
    ``aria-current`` value: ``"page"`` when that link goes to this page, ``"true"``
    when it goes to the page's index.
    """

    path: str
    pattern: str | None
    link: str | None
    current: str | None


#: The static parts of every page path, which a pattern carries unescaped, so a pattern
#: means the same in Python's ``re`` and in JavaScript (#448).
_STATIC_PATH_RE = re.compile(r"[a-z0-9/-]*")


def nav_entry(page: Mapping[str, Any]) -> NavEntry:
    """``page``'s entry in the current-page table, from its ``nav=`` key (#448).

    Every registered page declares ``nav=``, a ``components.NAV_LINKS`` key or
    ``None``; a page without one, or with another value, fails the import. A
    template's variables become ``[\\s\\S]*``, as fnmatch's ``*`` in Dash's router
    matches a ``/`` too (so ``/election/1824/x`` is the one-election view).
    """
    if "nav" not in page:
        raise RuntimeError(f"{page.get('module')} registers no nav= (#448)")
    link = page["nav"]
    if link is not None and link not in components.NAV_LINKS:
        raise RuntimeError(f"{page.get('module')} registers an unknown nav={link!r}")
    path = str(page["path"]).strip("/")
    template = page.get("path_template")
    pattern = None
    if template:
        stripped = str(template).strip("/")
        statics = re.split(r"<.*?>", stripped)
        if not all(_STATIC_PATH_RE.fullmatch(part) for part in statics):
            raise RuntimeError(f"{page.get('module')} has a template to escape")
        pattern = "^" + r"[\s\S]*".join(statics) + "$"
    current = None
    if link is not None:
        target = components.NAV_LINKS[link][1].strip("/")
        current = "page" if target == path and not template else "true"
    return NavEntry(path=path, pattern=pattern, link=link, current=current)


#: dcc's bundled plotly.js, as ``Dash._setup_plotlyjs`` names it in the ``plotly``
#: package.
PLOTLYJS_PACKAGE_PATH = "package_data/plotly.min.js"


class ExploreDash(dash.Dash):
    """Dash with a canonical link and ``og:url`` from the matched page, and 404s."""

    def _setup_plotlyjs(self) -> None:
        """Register plotly.js by its CDN address only, so the app never serves it.

        ``Dash.__init__`` calls this, before any request, to append dcc's plotly.js
        entry to the module-global ``dcc._js_dist`` (#430). Marked ``external_only``,
        Dash's resource filter keeps only the CDN address, so the package path is
        never registered and its component-suite route refuses it. Only the entry this
        call added is marked, and anything but exactly one such entry fails the
        import. A Dash private, pinned in ``TestDashPrivates``. ``Dash.get_dist``
        registers entries without the filter, but only for a component library first
        imported inside a callback; dcc is imported at startup, so this entry is never
        re-registered that way. Accepted residual: ``dcc._js_dist`` is module-global,
        so a second ``dash.Dash()`` built later in the same process would append an
        unmarked entry, which this app would then register and serve; none is built
        (production imports only this app). :meth:`_config` points graphs at the
        same CDN address (#432).
        """
        before = len(dcc._js_dist)
        super()._setup_plotlyjs()
        added = dcc._js_dist[before:]
        if not (
            len(added) == 1
            and added[0].get("namespace") == "plotly"
            and added[0].get("relative_package_path") == PLOTLYJS_PACKAGE_PATH
        ):
            raise RuntimeError(f"unexpected plotly.js entries from Dash: {added!r}")
        added[0]["external_only"] = True

    def _config(self) -> dict[str, Any]:
        """The client config, with graphs pointed at plotly.js's CDN address (#432).

        Dash's renderer reads ``serve_locally`` only to choose the plotly.js address
        it sets as ``window._dashPlotlyJSURL`` (the local package path, which this app
        no longer serves, or ``plotlyjs_url``), and Dash sends ``plotlyjs_url`` only
        when ``serve_locally`` is false. So the browser is told ``serve_locally: false``
        and given ``self._plotlyjs_url``, the address Dash derives from the installed
        plotly, while the app's own ``serve_locally`` stays true and every other
        asset is still served from here. ``charts.CHART_MOUNT_CALLBACK`` loads the
        script from that address, with no ``integrity`` attribute, when the page's
        first chart mounts, so a page with no chart never fetches it (D087, D088), and
        dcc's own loader never appends a script or fetches. Dash privates, pinned in
        ``TestDashPrivates``.
        """
        config: dict[str, Any] = super()._config()
        config["serve_locally"] = False
        config["plotlyjs_url"] = self._plotlyjs_url
        return config

    def index(self, *args: Any, **kwargs: Any) -> Any:
        # Resolved once, against one read of the snapshot: the status, the title and
        # the tags below come from the same answer even if the refresher swaps
        # meanwhile. The cards are built here, never by Dash's _page_meta_tags, which
        # would call the registry's title and so read the snapshot again (#325).
        query = flask.request.query_string.decode("utf-8", "replace")
        resolution = resolve(flask.request.path, query, api.CLIENT.snapshot)
        # A filter that moved to another page (#465): a 302, never a 301, which
        # browsers cache with no undo; the routing callback never reaches the index,
        # so a client-side route to the page renders it unfiltered.
        target = moved_location(
            resolution, MOVES.get(resolution.page.get("module", "")), query
        )
        if target is not None:
            return flask.redirect(target, code=302)
        cards = card_tags(resolution, flask.request.url_root)
        if resolution.found:
            own = [
                _tag("meta", {"property": "og:url", "content": resolution.og_url}),
                _tag("link", {"rel": "canonical", "href": resolution.canonical}),
            ]
        else:
            own = [_tag("meta", {"name": "robots", "content": "noindex"})]
        # Dash's own metas lead, then the theme script, then the card tags and ours
        # (see interpolate_index).
        setattr(
            flask.g,
            _G_TAGS,
            ([_tag("meta", meta) for meta in cards], own, resolution.title),
        )
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
        cards, own, page_title = tags
        # Dash's own metas lead, so <meta charset> sits inside the first 1024 bytes the
        # encoding prescan reads; the theme script follows them, ahead of Dash's
        # stylesheets (#359); then the card tags and ours.
        metas = "\n      ".join([f"{metas}", THEME_HEAD_SCRIPT, *cards, *own])
        return super().interpolate_index(
            metas=metas,
            # Escaped here: Dash interpolates the title into the HTML unescaped.
            title=html_escaping.escape(page_title, quote=True),
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
    # Dash's MCP server runs callbacks through a route of its own, which the routing
    # hook never sees; the argument overrides DASH_MCP_ENABLED (D089).
    enable_mcp=False,
    include_pages_meta=False,  # rebuilt in ExploreDash.index, without twitter:url
    title=SITE_TITLE,
    update_title=None,  # type: ignore[arg-type]  # Dash documents None: no "Updating…"
)
server = app.server
# The site navigation's marker matches a pathname as Dash's router does only with the
# app at the root, where ``strip_relative_path`` strips nothing but slashes (#448's
# review): served under a prefix, the marker would vanish while routing still worked.
if app.config.requests_pathname_prefix != "/":
    raise RuntimeError(
        "NAV_CALLBACK assumes the app is served at the root, not under "
        f"{app.config.requests_pathname_prefix!r}"
    )
# The site navigation and the theme toggle after it sit in a header above every page's
# main landmark, and the store beside both: Pages navigation swaps only page_container,
# so none is re-mounted, and the theme callback's first call runs once per document
# (#359, #447, #448).
app.layout = html.Div(
    [
        html.Header(
            [components.site_nav(API_DOCS_URL), components.theme_control()],
            className="site-header",
        ),
        html.Main(dash.page_container, className="explore"),
        dcc.Store(id=components.THEME_STORE_ID, storage_type="memory"),
    ]
)

#: Each page's moved filters (#465), by module: built once every page is registered, and
#: checked as it is built (:func:`page_move`), so a bad ``moved=`` fails the import.
MOVES: dict[str, Move] = {
    module: move
    for module, page in dash.page_registry.items()
    if (move := page_move(page, dash.page_registry)) is not None
}

#: The site navigation's current-page table (#448): one entry per registered page, in
#: the registry's order, which is the order Dash's router tries them in.
NAV_TABLE: tuple[NavEntry, ...] = tuple(
    nav_entry(page) for page in dash.page_registry.values()
)

#: The site navigation's callback (#448), run in the browser on the Pages router's own
#: Location, so it follows the pathname the router routes on, in the same dispatch: on
#: the first load (before the Location reports a pathname it reads
#: ``window.location.pathname``), after a client-side navigation and after back and
#: forward. It matches the pathname as the router does (:func:`router_key`) with the
#: app at the root (enforced above), against :data:`NAV_TABLE`: decoded once, each run
#: of percent-escapes as UTF-8 with replacement (``TextDecoder``, never
#: ``decodeURIComponent``, which throws on a malformed escape), as Python's ``unquote``
#: decodes it (D089), then leading and trailing slashes stripped, which is all
#: ``strip_relative_path`` strips there; each page in order by its template's pattern,
#: then its path, the first match winning; a pathname no page matches marks nothing.
#: ``dcc.Link`` renders no ``aria-*`` attribute, so the callback writes
#: ``aria-current`` onto the marked link itself and removes it from the others (React
#: manages no such attribute there, so nothing overwrites it; ``"false"`` is never
#: written), and returns the marked link's key, or ``""``, as the nav's
#: ``data-current``. The stylesheet draws the marker from ``aria-current``.
NAV_CALLBACK = (
    "function (pathname) {"
    f" var table = {json.dumps([entry.__dict__ for entry in NAV_TABLE])};"
    f" var ids = {json.dumps(components.NAV_LINK_IDS)};"
    ' var path = typeof pathname === "string" ? pathname : window.location.pathname;'
    " path = path.replace(/(?:%[0-9A-Fa-f]{2})+/g, function (run) {"
    " var bytes = new Uint8Array(run.length / 3);"
    " for (var b = 0; b < bytes.length; b++) {"
    " bytes[b] = parseInt(run.substr(b * 3 + 1, 2), 16); }"
    " return new TextDecoder().decode(bytes); });"
    ' path = path.replace(/^\\/+|\\/+$/g, "");'
    " var hit = null;"
    " for (var i = 0; i < table.length && hit === null; i++) {"
    " var entry = table[i];"
    " if ((entry.pattern !== null && new RegExp(entry.pattern).test(path))"
    " || path === entry.path) { hit = entry; } }"
    ' var marked = hit !== null && hit.link !== null ? hit.link : "";'
    " Object.keys(ids).forEach(function (key) {"
    " var link = document.getElementById(ids[key]);"
    " if (link === null) { return; }"
    ' if (key === marked) { link.setAttribute("aria-current", hit.current); }'
    ' else { link.removeAttribute("aria-current"); } });'
    " return marked;"
    " }"
)
clientside_callback(
    NAV_CALLBACK,
    Output(components.SITE_NAV_ID, "data-current"),
    Input(_ID_LOCATION, "pathname"),
)
# The graph is in no server layout (#452): this mounts it into the mount point (which
# every chart's layout holds) once plotly.js has loaded, and the next callback draws
# it. The next callback's graph outputs are absent from every layout Dash validates,
# which suppress_callback_exceptions=True allows.
clientside_callback(
    charts.CHART_MOUNT_CALLBACK,
    Output(charts.mount_id(MATCH), "children"),
    Input(charts.source_id(MATCH), "data"),
    State(charts.mount_id(MATCH), "id"),
)
clientside_callback(
    charts.CHART_CALLBACK,
    Output(charts.graph_id(MATCH), "figure"),
    Output(charts.graph_id(MATCH), "style"),
    Input(charts.source_id(MATCH), "data"),
    Input(components.THEME_STORE_ID, "data"),
)
clientside_callback(
    THEME_CALLBACK,
    Output(components.THEME_STORE_ID, "data"),
    *[Output(button, "aria-pressed") for button in THEME_BUTTONS],
    *[Input(button, "n_clicks") for button in THEME_BUTTONS],
    State(components.THEME_STORE_ID, "data"),
)


@server.errorhandler(dash.exceptions.DependencyException)
def _unregistered_suite_path(_error: Exception) -> werkzeug.exceptions.NotFound:
    """A component-suite path Dash never registered answers 404, not 500 (#430).

    Dash raises ``DependencyException`` only from ``_validate.validate_js_path``,
    for a file its component-suite route was never told to serve (plotly.js among
    them, above). Dash's Flask backend maps ``InvalidResourceError`` to 404 but
    registers nothing for ``DependencyException``, so without this handler such a
    path answers 500 and logs a traceback. The body is Flask's default 404 body
    (Werkzeug's ``NotFound``).
    """
    return werkzeug.exceptions.NotFound()


#: The custom-404 page, found as Dash's router finds it: its not-found state is the
#: title of every 404 that is not a page's own.
NOT_FOUND_PAGE: dict[str, Any] = next(
    (page for page in dash.page_registry.values() if is_not_found_page(page)), {}
)
if not isinstance(NOT_FOUND_PAGE.get("not_found"), api.NotFound):
    raise RuntimeError("no custom-404 page registers an api.NotFound")
for _page in dash.page_registry.values():
    follow_validation(_page)


#: The Pages router's callback as a routing request names it in ``output`` and Dash
#: keys it in ``callback_map``: its two outputs, in Dash's multi-output form.
ROUTER_OUTPUT = f"..{_ID_CONTENT}.children...{_ID_STORE}.data.."

#: The Flask endpoint Dash dispatches every callback request through.
DISPATCH_ENDPOINT = app.config.routes_pathname_prefix + "_dash-update-component"


def router_key(pathname: str) -> str:
    """The string Dash's Pages router matches ``pathname`` by: decoded once with
    ``unquote`` (UTF-8, errors replaced; ``+`` kept), then stripped as the router
    strips (Dash 4.5.0, plotly/dash#4074; D089). Pinned in ``TestDashPrivates``.
    Raises ``dash.exceptions.UnsupportedRelativePath`` for a decoded path that does
    not start with ``/``, as the router's own strip does."""
    return str(app.strip_relative_path(unquote(pathname)))


def strip_path_variables(pathname: str, search: str) -> str:
    """``search`` without any key named after a path variable of ``pathname``'s page.

    The page is the one Dash's router matches, by its own matcher on
    :func:`router_key`; a pathname the router's strip refuses is left alone, for Dash
    to refuse. Keys are
    read as the router's ``parse_qs(keep_blank_values=True)`` reads them: the text
    after ``?``, split on ``&`` only, each part's key everything before its first
    ``=`` (all of it, with no ``=``), ``+`` and percent-escapes decoded. So
    ``ye%61r=1`` and a bare ``year`` are dropped, and ``year%3Dx=1`` (key ``year=x``)
    is kept. Every other part is kept byte for byte, in order, empty ones included.
    """
    if not search.startswith("?"):
        return search
    try:
        key = router_key(pathname)
    except dash.exceptions.UnsupportedRelativePath:
        return search
    _, path_vars = _path_to_page(key)
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


def refuse_encoded_dispatch() -> werkzeug.Response | None:
    """Refuse a callback request whose body is content-encoded (D089, #456).

    Dash 4.5.0's dispatch decompresses a body sent with ``Content-Encoding: gzip``
    (plotly/dash#3925) whatever the callback, while :func:`_strip_routing_request`
    reads the body with ``get_json``, which cannot read it: a compressed routing
    request would reach the router with its query unfiltered, and a small one can
    expand to Dash's 64 MB cap on the one instance. No callback in this app sets
    ``compress_payload``, so Dash's own client never sends one; the request answers
    415 (Werkzeug's default body) before Dash reads it. Any encoding but identity is
    refused, so a later Dash accepting another one is refused too.
    """
    request = flask.request
    if request.method != "POST" or request.endpoint != DISPATCH_ENDPOINT:
        return None
    encoding = request.headers.get("Content-Encoding", "").strip().lower()
    if encoding in ("", "identity"):
        return None
    # Werkzeug's default body, as the DependencyException handler uses NotFound's.
    return werkzeug.exceptions.UnsupportedMediaType().get_response()


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
    refused = refuse_encoded_dispatch()
    if refused is not None:
        return refused
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
