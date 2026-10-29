"""Serve the dashboard from recorded API responses, for the browser tests (#321).

Run by ``conftest.py`` as ``python -m tests.e2e.serve <port>``, from ``dashboard/`` (as
``app.yaml`` and the D070(b) guard run the app) with ``dashboard`` and the repository
root on ``PYTHONPATH``. It lives under ``tests/``, never under ``dashboard/``, so the
deploy root's ``.gcloudignore`` allow-list cannot ship it.

The seam is the one ``test_dashboard_app.py``'s offline client uses: the app is
imported, then ``api.CLIENT`` is replaced before it takes traffic. Every runtime module
reads ``api.CLIENT`` when it is called, and the refresher starts on the first request,
so nothing still holds the original client. The guard's fake transport, which runs the
real ``api.fetch``, is the guard's business; this server tests the browser.

No request leaves the machine. Recorded paths answer from ``tests/fixtures/dashboard/``,
and anything else raises ``ApiUnavailable``, so the page shows its degraded state and
never reads live data. Behind that, an audit hook refuses every non-loopback name lookup
and connection. ``api.fetch``'s ``except Exception`` would turn such a refusal into the
degraded page, so the hook also writes :data:`NETWORK_SENTINEL` to stderr, which
``conftest.py`` fails the session on.

Nothing here runs at import: ``conftest.py`` imports :data:`NETWORK_SENTINEL` and
:data:`READY_LINE` from it.
"""

from __future__ import annotations

import json
import sys
from typing import Any

#: Written to stderr, flushed, whenever the audit hook refuses a non-loopback lookup or
#: connection.
NETWORK_SENTINEL = "E2E-SERVER-NETWORK-REFUSED"

#: Written to stderr once the cache is filled and the server is listening.
READY_LINE = "E2E-SERVER-READY"

LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})

#: The keep-warm ping's body (D076). The refresher pings once a TTL has passed.
HEALTH_BODY: dict[str, Any] = {"status": "ok"}

#: The browser tests open a handful of pages; the production bucket (30 fills a minute)
#: would degrade a page now and then, so the bucket is the offline client's.
BUCKET_PER_MINUTE = 6000.0
BUCKET_BURST = 1000.0


def _host(address: Any) -> str | None:
    """The host of a socket address, or None for one with no host (a Unix path)."""
    if isinstance(address, tuple) and address:
        return str(address[0])
    return None


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if event in ("socket.getaddrinfo", "socket.gethostbyname"):
        host = args[0]
    elif event in ("socket.connect", "socket.sendto"):
        host = _host(args[1])
        if host is None:
            return
    else:
        return
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if host in LOOPBACK:
        return
    sys.stderr.write(f"{NETWORK_SENTINEL} {event} {host!r}\n")
    sys.stderr.flush()
    raise OSError(f"the e2e server refuses {event} to {host!r}")


def _fixture_client() -> Any:
    """A client answering every recorded path from its file, at the meta's version."""
    from explore import api
    from tests.dashboard_fixtures import FIXTURE_DIR, RECORDED_FILES

    on_disk = {path.name for path in FIXTURE_DIR.glob("*.json")}
    assert set(RECORDED_FILES.values()) == on_disk, (
        "tests/dashboard_fixtures.py and tests/fixtures/dashboard/ disagree: "
        f"unmapped {sorted(on_disk - set(RECORDED_FILES.values()))}, "
        f"missing {sorted(set(RECORDED_FILES.values()) - on_disk)}"
    )
    bodies = {
        path: json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
        for path, name in RECORDED_FILES.items()
    }
    version = bodies[api.META_PATH]["provenance"]["snapshot_version"]

    def fixture_fetch(path: str, timeout: float = api.FETCH_TIMEOUT_S) -> api.Response:
        api.build_url(path)  # a malformed path raises ValueError, as in production
        if path == api.HEALTH_PATH:
            return api.Response(body=HEALTH_BODY, version=None)
        if path not in bodies:
            raise api.ApiUnavailable(f"GET {path}: no recorded response")
        return api.Response(body=bodies[path], version=version)

    return api.Client(
        fetch=fixture_fetch,
        prefetch_paths=api.registered_prefetch_paths,
        bucket=api.TokenBucket(per_minute=BUCKET_PER_MINUTE, burst=BUCKET_BURST),
    )


def main(port: int) -> None:
    sys.addaudithook(_audit)

    from werkzeug.serving import make_server

    from explore import api
    from explore import app as appmod

    api.CLIENT = _fixture_client()

    # Warmup always answers 200, even when its refresh fails, so check the fill itself.
    assert appmod.server.test_client().get("/_ah/warmup").status_code == 200
    snapshot = api.CLIENT.snapshot
    assert snapshot is not None, "warmup did not fill the cache from the fixtures"
    missing = set(api.registered_prefetch_paths()) - set(snapshot.responses)
    assert not missing, f"warmup left prefetch paths unfilled: {sorted(missing)}"

    server = make_server("127.0.0.1", port, appmod.server, threaded=True)
    sys.stderr.write(f"{READY_LINE} {port}\n")
    sys.stderr.flush()
    server.serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]))
