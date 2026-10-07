"""URL-state syntax every page shares: query values, the og:url normal form, patterns.

A page module cannot import another page module (Dash executes pages before they are
in ``sys.modules``), so the pieces two pages' parsers both need live here (#307):
the single-value rule, the one encoding of a query string that ``og:url`` and every
filter callback write, and the syntax of the path and query values the API itself
names (a four-digit year, a USPS state code, a candidate slug). The year range every
year-filtered table shares lives here too (#279): its two keys and their parse, the one
check of a year a body names (:func:`checked_year`), a served span, and the bounds a
render applies. Like ``components`` and ``labels``, this module reads no API and
imports nothing from ``explore``.
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

#: The query keys of a year range: the API's own names, shared by every page.
YEAR_FROM = "year_from"
YEAR_TO = "year_to"

#: The years a body may name: four digits without a leading zero, the domain of
#: :data:`YEAR_RE` that ``int()`` round-trips.
YEAR_MIN = 1000
YEAR_MAX = 9999


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


def checked_year(value: Any) -> int | None:
    """``value`` if it is a year as the API writes one, else ``None``.

    The one check of a year read from a body (#279): an ``int`` (never a ``bool``, which
    is one) from :data:`YEAR_MIN` to :data:`YEAR_MAX`. A float, a string or an
    out-of-range number is not a year, so it never reaches a path or a label.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if YEAR_MIN <= value <= YEAR_MAX else None


def control_year(value: Any) -> int | None:
    """A year as a slider reports it (an ``int`` or an integral ``float``), else
    ``None``. Never a ``bool``."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return checked_year(value)


def parse_year_range(params: Any) -> dict[str, str]:
    """The year range in a parsed query string: syntactic, total, and API-free.

    Keeps :data:`YEAR_FROM` / :data:`YEAR_TO` only as four ASCII digits. A range whose
    start is after its end, compared as written, drops both bounds. Whether a year lies
    inside a page's served span is the layout's question (:func:`year_range`).
    """
    if not isinstance(params, dict):
        return {}
    kept: dict[str, str] = {}
    for key in (YEAR_FROM, YEAR_TO):
        value = single(params.get(key))
        if value is not None and YEAR_RE.fullmatch(value):
            kept[key] = value
    if YEAR_FROM in kept and YEAR_TO in kept and kept[YEAR_FROM] > kept[YEAR_TO]:
        del kept[YEAR_FROM], kept[YEAR_TO]
    return kept


def year_span(first: Any, last: Any) -> tuple[int, int]:
    """A served span, ``(first, last)``, or ``TypeError`` for a malformed one.

    Both pass :func:`checked_year` and the first is no later than the last. That also
    bounds a slider's labels: an unchecked span would make their count, and the work of
    every render, as large as the body said. ``TypeError`` because that is what a
    layout turns into the degraded state.
    """
    start, end = checked_year(first), checked_year(last)
    if start is None or end is None:
        raise TypeError(f"span is not two years: {first!r}–{last!r}")
    if start > end:
        raise TypeError(f"span is not a range of years: {start}–{end}")
    return start, end


def year_range(
    pairs: Iterable[tuple[str, str]], first: int, last: int
) -> tuple[int, int]:
    """The bounds a render applies inside the span ``first``–``last``.

    Per parameter, as ``og:url`` is: a bound outside the span falls back to its
    default. Never inverted, since :func:`parse_year_range` already dropped an inverted
    pair and a bound replaced by its default cannot pass the other.
    """
    given = dict(pairs)
    start = int(given.get(YEAR_FROM, first))
    end = int(given.get(YEAR_TO, last))
    return (
        start if first <= start <= last else first,
        end if first <= end <= last else last,
    )


def year_range_search(years: Any, first: Any, last: Any) -> dict[str, str]:
    """A range slider's value as query parameters: a bound equal to its end of the
    span is the default and is omitted."""
    params: dict[str, str] = {}
    if isinstance(years, list) and len(years) == 2:
        low, high = (control_year(v) for v in years)
        if low is not None and low != first:
            params[YEAR_FROM] = str(low)
        if high is not None and high != last:
            params[YEAR_TO] = str(high)
    return params
