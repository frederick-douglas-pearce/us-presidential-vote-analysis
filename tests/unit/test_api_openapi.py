"""OpenAPI polish: metadata, tags, examples, live coverage window, /docs + /redoc (#98).

All offline, **no live DB** (D028): a small synthetic snapshot is served, and the assertions
read ``/openapi.json`` + the doc HTML. The coverage-window assertion uses distinct years
(1984, 2020) so a stale hard-coded span would be caught.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from usvote.api import create_app
from usvote.api.config import ApiSettings
from usvote.snapshot import build_snapshot

_TS = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


def _row(year: int, candidate_id: int, candidate: str, ev: int, rank: int) -> dict:
    return {
        "year": year,
        "state": "Texas",
        "state_usps": "TX",
        "candidate_id": candidate_id,
        "candidate": candidate,
        "total_electoral_votes": 38,
        "president_electoral_votes": ev,
        "national_electoral_votes": ev,
        "president_electoral_rank": rank,
        "took_office": rank == 1,
        "source": "MIT",
        "party": "DEMOCRAT" if candidate == "Cand B" else "REPUBLICAN",
        "candidate_votes": 5_000_000,
        "state_total_votes": 11_000_000,
        "reliability": "exact",
        "redistributable": True,
    }


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row(1984, 1, "Cand A", 38, 1),
            _row(1984, 2, "Cand B", 0, 2),
            _row(2020, 1, "Cand A", 0, 2),
            _row(2020, 2, "Cand B", 38, 1),
        ]
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    out = str(tmp_path / "snapshot.sqlite")
    build_snapshot(_frame(), out, build_timestamp=_TS)
    settings = ApiSettings(snapshot_path=out, cors_origins=["http://localhost:5173"])
    with TestClient(create_app(settings)) as c:
        yield c


# --- top-level metadata -----------------------------------------------------


def test_openapi_info_has_public_metadata(client: TestClient) -> None:
    info = client.get("/openapi.json").json()["info"]
    assert info["title"] == "US Presidential Vote API"
    assert info["version"] == "0.2.0"
    assert info["summary"]
    desc = info["description"]
    # The thesis + what the dataset is.
    assert "Electoral College" in desc and "popular vote" in desc
    # Provenance / licensing is prominent, and the redistributable boundary is explicit.
    assert "MIT Election Lab" in desc
    assert "CC0" in desc
    assert "UCSB" in desc
    # Points a first-time developer at the docs.
    assert "/docs" in desc and "/redoc" in desc


def test_openapi_contact_and_license(client: TestClient) -> None:
    info = client.get("/openapi.json").json()["info"]
    assert info["contact"]["url"].startswith("https://github.com/")
    assert info["license"]["name"].startswith("CC0")
    assert info["license"]["url"].startswith("http")


def test_openapi_description_reflects_live_coverage_window(client: TestClient) -> None:
    """The headline coverage line is filled from the loaded snapshot, not hard-coded."""
    desc = client.get("/openapi.json").json()["info"]["description"]
    assert "1984–2020" in desc
    assert "{coverage_window}" not in desc  # placeholder was substituted


# --- tags -------------------------------------------------------------------


def test_openapi_tags_are_grouped_and_described(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    tags = {t["name"]: t.get("description", "") for t in schema["tags"]}
    for name in ("Elections", "States", "Candidates", "Meta", "Ops"):
        assert name in tags, name
        assert tags[name], f"tag {name} has no description"


def test_endpoints_carry_the_right_tags(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/v1/elections"]["get"]["tags"] == ["Elections"]
    assert paths["/v1/states/{usps}"]["get"]["tags"] == ["States"]
    assert paths["/v1/candidates/{slug}"]["get"]["tags"] == ["Candidates"]
    assert paths["/v1/meta"]["get"]["tags"] == ["Meta"]
    assert paths["/health"]["get"]["tags"] == ["Ops"]


# --- examples ---------------------------------------------------------------


def test_response_schemas_carry_examples(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("EcPvRow", "NationalSummaryRow", "Provenance", "Meta", "ErrorBody"):
        assert schemas[name].get("examples"), f"{name} ships no OpenAPI example"


# --- interactive docs render ------------------------------------------------


def test_swagger_ui_renders(client: TestClient) -> None:
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_redoc_renders(client: TestClient) -> None:
    resp = client.get("/redoc")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
