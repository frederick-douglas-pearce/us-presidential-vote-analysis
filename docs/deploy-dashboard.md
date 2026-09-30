# Deploying the dashboard — App Engine standard (E9)

The dashboard runs on **App Engine standard** in its own GCP project, `uspv-explore`, on the
same billing account as the API ([decision **D071**](../.claude/specs/decisions.md)). This
runbook grows with E9. Its first part, from #283, sets up the project and the **cost guard**:
a budget and kill-switch that can pause the dashboard and nothing else. The app's own deploy,
its WIF identity and the `explore.` domain mapping are #277's and land here as later
sections.

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
  --format='yaml(budgetFilter,notificationsRule)'   # projects: only uspv-api; topic unchanged
```

Reading budgets needs `billingbudgets.googleapis.com` enabled on the quota project `gcloud`
uses.

## 2. Create the project and the App Engine app

```
PROJECT=uspv-explore ; REGION=us-west1
gcloud projects create "$PROJECT"
gcloud billing projects link "$PROJECT" --billing-account="$BILLING_ACCOUNT"
gcloud services enable appengine.googleapis.com cloudfunctions.googleapis.com \
  run.googleapis.com eventarc.googleapis.com pubsub.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com --project="$PROJECT"
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
so its identity needs only to write logs. Set it as the app's **default** service account,
so every version runs as it even without a `service_account:` line, and name it in each
version's `app.yaml` too.

```
gcloud iam service-accounts create explore-run --project="$PROJECT" \
  --display-name="Dashboard runtime"
RUNTIME_SA="explore-run@${PROJECT}.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${RUNTIME_SA}" --role=roles/logging.logWriter
gcloud app update --service-account="$RUNTIME_SA" --project="$PROJECT"
```

## 6. Probes

Run after any change to the guard, and record the output. The "only the dashboard" half
cannot be shown by publishing to the dashboard's topic alone (that topic cannot reach the
API's function), so it rests on readbacks that could each come back wrong:

- the dashboard budget's `budgetFilter.projects` is `uspv-explore` only, its amount is
  specified, and it publishes to `dashboard-budget-alerts`;
- the API budget's filter is `uspv-api` only, and it still publishes to `budget-alerts`;
- the API function's trigger topic is `projects/uspv-api/topics/budget-alerts`, and the
  dashboard topic's only subscription is the dashboard function's;
- the dashboard function's env and its runtime and trigger service accounts;
- `explore-killswitch` has no binding on `uspv-api`.

Then, against a running version:

1. **Below threshold:** publish `{"costAmount": 1, "budgetAmount": 5}` to
   `dashboard-budget-alerts`; the function logs `under threshold` and the app stays
   `SERVING`.
2. **Over threshold:** publish `{"costAmount": 5, "budgetAmount": 5}`. The app becomes
   `USER_DISABLED`, its instance count goes to 0 and it stops serving, while
   `https://api.us-presidential-election-center.org/health` still returns 200 and Cloud Run
   `usvote-api` keeps `max_instance_count = 1`.
3. **Un-pause** as the kill-switch README gives, and confirm the app serves again.
