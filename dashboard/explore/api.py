"""The dashboard's only way to read data: the public API, cached in-process (D071(d)).

Three properties hold here, and the tests pin each one:

- **One outbound chokepoint.** :func:`fetch` is the only function that opens a
  connection. It accepts ``/v1/`` paths only, builds the URL on the fixed
  :data:`~explore.config.API_BASE`, checks scheme and host before opening, follows no
  redirect and honours no proxy variable. A path like ``//evil.example/x`` or a 3xx to
  the Cloud Run origin therefore cannot move a request off the public host.
- **A cache keyed on ``snapshot_version``.** The API serves one immutable snapshot at a
  time, and each response's ``ETag`` is that snapshot's content hash. So a cached
  response stays correct until the version changes, and the cache is replaced whole
  when it does: :meth:`Client.refresh` prefetches every registered URL into a new
  :class:`Snapshot` and swaps it in with one assignment. A failed prefetch leaves the
  old snapshot serving. ``/v1/meta``'s body defines a snapshot's version; every other
  response is stored only in the snapshot whose version its ``ETag`` names. (What one
  page render reads is not pinned to one snapshot; that matters once a page reads more
  than one path, and #278 owns it.)
- **Bounded pressure on the API, and a bounded wait for a visitor.** Fills pass a token
  bucket kept well under the API's 60/min/IP rule (App Engine's egress addresses are
  shared). A visitor's request never refreshes the cache itself: with no snapshot yet it
  wakes the refresher and waits at most :data:`MAX_REQUEST_WAIT_S` for the first one,
  then reports the API as unavailable. So a slow or dead API cannot queue visitors on a
  lock, or hold every server thread behind network timeouts.

The refresher is one daemon thread per process (one gunicorn worker, so one cache),
started lazily by the app, never at import: an import-time thread would make network
calls in every test and tool that imports this module. After a failed cycle it backs
off for :data:`RETRY_BACKOFF_S` whatever wakes it, so visitors arriving while the API is
down cannot turn into a stream of retries.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import dash

from explore.config import API_BASE, API_HOST

log = logging.getLogger(__name__)

#: How often the refresher rechecks ``/v1/meta`` for a new snapshot version.
REFRESH_TTL_S = 300.0

#: Per-request network timeout. A cold API origin measured 9.1 s (D071(d)).
FETCH_TIMEOUT_S = 15.0

#: The token bucket: sustained fills per minute, and the burst allowed from rest.
FILLS_PER_MINUTE = 30.0
FILL_BURST = 10.0

#: How long a *visitor's* request may wait — for a fill token, or for the refresher's
#: first snapshot — before the page reports the API unavailable. Within D071(g)'s 3 s
#: first-data budget. The refresher's own fills wait as long as they need.
MAX_REQUEST_WAIT_S = 2.0

#: After a failed refresh, the refresher waits this long before retrying, and visitor
#: wake-ups do not shorten it.
RETRY_BACKOFF_S = 30.0

#: The one path the cache is versioned on.
META_PATH = "/v1/meta"

_PATH_RE = re.compile(r"^/v1/[A-Za-z0-9_\-./]*(\?[A-Za-z0-9_\-.=&%]*)?$")

JsonObject = dict[str, Any]


class ApiUnavailable(Exception):
    """The API could not be read: network, HTTP status, redirect, body or throttle."""


@dataclass(frozen=True)
class Response:
    """A parsed API response and the snapshot version its ``ETag`` names."""

    body: JsonObject
    version: str | None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect, so a 3xx surfaces as an error instead of a new host."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def build_opener() -> urllib.request.OpenerDirector:
    """An opener that follows no redirect and reads no proxy environment variable.

    Passing ``ProxyHandler({})`` stops ``build_opener`` adding its default handler,
    which would read ``HTTPS_PROXY`` and friends from the environment.
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


_OPENER = build_opener()


def build_url(path: str) -> str:
    """The absolute URL for an API path, refusing anything off the public host."""
    if not _PATH_RE.match(path) or "//" in path or ".." in path:
        raise ValueError(f"not a /v1/ API path: {path!r}")
    url = API_BASE + path
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != API_HOST:
        raise ValueError(f"refusing a URL off the public API host: {url!r}")
    return url


def etag_version(etag: str | None) -> str | None:
    """The snapshot version an ``ETag`` names, ignoring a weak-validator prefix.

    Cloudflare rewrites the strong tag to ``W/"…"`` whenever it compresses; the value
    identifies the snapshot and the validator strength does not.
    """
    if not etag:
        return None
    value = etag.strip()
    if value.startswith("W/"):
        value = value[2:]
    return value.strip('"') or None


def fetch(path: str) -> Response:
    """GET one API path. The only function in the dashboard that opens a connection."""
    # Outside the try on purpose: a path refused as off-host is a bug to surface, not
    # an unavailable API to paper over.
    url = build_url(path)
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "usvote-explore"}
    )
    try:
        with _OPENER.open(request, timeout=FETCH_TIMEOUT_S) as raw:
            status = raw.status
            etag = raw.headers.get("ETag")
            payload = raw.read()
    except urllib.error.HTTPError as exc:
        raise ApiUnavailable(f"GET {path}: HTTP {exc.code}") from exc
    except Exception as exc:
        # Everything else at the one I/O boundary: URLError, OSError, and the
        # http.client errors urllib does not wrap (IncompleteRead, BadStatusLine,
        # LineTooLong). Any of them escaping would turn the degraded message into a
        # server error and a blank page.
        raise ApiUnavailable(f"GET {path}: {type(exc).__name__}: {exc}") from exc
    if status != 200:
        raise ApiUnavailable(f"GET {path}: HTTP {status}")
    try:
        body = json.loads(payload)
    except ValueError as exc:
        raise ApiUnavailable(f"GET {path}: invalid JSON") from exc
    if not isinstance(body, dict):
        raise ApiUnavailable(f"GET {path}: expected a JSON object")
    return Response(body=body, version=etag_version(etag))


def snapshot_version_of(meta: JsonObject) -> str:
    """The ``snapshot_version`` a ``/v1/meta`` body carries."""
    try:
        version = meta["provenance"]["snapshot_version"]
    except (KeyError, TypeError) as exc:
        raise ApiUnavailable("/v1/meta carries no provenance.snapshot_version") from exc
    if not isinstance(version, str) or not version:
        raise ApiUnavailable("/v1/meta carries an empty snapshot_version")
    return version


@dataclass
class Snapshot:
    """Every cached response for one snapshot version."""

    version: str
    responses: dict[str, JsonObject] = field(default_factory=dict)


class TokenBucket:
    """Fills per minute with a burst allowance; the clock and sleep are injectable."""

    def __init__(
        self,
        per_minute: float = FILLS_PER_MINUTE,
        burst: float = FILL_BURST,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._rate = per_minute / 60.0
        self._burst = burst
        self._tokens = burst
        self._clock = clock
        self._sleep = sleep
        self._stamp = clock()
        self._lock = threading.Lock()

    def acquire(self, max_wait: float | None) -> None:
        """Take one token, waiting at most ``max_wait`` seconds (``None``: no limit)."""
        with self._lock:
            now = self._clock()
            refill = (now - self._stamp) * self._rate
            self._tokens = min(self._burst, self._tokens + refill)
            self._stamp = now
            wait = 0.0 if self._tokens >= 1.0 else (1.0 - self._tokens) / self._rate
            if max_wait is not None and wait > max_wait:
                raise ApiUnavailable(f"throttled: next fill in {wait:.1f}s")
            # Reserve the token now, so concurrent callers queue behind this one.
            self._tokens -= 1.0
        if wait > 0:
            self._sleep(wait)


class Client:
    """The in-process cache over the public API. One instance per process."""

    def __init__(
        self,
        fetch: Callable[[str], Response] = fetch,
        prefetch_paths: Callable[[], Iterable[str]] = lambda: (),
        bucket: TokenBucket | None = None,
        ttl: float = REFRESH_TTL_S,
        max_request_wait: float = MAX_REQUEST_WAIT_S,
        retry_backoff: float = RETRY_BACKOFF_S,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._fetch = fetch
        self._prefetch_paths = prefetch_paths
        self._bucket = bucket or TokenBucket()
        self._ttl = ttl
        self._max_request_wait = max_request_wait
        self._retry_backoff = retry_backoff
        self._sleep = sleep
        self._snapshot: Snapshot | None = None
        self._ready = threading.Event()  # set once the first snapshot is serving
        self._refresh_lock = threading.Lock()
        self._thread_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()

    @property
    def snapshot(self) -> Snapshot | None:
        """The snapshot currently serving, or ``None`` before the first refresh."""
        return self._snapshot

    def _fill(self, path: str, max_wait: float | None) -> Response:
        self._bucket.acquire(max_wait)
        # One log line per API call, so the calls a load test causes can be counted.
        log.info("api fetch %s", path)
        return self._fetch(path)

    def refresh(self, max_wait: float | None = None) -> Snapshot:
        """Recheck ``/v1/meta``; on a new version, prefetch and swap the cache whole."""
        with self._refresh_lock:
            meta = self._fill(META_PATH, max_wait)
            version = snapshot_version_of(meta.body)
            current = self._snapshot
            if current is not None and current.version == version:
                return current
            fresh = Snapshot(version=version, responses={META_PATH: meta.body})
            for path in dict.fromkeys(self._prefetch_paths()):
                if path in fresh.responses:
                    continue
                response = self._fill(path, max_wait)
                if response.version != version:
                    # The API moved on mid-prefetch; the next refresh starts over.
                    raise ApiUnavailable(
                        f"{path} answered for snapshot {response.version}, "
                        f"not {version}"
                    )
                fresh.responses[path] = response.body
            self._snapshot = fresh  # the atomic swap
            self._ready.set()
            log.info(
                "serving snapshot %s (%d responses)", version, len(fresh.responses)
            )
            return fresh

    def get(self, path: str) -> JsonObject:
        """A response for ``path``: cached if possible, else one throttled fill.

        Never refreshes on the request thread. With no snapshot yet, it wakes the
        refresher and waits at most ``max_request_wait`` for the first one.
        """
        snapshot = self._snapshot
        if snapshot is None:
            self.ensure_refresher()
            self._wake.set()
            self._ready.wait(self._max_request_wait)
            snapshot = self._snapshot
            if snapshot is None:
                raise ApiUnavailable("no snapshot yet; the refresher is retrying")
        cached = snapshot.responses.get(path)
        if cached is not None:
            return cached
        response = self._fill(path, self._max_request_wait)
        if response.version == snapshot.version:
            snapshot.responses[path] = response.body
        else:
            self._wake.set()  # a new version is live; let the refresher swap it in
        return response.body

    def _run(self) -> None:
        # A snapshot that is already serving (warmup filled it) needs no immediate
        # recheck; start with the wait instead of fetching /v1/meta a second time.
        failed = False
        if self._snapshot is not None:
            self._wake.wait(self._ttl)
            self._wake.clear()
        while True:
            # A wake-up requested before this cycle is answered by it.
            self._wake.clear()
            try:
                self.refresh()
                failed = False
            except Exception:  # never let the refresher die on one bad cycle
                log.exception("snapshot refresh failed; keeping the current snapshot")
                failed = True
            if failed:
                # Not wakeable: visitors arriving while the API is down must not turn
                # into a stream of retries.
                self._sleep(self._retry_backoff)
            else:
                # Cleared so a cold start's wake-up (set while this first refresh
                # ran) does not cost a second /v1/meta. A version-mismatch wake-up set
                # during the refresh is dropped here too; the next mismatched miss or
                # the TTL answers it. Reachable only once a page reads a path that is
                # not prefetched (#278, FU-1).
                self._wake.clear()
                self._wake.wait(self._ttl)

    def ensure_refresher(self) -> None:
        """Start the refresher thread if it is not running. Idempotent and cheap."""
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run, name="explore-refresher", daemon=True
            )
            self._thread.start()

    @property
    def refresher_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def registered_prefetch_paths() -> list[str]:
    """Every canonical API path a registered page declares it reads.

    Each page passes ``prefetch=(...)`` to ``dash.register_page``, which keeps it in the
    page registry; collecting from the registry, rather than from a list pages append to
    at import, does not depend on import order.
    """
    paths: list[str] = []
    for page in dash.page_registry.values():
        paths.extend(page.get("prefetch", ()))
    return paths


#: The process's one client. Pages read through it; tests replace it.
CLIENT = Client(prefetch_paths=registered_prefetch_paths)
