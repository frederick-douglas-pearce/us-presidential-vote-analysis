"""Load-test the dashboard at ``max_instances: 1`` (#277; D071's first flip condition).

The default is **5 page loads per second for 2 minutes**, about twice a whole
10,000-visit day compressed into one hour; ``--rate`` finds the knee below it (#277
measured 1, 2.5 and 5; #291 tracks raising it). A viral link means mostly first-time
visitors, so each simulated load is a **first** visit, fetching everything a fresh
browser fetches, with ``Accept-Encoding: gzip`` so the F1 instance does the compression
it does for real visitors:

1. ``GET /`` (the page shell);
2. every script and stylesheet the shell references (the Dash bundles, several MB before
   compression — the heaviest part of a first visit);
3. ``GET /_dash-layout`` and ``GET /_dash-dependencies``;
4. ``POST /_dash-update-component`` (the Pages routing callback that renders the page).

Reports p50/p95 latency per kind and for the whole page load, and counts of 5xx, 429 and
other failures. Stdlib only:

    python scripts/dashboard_load_test.py https://explore.us-presidential-election-center.org
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import statistics
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

ROUTING = {
    "output": ".._pages_content.children..._pages_store.data..",
    "outputs": [
        {"id": "_pages_content", "property": "children"},
        {"id": "_pages_store", "property": "data"},
    ],
    "inputs": [
        {"id": "_pages_location", "property": "pathname", "value": "/"},
        {"id": "_pages_location", "property": "search", "value": ""},
    ],
    "changedPropIds": ["_pages_location.pathname"],
    "state": [],
}
HEADERS = {"Accept-Encoding": "gzip", "User-Agent": "usvote-load-test"}
ASSET_RE = re.compile(r'(?:src|href)="(/(?:_dash-component-suites|assets)/[^"]+)"')

latencies: dict[str, list[float]] = defaultdict(list)
statuses: Counter[str] = Counter()
lock = threading.Lock()


def request(base: str, kind: str, path: str, body: bytes | None = None) -> bytes:
    headers = dict(HEADERS)
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=body, headers=headers)
    start = time.perf_counter()
    status = "000"
    payload = b""
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = response.read()
            status = str(response.status)
            if response.headers.get("Content-Encoding") == "gzip":
                payload = gzip.decompress(payload)
    except urllib.error.HTTPError as exc:
        status = str(exc.code)
    except OSError:
        status = "error"
    elapsed = time.perf_counter() - start
    with lock:
        latencies[kind].append(elapsed)
        statuses[status] += 1
    return payload


def page_load(base: str) -> None:
    start = time.perf_counter()
    shell = request(base, "shell", "/").decode("utf-8", errors="replace")
    for asset in dict.fromkeys(ASSET_RE.findall(shell)):
        request(base, "asset", asset)
    request(base, "layout", "/_dash-layout")
    request(base, "dependencies", "/_dash-dependencies")
    request(base, "routing", "/_dash-update-component", json.dumps(ROUTING).encode())
    with lock:
        latencies["page_load"].append(time.perf_counter() - start)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base", help="e.g. https://explore.us-presidential-election-center.org")
    parser.add_argument("--rate", type=float, default=5.0, help="page loads per second")
    parser.add_argument("--seconds", type=float, default=120.0)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    total = int(args.rate * args.seconds)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=64) as pool:
        for i in range(total):
            delay = started + i / args.rate - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            pool.submit(page_load, base)
    report = {
        "rate_per_s": args.rate,
        "seconds": args.seconds,
        "page_loads": total,
        "wall_s": round(time.perf_counter() - started, 1),
        "statuses": dict(statuses),
        "5xx": sum(n for s, n in statuses.items() if s.startswith("5")),
        "429": statuses.get("429", 0),
        "latency_s": {
            kind: {
                "n": len(values),
                "p50": round(statistics.median(values), 3),
                "p95": round(percentile(values, 0.95), 3),
                "max": round(max(values), 3),
            }
            for kind, values in sorted(latencies.items())
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
