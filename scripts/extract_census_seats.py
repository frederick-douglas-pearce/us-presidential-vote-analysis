"""Extract published House seats per state from Census Table 3, and regenerate the
curated authority in :mod:`usvote.census.seats`.

**This is a local tool, not shipped code, and that placement is the whole design** (#183
architect review, Q1). The full-span published seats source
(``cph-2-1-1-table-3.pdf``, 1789-2010) is a **text-layer PDF**, and every parser
``usvote`` ships is stdlib-only (``zipfile`` + ``xml.etree`` -- see
:mod:`usvote.census.parse`, whose docstring is an extended argument for adding no
dependency). Putting a PDF reader on the runtime path would mean a system binary
(``poppler-utils``) that cannot be pinned in ``uv.lock``, on the CI critical path, in a
package whose parse stage exists to avoid exactly that.

So the seats are **curated into the repo** as a provenance-carrying constant -- the
:data:`usvote.pv.absences.PV_ABSENCE_CATALOG` precedent, available here because the
source is public domain (a US government work), unlike UCSB under D022. This script is
how that constant is produced and how it is re-verified:

* ``python3 scripts/extract_census_seats.py --generate`` rewrites
  ``src/usvote/census/seats.py`` from the corpus PDF.
* ``tests/unit/test_census_seats.py::TestRealCorpus`` imports :func:`parse_seats_text`
  and :func:`extract_seats_text` and compares the committed constant against a fresh
  extraction, **skipping when ``USVOTE_CENSUS_CORPUS_DIR`` is unset** -- the #234
  pattern, so CI never needs ``pdftotext``.

**Two published-source hazards live here rather than in ``src/``**, because they are
properties of the extraction and not of anything the warehouse runs:

1. **The two pages are mirrored.** Page 1 carries the state label on the **left** with
   years running 2010->1900; page 2 carries it on the **right** with years running
   1890->1789. Orientation is detected from the header rather than assumed, and the
   column->year map is read from that header rather than being positional -- the same
   rule #234 established for the transposed population table.
2. **One cell is corrupt in the published PDF.** See
   :data:`PUBLISHED_CELL_DEFECTS`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

#: The 50 states + DC, spelled as the EC spine spells them. Used to tell a state row
#: from the region/division subtotal rows the table interleaves ("Northeast Region",
#: "New England Division", "United States"), which must never become data.
STATE_NAMES: frozenset[str] = frozenset(
    {
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "District of Columbia", "Florida", "Georgia",
        "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
        "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
        "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
        "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
        "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
        "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
    }
)

#: The published source's own "not applicable" marker: this state had **no apportioned
#: seats** under this census. It is a *statement*, and it is deliberately not the same
#: thing as a cell this extractor failed to find -- see
#: :func:`usvote.census.reconcile.assert_seats_series_complete`.
NOT_APPLICABLE = "(X)"

#: Cells the published PDF renders wrongly, with the correct value and its independent
#: source. **One entry, and it must stay a declared exception rather than a lenient
#: parse rule.**
#:
#: Michigan's 1980 cell extracts as ``l8`` -- lowercase letter L followed by 8, not the
#: digits ``18``. The hazard here runs opposite to the obvious one: a strict ``int()``
#: **raises**, which is safe and loud, while a permissive ``\\d+`` scavenge silently
#: yields **8**, an 11-seat error wearing a perfectly plausible number. So
#: :func:`_read_cell` rejects anything that is not wholly ``(X)`` or digits, and this
#: map is the only way a non-conforming cell becomes a value.
#:
#: The correct value is confirmed **independently of the defective file**, from a
#: different published Bureau table: ``apportionment.csv`` (the 2020 apportionment
#: release, "Apportionment of Seats in the U.S. House of Representatives: 1910 to 2020")
#: gives Michigan 1980 = 18.
PUBLISHED_CELL_DEFECTS: dict[tuple[int, str], tuple[str, int]] = {
    (1980, "Michigan"): ("l8", 18),
}

_YEAR = re.compile(r"^(1[789]\d\d|20[01]\d)$")
_DIGITS = re.compile(r"^\d+$")
_LEADER = re.compile(r"[.…]+")


class SeatsExtractionError(RuntimeError):
    """Raised when the published seats table does not parse as expected."""


def extract_seats_text(pdf_path: str | Path) -> str:
    """Return ``pdftotext -layout`` output for the seats PDF.

    Shells out deliberately: this is the local tool, and keeping the dependency here is
    what keeps it out of ``src/`` and out of CI.
    """
    try:
        done = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment-dependent
        raise SeatsExtractionError(
            "pdftotext is not installed. It is required only by this local extraction "
            "tool and its corpus-gated test, never by usvote itself."
        ) from exc
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise SeatsExtractionError(
            f"pdftotext failed on {pdf_path}: "
            f"{exc.stderr.decode(errors='replace')[:200]}"
        ) from exc
    return done.stdout.decode("utf-8", errors="strict")


def _read_cell(token: str, *, year: int, state: str) -> int | None:
    """Return one cell's seat count, ``None`` for ``(X)``.

    **Strict by construction.** Anything that is neither ``(X)`` nor wholly digits
    raises, unless it is a declared entry in :data:`PUBLISHED_CELL_DEFECTS`. Scavenging
    digits out of a malformed cell is what would turn ``l8`` into ``8`` in silence.
    """
    if token == NOT_APPLICABLE:
        return None
    if _DIGITS.match(token):
        return int(token)
    defect = PUBLISHED_CELL_DEFECTS.get((year, state))
    if defect is not None and defect[0] == token:
        return defect[1]
    raise SeatsExtractionError(
        f"Seats cell for {state} in {year} is {token!r}, which is neither "
        f"{NOT_APPLICABLE!r} nor a number, and is not a declared "
        f"PUBLISHED_CELL_DEFECTS entry. Refusing to guess: a lenient read of a "
        f"corrupt cell yields a plausible wrong seat count."
    )


def _header_years(line: str) -> list[int]:
    return [int(tok) for tok in line.split() if _YEAR.match(tok)]


def _split_row(
    tokens: list[str], *, label_on_right: bool, width: int
) -> tuple[str, list[str]]:
    """Split a data row into ``(label, cells)`` honouring the page's orientation."""
    if label_on_right:
        return " ".join(tokens[width:]), tokens[:width]
    return " ".join(tokens[:-width]), tokens[-width:]


def parse_seats_text(text: str) -> dict[int, dict[str, int | None]]:
    """Parse extracted Table 3 text into ``{census_year: {state: seats | None}}``.

    Handles both page orientations, reads each page's column->year map from its own
    header, and ignores the region/division subtotal rows.
    """
    seats: dict[int, dict[str, int | None]] = {}
    pages = text.split("\f")
    parsed_pages = 0
    for page in pages:
        lines = page.splitlines()
        header_idx = None
        years: list[int] = []
        for idx, line in enumerate(lines):
            candidate = _header_years(line)
            if len(candidate) >= 8:
                header_idx, years = idx, candidate
                break
        if header_idx is None:
            continue
        stripped = lines[header_idx].strip()
        label_on_right = stripped.endswith("State")
        if not label_on_right and not stripped.startswith("State"):
            raise SeatsExtractionError(
                f"Cannot determine label orientation from header {stripped[:60]!r}; "
                f"refusing to assume one."
            )
        parsed_pages += 1
        width = len(years)
        for line in lines[header_idx + 1 :]:
            tokens = _LEADER.sub(" ", line).split()
            if len(tokens) <= width:
                continue
            label, cells = _split_row(
                tokens, label_on_right=label_on_right, width=width
            )
            label = label.strip()
            if label not in STATE_NAMES:
                continue
            for year, token in zip(years, cells, strict=True):
                seats.setdefault(year, {})[label] = _read_cell(
                    token, year=year, state=label
                )
    if parsed_pages != 2:
        raise SeatsExtractionError(
            f"Expected 2 pages of Table 3, parsed {parsed_pages}. The published layout "
            f"has changed; do not regenerate from it without re-reading it."
        )
    return seats


def _render(seats: dict[int, dict[str, int | None]], years: list[int]) -> str:
    out = []
    for year in years:
        by_state = seats[year]
        out.append(f"    {year}: {{")
        items = [
            f'"{state}": {"None" if by_state[state] is None else by_state[state]}'
            for state in sorted(by_state)
        ]
        line = "       "
        for item in items:
            piece = f" {item},"
            if len(line) + len(piece) > 88:
                out.append(line)
                line = "       "
            line += piece
        out.append(line)
        out.append("    },")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="path to cph-2-1-1-table-3.pdf")
    parser.add_argument("--show", action="store_true", help="print a summary only")
    args = parser.parse_args(argv)
    seats = parse_seats_text(extract_seats_text(args.pdf))
    years = sorted(seats)
    if args.show:
        for year in years:
            counted = sum(1 for v in seats[year].values() if v is not None)
            total = sum(v for v in seats[year].values() if v is not None)
            print(f"{year}: {counted:2d} states with seats, total {total}")
        return 0
    print(_render(seats, years))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
