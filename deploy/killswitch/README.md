# Budget kill-switch

A tiny Cloud Function that **pauses** a service when billing spend crosses a threshold:
the hard cost cap neither Cloud Run nor App Engine provides natively
([D034](../../.claude/specs/decisions.md), [D071](../../.claude/specs/decisions.md)). It's
a backstop; at free-tier traffic it should never fire.

**One source, one deployment per target.** Each deployment lives in its target's own GCP
project and is triggered only by that project's own budget topic. The dashboard's function
runs as a service account holding a role in `uspv-explore` only, and that IAM boundary makes
one half of "pause only the dashboard" structural: the dashboard's function cannot pause the
API. The other half, that dashboard spend cannot trip the API's budget, is configuration
(the API budget's project filter), checked by readback in
[`docs/deploy-dashboard.md`](../../docs/deploy-dashboard.md) §6.

| Target | Project | Budget → topic | Action | Un-pause |
|---|---|---|---|---|
| `cloud_run` (the API) | `uspv-api` | `uspv budget`, filtered to `uspv-api` → `budget-alerts` | `max_instance_count = 0` on `usvote-api` | re-run the **Deploy (Cloud Run)** workflow (re-sets `--max-instances=1`) |
| `app_engine` (the dashboard) | `uspv-explore` | the dashboard budget, filtered to `uspv-explore` → `dashboard-budget-alerts` | app serving status → `USER_DISABLED` | REST `PATCH` below, or the console's **Enable application** |

**Flow:** Billing Budget → Pub/Sub topic → this function → once spend ≥
`PAUSE_AT_FRACTION` of the budget, pause the target. Below the threshold it logs and does
nothing. Resolve the cause before un-pausing.

**Never `max_instances: 0` on App Engine.** The `app.yaml` reference says zero *disables the
setting*, which removes the cap rather than stopping the app. Disabling the application
stops its instances and its serving.

## Configuration

`KILLSWITCH_TARGET` is **required** (no default), and the whole configuration is validated
when the function loads (the target, its required env, and that both numbers are finite and
positive), so a misconfigured deployment fails to start rather than failing
at the moment it should pause something.

| Env | Targets | Notes |
|---|---|---|
| `KILLSWITCH_TARGET` | both | `cloud_run` or `app_engine` |
| `GCP_PROJECT` | both | the target's project |
| `CLOUD_RUN_REGION`, `CLOUD_RUN_SERVICE` | `cloud_run` | required |
| `APP_ENGINE_OPERATION_TIMEOUT_S` | `app_engine` | optional, default `120`; keep it below the function's `--timeout` (the deploy below sets `300s`; the gen2 default is 60 s) |
| `PAUSE_AT_FRACTION` | both | optional, default `1.0` (pause at 100%) |

The budget must use a **specified amount**. A budget set to "last period's spend" reads $0
on a new project, and the function logs `MISCONFIGURED` and never pauses.

## Deploy: the API (`cloud_run`)

```
PROJECT=uspv-api ; REGION=us-west1 ; SERVICE=usvote-api

# 1. Pub/Sub topic the budget publishes to.
gcloud pubsub topics create budget-alerts --project="$PROJECT"

# 2. The function (2nd-gen, Pub/Sub-triggered). Its runtime SA needs run.admin on the service.
gcloud functions deploy budget-killswitch --project="$PROJECT" \
  --gen2 --runtime=python312 --region="$REGION" \
  --source=deploy/killswitch --entry-point=budget_killswitch \
  --trigger-topic=budget-alerts \
  --set-env-vars="KILLSWITCH_TARGET=cloud_run,GCP_PROJECT=${PROJECT},CLOUD_RUN_REGION=${REGION},CLOUD_RUN_SERVICE=${SERVICE},PAUSE_AT_FRACTION=1.0"

# Deployed before #283? That revision predates KILLSWITCH_TARGET, and the current source
# refuses to start without it: redeploy with the full --set-env-vars above (not a
# source-only deploy), then run the below-threshold probe under "Testing a deployment".

# 3. Billing → Budgets & alerts → a budget (e.g. $5/mo) whose scope is project uspv-api
#    ONLY, connected to the `budget-alerts` topic under "Manage notifications". Without the
#    project filter it covers the whole billing account, so another project's spend would
#    pause the API.
```

Grant the function's runtime service account `roles/run.admin` on the project so it can
pause the service. (A custom role with `run.services.get`/`run.services.update` is not
enough on its own: updating a service also needs `iam.serviceAccounts.actAs` on the
service's runtime identity.)
Today it runs as the default compute SA with `roles/run.admin`; moving it to a dedicated
least-privilege SA is [#288](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/288).

**Un-pause:** after resolving the cause, run **Actions → Deploy (Cloud Run) → Run
workflow**, which re-sets `--max-instances=1`.

## Deploy: the dashboard (`app_engine`)

Run these in the order [`docs/deploy-dashboard.md`](../../docs/deploy-dashboard.md) gives
(the guard exists before anything serves).

```
PROJECT=uspv-explore ; REGION=us-west1

# 1. Topic in the dashboard's own project.
gcloud pubsub topics create dashboard-budget-alerts --project="$PROJECT"

# 2. A least-privilege identity: a custom role holding only what the pause needs.
gcloud iam roles create appEngineKillswitch --project="$PROJECT" \
  --title="App Engine kill-switch" \
  --permissions=appengine.applications.get,appengine.applications.update,appengine.operations.get
gcloud iam service-accounts create explore-killswitch --project="$PROJECT" \
  --display-name="Dashboard budget kill-switch"
KS_SA="explore-killswitch@${PROJECT}.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${KS_SA}" --role="projects/${PROJECT}/roles/appEngineKillswitch"

# 3. The function, running AS that SA and triggered AS that SA (not the default compute SA).
gcloud functions deploy dashboard-killswitch --project="$PROJECT" \
  --gen2 --runtime=python312 --region="$REGION" \
  --source=deploy/killswitch --entry-point=budget_killswitch \
  --trigger-topic=dashboard-budget-alerts \
  --service-account="$KS_SA" --trigger-service-account="$KS_SA" --timeout=300s \
  --set-env-vars="KILLSWITCH_TARGET=app_engine,GCP_PROJECT=${PROJECT},PAUSE_AT_FRACTION=1.0"
gcloud functions add-invoker-policy-binding dashboard-killswitch --project="$PROJECT" \
  --region="$REGION" --member="serviceAccount:${KS_SA}"
```

**Un-pause:** after resolving the cause, set the serving status back. `gcloud app update`
has no serving-status flag, so use the Admin API (or the console: App Engine → Settings →
**Enable application**):

```
OP=$(curl -sS -X PATCH \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://appengine.googleapis.com/v1/apps/uspv-explore?updateMask=servingStatus" \
  -d '{"servingStatus": "SERVING"}' \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["name"].split("/")[-1])')
gcloud app operations wait "$OP" --project=uspv-explore   # the PATCH is a long-running op
gcloud app describe --project=uspv-explore --format='value(servingStatus)'   # SERVING
```

## Testing a deployment

Publish a message shaped like a budget notification to the target's own topic. A
below-threshold one must log `under threshold` and change nothing; never send an
over-threshold one to the API's topic except to test the API pause deliberately.

```
gcloud pubsub topics publish dashboard-budget-alerts --project=uspv-explore \
  --message='{"costAmount": 1, "budgetAmount": 5}'
```

`tests/unit/test_killswitch.py` pins the function's calls offline, against strict fakes of
the Google clients. Whether the live services accept those calls is what the probes in
[`docs/deploy-dashboard.md`](../../docs/deploy-dashboard.md) §6 establish (their output is
to be recorded on #283); re-run them after raising a ceiling in `requirements.txt`.
