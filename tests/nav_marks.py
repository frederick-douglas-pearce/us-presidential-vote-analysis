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
#: or strips differently from the router would part from it. Dash's router decodes the
#: pathname once before it strips and matches (Dash 4.5.0, D089), so an escape in a
#: static segment is matched as the character it spells, a double escape is not, and
#: a malformed or overlong one decodes to a replacement character that matches nothing
#: static.
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
    # The election subpages (#465) and an unserved year on one; an unknown section is
    # the line above. Every election page marks Elections the same way, so these pin
    # the mark only: which table entry matched (the subpages' before the overview's
    # greedy <year>) is TestCurrentPage.test_the_matcher_agrees_with_dashs_router's,
    # which compares the matched entry's module with the router's choice.
    "/election/1824/states": ("elections", "true"),
    "/election/1824/per-capita": ("elections", "true"),
    "/election/1825/states": ("elections", "true"),
    "/election/1824%2Fper-capita": ("elections", "true"),
    "/election//1824": ("elections", "true"),
    "/election/%31824": ("elections", "true"),
    "/%65lections": ("elections", "page"),
    "/%2Felections%2F": ("elections", "page"),
    "/election%2F1824": ("elections", "true"),
    "/%2565lections": None,
    "/%65lection/1824%FF": ("elections", "true"),
    "/elections%FF": None,
    "/%C0%AFelections": None,
    "/elections%": None,
    "/%G1": None,
    "/election/18%0A24": ("elections", "true"),
    "/%2F": ("home", "page"),
    "/Elections": None,
    "/states": ("states", "page"),
    "/state/GA": ("states", "true"),
    "/state/ga": ("states", "true"),
    "/state/ZZ": ("states", "true"),
    "/candidate/andrew-jackson": None,
    "/not-found-404": None,
    "/no-such": None,
}
