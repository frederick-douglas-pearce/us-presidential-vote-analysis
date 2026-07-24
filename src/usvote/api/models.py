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

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

#: Snapshot columns intentionally **not** on any public model. Empty today (every
#: ``ec_pv`` / ``national_rollup`` column is exposed under a public name), but the drift
#: guard reads this list, so a deliberately-internal future column has an explicit home
#: here rather than silently failing the completeness assert.
_DROPPED_COLUMNS: frozenset[str] = frozenset()

_ROW_CONFIG = ConfigDict(populate_by_name=True)


class EcPvRow(BaseModel):
    """One joined EC+PV fact row — a single ``(year, state, candidate)`` observation.

    The ``electoral_*`` / ``popular_*`` fields are renamed from the snapshot's internal
    ``president_*`` / ``candidate_votes`` / ``*_total_votes`` columns for a reader.
    PV fields are ``None`` for an EC getter MIT does not cover (an honest gap, never a
    fabricated 0) — see ``docs/api-snapshot.md``.
    """

    model_config = _ROW_CONFIG

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
        description="This candidate's electoral votes in this state (0 for a loser).",
    )
    national_electoral_votes: int = Field(
        description="This candidate's national EC total this year (window sum)."
    )
    electoral_rank: int = Field(
        validation_alias="president_electoral_rank",
        description="This candidate's national EC finishing rank (1 = most EVs).",
    )
    took_office: bool = Field(
        description="Whether this candidate assumed the presidency this term."
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

    The flip-relevant national totals only — national EC, national PV, and the PV
    denominator. No hybrid / flip / margin (those are E8-S8).
    """

    model_config = _ROW_CONFIG

    year: int = Field(description="Election year.")
    candidate: str = Field(description="Canonical candidate display name.")
    candidate_slug: str = Field(description="Durable public candidate id.")
    party: str | None = Field(
        default=None, description="Party of record (None where no PV is available)."
    )
    national_electoral_votes: int = Field(
        description="This candidate's national electoral-vote total this year."
    )
    electoral_rank: int = Field(
        validation_alias="president_electoral_rank",
        description="National EC finishing rank (1 = most EVs).",
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

    year: int = Field(description="A redistributable election year in the data.")
    candidate_count: int = Field(
        description="Distinct candidates with national roll-up rows this year."
    )


class Coverage(BaseModel):
    """The inclusive year window the snapshot contains (descriptive, not a promise)."""

    year_min: int
    year_max: int


class Meta(BaseModel):
    """The shared response envelope's provenance block.

    ``count`` is always ``len(data)`` for the response it accompanies — for an election
    detail response the sibling ``summary`` list is **not** counted.
    """

    snapshot_version: str = Field(description="Content-hash snapshot version (ETag).")
    source: str = Field(description="PV data source, e.g. 'MIT'.")
    license: str = Field(description="PV data license, e.g. 'CC0-1.0'.")
    coverage: Coverage = Field(description="The year window the snapshot contains.")
    count: int = Field(description="Number of items in this response's `data` array.")


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

    error: ErrorDetail
