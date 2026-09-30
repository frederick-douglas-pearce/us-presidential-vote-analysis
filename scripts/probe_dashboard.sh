#!/usr/bin/env bash
# Probe a deployed dashboard (#277): used by .github/workflows/deploy-dashboard.yml.
#
#   scripts/probe_dashboard.sh <base url> <canonical host> [tries]
#
# Passes only when BOTH hold:
# - the page shell (GET /) is 200 and names the canonical host in its canonical link;
# - the page content, fetched the way a browser renders it (the Dash Pages routing
#   callback, POST /_dash-update-component), carries the snapshot version the public API
#   is serving, and is not the degraded message.
# The second half is what proves the server-side API call works; the degraded page is a
# 200 too. Retried while a new instance warms up and fills its cache. The API's version
# is re-read on every try, and the one read first is accepted too, so an API cutover
# during a dashboard deploy does not fail a good deploy.
#
# The default 12 tries is sized for a cold instance warming up (a failing try is quick,
# ≈ 5–6 s). If every call hangs instead, a try can take 50 s (three 15 s requests and the
# 5 s sleep), and the workflow's 8-minute step timeout ends the probe first; the step
# then fails and the rollback runs, but this script's own error line is not printed.
set -uo pipefail

BASE="${1:?base url}"
CANONICAL_HOST="${2:?canonical host}"
TRIES="${3:-12}"
API_HOST="api.us-presidential-election-center.org"
ROUTING='{"output":".._pages_content.children..._pages_store.data..","outputs":[{"id":"_pages_content","property":"children"},{"id":"_pages_store","property":"data"}],"inputs":[{"id":"_pages_location","property":"pathname","value":"/"},{"id":"_pages_location","property":"search","value":""}],"changedPropIds":["_pages_location.pathname"],"state":[]}'
SHELL_HTML=$(mktemp)
trap 'rm -f "$SHELL_HTML"' EXIT

# The API's ETag is its snapshot content hash; Cloudflare makes it weak when it compresses.
api_version() {
  curl -sS -D - -o /dev/null --max-time 15 "https://${API_HOST}/v1/meta" \
    | tr -d '\r' | awk 'tolower($1)=="etag:"{gsub(/"/,"",$2); sub(/^W\//,"",$2); print $2}'
}

first=$(api_version)
if [ -z "$first" ]; then
  echo "::error::could not read the API's snapshot version"
  exit 1
fi

for i in $(seq 1 "$TRIES"); do
  current=$(api_version)
  code=$(curl -sS -o "$SHELL_HTML" -w '%{http_code}' --max-time 15 "${BASE}/") || code=000
  page=$(curl -sS --max-time 15 -H 'Content-Type: application/json' \
    --data "$ROUTING" "${BASE}/_dash-update-component") || page=""
  if [ "$code" = "200" ] \
    && grep -q "rel=\"canonical\" href=\"https://${CANONICAL_HOST}/\"" "$SHELL_HTML" \
    && ! grep -q "isn't responding" <<<"$page"; then
    for want in "$first" ${current:+"$current"}; do
      if grep -q "$want" <<<"$page"; then
        echo "  ✓ ${BASE} serves snapshot ${want:0:12}… (try ${i})"
        exit 0
      fi
    done
  fi
  echo "  … ${BASE}: shell HTTP ${code}; page carries the API's snapshot: no (try ${i}); retrying"
  sleep 5
done
echo "::error::${BASE} never served the API's snapshot (${first})"
exit 1
