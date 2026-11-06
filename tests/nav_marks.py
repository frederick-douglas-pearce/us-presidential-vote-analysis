"""The site navigation's current-page corpus (#448): each path, and the link it marks.

One corpus, two oracles: ``tests/unit/test_dashboard_nav.py`` checks the current-page
table's algorithm, run in Python, against Dash's router, and
``tests/e2e/test_dashboard_e2e_nav.py`` calls the registered clientside callback itself
in the browser on each path. Stdlib-only, as ``tests/dashboard_fixtures.py`` is, so the
e2e process imports nothing it does not need.
"""

from __future__ import annotations

#: Each path, the ``components.NAV_LINKS`` key it marks and that link's
#: ``aria-current``, or ``None`` where nothing is marked. The encoded, mixed-case,
#: doubled-slash and trailing-slash paths are where a matcher that decodes, folds case
#: or strips differently from the router would part from it.
MARKS: dict[str, tuple[str, str] | None] = {
    "/": ("home", "page"),
    "//": ("home", "page"),
    "/elections": ("elections", "page"),
    "/elections/": ("elections", "page"),
    "/elections/x": None,
    "/election": None,
    "/election/1824": ("elections", "true"),
    "/election/1825": ("elections", "true"),
    "/election/1824/x": ("elections", "true"),
    "/election//1824": ("elections", "true"),
    "/election/%31824": ("elections", "true"),
    "/%65lections": None,
    "/Elections": None,
    "/states": ("states", "page"),
    "/state/GA": ("states", "true"),
    "/state/ga": ("states", "true"),
    "/state/ZZ": ("states", "true"),
    "/candidate/andrew-jackson": None,
    "/not-found-404": None,
    "/no-such": None,
}
