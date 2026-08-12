"""The OG-card chassis is a *shared* asset: every published card re-renders from it.

`tooling/render-og-card.py` is a script, not a package module — `[tool.mypy] files`
covers `src` and `tests` only, and nothing imports it — so a layout change to it has
no failing test to catch it and silently rewrites every card the next time one is
rebuilt. That is the class of omission these tests close.

The load-bearing property is the one the module's own docstring promises: **an
already-shipped brief re-renders byte-identical**. #152 added content-fitted panel
heights (a five-row specimen in a box sized for twenty read as a rendering fault),
and the first attempt broke exactly this — `(PANEL_H - height) / 2` emitted
`y="148.0"` where the rest of the chassis emits `y="148"`, changing every shipped
card while looking correct on screen.

These run offline against the committed briefs and their committed SVGs; the PNG
step needs Inkscape and is deliberately not exercised here.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "tooling" / "render-og-card.py"
_IMAGES = _REPO / "social" / "images"

#: Every committed card. New cards belong here — the point is that *all* shipped
#: briefs stay reproducible, not two chosen ones.
SHIPPED_SLUGS = sorted(
    p.parent.name for p in _IMAGES.glob("*/og-card.toml")
)


def _load_renderer() -> ModuleType:
    """Import the hyphenated script by path (it is not an importable module name)."""
    spec = importlib.util.spec_from_file_location("render_og_card", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def renderer() -> ModuleType:
    return _load_renderer()


def test_shipped_slugs_is_not_empty() -> None:
    """Guard the guard: a bad glob would make every parametrised test vacuous."""
    assert SHIPPED_SLUGS, f"no og-card.toml briefs found under {_IMAGES}"


@pytest.mark.parametrize("slug", SHIPPED_SLUGS)
def test_committed_brief_rerenders_byte_identical(slug: str, renderer: ModuleType) -> None:
    """The promise in the module docstring, enforced for every shipped card."""
    brief = tomllib.loads((_IMAGES / slug / "og-card.toml").read_text())
    committed = (_IMAGES / slug / "og-card.svg").read_text()
    assert renderer.build_svg(brief) == committed, (
        f"{slug} no longer re-renders to its committed SVG — a chassis change "
        f"rewrote a published card. Re-render every card deliberately, or revert."
    )


def test_full_height_panel_is_unchanged_by_content_fitting(renderer: ModuleType) -> None:
    """At MAX_ROWS the panel must saturate to the original hardcoded geometry.

    This is *why* content-fitting is safe for already-shipped briefs, stated as an
    assertion rather than left as a property of the arithmetic.
    """
    assert renderer._panel_box(renderer.MAX_ROWS) == (renderer.PANEL_Y, renderer.PANEL_H)


def test_panel_geometry_is_integral(renderer: ModuleType) -> None:
    """Floats would render as y="148.0" and break byte-identity. See module docstring."""
    for n_rows in range(1, renderer.MAX_ROWS + 1):
        top, height = renderer._panel_box(n_rows)
        assert isinstance(top, int), f"{n_rows} rows -> non-integral top {top!r}"
        assert isinstance(height, int), f"{n_rows} rows -> non-integral height {height!r}"


def test_short_panel_is_centred_in_the_band(renderer: ModuleType) -> None:
    """A short specimen sits in the middle of the band, not clumped at its top."""
    top, height = renderer._panel_box(5)
    band_top, band_bottom = renderer.PANEL_Y, renderer.PANEL_Y + renderer.PANEL_H
    assert height < renderer.PANEL_H
    assert top > band_top
    # Equal slack above and below, to within the integer-division remainder.
    assert abs((top - band_top) - (band_bottom - (top + height))) <= 1


def test_panel_fits_its_rows(renderer: ModuleType) -> None:
    """Every row must land inside the panel — the fit must not clip the last one."""
    for n_rows in range(1, renderer.MAX_ROWS + 1):
        top, height = renderer._panel_box(n_rows)
        last_baseline = (
            top + renderer.HEAD_H + renderer.ROW_TOP_PAD + (n_rows - 1) * renderer.ROW_LEAD
        )
        assert last_baseline < top + height, f"{n_rows} rows: last row clipped"


@pytest.mark.parametrize("slug", SHIPPED_SLUGS)
def test_committed_pngs_exist_at_the_published_dimensions(slug: str) -> None:
    """`og_card_source` points at the PNG, so the PNG is what actually ships.

    Known limit, stated rather than implied: this does **not** prove the PNG was
    rendered from the committed SVG. Closing that would mean running Inkscape in
    CI (whose output is not version-stable) or pinning a hash of the SVG into the
    PNG's metadata. A stale PNG beside a fresh SVG would still pass — re-render
    deliberately after any chassis change; the byte-identity test above tells you
    when one happened.
    """
    from PIL import Image

    for name, expected in (
        ("og-card.png", (1200, 630)),
        ("og-card@2x.png", (2400, 1260)),
    ):
        path = _IMAGES / slug / name
        assert path.is_file(), f"{slug}/{name} missing — the published card"
        with Image.open(path) as img:
            assert img.size == expected, f"{slug}/{name} is {img.size}, want {expected}"
            # RGBA would composite on white in LinkedIn's preview and muddy the
            # dark card — the renderer flattens for exactly this reason.
            assert img.mode == "RGB", f"{slug}/{name} is {img.mode}, want RGB"


def test_collapsing_space_run_is_rejected(renderer: ModuleType) -> None:
    """SVG collapses consecutive spaces, so run-padding a column silently fails.

    Regression guard: post 1's brief originally padded with three literal spaces and
    rendered with one. It survived only because every leading token was a 4-digit
    year; labels of differing width would have broken the column invisibly.
    """
    panel = {
        "label": "L",
        "sublabel": "s",
        "rows": ["1824   John Quincy Adams"],
    }
    with pytest.raises(SystemExit, match="collapses"):
        renderer._panel(0, 100, panel)


def test_nbsp_gutter_is_accepted(renderer: ModuleType) -> None:
    """The sanctioned alternative must actually pass, or the guard is a dead end."""
    panel = {"label": "L", "sublabel": "s", "rows": ["1824   Adams"]}
    assert "1824   Adams" in renderer._panel(0, 100, panel)


def test_over_max_rows_is_rejected(renderer: ModuleType) -> None:
    """Silent truncation would drop record rows off a published card."""
    panel = {
        "label": "L",
        "sublabel": "s",
        "rows": ["x"] * (renderer.MAX_ROWS + 1),
    }
    with pytest.raises(SystemExit, match="max"):
        renderer._panel(0, 100, panel)


def test_mismatched_row_counts_are_rejected(renderer: ModuleType) -> None:
    """Index alignment across panels is the whole grammar; a mismatch must fail loud."""
    panels = [
        {"label": "L", "sublabel": "s", "rows": ["a", "b"]},
        {"label": "R", "sublabel": "s", "rows": ["a"]},
    ]
    with pytest.raises(SystemExit, match="row counts"):
        renderer._specimen_block(panels)
