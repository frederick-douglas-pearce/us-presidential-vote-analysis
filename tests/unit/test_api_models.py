"""Drift guard for the API response models (``usvote.api.models``, E8-S3 #97).

The public models rename several snapshot columns (``president_electoral_votes`` →
``electoral_votes``, …). That column↔field mapping is hand-maintained, so a column added
to the snapshot contract (:mod:`usvote.snapshot_schema`) could silently fail to surface on
the API. These tests assert every ``DATA_COLUMNS`` / ``ROLLUP_COLUMNS`` entry is either
mapped to a model field (by name or ``alias``) or explicitly listed on
``models._DROPPED_COLUMNS`` — mirroring the "validation is load-bearing" discipline and the
single-source-of-truth role of ``snapshot_schema``.
"""

from __future__ import annotations

import pydantic

from usvote.api import models
from usvote.snapshot_schema import DATA_COLUMNS, ROLLUP_COLUMNS


def _mapped_columns(model: type[pydantic.BaseModel]) -> set[str]:
    """The snapshot-column names a model consumes: each field's validation alias or name."""
    out: set[str] = set()
    for name, f in model.model_fields.items():
        va = f.validation_alias
        out.add(va if isinstance(va, str) else (f.alias or name))
    return out


def test_every_data_column_is_mapped_or_dropped() -> None:
    covered = _mapped_columns(models.EcPvRow) | models._DROPPED_COLUMNS
    missing = set(DATA_COLUMNS) - covered
    assert not missing, f"unmapped ec_pv columns (add a field or drop them): {missing}"


def test_every_rollup_column_is_mapped_or_dropped() -> None:
    covered = _mapped_columns(models.NationalSummaryRow) | models._DROPPED_COLUMNS
    missing = set(ROLLUP_COLUMNS) - covered
    assert not missing, f"unmapped rollup columns (add a field or drop them): {missing}"


def test_candidate_id_is_never_a_model_field() -> None:
    """D006: the internal surrogate must not appear on any public model."""
    for model in (models.EcPvRow, models.NationalSummaryRow, models.YearListItem):
        assert "candidate_id" not in _mapped_columns(model)
        assert "candidate_id" not in model.model_fields
