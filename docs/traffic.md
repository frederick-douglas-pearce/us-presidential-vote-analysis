# Traffic records: retention, export and cost

Request logs are the project's only record of traffic to the dashboard and the API. This
runbook says how long each record is kept, how to export it, and how to keep the cost of
keeping it in check (§1–§5, #502), then what each source counts and cannot see (§6), how to
recognize the project's own traffic (§7), the queries that read a window (§8), and whether
API callers can be identified at all (§9) (§6–§9, #503).

**Never commit an export.** Request logs carry client IP addresses. Exports live on the
owner's machine (or a private bucket), never in this public repo, and nothing per-visitor
is quoted here: aggregates only.

## 1. Where the records are

| Source | Project / account | Log | Retention |
|---|---|---|---|
| Dashboard requests (App Engine) | GCP `uspv-explore` | `appengine.googleapis.com/request_log` in the `_Default` bucket | 365 days (from 2026-11-22; was 30) |
| API origin requests (Cloud Run `usvote-api`) | GCP `uspv-api` | `run.googleapis.com/requests` in the `_Default` bucket | 365 days (from 2026-11-22; was 30) |
| API edge (`usvote-api-proxy` Worker, zone analytics) | Cloudflare, Workers Free | HTTP requests log, Workers Logs and analytics views (§6.3) | 30 days for the HTTP requests log, Zone Analytics and Worker metrics; 7 days for Workers Logs (Observability Free, §4) |
| Google Search (the apex's Domain property) | Google Search Console | Performance, Pages, Sitemaps reports | about 16 months for Performance |

The `_Required` bucket in each project (audit logs only, 400 days, free) is unchanged.

## 2. Retention in GCP

Read the current setting:

```
for p in uspv-explore uspv-api; do
  gcloud logging buckets list --project "$p" \
    --format='table(name.basename(),retentionDays,lifecycleState)'
done
```

Read on 2026-11-22, before the change (both projects identical):

```
LOCATION   RETENTION_DAYS  LIFECYCLE_STATE
_Default   30              ACTIVE
_Required  400             ACTIVE
```

Changed the same day:

```
for p in uspv-explore uspv-api; do
  gcloud logging buckets update _Default --location=global \
    --retention-days=365 --project "$p"
done
```

Read back afterward: `retentionDays: 365` in both.

**Cost.** Cloud Logging bills ingestion past a free 50 GiB per project per month
($0.50/GiB after that), and storage kept past 30 days at $0.01/GiB per month
([pricing](https://cloud.google.com/products/observability/pricing)). It is billed through
the GCP billing account both projects already use, as Cloud Logging line items beside
Cloud Run and App Engine. At 2026-11-22, month-to-date ingestion was about 28 MB
(`uspv-explore`) and 30 MB (`uspv-api`), so a full year of retention costs well under
$0.01 a month. The cost scales with traffic: at 100 times today's traffic, a year comes to
roughly 60 GiB across both projects (about $0.60 a month); at 1,000 times, about $6 a
month, and ingestion passes the free tier. §5 says when to act.

## 3. Exporting the request logs

Run this before any change that could shorten retention, and whenever a snapshot of the
current window is wanted. It writes gzipped newline-delimited JSON, oldest first, to a
dated folder outside the repo:

```
D=~/Documents/Projects/data/usvote-request-logs/$(date -u +%F)
mkdir -p "$D" && chmod 700 "$(dirname "$D")"
gcloud logging read \
  'logName="projects/uspv-explore/logs/appengine.googleapis.com%2Frequest_log"' \
  --project uspv-explore --freshness=400d --order=asc --format=json \
  | jq -c '.[]' | gzip -9 > "$D/explore_request_log.ndjson.gz"
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="usvote-api"
   AND logName="projects/uspv-api/logs/run.googleapis.com%2Frequests"' \
  --project uspv-api --freshness=400d --order=asc --format=json \
  | jq -c '.[]' | gzip -9 > "$D/api_requests.ndjson.gz"
chmod 600 "$D"/*
```

The first export (2026-11-22) held everything both projects still had: 10,450 dashboard
entries and 21,325 API entries, from 2026-10-24 to 2026-11-23 UTC. Nothing older remained.
One dashboard visit writes several entries (the page, its callbacks), so entries are not
visits; §6 says what each source counts.

**A later export** starts where the earlier one ends: add
`AND timestamp>="<the earlier export's last timestamp, UTC>"` to each filter. Exports may
overlap, at that boundary entry or by more; §8's queries drop repeated entries by their
`insertId`, so an overlap never counts twice. The second export (2026-11-28) started at
2026-11-23T00:00Z, before the first one's end (it ran just after midnight UTC), so the two
share the entries from 2026-11-23 00:00 to 01:50 UTC; nothing between them is missing.

## 4. Cloudflare

The account is on **Workers Free**, so from 2026-12-01 it stays on **Observability Free**:
no charges, 0.5 GB of Workers Logs ingested per day, seven days' retention. When the daily
limit is reached, ingestion pauses until it resets, so a large spike can leave Worker logs
missing for the rest of that day. The GCP logs still record every request that reaches the
origin; requests the Worker answers from its cache never reach it.

The free plan's history is short, so the owner captures the zone's analytics and the
`usvote-api-proxy` Worker's metrics views (CSV or screenshot, kept privately) when a record
of them is wanted. §6.3 records which views exist and their retention.

## 5. Periodic size check

**When:** on the first of each month, and after any marketing push.

**Read:** the stored and ingested bytes for each project, from Cloud Monitoring.
`bytes_stored` is what the retention charge is billed on: logs kept past 30 days. It has
no data until the first entries pass 30 days under the new setting.

```
T=$(gcloud auth print-access-token)
END=$(date -u +%FT%TZ); START=$(date -u -d '-1 day' +%FT%TZ)
for p in uspv-explore uspv-api; do
  for m in monthly_bytes_ingested bytes_stored; do
    v=$(curl -s -G -H "Authorization: Bearer $T" \
      "https://monitoring.googleapis.com/v3/projects/$p/timeSeries" \
      --data-urlencode "filter=metric.type=\"logging.googleapis.com/billing/$m\"" \
      --data-urlencode "interval.startTime=$START" \
      --data-urlencode "interval.endTime=$END" \
      | jq -r '[.timeSeries[]?.points[0].value
                | (.int64Value // .doubleValue) | tonumber] | add // "no data"')
    echo "$p $m: $v"
  done
done
```

**Act** when either project's logging cost would pass **$3 a month**: `bytes_stored` above
300 GiB, or `monthly_bytes_ingested` heading past the 50 GiB free tier. The API's budget
kill-switch ([`deploy-cloud-run.md` §9](deploy-cloud-run.md)) pauses the API at $5 a month
of total project cost, logging included, so act well before that.

**How:** export first (§3), then shorten retention with the §2 `update` command and a
smaller `--retention-days`. Shortening deletes the older entries after a seven-day grace
period, during which extending retention again restores them.

## 6. What each source counts

### 6.1 Dashboard: App Engine `request_log` (`uspv-explore`)

**Counts:** every request that reaches the app: document loads, Dash callbacks
(`POST /_dash-update-component`), script and font assets, App Engine's own `/_ah/warmup`
(one per instance start), and scanner probes, which are most of the 4xx.

**A landing** is a `GET` with status 200 for a page path, not an asset (§8.1 defines both).
Landings are counted per page template (`/state/<usps>`, `/election/<year>/states`, …).

**Client-side navigations do not appear with their own path.** The site navigation is Dash
Pages' `dcc.Link`: it changes the address bar in the browser and asks the server for the
new page's layout through a callback, so the request the log records is
`POST /_dash-update-component`, the same path for every page. The new page's path survives
only in that request's `referrer`: the browser sends the current page's address as the
Referer on same-origin requests, and the app sets no referrer policy that would trim it.
So the server log counts **landings, not pageviews**. Navigations can be recovered, as a
count, by ordering each visitor's callback referrers and counting the changes of path
(§8.3); every interaction on a page sends the same referrer, so a change of path is the
only sign of a navigation. **That count is an upper bound.** A visitor is an IP address and
user agent pair, so two tabs open on different pages, or two people on one network with the
same browser, interleave their referrers and every switch counts as a navigation. Landings
alone are the lower bound. Both export windows show pages in callback referrers that no
browser landed on, which is the navigation path at work.

**Cannot see:** who is a person. Many `Mozilla/…` user agents load `/` and never run a
callback: link previews, prefetchers and crawlers that present a browser user agent. A
visitor that ran at least one callback ran the app's JavaScript, which is the closest the
log comes to a person (§8.3 counts them). It also cannot tell the owner's own browsing from
anyone else's without an IP address (§7).

**Retention:** 365 days (§1). **Query:** §8.1 (landings), §8.3 (navigations).

### 6.2 API origin: Cloud Run request logs (`uspv-api`)

**Counts:** requests that reach the origin, which are **edge-cache misses only** for
`GET /v1`. The Worker answers cached `GET /v1` 200s from Cloudflare's edge for 30 days
(`s-maxage=2592000`, [`deploy-cloud-run.md` §7](deploy-cloud-run.md)). The cache is per
data center and keyed on the full URL, query string included, so the origin sees **at
least** the first request for each URL at each data center after a purge; it sees more when
Cloudflare evicts an entry early, and every request whose query string is new.
**Origin counts for `/v1` are a floor, not API use.** Paths outside `/v1` (`/`, `/docs`,
`/openapi.json`, `/health`) and every non-200 the Worker handles are never cached, so the
origin sees all of those that get past Cloudflare: requests the zone blocks first (the WAF
rate limit on `/v1`, [`deploy-cloud-run.md` §7](deploy-cloud-run.md), or its security
checks) never reach the Worker or the origin.

**Cannot see:** cached `/v1` reads, which are the normal case for a repeat caller. The
`referer` is logged when sent: the `/docs` page's own requests carry
`api.us-presidential-election-center.org`, and search arrivals carry a search engine's host.
A referer naming the apex is forged: the apex has no address record (§6.3), and every such
request in the exports was a failed scanner probe.

**Retention:** 365 days (§1). **Query:** §8.2.

### 6.3 API edge: Cloudflare (free plan)

Cloudflare sees **only the API host**. The dashboard's record is a DNS-only CNAME to App
Engine ([`deploy-dashboard.md`](deploy-dashboard.md), the custom-domain steps), so its
traffic never passes through Cloudflare. The apex has no address record yet, so it serves
nothing (#510 adds its redirect).

| View | Shows | Per endpoint? | Per user agent? | History |
|---|---|---|---|---|
| Zone Analytics (the zone's requests view) | requests, data transfer, visits, cache hit rate, status codes, cache status, top paths, countries, hosts, browsers, OS, device types, user agents | top paths, zone-wide | top user agents, zone-wide; not crossed with paths | 30 days |
| Worker `usvote-api-proxy` → Metrics | invocations, subrequests to the origin by status, errors, CPU and wall time, requests by data center | no | no | 30 days |
| HTTP requests log (Observability → Logs → HTTP requests) | one entry per request to the zone, cached or not: time, method, host, path, edge status, cache status, client IP, with further request and client fields | yes, per request | not checked: the client field group is where it would be | 30 days |
| Workers Logs (Observability) | the Worker's own log lines, of which the published Worker ([`deploy-cloud-run.md` §7](deploy-cloud-run.md)) writes none, plus each invocation's request if invocation logs are on (not checked) | only with invocation logs | only with invocation logs | 7 days (§4) |

Zone Analytics and the HTTP requests log also show client IPs; a capture of it is kept privately (§4) and never
quoted here. **Query:** these are console views; there is no query to save. A reading is a
capture, taken when wanted (§4).

### 6.4 Google Search Console (Domain property)

The apex is verified as a **Domain property**, which covers every host under it, so the
dashboard and the API appear in one property, separated by page URL.

- **Performance** (search type Web): clicks, impressions, click-through rate and average
  position, by query, page, country, device and date; about 16 months of history, with a
  delay of a few days.
- **Indexing → Pages:** which URLs Google has indexed and why the others are not.
- **Indexing → Sitemaps:** empty until the sitemap story (#508) submits one; after it, the
  sitemap's status and how many of its URLs were discovered.

**Before #508**, Google finds dashboard pages only by following links, so few are indexed.
**After it**, the Pages report should show the sitemap's URLs being discovered, and
Performance gains impressions for pages beyond `/`. **Query:** console views, read by the
owner (search.google.com/search-console → the property → the report).

## 7. Our own traffic: exclusion filters

Each filter recognizes our traffic by a field in the log, never by an IP address.

| Filter | Recognized by | Where it shows |
|---|---|---|
| `own-agents` | user agent starting `usvote-`: `usvote-explore` (the dashboard's keep-warm `/health` ping and its `/v1` fills, `dashboard/explore/api.py`), `usvote-load-test` (`scripts/dashboard_load_test.py`), and one-off scripts not in the repo, seen in the logs as `usvote-density-check/1.0`, `usvote-dev-check`, `usvote-fixture-recorder` and others | dashboard and API |
| `canary` | user agent `curl/…`, inside a run of `api-canary.yml` (daily, scheduled 13:17 UTC, though GitHub often starts it late, so match the run's own start and end, §8.4) | dashboard and API |
| `deploy-smoke` | user agent `curl/…`, inside a run of `deploy.yml` or `deploy-dashboard.yml` (§8.4) | dashboard and API |
| `unattributed-curl` | user agent `curl/…` outside any workflow run: mostly the owner's and the loop's own checks, but a third-party caller using curl lands here too, so do not exclude it as ours without looking | dashboard and API |
| `cold-start-script` | user agent containing `HeadlessChrome`: `scripts/measure_dashboard_cold_start.py` drives headless Chromium with Playwright's default user agent. Headless crawlers share it, so this filter over-excludes | dashboard |
| `owner-browsing` | **not recognizable** in the logs without an IP address. Exclude it in analytics instead (#504, #506 pick the method) | dashboard |
| `warmup` | path `/_ah/warmup`: App Engine starting an instance, not a request from outside | dashboard |

## 8. Reading a window: the queries

The queries run against an export (§3), offline. Save the definitions below once as
`~/Documents/Projects/data/usvote-request-logs/traffic.jq`, beside the exports and outside
the repo. Each query prints counts only; the ones that group by visitor hold the IP
address in memory and never print it. Set the window and the export folders first:

```
cd ~/Documents/Projects/data/usvote-request-logs
FROM=2026-10-01; TO=2026-11-23          # UTC dates; TO is exclusive
EX="2026-11-22 2026-11-28"              # the export folders that cover the window
```

```
def uaclass: (. // "") as $u
  | if $u == "" then "script"
    elif ($u | test("^usvote-"; "i")) then "own"
    elif ($u | test("^curl/"; "i")) then "curl"
    elif ($u | test("HeadlessChrome")) then "headless"
    elif ($u | test("bot|crawl|spider|slurp|facebookexternalhit|preview|ahrefs|semrush|petalbot|yandex|baidu|bytespider|gptbot|claude|ccbot|perplexity|amazonbot|applebot|censys|expanse|zgrab|scan|internet-measurement"; "i")) then "crawler"
    elif ($u | test("^(wget|python|go-http|okhttp|java|libwww|node|axios|httpx|aiohttp|undici|postman|php|ruby|reqwest|powershell)"; "i")) then "script"
    elif ($u | startswith("Mozilla/")) then "browser"
    else "other" end;
def bare: split("?")[0] | (rtrimstr("/") | if . == "" then "/" else . end);
def asset: test("^/(_dash-|_ah/|assets/|_favicon|_reload|static/)|[.](js|css|map|png|ico|svg|woff2?|txt|xml|json)$");
def page: bare
  | sub("^/election/[0-9]{4}"; "/election/<year>")
  | sub("^/state/[A-Za-z]{2}"; "/state/<usps>")
  | sub("^/candidate/[^/]+$"; "/candidate/<slug>");
def endpoint: bare
  | gsub("/[0-9]{4}(?=/|$)"; "/<year>")
  | sub("^/v1/states/[A-Za-z]{2}"; "/v1/states/<usps>")
  | sub("^/v1/candidates/[^/]+"; "/v1/candidates/<id>");
def landing: .protoPayload | .method == "GET" and .status == 200 and ((.resource | bare | asset) | not);
def tally: group_by(.) | map({(.[0]): length}) | add // {} | to_entries | sort_by(-.value) | from_entries;
def entries: [inputs] | unique_by(.insertId) | .[];
```

`entries` reads every export in `EX` and keeps one copy of each log entry, so overlapping
exports (§3) are safe. The user-agent classes are `browser`, `crawler` (including scanners), `script`, `curl`,
`headless` and `own`; §7 says which of them are ours.

### 8.1 Dashboard landings, by user-agent class and by page

```
for d in $EX; do zcat "$d/explore_request_log.ndjson.gz"; done \
| jq -n -L . --arg from "$FROM" --arg to "$TO" 'include "traffic";
  [entries | select(.timestamp >= $from and .timestamp < $to) | select(landing)
   | .protoPayload | {c: (.userAgent | uaclass), p: (.resource | page),
                      r: ((.referrer // "") | sub("^https?://"; "") | split("/")[0] // "(none)")}]
  | {landings_by_class: (map(.c) | tally),
     browser_landings_by_page: (map(select(.c == "browser") | .p) | tally),
     browser_landings_by_referrer_host: (map(select(.c == "browser") | .r) | tally)}'
```

### 8.2 API origin requests, by class, status and endpoint

```
for d in $EX; do zcat "$d/api_requests.ndjson.gz"; done \
| jq -n -L . --arg from "$FROM" --arg to "$TO" 'include "traffic";
  [entries | select(.timestamp >= $from and .timestamp < $to) | .httpRequest
   | {c: (.userAgent | uaclass), ua: .userAgent, s: .status,
      e: (.requestUrl | sub("^https?://[^/]+"; "") | endpoint),
      r: ((.referer // "") | sub("^https?://"; "") | split("/")[0] // "(none)")}]
  | {by_class: (map(.c) | tally), status: (map("\(.s / 100 | floor)xx") | tally),
     own_by_agent: (map(select(.c == "own") | .ua) | tally),
     served_by_endpoint: (map(select(.s < 400) | .e) | tally),
     served_v1_not_own_by_class: (map(select(.s < 400 and .c != "own" and (.e | startswith("/v1"))) | .c) | tally),
     referrer_host: (map(select(.r != "(none)") | .r) | tally)}'
```

### 8.3 Visitors that ran the app, and client-side navigations

A visitor here is one IP address and user agent pair, held in memory only. It ran the app
if it sent at least one callback; a navigation is a change of path in its callback
referrers (§6.1). Two tabs, or two people on one network with the same browser, share a
key, so `client_side_navigations` is an upper bound.

```
for d in $EX; do zcat "$d/explore_request_log.ndjson.gz"; done \
| jq -n -L . --arg from "$FROM" --arg to "$TO" 'include "traffic";
  [entries | select(.timestamp >= $from and .timestamp < $to) | .timestamp as $t | .protoPayload
   | select(.status == 200 and (.userAgent | uaclass) == "browser")
   | if .method == "GET" and ((.resource | bare | asset) | not)
     then {k: (.ip + "|" + .userAgent), t: $t, kind: "L", p: (.resource | bare)}
     elif .method == "POST" and (.resource | bare | endswith("_dash-update-component"))
          and ((.referrer // "") | test("^https://explore[.]"))
     then {k: (.ip + "|" + .userAgent), t: $t, kind: "C", p: (.referrer | sub("^https://[^/]+"; "") | bare)}
     else empty end]
  | group_by(.k) | map(sort_by(.t)) | map(select(any(.kind == "C"))) as $runners
  | ($runners | map(reduce .[] as $e ({cur: null, navs: []};
        if $e.kind == "L" or .cur == null then .cur = $e.p
        elif $e.p != .cur then .navs += [$e.p | page] | .cur = $e.p else . end) | .navs)
     | add // []) as $navs
  | {visitors_that_ran_the_app: ($runners | length),
     their_landings: ($runners | map(map(select(.kind == "L") | .p | page)) | add // [] | tally),
     client_side_navigations: ($navs | length), navigations_by_page: ($navs | tally)}'
```

### 8.4 Our curl traffic, by workflow run

`gh` lists each workflow's runs; a `curl/…` request inside a run (plus a minute either
side) belongs to it. Two limits: a re-run moves the run's `updatedAt` to the re-run's end,
so its window also takes in every curl in between; and a manual curl made while a run is
going is counted as the run's. Both only move requests between our own buckets.

```
for w in api-canary.yml deploy.yml deploy-dashboard.yml; do
  gh run list -R frederick-douglas-pearce/us-presidential-vote-analysis --workflow "$w" \
    --created ">=$FROM" --limit 400 --json createdAt,updatedAt \
    --jq ".[] | {w: \"$w\", from: .createdAt, to: .updatedAt}"
done | jq -s . > runs.json
for f in explore_request_log api_requests; do
  for d in $EX; do zcat "$d/$f.ndjson.gz"; done \
  | jq -n -c -L . --slurpfile runs runs.json --arg from "$FROM" --arg to "$TO" 'include "traffic";
    def secs: sub("[.][0-9]+"; "") | sub("Z$"; "") | . + "Z" | fromdate;
    ($runs[0] | map({w, a: ((.from | secs) - 60), b: ((.to | secs) + 60)})) as $r
    | [entries | select(.timestamp >= $from and .timestamp < $to)
       | select(((.protoPayload.userAgent // .httpRequest.userAgent) // "") | uaclass == "curl")
       | (.timestamp | secs) as $t
       | ([$r[] | select($t >= .a and $t <= .b) | .w] | first // "outside any run")]
    | tally'
done
```

**Live, without an export:** pipe `gcloud logging read` with the §3 filters (add
`AND timestamp>="<FROM>T00:00:00Z"`) and `--format=json | jq -c '.[]'` into the same `jq`
commands in place of the `zcat` loop.

## 9. Who calls the API

**Callers other than the dashboard and the canary can be identified only partly today.**

- **At the origin (§6.2):** a caller is visible by user-agent class and endpoint, but only
  for requests that missed the edge cache. A caller that reads routes someone else has
  already warmed at the same data center never reaches the origin, so the origin shows that
  callers exist, never how much they read. `/docs` and `/openapi.json` are never cached, so
  readers of the API's documentation are fully visible there, with search arrivals in the
  `referer`.
- **At the edge (§6.3):** Zone Analytics lists the zone's top user agents and top paths for
  30 days, separately, so a new caller shows up only once it is among the top entries, and
  never as "this agent read these routes". Worker metrics carry no path or user agent. Workers
  Logs hold no line the Worker writes (it writes none), and at most seven days of
  invocations if invocation logs are on. The **HTTP requests log**
  has one entry per request, cached or not, with its path and cache status, for 30 days: it
  is the one place a cached read is visible at all, in the console only.

**What would make callers visible:** a record written at the edge for every request,
cached or not, that keeps the user agent's class, the endpoint template, the cache result
and the data center, and no IP address, kept longer than 30 days and readable by a query
rather than in the console. Options are a regular export from the HTTP requests log, the
Worker writing that line to Workers Logs with a weekly export, or the Worker writing it to
a store Cloudflare keeps longer. Choosing one, and the report built on it, is the API usage
report story (#511).
