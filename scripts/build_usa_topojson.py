"""Build the US state outlines the /states map draws, from Natural Earth (D121(i)).

``python3 scripts/build_usa_topojson.py`` fetches Natural Earth's 1:110m
``admin_1_states_provinces_lakes`` GeoJSON at the pinned release, refuses it unless its
sha256 matches :data:`SOURCE_SHA256`, and writes
``dashboard/explore/assets/usa_110m.json``.
``--source <path>`` reads a local copy instead (the committed test fixture,
``tests/fixtures/natural_earth/``, is one), and ``--out <path>`` writes elsewhere.

**Why the dashboard ships its own file.** Plotly.js fetches the outlines for a
``locationmode: "USA-states"`` choropleth from ``topojsonURL``. The default address is
outside the app, so ``charts.CHART_CONFIG`` points it at the dashboard's assets
directory, and this script builds the one file plotly asks for there (``usa_110m.json``,
from ``geo.scope: "usa"`` and ``resolution: 110``).

**The shape plotly.js 4.1.1 reads.** It takes ``objects["subunits"]``, keeps only the
features whose ``properties.gu`` is ``"USA"``, and matches a location against the
feature's ``id``. So the file holds one object, ``subunits``, with one geometry per
state and DC. Each geometry's ``id`` is its USPS code (Natural Earth's ``postal``), and
its ``properties`` is exactly ``{"gu": <gu_a3>}``, because Natural Earth names that
field ``gu_a3``.

**The encoding.** Coordinates are quantized (a ``transform`` of :data:`QUANTIZATION`
steps per axis) and delta-encoded, and each ring is its own arc. Neighbors' borders are
not shared: plotly.js draws each feature's fill and outline from the feature itself, so
sharing would change only the file's size.

**Winding is checked, never repaired.** d3-geo, which plotly.js draws with and which
does not rewind rings, reads an exterior ring as clockwise; a counter-clockwise one
fills everything except the state. :func:`build` refuses an exterior ring that is not
clockwise, or a hole that is not counter-clockwise (planar, in lon/lat, on the quantized
points that ship). The pinned source passes as it is.

**Provenance rides inside the file** (D085), as a top-level ``provenance`` object
plotly.js does not read: source, version, URL, sha256, license and this build step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

NE_VERSION = "5.1.2"
SOURCE_NAME = "Natural Earth 1:110m Cultural Vectors, admin_1_states_provinces_lakes"
SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/"
    "geojson/ne_110m_admin_1_states_provinces_lakes.geojson"
)
SOURCE_SHA256 = "8e048ee20587e124e74de5c6bfeea8132ab2313a8f7f4f97e043617f8f37f7f6"
LICENSE = "public domain"
BUILD_STEP = "scripts/build_usa_topojson.py"
QUANTIZATION = 100_000

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "dashboard" / "explore" / "assets" / "usa_110m.json"

Point = tuple[int, int]


class BuildError(ValueError):
    """The source cannot be turned into the file plotly.js reads."""


def _rings(geometry: dict[str, Any]) -> list[list[list[list[float]]]]:
    """A geometry's polygons, each a list of rings, whatever its type."""
    kind = geometry.get("type")
    if kind == "Polygon":
        return [geometry["coordinates"]]
    if kind == "MultiPolygon":
        return list(geometry["coordinates"])
    raise BuildError(f"unsupported geometry type {kind!r}")


def _twice_area(ring: Sequence[Point]) -> int:
    """Twice the ring's signed planar area: negative when it runs clockwise."""
    return sum(
        x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False)
    )


def _encode(ring: Sequence[Point]) -> list[list[int]]:
    """One delta-encoded arc: the first point absolute, each next one a difference."""
    arc = [list(ring[0])]
    arc.extend(
        [x - px, y - py] for (px, py), (x, y) in zip(ring, ring[1:], strict=False)
    )
    return arc


def build(geojson: dict[str, Any], *, source_sha256: str) -> dict[str, Any]:
    """Turn the Natural Earth FeatureCollection into the TopoJSON plotly.js reads."""
    features = geojson.get("features")
    if not features:
        raise BuildError("the source holds no features")
    points = [
        point
        for feature in features
        for polygon in _rings(feature["geometry"])
        for ring in polygon
        for point in ring
    ]
    x0 = min(p[0] for p in points)
    y0 = min(p[1] for p in points)
    x1 = max(p[0] for p in points)
    y1 = max(p[1] for p in points)
    kx = (x1 - x0) / (QUANTIZATION - 1)
    ky = (y1 - y0) / (QUANTIZATION - 1)

    def quantize(ring: list[list[float]], label: str) -> list[Point]:
        out: list[Point] = []
        for x, y in ring:
            point = (round((x - x0) / kx), round((y - y0) / ky))
            if not out or out[-1] != point:
                out.append(point)
        if len(out) < 4 or out[0] != out[-1]:
            raise BuildError(
                f"{label}: a ring has fewer than 4 points after quantizing"
            )
        return out

    arcs: list[list[list[int]]] = []
    geometries: dict[str, dict[str, Any]] = {}
    for feature in features:
        props = feature.get("properties") or {}
        code = props.get("postal")
        gu = props.get("gu_a3")
        if not isinstance(code, str) or not code:
            raise BuildError(f"a feature has no postal code: {props.get('name')!r}")
        if gu != "USA":
            raise BuildError(f"{code}: gu_a3 is {gu!r}, not 'USA'")
        if code in geometries:
            raise BuildError(f"{code}: postal code appears twice")
        # TopoJSON nests arc indexes: a ring is a list of arcs (here always one), a
        # Polygon a list of rings, a MultiPolygon a list of Polygons.
        polygons: list[list[list[int]]] = []
        for polygon in _rings(feature["geometry"]):
            indexes: list[list[int]] = []
            for i, ring in enumerate(polygon):
                quantized = quantize(ring, code)
                clockwise = _twice_area(quantized) < 0
                if i == 0 and not clockwise:
                    raise BuildError(f"{code}: an exterior ring is not clockwise")
                if i > 0 and clockwise:
                    raise BuildError(f"{code}: a hole is not counter-clockwise")
                indexes.append([len(arcs)])
                arcs.append(_encode(quantized))
            polygons.append(indexes)
        geometries[code] = (
            {"type": "Polygon", "arcs": polygons[0]}
            if len(polygons) == 1
            else {"type": "MultiPolygon", "arcs": polygons}
        ) | {"id": code, "properties": {"gu": gu}}

    return {
        "type": "Topology",
        "bbox": [x0, y0, x1, y1],
        "transform": {"scale": [kx, ky], "translate": [x0, y0]},
        "arcs": arcs,
        "objects": {
            "subunits": {
                "type": "GeometryCollection",
                "geometries": [geometries[code] for code in sorted(geometries)],
            }
        },
        "provenance": {
            "source": SOURCE_NAME,
            "version": NE_VERSION,
            "url": SOURCE_URL,
            "sha256": source_sha256,
            "license": LICENSE,
            "build": BUILD_STEP,
        },
    }


def dumps(topology: dict[str, Any]) -> str:
    """The file's exact text: compact, sorted keys, one trailing newline."""
    return json.dumps(topology, separators=(",", ":"), sort_keys=True) + "\n"


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "usvote-build-usa-topojson"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body: bytes = response.read()
    return body


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, help="a local copy of the source")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    raw = args.source.read_bytes() if args.source else _fetch(SOURCE_URL)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        print(
            f"source sha256 {digest} is not the pinned {SOURCE_SHA256}; "
            "nothing written",
            file=sys.stderr,
        )
        return 1
    topology = build(json.loads(raw), source_sha256=digest)
    args.out.write_text(dumps(topology), encoding="utf-8", newline="\n")
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
