"""The /states map's state outlines, ``dashboard/explore/assets/usa_110m.json`` (D121(i), (j)).

The file is the one non-code, non-CSS file the deploy root admits
(``_deploy_root_file_allowed`` in ``test_dashboard_guards.py``), and these tests are what
make that entry mean "geometry": closed key sets at every level, the served roster as the
authority for its ids, and a byte-exact rebuild from the pinned Natural Earth source,
committed as ``tests/fixtures/natural_earth/`` (public domain). The build step is
``scripts/build_usa_topojson.py``, loaded by path.

Plotly.js reading the file and drawing 51 states is #623's e2e check (D121 Guards).
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

import explore.app as appmod
from explore import charts

REPO = Path(__file__).resolve().parents[2]
ASSET = REPO / "dashboard" / "explore" / "assets" / "usa_110m.json"
SOURCE = (
    REPO
    / "tests"
    / "fixtures"
    / "natural_earth"
    / "ne_110m_admin_1_states_provinces_lakes.geojson"
)
STATES_RECORDING = (
    REPO / "tests" / "fixtures" / "dashboard" / "v1_elections_states.json"
)
BUILDER = REPO / "scripts" / "build_usa_topojson.py"

PROVENANCE_KEYS = {"source", "version", "url", "sha256", "license", "build"}


def _load_builder() -> Any:
    spec = importlib.util.spec_from_file_location("build_usa_topojson", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


@pytest.fixture(scope="module")
def topology() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(ASSET.read_text(encoding="utf-8"))
    return loaded


def _geometries(topo: dict[str, Any]) -> list[dict[str, Any]]:
    geometries: list[dict[str, Any]] = topo["objects"]["subunits"]["geometries"]
    return geometries


def _polygons(geometry: dict[str, Any]) -> list[list[list[int]]]:
    """A geometry's polygons as lists of rings, each ring a list of arc indexes."""
    if geometry["type"] == "Polygon":
        return [geometry["arcs"]]
    polygons: list[list[list[int]]] = geometry["arcs"]
    return polygons


def _decode(arc: list[list[int]]) -> list[tuple[int, int]]:
    """Undo the delta encoding: quantized points, in order."""
    x = y = 0
    points = []
    for dx, dy in arc:
        x, y = x + dx, y + dy
        points.append((x, y))
    return points


def _twice_area(ring: list[tuple[int, int]]) -> int:
    return sum(
        x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False)
    )


# --- what the shipped file holds ------------------------------------------------------


class TestRoster:
    """D121(j): the file's ids are the served roster, and plotly's ``gu`` filter holds."""

    def test_its_ids_are_the_served_usps_codes(self, topology: dict[str, Any]) -> None:
        recording = json.loads(STATES_RECORDING.read_text(encoding="utf-8"))
        served = {row["state_usps"] for row in recording["data"]}
        ids = [g["id"] for g in _geometries(topology)]
        assert len(served) == 51
        assert len(ids) == len(set(ids))
        assert set(ids) == served

    def test_every_geometry_carries_gu_usa(self, topology: dict[str, Any]) -> None:
        assert all(g["properties"] == {"gu": "USA"} for g in _geometries(topology))


class TestClosedKeys:
    """Nothing but geometry and its provenance can ride in the file."""

    def test_its_top_level_keys(self, topology: dict[str, Any]) -> None:
        assert topology["type"] == "Topology"
        assert set(topology) == {
            "type",
            "bbox",
            "transform",
            "arcs",
            "objects",
            "provenance",
        }
        assert set(topology["transform"]) == {"scale", "translate"}

    def test_its_one_object_is_subunits(self, topology: dict[str, Any]) -> None:
        assert set(topology["objects"]) == {"subunits"}
        subunits = topology["objects"]["subunits"]
        assert set(subunits) == {"type", "geometries"}
        assert subunits["type"] == "GeometryCollection"

    def test_each_geometry_s_keys(self, topology: dict[str, Any]) -> None:
        for g in _geometries(topology):
            assert set(g) == {"type", "id", "properties", "arcs"}, g["id"]
            assert g["type"] in {"Polygon", "MultiPolygon"}, g["id"]

    def test_its_provenance(self, topology: dict[str, Any]) -> None:
        provenance = topology["provenance"]
        assert set(provenance) == PROVENANCE_KEYS
        assert all(isinstance(v, str) for v in provenance.values())
        assert provenance["sha256"] == builder.SOURCE_SHA256
        assert provenance["version"] == builder.NE_VERSION
        assert provenance["url"] == builder.SOURCE_URL
        assert provenance["license"] == "public domain"
        assert provenance["build"] == "scripts/build_usa_topojson.py"
        assert (REPO / provenance["build"]).is_file()


class TestShape:
    def test_every_arc_is_integers(self, topology: dict[str, Any]) -> None:
        for arc in topology["arcs"]:
            assert all(len(p) == 2 and all(type(v) is int for v in p) for p in arc), (
                arc[:2]
            )

    def test_every_referenced_arc_exists_and_is_used_once(
        self, topology: dict[str, Any]
    ) -> None:
        used = [
            index
            for g in _geometries(topology)
            for polygon in _polygons(g)
            for ring in polygon
            for index in ring
        ]
        assert sorted(used) == list(range(len(topology["arcs"])))

    def test_every_ring_is_closed_and_inside_the_bbox(
        self, topology: dict[str, Any]
    ) -> None:
        (kx, ky), (tx, ty) = (
            topology["transform"]["scale"],
            topology["transform"]["translate"],
        )
        x0, y0, x1, y1 = topology["bbox"]
        for arc in topology["arcs"]:
            ring = _decode(arc)
            assert len(ring) >= 4 and ring[0] == ring[-1]
            for qx, qy in ring:
                x, y = qx * kx + tx, qy * ky + ty
                assert x0 - kx <= x <= x1 + kx and y0 - ky <= y <= y1 + ky

    def test_exteriors_run_clockwise_and_holes_counter_clockwise(
        self, topology: dict[str, Any]
    ) -> None:
        """d3-geo, which plotly.js draws with, reads a clockwise exterior as the state;
        a counter-clockwise one would fill everything else (D121(i))."""
        for g in _geometries(topology):
            for polygon in _polygons(g):
                for i, ring in enumerate(polygon):
                    area = _twice_area(_decode(topology["arcs"][ring[0]]))
                    assert (area < 0) == (i == 0), (g["id"], i)

    def test_alaska_and_hawaii_sit_at_their_true_positions(
        self, topology: dict[str, Any]
    ) -> None:
        """The file is not pre-projected; ``albers usa`` insets both (#623)."""
        (kx, ky), (tx, ty) = (
            topology["transform"]["scale"],
            topology["transform"]["translate"],
        )
        by_id = {g["id"]: g for g in _geometries(topology)}
        for code, (lon_lo, lon_hi, lat_lo, lat_hi) in {
            "AK": (-180, -129, 51, 72),
            "HI": (-161, -154, 18, 23),
        }.items():
            for polygon in _polygons(by_id[code]):
                for ring in polygon:
                    for qx, qy in _decode(topology["arcs"][ring[0]]):
                        assert lon_lo <= qx * kx + tx <= lon_hi, code
                        assert lat_lo <= qy * ky + ty <= lat_hi, code


# --- built from Natural Earth ---------------------------------------------------------


class TestBuiltFromNaturalEarth:
    def test_the_fixture_is_the_pinned_source(self) -> None:
        assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == builder.SOURCE_SHA256

    def test_a_rebuild_from_the_source_is_the_shipped_file(self) -> None:
        raw = SOURCE.read_bytes()
        topo = builder.build(
            json.loads(raw), source_sha256=hashlib.sha256(raw).hexdigest()
        )
        assert builder.dumps(topo).encode("utf-8") == ASSET.read_bytes()

    def test_main_writes_the_shipped_file(self, tmp_path: Path) -> None:
        out = tmp_path / "usa_110m.json"
        assert builder.main(["--source", str(SOURCE), "--out", str(out)]) == 0
        assert out.read_bytes() == ASSET.read_bytes()

    def test_main_refuses_another_source_and_writes_nothing(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "other.geojson"
        source.write_bytes(SOURCE.read_bytes() + b" ")
        out = tmp_path / "usa_110m.json"
        assert builder.main(["--source", str(source), "--out", str(out)]) == 1
        assert not out.exists()


# --- served by the dashboard ----------------------------------------------------------


class TestServed:
    PATH = charts.CHART_CONFIG["topojsonURL"] + "usa_110m.json"

    def test_the_config_s_url_serves_the_file(self) -> None:
        response = appmod.server.test_client().get(self.PATH)
        assert response.status_code == 200
        assert response.get_data() == ASSET.read_bytes()

    def test_no_page_links_it(self) -> None:
        """Dash auto-includes only CSS and JS from assets/; plotly.js fetches the file."""
        page = appmod.server.test_client().get("/").get_data(as_text=True)
        assert "usa_110m" not in page


# --- the build, on synthetic input ----------------------------------------------------

SQUARE = [[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0], [0.0, 0.0]]  # clockwise
HOLE = [[2.0, 2.0], [8.0, 2.0], [8.0, 8.0], [2.0, 8.0], [2.0, 2.0]]  # counter-clockwise
ISLAND = [[12.0, 0.0], [12.0, 3.0], [15.0, 3.0], [15.0, 0.0], [12.0, 0.0]]


def _feature(
    code: str | None, geometry: dict[str, Any], gu: str = "USA"
) -> dict[str, Any]:
    props: dict[str, Any] = {"gu_a3": gu, "name": code}
    if code is not None:
        props["postal"] = code
    return {"type": "Feature", "properties": props, "geometry": geometry}


def _collection(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


class TestBuild:
    def test_a_polygon_with_a_hole_and_a_multipolygon(self) -> None:
        topo = builder.build(
            _collection(
                _feature(
                    "ZZ", {"type": "MultiPolygon", "coordinates": [[SQUARE], [ISLAND]]}
                ),
                _feature("AA", {"type": "Polygon", "coordinates": [SQUARE, HOLE]}),
            ),
            source_sha256="x",
        )
        geometries = _geometries(topo)
        assert [g["id"] for g in geometries] == ["AA", "ZZ"]
        assert geometries[0]["type"] == "Polygon"
        assert len(geometries[0]["arcs"]) == 2
        assert geometries[1]["type"] == "MultiPolygon"
        assert [len(p) for p in geometries[1]["arcs"]] == [1, 1]
        assert all(g["properties"] == {"gu": "USA"} for g in geometries)
        assert topo["provenance"]["sha256"] == "x"

    def test_quantized_points_decode_back_within_one_step(self) -> None:
        topo = builder.build(
            _collection(
                _feature("AA", {"type": "Polygon", "coordinates": [SQUARE, HOLE]})
            ),
            source_sha256="x",
        )
        (kx, ky), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
        for arc, ring in zip(topo["arcs"], [SQUARE, HOLE], strict=True):
            for (qx, qy), (x, y) in zip(_decode(arc), ring, strict=True):
                assert abs(qx * kx + tx - x) <= kx and abs(qy * ky + ty - y) <= ky

    @pytest.mark.parametrize(
        ("feature", "message"),
        [
            (
                _feature("AA", {"type": "Polygon", "coordinates": [SQUARE]}, gu="CAN"),
                "gu_a3",
            ),
            (_feature(None, {"type": "Polygon", "coordinates": [SQUARE]}), "no postal"),
            (
                _feature("AA", {"type": "Polygon", "coordinates": [SQUARE[::-1]]}),
                "exterior ring is not clockwise",
            ),
            (
                _feature(
                    "AA", {"type": "Polygon", "coordinates": [SQUARE, HOLE[::-1]]}
                ),
                "hole is not counter-clockwise",
            ),
            (_feature("AA", {"type": "Point", "coordinates": [0, 0]}), "unsupported"),
        ],
    )
    def test_it_refuses(self, feature: dict[str, Any], message: str) -> None:
        with pytest.raises(builder.BuildError, match=message):
            builder.build(_collection(feature), source_sha256="x")

    def test_it_refuses_a_repeated_postal_code(self) -> None:
        polygon = {"type": "Polygon", "coordinates": [SQUARE]}
        with pytest.raises(builder.BuildError, match="appears twice"):
            builder.build(
                _collection(
                    _feature("AA", polygon), _feature("AA", copy.deepcopy(polygon))
                ),
                source_sha256="x",
            )

    def test_it_refuses_a_ring_that_collapses_when_quantized(self) -> None:
        """Never padded or dropped: a ring below 4 distinct points is an error."""
        speck = [[5.0, 5.0], [5.0, 5.0000001], [5.0000001, 5.0000001], [5.0, 5.0]]
        with pytest.raises(builder.BuildError, match="fewer than 4 points"):
            builder.build(
                _collection(
                    _feature(
                        "AA",
                        {"type": "MultiPolygon", "coordinates": [[SQUARE], [speck]]},
                    )
                ),
                source_sha256="x",
            )
