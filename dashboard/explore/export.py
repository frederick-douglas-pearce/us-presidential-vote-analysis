"""The CSV a table offers for download (#309, D075), built at render time into its link.

Each table's link carries its file in a ``data:`` URL, built in the same render from the
same rows as the table's body, so the file is exactly the view: the same snapshot, the
same filters, the same rows. A click is a download inside the browser: there is no
route or callback behind it, so it makes no API request and writes nothing on the
server.

The file's shape:

- A UTF-8 byte-order mark, so a spreadsheet reads the text as UTF-8.
- A preamble of two-field rows, ``#`` then a sentence: each source the table carries,
  with its license and the license's URL, read from the response's ``meta.provenance``
  (never a literal); the snapshot version; the years each source covers; the view's
  URL; the notes that explain the table's nulls; and what an empty cell means. It
  states where the data comes from, not a license condition. The rows go through the
  same writer as the data, so a comma in a note never splits it, and a reader that
  skips lines starting with ``#`` (``pandas.read_csv(comment="#")``) skips them all.
- A blank row, the header of raw public ``/v1`` field names, and one row per shown row.

Rows are written here (:func:`row`, RFC 4180) rather than with the ``csv`` module, which
the D070(b) guard bans from runtime modules with ``io`` (``BANNED_MODULES`` in
``test_dashboard_guards.py``): this module only writes a file, and never reads one.

Which sources a table carries is read from its field names (:func:`sources`): every
exported field is in exactly one of :data:`EC_FIELDS`, :data:`POPULAR_VOTE_FIELDS` and
:data:`CENSUS_FIELDS`, so a later table names its sources without declaring them.

Like ``components``, ``labels`` and ``query``, this module reads no API, and it imports
nothing from ``explore``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any, NamedTuple
from urllib.parse import quote

from dash import html

#: The fields whose values come from the Electoral College source or are derived from
#: it (``pv_status`` from the in-repo absence catalog, ``ec_share_hybrid`` and
#: ``pv_coverage`` from the electoral counts), and the row keys.
EC_FIELDS = frozenset(
    {
        "year",
        "state",
        "state_usps",
        "candidate",
        "candidate_slug",
        "candidate_count",
        "state_electoral_votes",
        "electoral_votes",
        "electoral_votes_counted",
        "electoral_count_status",
        "electoral_count_status_reason",
        "pv_status",
        "national_electoral_votes",
        "national_electoral_votes_counted",
        "national_electoral_denominator",
        "electoral_rank",
        "took_office",
        "ec_share_full",
        "ec_share_hybrid",
        "pv_coverage",
    }
)

#: The fields whose values come from the popular-vote source. ``party`` is recorded
#: only where a popular-vote figure is (``labels.PARTY_NOTE``), ``has_popular_vote`` is
#: whether a year has any national popular-vote figure, and ``hybrid_score`` averages
#: in the popular-vote share.
POPULAR_VOTE_FIELDS = frozenset(
    {
        "popular_votes",
        "party",
        "national_pv_votes",
        "pv_share",
        "hybrid_score",
        "has_popular_vote",
    }
)

#: The fields whose values come from the census source (#280).
CENSUS_FIELDS = frozenset(
    {
        "governing_census_year",
        "population",
        "boundary_basis",
        "coverage",
        "persons_per_electoral_vote",
    }
)

#: Each source in preamble order: what it supplies, and the provenance keys naming it
#: and its license (``components.SOURCES`` reads the same triples).
EC_SOURCE = ("Electoral votes", "ec_source_name", "ec_license", "ec_license_url")
PV_SOURCE = ("Popular votes", "source_name", "license", "license_url")
CENSUS_SOURCE = (
    "Population",
    "census_source_name",
    "census_license",
    "census_license_url",
)

#: The preamble's last line: what an empty cell means.
NULL_LINE = "An empty cell is a null: the dataset holds no value there."

#: The first field of every preamble row.
COMMENT = "#"

#: The characters a spreadsheet may read as the start of a formula (OWASP's list).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

#: The byte-order mark the file starts with, so a spreadsheet reads it as UTF-8.
BOM = "\N{ZERO WIDTH NO-BREAK SPACE}"

#: What every download link's ``href`` starts with.
DATA_URL_PREFIX = "data:text/csv;charset=utf-8,"


class Download(NamedTuple):
    """What a table's download needs besides its rows and fields.

    ``name`` is what the link says it downloads ("the results by state"), so each link
    on a page has its own accessible name. ``provenance`` is the ``meta.provenance`` of
    the response the table's rows come from. A ``NamedTuple``, as a page's types are.
    """

    filename: str
    name: str
    provenance: dict[str, Any]
    view_url: str


def view_url(host: str, path: str, search: str) -> str:
    """A view's URL: its path on ``host`` and ``search``, the filters the render applied
    in the normal form a page's filter callback writes (``""`` or ``?…``), so two URLs
    that open the same view name it the same way."""
    return f"https://{host}{path}{search}"


def guard(text: str) -> str:
    """Text a spreadsheet will not run: a leading formula character gets a ``'``."""
    return "'" + text if text.startswith(FORMULA_STARTS) else text


def cell(value: Any) -> str:
    """A value as the CSV writes it.

    A null is empty, never ``0`` and never a label. A boolean is ``true`` or ``false``
    (checked before ``int``, which it is); a number is written as the API served it, so
    a negative number stays a number; a non-finite float (which ``json.loads`` accepts)
    is no figure, so it is empty. Anything else is text, guarded by :func:`guard`.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value) if math.isfinite(value) else ""
    return guard(str(value))


def sources(fields: Iterable[str]) -> list[tuple[str, str, str, str]]:
    """The sources a table with ``fields`` carries, in preamble order: the Electoral
    College's always, the popular vote's and the census's when a field of theirs is
    present."""
    names = set(fields)
    found = [EC_SOURCE]
    if names & POPULAR_VOTE_FIELDS:
        found.append(PV_SOURCE)
    if names & CENSUS_FIELDS:
        found.append(CENSUS_SOURCE)
    return found


def _line(text: str) -> str:
    """A preamble sentence: one line, guarded as a data cell is."""
    return guard(" ".join(text.splitlines()))


def preamble(
    fields: Sequence[str],
    provenance: dict[str, Any],
    url: str,
    notes: Iterable[str] = (),
) -> list[str]:
    """The preamble's sentences, in order, read from ``provenance``, never literals."""
    carried = sources(fields)
    coverage = provenance["coverage"]
    lines = [
        f"{label}: {provenance[name]} ({provenance[lic]}; {provenance[lic_url]})"
        for label, name, lic, lic_url in carried
    ]
    lines.append(f"Data snapshot: {provenance['snapshot_version']}")
    lines.append(f"Electoral votes cover {coverage['year_min']}–{coverage['year_max']}")
    if PV_SOURCE in carried:
        lines.append(
            f"Popular votes cover {coverage['pv_year_min']}–{coverage['pv_year_max']}"
        )
    lines.append(f"View: {url}")
    lines += notes
    lines.append(NULL_LINE)
    return [_line(str(text)) for text in lines]


#: The characters that make a field need quoting (RFC 4180).
QUOTE_WHEN = (",", '"', "\r", "\n")


def row(fields: Iterable[str]) -> str:
    """One CSV row (RFC 4180): a field holding a comma, a quote or a line break is
    quoted, its quotes doubled; rows end in CRLF."""
    return (
        ",".join(
            '"' + f.replace('"', '""') + '"' if any(c in f for c in QUOTE_WHEN) else f
            for f in fields
        )
        + "\r\n"
    )


def csv_text(
    fields: Sequence[str],
    rows: Iterable[dict[str, Any]],
    download: Download,
    notes: Iterable[str] = (),
) -> str:
    """The file: byte-order mark, preamble, a blank row, header, and one row per row."""
    lines = [
        row([COMMENT, text])
        for text in preamble(fields, download.provenance, download.view_url, notes)
    ]
    lines.append("\r\n")
    lines.append(row(fields))
    lines += [row([cell(values[field]) for field in fields]) for values in rows]
    return BOM + "".join(lines)


def href(text: str) -> str:
    """The ``data:`` URL carrying ``text``, every reserved character percent-encoded,
    so a ``#`` in the file never ends the URL."""
    return DATA_URL_PREFIX + quote(text, safe="")


def link_id(table_id: str) -> str:
    """The id of a table's download link."""
    return f"{table_id}-csv"


def link(table_id: str, download: Download, text: str) -> html.P:
    """A table's download link, named for what it downloads."""
    return html.P(
        html.A(
            f"Download {download.name} (CSV)",
            href=href(text),
            download=download.filename,
            id=link_id(table_id),
        ),
        className="download",
    )
