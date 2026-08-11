"""The shared synthetic snapshot fixture for the API tests (E8-S5, #99).

The whole API test surface (``test_api_app`` #96, ``test_api_endpoints`` #97,
``test_api_openapi`` #98, the E2E walk and the redistributable guard #99) is served
from **one** synthetic ``ec_pv_redistributable``-shaped frame defined here, so a
snapshot-schema change updates a single fixture rather than the several near-identical
``_row``/``_frame`` copies these tests used to carry.

**Built, never committed.** There is no checked-in ``.sqlite`` binary — the pytest
fixtures in ``tests/unit/conftest.py`` materialize this frame through the real
:func:`usvote.snapshot.build_snapshot` writer at test time, so the fixture can never
drift from the actual snapshot schema (the issue's anti-drift note).

**Synthetic, and safe to commit.** Values are fabricated (mirroring the D022
synthetic-fixture posture), but unlike the UCSB corpus this data is EC/MIT/CC0-shaped
and carries **no** licensing restriction — every row is ``source="MIT"``,
``redistributable=True``. No real UCSB bytes are involved.

The frame deliberately encodes a real **"EC winner ≠ PV winner"** flip year in the
1976–2024 redistributable window (2016): the candidate who *took office* leads the
Electoral College but **trails** the national popular vote — so the national-summary /
flip assertions the API exposes are meaningful. 2020 is an ordinary split year (its
rows are kept byte-for-byte compatible with #97's original endpoint assertions).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from usvote.count_status import (
    COUNT_STATUS_COLUMN,
    COUNT_STATUS_COUNTED,
    COUNT_STATUS_NOT_COUNTED,
    COUNT_STATUS_REASON_COLUMN,
    COUNTED_VOTES_COLUMN,
)
from usvote.pv.status import (
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
)
from usvote.transform import COUNT_STATUS_OVERRIDES

#: A real Archives sentence, borrowed from the curated vocabulary rather than invented.
#: ``usvote.snapshot`` pins every served ``count_status_reason`` to that vocabulary
#: (only U.S. Government prose may ship, D044 §3), so a fabricated sentence here would
#: fail the build — correctly. The rest of the fixture is synthetic; this one string
#: cannot be.
FIXTURE_NOT_COUNTED_REASON = COUNT_STATUS_OVERRIDES[
    (1872, "Georgia", "Horace Greeley")
][1]

#: Deterministic build timestamp so a snapshot's content hash (and thus the ETag) is
#: stable across test runs. Informational only — excluded from the content hash (D028).
SNAPSHOT_TS = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)

#: State full-name → USPS code, for the states this fixture builds rows for. The last
#: two arrived with #139's pre-1976 rows: Vermont stands in for a legislature-chosen
#: state and Nevada for a non-participating one.
_USPS = {
    "Texas": "TX",
    "California": "CA",
    "Vermont": "VT",
    "Nevada": "NV",
}


def api_snapshot_row(
    *,
    year: int,
    state: str,
    candidate_id: int,
    candidate: str,
    president_ev: int,
    national_ev: int,
    rank: int,
    took_office: bool,
    candidate_votes: int | None,
    state_total: int | None,
    total_ev: int,
    source: str | None = "MIT",
    party: str | None = None,
    reliability: str | None = "exact",
    # Nullable: a row with no popular vote has no `pv_source` row to join, so the live
    # view yields NULL here — not False. `assert_redistributable_only` matches only an
    # explicit False, which is what lets the pre-1976 rows through (D030).
    redistributable: bool | None = True,
    counted_ev: int | None = None,
    national_counted_ev: int | None = None,
    count_status: str = COUNT_STATUS_COUNTED,
    count_status_reason: str | None = None,
) -> dict[str, object]:
    """One ``build_snapshot`` input row (``join.EC_PV_COLUMNS`` + ``state_usps``).

    Keyword-only so a caller reads at a glance and can't transpose the many ints. The
    ``source`` / ``redistributable`` overrides exist so the redistributable-only guard
    test (#99) can craft a deliberately non-redistributable row and assert the build
    fails loud; the happy-path fixtures never override them.

    The four #144/#139 count parameters **default to the counted case** — counted ==
    cast, no reason — so every row written before they existed is byte-identical and
    only the rows that deliberately exercise a rejected vote differ. That is the point:
    a fixture change that quietly perturbed the existing rows would move the content
    hash and invalidate the ETag assertions built on it.
    """
    if party is None:
        party = "DEMOCRAT" if candidate == "Cand B" else "REPUBLICAN"
    return {
        "year": year,
        "state": state,
        "state_usps": _USPS[state],
        "candidate_id": candidate_id,
        "candidate": candidate,
        "total_electoral_votes": total_ev,
        "president_electoral_votes": president_ev,
        "national_electoral_votes": national_ev,
        "president_electoral_rank": rank,
        "took_office": took_office,
        "source": source,
        "party": party,
        "candidate_votes": candidate_votes,
        "state_total_votes": state_total,
        "reliability": reliability,
        "redistributable": redistributable,
        COUNTED_VOTES_COLUMN: president_ev if counted_ev is None else counted_ev,
        "national_counted_electoral_votes": (
            national_ev if national_counted_ev is None else national_counted_ev
        ),
        COUNT_STATUS_COLUMN: count_status,
        COUNT_STATUS_REASON_COLUMN: count_status_reason,
    }


def api_snapshot_status_row(
    *, year: int, state: str, pv_status: str = PV_STATUS_POPULAR_VOTE
) -> dict[str, object]:
    """One ``read_pv_status_roster``-shaped row (``year``, ``state``, ``pv_status``).

    The roster is **injected** rather than derived in the build (see
    :func:`usvote.snapshot.build_snapshot`): the real derivation cross-checks the
    in-repo absence catalog against the EC spine, and a two-state synthetic spine would
    make every genuine 1860s catalog entry look like a phantom key. So the fixture
    supplies statuses directly, and the catalog's own correctness is tested against the
    real spine elsewhere.
    """
    return {"year": year, "state": state, "pv_status": pv_status}


def synthetic_ec_pv_frame() -> pd.DataFrame:
    """The canonical synthetic ``ec_pv_redistributable`` input frame.

    Two candidates (``Cand A`` / ``Cand B``) × two states (Texas / California) across
    two years:

    - **2016 — the flip.** ``Cand B`` takes office with the larger national EC total
      (55 vs 38) but the *smaller* national popular vote (13,000,000 vs 18,000,000):
      an "EC winner ≠ PV winner" year, so ``/v1/elections/2016/summary`` can be asserted
      to expose the flip. (``national_electoral_votes`` equals the sum of the candidate's
      per-state ``president_electoral_votes``, matching the real view's window sum.)
    - **2020 — ordinary split.** ``Cand A`` wins Texas, ``Cand B`` wins California and
      takes office (national EC 55 vs 38). These rows match #97's original fixture so its
      value-specific rollup assertions carry over unchanged.
    - **1860 — the pre-1976 shape (#139).** Four states across two candidates, with no
      popular vote anywhere: the years the surface widened to. It exercises all three
      ``pv_status`` values (Texas/California ``popular_vote``, Vermont
      ``legislature_chosen``, Nevada ``not_participating``) — which is what makes "a
      state that never held a popular vote is distinguishable from one this source
      merely does not reach" a testable claim rather than a design note — and one
      ``not_counted`` row where cast (8) and counted (5) diverge.

    Pair it with :func:`synthetic_pv_status_frame`, which ``build_snapshot`` requires.
    """
    return pd.DataFrame(
        [
            # 2016 — national flip: B took office (EC 55) but A won the PV (18M vs 13M).
            # national_ev == sum of the candidate's per-state president_ev (A: 38+0=38,
            # B: 0+55=55), so the fixture matches the real view's window sum.
            api_snapshot_row(
                year=2016, state="Texas", candidate_id=1, candidate="Cand A",
                president_ev=38, national_ev=38, rank=2, took_office=False,
                candidate_votes=8_000_000, state_total=14_000_000, total_ev=38,
            ),
            api_snapshot_row(
                year=2016, state="California", candidate_id=1, candidate="Cand A",
                president_ev=0, national_ev=38, rank=2, took_office=False,
                candidate_votes=10_000_000, state_total=17_000_000, total_ev=55,
            ),
            api_snapshot_row(
                year=2016, state="Texas", candidate_id=2, candidate="Cand B",
                president_ev=0, national_ev=55, rank=1, took_office=True,
                candidate_votes=6_000_000, state_total=14_000_000, total_ev=38,
            ),
            api_snapshot_row(
                year=2016, state="California", candidate_id=2, candidate="Cand B",
                president_ev=55, national_ev=55, rank=1, took_office=True,
                candidate_votes=7_000_000, state_total=17_000_000, total_ev=55,
            ),
            # 2020 — split: A wins TX (38), B wins CA (55, rank 1, took office).
            api_snapshot_row(
                year=2020, state="Texas", candidate_id=1, candidate="Cand A",
                president_ev=38, national_ev=38, rank=2, took_office=False,
                candidate_votes=5_000_000, state_total=11_000_000, total_ev=38,
            ),
            api_snapshot_row(
                year=2020, state="Texas", candidate_id=2, candidate="Cand B",
                president_ev=0, national_ev=55, rank=1, took_office=True,
                candidate_votes=6_000_000, state_total=11_000_000, total_ev=38,
            ),
            api_snapshot_row(
                year=2020, state="California", candidate_id=1, candidate="Cand A",
                president_ev=0, national_ev=38, rank=2, took_office=False,
                candidate_votes=6_000_000, state_total=17_000_000, total_ev=55,
            ),
            api_snapshot_row(
                year=2020, state="California", candidate_id=2, candidate="Cand B",
                president_ev=55, national_ev=55, rank=1, took_office=True,
                candidate_votes=11_000_000, state_total=17_000_000, total_ev=55,
            ),
            # 1860 — the pre-1976 year (#139). No popular vote anywhere on this
            # surface, so every PV column is NULL and `pv_status` carries the reason.
            # Four states, each a different shape:
            #   Texas       — an ordinary popular-vote state, PV simply out of window
            #   California  — same, and where Cand D's votes are CAST but NOT COUNTED
            #   Vermont     — legislature_chosen: no popular vote was ever held
            #   Nevada      — not_participating: took no part, hence 0 electoral votes
            # Cand C cast 10 and counted 10; Cand D cast 8 but only 5 counted, so the
            # counted basis is what makes C rank 1 — the D046 property the API must be
            # able to show, on a row where cast alone would still say C wins but by a
            # different margin.
            api_snapshot_row(
                year=1860, state="Texas", candidate_id=3, candidate="Cand C",
                president_ev=6, national_ev=10, rank=1, took_office=True,
                candidate_votes=None, state_total=None, total_ev=6,
                source=None, party=None, reliability=None, redistributable=None,
            ),
            api_snapshot_row(
                year=1860, state="Texas", candidate_id=4, candidate="Cand D",
                president_ev=0, national_ev=8, rank=2, took_office=False,
                candidate_votes=None, state_total=None, total_ev=6,
                source=None, party=None, reliability=None, redistributable=None,
                national_counted_ev=5,
            ),
            api_snapshot_row(
                year=1860, state="California", candidate_id=3, candidate="Cand C",
                president_ev=0, national_ev=10, rank=1, took_office=True,
                candidate_votes=None, state_total=None, total_ev=8,
                source=None, party=None, reliability=None, redistributable=None,
            ),
            api_snapshot_row(
                year=1860, state="California", candidate_id=4, candidate="Cand D",
                president_ev=8, national_ev=8, rank=2, took_office=False,
                candidate_votes=None, state_total=None, total_ev=8,
                source=None, party=None, reliability=None, redistributable=None,
                counted_ev=5, national_counted_ev=5,
                count_status=COUNT_STATUS_NOT_COUNTED,
                count_status_reason=FIXTURE_NOT_COUNTED_REASON,
            ),
            api_snapshot_row(
                year=1860, state="Vermont", candidate_id=3, candidate="Cand C",
                president_ev=4, national_ev=10, rank=1, took_office=True,
                candidate_votes=None, state_total=None, total_ev=4,
                source=None, party=None, reliability=None, redistributable=None,
            ),
            api_snapshot_row(
                year=1860, state="Vermont", candidate_id=4, candidate="Cand D",
                president_ev=0, national_ev=8, rank=2, took_office=False,
                candidate_votes=None, state_total=None, total_ev=4,
                source=None, party=None, reliability=None, redistributable=None,
                national_counted_ev=5,
            ),
            api_snapshot_row(
                year=1860, state="Nevada", candidate_id=3, candidate="Cand C",
                president_ev=0, national_ev=10, rank=1, took_office=True,
                candidate_votes=None, state_total=None, total_ev=0,
                source=None, party=None, reliability=None, redistributable=None,
            ),
            api_snapshot_row(
                year=1860, state="Nevada", candidate_id=4, candidate="Cand D",
                president_ev=0, national_ev=8, rank=2, took_office=False,
                candidate_votes=None, state_total=None, total_ev=0,
                source=None, party=None, reliability=None, redistributable=None,
                national_counted_ev=5,
            ),
        ]
    )


def synthetic_pv_status_frame() -> pd.DataFrame:
    """The roster companion to :func:`synthetic_ec_pv_frame`, one row per (year, state).

    Modern years are all ``popular_vote`` — the real catalog records no absence at or
    after MIT's window, and ``usvote.snapshot.assert_modern_years_are_popular_vote``
    enforces exactly that, so any other value here would (rightly) fail the build. The
    1860 rows are where the three statuses are actually distinguishable, which is the
    whole reason the fixture grew a pre-1976 year.
    """
    modern = [
        api_snapshot_status_row(year=year, state=state)
        for year in (2016, 2020)
        for state in ("Texas", "California")
    ]
    historical = [
        api_snapshot_status_row(year=1860, state="Texas"),
        api_snapshot_status_row(year=1860, state="California"),
        api_snapshot_status_row(
            year=1860, state="Vermont", pv_status=PV_STATUS_LEGISLATURE_CHOSEN
        ),
        api_snapshot_status_row(
            year=1860, state="Nevada", pv_status=PV_STATUS_NOT_PARTICIPATING
        ),
    ]
    return pd.DataFrame(modern + historical)
