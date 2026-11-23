# Traffic records: retention, export and cost

Request logs are the project's only record of traffic to the dashboard and the API. This
runbook says how long each record is kept, how to export it, and how to keep the cost of
keeping it in check. It was started by #502; #503 extends it with what each source counts
and the queries that read it.

**Never commit an export.** Request logs carry client IP addresses. Exports live on the
owner's machine (or a private bucket), never in this public repo, and nothing per-visitor
is quoted here: aggregates only.

## 1. Where the records are

| Source | Project / account | Log | Retention |
|---|---|---|---|
| Dashboard requests (App Engine) | GCP `uspv-explore` | `appengine.googleapis.com/request_log` in the `_Default` bucket | 365 days (from 2026-11-22; was 30) |
| API origin requests (Cloud Run `usvote-api`) | GCP `uspv-api` | `run.googleapis.com/requests` in the `_Default` bucket | 365 days (from 2026-11-22; was 30) |
| API edge (`usvote-api-proxy` Worker, zone analytics) | Cloudflare, Workers Free | Workers Logs and analytics views | 7 days for Workers Logs (Observability Free, §4); short analytics history |

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
visits; #503 defines what each source counts.

## 4. Cloudflare

The account is on **Workers Free**, so from 2026-12-01 it stays on **Observability Free**:
no charges, 0.5 GB of Workers Logs ingested per day, seven days' retention. When the daily
limit is reached, ingestion pauses until it resets, so a large spike can leave Worker logs
missing for the rest of that day. The GCP logs still record every request that reaches the
origin; requests the Worker answers from its cache never reach it.

The free plan's history is short, so the owner captures the zone's analytics and the
`usvote-api-proxy` Worker's metrics views (CSV or screenshot, kept privately) when a record
of them is wanted. #503 records which views exist and their retention.

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
