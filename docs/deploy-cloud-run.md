# Deploying the API — Cloud Run behind Cloudflare (E8-S7)

The public deployment of the read-only API ([decision **D034**](../.claude/specs/decisions.md)).
It graduates the D032 cloud-agnostic container (E8-S6) to a hosted service: **Cloud Run**
(scale-to-zero, single instance) fronted by **Cloudflare (free plan)** for CDN caching,
rate limiting, and bot protection — provisioned once, then redeployed by a
`workflow_dispatch` GitHub Action ([`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)).

**Cost posture (the top priority):** the container scales to **zero** when idle, caps at
**one** instance, uses **request-based CPU** (billed only while serving), and Cloudflare's
edge absorbs repeat reads so the origin is rarely woken. A **budget kill-switch** caps the
worst case. At this project's traffic, expect to sit inside the Cloud Run free tier (≈ $0).

> **You run the provisioning** (steps 1–7) with your own GCP + Cloudflare credentials — the
> repo ships the glue, not access to your cloud. After that, refreshing data is one click
> (§8). Do the steps **in order**: Cloudflare's rate-limits + origin secret are configured
> **before** the origin is locked to Cloudflare, so there is never an unprotected public
> window.

---

## 0. Prerequisites

- A **GCP project** with billing enabled (see the [README quick commands](../README.md)).
- A **domain you control** on **Cloudflare** (free plan). One domain serves both this API
  (`api.<domain>`) and a future dashboard (`<domain>` / `www` on GitHub Pages). Cloudflare
  Registrar sells at wholesale cost and auto-wires DNS.
- `gcloud` authenticated locally (`gcloud auth login`) for the one-time setup.

Set shell variables (adjust to your names):

```
PROJECT=usvote-api
REGION=us-west1
REPO=usvote                       # Artifact Registry repo
SERVICE=usvote-api                # Cloud Run service
BUCKET=gs://${PROJECT}-snapshots  # private snapshot bucket
GH_REPO=frederick-douglas-pearce/us-presidential-vote-analysis
```

## 1. Enable APIs

```
gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  storage.googleapis.com
```

## 2. Artifact Registry + the private snapshot bucket

```
gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION"

gcloud storage buckets create "$BUCKET" --location="$REGION" --uniform-bucket-level-access
gcloud storage buckets update "$BUCKET" --versioning   # rollback a bad snapshot upload
```

## 3. Two least-privilege service accounts (D034 fork 5)

A **deploy** SA (used by CI via WIF) and a separate **runtime** SA (what the service runs
as). The deploy SA can push/deploy but **cannot** read the origin secret; the runtime SA
can read only that secret.

```
# Runtime SA — the identity the Cloud Run service runs as.
gcloud iam service-accounts create usvote-api-run --display-name="usvote API runtime"
RUNTIME_SA="usvote-api-run@${PROJECT}.iam.gserviceaccount.com"

# Deploy SA — assumed by GitHub Actions through WIF.
gcloud iam service-accounts create usvote-api-deploy --display-name="usvote API deploy"
DEPLOY_SA="usvote-api-deploy@${PROJECT}.iam.gserviceaccount.com"

# Deploy SA permissions (no secretAccessor!).
for ROLE in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${DEPLOY_SA}" --role="$ROLE"
done
gcloud storage buckets add-iam-policy-binding "$BUCKET" \
  --member="serviceAccount:${DEPLOY_SA}" --role=roles/storage.objectViewer
# Let the deploy SA deploy a service that RUNS AS the runtime SA.
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:${DEPLOY_SA}" --role=roles/iam.serviceAccountUser
```

## 4. Origin secret in Secret Manager (D034 fork 2)

A random shared secret. Cloudflare injects it as a header on every proxied request; the app
rejects any `/v1` request that lacks it, so bots can't bypass the edge by hitting the raw
`run.app` URL. The **runtime** SA (only) can read it. `openssl rand -hex 32` avoids the
repo's `python` (pyenv pins 3.14 via `.python-version`, which may not be installed — a bare
`python` there produces no output and creates an *empty* secret); hex is also clean to paste
into the Cloudflare Transform Rule.

```
openssl rand -hex 32 | \
  gcloud secrets create usvote-origin-secret --data-file=- --replication-policy=automatic
gcloud secrets add-iam-policy-binding usvote-origin-secret \
  --member="serviceAccount:${RUNTIME_SA}" --role=roles/secretmanager.secretAccessor
# Note the value — you'll paste it into the Cloudflare Transform Rule in §7.
gcloud secrets versions access latest --secret=usvote-origin-secret
```

## 5. Workload Identity Federation — keyless CI auth (D034 fork 5)

No long-lived key. **Attribute-lock the provider to this repo** so no other GitHub repo can
impersonate the deploy SA.

```
gcloud iam workload-identity-pools create github --location=global --display-name="GitHub"
POOL=$(gcloud iam workload-identity-pools describe github --location=global --format='value(name)')

gcloud iam workload-identity-pools providers create-oidc github-actions \
  --location=global --workload-identity-pool=github \
  --display-name="GitHub Actions" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${GH_REPO}'"

# Let identities FROM THIS REPO impersonate the deploy SA.
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/${POOL}/attribute.repository/${GH_REPO}"

gcloud iam workload-identity-pools providers describe github-actions \
  --location=global --workload-identity-pool=github --format='value(name)'
# ^ this full resource name is GCP_WORKLOAD_IDENTITY_PROVIDER below.
```

## 6. Build the snapshot and upload it (D034 fork 1; AC4 refresh path)

The snapshot can only be built from the local warehouse (needs Postgres). CI never builds
it — it's a **data input** pulled from GCS.

Run these with `uv run` so the project's managed Python 3.14 + all deps are used (a bare
`python` hits the pyenv `.python-version` pin — see §4):

```
# Build the warehouse + snapshot locally (see README "Local smoke test").
uv run python -m usvote all
uv run python -m usvote.snapshot          # writes $USVOTE_API_SNAPSHOT_PATH
gcloud storage cp "$USVOTE_API_SNAPSHOT_PATH" "${BUCKET}/api_snapshot.sqlite"
```

`usvote all` is a create-if-absent load — it assumes empty tables. If the warehouse **already
has data** (you've built it before), a bare `all` fails with
`UniqueViolation: … "state_pkey" … Key (state)=(Alabama) already exists`. Use **`--replace`**
for a clean rebuild (drops + recreates the `dwh` schema, re-scrapes, reloads — destructive to
the local warehouse only):

```
uv run python -m usvote all --replace     # rebuild an already-populated warehouse from scratch
uv run python -m usvote.snapshot
gcloud storage cp "$USVOTE_API_SNAPSHOT_PATH" "${BUCKET}/api_snapshot.sqlite"
```

**Redistributable-only (AC5)** is guaranteed at the source: the snapshot is built from
`ec_pv_redistributable` (MIT/CC0 only, [D030](../.claude/specs/decisions.md)), re-asserted at
build time. Nothing non-redistributable can reach the bucket or the hosted service.

## 7. Configure GitHub + Cloudflare, then deploy

**GitHub → repo Settings → Secrets and variables → Actions.** Set **Variables**:

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | `$PROJECT` |
| `GCP_REGION` | `us-west1` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | the full provider resource name from §5 |
| `GCP_DEPLOY_SA` | `$DEPLOY_SA` |
| `GCP_RUNTIME_SA` | `$RUNTIME_SA` |
| `ARTIFACT_IMAGE` | `us-west1-docker.pkg.dev/$PROJECT/usvote/usvote-api` |
| `SNAPSHOT_GCS_URI` | `${BUCKET}/api_snapshot.sqlite` |
| `CLOUD_RUN_SERVICE` | `$SERVICE` |
| `API_CORS_ORIGINS` | your dashboard origin(s), comma-separated (never `*`) |
| `ORIGIN_SECRET_NAME` | `usvote-origin-secret` |
| `CLOUDFLARE_HOSTNAME` | `api.<domain>` — **leave unset for the very first deploy** |

Add a protected **`production` Environment** (Settings → Environments) with yourself as a
**required reviewer** — a human gate on this irreversible public deploy.

**First deploy (origin still open, no public DNS yet):** run **Actions → Deploy (Cloud Run)
→ Run workflow**. It builds, pushes, deploys, and asserts `/health`. Grab the `run.app` URL
from the deploy log.

**Cloudflare setup** (now that the service exists), on your zone:
1. **DNS:** add a **proxied** (orange-cloud) `CNAME api → <service>.run.app`; map the custom
   domain to the service (`gcloud run domain-mappings create --service=$SERVICE
   --domain=api.<domain> --region=$REGION`) and set SSL/TLS mode **Full (strict)**.
2. **Cache Rule:** for `Hostname eq api.<domain> and URI Path starts_with "/v1"` → **Eligible
   for cache**, **Edge Cache TTL** a long hold (e.g. 1 month) — this is the *long* hold the
   [D034 caching model](../.claude/specs/decisions.md) relies on; the deploy purges it on
   each new version. Leave `/health` uncached.
3. **Transform Rule (origin lock):** add a request header
   `X-Usvote-Origin-Secret: <the secret from §4>` on requests to `api.<domain>`.
4. **Rate limiting:** a reasonable per-IP rule (e.g. 60 req/min on `/v1*`, block/challenge on
   exceed) + enable **Bot Fight Mode** (Security → Bots).
5. Get the **Zone ID** (zone Overview) and create a scoped **API Token** (My Profile → API
   Tokens → *Zone → Cache Purge* on this zone only).

**Lock the origin + wire Cloudflare into CI:** set the GitHub **Secrets**
`CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ZONE_ID`, set the **Variable** `CLOUDFLARE_HOSTNAME =
api.<domain>`, then **re-run the workflow**. This deploy binds the origin secret (now the raw
`run.app` `/v1` returns **403**), purges Cloudflare, and the post-deploy smoke asserts raw
`/v1` → 403 **and** `https://api.<domain>/v1` → 200. From here the origin is reachable only
through Cloudflare's rate-limited, cached edge.

## 8. Refreshing the data (the snapshot-refresh story, AC4)

Data changes rarely (a bug fix, or every ~4 years for a new election):

```
uv run python -m usvote all && uv run python -m usvote.snapshot   # rebuild from the warehouse
gcloud storage cp "$USVOTE_API_SNAPSHOT_PATH" "${BUCKET}/api_snapshot.sqlite"
```

Then **Actions → Deploy (Cloud Run) → Run workflow**. The image is tagged with the new
`snapshot_version`, Cloud Run cuts over, and the workflow **purges Cloudflare after cutover**
so the edge refills from the new revision. Because the ETag is the content hash, clients
holding the old version revalidate and get the fresh data automatically.

## 9. Budget kill-switch (recommended — Cloud Run has no native hard cost cap)

See [`deploy/killswitch/`](../deploy/killswitch/): a tiny Cloud Function that, on a Billing
Budget Pub/Sub alert crossing your threshold, sets the service to `--max-instances=0`
(effectively pausing it) so a runaway bill is impossible. Also set plain **budget email
alerts** at 50/90/100% (Billing → Budgets & alerts). At free-tier traffic you'll never hit
it — it's the backstop, not the plan.

## What this does NOT do

- No live database anywhere ([D028](../.claude/specs/decisions.md)) — the snapshot is baked
  into the image; Postgres is touched only when *building* the snapshot locally.
- No non-redistributable data is ever served ([D030](../.claude/specs/decisions.md)).
- The image stays cloud-agnostic ([D032](../.claude/specs/decisions.md)): a provider swap
  (Fly.io/Render) touches only `deploy.yml`, never the app or the image.
