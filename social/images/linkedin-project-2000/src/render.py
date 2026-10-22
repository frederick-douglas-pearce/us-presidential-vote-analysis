"""Render the LinkedIn project cards (1200x630 PNG + 2x) from their HTML sources.

Run from this directory:
    uvx --with playwright --with pillow python render.py card1 card2
"""

import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(
        viewport={"width": 1200, "height": 630}, device_scale_factor=2
    )
    for name in sys.argv[1:]:
        page.goto(Path(name + ".html").resolve().as_uri())
        page.wait_for_timeout(300)
        page.screenshot(path=name + "@2x.png")
        # Flatten to RGB and downscale the 2x render, as tooling/render-og-card.py does.
        img = Image.open(name + "@2x.png").convert("RGB")
        img.resize((1200, 630), Image.Resampling.LANCZOS).save(name + ".png")
    browser.close()
