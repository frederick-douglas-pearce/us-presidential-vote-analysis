"""URL-state syntax every page shares: query values, the og:url normal form, patterns.

A page module cannot import another page module (Dash executes pages before they are
in ``sys.modules``), so the pieces two pages' parsers both need live here (#307):
the single-value rule, the one encoding of a query string that ``og:url`` and every
filter callback write, and the syntax of the path and query values the API itself
names (a four-digit year, a USPS state code, a candidate slug). Like ``components``
and ``labels``, this module reads no API and imports nothing from ``explore``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote, urlencode

#: A year as the API writes one. ASCII only: ``\d`` and ``int()`` accept other digits.
YEAR_RE = re.compile(r"[0-9]{4}")

#: A USPS state code, the API's ``state`` filter (``/v1/elections/{year}?state=``).
USPS_RE = re.compile(r"[A-Z]{2}")

#: A candidate slug as ``usvote.slug`` produces one, the API's ``candidate`` filter.
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

#: The longest slug a parser keeps; the snapshot's longest is far shorter.
SLUG_MAX = 64


def single(value: Any) -> str | None:
    """A query value, if it is one string or the same string repeated."""
    values = value if isinstance(value, list) else [value]
    if not values or any(v != values[0] for v in values):
        return None
    return values[0] if isinstance(values[0], str) else None


def is_slug(value: str) -> bool:
    """Whether ``value`` is a candidate slug no longer than :data:`SLUG_MAX`."""
    return len(value) <= SLUG_MAX and SLUG_RE.fullmatch(value) is not None


def encode_search(pairs: Iterable[tuple[str, str]]) -> str:
    """The normal form of a query string: ``""``, or ``?`` and the sorted, de-duplicated
    pairs, percent-encoded with ``quote``.

    The one encoding ``og:url`` and every filter callback use, so a callback's URL and
    the URL a link preview names are the same bytes (``dcc.Location`` joins pathname
    and search verbatim).
    """
    kept = sorted(set(pairs))
    return "?" + urlencode(kept, quote_via=quote) if kept else ""
