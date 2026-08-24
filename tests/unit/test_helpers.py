"""Unit coverage for the shared test helpers in ``tests/_helpers.py``.

Currently just :func:`~tests._helpers.non_null_flag`, and it earns a test for a specific
reason (#165): the integration leg that helper was written for is gated on all three local
corpora, so it **never runs in CI** (D022 — no UCSB bytes are committed). Without something
offline pinning the rule, the fix's non-vacuity would rest entirely on one maintainer's
local run. These cases are the part a reviewer can reproduce with nothing but the repo.

The rule under test is that a nullable boolean read back through pandas arrives in one of
*four* spellings, and no single naive assert is correct across them — see the helper's own
docstring for which, and why.
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
    with pytest.raises(AssertionError, match="no winner"):
        non_null_flag(value, label="2000 hybrid_flip")


def test_the_failure_message_names_where_the_value_came_from() -> None:
    """The label is in the message — a bare value cannot say which cell it was."""
    with pytest.raises(AssertionError, match="1824 pv_flip under mismatched"):
        non_null_flag(None, label="1824 pv_flip under mismatched")


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
    got = non_null_flag(value)
    assert got is expected
    assert type(got) is bool


def test_a_false_flag_is_not_confused_with_a_null() -> None:
    """The regression #165 was filed for, stated as one assertion.

    ``bool(None) is False`` — so the pre-#165 spelling passed on a NULL "no winner"
    exactly as it did on a legitimate ``false``. These two lines must now diverge.
    """
    assert non_null_flag(np.False_) is False
    with pytest.raises(AssertionError):
        non_null_flag(None)
