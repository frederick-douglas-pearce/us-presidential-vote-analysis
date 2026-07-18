"""Runnable entry point — ``python -m usvote.ucsb`` snapshots the UCSB PV pages.

Mirrors the EC :mod:`usvote.__main__`: resolves configuration from the environment and
calls the programmatic entry point, with no logic of its own. This is what makes the
snapshot reproducible — the next refresh (2028) re-runs a versioned, tested module
rather than hunting for a loose script on one machine (D023).

Be aware this is a **network-touching, deliberately slow** command: it honors UCSB's
``Crawl-delay: 10``, so a full 60-election run takes ~10 minutes. It is safe to re-run —
pages already snapshotted are skipped.
"""

from __future__ import annotations

import sys

from usvote.config import ConfigError
from usvote.ucsb.scrape import UCSBScrapeError, snapshot_elections


def main(argv: list[str] | None = None) -> int:
    try:
        snapshot_elections()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    except UCSBScrapeError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
