"""Redistributable-only regression guard (E8-S5, #99, D030).

Belt-and-suspenders over the #95 source guarantee and the #97 endpoint layer: the API must
serve **only** MIT/CC0 (redistributable) data, and it must be impossible for a
``redistributable=false`` / non-MIT row to reach either the built snapshot or a served
response.

Two layers:
1. **Build-time** — :func:`usvote.snapshot.build_snapshot` (via ``assert_redistributable_only``)
   fails loud on a ``redistributable=false`` row and on a non-MIT ``source``, rather than
   trusting the upstream ``ec_pv_redistributable`` view.
2. **Serve-time** — no ``/v1`` endpoint that carries a per-row ``source`` ever surfaces a
   row whose source is anything but MIT (or NULL, an honest D005 no-PV gap).

All offline (D028): synthetic frame → real SQLite snapshot, no live Postgres.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.api_snapshot import (
    SNAPSHOT_TS,
    synthetic_ec_pv_frame,
    synthetic_pv_status_frame,
)
from usvote.pv.status import PV_STATUS_VALUES
from usvote.snapshot import SnapshotError, build_snapshot
from usvote.transform import COUNT_STATUS_OVERRIDES

# --- build-time guard -------------------------------------------------------


def test_build_refuses_a_non_redistributable_row(tmp_path: Path) -> None:
    """A single ``redistributable=false`` row must fail the build loud, not slip through."""
    frame = synthetic_ec_pv_frame()
    frame.loc[0, "redistributable"] = False
    with pytest.raises(SnapshotError, match="redistributable"):
        build_snapshot(
            frame,
            str(tmp_path / "snap.sqlite"),
            pv_status_df=synthetic_pv_status_frame(),
            build_timestamp=SNAPSHOT_TS,
        )


def test_build_refuses_a_non_mit_source_row(tmp_path: Path) -> None:
    """A non-MIT ``source`` (e.g. a UCSB row) must fail the build loud (D016/D030)."""
    frame = synthetic_ec_pv_frame()
    frame.loc[0, "source"] = "UCSB"
    with pytest.raises(SnapshotError, match="non-MIT"):
        build_snapshot(
            frame,
            str(tmp_path / "snap.sqlite"),
            pv_status_df=synthetic_pv_status_frame(),
            build_timestamp=SNAPSHOT_TS,
        )


# --- serve-time guard -------------------------------------------------------

#: Every row-carrying path in the fixture snapshot, so each serve-time guard below is a
#: full sweep rather than a spot-check. 1860 is here because the pre-1976 rows are the
#: ones carrying the columns #139 added.
_ALL_ROW_PATHS = (
    [f"/v1/elections/{y}" for y in (1860, 2016, 2020)]
    + [f"/v1/states/{s}" for s in ("TX", "CA", "VT", "NV")]
    + [f"/v1/candidates/{slug}" for slug in ("cand-a", "cand-b", "cand-c", "cand-d")]
)


def test_no_endpoint_surfaces_a_non_mit_row(client: TestClient) -> None:
    """Across every row-carrying endpoint, no served row has a non-MIT ``source``.

    Strengthens the original three-path spot-check into a full sweep over each covered
    year / state / candidate in the fixture.
    """
    for path in _ALL_ROW_PATHS:
        body = client.get(path).json()
        for row in body["data"]:
            # ``row["source"]`` (not ``.get``) so a dropped/renamed field fails loud
            # rather than silently matching the allowed ``None``.
            assert row["source"] in (None, "MIT"), f"{path}: {row}"


def test_no_endpoint_surfaces_a_pv_status_outside_the_enum(client: TestClient) -> None:
    """Every served ``pv_status`` is one of the three D024 values (#139 / D048).

    This is the structural form of "the enum ships, the expression does not". The
    pre-1976 classifications are historical facts we curated in-repo with public-domain
    citations, and a value drawn from a closed three-element set cannot carry anyone
    else's *expression* — which is what makes shipping them a property rather than an
    argument.
    """
    for path in _ALL_ROW_PATHS:
        for row in client.get(path).json()["data"]:
            assert row["pv_status"] in PV_STATUS_VALUES, f"{path}: {row}"


def test_no_endpoint_surfaces_roster_free_text(client: TestClient) -> None:
    """The roster's free-text ``note`` reaches no endpoint (D022).

    ``pv_state_status.note`` holds verbatim UCSB prose. The public roster is derived
    from the in-repo catalog and its ``note`` is null by construction, so this cannot
    fail today — which is exactly when a licensing guard is worth writing, since the way
    it *would* fail is a future change repointing the build at the warehouse roster.
    """
    for path in _ALL_ROW_PATHS:
        for row in client.get(path).json()["data"]:
            assert "note" not in row, f"{path}: {row}"


def test_no_endpoint_surfaces_an_uncatalogued_count_reason(client: TestClient) -> None:
    """Served ``count_status_reason`` values come from the curated Archives vocabulary.

    The one free-text column the public surface carries, admissible only because it is
    a U.S. Government work (D044 §3) drawn from a closed set. Without pinning it to that
    set, the provenance claim would be a docstring rather than a property.
    """
    allowed = {reason for _, reason in COUNT_STATUS_OVERRIDES.values()}
    for path in _ALL_ROW_PATHS:
        for row in client.get(path).json()["data"]:
            reason = row["electoral_count_status_reason"]
            assert reason is None or reason in allowed, f"{path}: {reason!r}"


#: The paths whose response carries the per-election ``election`` object (#102).
_ELECTION_OBJECT_PATHS = (
    [f"/v1/elections/{y}" for y in (1860, 2016, 2020)]
    + [f"/v1/elections/{y}/summary" for y in (1860, 2016, 2020)]
)

#: Every field the ``election`` object is allowed to carry. A **whitelist**, because the
#: sweeps above iterate ``body["data"]`` and so cannot see this object at all — #102 added
#: a public surface outside their reach, and the way this guard would fail is a future
#: column landing on ``hybrid_summary`` and reaching the API without anyone asking whose
#: text it is.
_ALLOWED_ELECTION_FIELDS = frozenset(
    {
        "year",
        "electoral_denominator",
        "ec_winner",
        "ec_winner_slug",
        "pv_winner",
        "pv_winner_slug",
        "hybrid_winner",
        "hybrid_winner_slug",
        "ec_determinative",
        "pv_coverage",
        "pv_flip",
        "hybrid_flip",
        "ec_margin",
        "pv_margin",
        "hybrid_margin",
    }
)


def test_the_election_object_carries_no_unexpected_field(client: TestClient) -> None:
    """The per-election object ships exactly the fields we vetted, and no others (#102).

    The three sweeps above iterate ``body["data"]``, so the ``election`` key #102 added is
    **outside every one of them**. Found during this issue's security review, which
    cleared it as a non-exposure — the object carries no ``source``, ``pv_status`` or
    ``note`` — while noting the surface was unswept. A whitelist rather than a
    blocklist: it fails on anything new, including the field nobody thought to forbid.

    The only free text here is the three winner **names**, which come from
    ``dwh.candidate`` (the NARA spine, US-PD) via the same column the fact rows already
    expose as ``candidate`` — not from a popular-vote source.
    """
    for path in _ELECTION_OBJECT_PATHS:
        election = client.get(path).json()["election"]
        assert election is not None, f"{path}: no election object"
        unexpected = set(election) - _ALLOWED_ELECTION_FIELDS
        assert not unexpected, f"{path}: unvetted field(s) on the public surface: {unexpected}"
