#!/usr/bin/env python3
"""Render an Open Graph share card (1200x630 PNG + 2x retina) from a TOML brief.

Ported from the `claude-code-sessions` repo's `og-card` skill, with the specimen
frame swapped: that series shows a terminal window (its subject is session JSON),
this one shows **record panels** (its subject is what historical records do and
don't say). The chassis — dimensions, palette, type scale, wordmark — is shared on
purpose, so both series read as the same author.

Usage:
    uv run python tooling/render-og-card.py social/images/<slug>/og-card.toml

Writes `og-card.svg`, `og-card@2x.png` (2400x1260), and `og-card.png` (1200x630)
alongside the brief.

Gotchas inherited from the source implementation, all load-bearing:

- **Inkscape is snap-confined to $HOME.** Absolute paths only, resolved; a brief
  outside $HOME fails fast rather than silently no-opping.
- **RGBA -> RGB flatten is mandatory.** Inkscape exports RGBA even with no
  transparency, and LinkedIn's preview generator composites RGBA on *white*, which
  muddies a dark card. Flatten onto the background colour before writing.
- **Render at 2x, downscale with Pillow.** Inkscape's own 1x output is harsher than
  a LANCZOS downscale of the 2x.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

BG = "#0f0f14"
PANEL_BG = "#16161d"
PANEL_HEAD = "#1d1d26"
FG = "#ffffff"
MUTED = "#8a8a99"
SUBHEAD_FG = "#c0c0c8"

WIDTH, HEIGHT = 1200, 630
MARGIN = 40
PANEL_GAP = 16
# The specimen is the point of the card, so the title block is deliberately
# under-sized relative to a normal OG card: LinkedIn already renders the post title
# as link text directly beneath the image, so spending height on it twice buys
# nothing and starves the panels.
TITLE_SIZE = 42
TITLE_YS = {1: (72,), 2: (50, 94)}
SUBHEAD_Y = 128
SUBHEAD_SIZE = 23
PANEL_Y = 148
PANEL_H = 436
HEAD_H = 40
ROW_SIZE = 16
ROW_LEAD = 18
ROW_PAD_X = 26
ROW_TOP_PAD = 24

_REPO = Path(__file__).resolve().parents[1]
TEMPLATE = _REPO / "social" / "images" / "og-card-template.svg"


def _title_block(lines: list[str]) -> str:
    """Centred title, one <text> per line. Two lines is the design budget."""
    if len(lines) not in TITLE_YS:
        raise SystemExit(f"card.title takes 1-2 lines, got {len(lines)}")
    return "\n".join(
        f'<text x="600" y="{y}" text-anchor="middle" fill="{FG}" '
        f'font-size="{TITLE_SIZE}" font-weight="300">{escape(line)}</text>'
        for y, line in zip(TITLE_YS[len(lines)], lines, strict=True)
    )


def _subhead_block(text: str) -> str:
    return (
        f'<text x="600" y="{SUBHEAD_Y}" text-anchor="middle" fill="{SUBHEAD_FG}" '
        f'font-size="{SUBHEAD_SIZE}" font-weight="400">{escape(text)}</text>'
    )


def _panel(x: float, w: float, panel: dict) -> str:
    """One record panel: rounded card, header bar, then index-aligned rows.

    Rows are positional. An empty string emits no <text> at all — the blank slot
    is the message, so it must render as genuine absence, not as a placeholder.
    """
    rows = panel["rows"]
    max_rows = (PANEL_H - HEAD_H - ROW_TOP_PAD) // ROW_LEAD
    if len(rows) > max_rows:
        raise SystemExit(
            f"panel '{panel['label']}' has {len(rows)} rows, max {max_rows}"
        )

    head_y = PANEL_Y + HEAD_H
    parts = [
        f'<rect x="{x}" y="{PANEL_Y}" width="{w}" height="{PANEL_H}" rx="14" '
        f'fill="{PANEL_BG}"/>',
        f'<rect x="{x}" y="{PANEL_Y}" width="{w}" height="{HEAD_H}" rx="14" '
        f'fill="{PANEL_HEAD}"/>',
        # Square off the header bar's bottom corners so it reads as a bar, not a pill.
        f'<rect x="{x}" y="{head_y - 14}" width="{w}" height="14" '
        f'fill="{PANEL_HEAD}"/>',
        f'<text x="{x + ROW_PAD_X}" y="{PANEL_Y + 27}" fill="{FG}" font-size="20" '
        f'font-weight="500">{escape(panel["label"])}</text>',
        f'<text x="{x + w - ROW_PAD_X}" y="{PANEL_Y + 27}" text-anchor="end" '
        f'fill="{MUTED}" '
        f'font-size="17" font-weight="300">{escape(panel["sublabel"])}</text>',
    ]
    y = head_y + ROW_TOP_PAD
    for row in rows:
        if row:
            parts.append(
                f'<text x="{x + ROW_PAD_X}" y="{y}" fill="{FG}" font-size="{ROW_SIZE}" '
                f'font-weight="300">{escape(row)}</text>'
            )
        y += ROW_LEAD
    return "<g>\n" + "\n".join(parts) + "\n</g>"


def _specimen_block(panels: list[dict]) -> str:
    if len(panels) != 2:
        raise SystemExit(f"this template renders exactly 2 panels, got {len(panels)}")
    lengths = {len(p["rows"]) for p in panels}
    if len(lengths) != 1:
        raise SystemExit(
            f"panel row counts must match for index alignment, got {lengths}"
        )
    w = (WIDTH - 2 * MARGIN - PANEL_GAP) / 2
    return "\n".join(
        _panel(MARGIN + i * (w + PANEL_GAP), w, p) for i, p in enumerate(panels)
    )


def build_svg(brief: dict) -> str:
    card = brief["card"]
    svg = TEMPLATE.read_text()
    for token, block in (
        ("{{TITLE_BLOCK}}", _title_block(card["title"])),
        ("{{SUBHEAD_BLOCK}}", _subhead_block(card["subhead"])),
        ("{{SPECIMEN_BLOCK}}", _specimen_block(brief["panel"])),
        ("{{SERIES_MARK}}", escape(card.get("series_mark", ""))),
    ):
        svg = svg.replace(token, block)
    return svg


def render(brief_path: Path) -> None:
    brief_path = brief_path.resolve()
    if Path.home() not in brief_path.parents:
        raise SystemExit(
            f"brief must live under {Path.home()} (Inkscape is snap-confined)"
        )

    out = brief_path.parent
    svg_path = out / "og-card.svg"
    png2x = out / "og-card@2x.png"
    png1x = out / "og-card.png"

    with brief_path.open("rb") as fh:
        brief = tomllib.load(fh)
    svg_path.write_text(build_svg(brief))

    subprocess.run(
        ["inkscape", str(svg_path), "--export-type=png", f"--export-filename={png2x}",
         f"--export-width={WIDTH * 2}", f"--export-height={HEIGHT * 2}"],
        check=True, capture_output=True,
    )

    # Flatten RGBA onto BG *before* downscaling: LinkedIn composites RGBA on white.
    img = Image.open(png2x).convert("RGBA")
    flat = Image.new("RGB", img.size, BG)
    flat.paste(img, mask=img.split()[3])
    flat.save(png2x)
    flat.resize((WIDTH, HEIGHT), Image.LANCZOS).save(png1x)

    for p in (svg_path, png2x, png1x):
        print(f"wrote {p.relative_to(Path.cwd()) if Path.cwd() in p.parents else p}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("brief", type=Path, help="path to og-card.toml")
    sys.exit(render(ap.parse_args().brief))
