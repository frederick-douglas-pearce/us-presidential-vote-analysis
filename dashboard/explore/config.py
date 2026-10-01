"""The dashboard's two fixed addresses. Neither is configurable, on purpose.

D070(b) and #277's acceptance criteria make the public API the dashboard's **only** data
input, through one base URL. Any override (an environment variable, an ``app.yaml``
setting, a dev flag) would be a second input, and a base URL supplied by configuration
is exactly what a source-text guard cannot see. So both values are constants, and the
tests pin them against independent literals rather than against this module.
"""

from __future__ import annotations

#: The public API host, behind Cloudflare. Never the Cloud Run origin (D070(b)), which
#: would also bypass the edge cache the dashboard relies on.
API_HOST = "api.us-presidential-election-center.org"

#: The only base every request is built on (``API_BASE + "/v1/..."``).
API_BASE = f"https://{API_HOST}"

#: Where the dashboard is served (D071(c)). The App Engine default host redirects here,
#: and every page's canonical link and ``og:url`` name it.
CANONICAL_HOST = "explore.us-presidential-election-center.org"

#: The site title, used for the browser tab and link previews.
SITE_TITLE = "Explore — US Presidential Election Center"
