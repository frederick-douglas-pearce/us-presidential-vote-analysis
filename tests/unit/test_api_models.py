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

import json
from typing import Any

import pydantic

from tests._helpers import FIXTURES_DIR
from usvote.api import models
from usvote.join import EC_PV_COLUMNS
from usvote.snapshot import DERIVED_DATA_COLUMNS
from usvote.snapshot_schema import (
    DATA_COLUMNS,
    HYBRID_SUMMARY_COLUMNS,
    PER_CAPITA_COLUMNS,
    ROLLUP_COLUMNS,
)


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


def test_every_hybrid_summary_column_is_mapped_or_dropped() -> None:
    """The third tuple joins the drift guard (#102).

    Without this, every column on the new ``hybrid_summary`` table sits **outside** the
    guard's coverage: the two asserts above read ``DATA_COLUMNS`` and
    ``ROLLUP_COLUMNS`` only, so a per-election field added to the snapshot contract and
    never given a model field would surface nowhere and fail nothing.
    """
    covered = _mapped_columns(models.ElectionSummary) | models._DROPPED_COLUMNS
    missing = set(HYBRID_SUMMARY_COLUMNS) - covered
    assert not missing, (
        f"unmapped hybrid_summary columns (add a field or drop them): {missing}"
    )


def test_every_data_column_comes_from_the_join_view_or_is_explicitly_derived() -> None:
    """``DATA_COLUMNS`` ⊆ ``EC_PV_COLUMNS`` ∪ the explicitly-derived set.

    A **subset** assert, and the direction matters. The reverse — asserting
    ``DATA_COLUMNS`` covers ``EC_PV_COLUMNS`` — is forbidden by D047 §3: the two tuples
    are independent on purpose, which is exactly what let #144 add join-view columns
    without touching the public payload or the content hash. Coupling them would undo
    that.

    What this catches is a typo in a hand-added name. Both the snapshot projection and
    the synthetic test frame are hand-authored, so the *same* misspelling in both passes
    the whole offline suite and fails only at ``data_df[list(DATA_COLUMNS)]`` against a
    real warehouse — on the one machine that has one.
    """
    unexplained = set(DATA_COLUMNS) - set(EC_PV_COLUMNS) - DERIVED_DATA_COLUMNS
    assert not unexplained, (
        f"DATA_COLUMNS entries {sorted(unexplained)} are neither join-view columns nor "
        "listed in DERIVED_DATA_COLUMNS — likely a typo, which would only surface "
        "against a live warehouse."
    )


def test_candidate_id_is_never_a_model_field() -> None:
    """D006: the internal surrogate must not appear on any public model."""
    for model in (
        models.EcPvRow,
        models.NationalSummaryRow,
        models.YearListItem,
        models.CandidateListItem,
    ):
        assert "candidate_id" not in _mapped_columns(model)
        assert "candidate_id" not in model.model_fields


def _models_with_examples() -> list[tuple[type[pydantic.BaseModel], Any]]:
    """Every model that ships an OpenAPI ``examples`` list, paired with its examples."""
    out: list[tuple[type[pydantic.BaseModel], Any]] = []
    for name in dir(models):
        obj = getattr(models, name)
        if not (isinstance(obj, type) and issubclass(obj, pydantic.BaseModel)):
            continue
        extra = obj.model_config.get("json_schema_extra")
        if isinstance(extra, dict) and "examples" in extra:
            out.append((obj, extra["examples"]))
    return out


def test_every_shipped_example_validates() -> None:
    """The hand-authored OpenAPI examples must validate against their model (E8-S4 #98).

    Examples are authored in the **public** field names Swagger renders; ``model_validate``
    catches any key/type drift the same way the column guard catches snapshot drift — so a
    stale example fails CI rather than misleading an external developer.
    """
    pairs = _models_with_examples()
    assert pairs, "no models ship OpenAPI examples — did the config helper regress?"
    for model, examples in pairs:
        for ex in examples:
            model.model_validate(ex)  # raises on drift


def test_the_pre_1976_example_ships_the_served_greeley_note() -> None:
    """The 1872 Greeley example's note is the served value verbatim (#386).

    Pinned here rather than imported into ``models.py``, which may not import
    ``usvote.party`` (the serving side's import set stays ``snapshot_schema`` + pydantic).
    """
    from usvote.party import TABLE1_ROW_NOTES

    example = models._EC_PV_PRE_1976_EXAMPLE
    assert example["candidate"] == "Horace Greeley"
    assert example["nominating_party_note"] == TABLE1_ROW_NOTES[(1872, "Horace Greeley")]


def test_key_public_models_ship_an_example() -> None:
    """The public-facing response models each advertise at least one example.

    Counts a model only when its examples list is non-empty: an ``examples`` key
    holding ``[]`` advertises nothing.
    """
    with_examples = {model for model, examples in _models_with_examples() if examples}
    for model in (
        models.EcPvRow,
        models.NationalSummaryRow,
        models.YearListItem,
        models.CandidateListItem,
        models.Provenance,
        models.Meta,
        models.SnapshotMetaResponse,
        models.ErrorBody,
    ):
        assert model in with_examples, model.__name__


def test_every_per_capita_column_is_mapped_or_dropped() -> None:
    """The fourth tuple joins the drift guard (#245), for the reason the third did."""
    covered = _mapped_columns(models.PerCapitaRow) | models._DROPPED_COLUMNS
    missing = set(PER_CAPITA_COLUMNS) - covered
    assert not missing, (
        f"unmapped per_capita columns (add a field or drop them): {missing}"
    )


# Recorded ``/v1`` responses from the deployed API (test input only). They were not
# built from these models, so comparing an example with them is not circular. They are
# a recording, not the live API: an example follows a later snapshot only once the
# fixtures are re-recorded.
_RECORDED = FIXTURES_DIR / "dashboard"


def _recorded(name: str) -> dict[str, Any]:
    body: dict[str, Any] = json.loads((_RECORDED / name).read_text(encoding="utf-8"))
    return body


def _published_examples(model: type[pydantic.BaseModel]) -> list[Any]:
    """The examples ``model`` publishes to ``/docs``, read from its config, not a constant."""
    extra = model.model_config.get("json_schema_extra")
    examples = extra.get("examples") if isinstance(extra, dict) else None
    assert isinstance(examples, list) and examples, (
        f"{model.__name__} publishes no examples"
    )
    return examples


def test_the_year_list_examples_match_the_recorded_served_rows() -> None:
    """Each ``/v1/elections`` example shows what the API served for its year (#351).

    One once showed 2000 with ``candidate_count`` 7, 2016's value, which taught a reader
    of ``/docs`` that the count covers more than the candidates who received electoral
    votes.
    """
    served = _recorded("v1_elections.json")["data"]
    for example in _published_examples(models.YearListItem):
        rows = [r for r in served if r["year"] == example["year"]]
        assert len(rows) == 1, f"no single recorded row for {example['year']}: {rows}"
        assert example == rows[0]


def test_the_meta_examples_match_the_recorded_served_counts() -> None:
    """Each ``/v1/meta`` example's counts are the recorded served ones (#351).

    The same two counts are pinned in two other places, deliberately independently: the
    recorded ``tests/fixtures/dashboard/v1_meta.json`` (read here) and the integration
    oracle's ``CANDIDATE_COUNT`` / ``ROW_COUNT`` in
    ``tests/integration/test_snapshot_build.py``. A change that moves either count fails
    the integration oracle the next time it is run (``pytest -m integration`` with a test
    database (``USVOTE_TEST_DB_*``) and the four local corpora set; CI sets no corpora, so
    it skips it), and this test only once the fixture is re-recorded.
    """
    served = _recorded("v1_meta.json")
    for example in _published_examples(models.SnapshotMetaResponse):
        for key in ("row_count", "candidate_count"):
            assert example[key] == served[key], key
