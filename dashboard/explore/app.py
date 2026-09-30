"""The Dash app and its WSGI entry point (``explore.app:server``, per ``app.yaml``).

Beyond Dash itself this module adds four things, all host-level:

- **The canonical host.** A request to the App Engine default host (``*.appspot.com``)
  301s to :data:`~explore.config.CANONICAL_HOST`, so the vendor domain never stays in
  the address bar. Two exemptions: ``/_ah/*`` (App Engine's own warmup) and
  version-specific hosts (``<version>-dot-…``), which the deploy workflow probes before
  moving traffic.
- **A canonical link and ``og:url``** on every page, naming the canonical host whichever
  host served it.
- **The refresher.** ``/_ah/warmup`` refreshes the cache synchronously before the
  instance takes traffic, and every request makes sure the refresher thread is running.
  Neither happens at import, so importing this module makes no network call.
- **No validation layout.** ``suppress_callback_exceptions=True`` stops Dash from
  calling every page's ``layout()`` on the first request and embedding the result in
  every index page. The index HTML therefore carries no data and never waits on the
  API, which is what keeps a link preview's time to first byte short (D071(g)).
"""

from __future__ import annotations

import html as html_escaping
import logging
from typing import Any
from urllib.parse import quote

import dash
import flask
import werkzeug
from dash import html

from explore import api
from explore.config import CANONICAL_HOST, SITE_TITLE

log = logging.getLogger(__name__)

# App Engine collects stdout/stderr; INFO carries the cache's "serving snapshot" and
# "api fetch" lines, which is how API calls are counted (runbook §12). A no-op when the
# host process (a test runner, say) has configured logging already.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

VENDOR_HOST_SUFFIX = ".appspot.com"
VERSION_HOST_MARKER = "-dot-"


def canonical_url(path: str) -> str:
    """The canonical URL for a request path, re-quoted.

    ``flask.request.path`` is percent-decoded, and Dash answers every path, so the path
    is attacker-controlled text: quoting it keeps ``"``, ``<``, ``?``, ``#`` and line
    breaks out of both the HTML this URL is written into and the redirect built from it.
    """
    return f"https://{CANONICAL_HOST}{quote(path, safe='/')}"


class ExploreDash(dash.Dash):
    """Dash with a canonical link and ``og:url`` on every page."""

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
        # Escaped as well as quoted: this is written into attribute values.
        url = html_escaping.escape(canonical_url(flask.request.path), quote=True)
        metas = (
            f"{metas}"
            f'\n      <meta property="og:url" content="{url}">'
            f'\n      <link rel="canonical" href="{url}">'
        )
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
    title=SITE_TITLE,
    update_title=None,  # type: ignore[arg-type]  # Dash documents None: no "Updating…"
)
server = app.server
app.layout = html.Main(dash.page_container, className="explore")


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
    api.CLIENT.ensure_refresher()
    return None


@server.route("/_ah/warmup")
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
