"""Measure the dashboard's cold start against D071(g)'s MVP target (#277).

The target (owner, 2026-09-28): any shareable path returns its Open Graph HTML in
**≤ 1 s TTFB**, and a cold shared link reaches its **first data cell in ≤ 3 s** at a
390 px viewport on 10 Mbps / 100 ms. "Cold" is the visitor's side: every run is a fresh
browser context with an empty cache. Which *server* state a run measures (dashboard just
restarted, API edge purged) is set up by the operator before running this; the runbook
(docs/deploy-dashboard.md §12) gives the sequences.

Two numbers per run:

- ``ttfb_s``: time to the first byte of ``GET <url>``, the HTML a link-preview scraper
  reads (stdlib, no browser);
- ``first_data_s``: from navigation start until the first provenance line is visible, in
  headless Chromium under the throttled network.

Playwright is not a repo dependency; run it with uvx:

    uvx --with playwright python -m playwright install chromium
    uvx --with playwright python scripts/measure_dashboard_cold_start.py \\
        https://explore.us-presidential-election-center.org/ --runs 3 --label warm
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request

from playwright.sync_api import sync_playwright

#: 10 Mbps each way and 100 ms round trip, as DevTools expresses them.
THROUGHPUT_BYTES_PER_S = 10_000_000 / 8
LATENCY_MS = 100
VIEWPORT = {"width": 390, "height": 844}
FIRST_DATA_SELECTOR = "#provenance li"


def ttfb(url: str) -> float:
    request = urllib.request.Request(url, headers={"User-Agent": "usvote-cold-start"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read(1)
        return time.perf_counter() - start


def first_data(url: str) -> float:
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
            page.wait_for_selector(FIRST_DATA_SELECTOR, state="visible", timeout=30_000)
            return time.perf_counter() - start
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--label", default="", help="the server state being measured")
    args = parser.parse_args()
    for run in range(1, args.runs + 1):
        first_byte = round(ttfb(args.url), 3)
        data = round(first_data(args.url), 3)
        result = {
            "label": args.label,
            "run": run,
            "ttfb_s": first_byte,
            "first_data_s": data,
            "meets_target": first_byte <= 1.0 and data <= 3.0,
        }
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
