"""Presentation-layer provenance lookups (E8-S4, #98): codes → public display text.

The snapshot stores only short **codes** (``source="MIT"``, ``license="CC0-1.0"``) —
that is the drift-proof source of truth (D016/D028). Turning those codes into the
public, human-facing strings the OpenAPI surface advertises (the spelled-out source
name, the license URL, the redistributable-boundary statement) is *presentation*
knowledge, so it lives here in the API subpackage rather than in the build↔serve
contract (:mod:`usvote.snapshot_schema`).

The maps are keyed **by** the raw codes, so this module can never become a second
source of truth for the code values themselves — it only *annotates* a code the
snapshot already emitted. An unmapped code raises :class:`UnknownProvenanceCode` rather
than silently blanking: a new PV source must add its display row here, and a test
asserts the codes the snapshot can emit are all mapped.

Stdlib-only (dataclasses): nothing here may drag pandas/DB across the ``usvote/api/``
import boundary (D028, enforced by ``tests/unit/test_api_import_graph.py``).
"""

from __future__ import annotations

from dataclasses import dataclass


class UnknownProvenanceCode(Exception):
    """A source/license code has no public display mapping (fail loud, D005)."""


@dataclass(frozen=True)
class SourceDisplay:
    """Public presentation of a PV ``source`` code."""

    code: str
    name: str


@dataclass(frozen=True)
class LicenseDisplay:
    """Public presentation of a PV ``license`` code."""

    code: str
    name: str
    url: str


#: Source code → spelled-out name. Keyed by the snapshot's ``source`` / ``ec_source``
#: codes. The **popular-vote** side is MIT-only (D016: redistributable=true; UCSB is
#: excluded at the source). The **electoral-college** side is the National Archives, and
#: it arrived with #139 (D048): the surface used to be MIT's window and nothing else, so
#: one source told the whole story. It no longer does — most of the widened table is
#: 1824–1972, where there is no popular vote at all and the only data is the Archives'.
_SOURCES: dict[str, SourceDisplay] = {
    "MIT": SourceDisplay(code="MIT", name="MIT Election Lab"),
    "NARA": SourceDisplay(
        code="NARA", name="U.S. National Archives and Records Administration"
    ),
}

#: License code → name + canonical URL. Keyed by the snapshot's ``license`` /
#: ``ec_license`` codes (D016: MIT is CC0 1.0, verified against the upstream Harvard
#: Dataverse record). ``US-PD`` is not an SPDX identifier because there is none for the
#: case: a work of the U.S. Government is uncopyrightable by statute rather than
#: released under a license (17 U.S.C. § 105). That statutory status is exactly what
#: lets ``count_status_reason`` ship the Archives' own sentence where UCSB prose cannot
#: (D022 / D044 §3).
_LICENSES: dict[str, LicenseDisplay] = {
    "CC0-1.0": LicenseDisplay(
        code="CC0-1.0",
        name="CC0 1.0 Universal (Public Domain Dedication)",
        url="http://creativecommons.org/publicdomain/zero/1.0",
    ),
    "US-PD": LicenseDisplay(
        code="US-PD",
        name="Public domain (a work of the U.S. Government, 17 U.S.C. § 105)",
        url="https://www.usa.gov/government-works",
    ),
}


def source_display(code: str) -> SourceDisplay:
    """Return the public display for a ``source`` code, or fail loud if unmapped."""
    try:
        return _SOURCES[code]
    except KeyError:
        raise UnknownProvenanceCode(
            f"No provenance display mapping for source code {code!r}; add it to "
            f"usvote.api.provenance._SOURCES."
        ) from None


def license_display(code: str) -> LicenseDisplay:
    """Return the public display for a ``license`` code, or fail loud if unmapped."""
    try:
        return _LICENSES[code]
    except KeyError:
        raise UnknownProvenanceCode(
            f"No provenance display mapping for license code {code!r}; add it to "
            f"usvote.api.provenance._LICENSES."
        ) from None


def redistributable_note(
    source: SourceDisplay,
    license_: LicenseDisplay,
    *,
    ec_source: SourceDisplay,
    ec_license: LicenseDisplay,
    pv_year_min: int,
    pv_year_max: int,
) -> str:
    """The redistributable-boundary statement, built from the resolved displays (D030).

    Composed from the resolved displays so no source or license name appears twice —
    this note cannot drift from :data:`_SOURCES` / :data:`_LICENSES`.

    **It names both provenances, and that is the point** (#139 / D048). Before the
    surface widened, every row carried MIT popular vote, so a note naming only MIT was
    complete. After it, most rows are electoral-college data from the Archives with no
    popular vote at all — and a note that still said "sourced from MIT Election Lab"
    beside a rendered coverage window of 1824–2024 would assert, to a reader, that MIT
    covers 1824. The popular-vote window is stated numerically here for the same reason:
    "which years can I actually compare popular votes for" must be answerable from the
    text, not inferred from a field of nulls.
    """
    return (
        f"Redistributable data only. Electoral-college figures come from the "
        f"{ec_source.name} — {ec_license.name} — and cover every election in the "
        f"snapshot. Popular-vote figures come from {source.name} under "
        f"{license_.name} and cover {pv_year_min}–{pv_year_max} only; earlier "
        f"elections carry no popular vote on this surface, and each row's `pv_status` "
        f"says whether that is because none was held or because no redistributable "
        f"source reaches it. Non-redistributable UCSB / American Presidency Project "
        f"data is excluded from this public API surface."
    )
