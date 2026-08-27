"""Unit tests for the MIT year-coverage guard (``usvote.mit.validate``) — #177.

Every branch is exercised over a plain year set: the assert is pure over a
``Collection[int]``, so no CSV, no fixture and no database is involved. What the guard
does *on the shipped path* — that it runs pre-filter, and that ``run_warehouse``
forwards it on — is wired in ``test_mit_pipeline.py`` and ``test_warehouse.py``.

**The load-bearing test here is** :meth:`TestHighWater.
test_contiguity_alone_cannot_reach_a_dropped_newest_year`. The issue's central claim is
that contiguity *provably* cannot catch a dropped top year, and that test does not
merely assert the guard raises — it shows the same year set **passing** the contiguity
half and failing only on the high-water half, which is what makes the two checks
non-redundant rather than belt-and-braces.
"""

from __future__ import annotations

import pytest

from usvote.mit.transform import MITTransformError
from usvote.mit.validate import MITCoverageError, assert_mit_year_coverage
from usvote.pv.source import MIT_PV_YEAR_MAX, MIT_PV_YEAR_MIN

#: The real file's span, as measured from
#: ``1976-2024-president.csv``: 13 contiguous elections.
FULL_SPAN = list(range(1976, 2025, 4))


class TestTheGuardAcceptsRealCoverage:
    def test_the_full_shipped_span_passes(self) -> None:
        assert_mit_year_coverage(FULL_SPAN)

    def test_order_and_duplicates_do_not_matter(self) -> None:
        """The input is a year *set*; a frame's ``unique()`` order is not guaranteed."""
        assert_mit_year_coverage(list(reversed(FULL_SPAN)) + [2024, 1976])

    def test_the_default_expected_max_is_the_shipped_constant(self) -> None:
        """Pins the default to :data:`MIT_PV_YEAR_MAX` rather than a re-typed literal.

        Without this, bumping the constant for a new cycle would leave the guard
        silently checking the old year — the exact staleness the constant exists to
        prevent, reintroduced at its only consumer.
        """
        one_short = [y for y in FULL_SPAN if y != MIT_PV_YEAR_MAX]
        assert_mit_year_coverage(one_short, expected_max=max(one_short))
        with pytest.raises(MITCoverageError):
            assert_mit_year_coverage(one_short)


class TestInteriorHoles:
    def test_a_missing_interior_election_raises_and_names_it(self) -> None:
        holed = [y for y in FULL_SPAN if y != 1996]

        with pytest.raises(MITCoverageError, match=r"contiguous run.*\[1996\]"):
            assert_mit_year_coverage(holed)

    def test_several_holes_are_all_named(self) -> None:
        holed = [y for y in FULL_SPAN if y not in (1996, 2008)]

        with pytest.raises(MITCoverageError, match=r"\[1996, 2008\]"):
            assert_mit_year_coverage(holed)

    def test_a_year_that_is_not_an_election_year_is_reported_from_the_other_side(
        self,
    ) -> None:
        """A stray 1977 is caught by the same set comparison, as a non-election year."""
        with pytest.raises(MITCoverageError, match=r"non-election year\(s\) \[1977\]"):
            assert_mit_year_coverage([*FULL_SPAN, 1977])


class TestHighWater:
    def test_contiguity_alone_cannot_reach_a_dropped_newest_year(self) -> None:
        """The issue's central claim, asserted as a *mechanism* and not an outcome.

        A file truncated after 2020 is still a perfectly contiguous run of elections,
        so the contiguity half has nothing to object to — proved here by passing the
        very same year set with ``expected_max`` moved to its own maximum, which
        exercises contiguity and skips high-water. The default call then fails, and the
        only difference between the two calls is the high-water bound. That is what
        establishes the two checks are non-redundant; asserting merely that the default
        call raises would leave a guard with the contiguity half deleted looking
        identical.
        """
        truncated = [y for y in FULL_SPAN if y <= 2020]

        assert_mit_year_coverage(truncated, expected_max=2020)

        with pytest.raises(MITCoverageError, match=r"newest covered election is 2020"):
            assert_mit_year_coverage(truncated)

    def test_the_message_names_the_elections_whose_popular_vote_would_go_null(
        self,
    ) -> None:
        truncated = [y for y in FULL_SPAN if y <= 2016]

        with pytest.raises(MITCoverageError, match=r"\[2020, 2024\]"):
            assert_mit_year_coverage(truncated)

    def test_a_later_maximum_raises_as_a_stale_constant(self) -> None:
        """The ``>`` side raises too — the asymmetry with the floor guard.

        A scoped build only ever *lowers* the observed maximum, so unlike
        ``min(observed) > MIT_PV_YEAR_MIN`` there is no benign scoped-build reading
        here: above means MIT published a newer cycle and the constant is stale.
        """
        with pytest.raises(MITCoverageError, match=r"constant is stale"):
            assert_mit_year_coverage([*FULL_SPAN, 2028])

    def test_the_stale_constant_message_says_the_guard_itself_goes_weak(self) -> None:
        """Not decoration: it is the reason the ``>`` side is an error at all."""
        with pytest.raises(MITCoverageError, match=r"no longer notice 2028"):
            assert_mit_year_coverage([*FULL_SPAN, 2028])


class TestTheFloorIsSomebodyElsesJob:
    def test_a_build_starting_later_than_the_floor_passes(self) -> None:
        """#177's "leave the bottom alone" — AC-4, and the test that would go red if
        the declined span-equality collapse were ever slipped back in.

        ``assert_mit_year_floor`` deliberately passes ``min(observed) >
        MIT_PV_YEAR_MIN`` as an ordinary scoped build. A guard here asserting ``min ==
        MIT_PV_YEAR_MIN`` would contradict it, leaving two owners of the same bound
        with opposite semantics (D052).
        """
        from_1980 = [y for y in FULL_SPAN if y > MIT_PV_YEAR_MIN]

        assert_mit_year_coverage(from_1980)

    def test_even_a_single_year_at_the_top_passes(self) -> None:
        """The degenerate scoped case: one election, which is trivially contiguous."""
        assert_mit_year_coverage([MIT_PV_YEAR_MAX])


class TestEmptyInput:
    def test_no_years_at_all_raises(self) -> None:
        """The opposite of the floor guard's treatment, and deliberately so.

        "Every year disappeared" is the maximal case of the very failure this guard is
        about, so passing it would make the guard vacuous under its own worst input. A
        floor question, by contrast, is genuinely vacuous on an empty set.
        """
        with pytest.raises(MITCoverageError, match=r"no MIT election years at all"):
            assert_mit_year_coverage([])


class TestParameterisation:
    def test_error_cls_and_caller_are_honoured(self) -> None:
        class Custom(RuntimeError):
            pass

        with pytest.raises(Custom, match=r"my_caller:"):
            assert_mit_year_coverage([], error_cls=Custom, caller="my_caller")

    def test_the_error_is_a_mit_transform_error(self) -> None:
        """So a coverage failure is separable by type, and still catchable as MIT's."""
        assert issubclass(MITCoverageError, MITTransformError)
