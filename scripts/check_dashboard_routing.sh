#!/usr/bin/env bash
# Check a deployed dashboard's routing (#526): used by .github/workflows/deploy-dashboard.yml
# on the new version's own host, after scripts/probe_dashboard.sh and before traffic moves,
# so a failure rolls the deploy back.
#
#   scripts/check_dashboard_routing.sh <base url>
#
# Four checks, each judged on its own; every one's result is printed, and the script exits
# nonzero if any fails (docs/deploy-dashboard.md §9 says why each matters):
# - cache filled: GET /election/1825 answers 404 with the app's noindex tag. 1825 is never
#   an election year, but before the instance holds the year list the index answers 200
#   for any year, and that 200 would read as a double decode below. The precondition, so it
#   is retried on any other answer: a request wakes the refresher.
# - decoded once (D089): GET /election/%2531824 answers 404 with noindex. Decoded once it is
#   the year "%31824", which the page refuses; a 200 means something in front of the app
#   decoded the path first. Not judged while the cache is not filled.
# - decoded-once control: GET /election/%31824 answers 200 (it spells 1824).
# - no local plotly.js (#430): HEAD on Dash's bundled plotly.js path answers 404.
# The escaped paths are sent as written: curl does not decode them.
#
# The last three are retried only when no answer arrived (curl's 000) or the answer was a
# 5xx, which none of the failures they look for is; any other answer is final, since a
# double decode is deterministic. Prints status codes and yes/no only, never response
# bytes. Worst case, every request hanging: 4 checks × (3 tries × 20 s + 2 × 5 s) = 280 s,
# under the workflow step's 6-minute timeout.
set -uo pipefail

BASE="${1:?base url}"
BODY=$(mktemp)
trap 'rm -f "$BODY"' EXIT
FAILED=()
CODE=""
NOINDEX=""

# fetch [curl option...] <url>: sets CODE, and NOINDEX to whether the body carries the
# index's noindex tag (unfetched when no answer arrived).
fetch() {
  # Truncate first: a curl that fails before any body arrives leaves its -o file as it
  # was, and no check may read an earlier check's body as its own.
  : > "$BODY"
  CODE=$(curl -sS -o "$BODY" -w '%{http_code}' --max-time 20 "$@") || CODE=000
  if [ "$CODE" = 000 ]; then
    NOINDEX=unfetched
  elif grep -q 'content="noindex"' "$BODY"; then
    NOINDEX=yes
  else
    NOINDEX=no
  fi
}

not_found_page() { [ "$CODE" = 404 ] && [ "$NOINDEX" = yes ]; }
cache_cold() { ! not_found_page; }
transient() { [ "$CODE" = 000 ] || [ "${CODE:0:1}" = 5 ]; }

# fetch_retrying <predicate> [curl option...] <url>: up to three tries, 5 s apart, while
# the predicate holds for the answer.
fetch_retrying() {
  local retry="$1" i
  shift
  for i in 1 2 3; do
    fetch "$@"
    "$retry" || return 0
    if [ "$i" -lt 3 ]; then sleep 5; fi
  done
  return 0
}

pass() { echo "  ✓ $1"; }
miss() {
  echo "  ✗ $1"
  FAILED+=("$2")
}

fetch_retrying cache_cold "${BASE}/election/1825"
if not_found_page; then
  cache=filled
  pass "cache filled: /election/1825 got 404, noindex: yes"
else
  cache=cold
  miss "cache filled: /election/1825 got ${CODE}, noindex: ${NOINDEX}; want 404 with noindex" "cache filled"
fi

fetch_retrying transient "${BASE}/election/%2531824"
if [ "$cache" = cold ]; then
  echo "  - decoded once: /election/%2531824 got ${CODE}, noindex: ${NOINDEX}; not judged, the cache is not filled"
elif not_found_page; then
  pass "decoded once: /election/%2531824 got 404, noindex: yes"
else
  miss "decoded once: /election/%2531824 got ${CODE}, noindex: ${NOINDEX}; want 404 with noindex" "decoded once"
fi

fetch_retrying transient "${BASE}/election/%31824"
if [ "$CODE" = 200 ]; then
  pass "decoded-once control: /election/%31824 got 200"
else
  miss "decoded-once control: /election/%31824 got ${CODE}; want 200" "decoded-once control"
fi

fetch_retrying transient --head "${BASE}/_dash-component-suites/plotly/package_data/plotly.min.js"
if [ "$CODE" = 404 ]; then
  pass "no local plotly.js: got 404"
else
  miss "no local plotly.js: got ${CODE}; want 404" "no local plotly.js"
fi

# The workflow-command line names checks, never paths: the runner decodes %25 in it.
if [ "${#FAILED[@]}" -ne 0 ]; then
  printf -v failed '%s; ' "${FAILED[@]}"
  echo "::error::${BASE} failed the routing checks: ${failed%; }"
  exit 1
fi
echo "  ✓ ${BASE}: every routing check passed"
