# Deploying the dashboard — App Engine standard (E9)

The dashboard runs on **App Engine standard** in its own GCP project, `uspv-explore`, on the
same billing account as the API ([decision **D071**](../.claude/specs/decisions.md)). This
runbook grows with E9. §1–§6 (#283) set up the project and the **cost guard**: a budget and
kill-switch that can pause the dashboard and nothing else. §7–§12 (#277) add the deploy
identity, the `explore.` domain, the deploy workflow, monitoring and measurement.

The app itself lives in [`dashboard/`](../dashboard/), the App Engine deploy root: the
`explore/` package, `app.yaml` and an allow-list `.gcloudignore`. Its dependencies are the
lock's `dashboard` group, exported to `dashboard/requirements.txt` at deploy time (never
committed). It reads data only from `https://api.us-presidential-election-center.org`,
through one in-process cache keyed on the API's `snapshot_version` (D071(d)); the page
content comes from `/v1/meta`, whose `provenance` object is what #277's acceptance criteria
call `meta.provenance` (the list endpoints wrap the same object in `meta`).

> **Order matters: the guard comes before anything serves.** Scope the API's budget first,
> so the new project's first spend cannot land on the API's kill-switch. Then create the
> dashboard's budget and kill-switch before any version serves.

## 1. Scope the API's budget to `uspv-api`

The existing `uspv budget` ($5/mo) publishes to `projects/uspv-api/topics/budget-alerts`,
whose function can pause only the API. Without a project filter the budget covers the
whole billing account, so dashboard spend would pause the **API** and leave the dashboard
running.

```
BILLING_ACCOUNT=<the billing account id>
gcloud billing budgets list --billing-account="$BILLING_ACCOUNT" --format=yaml   # find its id
gcloud billing budgets update <BUDGET_ID> --billing-account="$BILLING_ACCOUNT" \
  --filter-projects=projects/uspv-api
gcloud billing budgets describe <BUDGET_ID> --billing-account="$BILLING_ACCOUNT" \
  --format='yaml(budgetFilter,notificationsRule)'
# budgetFilter.projects: only projects/<N>, where N is uspv-api's project number
# (gcloud projects describe uspv-api --format='value(projectNumber)'); the API accepts
# an ID on input and returns the number. notificationsRule.pubsubTopic: unchanged.
```

The `gcloud billing budgets` commands (list, describe, update, create) need
`billingbudgets.googleapis.com` enabled on the quota project `gcloud` uses:
`--billing-project` if passed, else the `billing/quota_project` property, else the current
project (which `--project` sets for one command).

## 2. Create the project and the App Engine app

```
PROJECT=uspv-explore ; REGION=us-west1
gcloud projects create "$PROJECT"
gcloud billing projects link "$PROJECT" --billing-account="$BILLING_ACCOUNT"
gcloud services enable appengine.googleapis.com cloudfunctions.googleapis.com \
  run.googleapis.com eventarc.googleapis.com pubsub.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com iam.googleapis.com \
  --project="$PROJECT"
gcloud app create --region="$REGION" --project="$PROJECT"   # the region is permanent
```

## 3. The kill-switch

Deploy it as [`deploy/killswitch/README.md`](../deploy/killswitch/README.md) → *Deploy: the
dashboard* gives: the `dashboard-budget-alerts` topic, the `explore-killswitch` service
account with its custom role, and the `dashboard-killswitch` function (target
`app_engine`).

## 4. The dashboard's budget

$5/month, a **specified amount** (never "last period's spend", which is $0 on a new project
and never pauses). Thresholds alert well before the cap; the kill-switch pauses at 100%.
Reaching $5 is a prompt to review the design, not to raise the budget.

```
gcloud billing budgets create --billing-account="$BILLING_ACCOUNT" \
  --display-name="uspv-explore budget" --budget-amount=5USD \
  --filter-projects="projects/${PROJECT}" \
  --threshold-rule=percent=0.25 --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.75 --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0 \
  --notifications-rule-pubsub-topic="projects/${PROJECT}/topics/dashboard-budget-alerts"
```

## 5. The runtime service account

The dashboard only calls the public API over HTTPS: it holds no secret and calls no GCP API,
so at runtime its identity needs only to write logs. Set it as the app's **default** service
account, so every version runs as it even without a `service_account:` line, and name it in
each version's `app.yaml` too.

App Engine also **builds** each version as that version's service account, so the same
identity needs build rights. Grant them on the specific resources the build touches, never
project-wide (the troubleshooter's Storage Admin advice is far broader): read and object
writes on the staging bucket (Cloud Build stores its log there by appending and composing
objects, so `objectCreator` is not enough), and push to two registries. `us.gcr.io` does
not exist in a new project; create it rather than granting create-on-push. #283's first
placeholder deploy established this set error by error (its record is on #283); whether the
`gae-standard` grant is strictly needed was not isolated.

```
gcloud iam service-accounts create explore-run --project="$PROJECT" \
  --display-name="Dashboard runtime"
RUNTIME_SA="explore-run@${PROJECT}.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${RUNTIME_SA}" --role=roles/logging.logWriter
gcloud app update --service-account="$RUNTIME_SA" --project="$PROJECT"

# Build rights, each on one resource.
STAGING="gs://staging.${PROJECT}.appspot.com"
for ROLE in roles/storage.objectUser roles/storage.legacyBucketReader; do
  gcloud storage buckets add-iam-policy-binding "$STAGING" \
    --member="serviceAccount:${RUNTIME_SA}" --role="$ROLE"
done
gcloud artifacts repositories create us.gcr.io --repository-format=docker \
  --location=us --project="$PROJECT"
gcloud artifacts repositories add-iam-policy-binding us.gcr.io --location=us \
  --project="$PROJECT" --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/artifactregistry.writer
gcloud artifacts repositories add-iam-policy-binding gae-standard --location="$REGION" \
  --project="$PROJECT" --member="serviceAccount:${RUNTIME_SA}" \
  --role=roles/artifactregistry.writer
```

The staging bucket appears with `gcloud app create`; `gae-standard` appears on the first
build attempt, so if it is missing, run one deploy (it fails) and then grant.

## 6. Probes

Run after any change to the guard, and record the output. The "only the dashboard" half
cannot be shown by publishing to the dashboard's topic alone (that topic cannot reach the
API's function), so it rests on readbacks that could each come back wrong (budget filters
read back as project **numbers**: compare against
`gcloud projects describe <id> --format='value(projectNumber)'`):

- the dashboard budget's `budgetFilter.projects` is `uspv-explore`'s number only, its
  amount is specified, and it publishes to `dashboard-budget-alerts`;
- the API budget's filter is `uspv-api`'s number only, and it still publishes to
  `budget-alerts`;
- the API function's trigger topic is `projects/uspv-api/topics/budget-alerts`, and the
  dashboard topic's only subscription is the dashboard function's;
- the dashboard function's env and its runtime and trigger service accounts;
- `explore-killswitch` has no binding on `uspv-api`.

Then, against a running version whose `app.yaml` pins the instance count, so "instances
reach 0" can fail rather than happen through idleness. The dashboard's own `app.yaml` does
(§9). Before #277 shipped the app, #283 used a **throwaway placeholder** deployed from a
scratch directory, kept here for the record:

```yaml
# app.yaml (plus a main.py serving "ok" on /, and requirements.txt with gunicorn + flask)
runtime: python314
service_account: explore-run@uspv-explore.iam.gserviceaccount.com
inbound_services: [warmup]
automatic_scaling: {min_instances: 1, max_instances: 1}
```

```
gcloud app deploy --project=uspv-explore --quiet
HOST=$(gcloud app describe --project=uspv-explore --format='value(defaultHostname)')
```

The build runs as `explore-run`, so the §5 build grants must be in place first (App
Engine's [deployment troubleshooter](https://cloud.google.com/appengine/docs/standard/troubleshooter/deployment)
covers the errors a missing one produces). With the domain mapped (§8), run probes 2 and 3
with `HOST=explore.us-presidential-election-center.org`. The instance-count checks in probe
2 mean something only if the serving version pins `min_instances: 1`.

1. **Below threshold:** publish `{"costAmount": 1, "budgetAmount": 5}` to
   `dashboard-budget-alerts`; the function logs `under threshold` and the app stays
   `SERVING`.
2. **Over threshold:** record `gcloud app instances list --project=uspv-explore` (one
   instance), then publish `{"costAmount": 5, "budgetAmount": 5}`. The app becomes
   `USER_DISABLED`; `gcloud app instances list` goes empty; `curl -sS -o /dev/null -w
   '%{http_code}' "https://$HOST/"` no longer returns 200 (record what it returns). Meanwhile
   `https://api.us-presidential-election-center.org/health` still returns 200 and Cloud Run
   `usvote-api` keeps `max_instance_count = 1`.
3. **Un-pause** as the kill-switch README gives, and confirm the app serves again.

## 7. The deploy identity (WIF)

A pool of its own in `uspv-explore`, so nothing that can edit the API's deploy identity can
reach the dashboard's. The provider is locked to this repository **and** to the dashboard
workflow file.

```
GH_REPO=frederick-douglas-pearce/us-presidential-vote-analysis
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project="$PROJECT"
gcloud iam workload-identity-pools create github --location=global \
  --display-name="GitHub" --project="$PROJECT"
gcloud iam workload-identity-pools providers create-oidc github-actions \
  --location=global --workload-identity-pool=github --project="$PROJECT" \
  --display-name="GitHub Actions" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.workflow_ref=assertion.workflow_ref" \
  --attribute-condition="assertion.repository=='${GH_REPO}' && assertion.workflow_ref.startsWith('${GH_REPO}/.github/workflows/deploy-dashboard.yml@')"
POOL=$(gcloud iam workload-identity-pools describe github --location=global \
  --project="$PROJECT" --format='value(name)')

gcloud iam service-accounts create explore-deploy --project="$PROJECT" \
  --display-name="Dashboard deploy (GitHub Actions)"
DEPLOY_SA="explore-deploy@${PROJECT}.iam.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" --project="$PROJECT" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/${POOL}/attribute.repository/${GH_REPO}"
```

Its roles, each as narrow as the deploy allows. `gcloud app deploy` uploads the source **as
the caller**, so the deploy account needs the staging bucket too; the build itself runs as
`explore-run` (§5).

```
for ROLE in roles/appengine.deployer roles/appengine.serviceAdmin \
            roles/cloudbuild.builds.editor; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${DEPLOY_SA}" --role="$ROLE"
done
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --project="$PROJECT" \
  --member="serviceAccount:${DEPLOY_SA}" --role=roles/iam.serviceAccountUser
for ROLE in roles/storage.objectUser roles/storage.legacyBucketReader; do
  gcloud storage buckets add-iam-policy-binding "$STAGING" \
    --member="serviceAccount:${DEPLOY_SA}" --role="$ROLE"
done
```

**Never grant it `roles/appengine.appAdmin`.** Un-pausing a kill-switched app
(`USER_DISABLED` → `SERVING`) needs that role, so without it no deploy run can undo the
kill-switch; un-pausing stays a deliberate human step (§6 probe 3).

GitHub repository variables (Settings → Secrets and variables → Actions → Variables):
`EXPLORE_GCP_PROJECT_ID` (`uspv-explore`), `EXPLORE_WIF_PROVIDER` (the provider's full
resource name: `gcloud iam workload-identity-pools providers describe github-actions
--location=global --workload-identity-pool=github --project="$PROJECT"
--format='value(name)'`), `EXPLORE_DEPLOY_SA`, `EXPLORE_HOSTNAME`
(`explore.us-presidential-election-center.org`) and `EXPLORE_APP_HOSTNAME` (the app's
default host, `gcloud app describe --format='value(defaultHostname)'`, for the canary).

## 8. The domain (before the first real deploy)

The mapping is app-level, so it is made once, against whatever version serves. Doing it
before the first real deploy is what lets the canonical host be a constant in
`explore/config.py`: the app redirects the `appspot.com` host to `explore.` from its first
version, and a browser caches a 301, so it must never point at a host that is not mapped yet.

1. **Verify the apex in Search Console** as the Google account that runs `gcloud`:
   `gcloud domains verify us-presidential-election-center.org` opens Search Console; choose
   the **Domain** property and add the TXT record it gives to the Cloudflare zone. Confirm
   with `gcloud domains list-user-verified`.
2. **Map the host**, with a Google-managed certificate:
   ```
   gcloud app domain-mappings create explore.us-presidential-election-center.org \
     --certificate-management=AUTOMATIC --project="$PROJECT"
   ```
   It prints the DNS record to create (a CNAME to `ghs.googlehosted.com.`).
3. **Add the CNAME in Cloudflare as DNS only** (grey cloud), never proxied: the dashboard
   is served by App Engine directly (D071(c)), and the zone's "Always use HTTPS" setting,
   which the API sits under, is left as it is.
4. **Wait for the certificate**: `gcloud app domain-mappings describe
   explore.us-presidential-election-center.org --project="$PROJECT"` until
   `sslSettings.certificateId` is set and `https://explore.…/` answers with a valid
   certificate.

## 9. Deploying

Run **Deploy dashboard (App Engine)** (`.github/workflows/deploy-dashboard.yml`) from the
Actions tab. It is `workflow_dispatch` only and waits on the `production` environment's
reviewer, like the API's deploy. What it does, in the order that makes rollback automatic:

1. exports `dashboard/requirements.txt` from the lock and refuses one that could install
   `usvote` (`--no-emit-project`: the deployed runtime has no `usvote` to import);
2. deploys a new version (`v-<sha12>-r<run>-a<attempt>`) **without promoting it**. The
   attempt is in the id because "Re-run jobs" keeps the run number and the SHA; an id that
   already exists is refused, since deploying onto it would replace it in place before
   any probe;
3. probes it on its own host, `https://<version>-dot-<app host>/`, with
   [`scripts/probe_dashboard.sh`](../scripts/probe_dashboard.sh): the page shell is 200 and
   names the canonical host, and the page content carries the snapshot version the API is
   serving (the degraded page is a 200 too, so a status code alone proves nothing);
4. moves all traffic to it and probes `explore.` the same way, then checks that the
   `appspot.com` host 301s to `explore.`;
5. only then deletes every other version, and asserts exactly one remains. `min_instances`
   and `max_instances` are per-version settings, so a leftover version would keep its own
   pinned instance running.

If anything from the deploy through the redirect check fails, times out or is cancelled,
the **Roll back** step moves traffic back to the previous version and deletes the new
one, and the site keeps serving what it served before. Each probe has its own 8-minute
step timeout, so a hung probe fails its step (and rolls back) well inside the job's
40 minutes. The step says plainly when it could not roll back ("ROLLBACK FAILED"), or had
nothing to restore (a first deploy), and then fails the job; see §10. If step 5 fails,
the new version is serving and an old one is left behind: the job fails with a message
naming the cleanup to do by hand.

**After a deploy, check by hand that the raw request path reaches the app** (D073). The index
404s a path whose percent-escapes change it when decoded, comparing gunicorn's `RAW_URI` with
the decoded path; if App Engine's front end ever dropped or decoded the raw target, that check
would silently stop applying. The workflow's probes fetch only `/`, which cannot tell:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://explore.us-presidential-election-center.org/%2F  # 404
curl -s -o /dev/null -w '%{http_code}\n' https://explore.us-presidential-election-center.org/     # 200
```

`/%2F` decodes to `//`, which the app reads as `/`: a **200** there means the raw target did
not arrive, and the check is not running.

`app.yaml` pins one F1 instance (`min_instances: 1`, `max_instances: 1`, warmup), runs one
gunicorn worker (one process, so one cache) as `explore-run`, and carries no
`env_variables`; `tests/unit/test_dashboard_guards.py` pins each of those.

## 10. Redeploy and rollback

- **Redeploy** the same code: run the workflow again. **After the kill-switch, un-pause
  first** (the [kill-switch README](../deploy/killswitch/README.md)); a deploy cannot
  un-pause the app, by design (the deploy account has no `appengine.appAdmin`, §7), and
  its probes fail while the app is `USER_DISABLED`.
- **Roll back** to earlier code: push a branch or tag at that commit and pick it in the
  workflow's "Use workflow from" selector. The ref must contain
  `.github/workflows/deploy-dashboard.yml`, so this reaches only commits from #277 on. The
  previous version is deleted after every successful deploy, so there is no old version
  to switch traffic back to by hand; the automatic rollback in §9 covers a deploy that
  fails its probes.
- **After any failed deploy**, check that exactly one version remains, since a second
  version keeps a pinned instance running and spends the budget:
  `gcloud app versions list --project=uspv-explore --service=default`. Delete strays with
  `gcloud app versions delete <id> --project=uspv-explore --service=default`, never the
  one with `TRAFFIC_SPLIT` 1.00.
- **Pause by hand** (abuse, or an incident): the same `PATCH` the
  [kill-switch README](../deploy/killswitch/README.md) gives for un-pausing, with
  `{"servingStatus": "USER_DISABLED"}`, or the console's **Disable application**. `gcloud
  app update` has no serving-status flag. Un-pause as that README says.

## 11. Monitoring and cost

The daily [API canary](../.github/workflows/api-canary.yml) probes the dashboard too, when
`EXPLORE_HOSTNAME` is set:

- `https://explore.…/` is 200 at that hostname, with no redirect, and its canonical link
  names it;
- the page content (the Dash routing callback) is not the degraded message and carries the
  snapshot version the API's `/health` reports. It retries past two refresh intervals
  (5 min each) before failing, so an API deploy during the run is not a false alarm;
- with `EXPLORE_APP_HOSTNAME` set, the `appspot.com` host 301s to `explore.`.

**Declined: the browser-side `Origin` check.** #277's AC asks the canary to send
`Origin: https://explore.…` and assert `Access-Control-Allow-Origin` *for a browser-side
dashboard*. This one is server-side (D071(d)): the browser only ever talks to `explore.`,
and App Engine fetches `/v1` with no `Origin` header, so CORS never applies and
`API_CORS_ORIGINS` is deliberately unchanged. If a browser-side component is ever added,
that story adds the origin and this check.

**The degraded message** appears only when the cache is **empty** (a fresh instance that
could not reach the API). A warm cache keeps serving the last snapshot it read when the API
is down, which is correct under D034: snapshots are immutable, so the last one is still true.

**Cost posture.** One F1 instance pinned all day uses 24 of the free tier's 28 F1
instance-hours per day, per project, so compute is about $0 (D071(b)); `max_instances: 1`
is a hard cap on instances. Egress is compressed (`compress=True`). The $5 budget and the
kill-switch (§3–§4) pause the app at 100%, well inside the $10/month ceiling. **Residual
exposure:** the origin is DNS-only, so Cloudflare does not stand in front of it, and abuse
could run up egress before the budget's alerts (which lag by hours) fire the kill-switch.
That is one of D071's flip conditions.

## 12. Measuring cold start and load

The MVP target (D071(g)): OG HTML in ≤ 1 s TTFB, and first data in ≤ 3 s for a cold shared
link at 390 px on 10 Mbps / 100 ms.
[`scripts/measure_dashboard_cold_start.py`](../scripts/measure_dashboard_cold_start.py)
measures both from one navigation in a fresh browser context each run, and reports a run
that got the plain-language message instead of data as `degraded`. **Nothing else may
reach the server first**: a `curl` sent ahead of the browser would take the start-up and
start the cache fill, and the browser would measure the second visitor. The server
states worth measuring:

- **Warm** (the ordinary case): run it.
- **Dashboard cold**: right after a deploy (warmup has run), and after a kill-switch
  un-pause (the instance starts from nothing).
- **API edge cold**: the order matters, because a running dashboard's refresher re-reads
  `/v1/meta` through the edge every 5 minutes and so refills it. **Pause the dashboard
  first** (§10), then purge the API's Cloudflare cache, wait until the API origin has had
  no request for about 15 minutes (it then scales to zero; check its request log, since
  crawlers wake it too), then un-pause and measure the first visitor. A purge alone
  changes nothing a visitor sees: the dashboard serves from its in-process cache, and the
  purge does not change `snapshot_version`, so no refetch happens. By design, a visitor
  meets a cold API only when the cache is empty.

[`scripts/dashboard_load_test.py`](../scripts/dashboard_load_test.py) drives first-visit
page loads (shell, every bundle, layout, dependencies, the routing callback) against the
single instance. Read server-side latency from App Engine's request log, not the client:
the client's numbers include its own bandwidth. Measured 2026-09-30 (#277): at 1 and 2.5
loads/s the server p95 was 16 ms and 77 ms; at 5 loads/s every request queued to about
1.15 s (no 5xx or 429). The knee is between 2.5 and 5 first-visit loads per second, far
above a 10,000-visit day's busiest hour; #291 tracks raising it. Count the API calls a
run caused from the app's log (`api fetch` lines):

```
gcloud logging read 'resource.type="gae_app" AND textPayload:"api fetch"' \
  --project="$PROJECT" --freshness=10m --format='value(timestamp,textPayload)'
```
