"""Unit coverage for the shared test helpers in ``tests/_helpers.py``.

Currently just :func:`~tests._helpers.non_null_flag`, and it earns a test for a specific
reason (#165). The helper's **happy path does** run in CI — it is called from
``test_the_live_views_match_the_pandas_oracle``, which is deliberately not corpus-gated,
and CI runs ``pytest -m integration`` against a Postgres service container. What never runs
in CI is its **rejection branch on the legs that motivated it**: the 2000 ``hybrid_flip``
leg sits in ``test_hybrid_views_over_a_real_full_warehouse``, gated on all four corpus
env vars (D022 — no UCSB bytes are committed), which CI does not set. So without these
cases the *fix's* non-vacuity would rest entirely on one maintainer's local run. This is
the part a reviewer can reproduce with nothing but the repo.

The rule under test is that a nullable boolean read back through pandas arrives in one of
four spellings — Python ``bool``/``None`` from an object column, ``numpy.bool_`` from a
``bool`` column, ``pd.NA`` from the pandas builders, and ``np.nan`` for a null float — and
that no single naive assert is correct across them. The helper's docstring covers all four.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests._helpers import non_null_flag


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="python-None"),
        pytest.param(pd.NA, id="pandas-NA"),
        pytest.param(np.nan, id="numpy-nan"),
    ],
)
def test_every_null_spelling_is_rejected(value: object) -> None:
    """All three nulls raise, and the message names the encoding rather than the value.

    ``None`` is what psycopg2 hands back for a NULL boolean, ``pd.NA`` is what
    :func:`usvote.hybrid._flip` returns, and ``np.nan`` is how a null float materializes;
    a helper that caught only one of them would leave the other two laundering.
    """
    with pytest.raises(AssertionError, match="came back NULL"):
        non_null_flag(value, label="2000 hybrid_flip")


def test_the_failure_message_names_where_the_value_came_from() -> None:
    """The label is in the message — a bare value cannot say which cell it was."""
    with pytest.raises(AssertionError, match="1824 pv_flip under mismatched"):
        non_null_flag(None, label="1824 pv_flip under mismatched")


def test_the_message_names_no_producing_function() -> None:
    """It guards ``ec_determinative`` too, whose NULL never comes from ``_flip``.

    A hardcoded ``usvote.hybrid._flip`` pointer would send a maintainer chasing a red
    ``ec_determinative`` leg to a function that is not on that column's derivation path
    (it comes from ``build_hybrid_summary``'s own ``pd.NA`` branch, and in SQL from a
    filtered ``bool_or``). ``label`` carries the specifics instead.
    """
    with pytest.raises(AssertionError) as excinfo:
        non_null_flag(None, label="1824 ec_determinative under mismatched")
    assert "_flip" not in str(excinfo.value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(True, True, id="python-True"),
        pytest.param(False, False, id="python-False"),
        pytest.param(np.True_, True, id="numpy-True"),
        pytest.param(np.False_, False, id="numpy-False"),
    ],
)
def test_both_dtypes_normalize_to_the_python_singleton(
    value: object, expected: bool
) -> None:
    """The whole point: ``is True`` / ``is False`` holds afterwards, either dtype.

    ``pd.read_sql`` returns ``object`` cells (Python ``bool``) for a boolean column
    carrying a NULL and ``bool`` cells (``numpy.bool_``) for one that is not, and
    ``numpy.False_ is False`` is **False** — so asserting identity on the raw cell fails
    against a *correct* value. Asserting identity on this return value does not.
    """
    got = non_null_flag(value, label="a flag")
    assert got is expected
    assert type(got) is bool


def test_a_false_flag_is_not_confused_with_a_null() -> None:
    """The regression #165 was filed for, stated as one assertion.

    ``bool(None) is False`` — so the pre-#165 spelling passed on a NULL "no winner"
    exactly as it did on a legitimate ``false``. These two lines must now diverge.
    """
    assert non_null_flag(np.False_, label="a false flag") is False
    with pytest.raises(AssertionError):
        non_null_flag(None, label="a null flag")


@pytest.mark.parametrize(
    "value",
    [
        pytest.param([False], id="one-element-list"),
        pytest.param((False,), id="one-element-tuple"),
        pytest.param(np.array([True, False]), id="ndarray"),
        pytest.param(pd.Series([True, None]), id="series"),
        pytest.param([], id="empty-list"),
    ],
)
def test_array_likes_are_rejected_as_non_scalar(value: object) -> None:
    """A Series or array must fail with a diagnosis, not a bare ``ValueError``.

    ``pd.isna`` returns an *array* for an array-like, so ``not pd.isna(value)`` would raise
    ``ValueError: truth value ... is ambiguous`` — and a one-element sequence is worse
    still: it is truthy regardless of content, so ``[False]`` would slip past the null
    check and return ``True``.
    """
    with pytest.raises(AssertionError, match="not a scalar cell"):
        non_null_flag(value, label="2000 hybrid_flip")


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(0, id="int-zero"),
        pytest.param(2, id="int-two"),
        pytest.param("False", id="str-False"),
        pytest.param("", id="empty-str"),
        pytest.param(np.float64(0.0), id="numpy-float"),
    ],
)
def test_non_boolean_scalars_are_rejected(value: object) -> None:
    """``bool()`` would coerce these silently, which is this helper's whole objection.

    ``"False"`` is the sharpest: it is truthy, so a coercing helper would report the
    string ``"False"`` as ``True``.
    """
    with pytest.raises(AssertionError, match="not a boolean cell"):
        non_null_flag(value, label="2000 hybrid_flip")


def test_label_is_required() -> None:
    """Keyword-only and non-defaulted, so mypy catches a call site that forgets it.

    The message is the reason the helper exists; a call that cannot say which cell failed
    produces a diagnosis strictly worse than the one it was written to give.
    """
    with pytest.raises(TypeError):
        non_null_flag(True)  # type: ignore[call-arg]
