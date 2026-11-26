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
3. **Un-pause** as the kill-switch README gives: the API's `/health` returns 200
   immediately before the `PATCH`, `gcloud app instances list` shows an instance, `/health`
   returns 200 again, and your own `GET /` returns 200. That 200 confirms the pause is
   lifted; it does not show the page has data, since the degraded page is a 200 too (§9).
   For that, run [`scripts/probe_dashboard.sh`](../scripts/probe_dashboard.sh) against
   `explore.`.

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
4. checks its routing on the same host with
   [`scripts/check_dashboard_routing.sh`](../scripts/check_dashboard_routing.sh) (#526):
   that the instance's cache is filled, that the path is decoded once, by the app, and
   that the app serves no copy of plotly.js (each explained below);
5. moves all traffic to it and probes `explore.` the same way, then checks that the
   `appspot.com` host 301s to `explore.`;
6. only then deletes every other version, and asserts exactly one remains. `min_instances`
   and `max_instances` are per-version settings, so a leftover version would keep its own
   pinned instance running.

If anything from the deploy through the redirect check fails, times out or is cancelled,
the **Roll back** step moves traffic back to the previous version and deletes the new
one, and the site keeps serving what it served before. A routing check that fails rolls
back before any traffic has moved. Each probe and check has its own step timeout (8
minutes for each probe, 6 for the routing check, 2 for the redirect check), so a hung one
fails its step (and rolls back) well inside the job's 40 minutes. The step says plainly
when it could not roll back ("ROLLBACK FAILED"), or had nothing to restore (a first
deploy), and then fails the job; see §10. If step 6 fails, the new version is serving and
an old one is left behind: the job fails with a message naming the cleanup to do by hand.

#294 drilled Roll back against production, on both of its triggers, after a deploy that
succeeded and before traffic moved: a version-host probe that failed, and a run
cancelled with `gh run cancel` during that probe. Each time, traffic never left the
previous version, the new version was deleted, and exactly one version remained, with
no hand cleanup. So **cancelling a run during the version-host probe is a safe way to
stop a deploy**. The Roll back message reads "deploy of … failed; rolled back to … and
deleted …" for a cancelled run too. Not drilled: a failure or cancel during the build
(Roll back's other branch, which can leave the new version to delete by hand, §10), and
any failure or cancel after traffic has moved, so the restore has not yet been seen to
move traffic back.

Each failing probe try reports every check's result: the shell's HTTP status, whether
the canonical link names `explore.` (`yes` or `no`), and whether the page carries the
API's snapshot (`yes`, `no` or `degraded`). A request curl could not complete (a
timeout, a refused connection, DNS) reports `unfetched` for its check, and a failed
shell request's status shows as 000; an HTTP error response that arrives whole is
judged like any other.

**The routing check** (step 4) prints one line per check, with the status the server
answered and, for `/election/1825` and `/election/%2531824`, whether the body carries
the index's `noindex` tag (`yes`, `no`, or `unfetched` when no answer arrived); a failed
run ends with one `::error::` line naming every check that failed. The cache check is
retried on anything but a 404 with `noindex`, no answer (000) included (below); the
other three are retried only when no answer arrived (curl exited nonzero, reported as
000) or the answer was a 5xx, and any other answer is final. It never prints response
bytes. What each check is for:

- **The path is decoded once, by the app** (D089, which replaced D073's raw-target check).
  Dash's router decodes the browser's pathname once, and the index matches `request.path`,
  which gunicorn has decoded once; they agree only if nothing in front of the app (App
  Engine's front end) decodes the path first. `/election/%2531824` must answer **404** with
  the `noindex` tag. Decoded once, it is the year `%31824`, which the page refuses: a
  **200** there means the path was decoded twice (`%25` became `%` in front of the app,
  then the app read 1824), and an escaped link could open a page its own URL does not name.
  The `noindex` tag is what shows the 404 is the app's own (only its index emits it): a 404
  without it came from somewhere in front of the app. `/election/%31824` is the control:
  decoded once, it is 1824, and must answer 200.
- **The cache is filled first.** Before the instance holds the year list, the index
  answers 200 for any year, so a 200 on `/election/%2531824` would read as a double decode.
  So the check first asks for `/election/1825` (never an election year), which must answer
  404 with `noindex`, retried a few seconds apart since a request wakes the refresher. If
  it never does, the run fails naming the cache check, and the `%2531824` result is
  reported as not judged. The probe in step 3 normally fills the one instance's cache
  before this. A 404 *without* the tag on `/election/1825` is not a cold cache: it came from
  something in front of the app, or the app's 404 lost its tag, and it fails the same way.
- **No local plotly.js** (#430, §11). A `HEAD` of
  `/_dash-component-suites/plotly/package_data/plotly.min.js` must answer 404. A **200**
  with `content-length: 4815814` means the deployed version still registers the file.
  The daily canary repeats this check against `explore.` (§11), which also covers a
  rollback to a ref older than #526, whose workflow has no routing check.

To repeat a check by hand against the public host:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://explore.us-presidential-election-center.org/election/%2531824  # 404
curl -s https://explore.us-presidential-election-center.org/election/%2531824 | grep -c 'content="noindex"'    # 1
curl -s -o /dev/null -w '%{http_code}\n' https://explore.us-presidential-election-center.org/election/%31824    # 200
curl -sI https://explore.us-presidential-election-center.org/_dash-component-suites/plotly/package_data/plotly.min.js | head -1  # HTTP/2 404
```

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
  app update` has no serving-status flag. **Un-pause** as that README says, in four
  steps (#347): request `https://api.us-presidential-election-center.org/health` and
  confirm 200 immediately before the `PATCH` (the paused dashboard sent no keep-warm ping,
  so this also wakes the API's origin); un-pause; wait until `gcloud app instances list`
  shows an instance, because `SERVING` does not mean one is running (after a pause of under
  3 minutes none started for 5 min 20 s, and every request failed meanwhile); then request
  `/health` again, which keeps the origin warm however long the instance took, and make
  your own `GET /` on `explore.`. That `GET /` confirms the pause is lifted (a 200 does not
  show the page has data, since the degraded page is a 200 too;
  [`scripts/probe_dashboard.sh`](../scripts/probe_dashboard.sh) checks that); it does not
  shorten the wait for a visitor who arrives meanwhile. Then run the escalation queries in
  [keep-warm residual](#keep-warm-residual-347).

## 11. Monitoring and cost

The daily [API canary](../.github/workflows/api-canary.yml) probes the dashboard too, when
`EXPLORE_HOSTNAME` is set:

- `https://explore.…/` is 200 at that hostname, with no redirect, and its canonical link
  names it;
- the page content (the Dash routing callback) is not the degraded message and carries the
  snapshot version the API's `/health` reports. It retries past two refresh intervals
  (5 min each) before failing, so an API deploy during the run is not a false alarm;
- with `EXPLORE_APP_HOSTNAME` set, the `appspot.com` host 301s to `explore.`;
- a `HEAD` of the bundled plotly.js script path is 404 (**No local plotly.js**, below;
  #440). A 200 means the running version serves the 4.8 MB file again. No deploy runs this
  check automatically (#526 will add it to the deploy workflow), and a rollback deploys an
  older ref with that ref's own workflow (§10); the canary runs from `main`, so it sees the
  regression whichever ref deployed.

**Declined: the browser-side `Origin` check.** #277's AC asks the canary to send
`Origin: https://explore.…` and assert `Access-Control-Allow-Origin` *for a browser-side
dashboard*. This one is server-side (D071(d)): the browser only ever talks to `explore.`,
and App Engine fetches `/v1` with no `Origin` header, so CORS never applies and
`API_CORS_ORIGINS` is deliberately unchanged. If a browser-side component is ever added,
that story adds the origin and this check.

**The degraded message** appears when a page needs a response the cache does not hold and
cannot get within the render's deadline: an empty cache (a fresh instance that could not
reach the API), or a path filled on a miss (a year or state page, D072) whose fill failed
or was too slow (§12, [cold year links](#cold-year-links-310)). A warm cache keeps serving
the last snapshot it read when the API is down, which is correct under D034: snapshots are
immutable, so the last one is still true.

**Cost posture.** One F1 instance pinned all day uses 24 of the free tier's 28 F1
instance-hours per day, per project, so compute is about $0 (D071(b)); `max_instances: 1`
is a hard cap on instances. Egress is compressed (`compress=True`). The $5 budget and the
kill-switch (§3–§4) pause the app at 100%, well inside the $10/month ceiling. **Residual
exposure:** the origin is DNS-only, so Cloudflare does not stand in front of it, and abuse
could run up egress before the budget's alerts (which lag by hours) fire the kill-switch.
That is one of D071's flip conditions.

**No local plotly.js (#430).** Dash registers dcc's bundled plotly.js as a servable
component-suite file, and the instance answered every request for it itself, compressing
it each time: the largest response the site could be made to send, though no page draws a
graph. The app now registers it by its CDN address only (`ExploreDash._setup_plotlyjs`), so
the script path answers 404 (Flask's default body), as does any component-suite path Dash
never registered. Pointing graphs at the CDN is #432's. The record, from
`curl -sI https://explore.us-presidential-election-center.org/_dash-component-suites/plotly/package_data/plotly.min.js`:

| When | Status | Body |
|---|---|---|
| Before (2026-11-05) | `HTTP/2 200` | `content-length: 4815814`; 1,472,154 bytes with `Accept-Encoding: gzip` |
| After (2026-11-05, deploy run 42028422287 of 62155d2) | `HTTP/2 404` | `content-length: 207`, Flask's default 404 body |

The six component-suite files over 500 KB that #439 listed, none used by any page, are
still served: in the 30 days to 2026-11-13, four got no request and two got four each.
A component-suite file Dash registers but did not install answers 404 since #439. Of the
two files #439's logs showed loading on pages that use neither (#524), dash_table's
`bundle.js` (33,445 bytes) no longer loads on any page: Dash adds it to every index, no page
renders a DataTable, and `app.defer_dash_table_bundle` marks it dynamic, so the path stays
served (200) for a page cached before the change but no page requests it. dcc's
`async-datepicker.js` (213,571 bytes) still loads on every page with a dropdown, a slider or
a chart: despite its name it is a split chunk dcc's own Graph, Dropdown and Slider loaders
require, so it cannot be refused without patching Dash; the home page and the not-found
page load no lazily loaded dcc chunk (`test_dashboard_e2e_suites.py`). The daily canary
checks the plotly.js 404 (#440, above).

**The keep-warm ping (D076).** The refresher GETs the API's `/health` once per refresh
interval (5 min), so the API origin does not scale to zero while the dashboard runs. That is
about 288 requests a day, each also a Worker invocation against the Cloudflare account's
free 100,000 a day (D071 finding 1), and about $0 at the origin under request-based CPU
(`docs/deploy-cloud-run.md`). Each ping logs one `api ping /health <elapsed>s` line, or a
warning `api ping /health failed after …`, never an `api fetch` line, so the `api fetch`
counts in §12 stay `/v1` fills only. To see the pings:

```
gcloud logging read 'resource.type="gae_app" AND textPayload:"api ping"' \
  --project="$PROJECT" --freshness=30m --format='value(timestamp,textPayload)'
```

There is no lever to pause the ping alone: pausing the app (§10) stops it, and the API's
kill-switch leaves it failing once per interval, logged, with no effect on the cache.

## 12. Measuring cold start and load

The MVP target (D071(g)): OG HTML in ≤ 1 s TTFB, and first data in ≤ 3 s for a cold shared
link at 390 px on 10 Mbps / 100 ms.
[`scripts/measure_dashboard_cold_start.py`](../scripts/measure_dashboard_cold_start.py)
measures both from one navigation in a fresh browser context each run, and reports a run
that got the plain-language message instead of data as `degraded`. **When the instance
itself is what is being measured cold, nothing else may reach the server first**: a `curl`
sent ahead of the browser would take the start-up and start the cache fill, and the
browser would measure the second visitor. (A run that measures one year missing from a
warm instance's cache, as in [cold year links](#cold-year-links-310) below, needs only
that year's API paths unfilled on the dashboard, plus the API state it targets; that
section gives the checks.) The server states worth measuring:

- **Warm** (the ordinary case): run it.
- **Dashboard cold**: after a [restart](#restarting-the-instance-to-empty-its-cache)
  (warmup has run, when App Engine sends it), and after a kill-switch un-pause (the
  instance starts from nothing). A deploy's own probes are the new instance's first
  visitors, so a run after a deploy measures an instance that is already up.
- **API origin cold** (any run that needs the origin idle): **pause the dashboard first**
  (§10). A running dashboard pings the origin's `/health` every 5 minutes (D076), so the
  origin never goes idle while it serves, and nothing pauses the ping alone. A
  [restart](#restarting-the-instance-to-empty-its-cache) or a redeploy is no substitute:
  the instance it replaces pinged within the last few minutes. Wait for the origin to go
  idle ("Origin idle" in [cold year links](#cold-year-links-310)), then un-pause. The
  origin then stays cold for one `REFRESH_TTL_S` (5 min) **only if the new instance's
  warmup ran and succeeded**: its refresher then waits that long before its first cycle
  and first ping, and warmup reaches the origin only if the edge lacks `/v1/meta` or
  `/v1/elections`. If warmup failed, the refresher retries and pings at once; if it did
  not run, the refresher starts on the first request and pings at once. App Engine sent
  warmup on both un-pauses #347 watched ([un-pause](#un-pause-re-measured-2026-10-23)), but
  confirm it each time. So confirm the window from the logs
  before each run: since the un-pause, the new instance logged `serving snapshot` (check 2
  of the restart) and no `api ping` line (the query in §11), and the API logged no request.
  An origin-cold run then needs no API deploy, only the pause, the idle wait and the
  un-pause, measured inside that window and before any request of its own wakes the
  origin. So it un-pauses without the [un-pause](#10-redeploy-and-rollback) procedure's two
  `/health` requests, keeps its wait for an instance, and sends the measured navigation in
  place of the operator's `GET /`.
- **API edge cold** for what the dashboard prefetches (`/v1/meta`, `/v1/elections`): the
  order matters, because a running dashboard's refresher re-reads `/v1/meta` through the
  edge every 5 minutes and so refills it. **Pause the dashboard first** (§10), then purge
  the API's Cloudflare cache, wait until the API origin is idle (it scales to zero about
  15 minutes after its last request; check as in [cold year links](#cold-year-links-310),
  since crawlers wake it too), then un-pause and measure the first visitor. The new
  instance's warmup then refetches `/v1/meta` and `/v1/elections` through the purged edge,
  so warmup's fills, not the visitor's, meet the purged edge and any cold origin. A
  visitor who arrives after warmup reads those paths from the in-process cache, and one
  who arrives during it waits for it. A run that pre-pings `/health` (the
  [un-pause](#10-redeploy-and-rollback) procedure) therefore measures a dashboard boot with
  the origin warm, and is not an origin-cold run. A purge alone
  changes nothing a visitor of a prefetched path sees: the dashboard serves those from its
  in-process cache, and the purge does not change `snapshot_version`, so no refetch
  happens. A path filled on a miss (a year page, a state page; D072) is different: its
  first visitor after a restart or a new snapshot reads it through the edge, and possibly
  from a cold origin. That is the case [cold year links](#cold-year-links-310) and
  [cold state links](#cold-state-links-344) measure.

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

### Restarting the instance to empty its cache

The cache lives in the one gunicorn process on the one pinned instance (`app.yaml`). A new
snapshot version replaces it with one holding only the prefetched paths; short of that,
only a new process empties it, and on App Engine that means a new instance. **Delete the
running instance**; `min_instances: 1` makes App Engine start another at once. It needs
`appengine.instances.delete`: an owner, App Engine Admin or App Engine Service Admin. The
deploy account holds Service Admin (§7), but run this as a person.

**Before you start:** no dashboard deploy (`deploy-dashboard.yml`) or API deploy
(`deploy.yml`) is running or about to. Stay clear of the daily canary (`api-canary.yml`): it
probes `explore.`, which spoils a dashboard-cold run, and its uncached `/health` wakes the
API origin, which spoils an origin-cold one. It is scheduled 13:17 UTC but has lately
started 4–8 hours late, so measure before 13:17 UTC, or after
`gh run list --workflow=api-canary.yml` shows today's run completed. A restart cannot
give an origin-cold run: the running dashboard's keep-warm ping (D076) keeps the origin
warm, so use the pause in [API origin cold](#12-measuring-cold-start-and-load) instead.
**Blast radius:** the delete drops whatever the one instance is serving at that moment, and
every visitor's cached responses go with it.

Run these in one shell; the checks below use its variables.

```bash
PROJECT=uspv-explore
STATUS=$(gcloud app describe --project=$PROJECT --format='value(servingStatus)')
VERSION=$(gcloud app versions list --project=$PROJECT --service=default \
  --filter='traffic_split>0' --format='value(id)')
OLD=$(gcloud app instances list --project=$PROJECT --service=default \
  --version="$VERSION" --format='value(id)')
NEW=
if [ "$STATUS" != SERVING ]; then
  echo "app is $STATUS: un-pause first (§10)"
elif [ "$(printf '%s\n' "$VERSION" | grep -c .)" -ne 1 ] \
  || [ "$(printf '%s\n' "$OLD" | grep -c .)" -ne 1 ]; then
  echo "expected one serving version with one instance: VERSION=[$VERSION] OLD=[$OLD]"
else
  RESTART_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if gcloud app instances delete "$OLD" --project=$PROJECT --service=default \
      --version="$VERSION" --quiet; then
    for _ in $(seq 18); do
      NEW=$(gcloud app instances list --project=$PROJECT --service=default \
        --version="$VERSION" --format='value(id)' | grep -vxF "$OLD")
      [ -n "$NEW" ] && break
      sleep 10
    done
    if [ -n "$NEW" ]; then echo "new instance: $NEW"
    else echo "no new instance after 3 minutes: redeploy instead (below)"; fi
  else
    echo "delete refused: redeploy instead (below)"
  fi
fi
```

Then check, before measuring:

1. **Warmup ran** on the new instance, and how long it took:
   ```bash
   gcloud logging read "resource.type=\"gae_app\" AND logName:\"request_log\" \
     AND protoPayload.resource=\"/_ah/warmup\" AND timestamp>=\"$RESTART_TS\"" \
     --project=$PROJECT \
     --format='value(timestamp,protoPayload.latency,protoPayload.wasLoadingRequest)'
   ```
2. **The cache is empty**: since `RESTART_TS`, the new instance (`labels.clone_id`) logged
   one `serving snapshot … (N responses)`, N being `/v1/meta` plus the paths pages
   register in `prefetch=` (2 today, D072), and `api fetch` lines for those paths only:
   ```bash
   gcloud logging read "resource.type=\"gae_app\" AND (textPayload:\"serving snapshot\" \
     OR textPayload:\"api fetch\") AND timestamp>=\"$RESTART_TS\"" \
     --project=$PROJECT --format='value(timestamp,labels.clone_id,textPayload)'
   ```
   App Engine does not guarantee warmup. If neither line appears within about 2 minutes:
   for a cold-year run, send one `GET /` (it starts the refresher, which fills only the
   prefetched paths and pings the API origin at once, so no origin-cold run can follow) and
   note that warmup did not run; for a dashboard-cold run, send nothing, since the measured
   navigation must be the first request.
3. **Immediately before each run**, the year or state you are about to measure was not
   filled since the restart (visitors and crawlers can reach it): the same query with
   `textPayload:"api fetch /v1/elections/<year>"` (a state: `/v1/states/<USPS>`; a state run
   meant to make three fills, also `/v1/elections/<year_max>`, the roster) returns nothing.
   With no restart in this shell, set both variables first:
   `PROJECT=uspv-explore RESTART_TS=$(gcloud app instances list --project=uspv-explore --service=default --format='value(instance.startTime)')`.

Drilled 2026-10-10 UTC (#310): the delete completed at 04:49:37Z, the new instance started
about 1 s later, `/_ah/warmup` ran on it as a loading request (1.67 s), and it was serving
its snapshot 2.5 s after the delete. No visitor request arrived in the gap, so the drill
does not show what one mid-restart would see.

**Other ways, and when to use them.** A **redeploy** (§9) also empties the cache. Use it if
the delete is refused or no new instance appears; pick the measured commit through a tag
in "Use workflow from", since the workflow deploys the selected ref. Its probes request `/`
and its routing callback and read `/v1/meta` from the API directly, so they reach no year
or state path. Like a restart, a redeploy cannot give an origin-cold run: the new
instance's refresher keeps pinging the origin (D076). **The kill-switch pause** (§10) takes
the whole app down, so use it only when the dashboard must stay silent, as in "API origin
cold" and "API edge cold" above, and check for a new instance id after the un-pause.
`gcloud app versions stop` is not available: it needs manual or basic scaling, and this app
uses automatic.

### Cold year links (#310)

What the first reader of a shared `/election/<year>` link waits for, at D072's prefetch
extent (`/v1/meta` and `/v1/elections` only). Since #465 (D092) each election page makes one
fill on a miss: the overview `/v1/elections/{year}`, the states page nothing more after it (the
same path, cold), and the per-capita page `/v1/elections/{year}/per-capita`; the measurements
below predate #465, when one page made both fills. Each render runs under one render deadline
(`MAX_REQUEST_WAIT_S`, 2.0 s), and each fill is capped at `VISITOR_FETCH_TIMEOUT_S` (1.5 s). Three
states, all with the dashboard serving a snapshot and that year missing from its cache
(check 3 above):

- **Edge and origin cold**: a year the edge should not hold (below), with the API origin
  idle. Run this first: its cold start warms the origin for the next state. Since D076 the
  origin is idle only after a pause of the dashboard (§10), and then for at most one
  `REFRESH_TTL_S` after the un-pause, under the conditions
  [API origin cold](#12-measuring-cold-start-and-load) gives; the 2026-10-10 runs below
  predate the ping.
- **Edge cold, origin warm**: another such year, within about 10 minutes of an origin
  request (the previous state's run will do).
- **Edge warm**: the API's Cloudflare cache holds the year. That cache is per data center,
  so warm it only through the dashboard's own fills, never with a `curl` from elsewhere,
  which reaches a different one. Measure years an earlier run filled **with data** (all of
  state 2's; the degraded runs below left nothing at the edge, since their one fill was
  abandoned), after a
  [restart](#restarting-the-instance-to-empty-its-cache), with no API deploy in between
  (the API deploy purges the edge).

Before each run, record `RUN_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)` and check the API's side.
**Edge cold.** A year (`YEAR`) whose `/v1/elections/<year>` the origin has seen no request
under since the last API deploy (`SINCE`, the newest revision's creation time) is not at
the edge, provided the deploy's purge reached the dashboard's data center (`deploy.yml`
verifies only the runner's). That pre-check is sufficient, not necessary: the edge also evicts entries
without a purge, and a request from elsewhere fills a different data center's cache, so a
year that fails it may still miss. The six edge-cold runs below (the first two states) all
failed it (every year had been requested since the last API deploy) and all missed the
edge. **The deciding test is
after the run**: a fill that reached the origin missed the edge (classification, below).
**Origin idle** (origin-cold state only): no request of any kind reached it in the last 15
minutes, and it has logged `Shutting down` since its last one, because scanners hit
non-`/v1/` paths too:

```bash
SINCE=$(gcloud run revisions list --service=usvote-api --project=uspv-api \
  --region=us-west1 --limit=1 --format='value(metadata.creationTimestamp)')
# Edge cold (sufficient, not necessary): nothing printed means cold, if the last purge took.
gcloud logging read 'resource.type="cloud_run_revision" AND
  resource.labels.service_name="usvote-api" AND
  httpRequest.requestUrl:"/v1/elections/'"$YEAR"'" AND timestamp>="'"$SINCE"'"' \
  --project=uspv-api --format='value(timestamp,httpRequest.requestUrl)'
# Origin idle: no request line in the last 15 minutes, and the newest line is Shutting down.
# If nothing prints, widen --freshness until a Shutting down appears with no request after it.
gcloud logging read 'resource.type="cloud_run_revision" AND
  resource.labels.service_name="usvote-api" AND
  (logName:"run.googleapis.com%2Frequests" OR textPayload:"Shutting down")' \
  --project=uspv-api --freshness=20m --format='value(timestamp,httpRequest.requestUrl,textPayload)'
```

Then measure, one run per year (a year is cold once):

```bash
YEAR=1852 STATE="edge cold, origin warm"   # the year and state of this run
uvx --with playwright python scripts/measure_dashboard_cold_start.py \
  "https://explore.us-presidential-election-center.org/election/$YEAR" --label "$STATE"
```

**Classify each run from the logs, never by assumption.** The dashboard's `api fetch` lines
(project `uspv-explore`) say what the instance filled. The API's Cloud Run request log says
whether a fill reached the origin, that is, missed the edge, and a `Starting new instance`
line beside it marks an origin cold start (one before this run's fill, and not beside this
run's own year path, means something else woke the origin first, such as the canary or the
dashboard's own keep-warm ping, whose `/health` this query does not show: discard the run).
Bound both by `RUN_TS`, so an empty result means "nothing since this run" rather than
"nothing in the last few minutes":

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND
  resource.labels.service_name="usvote-api" AND (httpRequest.requestUrl:"/v1/" OR
  textPayload:"Starting new instance") AND timestamp>="'"$RUN_TS"'"' --project=uspv-api \
  --format='value(timestamp,httpRequest.requestUrl,httpRequest.latency,textPayload)'
```

The dashboard's 5-minute `/v1/meta` recheck is answered by the edge, which holds it for up
to 30 days (the Worker's `s-maxage`) unless a purge or eviction clears it first, so it
seldom reaches the origin and does not keep it warm (the first recheck after a purge or an
eviction does). Since D076 the refresher's `/health` ping keeps the origin warm instead.
This query does not show the ping, since it filters on `/v1/`; to see it, query
`httpRequest.requestUrl:"/health"` instead.

**Measured 2026-10-10 UTC, 04:46–05:45Z (#310)**, version `v-59ebc741fcd0-r5-a1`, snapshot
`71b777de…`. In time order: 1836, then state 2, then the 1836 reload, the restart, the
edge-warm runs (04:50Z), then 1880 and 1888.

| State | Year | TTFB (s) | First data, or the message (s) | Outcome | From the logs |
|---|---|---|---|---|---|
| Edge and origin cold | 1836 | 0.13 | 2.58 | **degraded** | origin cold start; the year took 2.27 s at the origin, past the 1.5 s fill cap; per-capita never requested |
| Edge and origin cold | 1880 | 0.23 | 2.67 | **degraded** | origin cold start; the year took 1.76 s at the origin; per-capita never requested |
| Edge and origin cold | 1888 | 0.36 | 2.82 | **degraded** | origin cold start; the year took 2.57 s at the origin; per-capita never requested |
| Edge cold, origin warm | 1852 | 0.15 | 1.62 | data | both paths at the origin, under 10 ms each |
| Edge cold, origin warm | 1876 | 0.14 | 1.61 | data | both paths at the origin, under 10 ms each |
| Edge cold, origin warm | 1840 | 0.15 | 1.59 | data | both paths at the origin, under 10 ms each |
| Edge warm | 1852 | 0.10 | 1.23 | data | no origin request |
| Edge warm | 1876 | 0.22 | 1.27 | data | no origin request |
| Edge warm | 1840 | 0.09 | 1.55 | data | no origin request |

- **Edge warm and edge cold with a warm origin meet D071(g)**, with a second to spare: a
  fill through the edge costs about 0.1–0.2 s, and the origin answered in under 10 ms.
- **A year cold at both the edge and the origin missed it on every run.** A Cloud Run cold
  start put the first fill at 1.8–2.6 s, past `VISITOR_FETCH_TIMEOUT_S`, so the render gave
  up and showed "isn't responding". This is the cost D072 accepted. The first remedy is
  #346's keep-warm ping (D076); #343's backfill is the escalation if #347 finds it is not
  enough, and its seven days did not ([keep-warm residual](#keep-warm-residual-347)).
- **An abandoned fill is not cached.** Reloading 1836 two minutes later, after the state-2
  runs, reached data in 1.63 s, but both of its paths went to the origin again: the edge
  kept nothing from the request the dashboard abandoned. The Worker stores a response only
  after the origin answers (`docs/deploy-cloud-run.md`), and the dashboard had disconnected
  before that; the origin's 200 still landed, so the Worker's pending store was evidently
  dropped with the client. The reload succeeded because the origin was warm by then.
- **How often a link meets a cold origin** depended on traffic: the origin scaled to zero a
  little over 15 minutes after its last request, each of the three times it was watched,
  and the dashboard's own rechecks did not keep it warm. At MVP traffic, many first opens of
  a year might have found it cold; scanners that reach the origin directly also wake it.
  #346 answered this with the keep-warm ping (D076); what it leaves uncovered is #347's.
- **Warmup and swap.** After the restart, `/_ah/warmup` took 1.67 s; on the deploy App
  Engine sent no warmup request, and the deploy probe's `GET /` was the loading request
  (4.34 s, instance start included). Either way the snapshot swap, from the `/v1/meta` fetch
  to `serving snapshot`, took 0.28 s, for two responses. The instance used 106–126 MiB of
  F1's 384 MiB (`gcloud app instances list`, `instance.memoryUsage`).

**Measured 2026-10-11 UTC, 08:38–10:01Z, with the keep-warm ping live (#346)**, version
`v-7ed3bee8be7e-r6-a1` (the PR's branch head, deployed before merge), snapshot `71b777de…`.
App Engine again sent no warmup on the deploy, so the refresher started on the deploy
probe's `GET /` and pinged at once (08:38:19Z). The dashboard logged `api ping /health` every
5 minutes, 0.11–0.17 s each; the API logged a `GET /health` from `usvote-explore` for each,
answered in 3–8 ms, and no `Starting new instance` or `Shutting down` in the window. The 17
pings the API logged came 300.04–300.22 s apart: one `REFRESH_TTL_S` plus that cycle's
`/v1/meta` check, within D076's bound.

Every year had reached the origin since the last API deploy (2026-09-27), so the edge-cold
pre-check selected nothing; the years were the four the origin had gone longest without
(last requested 2026-10-08), each unfilled on the new instance (check 3). Runs about 20
minutes apart:

| State | Year | Run (Z) | TTFB (s) | First data (s) | Outcome | From the logs |
|---|---|---|---|---|---|---|
| Edge cold, origin warm by the ping | 1828 | 08:58:58 | 0.49 | 1.91 | data | both paths at the origin, 4–7 ms; last ping 08:58:19 |
| Edge cold, origin warm by the ping | 1844 | 09:20:15 | 0.23 | 1.70 | data | both paths at the origin, 4–7 ms; last ping 09:18:20 |
| Edge cold, origin warm by the ping | 1860 | 09:40:25 | 0.23 | 1.65 | data | both paths at the origin, 5–11 ms; last ping 09:38:20 |
| Edge cold, origin warm by the ping | 1872 | 10:00:34 | 0.13 | 1.72 | data | both paths at the origin, 4–10 ms; last ping 09:58:21 |

- **Every edge-cold year link met D071(g)** (≤ 3 s to first data), each a fill that missed
  the edge, against a warm origin.
- **Without the ping, runs 2–4 would have met a cold origin.** Apart from the pings, the
  origin's only requests in the window were the runs' own and one scanner `GET /` at
  08:59:18Z, so 20–21 minutes passed before each of those runs with nothing else reaching
  it, past the ~15 minutes after which #310 saw it scale to zero.
- **One `api fetch` line was missing** from the dashboard's log: 1828's year fill, which the
  API's request log shows at 08:59:01.89Z beside its per-capita fill. The other three runs
  logged both lines. Classify from the API's request log, as above, not from the count of
  `api fetch` lines alone.
- What the ping leaves uncovered (un-pause, a start with no warmup and no request, a Cloud
  Run instance replacement) was measured over seven days in #347: see
  [keep-warm residual](#keep-warm-residual-347) below.

### Cold state links (#344)

What the first reader of a shared `/state/<usps>` link waits for, at D072's prefetch extent.
The page fills three paths on a miss, in order: the roster (`/v1/elections/{year_max}`, the
`validate` source the state's code is judged against), then `/v1/states/{usps}` and
`/v1/states/{usps}/per-capita`, under the same render deadline and fill cap as a year page.
The roster is the latest year's own path, shared by every state page, by the state picker
`/states` and by `/election/<year_max>`, so **a state page makes three fills only when it is
the first of those pages after the cache empties**; every later state link makes two. A
three-fill run therefore needs its own [restart](#restarting-the-instance-to-empty-its-cache),
and check 3 on the roster as well as the state.

Since #559 (D105) T7 is a page of its own, `/state/<usps>/per-capita`: the history page fills
the roster and `/v1/states/{usps}` only, and the per-capita page the roster and
`/v1/states/{usps}/per-capita`, so a state link now makes at most two fills, and one once the
roster is cached. Since #619 (D118) T4 is a page of its own too, `/state/<usps>/elections`,
which fills the same two paths as the history page, so a visit to either after the other makes
no fill. The measurement below was taken before both splits and is kept as measured.

The method is [cold year links](#cold-year-links-310)' with state paths in place of year
paths: check 3 on `api fetch /v1/states/<USPS>`, the edge-cold pre-check on
`httpRequest.requestUrl:"/v1/states/<USPS>"`, and each run classified from both logs.

**Measured 2026-10-31 UTC, 03:07–03:16Z (#344)**, version `v-2be50301c093-r15-a1`, snapshot
`37af4064…`, API revision `usvote-api-00010-h7p`. No `/v1/states/` path had reached the
origin since that revision's deploy (2026-10-21), so every state passed the edge-cold
pre-check; the roster had (2026-10-22, from the dashboard). Four restarts (R1–R4): each new
instance was serving its snapshot 2.8–5.6 s after the delete command was issued (the command
itself took 2–3 s to return), after a warmup of 1.30–3.12 s.
The origin was warm from the last keep-warm ping (03:05:51Z) and the runs' own requests: each
restart began the refresher's wait again, so no ping was logged during the runs, and the API
logged no `Starting new instance`.

| Restart | State | Run (Z) | Fills | TTFB (s) | First data (s) | Outcome | From the logs |
|---|---|---|---|---|---|---|---|
| R1 | MT | 03:07:57 | three, state paths edge cold | 0.30 | 1.94 | data | roster from the edge; both state paths at the origin, 16–18 ms |
| R1 | NE | 03:08:43 | two, edge cold | 0.18 | 1.81 | data | both at the origin, 12 ms |
| R1 | NM | 03:09:20 | two, edge cold | 0.20 | 1.75 | data | both at the origin, 6–8 ms |
| R1 | OR | 03:09:56 | two, edge cold | 0.22 | 1.93 | data | both at the origin, 9–13 ms |
| R2 | ID | 03:11:21 | three, state paths edge cold | 0.22 | 1.93 | data | roster from the edge; both state paths at the origin, 6–10 ms |
| R3 | ND | 03:12:45 | three, state paths edge cold | 0.15 | 2.14 | data | roster from the edge; both state paths at the origin, 8–11 ms |
| R4 | NE | 03:14:10 | three, edge warm | 0.14 | 1.60 | data | no origin request |
| R4 | NM | 03:14:46 | two: state path missed the edge, per-capita edge warm | 0.15 | 1.75 | data | `/v1/states/NM` at the origin (9 ms), five minutes after R1 filled it; per-capita from the edge |
| R4 | OR | 03:15:24 | two, edge warm | 0.22 | 1.66 | data | no origin request |

- **Every state link met D071(g)**, with three fills or two, from the edge or past it to a
  warm origin: first data in 1.60–2.14 s. The three-fill runs with edge-cold state
  paths (R1–R3) took 1.93–2.14 s, against 1.75–1.93 s for the two-fill runs with both
  state paths edge cold (R1). **Nothing changes:** the warm extent stays D072's, and #343
  stays deferred (D080).
- **Not measured, on purpose: edge and origin cold** (owner, 2026-10-31). Forcing it
  pauses the public dashboard (§10) for at least the 15 minutes the origin takes to go
  idle ([API origin cold](#12-measuring-cold-start-and-load)). #310's three origin-cold
  year runs each degraded on their first fill to reach the cold origin (1.8–2.6 s there,
  against the 1.5 s `VISITOR_FETCH_TIMEOUT_S`), and a state link's first such fill meets the
  same cap, so it would be expected to degrade the same way: the cost D072 accepts, which
  D076's ping keeps rare (D080).
- **Not measured, on purpose: all three fills missing the edge** (the roster too, as after an
  API deploy's purge). Expected to meet the target, inferred rather than measured: #310 put a
  fill that misses the edge, against a warm origin, at about 0.1–0.2 s, so the roster missing
  too adds at most about that (the roster was already one of the fills here, from the edge) to
  runs that took 1.93–2.14 s here. The limit that decides degraded or
  not is the server's 2.0 s `MAX_REQUEST_WAIT_S` over all three fills, not the browser's 3 s,
  and three such fills sum to well under it. These runs cannot size one miss more finely:
  their timings vary by more than that across states and restarts (NM took 1.75 s with two
  misses in R1 and with one in R4).
- **An entry at the edge can be gone minutes later.** NM's state path missed the edge in R4,
  five minutes after R1 filled it, while its per-capita path hit. Eviction or another data
  center; which is not established. As for years, classify each run from the origin log,
  never from what an earlier run filled.

### Keep-warm residual (#347)

What D076's ping leaves uncovered in real traffic. **Window:** the seven days from #346's
deploy to `main`, `2026-10-11T10:27Z` to `2026-10-18T10:27Z` (`FROM` and `TO` below). In it:
API revisions `usvote-api-00006-df5` and, from 2026-10-16 09:11Z, `00007-w6n` (#330's
deploy, the window's one `deploy.yml` run); six dashboard deploys after the one that opens
the window (`deploy-dashboard.yml`, two from feature branches); no change of the
dashboard's serving status, so no pause or un-pause (the third query below prints nothing
for the window); no kill-switch pause; the daily canary as usual.

**API cold starts.** Every `Starting new instance` line on `usvote-api`, classified by the
first request **that instance** served. Select it by the instance's `labels.instanceId`, not
by time: the request that makes Cloud Run start an instance is logged at its arrival, just
*before* the `Starting new instance` line (the 2026-10-23 pre-ping: request 03:07:06.814Z,
start 03:07:06.851Z), so "the first request after the start" would skip it. The test is the
API's request log; the dashboard's `api ping` line corroborates.

```bash
# Set FROM and TO first (RFC 3339): after an un-pause, FROM just before it and TO now; for #347's window, FROM=2026-10-11T10:27:00Z TO=2026-10-18T10:27:00Z.
: "${FROM:?set FROM to the start of the window to check}" "${TO:?set TO to its end}"
gcloud logging read 'resource.type="cloud_run_revision" AND
  resource.labels.service_name="usvote-api" AND textPayload:"Starting new instance" AND
  timestamp>="'"$FROM"'" AND timestamp<"'"$TO"'"' --project=uspv-api \
  --format='value(timestamp,labels.instanceId,textPayload)'
# For each start's INSTANCE id, the first request that instance served (none: it served none):
gcloud logging read 'resource.type="cloud_run_revision" AND
  resource.labels.service_name="usvote-api" AND logName:"run.googleapis.com%2Frequests" AND
  labels.instanceId="'"$INSTANCE"'"' --project=uspv-api --order=asc --limit=1 \
  --format='value(timestamp,httpRequest.requestUrl,httpRequest.userAgent,httpRequest.latency)'
# Pauses and un-pauses of the dashboard (each is an UpdateApplication):
gcloud logging read 'protoPayload.methodName:"UpdateApplication" AND
  timestamp>="'"$FROM"'" AND timestamp<"'"$TO"'"' --project=uspv-explore \
  --format='value(timestamp,protoPayload.methodName)'
```

| Start (Z) | Reason | First request this instance served | Class |
|---|---|---|---|
| 10-13 03:32:03 | autoscaling, beside a `Shutting down` | none: it shut down at 03:32:13 | served nothing |
| 10-13 03:34:04 | autoscaling, beside a `Shutting down` | dashboard `/health` at 03:35:35, 22 ms | absorbed by the ping |
| 10-16 09:11:12 | deployment rollout (`00007`) | none | excluded: deploy |
| 10-16 09:11:16 | autoscaling, during that rollout | deploy smoke `curl /health` at 09:11:20 | excluded: deploy |
| 10-16 19:50:49 | autoscaling, beside a `Shutting down` | dashboard `/health` at 19:55:37, 29 ms | absorbed by the ping |

**No start was first reached by a visitor's fill.** The three outside the deploy have the
shape of a Cloud Run instance replacement: the old instance shut down as the new one
started, the last request before each was a ping the *old* instance answered in 3–10 ms,
and the new instance's first request, where it served one, was the next ping.

**Gaps between pings.** Pings that reached the API (`GET /health` from `usvote-explore`),
and the dashboard's own `api ping` lines (§11), compared:

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND
  resource.labels.service_name="usvote-api" AND logName:"run.googleapis.com%2Frequests" AND
  httpRequest.requestUrl:"/health" AND httpRequest.userAgent:"usvote-explore" AND
  timestamp>="'"$FROM"'" AND timestamp<"'"$TO"'"' --project=uspv-api --order=asc \
  --limit=5000 --format='value(timestamp,httpRequest.status)'
gcloud logging read 'resource.type="gae_app" AND (textPayload:"api ping" OR
  protoPayload.resource:"/_ah/warmup" OR protoPayload.wasLoadingRequest=true OR
  textPayload:"serving snapshot") AND timestamp>="'"$FROM"'" AND timestamp<"'"$TO"'"' \
  --project=uspv-explore --order=asc --limit=10000 \
  --format='value(timestamp,labels.clone_id,protoPayload.resource,textPayload)'
```

The API logged 2017 pings, all 200; the dashboard logged 2014 that succeeded and one that
failed. Matched line by line (within 20 s), they reconcile: 2014, less the 20:13 ping missing
from the API's request log, plus the 11:06 ping missing from the dashboard's, plus three API lines
with the `usvote-explore` user agent that match no ping the deployed dashboard logged
(10-13 08:12:25, 08:17:26 and 09:00:04; their source is not established). Six intervals
exceeded 7 minutes on one side or the other, and the app was `SERVING` throughout:

| Gap (Z) | Length | Cause |
|---|---|---|
| 10-13 02:02 → 02:11 | 9.2 min | App Engine replaced the instance twice (02:04, 02:06), each with a warmup (5.4 s, 2.2 s); the refresher waits one `REFRESH_TTL_S` after warmup before its first ping |
| 10-13 03:11 → 03:20 | 9.1 min | the same, twice (03:13, 03:15; warmups 7.1 s, 2.4 s) |
| 10-17 15:06 → 15:16 | 9.6 min | the same, once (15:11; warmup 5.1 s) |
| 10-14 17:13 → 17:23 | 10.0 min at the API | the 17:18 ping failed after 15.3 s (a TLS handshake timeout); the dashboard tried on time, and the next ping succeeded |
| 10-14 20:08 → 20:18 | 10.0 min in the API's request log only | log loss: the dashboard logged the 20:13 ping, and the API's own access line shows it served `GET /health` 200 at 20:13:09 |
| 10-17 11:01 → 11:11 | 10.0 min in the dashboard's log only | log loss: the API logged the 11:06 ping |

- **The longest real gap was 10.0 minutes**, under the ~15 minutes after which the origin
  scales to zero, and no API cold start sat beside any gap. The idle window was never reached.
- **The no-warmup case did not occur.** Every dashboard instance outside a deploy started
  with a warmup that succeeded; every deploy's instance started with the deploy probe's
  `GET /` as its loading request and pinged about 4 s later, as soon as it was serving. No instance started with no
  warmup and no request.
- **App Engine replaces the pinned instance now and then**, here five times in three
  episodes, outside any deploy. Each costs one ping interval plus the replacement time,
  as D076 foresaw ("the same holds after App Engine recycles the instance"). An instance
  replaced again within two minutes never pinged.
- **Either side's log can drop a line.** Corroborate a gap from the other side before
  calling it real, as with the missing `api fetch` line in the 2026-10-11 runs above.

**Escalation to #343** (backfill every served year after the swap) is met when the first
request a new `usvote-api` instance serves is a visitor's fill from the dashboard: a `/v1/`
request from `usvote-explore` other than `/v1/meta` and the exact `/v1/elections`, which
warmup and the refresher prefetch. The paths a page fills on a miss are its `on_miss`
declarations (`dashboard/explore/pages/`). Starts caused by a deploy or a measurement run
are excluded; a start after an un-pause is not, since the un-pause procedure pre-pings the
API, so a visitor meeting one means the procedure failed. The first two queries above are
the test; the third lists the window's pauses and un-pauses, so a qualifying start after
one points at the un-pause procedure. **Not met in this window**, so #343 is deferred
(D080). **Run them after every un-pause, with `FROM` just before the un-pause and `TO` now,
and whenever a visitor reports the degraded page, with a window around the report.**

### Un-pause, re-measured (2026-10-23)

#295's sequence, with the [un-pause](#10-redeploy-and-rollback) procedure's pre-ping: the
dashboard paused, the API's Cloudflare cache purged (Purge Everything on the zone), the
origin idle, then `/health` and the un-pause. Dashboard version `v-9285a7370a4b-r14-a1`, API
revision `usvote-api-00010-h7p`, no deploy that day, the canary's last run 9 hours earlier.
Measured by #277's method: `scripts/measure_dashboard_cold_start.py`, one navigation per run
in a fresh browser context, 390 px on 10 Mbps / 100 ms (the script's fixed settings).

| Sequence 1 (Z) | |
|---|---|
| 02:53:59 | paused; the last keep-warm ping had reached the API at 02:51:01 |
| ~02:59 | edge purged |
| 03:06:06 | origin idle: `Shutting down`, no request since 02:51:01 |
| 03:07:06.8 | pre-ping `GET /health`: 200 in 4.64 s, beside a `Starting new instance` (the origin was cold) |
| 03:07:13.06 | un-pause done |
| 03:07:13.6 | `/_ah/warmup` (3.92 s; the app's start took about 2.8 s of it) |
| 03:07:17.20, 17.44 | warmup's `/v1/meta` and `/v1/elections` at the origin, 10 and 51 ms (the edge was purged) |
| 03:07:17.5 | `serving snapshot`, 4.4 s after the un-pause |
| 03:07:20.2 | the measured navigation's `GET /` |
| 03:12:17.8 | first `api ping`, one `REFRESH_TTL_S` after `serving snapshot` |

| Run | TTFB (s) | First data (s) | Outcome |
|---|---|---|---|
| #295's baseline, 2026-10-01 (no pre-ping) | 4.12 | 5.02 | data |
| First after the un-pause, API pre-pinged | 0.17 | 1.04 | data |
| Next two | 0.09 | 0.99–1.00 | data |

- **App Engine sent warmup on the un-pause** (and again in sequence 2), so its refresher
  waited one `REFRESH_TTL_S` before its first ping. The pre-ping kept the origin warm until
  then.
- **Warmup reached the origin.** With the edge purged, its two fills missed the edge, so an
  edge-cold run's warmup wakes the origin by itself; with the pre-ping, the origin was
  already warm and they took 10–51 ms.
- **The measured run did not arrive during boot.** It reached the instance 2.7 s after
  `serving snapshot` (the browser tool's own start delayed it), so it measures the first
  visitor after boot. A visitor who arrives during boot waits for warmup to return, as
  #295 found: in sequence 2 a `GET /` that arrived 13 ms before warmup ended was held
  until it had. That visitor's first data is inferred, not measured: warmup's remainder plus
  about 1 s, so about 5 s after a 3.9 s warmup. D080 accepts up to 6 s.

**Sequence 2** (to measure that visitor) paused at 03:52:48 and un-paused at 03:55:29.7,
2 min 41 s later, after a second purge and a pre-ping (200, 0.28 s). The app reported
`SERVING`, but **App Engine started no instance for 5 min 20 s**: `gcloud app instances
list` stayed empty, all three runs timed out, and requests failed with 500 ("Request was
aborted after waiting too long to attempt to service your request.") or 503. The instance
came up at 04:00:49 (warmup 1.74 s, `serving snapshot` 04:00:51.25). Sequence 1's instance
started 0.5 s after an un-pause that followed a 13-minute pause. What governs the delay is
not established (one sample each), so the un-pause procedure now waits for an instance,
then requests `/health` again before the operator's own `GET /`.

### Chart C1, measured after deploy (2026-11-10, #433)

C1 is the first chart on a page (`/election/<year>`), so its story re-measured D071(g) and
the instance's memory after it shipped. Dashboard version `v-f1a4ef516288-r22-a1` (deploy
run 42781499052 of f1a4ef5), snapshot `37af4064…`, API origin warm by the keep-warm ping
throughout. Measured 08:24–08:28Z, clear of the daily canary (its last run 2026-11-09
22:59Z, the next due 13:17Z), by #277's method: `scripts/measure_dashboard_cold_start.py`
(390 px, 10 Mbps / 100 ms, a fresh browser context each run), with
`--chart "#c1 .main-svg"` for the time until the chart is drawn, which is not a D071(g)
measure.

The first run of each year was that year's first visit on the new instance, so a fill on a
miss: both of its paths missed the API edge and reached the origin, which answered in
6–20 ms. The other runs read the year from the instance's cache.

| Year | First visit: TTFB / first data / chart (s) | From cache: TTFB (s) | From cache: first data (s) | From cache: chart (s) |
|---|---|---|---|---|
| 1824 | 0.18 / 2.13 / 5.76 | 0.16–0.21 | 1.23–1.36 | 4.27–4.53 |
| 1860 | 0.21 / 2.26 / 5.39 | 0.17–0.21 | 1.38–1.43 | 4.51–4.57 |
| 1872 | 0.14 / 2.65 / 5.78 | 0.11–0.15 | 1.77–1.81 | 4.70–4.80 |
| 2016 | 0.22 / **3.15** / 6.27 | 0.10–0.18 | 2.07–2.28 | 5.12–5.43 |
| 2024 | 0.14 / 2.07 / 5.25 | 0.14–0.21 | 1.29–1.44 | 4.33–4.55 |
| 2020 | 0.11 / 2.18 / 5.24 | 0.31 | 1.49 | 4.59 |
| 2012 | 0.23 / 2.16 / 5.19 | 0.15 | 1.36 | 4.49 |
| 2008 | 0.21 / 1.98 / 5.09 | 0.17 | 1.31 | 4.37 |
| 2000 | 0.15 / 2.08 / 5.42 | 0.20 | 1.61 | 4.47 |

Every run reached data, with no degraded page. 2016 had five runs from the cache, the
other years one or two.

- **TTFB met D071(g) on all 26 runs** (0.10–0.31 s, against ≤ 1 s).
- **First data met it on 25 of 26.** The miss was 2016's one first visit, at 3.15 s. A first
  visit took 0.47–0.95 s longer than the same year from the cache, for every year (its two
  fills go out one after the other, logged 0.27–0.45 s apart), so 2016 is not slower to
  fill. It is slower to render: from the cache it is the slowest year (2.07–2.28 s, five
  runs), and its first visit adds the usual fill cost on top. With one sample, how often a
  first visit to 2016 passes 3 s is not established.
- **Slower than a month ago, for reasons not separated.** #346's runs on 2026-10-11 measured
  1860 and 1872 in the same state (edge cold, origin warm by the ping) at 1.65 s and
  1.72 s; their first visits now took 2.26 s and 2.65 s, 0.6–0.9 s more. Between the two
  versions the dashboard gained, among others, the theme choice and toggle, the site
  navigation, the Dash 4.5.0 upgrade and C1, so how much of that C1 adds is not measured.
  No modern year had been measured on `/election/<year>` before.
- **Where a 2016 load from the cache spends its time** (one traced run, first data at
  2.16 s): the routing callback's response (21,314 bytes as transferred, carrying the
  figure in its source store) had arrived by 1.35 s; dcc's dropdown and date-picker
  chunks by 2.11 s; then first data. plotly.js (`cdn.plot.ly/plotly-4.1.1.min.js`,
  1,473,344 bytes as transferred, 1.39 s) finished at 3.57 s, so its request started at
  about 2.18 s, around first data, when the chart mounted (D088). dcc's `async-graph.js`
  finished at 5.02 s, and the chart was drawn at 5.41 s. **So the first data cell does not
  wait for plotly.js**, and from the cache the chart draws 2.9–3.2 s after first data.
- **Request budget held.** The dashboard logged 18 `api fetch` lines for nine years, the
  two fills each (`ELECTION_MISSES` then; one page made both before #465), and no others; no
  warnings and no 5xx.
- **Memory:** the instance used 115.6 MB (110.2 MiB) after the deploy probes (10 requests),
  144.7 MB (138.0 MiB) after the first five years were filled (280 requests) and 147.0 MB
  (140.2 MiB) after nine (496 requests): 38 % of the 384 MB D071 names for F1 (37 % if
  that limit is 384 MiB), so D071's F1 flip condition is not near
  (`gcloud app instances list`, `instance.memoryUsage`, in bytes). #310 measured
  106–126 MiB before any chart.

### Election pages after the split and C3, measured after deploy (2026-11-11, #470)

#465 split the one-election view into three pages, and #435 added C3 to the third, so #470
re-measured D071(g) and the instance's memory on all three:

- the Overview, `/election/<year>`, with C1;
- Results by state, `/election/<year>/states`, with no chart;
- People per electoral vote, `/election/<year>/per-capita`, with C3.

These runs are also #435's own D071(g) re-measure.

Dashboard version `v-74950100c6cb-r25-a1` (deploy run 42987028675 of 7495010, whose
`dashboard/`, `uv.lock` and `pyproject.toml` are those of 5dc5306, the commit that shipped
C3), snapshot `37af4064…` (the baseline's). Since the baseline the API is at 0.8.0 (#431,
deploy run 42978898772, 07:21–07:23Z), whose deploy purged the API edge. The API origin was
warm throughout, by the keep-warm ping (08:59:25Z and 09:04:25Z) and the runs' own fills; it
logged no `Starting new instance` in the window. Measured 09:00–09:11Z, clear of the daily
canary (its last run 2026-11-10 20:28Z, the next due 13:17Z), by #277's method:
`scripts/measure_dashboard_cold_start.py` (390 px, 10 Mbps / 100 ms, a fresh browser context
each run), with `--chart "#c1 .main-svg"` on the Overview and `--chart "#c3 .main-svg"` on
People per electoral vote. The chart column is the time until the chart is drawn, which is
not a D071(g) measure.

**Four instances**, because the Overview and Results by state fill the same path
(`/v1/elections/{year}`), so a first visit to each needs its own instance:

- **A**, the deploy's new instance: a first visit to the Overview and then to People per
  electoral vote for each year (People per electoral vote fills its own path,
  `/v1/elections/{year}/per-capita`); then every year from the cache on all three pages.
- **B**, after a [restart](#restarting-the-instance-to-empty-its-cache) at 09:07:27Z: a
  first visit to Results by state for each year.
- **C** and **D**, after restarts at 09:09:54Z and 09:10:20Z: one first visit to the 2016
  Overview each.

Warmup ran on each restarted instance, as a loading request, in 2.52–2.75 s. Each first
visit was a genuine miss, by the run's `api fetch` lines: its fill is a line logged during
that run, and no earlier line names that path on that instance since it started. On B, C
and D, check 3 also ran before each first visit; on A, whose 18 first visits ran back to
back, it did not, and the lines were read after the runs. Check 3's query as written
(`api fetch /v1/elections/<year>`) is a substring match, so for People per electoral vote
the line to look for is `api fetch /v1/elections/<year>/per-capita`.

**Where each first visit's fill was answered.**

- On A, all 18 fills missed the API edge and reached the origin, which answered in 5–17 ms.
- On B, the fills for 1824, 1860, 2008 and 2012 reached the origin (7–9 ms), and the edge
  answered the other five, though A had filled all nine through it a few minutes before.
  Why those four missed is not established: an eviction, or a different data center, would
  do it.
- C's 2016 fill reached the origin (92 ms), and D's was answered by the edge.

**Overview**

| Year | First visit: TTFB / first data / chart (s) | From cache: TTFB (s) | From cache: first data (s) | From cache: chart (s) |
|---|---|---|---|---|
| 1824 | 0.16 / 1.62 / 4.73 | 0.10–0.12 | 1.03–1.08 | 3.96–4.08 |
| 1860 | 0.10 / 1.59 / 4.50 | 0.09–0.12 | 1.10–1.11 | 3.99–4.12 |
| 1872 | 0.29 / 1.68 / 4.60 | 0.11–0.13 | 1.07–1.11 | 4.01–4.05 |
| 2016 | A 0.14 / 1.59 / 4.49; C 0.14 / 1.58 / 4.62; D 0.11 / 1.53 / 4.46 | 0.09–0.12 | 1.02–1.08 | 4.00–4.08 |
| 2024 | 0.09 / 1.55 / 4.27 | 0.09–0.11 | 1.06–1.09 | 3.92–3.97 |
| 2020 | 0.08 / 1.11 / 4.43 | 0.11–0.12 | 1.05–1.15 | 4.05 |
| 2012 | 0.14 / 1.60 / 4.29 | 0.11–0.17 | 1.06–1.09 | 4.03 |
| 2008 | 0.11 / 1.57 / 4.29 | 0.13–0.14 | 1.08–1.12 | 4.03–4.08 |
| 2000 | 0.10 / 1.55 / 4.30 | 0.12–0.22 | 1.14–1.22 | 4.08–4.26 |

2016 had three first visits (instances A, C and D) and five runs from the cache; each
other year had one first visit and two runs from the cache. 2020's first visit (1.11 s to
first data) is as fast as its runs from the cache, though it was a genuine miss: its one
`/v1/elections/2020` fill is logged at 09:01:45.66Z, during that run, and reached the origin
(7 ms). Why it was faster than the other first visits is not established.

**Results by state**

| Year | First visit: TTFB / first data (s) | From cache: TTFB (s) | From cache: first data (s) |
|---|---|---|---|
| 1824 | 0.12 / 1.70 | 0.10 | 1.16 |
| 1860 | 0.13 / 1.73 | 0.07–**4.90** | 1.18–**5.98** |
| 1872 | 0.13 / 1.92 | 0.11 | 1.54–1.65 |
| 2016 | 0.12 / 1.97 | 0.11–0.12 | 1.83–1.91 |
| 2024 | 0.14 / 1.57 | 0.08–0.14 | 1.14–1.16 |
| 2020 | 0.11 / 1.54 | 0.09–0.13 | 1.11–1.21 |
| 2012 | 0.14 / 1.61 | 0.09–0.12 | 1.14–1.23 |
| 2008 | 0.17 / 1.67 | 0.10–0.14 | 1.12–1.15 |
| 2000 | 0.18 / 1.61 | 0.10 | 1.17–1.22 |

The first visits ran on instance B, and the runs from the cache on A, where the Overview's
first visit had already filled the path.

**People per electoral vote**

| Year | First visit: TTFB / first data / chart (s) | From cache: TTFB (s) | From cache: first data (s) | From cache: chart (s) |
|---|---|---|---|---|
| 1824 | 0.09 / 1.54 / 4.35 | 0.09–0.11 | 1.12–1.13 | 4.04–4.06 |
| 1860 | 0.09 / 1.60 / 4.37 | 0.13–0.14 | 1.07–1.12 | 3.96–4.08 |
| 1872 | 0.12 / 1.54 / 4.41 | 0.09–0.12 | 1.02–1.08 | 4.03 |
| 2016 | 0.12 / 1.61 / 4.48 | 0.09–0.12 | 1.05–1.06 | 4.06–4.11 |
| 2024 | 0.10 / 1.55 / 4.45 | 0.10–0.16 | 1.08–1.12 | 4.14–4.15 |
| 2020 | 0.11 / 1.56 / 4.50 | 0.09–0.10 | 1.07–1.09 | 4.13–4.18 |
| 2012 | 0.12 / 1.57 / 4.45 | 0.12–0.14 | 1.04–1.07 | 4.05–4.09 |
| 2008 | 0.07 / 1.53 / 4.30 | 0.09–0.10 | 1.04 | 4.08–4.12 |
| 2000 | 0.10 / 1.56 / 4.19 | 0.08–0.11 | 1.03–1.06 | 4.03–4.09 |

Every run on all three pages reached data, with no degraded page.

**Whether D071(g) held, per page:**

- **Overview:** TTFB on 32 of 32 runs (0.08–0.29 s), first data on 32 of 32 (1.11–1.68 s on
  a first visit, 1.02–1.22 s from the cache).
- **People per electoral vote:** TTFB on 27 of 27 (0.07–0.16 s), first data on 27 of 27
  (1.53–1.61 s on a first visit, 1.02–1.13 s from the cache).
- **Results by state:** TTFB on 26 of 27, first data on 26 of 27.
  - The miss was 1860's second run from the cache: TTFB 4.90 s, first data 5.98 s.
  - App Engine's request log shows the app served that request in 8.4 ms, logged at
    09:03:11.11Z; the run before it was logged at 09:03:04.36Z and served in 8.9 ms.
  - So the 4.9 s was spent outside the app's own handling of the request: on the measuring
    machine, its network, or Google's front end, on the way in or out, which these logs do
    not separate. It is still a miss by D071(g)'s measure.
  - The other 26 runs took 0.07–0.18 s to first byte and 1.11–1.97 s to first data. Among
    them, 2016 and 1872 were the page's slowest years, on a first visit and from the cache.

**Against the baseline** (the Overview, year by year, against the 2026-11-10 record above):

| Year | First visit: first data (s), 2026-11-10 → now | From cache: first data (s), 2026-11-10 → now |
|---|---|---|
| 1824 | 2.13 → 1.62 | 1.23–1.36 → 1.03–1.08 |
| 1860 | 2.26 → 1.59 | 1.38–1.43 → 1.10–1.11 |
| 1872 | 2.65 → 1.68 | 1.77–1.81 → 1.07–1.11 |
| 2016 | 3.15 → 1.53–1.59 | 2.07–2.28 → 1.02–1.08 |
| 2024 | 2.07 → 1.55 | 1.29–1.44 → 1.06–1.09 |
| 2020 | 2.18 → 1.11 | 1.49 → 1.05–1.15 |
| 2012 | 2.16 → 1.60 | 1.36 → 1.06–1.09 |
| 2008 | 1.98 → 1.57 | 1.31 → 1.08–1.12 |
| 2000 | 2.08 → 1.55 | 1.61 → 1.14–1.22 |

- **First visits:** first data is faster on every year, by 0.41–1.07 s on the eight years
  other than 2016 (0.41–0.97 s without 2020's fast first visit, above). 2016's three first
  visits took 1.53–1.59 s, against that record's one at 3.15 s, so 2016 is no longer near
  the target.
- **From the cache:** first data is faster on every year, and each year's slowest run now is
  faster than its fastest then: 1.02–1.22 s in all, against that record's 1.23–2.28 s.
  2016's five runs took 1.02–1.08 s, against 2.07–2.28 s.
- **Why, not separated.** Between the two versions the dashboard gained #464's bar of
  earlier and later election links, #465's split and C3, and the API moved to 0.8.0. The
  likeliest cause is the split, which moved Results by state (T2 and its four filters) and
  People per electoral vote (T6) off the Overview (D092), but none of the four was measured
  on its own.
- The chart is drawn 2.86–3.05 s after first data on a run from the cache, about as in the
  baseline.

**Request budget held.** The dashboard logged 38 `api fetch` lines from A's first line
(08:59:24Z) to the last run's fill (09:10:36Z), by check 2's query (§12) bounded to that
window, counting its `api fetch` lines:

- each instance's two prefetched paths (`/v1/meta` and `/v1/elections`) as it started;
- on A, 18 fills, one for each first visit, and one `/v1/meta` recheck by the refresher
  (09:04:25Z);
- on B, nine fills, one for each Results by state page reached cold;
- on C and D, one fill each.

The runs from the cache made no fills. Neither did Results by state reached through a path
the Overview had filled. The app logged no warnings and no 5xx. After the window, D logged
two more: its refresher's `/v1/meta` recheck (09:15:24Z) and a fill of `/v1/elections/1872`
(09:16:26Z, reaching the origin in 11 ms) that no run made. The refresher fills only the
prefetched paths, so a page request from outside the measurement made it.

**Memory.** Instance A, from `gcloud app instances list` (`instance.memoryUsage`, in bytes):

- 115.1 MB (109.8 MiB), 30 % of the 384 MB D071 names for F1 (29 % of 384 MiB), after the
  deploy probes (5 requests);
- 135.4 MB (129.1 MiB), 35 % (34 %), after the first five years were filled on the Overview
  and People per electoral vote (180 requests);
- 143.7 MB (137.1 MiB), 37 % (36 %), after all nine years on all three pages (1,307
  requests).

The peak is below the baseline's 147.0 MB peak, so D071's F1 flip condition is not near.

**Decision rule (#470).**

- One Results by state run missed D071(g), so the rule filed a follow-up investigation,
  #482, which links #470 and carries these runs as its evidence.
- Every 2016 first visit to the Overview was below 2.8 s, so that trigger did not fire.
- Memory is far from F1's limit.

### Chart C2 on the elections index, measured after deploy (2026-11-12, #434)

C2 (#434, D096) is the first chart on `/elections`, and it fills N1
(`/v1/elections/summary`) on the first visit after a start, so its story re-measured D071(g)
on that page (D096(f)). No earlier record measures `/elections`, so there is no baseline.

Dashboard version `v-e86957ade9ef-r26-a1` (deploy run 43134835942 of e86957a, the merge of
#487, which shipped C2), snapshot `37af4064…`, API 0.8.0, with no API deploy since the
#470 record. The API origin was warm throughout, by the keep-warm ping (its last `/health`
before the runs at 01:33:05Z); it logged no `Starting new instance` in the window. Measured
01:34–01:38Z, clear of the daily canary (its last run 2026-11-11 20:13Z, the next due
13:17Z), by #277's method: `scripts/measure_dashboard_cold_start.py` (390 px, 10 Mbps /
100 ms, a fresh browser context each run), with `--chart "#c2 .main-svg"`. The chart column
is the time until the chart is drawn, which is not a D071(g) measure.

**Three instances**, one first visit each:

- **A**, the deploy's new instance: a first visit, then six runs from the cache. The deploy's
  probes request `/`, not `/elections`, so they fill nothing N1 needs.
- **B** and **C**, after [restarts](#restarting-the-instance-to-empty-its-cache) at
  01:35:45Z and 01:36:57Z: one first visit each. Warmup ran on each as a loading request
  (1.93 s and 2.03 s), and each was serving its snapshot 2–3 s after the delete.

Each first visit was a genuine miss: its `api fetch /v1/elections/summary` line was logged
during that run (01:34:13Z, 01:36:08Z, 01:37:21Z), and no earlier line names that path on
that instance. On B and C, check 3 ran before the run. The API's request log shows no
`/v1/` request in the window, so the edge answered all three fills.

| Run | Instance | TTFB (s) | First data (s) | Chart (s) |
|---|---|---|---|---|
| First visit | A | 0.23 | 1.64 | 4.84 |
| First visit | B | 0.20 | 1.63 | 4.22 |
| First visit | C | 0.16 | 1.60 | 5.09 |
| From the cache (6 runs) | A | 0.09–0.20 | 1.11–1.31 | 4.32–4.66 |

Every run reached data, with no degraded page and no C2 section degraded.

- **TTFB met D071(g) on 9 of 9 runs** (0.09–0.23 s, against ≤ 1 s).
- **First data met it on 9 of 9** (1.60–1.64 s on a first visit, 1.11–1.31 s from the
  cache, against ≤ 3 s). A first visit took about 0.3–0.5 s longer than a run from the
  cache: N1's one fill.
- The chart is drawn 2.6–3.5 s after first data on a first visit, and 3.1–3.5 s after it
  from the cache, a little later than C1 and C3 on the election pages (2.86–3.05 s from
  the cache, in #470's record).

**Request budget held.** The dashboard logged 9 `api fetch` lines from A's first line
(01:33:04Z) to C's fill (01:37:21Z): each instance's two prefetched paths (`/v1/meta` and
`/v1/elections`) as it started, and one N1 fill for each first visit. The runs from the
cache, and a filter change (`?pv=1`, checked by hand after the runs), made none. The app
logged no warnings and no 5xx.

**Memory** (`gcloud app instances list`, `instance.memoryUsage`, in bytes):

- A: 115.2 MB (109.9 MiB), 30 % of the 384 MB D071 names for F1, after the deploy probes
  (5 requests); 130.1 MB (124.0 MiB), 34 %, after its seven runs (131 requests).
- C: 123.7 MB (118.0 MiB), 32 %, after its first visit and the hand checks below
  (85 requests).

The peak is below #470's 143.7 MB, so D071's F1 flip condition is not near.

**Checked by hand on the deployed version**, after the runs:

- At 390 px (light and dark) and 1280 px, the page has no sideways scroll; every year's tick
  and point label shows, and the dashed line and the points differ without color.
- The companion table has one row per served year (1824–2024). 1824 reads Andrew Jackson,
  99 of 261, 37.9 %, no majority, did not take office, and sits below the line; 1876
  (185 of 369, 50.1 %) and 2000 (271 of 538, 50.4 %) sit just above it; 2016 is 304 of 538;
  1868 and 1872 read 214 of 294 and 286 of 366, counted votes of electors appointed. Each
  year links to its `/election/<year>` and each name to its candidate page.
- `?pv=1` narrows the list of elections and leaves C2's table unchanged (D096(b)).
- Both downloads are offered: the Electoral College leaders and the elections (CSV).
- §9's checks: `/election/%2531824` is a 404 with `noindex`, `/election/%31824` a 200, and
  the plotly.js path a 404.

### Charts C4 and C5 on the elections index, measured after deploy (2026-11-13, #436)

C4 and C5 (#436, D100) follow the list of elections on `/elections`, and the first visit after
a start now fills two paths: N1 (`/v1/elections/summary`) and N2 (`/v1/elections/states`,
about 680 KB uncompressed). D100(i) asked for D071(g) re-measured on that page, with N2's
cold fill and the instance's memory, not only an edge-hit render. The baseline is
[C2's record](#chart-c2-on-the-elections-index-measured-after-deploy-2026-11-12-434), the
same page before N2.

Dashboard version `v-7dd6a1a5dc3d-r27-a1` (deploy run 43382427516 of 7dd6a1a, the merge of
#497, which shipped C4 and C5; the deploy also carried #437's headline metrics and #484's
chart-rules hardening, merged since C2's record), snapshot `37af4064…`, API 0.9.0 (#428's
deploy, 2026-11-12). The API origin was warm throughout, by the keep-warm ping (07:06:02Z,
07:11:03Z, 07:16:03Z); it logged one `Starting new instance` at 07:11:45Z, before the runs.
Measured 07:17–07:20Z, clear of the daily canary (its last run 2026-11-12 20:51Z, the next due
13:17Z), by #277's method: `scripts/measure_dashboard_cold_start.py` (390 px, 10 Mbps /
100 ms, a fresh browser context each run), with `--chart "#c5 .main-svg"`, the lower of the
two new charts. The chart column is the time until C5 is drawn, which is not a D071(g)
measure.

**Three instances**, one first visit each:

- **A**, the deploy's new instance: a first visit, then six runs from the cache. The deploy's
  probes request `/`, not `/elections`, so they fill neither path.
- **B** and **C**, after [restarts](#restarting-the-instance-to-empty-its-cache) at
  07:18:42Z and 07:19:27Z: one first visit each. Warmup ran on each as a loading request
  (1.94 s and 2.77 s), and each was serving its snapshot (2 responses) 4–5 s after the
  delete.

Each first visit was a genuine miss on both paths: its `api fetch /v1/elections/summary` and
`api fetch /v1/elections/states` lines were logged during that run (07:17:09Z, 07:19:17Z,
07:19:53Z), and no earlier line names either path on that instance. On B and C, check 3 ran
before the run. The API's request log shows no `/v1/` request in the window, so the edge
answered all six fills.

| Run | Instance | TTFB (s) | First data (s) | C5 drawn (s) |
|---|---|---|---|---|
| First visit | A | 0.14 | 1.56 | 4.32 |
| First visit | B | 0.29 | 1.65 | 4.18 |
| First visit | C | 0.16 | 1.59 | 3.98 |
| From the cache (6 runs) | A | 0.08–0.20 | 1.05–1.59 | 3.75–3.98 |
| `?state=GA`, from the cache | C | 0.18 | 1.06 | 3.80 |

Every run reached data, with no degraded page, no section degraded and no state choice
withheld.

- **TTFB met D071(g) on 10 of 10 runs** (0.08–0.29 s, against ≤ 1 s).
- **First data met it on 10 of 10** (1.56–1.65 s on a first visit, 1.05–1.59 s from the
  cache, against ≤ 3 s), within C2's record (1.60–1.64 s on a first visit) although each
  first visit now makes two fills.
- **N2's cold fill.** The fetch line is logged as a fill starts. On each first visit N2's
  started 0.07–0.08 s after N1's, so N1 took that long from the edge. The routing
  callback that makes both fills took 0.47 s (A), 0.27 s (B) and 0.26 s (C) on the server,
  against 0.08–0.16 s for the same render from the cache, so the two fills together added
  0.1–0.4 s, of which N2's is the remainder after N1's 0.07–0.08 s. Both were edge hits;
  a fill that reached the origin was not measured.
- C5 is drawn 2.4–2.8 s after first data on a first visit and 2.4–2.8 s from the cache,
  earlier than C2 was in its record (2.6–3.5 s), with three charts now on the page.

**Request budget held.** The dashboard logged 14 `api fetch` lines from A's start
(07:06:02Z) to C's fills (07:19:53Z): each instance's two prefetched paths as it started, A's
two later `/v1/meta` refreshes, and one N1 and one N2 fill for each first visit. The runs from
the cache, and the one-state run, made none. The app logged no warnings and no 5xx.

**Memory** (`gcloud app instances list`, `instance.memoryUsage`, in bytes):

- A: 119.1 MB (113.6 MiB), 31 % of the 384 MB D071 names for F1, after the deploy probes
  (8 requests); 138.9 MB (132.5 MiB), 36 %, after its seven runs (141 requests), with N1
  and N2 cached.
- C: 127.1 MB (121.3 MiB), 33 %, after its first visit and the one-state run
  (39 requests).

The peak is below #470's 143.7 MB, so D071's F1 flip condition is not near.

**Checked on the deployed version** with a scripted browser at 390 px, in light and dark,
after the runs: all states, `?state=GA` and `?state=AK` each draw C4 and C5 with every year's
tick (51 each) and no sideways scroll; C5's band reads "This dataset's popular-vote figures
begin in 1976"; Georgia's titles name it and its markers read "No electors: took no part"
(C4, 1864), "Legislature chose the electors" and "Took no part" (C5); Alaska's table has its
17 rows from 1960. §9's checks: `/election/%2531824` is a 404 with `noindex`,
`/election/%31824` a 200, and the plotly.js path a 404.

### Year on the x-axis of C2, C4 and C5, measured after deploy (2026-11-18, #558)

#558 (D104) put election year on a numeric x-axis for C2, C4 and C5 and moved C2's point
labels to the hover. It changes no data read, so `/elections` still fills N1 and N2 on the
first visit after a start; D104(h) asked for D071(g) re-measured on that page. The baseline
is [C4 and C5's record](#charts-c4-and-c5-on-the-elections-index-measured-after-deploy-2026-11-13-436),
the same page with the year axis down the side.

Dashboard version `v-96c6a7758039-r31-a1` (deploy run 44291060865 of 96c6a77, the merge of
#572, which shipped the change), snapshot `37af4064…`, API 0.9.0, with no API deploy since
C4 and C5's record. The API origin was warm throughout, by the keep-warm ping (10:59:17Z,
11:04:17Z, 11:04:57Z); it logged no `Starting new instance` in the window. Measured
11:05–11:08Z, clear of the daily canary (its last run 2026-11-17 21:47Z, the next due
13:17Z), by #277's method: `scripts/measure_dashboard_cold_start.py` (390 px, 10 Mbps /
100 ms, a fresh browser context each run), with `--chart "#c5 .main-svg"`, as in the
baseline. The chart column is the time until C5 is drawn, which is not a D071(g) measure.

**Three instances**, one first visit each:

- **A**, the deploy's new instance: a first visit, then six runs from the cache. The deploy's
  probes request `/`, not `/elections`, so they fill neither path.
- **B** and **C**, after [restarts](#restarting-the-instance-to-empty-its-cache) at
  11:06:40Z and 11:07:13Z: one first visit each. Warmup ran on each as a loading request
  (2.05 s and 2.43 s), and each was serving its snapshot (2 responses) 4–5 s after the
  delete.

Each first visit was a genuine miss on both paths: its `api fetch /v1/elections/summary` and
`api fetch /v1/elections/states` lines were logged during that run (11:05:52Z, 11:06:59Z,
11:07:32Z), and no earlier line names either path on that instance. On B and C, check 3 ran
before the run. The API's request log shows no `/v1/` request in the window, so the edge
answered all six fills.

| Run | Instance | TTFB (s) | First data (s) | C5 drawn (s) |
|---|---|---|---|---|
| First visit | A | 0.13 | 1.50 | 3.99 |
| First visit | B | 0.14 | 1.50 | 3.99 |
| First visit | C | 0.15 | 1.17 | 3.97 |
| From the cache (6 runs) | A | 0.09–0.16 | 0.99–1.20 | 3.77–4.24 |
| `?state=GA`, from the cache | C | 0.10 | 1.06 | 3.71 |

Every run reached data, with no degraded page, no section degraded and no state choice
withheld.

- **TTFB met D071(g) on 10 of 10 runs** (0.09–0.16 s, against ≤ 1 s).
- **First data met it on 10 of 10** (1.17–1.50 s on a first visit, 0.99–1.20 s from the
  cache, against ≤ 3 s), within the baseline (1.56–1.65 s and 1.05–1.59 s).
- **The fills.** The routing callback that makes both fills took 0.28 s (A), 0.27 s (B) and
  0.28 s (C) on the server, against 0.06–0.20 s for the same render from the cache, as in
  the baseline (0.26–0.47 s). N2's fill started 0.07–0.09 s after N1's. Both were edge hits.
- C5 is drawn 2.5–2.8 s after first data on a first visit and 2.6–3.2 s from the cache,
  in line with the baseline (2.4–2.8 s); the flipped charts draw no slower.

**Request budget held.** The new version logged 12 `api fetch` lines from A's start
(11:04:57Z) to C's fills (11:07:32Z): each instance's two prefetched paths as it started,
and one N1 and one N2 fill for each first visit. The runs from the cache, the one-state run and the checks below made none. The app
logged no warnings and no 5xx.

**Memory** (`gcloud app instances list`, `instance.memoryUsage`, in bytes):

- A: 139.4 MB (132.9 MiB), 36 % of the 384 MB D071 names for F1, after its seven runs
  (140 requests), with N1 and N2 cached.
- B: 126.0 MB (120.2 MiB), 33 %, after its first visit (19 requests).
- C: 135.7 MB (129.4 MiB), 35 %, after its first visit, the one-state run and the checks
  below (329 requests).

The peak is below #470's 143.7 MB, so D071's F1 flip condition is not near.

**Checked on the deployed version** with a scripted browser, after the runs, at 360 px and
390 px, in light and dark, for all states, `?state=GA`, `?state=SC` and `?state=AK` (16
renders): no sideways scroll; C2, C4 and C5 each draw the year ticks 1840, 1880, 1920, 1960
and 2000 along the bottom, at least 6 px apart; no point or bar draws text; every tick,
axis title, band label and key entry sits inside the width with none over another. C2
draws 51 points, and the hover on the last reads "2024: Donald J. Trump" with its electoral
share. C5's band reads "Shaded: years before this dataset's popular-vote figures begin in
1976", and C4 and C5's titles name the chosen state. §9's checks: `/election/%2531824` is a
404 with `noindex`, `/election/%31824` a 200, and the plotly.js path a 404.

### Chart C7 on the state history page, measured after deploy (2026-11-19, #560)

#560 (D106) added C7, a state's electors appointed per election, and its companion table to
`/state/<usps>`. C7 reads the `/v1/states/{usps}` body the page already filled, so the page's
fills on a miss are unchanged since #559: the roster (`/v1/elections/{year_max}`) and
`/v1/states/{usps}`. #560 asked for D071(g) re-measured on that page after deploy, since it
gains a chart. The baseline is [cold state links](#cold-state-links-344), measured before
#559 moved T7 off the page, when a first visit also filled the per-capita path.

Dashboard version `v-4ff38dcfa97d-r32-a1` (deploy run 44470276123 of 4ff38dc, the merge of
#580, after #576 shipped C7), snapshot `37af4064…`, API 0.9.0, revision
`usvote-api-00013-czh`. The API origin was warm throughout: it started at 07:22:47Z, before
the window, and the keep-warm ping reached it at 07:23, 07:28, 07:33 and 07:38Z; it logged
no other `Starting new instance` in the window. Measured 07:38–07:42Z, clear of the daily
canary (its last run 2026-11-18 21:27Z, the next due 13:17Z), by #277's method:
`scripts/measure_dashboard_cold_start.py` (390 px, 10 Mbps / 100 ms, a fresh browser
context each run), with `--chart "#c7 .main-svg"`. The chart column is the time until C7 is
drawn, which is not a D071(g) measure.

**Three instances:**

- **A**, the deploy's new instance, up since 06:13Z. A visitor had already opened
  `/state/AL` (06:14Z), so A held the roster, and its first visit to `/state/GA` made one
  fill. Six runs from the cache followed.
- **B** and **C**, after [restarts](#restarting-the-instance-to-empty-its-cache) at
  07:39:23Z and 07:40:30Z: one first visit each, making both fills (`/state/TX` on B,
  `/state/CA` on C). Warmup ran on each as a loading request (1.32 s and 1.27 s), and each
  was serving its snapshot (2 responses) 2.7–3.8 s after the delete command was issued. B
  then had a second state, `/state/NY`, with the roster cached; C had three runs from the
  cache.

Each first visit was a genuine miss: check 3 found no earlier fill of its state (or, on B
and C, of the roster) on that instance, and each run's `api fetch` lines were logged during
it. Every state path missed the edge and reached the warm origin (8–9 ms there), and each
roster fill was an edge hit.

| Run | Instance | Fills | TTFB (s) | First data (s) | C7 drawn (s) |
|---|---|---|---|---|---|
| GA, first visit | A | one (state) | 0.23 | 1.31 | 4.15 |
| TX, first visit | B | two (roster, state) | 0.19 | 1.24 | 4.10 |
| NY, roster cached | B | one (state) | 0.12 | 1.18 | 3.86 |
| CA, first visit | C | two (roster, state) | 0.13 | 1.59 | 3.99 |
| GA, from the cache (6 runs) | A | none | 0.10–0.17 | 1.06–1.17 | 3.81–3.92 |
| CA, from the cache (3 runs) | C | none | 0.14–0.22 | 1.06–1.12 | 3.72–3.88 |

Every run reached data, with no degraded page and C7's section never unavailable.

- **TTFB met D071(g) on 13 of 13 runs** (0.10–0.23 s, against ≤ 1 s).
- **First data met it on 13 of 13** (1.18–1.59 s with a fill, 1.06–1.17 s from the cache,
  against ≤ 3 s), within the baseline's two-fill runs (1.75–1.93 s), which filled one more
  path.
- **The fills.** The routing callback took 0.24 s with one fill (A's GA) and 0.15 s (B's
  NY), and 0.25 s (B) and 0.32 s (C) with two, against 0.11–0.12 s for the same render from
  the cache.
- C7 is drawn 2.4–2.9 s after first data on every run, with a fill or from the cache, as
  C5 is on `/elections` (2.5–3.2 s in [#558's record](#year-on-the-x-axis-of-c2-c4-and-c5-measured-after-deploy-2026-11-18-558)).

**Request budget held.** Besides the refresher's `/v1/meta` cycles, the version logged only
the expected fills in the window: GA on A; on B its two prefetched paths, the roster, TX
and NY; on C its two prefetched paths, the roster and CA; and GA, TX and AK from the checks
below. The runs from the cache made none. The app logged no warnings and no 5xx since the
deploy.

**Memory** (`gcloud app instances list`, `instance.memoryUsage`, in bytes):

- A: 139.4 MB (132.9 MiB), 36 % of the 384 MB D071 names for F1, after its seven runs
  (163 requests since 06:13Z).
- B: 125.3 MB (119.5 MiB), 33 %, after its two runs (37 requests).
- C: 131.9 MB (125.8 MiB), 34 %, after its four runs and the checks below (293 requests).

The peak is below #470's 143.7 MB, so D071's F1 flip condition is not near.

**Checked on the deployed version** with a scripted browser, after the runs, at 360 px and
390 px, in light and dark, for GA, TX and AK (12 renders): no sideways scroll; C7 is drawn
on every render, with the year ticks 1840, 1880, 1920, 1960 and 2000 along the bottom, at
least 23 px apart at 360 px; no tick, axis title, key entry or label sits over another or
outside the width. GA's and TX's charts carry the "No electors: took no part" marker for
their zero allotments, and AK's carries none. §9's checks: `/election/%2531824` is a 404
with `noindex`, `/election/%31824` a 200, and the plotly.js path a 404.

### The elections index and its two subpages, measured after deploy (2026-11-19, #562)

#562 (D107) split `/elections` into an index and two subpages: the list and its averages stay
on `/elections`, C2 moves to `/elections/majority`, and C4 and C5 move to
`/elections/over-time`. Each page prefetches `/v1/elections` and fills N1
(`/v1/elections/summary`) on a miss, and N2 is no longer read by any of them, so a first
visit after a start makes one fill, which then serves all three pages. #562 asked for D071(g)
re-measured on each of the three pages after deploy. The baseline is
[#558's record](#year-on-the-x-axis-of-c2-c4-and-c5-measured-after-deploy-2026-11-18-558),
the one page that carried all three charts and filled both N1 and N2.

Dashboard version `v-ac6cd8a8788e-r33-a1` (deploy run 44532819061 of ac6cd8a, the merge of
#583), snapshot `37af4064…`, API 0.9.0, revision `usvote-api-00013-czh`, with no API deploy
since 2026-11-12. The API origin was warm throughout: it answered `/health` from 13:15Z to
13:30Z and logged no `Starting new instance` in the window. Measured 13:29–13:32Z, by #277's
method: `scripts/measure_dashboard_cold_start.py` (390 px, 10 Mbps / 100 ms, a fresh browser
context each run), with `--chart "#c2 .main-svg"` on `/elections/majority` and
`--chart "#c5 .main-svg"` on `/elections/over-time` (one run with `#c4`). The chart column is
the time until that chart is drawn, which is not a D071(g) measure. The window falls after
the daily canary's 13:17Z slot, which runs late: its last run was 2026-11-18 21:27Z and
today's had not started when the window closed, so no canary request fell inside it.

**Three instances**, one first visit each, each on a different page:

- **A**, the deploy's new instance, up since 13:25:00Z: a first visit to `/elections`, then
  three runs from the cache on each of the three pages. The deploy's probes request `/`, so
  A held no N1 before the run.
- **B** and **C**, after [restarts](#restarting-the-instance-to-empty-its-cache) at
  13:30:10Z and 13:31:06Z: a first visit to `/elections/majority` on B and to
  `/elections/over-time` on C, then runs from the cache. Warmup ran on each as a loading
  request (2.20 s and 2.12 s), and each was serving its snapshot (2 responses) about 4 s
  after the delete command was issued.

Each first visit was a genuine miss: check 3 found no N1 fill on that instance before the
run, and its `api fetch /v1/elections/summary` line was logged during it (13:29:16Z,
13:30:38Z, 13:31:27Z). A's and C's fills were edge hits; B's reached the warm origin (10 ms
there).

| Run | Instance | TTFB (s) | First data (s) | Chart drawn (s) |
|---|---|---|---|---|
| `/elections`, first visit | A | 0.15 | 1.10 | (no chart) |
| `/elections/majority`, first visit | B | 0.12 | 1.54 | 3.80 (C2) |
| `/elections/over-time`, first visit | C | 0.17 | 1.57 | 3.90 (C5) |
| `/elections`, from the cache (4 runs) | A, B | 0.11–0.15 | 1.00–1.09 | (no chart) |
| `/elections/majority`, from the cache (5 runs) | A, B | 0.08–0.20 | 0.99–1.13 | 3.59–4.58 (C2) |
| `/elections/over-time`, from the cache (6 runs) | A, C | 0.08–0.67 | 0.99–1.53 | 3.63–4.14 (C5), 3.66 (C4) |

Every run reached data, with no degraded page and no section unavailable.

- **TTFB met D071(g) on 18 of 18 runs** (0.08–0.67 s, against ≤ 1 s). The one above 0.20 s
  was A's first run of `/elections/over-time` (0.67 s), whose first data (1.53 s) was also
  the slowest from the cache; the next two runs there were 0.09 s and 0.11 s.
- **First data met it on 18 of 18** (1.10–1.57 s on a first visit, 0.99–1.53 s from the
  cache, against ≤ 3 s), within the baseline (1.17–1.50 s on a first visit, 0.99–1.20 s
  from the cache).
- **The fill.** The routing callback that makes the fill took 0.17 s (A, `/elections`),
  0.29 s (B, `/elections/majority`) and 0.17 s (C, `/elections/over-time`) on the server,
  against 0.013–0.032 s for the same renders from the cache; the baseline's two-fill
  callback took 0.27–0.28 s, and 0.06–0.20 s from the cache.
- C2 is drawn 2.3 s after first data on B's first visit and 2.5–3.6 s from the cache; C5
  2.3 s after first data on C's first visit and 2.6 s from the cache, against the
  baseline's 2.5–3.2 s for C5.

**Request budget held.** The new version logged only the expected fills: each instance's
two prefetched paths as it started, and one N1 fill for each first visit. The runs from the
cache and the checks below made none. The app logged no warnings and no 5xx since the
deploy.

**Memory** (`gcloud app instances list`, `instance.memoryUsage`, in bytes):

- A: 134.2 MB (128.0 MiB), 35 % of the 384 MB D071 names for F1, after its ten runs (169
  requests).
- B: 122.6 MB (116.9 MiB), 32 %, after its four runs (65 requests).
- C: 124.1 MB (118.3 MiB), 32 %, after its four runs (65 requests).

The peak is below #470's 143.7 MB, so D071's F1 flip condition is not near.

**Checked on the deployed version** with a scripted browser, after the runs, at 360 px and
390 px, in light and dark, on each of the three pages (12 renders): no sideways scroll, and
none of the three pages' unavailable notes rendered. C2, C4 and C5 are drawn on every render,
each with the year ticks 1840, 1880, 1920, 1960 and 2000 along the bottom, at least 12 px
apart at 360 px (C5's, the closest); no chart text sits over other chart text or outside
the width. C2 draws 51 points and C4 51 bars. §9's checks: `/election/%2531824` is a 404
with `noindex`, `/election/%31824` a 200, and the plotly.js path a 404.

### C2's three shares on `/elections/majority`, measured after deploy (2026-11-20, #564)

#564 (D108) extends C2 from the leader's electoral share alone to three shares per election:
the electoral share, the popular-vote share and the hybrid score, which is the project's
proposal. The popular-vote and hybrid marks are drawn for the years MIT covers. The page
still makes one fill on a miss, N1 (`/v1/elections/summary`), so the change is in what C2
draws, not in what the page reads. #564 asked for D071(g) to be re-measured on
`/elections/majority` after deploy. The baseline is that page in
[#562's record](#the-elections-index-and-its-two-subpages-measured-after-deploy-2026-11-19-562).

Dashboard version `v-3afc923d4261-r34-a1` (deploy run 44654389151 of 3afc923, the merge of
#591), snapshot `37af4064…`, API 0.9.0, revision `usvote-api-00013-czh`, with no API deploy
since 2026-11-12. The API origin was warm throughout: the dashboard's keep-warm ping reached
its `/health` every few minutes from 01:26Z on, and it logged no `Starting new instance` in
the window. Measured 01:42–01:44Z, by #277's method: `scripts/measure_dashboard_cold_start.py`
(390 px, 10 Mbps / 100 ms, a fresh browser context each run) with `--chart "#c2 .main-svg"`.
The chart column is not a D071(g) measure. The previous day's canary had completed at 21:38Z
and the next was not due until 13:17Z, so no canary request fell inside the window.

**Two instances**, each after a
[restart](#restarting-the-instance-to-empty-its-cache): B at 01:41:35Z and C at 01:42:49Z.
The deploy's own instance could not give a first visit: a browser visit at 01:37:43Z, before
the window, had already filled N1 on it. Warmup ran on each as a loading request (2.23 s and
5.16 s), and each was serving its snapshot (2 responses) 4–14 s after the delete command was
issued. Each first visit was a genuine miss: check 3 found no N1 fill on that instance
before the run, and its `api fetch /v1/elections/summary` line was logged during it
(01:42:14Z, 01:43:31Z). Both fills were edge hits: the origin logged no `/v1/` request
after 01:37:49Z.

| Run | Instance | TTFB (s) | First data (s) | Chart drawn (s) |
|---|---|---|---|---|
| First visit | B | 0.23 | 1.64 | 5.16 |
| First visit | C | 0.16 | 1.54 | 3.93 |
| From the cache (4 runs) | B | 0.15–0.23 | 1.04–1.11 | 3.73–3.86 |
| From the cache (3 runs) | C | 0.15–0.17 | 1.01–1.08 | 3.71–3.78 |

Every run reached data, with no degraded page and no section unavailable.

- **TTFB met D071(g) on 9 of 9 runs** (0.15–0.23 s, against ≤ 1 s).
- **First data met it on 9 of 9** (1.54–1.64 s on a first visit, 1.01–1.11 s from the
  cache, against ≤ 3 s). The baseline was 1.54 s on a first visit and 0.99–1.13 s from the
  cache.
- **The fill.** The routing callback that makes the fill took 0.33 s (B) and 0.34 s (C) on
  the server, against 0.29 s in the baseline, and 0.021–0.040 s for the same render from
  the cache (baseline 0.013–0.032 s).
- **C2 drawn.** From the cache it took 3.71–3.86 s, inside the baseline's 3.59–4.58 s. C's
  first visit drew it in 3.93 s (baseline 3.80 s). B's took 5.16 s, 3.5 s after first data,
  the only run outside that spread. Its server side was no slower than C's (fill 0.33 s,
  first data 1.64 s), so the extra time was spent in the browser after first data, which
  includes fetching plotly.js from its CDN (D087/D088). This record does not separate that
  further.

**Request budget held.** Each instance logged only the expected fills: the two prefetched
paths as it started, and one N1 fill for its first visit. The runs from the cache made none.
The app logged no warnings and no 5xx since the deploy.

**Memory** (`gcloud app instances list`, `instance.memoryUsage`, in bytes): C, 132.3 MB
(126.2 MiB), 34 % of the 384 MB D071 names for F1, after its four runs (65 requests). This is
below #562's peak of 134.2 MB, so the three shares did not move D071's F1 flip condition.

**Checked on the deployed version** with a scripted browser, after the runs, at 360 px and
390 px, in light and dark (4 renders): no sideways scroll, and the page's unavailable note
did not render. C2 is drawn on every render, with the year ticks 1840, 1880, 1920, 1960 and
2000, and 51 electoral-share points, 13 popular-vote triangles, 13 hybrid stars and the 2
years the popular-vote and electoral leaders differed in MIT's range. §9's checks:
`/election/%2531824` is a 404 with `noindex`, `/election/%31824` a 200, and the plotly.js
path a 404.

### The chart refinements and the year filter, measured after deploy (2026-11-20, #593 and #596)

#593 (D109) refines C2, C4, C5 and C7 and colors each chart by measure. #596 (D110) adds the
year filter to `/elections/majority` and `/elections/over-time`, narrows C2's hybrid
crossbar to 10 px and shortens C5's value-axis ticks (`~s`). Neither changes what a page
reads: each subpage still makes one fill on a miss, N1 (`/v1/elections/summary`), and the
filter is applied to that response, so a filtered view needs no other fill. Each issue asked
for D071(g) to be re-measured on both subpages after deploy. Both shipped in one deploy, so
one record covers both. The baselines are
[#562's record](#the-elections-index-and-its-two-subpages-measured-after-deploy-2026-11-19-562)
and [#564's](#c2s-three-shares-on-electionsmajority-measured-after-deploy-2026-11-20-564).

Dashboard version `v-b042b4602c60-r35-a1` (deploy run 44777229480 of b042b46, the merge of
#597), snapshot `37af4064…`, API 0.9.0, revision `usvote-api-00013-czh`, with no API deploy
since 2026-11-12. The API origin was warm throughout and logged no `Starting new instance`
in the window. Measured 16:59–17:02Z, by #277's method: `scripts/measure_dashboard_cold_start.py`
(390 px, 10 Mbps / 100 ms, a fresh browser context each run), with `--chart "#c2 .main-svg"`
on `/elections/majority` and `--chart "#c5 .main-svg"` on `/elections/over-time` (one run
with `#c4`). The chart column is not a D071(g) measure. The filtered runs used
`?year_from=1960` and, on B, `?year_from=1900&year_to=1980`. The previous day's canary had
completed at 21:38Z and today's had not started when the window closed, so no canary request
fell inside it.

**Three instances**, one first visit each:

- **A**, the deploy's new instance, up since 16:58:04Z: a first visit to
  `/elections/over-time`, then runs from the cache on both pages, filtered and not. The
  deploy's probes request `/`, so A held no N1 before the run.
- **B** and **C**, after [restarts](#restarting-the-instance-to-empty-its-cache) at
  17:00:06Z and 17:01:06Z: a first visit to `/elections/majority` on B, and to the filtered
  link `/elections/over-time?year_from=1960` on C (a shared filtered link, the case #596
  adds), then runs from the cache. Warmup ran on each as a loading request (2.27 s and
  2.31 s), and each was serving its snapshot (2 responses) about 4 s after the delete
  command was issued.

Each first visit was a genuine miss: check 3 found no N1 fill on that instance before the
run, and its `api fetch /v1/elections/summary` line was logged during it (16:59:17Z,
17:00:32Z, 17:01:26Z). A's and B's fills were edge hits; C's reached the warm origin (45 ms
there), the only `/v1/` request the origin logged in the window.

| Run | Instance | TTFB (s) | First data (s) | Chart drawn (s) |
|---|---|---|---|---|
| `/elections/over-time`, first visit | A | 0.24 | 1.19 | 3.92 (C5) |
| `/elections/majority`, first visit | B | 0.23 | 1.29 | 4.09 (C2) |
| `/elections/over-time?year_from=1960`, first visit | C | 0.21 | 1.57 | 4.01 (C5) |
| `/elections/majority`, from the cache (4 runs) | A, B | 0.11–0.18 | 1.04–1.08 | 3.66–3.84 (C2) |
| `/elections/majority`, filtered, from the cache (5 runs) | A, B, C | 0.11–0.21 | 1.02–1.09 | 3.56–3.70 (C2) |
| `/elections/over-time`, from the cache (4 runs) | A, B, C | 0.13–0.24 | 0.98–1.12 | 3.56–3.67 (C5), 3.69 (C4) |
| `/elections/over-time`, filtered, from the cache (4 runs) | A, C | 0.09–0.32 | 1.02–1.16 | 3.51–3.88 (C5) |

Every run reached data, with no degraded page and no section unavailable.

- **TTFB met D071(g) on 20 of 20 runs** (0.09–0.32 s, against ≤ 1 s).
- **First data met it on 20 of 20** (1.19–1.57 s on a first visit, 0.98–1.16 s from the
  cache, against ≤ 3 s), within the baselines (1.54–1.64 s on a first visit, 0.99–1.53 s
  from the cache).
- **The fill.** The routing callback that makes the fill took 0.17 s (A), 0.28 s (B) and
  0.38 s (C, filtered) on the server, against 0.17–0.34 s in the baselines, and
  0.010–0.090 s for the renders from the cache, filtered or not (baselines 0.013–0.040 s;
  the two above 0.04 s were A's first two renders of `/elections/majority`, 0.057 s and
  0.090 s).
- **Charts drawn** in 3.51–3.88 s from the cache and 3.92–4.09 s on a first visit, inside
  the baselines' 3.59–4.58 s; a filtered view drew no slower than the full span.

**Request budget held.** The new version logged only the expected fills: each instance's two
prefetched paths as it started, and one N1 fill for each first visit. The runs from the
cache, filtered or not, made none. The app logged no warnings and no 5xx since the deploy.

**Memory** (`gcloud app instances list`, `instance.memoryUsage`, in bytes): C, 124.7 MB
(118.9 MiB), 32 % of the 384 MB D071 names for F1, after its runs and the checks below (86
requests). This is below #562's peak of 134.2 MB, so D071's F1 flip condition is not near.

**Checked on the deployed version** with a scripted browser, after the runs, at 360 px and
390 px, in light and dark, on `/elections/majority` and `/elections/over-time` each with no
filter and with `?year_from=1960`, and on `/state/TX` for C7 (20 renders): no sideways
scroll, no unavailable note, and on every chart no text over other text or outside the
chart's width.

- **C2** draws 51 electoral-share points (17 when filtered to 1960 on), 13 popular-vote
  triangles, 13 hybrid crossbars (`line-ew`, size 10) and 2 different-winner asterisks.
- **C4** draws 51 bars (17 filtered); **C5** 13 bars, with value ticks 0, 50M, 100M and
  150M.
- **Year ticks** read 1840–2000 on the full span and 1980, 2000 when filtered; C7 reads
  1840–2000.
- **The filtered page's** `og:url` names the filter and its canonical link is query-free
  (D110(b)).
- **§9's checks:** `/election/%2531824` is a 404 with `noindex`, `/election/%31824` a 200,
  and the plotly.js path a 404.

### Chart C10 on the state history page, measured after deploy (2026-11-22, #582)

#582 (D113) added C10, a state's total popular vote per election, in its own card below C7 on
`/state/<usps>`. Like C7, it reads the `/v1/states/{usps}` body the page already filled, so
the page's fills on a miss are unchanged: the roster (`/v1/elections/{year_max}`) and
`/v1/states/{usps}`. #582 asked for D071(g) re-measured on that page after deploy. The
baseline is
[#560's record](#chart-c7-on-the-state-history-page-measured-after-deploy-2026-11-19-560).

Dashboard version `v-17433b9ff088-r37-a1` (deploy run 45001265605 of 17433b9, the merge of
#605), snapshot `b09807fa…`, API 0.10.0, revision `usvote-api-00014-q75` (deployed
01:11Z that day, so the snapshot differs from the baseline's). The API origin was warm
throughout: the keep-warm ping reached it every 5 minutes before the window (the last at
08:08 and 08:09Z), and it logged no `Starting new instance` in the window. Measured
08:10–08:13Z, clear of the daily canary (its last run 2026-11-21 20:07Z, the next due
13:17Z), by #277's method: `scripts/measure_dashboard_cold_start.py` (390 px, 10 Mbps /
100 ms, a fresh browser context each run), with `--chart "#c10 .main-svg"` (one run with
`#c7`). The chart column is the time until that chart is drawn, which is not a D071(g)
measure.

**Three instances:**

- **A**, the deploy's new instance, up since 08:09:07Z (the deploy probe's `GET /` was its
  loading request; no warmup). It held only the two prefetched paths, so its first visit,
  `/state/GA`, made both fills. Five runs from the cache followed, then `/state/NY` with the
  roster cached, and one more GA run timing C7.
- **B** and **C**, after [restarts](#restarting-the-instance-to-empty-its-cache) at
  08:11:19Z and 08:11:50Z: one first visit each, making both fills (`/state/TX` on B,
  `/state/CA` on C). Warmup ran on each (1.94 s and 1.69 s), and each was serving its
  snapshot (2 responses) about 3.5 s after the delete command was issued. B then had
  `/state/NY` with the roster cached; C had three runs from the cache.

Each first visit was a genuine miss: no earlier fill of its state (or of the roster, for a
two-fill run) on that instance, and each run's `api fetch` lines were logged during it.
Every roster fill was an edge hit. Of the state paths, GA (A) and NY (B, 42 s after A
filled it) were edge hits; NY (A), TX and CA missed the edge and reached the warm origin
(61, 17 and 16 ms there).

| Run | Instance | Fills | TTFB (s) | First data (s) | Chart drawn (s) |
|---|---|---|---|---|---|
| GA, first visit | A | two (roster, state) | 0.16 | 1.56 | 4.34 (C10) |
| NY, roster cached | A | one (state) | 0.18 | 1.58 | 4.08 (C10) |
| TX, first visit | B | two (roster, state) | 0.18 | 1.52 | 4.13 (C10) |
| NY, roster cached | B | one (state) | 0.18 | 1.17 | 3.97 (C10) |
| CA, first visit | C | two (roster, state) | 0.18 | 1.56 | 4.22 (C10) |
| GA, from the cache (5 runs) | A | none | 0.16–0.20 | 1.12–1.56 | 3.83–4.07 (C10) |
| GA, from the cache | A | none | 0.16 | 1.18 | 4.09 (C7) |
| CA, from the cache (3 runs) | C | none | 0.14–0.19 | 1.04–1.08 | 3.80–3.84 (C10) |

Every run reached data, with no degraded page and no section unavailable.

- **TTFB met D071(g) on 14 of 14 runs** (0.14–0.20 s, against ≤ 1 s).
- **First data met it on 14 of 14** (1.17–1.58 s with a fill, 1.04–1.56 s from the cache,
  against ≤ 3 s). The baseline's first visits took 1.24–1.59 s; from the cache it took
  1.06–1.17 s, and so did these runs but one (A's third GA run, 1.56 s, among four at
  1.12–1.23 s).
- **The fills.** The routing callback took 0.26–0.47 s with two fills and 0.13–0.38 s with
  one (NY on A, 0.38 s, went to the origin; NY on B, 0.13 s, was an edge hit), against
  0.15–0.32 s in the baseline; from the cache 0.07–0.19 s on A and 0.04 s on C (baseline
  0.11–0.12 s).
- **C10 is drawn 2.5–2.8 s after first data** on every run, with a fill or from the cache,
  as C7 was in the baseline (2.4–2.9 s). C7 drawn at 4.09 s sits at the top of the
  baseline's 3.72–4.15 s.

**Request budget held.** Besides the refresher's `/v1/meta` cycles, the version logged only
the expected fills in the window: on A the roster, GA and NY; on B its two prefetched paths,
the roster, TX and NY; on C its two prefetched paths, the roster and CA; and GA, TX and AK
from the checks below. The runs from the cache made none. The app logged no warnings and no
5xx since the deploy.

**Memory** (`gcloud app instances list`, `instance.memoryUsage`, in bytes): C, 133.0 MB
(126.8 MiB), 35 % of the 384 MB D071 names for F1, after its runs and the checks below (292
requests). This is below #470's peak of 143.7 MB, so D071's F1 flip condition is not near.

**Checked on the deployed version** with a scripted browser, after the runs, at 360 px and
390 px, with the browser's color scheme light and dark, for GA, TX and AK (12 renders): no
sideways scroll, no unavailable note, and C7 and C10 drawn on every render with no text over
other text or outside the chart's width. Both charts read the year ticks 1840, 1880, 1920,
1960 and 2000, at least 15 px apart edge to edge at 360 px (21 px at 390 px). C10's short
value ticks (D113) read 0, 2M, 4M for GA; 0, 5M, 10M for TX; and 0, 100k, 200k, 300k for
AK. §9's checks: `/election/%2531824` is a 404 with `noindex`, `/election/%31824` a 200,
and the plotly.js path a 404.

### Chart C9 and T1's N1 columns on `/elections`, measured after deploy (2026-11-23, #563)

#563 (D116) added C9, the number of candidates who received electoral votes in each
election, to the list of elections, above T1, and appended to T1 four of N1's fields, the
electoral and popular-vote margins and a page-only Recipients column. The page already read
N1 (`/v1/elections/summary`) on a miss, so its fills are unchanged: one N1 fill on the first
visit after a start. What changed is what that render does with N1: it checks N1's
recipient rows and reconciles each year's count with `candidate_count` over every served
year before the filters, then draws C9 and the new cells. #563 asked for D071(g)
re-measured on `/elections` after deploy. The baseline is that page in
[#562's record](#the-elections-index-and-its-two-subpages-measured-after-deploy-2026-11-19-562).

Dashboard version `v-b688875e2ec2-r38-a1` (deploy run 45257702244 of b688875, the merge of
#627), snapshot `b09807fa…`, revision `usvote-api-00014-q75`, as in
[#582's record](#chart-c10-on-the-state-history-page-measured-after-deploy-2026-11-22-582)
(the snapshot differs from the baseline's). The API origin was warm throughout: the
keep-warm ping reached its `/health` at 20:16Z and 20:19Z, and its last `Starting new
instance` was at 20:05Z, before the window. Measured 20:20–20:21Z, before the day's
canary had started (its last run 2026-11-22 20:22Z), by #277's method:
`scripts/measure_dashboard_cold_start.py` (390 px, 10 Mbps / 100 ms, a fresh browser
context each run) with `--chart "#c9 .main-svg"`. The chart column is the time until C9 is
drawn, which is not a D071(g) measure.

**Two instances:**

- **A**, the deploy's new instance, up since 20:19:16Z. The deploy's probes request `/`, so
  A held only the two prefetched paths, and its first visit made the N1 fill. Three runs
  from the cache followed.
- **B**, after a [restart](#restarting-the-instance-to-empty-its-cache) at 20:20:39Z.
  Warmup ran as a loading request (1.85 s), and B was serving its snapshot (2 responses)
  about 4 s after the delete command was issued. One first visit, then three runs from the
  cache.

Each first visit was a genuine miss: no N1 fill on that instance before the run, and its
`api fetch /v1/elections/summary` line was logged during it (20:20:03Z on A, 20:21:03Z on
B). A's fill reached the warm origin (32 ms there); B's was an edge hit.

| Run | Instance | TTFB (s) | First data (s) | Chart drawn (s) |
|---|---|---|---|---|
| `/elections`, first visit | A | 0.23 | 1.65 | 4.41 (C9) |
| `/elections`, first visit | B | 0.16 | 1.55 | 4.11 (C9) |
| `/elections`, from the cache (3 runs) | A | 0.13–0.17 | 0.99–1.10 | 3.61–3.80 (C9) |
| `/elections`, from the cache (3 runs) | B | 0.09–0.21 | 0.97–1.08 | 3.60–3.65 (C9) |

Every run reached data, with no degraded page and no section unavailable.

- **TTFB met D071(g) on 8 of 8 runs** (0.09–0.23 s, against ≤ 1 s).
- **First data met it on 8 of 8** (1.55–1.65 s on a first visit, 0.97–1.10 s from the
  cache, against ≤ 3 s). From the cache this is the baseline's 1.00–1.09 s; a first visit
  is about 0.5 s slower than the baseline's 1.10 s.
- **The fill.** The routing callback that makes the fill took 0.68 s (A, origin) and
  0.47 s (B, edge hit) on the server, against the baseline's 0.17 s; from the cache it took
  0.023–0.036 s, against 0.013–0.032 s. The first visit's extra time is in the render that
  first reads N1 (the reconciliation over every served year, C9 and the new cells), not in
  the renders from the cache.
- **C9 is drawn 2.5–2.8 s after first data** on every run, as C2, C5, C7 and C10 are in
  their records (2.3–3.6 s).

**Request budget held.** Besides the refresher's cycles and pings, the version logged only
the expected fills: each instance's two prefetched paths as it started, and one N1 fill for
each first visit. The runs from the cache and the checks below made none. The app logged no
warnings and no 5xx since the deploy.

**Memory** (`gcloud app instances list`, `instance.memoryUsage`, in bytes): B, 129.0 MB
(123.1 MiB), 34 % of the 384 MB D071 names for F1, after its runs and the checks below (141
requests). This is below #470's peak of 143.7 MB, so D071's F1 flip condition is not near.

**Checked on the deployed version** with a scripted browser, after the runs, at 360 px and
390 px, with the browser's color scheme light and dark (4 renders): no sideways scroll, no
unavailable note, C9 drawn with 51 bars and T1 with 51 rows, the year ticks 1840, 1880,
1920, 1960 and 2000 at least 18 px apart edge to edge at 360 px (24 px at 390 px), and no
chart text outside the width. §9's checks: `/election/%2531824` is a 404 with `noindex`,
`/election/%31824` a 200, and the plotly.js path a 404.

### The `/states` history table, measured after deploy (2026-11-26, #641)

#641 (D123) put *State histories compared* first on `/states`: every state's four history
figures, read from N2 (`/v1/elections/states`), which the page declares in `on_miss` beside
the roster (`/v1/elections/{year_max}`). D072's prefetch extent is unchanged, so the first
visit to `/states` after a start makes two fills, the roster and N2, and runs every state's
N2 rows through the shared collapse and `history_figures`. #641 asked for D071(g)
re-measured on `/states` after deploy. No earlier record measured `/states`, so there is no
baseline; D123(a)'s flip condition (move N2 to the prefetch) is a run over D071(g), or the
section degrading on a warm origin.

Dashboard version `v-9501f27607a6-r42-a1` (deploy run 45808432684 of 9501f27, the merge of
#647), snapshot `b09807fa…`, revision `usvote-api-00014-q75`. The API origin was warm
throughout: the keep-warm ping reached its `/health` at 11:12:54Z and 11:14:10Z, and it
logged no `Starting new instance` from 10:50Z on. Measured 11:14–11:16Z, before the day's
canary (its last run 2026-11-25 22:35Z), by #277's method:
`scripts/measure_dashboard_cold_start.py` (390 px, 10 Mbps / 100 ms, a fresh browser
context each run) with `--chart "#states-history"`. That column is the time until the
history table is visible, which is not a D071(g) measure.

**Two instances:**

- **A**, the deploy's new instance, up since 11:14:05Z. The deploy's probes request `/`, so
  A held only the two prefetched paths, and its first visit made both fills. Three runs
  from the cache followed.
- **B**, after a [restart](#restarting-the-instance-to-empty-its-cache) at 11:15:08Z.
  Warmup ran as a loading request (1.91 s), and B was serving its snapshot (2 responses)
  about 4 s after the delete command was issued. One first visit, then three runs from the
  cache.

Each first visit was a genuine miss: no fill on that instance before the run, and its
`api fetch /v1/elections/2024` and `api fetch /v1/elections/states` lines were logged
during it (11:14:50Z on A, 11:15:29Z on B). A's two fills reached the warm origin (12 ms
for the roster, 94 ms for N2); B's were edge hits (no origin request).

| Run | Instance | TTFB (s) | First data (s) | Table visible (s) |
|---|---|---|---|---|
| `/states`, first visit | A | 0.24 | 1.63 | 1.65 |
| `/states`, first visit | B | 0.30 | 1.62 | 1.64 |
| `/states`, from the cache (3 runs) | A | 0.15–0.18 | 1.03–1.08 | 1.08–1.12 |
| `/states`, from the cache (3 runs) | B | 0.15–0.26 | 1.02–1.13 | 1.08–1.15 |

Every run reached data, with the history section rendered and no degraded page.

- **TTFB met D071(g) on 8 of 8 runs** (0.15–0.30 s, against ≤ 1 s).
- **First data met it on 8 of 8** (1.62–1.63 s on a first visit, 1.02–1.13 s from the
  cache, against ≤ 3 s). The table is visible within 0.06 s of first data on every run:
  it renders in the same response, with no chart to wait for.
- **The fills.** The routing callback that makes both fills took 0.36 s (A, origin) and
  0.22 s (B, edge hits) on the server; from the cache it took 0.029–0.041 s. A first visit
  costs about 0.6 s over a render from the cache, as on `/elections` after #563.
- **D123(a)'s flip condition is not met**: no run exceeded D071(g), and the section never
  degraded on the warm origin. N2 stays filled on a miss.

**Request budget held.** Besides the refresher's cycles and pings, the version logged only
the expected fills: each instance's two prefetched paths as it started, and the roster and
N2 for each first visit. The runs from the cache made none. The checks below made two more,
`/v1/states/GA` and `/v1/states/TX`, from the visits to those state pages. The app logged
no warnings and no 5xx since the deploy.

**Memory** (`gcloud app instances list`, `instance.memoryUsage`, in bytes): B, 129.9 MB
(123.9 MiB), 34 % of the 384 MB D071 names for F1, after its runs (57 requests). This is
below #470's peak of 143.7 MB, so D071's F1 flip condition is not near.

**Checked on the deployed version** with a scripted browser, after the runs, at 360 px and
390 px, with the browser's color scheme light and dark (4 renders): no sideways scroll, no
section-unavailable sentence, the table with 51 rows, each state's name linked to
`/state/<usps>`, and the download link present. AC2 on the live site: Georgia's row reads
50, 1824, 49 of 50, +7, and Texas's 43, 1848, 43 of 43, +36, each equal to the four figures
on `/state/GA` and `/state/TX`. §9's checks: `/election/%2531824` is a 404 with `noindex`,
`/election/%31824` a 200, and the plotly.js path a 404.
