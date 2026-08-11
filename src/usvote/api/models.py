"""Pydantic response models + the shared ``{data, meta}`` envelope (E8-S3, #97).

The public surface of the API. Each snapshot column (:mod:`usvote.snapshot_schema`
``DATA_COLUMNS`` / ``ROLLUP_COLUMNS``) maps to a **field on one of these models** whose
name reads naturally to an external consumer — the ``president_*`` internal prefix (this
candidate's per-state electoral votes, not "the president's") is renamed to a clearer
public name. The snapshot column is the field's ``validation_alias`` (input only), so a
row keyed by snapshot columns validates directly (``model_validate(dict(row))``) while
the response serializes back under the **public field name** (FastAPI dumps
``by_alias=True``, falling back to the field name when only a validation alias is set).

That column↔field mapping is the single source of truth a drift guard keys off
(``tests/unit/test_api_models.py``): every ``DATA_COLUMNS`` / ``ROLLUP_COLUMNS`` entry
must be a field name / validation alias on its model or on :data:`_DROPPED_COLUMNS`, so
a column added to the snapshot contract cannot silently fail to surface.

Boundary (D028): pydantic + :mod:`usvote.snapshot_schema` only (no pandas, no DB).
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from usvote.api import provenance
from usvote.snapshot_schema import SnapshotMeta

#: Snapshot columns intentionally **not** on any public model. Empty today (every
#: ``ec_pv`` / ``national_rollup`` column is exposed under a public name), but the drift
#: guard reads this list, so a deliberately-internal future column has an explicit home
#: here rather than silently failing the completeness assert.
_DROPPED_COLUMNS: frozenset[str] = frozenset()


def _config(*examples: dict[str, Any]) -> ConfigDict:
    """Row config that also carries the OpenAPI examples (in public field names).

    ``populate_by_name=True`` lets a snapshot row validate by ``validation_alias`` *and*
    lets an example authored in the **public** field name validate — so the examples
    Swagger renders are exactly what an external consumer sends/receives, and the
    ``test_api_models`` drift guard can ``model_validate`` each one (D004: validation is
    load-bearing).

    Variadic since #139: ``EcPvRow`` now ships two, because the modern and pre-1976
    shapes differ in every way that matters to a reader — one has popular votes, the
    other has a ``pv_status`` explaining their absence and a count status explaining a
    rejected electoral vote. One example could only show half the surface.
    """
    return ConfigDict(
        populate_by_name=True, json_schema_extra={"examples": list(examples)}
    )


# Realistic examples, authored once as module constants so the drift guard can import
# and ``model_validate`` them. The 2000 Bush/Florida observation is the canonical
# figure — the election the whole thesis is built around (lost the PV, took office).
_COVERAGE_EXAMPLE: dict[str, Any] = {
    "year_min": 1824,
    "year_max": 2024,
    "pv_year_min": 1976,
    "pv_year_max": 2024,
}

_EC_PV_ROW_EXAMPLE: dict[str, Any] = {
    "year": 2000,
    "state": "Florida",
    "state_usps": "FL",
    "candidate": "George W. Bush",
    "candidate_slug": "george-w-bush",
    "state_electoral_votes": 25,
    "electoral_votes": 25,
    "electoral_votes_counted": 25,
    "national_electoral_votes": 271,
    "national_electoral_votes_counted": 271,
    "electoral_rank": 1,
    "took_office": True,
    "electoral_count_status": "counted",
    "electoral_count_status_reason": None,
    "pv_status": "popular_vote",
    "source": "MIT",
    "party": "REPUBLICAN",
    "popular_votes": 2912790,
    "state_popular_total": 5963110,
    "reliability": "exact",
}

# The pre-1976 shape, shown deliberately: 1872 Georgia is the row where every column
# this issue added is doing work at once — votes cast but not counted, an Archives
# sentence saying why, and a popular vote that exists but is not on this surface.
_EC_PV_PRE_1976_EXAMPLE: dict[str, Any] = {
    "year": 1872,
    "state": "Georgia",
    "state_usps": "GA",
    "candidate": "Horace Greeley",
    "candidate_slug": "horace-greeley",
    "state_electoral_votes": 11,
    "electoral_votes": 3,
    "electoral_votes_counted": 0,
    "national_electoral_votes": 3,
    "national_electoral_votes_counted": 0,
    "electoral_rank": 6,
    "took_office": False,
    "electoral_count_status": "not_counted",
    "electoral_count_status_reason": (
        "In Georgia, Greeley received 3 electoral votes for President, but these were "
        "not counted by resolution of the House."
    ),
    "pv_status": "popular_vote",
    "source": None,
    "party": None,
    "popular_votes": None,
    "state_popular_total": None,
    "reliability": None,
}

_NATIONAL_SUMMARY_EXAMPLE: dict[str, Any] = {
    "year": 2000,
    "candidate": "Albert Gore Jr.",
    "candidate_slug": "albert-gore-jr",
    "party": "DEMOCRAT",
    "national_electoral_votes": 266,
    "national_electoral_votes_counted": 266,
    "national_electoral_denominator": 538,
    "electoral_rank": 2,
    "took_office": False,
    "national_pv_votes": 50996062,
    "national_pv_denominator": 105593982,
}

_YEAR_LIST_EXAMPLE: dict[str, Any] = {
    "year": 2000,
    "candidate_count": 7,
    "has_popular_vote": True,
}

# Derive every display field from the provenance maps (not literals), so the shipped
# example can't drift from _SOURCES / _LICENSES if a name or URL is ever edited.
_EX_SRC = provenance.source_display("MIT")
_EX_LIC = provenance.license_display("CC0-1.0")
_EX_EC_SRC = provenance.source_display("NARA")
_EX_EC_LIC = provenance.license_display("US-PD")

_PROVENANCE_EXAMPLE: dict[str, Any] = {
    "snapshot_version": (
        "bc6056f38fd9ed04f396a2e54a38a657994a4d8f0a8a317526e47bfb92cd33f2"
    ),
    "source": _EX_SRC.code,
    "source_name": _EX_SRC.name,
    "license": _EX_LIC.code,
    "license_url": _EX_LIC.url,
    "ec_source": _EX_EC_SRC.code,
    "ec_source_name": _EX_EC_SRC.name,
    "ec_license": _EX_EC_LIC.code,
    "ec_license_url": _EX_EC_LIC.url,
    "coverage": _COVERAGE_EXAMPLE,
    "redistributable_note": provenance.redistributable_note(
        _EX_SRC,
        _EX_LIC,
        ec_source=_EX_EC_SRC,
        ec_license=_EX_EC_LIC,
        pv_year_min=1976,
        pv_year_max=2024,
    ),
}

_META_EXAMPLE: dict[str, Any] = {"provenance": _PROVENANCE_EXAMPLE, "count": 2}

_SNAPSHOT_META_RESPONSE_EXAMPLE: dict[str, Any] = {
    "provenance": _PROVENANCE_EXAMPLE,
    "schema_version": 2,
    "row_count": 5623,
    "candidate_count": 96,
    "build_timestamp": "2026-08-10T01:05:05.969957+00:00",
}

_ERROR_EXAMPLE: dict[str, Any] = {
    "error": {
        "code": "year_not_found",
        "message": (
            "No election data for year 1800; the snapshot covers 1824–2024 "
            "(popular vote 1976–2024)."
        ),
    }
}


class EcPvRow(BaseModel):
    """One joined EC+PV fact row — a single ``(year, state, candidate)`` observation.

    The ``electoral_*`` / ``popular_*`` fields are renamed from the snapshot's internal
    ``president_*`` / ``candidate_votes`` / ``*_total_votes`` columns for a reader.
    PV fields are ``None`` wherever no redistributable popular vote exists (an honest
    gap, never a fabricated 0) — which, since the surface widened to 1824, is most of
    the table. ``pv_status`` is the sibling that says *which kind* of nothing it is, so
    a null popular vote is never bare; see ``docs/api-snapshot.md``.

    **Two electoral-vote measures, and they are not interchangeable.**
    ``electoral_votes`` is what the state's electors **cast**;
    ``electoral_votes_counted`` is what entered Congress's final count. They differ in
    exactly two elections (1868 and 1872) and ``electoral_count_status`` says why.
    ``electoral_rank`` and ``took_office`` are on the **counted** basis, because who won
    is settled by the votes Congress counted (D046).
    """

    model_config = _config(_EC_PV_ROW_EXAMPLE, _EC_PV_PRE_1976_EXAMPLE)

    year: int = Field(description="Election year.")
    state: str = Field(description="Full state name (the canonical grain key).")
    state_usps: str = Field(description="USPS two-letter code, e.g. 'CA'.")
    candidate: str = Field(description="Canonical candidate display name.")
    candidate_slug: str = Field(
        description="Durable public candidate id (deterministic name slug)."
    )
    state_electoral_votes: int = Field(
        validation_alias="total_electoral_votes",
        description="The state's total electoral-vote allotment this year.",
    )
    electoral_votes: int = Field(
        validation_alias="president_electoral_votes",
        description=(
            "Electoral votes this candidate's electors CAST in this state (0 for a "
            "loser). See electoral_votes_counted for what Congress counted."
        ),
    )
    electoral_votes_counted: int = Field(
        validation_alias="president_electoral_votes_counted",
        description=(
            "Of those cast, the electoral votes that entered Congress's final count. "
            "Equal to electoral_votes except in 1868 and 1872."
        ),
    )
    national_electoral_votes: int = Field(
        description="This candidate's national CAST electoral-vote total this year."
    )
    national_electoral_votes_counted: int = Field(
        validation_alias="national_counted_electoral_votes",
        description=(
            "This candidate's national COUNTED electoral-vote total this year — e.g. "
            "Grant in 1872 cast 300 and counted 286."
        ),
    )
    electoral_rank: int = Field(
        validation_alias="president_electoral_rank",
        description=(
            "This candidate's national EC finishing rank (1 = most EVs), on the "
            "COUNTED basis — so it may not order the cast totals."
        ),
    )
    took_office: bool = Field(
        description="Whether this candidate assumed the presidency this term."
    )
    electoral_count_status: str = Field(
        validation_alias="count_status",
        description=(
            "Whether these cast electoral votes were counted by Congress: 'counted', "
            "'not_counted' (Congress refused them), or 'disputed' (Congress never "
            "resolved the question)."
        ),
    )
    electoral_count_status_reason: str | None = Field(
        default=None,
        validation_alias="count_status_reason",
        description=(
            "The National Archives' own sentence explaining a non-'counted' status; "
            "None when the votes were counted normally."
        ),
    )
    pv_status: str = Field(
        description=(
            "Why this state has or lacks a popular vote: 'popular_vote' (one was "
            "held), 'legislature_chosen' (the legislature appointed the electors), or "
            "'not_participating' (the state took no part). A 'popular_vote' state with "
            "null popular_votes simply falls outside this surface's popular-vote "
            "window — see meta.provenance.coverage."
        ),
    )
    source: str | None = Field(
        default=None, description="PV data source (None where no PV is available)."
    )
    party: str | None = Field(
        default=None, description="Party of record (None where no PV is available)."
    )
    popular_votes: int | None = Field(
        default=None,
        validation_alias="candidate_votes",
        description="This candidate's popular votes in this state (None where no PV).",
    )
    state_popular_total: int | None = Field(
        default=None,
        validation_alias="state_total_votes",
        description="The state's total votes cast (source denominator; None if no PV).",
    )
    reliability: str | None = Field(
        default=None, description="PV reliability tag (None where no PV is available)."
    )


class NationalSummaryRow(BaseModel):
    """One per-candidate national roll-up row for a year (from ``national_rollup``).

    The flip-relevant national totals only — national EC (cast and counted, with the
    appointed denominator), national PV, and the PV denominator. No hybrid / flip /
    margin (those are E8-S8).

    **There is deliberately no ``pv_status`` here, and its absence is a design choice
    rather than an omission.** A year can be *mixed* — in 1824 six states' legislatures
    appointed electors while eighteen held a popular vote — so no single status is true
    of a whole year, and inventing one would be exactly the flattening this project
    objects to. A summary row's null popular vote is disambiguated at **year** level
    instead: ``meta.provenance.coverage.pv_year_min`` and the ``has_popular_vote`` flag
    on ``GET /v1/elections``. Per-state reasons live on the fact rows.
    """

    model_config = _config(_NATIONAL_SUMMARY_EXAMPLE)

    year: int = Field(description="Election year.")
    candidate: str = Field(description="Canonical candidate display name.")
    candidate_slug: str = Field(description="Durable public candidate id.")
    party: str | None = Field(
        default=None, description="Party of record (None where no PV is available)."
    )
    national_electoral_votes: int = Field(
        description="This candidate's national CAST electoral-vote total this year."
    )
    national_electoral_votes_counted: int = Field(
        validation_alias="national_counted_electoral_votes",
        description=(
            "This candidate's national COUNTED electoral-vote total — the votes that "
            "entered Congress's final count."
        ),
    )
    national_electoral_denominator: int = Field(
        description=(
            "The year's whole number of electors APPOINTED (each state counted once) "
            "— the 12th Amendment's denominator. A majority of it wins outright: 1872 "
            "is 366, so Grant's 286 counted votes cleared the 184 needed."
        )
    )
    electoral_rank: int = Field(
        validation_alias="president_electoral_rank",
        description=(
            "National EC finishing rank (1 = most EVs), on the COUNTED basis — so it "
            "may not order the cast totals."
        ),
    )
    took_office: bool = Field(
        description="Whether this candidate assumed the presidency this term."
    )
    national_pv_votes: int | None = Field(
        default=None,
        description="This candidate's national popular-vote total (None where no PV).",
    )
    national_pv_denominator: int | None = Field(
        default=None,
        description="Total votes cast nationally this year (each state counted once).",
    )


class YearListItem(BaseModel):
    """One entry in the list-years index: a covered year and its candidate count."""

    model_config = _config(_YEAR_LIST_EXAMPLE)

    year: int = Field(description="An election year in the data.")
    candidate_count: int = Field(
        description="Distinct candidates with national roll-up rows this year."
    )
    has_popular_vote: bool = Field(
        description=(
            "Whether this year carries popular-vote figures on this surface. False for "
            "every election before the popular-vote window — the electoral-college "
            "data is still complete. Answers 'which years can I compare PV for' "
            "without a second call."
        )
    )


class Coverage(BaseModel):
    """The year windows the snapshot contains (descriptive, not a promise).

    **Two windows, because they genuinely differ.** ``year_min``/``year_max`` is
    everything the snapshot serves; ``pv_year_min``/``pv_year_max`` is the narrower
    span that also carries popular votes. Stating both here is what stops a reader
    inferring coverage from a field of nulls — the mistake this whole surface is built
    to make impossible.
    """

    year_min: int = Field(description="Earliest election year in the snapshot.")
    year_max: int = Field(description="Latest election year in the snapshot.")
    pv_year_min: int = Field(
        description="Earliest election year with popular-vote data."
    )
    pv_year_max: int = Field(description="Latest election year with popular-vote data.")


class Provenance(BaseModel):
    """Where every response's data came from — identical across the whole snapshot.

    The raw codes and ``coverage`` / ``snapshot_version`` are read **straight from the
    snapshot metadata** (E8-S1) so they can't drift from what was actually built; the
    human ``*_name`` / ``*_url`` / ``redistributable_note`` are the presentation of
    those codes (:mod:`usvote.api.provenance`). The note makes the D030 redistributable
    boundary explicit: MIT (CC0) and the Archives (public domain) only, UCSB excluded.

    **Two provenances, because the surface has two** (#139 / D048). ``source`` /
    ``license`` describe the **popular-vote** data and keep their original unprefixed
    names for backward compatibility; ``ec_source`` / ``ec_license`` describe the
    **electoral-college** data. Before the window widened the distinction was invisible
    — every served row had MIT popular vote attached. It is not invisible now: most of
    the table is pre-1976, where the only data is the Archives'.
    """

    model_config = _config(_PROVENANCE_EXAMPLE)

    snapshot_version: str = Field(description="Content-hash snapshot version (ETag).")
    source: str = Field(description="Popular-vote data source code, e.g. 'MIT'.")
    source_name: str = Field(description="Spelled-out source, e.g. 'MIT Election Lab'.")
    license: str = Field(description="Popular-vote data license code, e.g. 'CC0-1.0'.")
    license_url: str = Field(description="Canonical URL for the license.")
    ec_source: str = Field(
        description="Electoral-college data source code, e.g. 'NARA'."
    )
    ec_source_name: str = Field(
        description="Spelled-out EC source, e.g. 'U.S. National Archives …'."
    )
    ec_license: str = Field(
        description="Electoral-college data license code, e.g. 'US-PD'."
    )
    ec_license_url: str = Field(description="Canonical URL for the EC license.")
    coverage: Coverage = Field(description="The year windows the snapshot contains.")
    redistributable_note: str = Field(
        description="Plain-language statement of the redistributable data boundary."
    )

    @classmethod
    def from_snapshot_meta(cls, meta: SnapshotMeta) -> Provenance:
        """Build from snapshot metadata, resolving the code → display mappings.

        Raises :class:`usvote.api.provenance.UnknownProvenanceCode` if the snapshot's
        source/license code has no public display — a new source must be mapped, never
        silently blanked.
        """
        src = provenance.source_display(meta.source)
        lic = provenance.license_display(meta.license)
        ec_src = provenance.source_display(meta.ec_source)
        ec_lic = provenance.license_display(meta.ec_license)
        return cls(
            snapshot_version=meta.snapshot_version,
            source=src.code,
            source_name=src.name,
            license=lic.code,
            license_url=lic.url,
            ec_source=ec_src.code,
            ec_source_name=ec_src.name,
            ec_license=ec_lic.code,
            ec_license_url=ec_lic.url,
            coverage=Coverage(
                year_min=meta.year_min,
                year_max=meta.year_max,
                pv_year_min=meta.pv_year_min,
                pv_year_max=meta.pv_year_max,
            ),
            redistributable_note=provenance.redistributable_note(
                src,
                lic,
                ec_source=ec_src,
                ec_license=ec_lic,
                pv_year_min=meta.pv_year_min,
                pv_year_max=meta.pv_year_max,
            ),
        )


class Meta(BaseModel):
    """The response envelope's ``meta`` block: provenance + this response's count.

    ``provenance`` is snapshot-scoped (the same on every response); ``count`` is
    response-scoped and is always ``len(data)`` for the response it accompanies — for an
    election detail response the sibling ``summary`` list is **not** counted.
    """

    model_config = _config(_META_EXAMPLE)

    provenance: Provenance = Field(description="Data source, license, and coverage.")
    count: int = Field(description="Number of items in this response's `data` array.")


class SnapshotMetaResponse(BaseModel):
    """The ``GET /v1/meta`` payload: full snapshot provenance plus build/ops details.

    ``provenance`` is the same block that rides in every response envelope's ``meta``;
    the remaining fields are operational (schema version, row/candidate counts, the
    informational build timestamp) — useful when inspecting the served snapshot.
    """

    model_config = ConfigDict(
        json_schema_extra={"examples": [_SNAPSHOT_META_RESPONSE_EXAMPLE]}
    )

    provenance: Provenance = Field(description="Data source, license, and coverage.")
    schema_version: int = Field(description="Snapshot serving-contract schema version.")
    row_count: int = Field(description="Number of `ec_pv` fact rows in the snapshot.")
    candidate_count: int = Field(description="Distinct candidates in the snapshot.")
    build_timestamp: str = Field(
        description="When the snapshot was built (informational; not part of the ETag)."
    )


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    """The standard ``{data, meta}`` response wrapper for a list payload."""

    data: list[T]
    meta: Meta


class ElectionResponse(BaseModel):
    """One election: its per-state fact rows plus the national roll-up (AC point 2).

    ``data`` carries the state rows; ``summary`` carries the per-candidate national
    roll-up. ``meta.count`` counts ``data`` only.
    """

    data: list[EcPvRow]
    summary: list[NationalSummaryRow]
    meta: Meta


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable explanation.")


class ErrorBody(BaseModel):
    """The typed body returned on a 404 (never a stack trace)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_ERROR_EXAMPLE]})

    error: ErrorDetail
