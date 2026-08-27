"""End-to-end API integration test over the shared synthetic snapshot (E8-S5, #99).

Drives the *running* app with FastAPI's ``TestClient`` across every ``/v1`` surface in one
walk — ``/health`` → ``/v1/meta`` → ``/v1/elections`` → ``/v1/elections/{year}`` (+ sibling
``summary``) → ``/v1/states/{usps}`` → ``/v1/candidates/{slug}`` — asserting the real
``{data, meta}`` envelope, the content-hash **ETag** + conditional-304, human provenance,
and that the fixture's 2016 **EC-winner-≠-PV-winner flip** is observable through the
national summary.

It runs in CI: the snapshot is built from an in-memory synthetic frame via
:func:`usvote.snapshot.build_snapshot`, so there is **no live Postgres** (D028). The
``client`` fixture is the shared one in ``tests/unit/conftest.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _assert_envelope(body: dict) -> None:
    """Every ``{data, meta}`` response: ``meta.count == len(data)`` and MIT/CC0 provenance."""
    assert "data" in body and "meta" in body
    assert isinstance(body["data"], list)
    assert body["meta"]["count"] == len(body["data"])
    prov = body["meta"]["provenance"]
    assert prov["source"] == "MIT"
    assert prov["license"] == "CC0-1.0"
    assert prov["snapshot_version"]


def test_health_then_meta_then_data_walk(client: TestClient) -> None:
    # 1. /health — no envelope, but the loaded snapshot's coverage + source.
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["snapshot_loaded"] is True
    assert health["coverage"] == {
        "year_min": 1860,
        "year_max": 2020,
        "pv_year_min": 2016,
        "pv_year_max": 2020,
    }
    assert health["source"] == "MIT"

    # 2. /v1/meta — provenance + the content-hash ETag.
    meta_resp = client.get("/v1/meta")
    assert meta_resp.status_code == 200
    version = meta_resp.json()["provenance"]["snapshot_version"]
    assert meta_resp.headers["etag"] == f'"{version}"'

    # 3. /v1/elections — the covered years, envelope intact.
    elections = client.get("/v1/elections").json()
    _assert_envelope(elections)
    assert [item["year"] for item in elections["data"]] == [1860, 2016, 2020]
    # The widened surface: 1860 is served, and says so about its popular vote.
    assert [item["has_popular_vote"] for item in elections["data"]] == [
        False,
        True,
        True,
    ]

    # 4. /v1/elections/{year} — per-state rows (public field names) + sibling summary.
    year_body = client.get("/v1/elections/2020").json()
    _assert_envelope(year_body)
    assert len(year_body["data"]) == 4  # 2 states x 2 candidates; summary not counted
    assert len(year_body["summary"]) == 2
    row = year_body["data"][0]
    assert "electoral_votes" in row and "popular_votes" in row
    assert "candidate_id" not in row  # D006: internal id never surfaced

    # 5. /v1/states/{usps} and /v1/candidates/{slug} — cross-year slices.
    tx = client.get("/v1/states/TX").json()
    _assert_envelope(tx)
    assert {r["state_usps"] for r in tx["data"]} == {"TX"}
    assert {r["year"] for r in tx["data"]} == {1860, 2016, 2020}

    # 5b. The pre-popular-vote era is reachable, and its nulls are explained rather
    # than bare — the whole point of widening the window (#139).
    historical = client.get("/v1/elections/1860").json()
    _assert_envelope(historical)
    by_state = {r["state"]: r for r in historical["data"]}
    assert by_state["Vermont"]["popular_votes"] is None
    assert by_state["Vermont"]["pv_status"] == "legislature_chosen"
    assert by_state["Nevada"]["pv_status"] == "not_participating"
    assert by_state["Texas"]["pv_status"] == "popular_vote"  # held, just not covered
    assert historical["summary"][0]["national_electoral_denominator"] == 18

    cand = client.get("/v1/candidates/cand-a").json()
    _assert_envelope(cand)
    assert {r["candidate_slug"] for r in cand["data"]} == {"cand-a"}


def test_conditional_get_304_end_to_end(client: TestClient) -> None:
    """A repeat GET with the served ETag short-circuits to a bodyless 304."""
    first = client.get("/v1/elections/2016")
    etag = first.headers["etag"]
    again = client.get("/v1/elections/2016", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""


def test_2016_flip_is_observable_through_summary(client: TestClient) -> None:
    """The fixture's 2016 flip: the took-office candidate leads the EC but trails the PV.

    This is the "EC winner ≠ PV winner" case the API exists to expose (2000/2016-shaped),
    asserted end-to-end through the precomputed national roll-up.
    """
    summary = client.get("/v1/elections/2016/summary").json()
    _assert_envelope(summary)
    by_slug = {r["candidate_slug"]: r for r in summary["data"]}
    took_office = by_slug["cand-b"]
    rival = by_slug["cand-a"]

    assert took_office["took_office"] is True
    assert rival["took_office"] is False
    # Won the Electoral College...
    assert took_office["national_electoral_votes"] > rival["national_electoral_votes"]
    # ...but lost the popular vote — the flip.
    assert took_office["national_pv_votes"] < rival["national_pv_votes"]
    assert took_office["national_pv_votes"] == 13_000_000
    assert rival["national_pv_votes"] == 18_000_000


def test_2016_flip_is_stated_outright_by_the_election_summary(
    client: TestClient,
) -> None:
    """#102: the flip the sibling test *infers* from two totals is now **stated**.

    That test compares ``national_electoral_votes`` against ``national_pv_votes`` and
    concludes a flip happened. This asserts the API says so itself — which is the whole
    point of the story: a consumer should not have to re-derive the comparison to learn
    the answer, and re-deriving it is where they get the denominator wrong.
    """
    body = client.get("/v1/elections/2016/summary").json()
    election = body["election"]

    assert election["year"] == 2016
    assert election["ec_winner_slug"] == "cand-b"
    assert election["pv_winner_slug"] == "cand-a"
    assert election["pv_flip"] is True
    # The names ship beside the slugs, so a display consumer needs no second call.
    assert election["ec_winner"] == "Cand B"
    assert election["pv_winner"] == "Cand A"
    # Margins are percentage points and both methods are contested here.
    assert election["ec_margin"] > 0.0
    assert election["pv_margin"] > 0.0


def test_the_election_summary_rides_along_on_the_year_endpoint(
    client: TestClient,
) -> None:
    """``/v1/elections/{year}`` carries the same object, so one call answers everything.

    The state rows, the per-candidate roll-up and the per-election comparison arrive
    together; a reader who wants "who won, and would another method disagree" makes one
    request.
    """
    body = client.get("/v1/elections/2016").json()
    assert body["election"]["pv_flip"] is True
    assert body["election"]["year"] == 2016
    # `meta.count` still counts `data` only — the new key must not change it.
    assert body["meta"]["count"] == len(body["data"])


def test_a_pre_popular_vote_year_reports_null_flips_not_false(
    client: TestClient,
) -> None:
    """1860: the EC half is answered, the PV half is null — and null, not ``false``.

    ``false`` would assert that the popular vote *agreed* with the electoral college in
    a year this surface has no popular vote for. That is the missing-vs-zero error the
    whole project is about, so it gets an explicit test rather than being left to the
    construction that happens to produce it.
    """
    election = client.get("/v1/elections/1860/summary").json()["election"]

    assert election["pv_flip"] is None
    assert election["hybrid_flip"] is None
    assert election["pv_winner"] is None
    assert election["pv_winner_slug"] is None
    # The electoral college is fully recorded back to 1824 — this half must be real.
    assert election["ec_winner"] is not None
    assert election["ec_winner_slug"] is not None
    assert election["electoral_denominator"] is not None
    # And coverage is real, because it comes from the in-repo catalog rather than the
    # warehouse roster (the divergence #102 introduced on purpose).
    assert election["pv_coverage"] is not None


def test_the_per_candidate_hybrid_fields_reach_the_summary_rows(
    client: TestClient,
) -> None:
    """AC-4's per-candidate half: shares and the hybrid score on each roll-up row."""
    rows = client.get("/v1/elections/2016/summary").json()["data"]
    for row in rows:
        for field in (
            "ec_share_full",
            "pv_share",
            "ec_share_hybrid",
            "pv_coverage",
            "hybrid_score",
        ):
            assert field in row, f"{field} must surface on the summary row"
            assert row[field] is not None
        # The D037/A safety property, visible to a consumer.
        assert row["ec_share_full"] == row["ec_share_hybrid"]
        # The hybrid really is the average of the two ratios, not a ratio of sums.
        assert row["hybrid_score"] == pytest.approx(
            (row["ec_share_hybrid"] + row["pv_share"]) / 2
        )
