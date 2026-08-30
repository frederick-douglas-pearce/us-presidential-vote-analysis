"""Unit coverage for the shared test helpers in ``tests/_helpers.py``.

Covers the two boolean-cell helpers, :func:`~tests._helpers.non_null_flag` and its SQLite
sibling :func:`~tests._helpers.non_null_sqlite_flag`. The first earns a test for a specific
reason (#165). The helper's **happy path does** run in CI — it is called from
``test_the_live_views_match_the_pandas_oracle``, which is deliberately not corpus-gated,
and CI runs ``pytest -m integration`` against a Postgres service container. What never runs
in CI is its **rejection branch on the legs that motivated it**: the 2000 ``hybrid_flip``
leg sits in ``test_hybrid_views_over_a_real_full_warehouse``, gated on all four of its env
vars — the three local corpora plus the TIGER shapefile (D022 — no UCSB bytes are
committed) — none of which CI sets. So without these cases the *fix's* non-vacuity would
rest entirely on one maintainer's local run. This is the part a reviewer can reproduce
with nothing but the repo.

The rule under test is that a nullable boolean read back through pandas arrives in one of
four spellings — Python ``bool``/``None`` from an object column, ``numpy.bool_`` from a
``bool`` column, ``pd.NA`` from the pandas builders, and ``np.nan`` for a null float — and
that no single naive assert is correct across them. The helper's docstring covers all four.

The **SQLite** helper (#172) exists because that tier has a fifth spelling the four above do
not include: the snapshot stores every boolean as ``INTEGER`` and ``sqlite3`` is opened
without ``detect_types``, so a read hands back a Python ``int``. ``non_null_flag`` rejects an
``int`` on purpose, so the tier needed its own helper rather than a widened one — and the
cases below pin *both* halves of that split, since a sibling that quietly accepted pandas
cells too would put the "which one do I call?" trap straight back.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import pytest

from tests._helpers import non_null_flag, non_null_sqlite_flag


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


#: One value per rejection branch of :func:`~tests._helpers.non_null_flag`, so the two
#: properties below are pinned on **every** message rather than only the NULL one. Without
#: this, re-adding a ``_flip`` pointer to -- or dropping ``label`` from -- either of the
#: other two messages would fail nothing.
REJECTED_BY_EVERY_BRANCH = [
    pytest.param(None, id="null-branch"),
    pytest.param(pd.Series([True, None]), id="non-scalar-branch"),
    pytest.param("False", id="non-boolean-branch"),
]


@pytest.mark.parametrize("value", REJECTED_BY_EVERY_BRANCH)
def test_no_message_names_a_producing_function(value: object) -> None:
    """It guards ``ec_determinative`` too, whose NULL never comes from ``_flip``.

    A hardcoded ``usvote.hybrid._flip`` pointer would send a maintainer chasing a red
    ``ec_determinative`` leg to a function that is not on that column's derivation path
    (it comes from ``build_hybrid_summary``'s own ``pd.NA`` branch, and in SQL from a
    filtered ``bool_or``). ``label`` carries the specifics instead.
    """
    with pytest.raises(AssertionError) as excinfo:
        non_null_flag(value, label="1824 ec_determinative under mismatched")
    assert "_flip" not in str(excinfo.value)


@pytest.mark.parametrize("value", REJECTED_BY_EVERY_BRANCH)
def test_every_message_interpolates_the_label(value: object) -> None:
    """The label is the whole diagnostic value, so no branch may omit it."""
    with pytest.raises(AssertionError, match="2000 hybrid_flip"):
        non_null_flag(value, label="2000 hybrid_flip")


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
    with pytest.raises(TypeError, match="label"):
        non_null_flag(True)  # type: ignore[call-arg]


# --- non_null_sqlite_flag (#172) -------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(1, True, id="int-one"),
        pytest.param(0, False, id="int-zero"),
    ],
)
def test_a_sqlite_flag_returns_the_python_singleton(
    value: object, expected: bool
) -> None:
    """Identity, not just truthiness — the invariant every converted call site rests on.

    ``1 is True`` is **False**, so a helper that returned what SQLite handed it would turn
    every ``non_null_sqlite_flag(...) is True`` site red against a *correct* value. That is
    the one way this refactor could have changed a verdict rather than a message, so it is
    pinned here rather than left to the call sites to discover.
    """
    got = non_null_sqlite_flag(value, label="2016 pv_flip")
    assert got is expected
    assert type(got) is bool


def test_a_sqlite_null_is_rejected_where_bool_would_launder_it() -> None:
    """The live regression #172 found, reproduced through a real SQLite roundtrip.

    ``tests/integration/test_snapshot_build.py`` asserted ``bool(hybrid_flip) is False``
    over a snapshot read with no null guard, and ``bool(None) is False`` is **True** — so a
    NULL passed. Only the False leg was ever silent: ``bool(None) is True`` fails. The
    roundtrip is real rather than mocked because the premise under test is what ``sqlite3``
    actually returns for a nullable ``INTEGER``, which is not a fact about our code.
    """
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE t (flag INTEGER)")
        conn.executemany("INSERT INTO t VALUES (?)", [(1,), (0,), (None,)])
        one, zero, null = (r[0] for r in conn.execute("SELECT flag FROM t"))
    finally:
        conn.close()

    assert (one, zero, null) == (1, 0, None)
    assert bool(null) is False  # the laundering, stated so the fix is not vacuous
    assert non_null_sqlite_flag(one, label="a flag") is True
    assert non_null_sqlite_flag(zero, label="a flag") is False
    with pytest.raises(AssertionError, match="came back NULL"):
        non_null_sqlite_flag(null, label="2000 hybrid_flip")


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(2, id="int-two"),
        pytest.param(-1, id="int-negative"),
    ],
)
def test_a_sqlite_int_outside_zero_one_is_rejected(value: object) -> None:
    """An INTEGER column holding a boolean holds 0 or 1; anything else is a wrong column.

    Without this the helper would report ``2`` as ``True``, which is the same silent
    coercion :func:`non_null_flag` refuses for pandas cells.
    """
    with pytest.raises(AssertionError, match="not a 0/1 flag"):
        non_null_sqlite_flag(value, label="2000 hybrid_flip")


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(1.0, id="float-one"),
        pytest.param("1", id="str-one"),
        pytest.param(np.float64(1.0), id="numpy-float"),
    ],
)
def test_non_sqlite_scalars_are_rejected(value: object) -> None:
    with pytest.raises(AssertionError, match="not a SQLite boolean cell"):
        non_null_sqlite_flag(value, label="2000 hybrid_flip")


@pytest.mark.parametrize(
    ("value", "helper", "match"),
    [
        pytest.param(
            np.True_, non_null_sqlite_flag, "not a SQLite boolean cell", id="pandas-cell"
        ),
        pytest.param(
            pd.DataFrame({"pv_flip": [True, None]}).iloc[0]["pv_flip"],
            non_null_sqlite_flag,
            "not a SQLite boolean cell",
            id="pandas-nullable-cell",
        ),
        pytest.param(1, non_null_flag, "not a boolean cell", id="sqlite-cell"),
    ],
)
def test_the_two_helpers_are_not_interchangeable(
    value: object, helper: object, match: str
) -> None:
    """Each rejects the other tier's dtype, which is what makes the split enforceable.

    This is the property that keeps two helpers from becoming a "which one do I call?"
    trap: a wrong pick fails loudly at authoring time instead of quietly working.

    **The ``pandas-nullable-cell`` case is the one that was actually broken**, and it is why
    the SQLite helper checks ``type(value) is int`` rather than ``isinstance``. ``bool`` is
    an ``int`` subclass, so an ``isinstance`` check accepted a Python ``bool`` — which is
    exactly what ``pd.read_sql`` yields for a boolean column carrying a NULL. The pandas
    spelling this split most needs to refuse was the one sailing through, while the
    ``numpy.bool_`` case tested here passed for a reason that had nothing to do with the
    intent. The asserts below pin the discrimination the fix depends on.

    A ``numpy.bool_`` is the sharpest case in the other direction: its bare
    ``__name__`` is ``"bool"``, so the rejection message qualifies the type with its module
    or it would read as though a plain ``bool`` had been refused.
    """
    # Read through an ``object`` local: mypy narrows a literal ``True`` to a type it can
    # reason about exactly, and would call the second check unreachable — making the
    # assertion vanish at exactly the point it is load-bearing.
    py_true: object = True
    assert isinstance(py_true, int), "bool subclasses int — why isinstance was too loose"
    assert type(py_true) is not int, "...and why `type(...) is int` is the right check"
    with pytest.raises(AssertionError, match=match):
        helper(value, label="2000 hybrid_flip")  # type: ignore[operator]


def test_a_rejected_numpy_bool_names_its_module() -> None:
    """``numpy.bool``'s bare ``__name__`` is ``"bool"``, so the message qualifies it.

    **The match is anchored on the interpolated segment**, pairing the value with its
    parenthesised type. Matching ``numpy.bool`` anywhere in the message would be weaker: it
    would also be satisfied by any prose elsewhere in the string that happened to name the
    type, so the assertion would stop distinguishing a qualified interpolation from an
    unqualified one — which is the only thing it is here to check. (An earlier revision of
    the message did carry such prose, and the bare match still succeeded against it with the
    qualification removed — verified, which is why the anchor is here.)
    """
    with pytest.raises(AssertionError, match=r"cell: np\.True_ \(numpy\.bool"):
        non_null_sqlite_flag(np.True_, label="2000 hybrid_flip")


def test_sqlite_label_is_required() -> None:
    with pytest.raises(TypeError, match="label"):
        non_null_sqlite_flag(1)  # type: ignore[call-arg]
