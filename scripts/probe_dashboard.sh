#!/usr/bin/env bash
# Probe a deployed dashboard (#277): used by .github/workflows/deploy-dashboard.yml.
#
#   scripts/probe_dashboard.sh <base url> <canonical host> [tries]
#
# Passes only when BOTH hold:
# - the page shell (GET /) is 200 and names the canonical host in its canonical link;
# - the page content, fetched the way a browser renders it (the Dash Pages routing
#   callback, POST /_dash-update-component), carries the snapshot version the public API
#   is serving right now, and is not the degraded message.
# The second half is what proves the server-side API call works; the degraded page is a
# 200 too. Retried while a new instance warms up and fills its cache.
set -uo pipefail

BASE="${1:?base url}"
CANONICAL_HOST="${2:?canonical host}"
TRIES="${3:-20}"
API_HOST="api.us-presidential-election-center.org"
ROUTING='{"output":".._pages_content.children..._pages_store.data..","outputs":[{"id":"_pages_content","property":"children"},{"id":"_pages_store","property":"data"}],"inputs":[{"id":"_pages_location","property":"pathname","value":"/"},{"id":"_pages_location","property":"search","value":""}],"changedPropIds":["_pages_location.pathname"],"state":[]}'

# The API's ETag is its snapshot content hash; Cloudflare makes it weak when it compresses.
want=$(curl -sS -D - -o /dev/null --max-time 20 "https://${API_HOST}/v1/meta" \
  | tr -d '\r' | awk 'tolower($1)=="etag:"{gsub(/"/,"",$2); sub(/^W\//,"",$2); print $2}')
if [ -z "$want" ]; then
  echo "::error::could not read the API's snapshot version"
  exit 1
fi

for i in $(seq 1 "$TRIES"); do
  code=$(curl -sS -o /tmp/probe-shell.html -w '%{http_code}' --max-time 20 "${BASE}/" || echo 000)
  page=$(curl -sS --max-time 20 -H 'Content-Type: application/json' \
    --data "$ROUTING" "${BASE}/_dash-update-component" || echo "")
  if [ "$code" = "200" ] \
    && grep -q "rel=\"canonical\" href=\"https://${CANONICAL_HOST}/\"" /tmp/probe-shell.html \
    && grep -q "$want" <<<"$page" \
    && ! grep -q "isn't responding" <<<"$page"; then
    echo "  ✓ ${BASE} serves snapshot ${want:0:12}… (try ${i})"
    exit 0
  fi
  echo "  … ${BASE}: shell HTTP ${code}; page carries the snapshot: $(grep -c "$want" <<<"$page") (try ${i}); retrying"
  sleep 6
done
echo "::error::${BASE} never served the API's snapshot ${want}"
exit 1
