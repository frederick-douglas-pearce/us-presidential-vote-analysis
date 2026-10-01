"""Measure the dashboard's cold start against D071(g)'s MVP target (#277).

The target (owner, 2026-09-28): any shareable path returns its Open Graph HTML in
**≤ 1 s TTFB**, and a cold shared link reaches its **first data cell in ≤ 3 s** at a
390 px viewport on 10 Mbps / 100 ms. "Cold" is the visitor's side: every run is a fresh
browser context with an empty cache. Which *server* state a run measures (dashboard just
restarted, API edge purged) is set up by the operator before running this; the runbook
(docs/deploy-dashboard.md §12) gives the sequences.

Each run is ONE browser navigation, and both numbers come from it:

- ``ttfb_s``: the navigation's own time to first byte (Navigation Timing
  ``responseStart``), under the throttled network;
- ``first_data_s``: from navigation start until the first provenance line is visible;
- ``outcome``: ``data``, or ``degraded`` when the page showed the plain-language message
  instead (a cold cache the refresher could not fill within the visitor's wait), which
  never meets the target.

The browser must be the first request the server sees. A request sent first (a
``curl`` for the TTFB, say) would absorb the instance's start-up and start the cache
fill, and the browser would then measure the second visitor. A link-preview scraper
fetching a shared link before the person clicks it does exactly that; measure that case
on purpose, by sending the request yourself first, never by accident.

Playwright is not a repo dependency; run it with uvx:

    uvx --with playwright python -m playwright install chromium
    uvx --with playwright python scripts/measure_dashboard_cold_start.py \\
        https://explore.us-presidential-election-center.org/ --runs 3 --label warm
"""

from __future__ import annotations

import argparse
import json
import time

from playwright.sync_api import sync_playwright

#: 10 Mbps each way and 100 ms round trip, as DevTools expresses them.
THROUGHPUT_BYTES_PER_S = 10_000_000 / 8
LATENCY_MS = 100
VIEWPORT = {"width": 390, "height": 844}
FIRST_DATA_SELECTOR = "#provenance li"
DEGRADED_SELECTOR = "#unavailable"


def measure(url: str) -> tuple[float, float, bool]:
    """One cold-browser navigation: (TTFB, time to data or the message, degraded?)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(viewport=VIEWPORT)
            page = context.new_page()
            cdp = context.new_cdp_session(page)
            cdp.send("Network.enable")
            cdp.send(
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": LATENCY_MS,
                    "downloadThroughput": THROUGHPUT_BYTES_PER_S,
                    "uploadThroughput": THROUGHPUT_BYTES_PER_S,
                },
            )
            start = time.perf_counter()
            page.goto(url, wait_until="commit")
            page.wait_for_selector(
                f"{FIRST_DATA_SELECTOR}, {DEGRADED_SELECTOR}",
                state="visible",
                timeout=30_000,
            )
            elapsed = time.perf_counter() - start
            degraded = page.locator(DEGRADED_SELECTOR).count() > 0
            response_start_ms = page.evaluate(
                "performance.getEntriesByType('navigation')[0].responseStart"
            )
            return response_start_ms / 1000, elapsed, degraded
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--label", default="", help="the server state being measured")
    args = parser.parse_args()
    for run in range(1, args.runs + 1):
        first_byte, data, degraded = measure(args.url)
        result = {
            "label": args.label,
            "run": run,
            "ttfb_s": round(first_byte, 3),
            "first_data_s": round(data, 3),
            "outcome": "degraded" if degraded else "data",
            "meets_target": not degraded and first_byte <= 1.0 and data <= 3.0,
        }
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
