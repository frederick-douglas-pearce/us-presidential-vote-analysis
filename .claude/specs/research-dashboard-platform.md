# Research: Dashboard Platform and Host (E9-S1)

> **Status: COMPLETE. Architect-reviewed (§12).** This is the E9-S1 (issue #276) research
> deliverable. It chooses the platform and host for the public dashboard at
> `explore.us-presidential-election-center.org` that reads the live `/v1` API (D070). The choice
> records as **D071**. It evaluates the five candidates #276 names, scans "none of the above"
> seriously (browser-side Python on static hosts, and a sweep of general-purpose app hosts), tests
> the four hypotheses the issue set, and answers the API sub-question.
>
> **The headline: Plotly Dash on Google App Engine standard, in its own GCP project, one
> always-on F1 instance.**
> - **Cost: about $0/month in compute.** The free tier is 28 F1-hours per day per project, and one
>   pinned instance uses 24.
> - **It never cold-starts**, and it serves the custom domain through a **GA** mapping.
> - **Measured on a throwaway deployment:** a fresh browser rendered the election table in
>   **1.7 s** (2.2 s at 10 Mbps / 100 ms), and the server returned the page, with its per-URL Open
>   Graph tags, in **0.13–0.19 s**.
> - **Runner-up:** Dash on Cloud Run behind Firebase Hosting (§1).
>
> **Three findings change what later stories must do.**
> 1. **Hypothesis (d) is CONTRADICTED.** A live probe showed the API's edge keeping a separate
>    cache entry for each `Origin` value (§8). No Worker or CORS change is needed for it.
> 2. **The Cloudflare Workers free quota, not CORS, is the cross-cutting risk.** The quota is
>    100,000 requests/day, **account-wide**, and the API's Worker already spends it. A second Worker
>    in front of `explore.`, or a browser-side dashboard making about 10 or more API calls per
>    visit, could exhaust it on a viral day. The **public API** would then return 1027 errors until
>    midnight UTC.
> 3. **The existing $5 budget covers the whole billing account.** It has no project filter,
>    VERIFIED from the live budget config. Its kill-switch pauses only the API. So a dashboard's
>    overspend would pause the **API**, and the dedicated-project design needs S1b to deliver the
>    isolation it promises (§9).

**Date:** 2026-09-27/28 · **Method:** eight parallel read-only research agents:
- Streamlit Community Cloud;
- Dash on Render;
- Gradio on HF Spaces;
- Shiny on Posit;
- self-hosting on Cloud Run, including the Workers-quota and hypothesis (b) questions;
- browser-side Python on static hosts, plus a non-Python control;
- a cross-cutting pass on marketability, sharing, accessibility and analytics;
- a sweep of general-purpose app hosts, added at the owner's request.

Then parent verification: raw re-fetches of the pages the verdict depends on, live probes of the
production API, **three throwaway deployments** measured and then torn down (§5, §13), and an
architect review (§12).

**Evidence labels, following `research-faithless-electors.md`. They are load-bearing.**

| Label | Meaning |
|---|---|
| **VERIFIED** | Primary artifact fetched and read: vendor docs, pricing page, source code, or this project's own config |
| **MEASURED** | Observed on a deployment, probe or local build made for this spike. Conditions stated beside the number |
| **ATTRIBUTED** | A named secondary source says so. Usable only with the source named in-line |
| **UNVERIFIED** | Could not be confirmed. Not a basis for a decision |
| **CONTRADICTED** | A better source or a measurement disproves it |

MEASURED is added to the four-label set because this spike, unlike the earlier two, ran things.
Pricing and limits are quoted verbatim with their URL. Every retrieval is dated 2026-09-28 unless
stated otherwise.

**A verification limit worth stating plainly.** The per-candidate characterizations in §6 rest on
the research agents' fetches.

The parent independently re-fetched **every page the recommendation and runner-up depend on**, as
raw HTML with curl and grep rather than through a summarizing fetch tool:
- App Engine's free-tier and pricing pages, the `app.yaml` reference, the environments comparison,
  and the app-management page;
- Cloud Run pricing and Cloud Run domain mapping;
- the Cloudflare Workers limits page, Pages Functions pricing, Custom Domains, and the
  CORS-and-cache page;
- Render's free-tier doc and pricing page.

**Not re-fetched by the parent:** Firebase Hosting's pages (agent H's raw fetch); every
ruled-out host in §6.

The raw-fetch discipline was earned. **A summarizing fetch of the Cloud Run domain-mapping page
reported "us-west1 is NOT included" in the supported regions. The raw page lists us-west1.**

---

## 1. Recommendation

**Platform:** Plotly Dash (Python).

**Host:** Google App Engine standard environment:
- Python 3.14 runtime;
- one F1 instance pinned with `automatic_scaling: {min_instances: 1, max_instances: 1}`;
- a **new GCP project** dedicated to the dashboard, on the existing billing account.

**Domain:** App Engine custom-domain mapping for `explore.`, served through a DNS-only
(grey-cloud) CNAME in Cloudflare.

Why this and not the others, criterion by criterion in the issue's order:

1. **Cost: about $0/month at idle, about $1 on a 10,000-visit day.**
   - VERIFIED, <https://cloud.google.com/free/docs/free-cloud-features>: *"28 hours per day of F1
     instances . 9 hours per day of B1 instances . 1 GB of outbound data transfer per day."*
   - VERIFIED, <https://cloud.google.com/appengine/pricing>: *"F1 0 hour to 28 hour Free per 1 day
     / project 28 hour and above $0.05 / 1 hour, per 1 day / project"* and *"Outgoing network
     traffic* 0 gibibyte to 1 gibibyte Free per 1 day / project 1 gibibyte and above $0.138948 / 1
     gibibyte"*.
   - One pinned instance uses 24 of the 28 free hours.
   - **The instance cap is per version.** VERIFIED, <https://cloud.google.com/appengine/docs/standard/reference/app-yaml>:
     `max_instances` is *"the maximum number of instances for App Engine to create for this module
     version"*, and `min_instances` *"applies only if the version of the app defined by this
     app.yaml file is configured to receive traffic"*.
   - So a non-serving old version holds no pinned instance, but two serving versions, or a deploy
     overlap, could exceed 28 h/day (INFERRED). **S2 deletes the previous version after each
     promotion.**
   - MEASURED: a first visit transfers 0.91 MB, so a viral day is ≈ 9 GB ≈ **$1.1** of egress.
   - Deploys add Cloud Build and staging-bucket storage (pennies, INFERRED). Hence "about $0", not
     "$0".
   - A dedicated project gets its own per-project free hours. It gets its own budget only once S1b
     scopes the existing budget (§9).
2. **Ease.**
   - One service and one `gcloud app deploy` from GitHub Actions on the keyless WIF pattern the API
     already uses.
   - No container, and no second front door.
   - View logic is plain Python, unit-testable offline: Dash callbacks are importable functions
     (VERIFIED, <https://dash.plotly.com/testing>).
   - Costs:
     - App Engine installs from `requirements.txt`, exported from `uv.lock`.
     - The region is permanent: *"You cannot change an app's region after you set it"* (VERIFIED,
       <https://cloud.google.com/appengine/docs/standard/locations>).
     - App Engine deploys are not containers, unlike the D032 API, so the paid fallback hosts would
       need a Dockerfile. The lock-in is mild but real.
3. **Python and marketable.**
   - Dash is **second in the only named survey that measures dashboard libraries**. JetBrains/PSF
     2024 "Libraries for creating dashboards": Streamlit 33%, Plotly Dash 28% (ATTRIBUTED).
   - 6.25M PyPI downloads last month (ATTRIBUTED, pypistats).
   - The host scores lower: App Engine is not separately surveyed, and it reads as older than Cloud
     Run (INFERRED). **This is the recommendation's soft spot, and the flip conditions below name
     it.**
   - Streamlit, the most adopted framework, has no path onto this host. App Engine standard
     supports no websockets (*"WebSockets No Yes"*, standard against flexible, VERIFIED,
     <https://cloud.google.com/appengine/docs/the-appengine-environments>), and Streamlit requires
     them (§6.5).
4. **Custom domain.**
   - App Engine's mapping carries **no Preview label**. Cloud Run's mapping is *"in the preview
     launch stage … not production-ready"* (both VERIFIED).
   - It needs the apex verified in Search Console.
   - It needs either a DNS-only CNAME or Cloudflare's zone-wide "Always use https" turned off
     (VERIFIED). **Take the DNS-only CNAME.** Do not change a zone-wide setting the API sits
     under.
   - **The cost of DNS-only, stated plainly:** `explore.` then has no Cloudflare rate limit, DDoS
     absorption or edge cache in front of it. Egress is the one uncapped cost line, so repeated
     abusive pulls of the 0.9 MB page are uncapped cost (INFERRED). S1b's budget and kill-switch
     are the backstop.
5. **Cold start: none for the dashboard.**
   - The instance is pinned.
   - MEASURED: a fresh browser reached a rendered AG Grid table in 1.7 s. The same app on
     scale-to-zero Cloud Run took 2.1–3.8 s for the HTML alone after idle (§4.5).
   - **The API behind it still scales to zero, and that is the one cold start left.** MEASURED:
     with the dashboard warm and a never-fetched election, a fresh browser took **9.12 s** to render
     the table after the API had idled about 40 minutes, against 1.13 s warm.
   - S2's throttled warmup prefetch of the canonical `/v1` URLs removes it: visitors then hit the
     Worker's edge cache, not the API (§4.5).
6. **Sharing.**
   - Dash Pages server-renders `og:title` / `og:description` / `og:image` into the **first HTML
     response per path**. VERIFIED from source; MEASURED on all three deployments.
   - Link scrapers do not run JavaScript (VERIFIED, Apple TN3156, §4.6). So a path-keyed view
     (`/election/<year>`) unfurls with its own card.
   - `dcc.Location` reads and writes the query string (VERIFIED).
   - An always-warm origin also meets Meta's *"within a few seconds"* crawl budget.
7. **Forward compatibility.** A full Python server inside GCP. A sibling chat service would be a
   separate service and needs nothing from this choice.

**Runner-up: Dash on Cloud Run behind Firebase Hosting** (Blaze plan, a `**` rewrite to the
service).
- **What it gets right:**
  - $0 at idle.
  - A GA custom domain. Google lists Firebase Hosting as a sanctioned Cloud Run custom-domain
    method (VERIFIED).
  - MEASURED: its CDN served a cached page in **0.15 s** (`x-cache: HIT`) after a cold first hit
    of 2.2 s.
  - Higher host marketability: Cloud Run + Docker + Firebase. Firebase is 13.1% in Stack Overflow
    2025 (ATTRIBUTED).
- **But the CDN hides cold start from scrapers, not from visitors.** MEASURED after 21 min idle: a
  scraper-style fetch of a cached page returned `x-cache: HIT` in **0.14 s**, while a fresh browser
  took **6.23 s** to render the table. The page-content callback is a POST, and it had to wake
  Cloud Run.
- **More moving parts:** two deploys, and a `public` Cache-Control hook the app must add, because
  Firebase treats dynamic content as private by default (VERIFIED).

**Conditions that flip the choice to the runner-up:**
- the real dashboard exceeds F1's 384 MB, or its callback latency on the 600 MHz CPU is
  unacceptable (an always-on F2 is not free);
- a load test shows `max_instances: 1` queuing or erroring under a viral-day rate. The cap fixes
  cost but also fixes capacity;
- the pin turns out to be billed after all, through a free-tier change or versions that cannot be
  kept to one;
- App Engine recycles the pinned instance often enough that visitors see cold starts;
- abuse traffic makes the DNS-only origin's uncapped egress a real cost. The runner-up's CDN
  absorbs cached GETs;
- App Engine standard is deprecated, or its Python runtime starts to lag;
- Fred weights host marketability above always-warm simplicity.

**Conditions that flip it to a paid host.** If both GCP options fail live, the fallbacks are
**Fly.io** (shared-cpu-1x always on, ≈ $2–4/month, INFERRED from VERIFIED rates) or **Render
Starter** ($7/month, VERIFIED). Both are inside the $10 ceiling.

**Code location: this repo**, in a top-level `dashboard/` directory with its own `dashboard`
dependency group (§10).

**API and infrastructure changes (§9):**
- **S1b, required before Phase 0 goes live:** scope the existing budget to `uspv-api`, and give
  the dashboard project its own budget and kill-switch.
- **S1a, optional:** `Literal` vocabularies in the API models. It is a D031 OpenAPI-quality
  improvement, not a gate, because S2's AC already lets the dashboard's tests import the
  vocabulary modules.
- **No CORS, Worker, rate-limit or origin-secret change is needed** for a server-side dashboard.

---

## 2. Head-to-head matrix

**Scale.** Raw scores 1–5 (5 best) per criterion, **unweighted**, so a reader can re-weight. **C1
scores monthly cost alone:**

| Monthly cost | C1 |
|---|---|
| $0 | 5 |
| ≤ $5 | 4 |
| $5–10 | 3 |
| >$10 | 1 |

Risks such as quota exhaustion sit in the last column, not in C1.

**Columns.** C1 cost · C2 ease · C3 Python/marketable (framework / host) · C4 custom domain · C5
cold start as a *visitor* sees it · C6 sharing · C7 forward compatibility. Cells summarize §§4–6,
which carry the evidence labels.

| # | Candidate | C1 | C2 | C3 fw / host | C4 | C5 | C6 | C7 | Dealbreaker (bold) / main risk |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Dash on App Engine F1, pinned (recommended)** | 5 | 4 | 4 / 2 | 5 | 5 | 4 | 5 | F1 headroom and capacity under load (live risk) |
| 2 | **Dash on Cloud Run + Firebase Hosting (runner-up)** | 5 | 3 | 4 / 4 | 5 | 2 | 4 | 5 | 6.2 s visitor wait after idle |
| 3 | Dash on Cloud Run + Cloud Run domain mapping | 5 | 3 | 4 / 4 | 3 | 2 | 3 | 5 | domain mapping is Preview, "not production-ready" |
| 4 | Dash on Cloud Run + a second Worker (on Workers Paid) | 4 | 3 | 4 / 4 | 4 | 2 | 3 | 5 | on the free plan it spends the API's quota |
| 5 | Streamlit / Shiny on Cloud Run | 4 | 3 | 5 or 3 / 4 | 3 | 2 | 2–4 | 5 | websockets need a Worker (Workers Paid) or Preview mapping; 60-min session cap |
| 6 | Dash on Render Starter | 3 | 4 | 4 / 2 | 4 | 5 | 4 | 5 | card on file; bandwidth uncapped |
| 7 | Dash on Render Free | 5 | 4 | 4 / 2 | 4 | 1 | 2 | 5 | 15-min spin-down, about 1 min wake, robots disallow-all while asleep |
| 8 | Streamlit on Community Cloud | 5 | 3 | 5 / 2 | 1 | 1 | 2 | 4 | **no custom domain** |
| 9 | Gradio on HF Spaces (PRO $9) | 3 | 3 | 3 / 3 | 3 | 3 | 1 | 4 | no URL write |
| 10 | Shiny on Posit Connect Cloud | 1 | 4 | 3 / 2 | 1 | 2 | 3 | 5 | **$59/mo for a custom domain** |
| 11 | Shiny on shinyapps.io | 1 | 2 | 3 / 1 | 1 | 2 | 1 | 3 | **$349/mo, iframe, Py ≤3.12, retiring** |
| 12 | stlite on Cloudflare Pages | 5 | 3 | 5 / 2 | 5 | 1 | 4 | 4 | 16.6–19.0 s boot; browser API calls spend the Workers quota |
| 13 | Panel on Pyodide, Cloudflare Pages | 5 | 3 | 3 / 2 | 5 | 3 | 2 | 4 | 8.7 s to live; shared-URL restore failed |
| 14 | Shinylive | 5 | 3 | 3 / 1 | 5 | 2 | 1 | 4 | **no URL state** |
| 15 | marimo WASM | 5 | 3 | 4 / 2 | 5 | 1 | 4 | 4 | 19 s boot |
| 16 | Fly.io always-on | 4 | 4 | 4 / 2 | 5 | 5 | 4 | 5 | card required, no free tier |
| 17 | Railway Hobby | 4 | 4 | 4 / 1 | 5 | 5 | 4 | 5 | Free has no custom domain |
| 18 | Cloudflare Containers | 3 | 3 | 4 / 3 | 5 | 4 | 4 | 5 | uncapped usage; also lifts the API quota |
| 19 | Vercel Hobby | 5 | 4 | 4 / 4 | 5 | 3 | 3 | 4 | **overage is a 30-day outage** |
| 20 | Non-Python static (control) | 5 | 4 | 1 / – | 5 | 5 | 5 | 5 | **not Python (C3)** |

**Re-weighting check.** With cost first, the C1=5 rows are 1, 2, 3, 7, 8, 12, 13, 14, 15, 19 and
20. Of those:
- rows 8, 14, 19 and 20 carry a bold dealbreaker;
- rows 3, 7, 12, 13 and 15 score ≤3 on C5 or C4 and lose to row 1 on C2 or C5;
- rows 1 and 2 remain.

Row 1 beats row 2 on C2 (ease) and C5 (cold start). Row 2 beats row 1 only on C3-host.
**They swap only if host marketability outweighs ease plus cold start.** That is the last flip
condition in §1.

---

## 3. "None of the above": what the scan covered

Both finalists came from this scan. Neither was on the issue's candidate list.

- **Browser-side Python on a static host:** stlite, Shinylive, Panel on Pyodide, marimo WASM,
  PyScript/raw Pyodide, and Quarto, on Cloudflare Pages or GitHub Pages.
  - Agent F built each one and measured it (§5.3).
  - Cloudflare Pages beats GitHub Pages on every axis compared (§6.6).
- **Other framework-on-Cloud-Run combinations:** Streamlit, Shiny and Dash on Cloud Run (§6.5).
- **A non-Python static control** (vanilla JS / Vite / Observable Framework). MEASURED at 0.02 MB
  and 0.10 s cold. It loses only on C3, which is a hard requirement for a portfolio project.
- **General-purpose app hosts**, added at Fred's request (agent H): Vercel, Fly.io, Railway,
  Netlify, App Engine standard, Firebase Hosting + Cloud Run, and a screen of Koyeb, Northflank,
  DigitalOcean App Platform, PythonAnywhere, Heroku, Azure Container Apps, AWS App Runner and
  Lambda URLs, Oracle Always Free, Cloudflare Containers, Leapcell, Zeabur and Modal (§6.9).

---

## 4. Per-criterion findings

### 4.1 Cost, and the constraint that dominates it

**The Cloudflare Workers free quota is account-wide, and the API already spends it.** VERIFIED,
<https://developers.cloudflare.com/workers/platform/limits/> (updated Sep 5, 2026), raw re-fetch:
- *"Accounts on the Workers Free plan have a daily request limit of 100,000 requests, resetting at
  midnight UTC."*
- When a limit is exceeded, a **route** fails open (*"Bypasses the Worker. Requests behave as if no
  Worker is configured."*) or closed (*"Returns a Cloudflare `1027` error page."*).

The API is a **Custom Domain** Worker, not a route, and it has no origin to fall back to. Per
D035, a bypassed request would reach `run.app` without the Host rewrite and 404. **Treat
exhaustion as an API outage** (INFERRED). Exhausting the quota to observe it would take the live
API down.

What spends the quota on a viral day of **10,000 visits** (this spike uses that number
throughout):

| Design | Worker requests that day | Label |
|---|---|---|
| Server-side dashboard, in-process API cache, no Worker in front | ≲ a few hundred (distinct `/v1` URLs × instance lifetimes) | INFERRED |
| Browser-side dashboard calling `api.` from each browser | 10,000 × *k*, where *k* = API calls per visit; **k ≥ 10 exhausts the quota** even with no other traffic | INFERRED from the VERIFIED quota |
| Any dashboard fronted by a second Worker on `explore.` | every page, asset and callback request: ≈ 160k–250k | INFERRED (agent E) |
| Static assets on Cloudflare Pages | 0 | VERIFIED: *"On both free and paid plans, requests to static assets are free and unlimited"*, <https://developers.cloudflare.com/pages/functions/pricing/> |

**The escape hatch is Workers Paid.** VERIFIED,
<https://developers.cloudflare.com/workers/platform/pricing/>: *"minimum charge of $5 USD per month
for an account"*, *"10 million included per month +$0.30 per additional million"*. It protects the
API whatever the dashboard does. The recommended design does not need it. It is filed as its own
API-resilience decision, **#285**.

**Per-host cost at the two traffic levels** (verbatim quotes in §6):

| Host | Near-zero traffic | 10,000-visit day | Hard cap? | Card |
|---|---|---|---|---|
| App Engine F1, pinned | ≈ $0 | ≈ $1.1 egress | compute: per version (`max_instances`, VERIFIED); egress: none | already on file |
| Cloud Run + Firebase Hosting | ≈ $0 | ≈ $0–2 (Hosting transfer; the free allowance is CONTRADICTED between two Google pages) | none | on file |
| Render Starter | $7 | $7 + ≈ $0–12 of bandwidth, depending on config | none | required |
| Fly.io always-on | ≈ $2–4 | + ≈ $0.30 egress | none | required |
| Cloudflare Pages (static) | $0 | $0 | yes, but the API quota is the real limit | no |
| Streamlit Community Cloud | $0 | $0 (fails at resource limits) | yes | no |

### 4.2 Ease of implementation and maintenance

Every server-side option can unit-test its view logic offline, all VERIFIED:
- Dash callbacks are plain importable functions;
- Streamlit has `AppTest`;
- Shiny has had `test_server()` since 1.8.0.

The differentiators are deploy topology, lock-in and churn:

- **App Engine:**
  - One `app.yaml` and one `gcloud app deploy`, run from Actions with WIF.
  - Needs `requirements.txt`, exported via `uv export --only-group dashboard`.
  - The region is permanent.
  - New projects default `max_instances` to 20, so **set it explicitly**. VERIFIED: *"For new
    projects you create after March 2025, App Engine sets the maximum instances default for standard
    environment deployments to 20."*
  - Not a container, so moving to a container host later needs a Dockerfile.
- **Cloud Run + Firebase:**
  - A container build (the D033 pattern), plus a Firebase release.
  - MEASURED: a Hosting version with a `run` rewrite can be created, finalized and released entirely
    through the REST API. CI needs no `firebase` CLI login, though the Firebase terms must first be
    accepted once in the console.
- **Framework churn:**
  - Dash went 4.0.0 (2026-02-03) → 4.4.1 (2026-07-21) → 4.5.0rc0 (2026-09-21). `DataTable` is
    deprecated for AG Grid and is removed in 5.0 (VERIFIED, <https://dash.plotly.com/datatable>).
  - Streamlit shipped 12 releases between 2026-03-31 and 2026-09-15, including a Tornado→Starlette
    server swap (VERIFIED, PyPI).

### 4.3 Python and marketable

Framework and host are scored separately, as the issue asked. All figures are dated 2026-09-28.

| Framework | PyPI downloads, last month (pypistats) | GitHub stars | JetBrains/PSF 2024 "dashboards" | HN "Who is hiring", Oct 2025–Sep 2026 (exact match) |
|---|---|---|---|---|
| Streamlit | 19,132,152 | 45,845 | 33% | 6 |
| Dash | 6,253,566 | 24,438 | 28% | 1 ("plotly") |
| Gradio | 5,227,393 | 43,633 | 11% | 0 |
| Panel | 1,378,386 | 5,779 | 10% | 0 |
| Shiny for Python | 222,825 | 1,754 | not listed | 0 |

Sources, all ATTRIBUTED: <https://pypistats.org/api/packages/dash/recent> (and the other
packages); the GitHub API; <https://lp.jetbrains.com/python-developers-survey-2024/>; HN Algolia
with typo tolerance off, since with it on, "streamlit" matches "streamline".

Caveats:
- None of the five appears in the Stack Overflow 2025 survey (VERIFIED by absence,
  <https://survey.stackoverflow.co/2025/technology>).
- Raw downloads mostly count CI and transitive installs. Read them as an order of magnitude
  (INFERRED).
- The 2025 and 2026 JetBrains pages return 404. The 2026 survey's results are not yet published
  (VERIFIED).
- LinkedIn's guest job counts (for example "7,000+ holoviz jobs") are fuzzy-match noise and are
  **excluded as a signal** (UNVERIFIED as a metric).

**Hosts** (Stack Overflow 2025, "Cloud development", all respondents, ATTRIBUTED): AWS 43.3%,
Azure 26.3%, Google Cloud 24.6%, Cloudflare 20.1%, Firebase 13.1%, DigitalOcean 10.7%, Vercel
10.6%, Netlify 5.9%, Heroku 5.4%, Railway 1.5%. Render, Fly and App Engine are not listed
separately.

**Reading it.** Streamlit is the most adopted by every named source, and Dash is a clear second.
The recommendation takes Dash because every Streamlit hosting path that fits the ceiling fails
elsewhere:
- Community Cloud fails C4 and C5;
- App Engine standard has no websockets;
- Cloud Run needs a Worker or a Preview domain mapping for websockets;
- the browser-side path (stlite) takes 16–19 s to boot.

It is not a judgment that Dash is the more marketable framework.

### 4.4 Custom domain

| Host | `explore.` on the recommended tier? | Cloudflare mechanics | Label |
|---|---|---|---|
| App Engine | yes, GA, managed cert | DNS-only CNAME, or turn off zone-wide "Always use https" | VERIFIED |
| Firebase Hosting | yes, GA | a TXT record kept present, plus A/AAAA records; proxied likely breaks cert issuance | VERIFIED / INFERRED |
| Cloud Run domain mapping | yes, but **Preview**; us-west1 supported | "turn off the 'Always use https' option" | VERIFIED (raw re-fetch) |
| Cloud Run via a second Worker | yes | spends the Workers quota | VERIFIED |
| Render | yes, even on Free | "DNS only" until the cert issues, then optionally Proxied | VERIFIED |
| Streamlit Community Cloud | **no** | only iframe embedding | VERIFIED (docs) / ATTRIBUTED (forum) |
| HF Spaces | PRO only ($9) | CNAME to `hf.space`; proxied unverified | VERIFIED |
| Posit Connect Cloud | Enhanced ($59) only | "DNS only" plus **"Disable Universal SSL"** zone-wide | VERIFIED |
| Cloudflare Pages | yes | CNAME auto-created on the same zone; no Host rewrite needed | VERIFIED |
| GitHub Pages | yes | DNS-only; proxied blocks the cert (GitHub staff, 2020) | VERIFIED / ATTRIBUTED |

**A correction to the issue's framing** (INFERRED, agent H). D035's 404 happened because Cloud Run
knew only its `run.app` hostname. Hosts that register the custom hostname themselves (App Engine,
Firebase, Render, Fly, Railway) route a proxied CNAME without any Host rewrite. What proxying
breaks on those hosts is **certificate issuance and renewal**. That is why DNS-only is the safe
default everywhere, and why no finalist needs a Worker.

**The price of DNS-only** is that nothing of Cloudflare's sits in front of the origin: no WAF rate
limit, no edge cache, no bot mitigation. For App Engine that leaves the uncapped egress line
exposed (§1 item 4). For the runner-up, Firebase's own CDN plays that role.

### 4.5 Cold start

Measured and documented, side by side. Every MEASURED row used the same throwaway app:
- Dash 4.4.1 Pages with dash-ag-grid 35.3.0;
- rendering one election's `/v1/elections/{year}` rows;
- an in-process `lru_cache` of API responses.

Browser timings were taken in headless Chrome via Playwright, at a 390×844 phone viewport on a
desktop CPU (i7-9750H). Each measures the time until the first AG Grid data cell exists.

| Host / state | Server TTFB | Browser: page → table rendered | Label |
|---|---|---|---|
| App Engine F1, pinned (dashboard never cold) | 0.13–0.19 s (first hit 0.82 s) | **1.72 s** fresh cache / 1.05 s warm; **2.20 s** / 1.12 s at 10 Mbps, 100 ms | MEASURED |
| App Engine F1, **stacked**: dashboard warm, a never-fetched election, API idle ~40 min | 0.28 s (HTML only; see note) | **9.12 s** fresh cache / 1.13 s warm | MEASURED |
| Cloud Run, scale-to-zero, ≥21 min idle: dashboard container cold | 3.76, 3.37, 2.08, 2.33 s | — | MEASURED |
| Cloud Run, same, `--cpu-boost` | 4.54, 4.57 s (n=2: no improvement observed) | — | MEASURED |
| Cloud Run, warm | 0.12–0.20 s | — | MEASURED |
| Cloud Run behind Firebase Hosting, first hit (CDN MISS, instance cold) | 2.21 s | 1.78 s fresh / 0.77 s warm (instance now warm) | MEASURED |
| Firebase Hosting, cached URL, CDN HIT | 0.15 s | — | MEASURED |
| Firebase Hosting, cached URL, Cloud Run cold after 21 min idle | 0.14 s (`x-cache: HIT`, what a scraper sees) | **6.23 s** fresh / 0.75 s warm | MEASURED |
| Render Free | "about one minute" to wake | — | VERIFIED |
| Streamlit Community Cloud | sleeps after 12 h; a visitor must click to wake | — | VERIFIED |
| Posit Connect Cloud (a third-party app) | 2.23 s to a "Loading…" interstitial, 4.54 s total | — | MEASURED (agent D, n=1) |
| stlite (Pyodide 0.29.3) | — | 16.6–19.0 s cold, 16.2 s warm | MEASURED (agent F) |
| Panel on Pyodide | — | 0.9 s to a prerendered view, 8.7 s to live | MEASURED (agent F) |
| marimo WASM | — | 19.2 s | MEASURED (agent F) |
| Vanilla JS control | — | 0.10 s | MEASURED (agent F) |

**A measurement note that corrects the design of the Cloud Run series.** A Dash Pages page's HTML
does not contain its own page's data. The HTML for `/election/1872` embeds the home view's rows
(REPRODUCED by grepping the response), and 1872's table arrives through the `_pages_location`
callback, which is where the server calls the API.

So **`curl` TTFB never includes the per-year API fetch.** The Cloud Run series' planned
"stacked" and "dashboard-only" split therefore did not measure what it was named for (§5.1). All
six samples measured a cold dashboard container, plus one edge-cached fetch.

**The true stacked cost is the browser row: 9.12 s against 1.13 s warm.** The API was idle about
40 minutes, and the Worker's edge had never cached that URL. Attributing the ~8 s difference to the
API's own cold start is INFERRED: the API's instance state was not observed directly.

**Consequence for S2:** a throttled warmup prefetch of the canonical `/v1` URLs (under 60/min, so
about 150–250 URLs in about 4 minutes) fills the edge cache for the dashboard's colo. After that,
visitors never wake the API between snapshot versions.

**What it costs to buy the cold start away:**
- **App Engine:** $0. The pin fits the free tier.
- **Cloud Run** with `--min-instances=1` at 1 vCPU / 512 MiB: **$9.86/month gross** at the VERIFIED
  idle rates of *"Idle time (Min instance 1 ) $0.0000025"* per vCPU-second and per GiB-second
  (<https://cloud.google.com/run/pricing>). Whether the spending-based free-tier discount covers the
  idle SKUs, bringing it to ≈ $4.64, is UNVERIFIED.
- **Render Starter:** $7.
- **Streamlit Community Cloud:** cannot be bought out.

**The browser-side cold start is CPU-bound, not cache-bound** (agent F).
- Warm reloads were barely faster.
- Chrome partitions its cache per site (VERIFIED, Chrome 86+), so a visitor's earlier Pyodide
  download from another site is not reused.

Fred's suggestion was a fast static landing page, with the Python runtime loading only after
click-through. It fixes the first impression but not the wait, which moves to the click, and on a
phone that wait is likely around 30 s (INFERRED from the desktop numbers). The browser-side family
therefore stays a fallback, not a contender.

### 4.6 Sharing: shareable URLs and link previews

**Why the OG tags must be in the server's first response:**
- Apple: *"Link previews do not follow `meta` redirects, nor run JavaScript; metadata must be
  available directly on the linked page"* (VERIFIED,
  <https://developer.apple.com/documentation/technotes/tn3156-create-rich-previews-for-messages>).
- Meta: *"Ensure that the content can be crawled by the crawler within a few seconds or Facebook
  will be unable to display the content"* (VERIFIED,
  <https://developers.facebook.com/docs/sharing/webmasters/web-crawlers/>).
- Slack reads *"the first 32kB of the response"* (ATTRIBUTED,
  <https://blog.daveallie.com/slack-link-unfurling/>).

A cold origin is therefore a sharing risk, not only a UX one.

| Framework | Read query string | Write query string | Per-URL OG in the first HTML |
|---|---|---|---|
| Dash | `dcc.Location.search`; Pages layout kwargs | yes (always `pushState`) | **yes, per path** (Pages); per-query via `hooks.index` |
| Shiny for Python | `session.clientdata.url_search()` | `session.bookmark.update_query_string(mode="replace"/"push")` | **yes**: the UI is a function of the request, plus `head_content` |
| Streamlit | `st.query_params` | yes; `bind="query-params"` on widgets | **no**: static index; only via the experimental `st.App` middleware |
| Gradio | `gr.Request.query_params` | **no Python API** | per app only |
| Panel | `pn.state.location.query_params` | `location.sync` | via a custom Jinja template |

All VERIFIED from docs and source (agent G). **Design consequence: make every shareable view a
path** (`/election/2000`, `/state/OH`) so Dash Pages emits its card, and keep the query string for
filters within a view.

MEASURED on all three deployments: the first response carries `og:title` = "1860 election —
explore" (and so on). App Engine also serves the same app at its `appspot.com` hostname. S2 must
redirect it to `explore.` and set `og:url` and a canonical link, so shares never carry the vendor
domain.

### 4.7 Forward compatibility (tie-breaker only)

- Every server-side host scores 5. A sibling chat service on its own subdomain needs nothing from
  the dashboard's host, and the dashboard needs no secret.
- Browser-side options and Community Cloud score 4. That is not for holding no secret, which the
  issue does not penalize; it is because they would need a second host for any server-side
  component.
- No candidate was decided on this criterion.

### 4.8 Also reported (not scored)

- **Phone width:**
  - Dash emits a viewport meta by default but has no responsive grid of its own. It needs
    dash-bootstrap-components or CSS (INFERRED).
  - All four Pyodide builds rendered at 390 px, with the table scrolling horizontally (MEASURED,
    agent F).
- **Table keyboard and screen-reader support.** This is a platform property that is hard to change
  later.
  - **Dash AG Grid** claims WCAG 2.0 AA / Section 508 and ARIA `role="grid"`, tested with JAWS and
    VoiceOver. It needs `ensureDomOrder` and the row/column virtualisation switches turned off,
    since screen readers *"assume all elements of the grid are loaded"* (VERIFIED vendor claim, not
    independently audited, <https://www.ag-grid.com/javascript-data-grid/accessibility/>).
  - **Streamlit `st.dataframe`** is a canvas grid with no accessible name yet (PR #17125 open).
  - **Gradio** gained ARIA grid support only in 6.27.0 (2026-09-11).
  - **Shiny** renders a real `<table>`, but with no `aria-sort`.
  - **Panel's Tabulator** has an ARIA grid and `aria-sort`.
  - A screen-reader pass on the chosen widget is still owed (S3).
- **Cookie-less analytics:**
  - Cloudflare Web Analytics is free, and says *"We don't use any client-side state, like cookies
    or localStorage, for the purposes of tracking users"* (VERIFIED,
    <https://blog.cloudflare.com/free-privacy-first-analytics-for-a-better-web/>).
  - On a DNS-only host it needs the manual JS beacon (limit *"Not proxied through Cloudflare |
    10"* sites, VERIFIED). Dash can inject it through `external_scripts`.
  - The beacon posts to `cloudflareinsights.com`, not `api.`, so it spends no Worker quota
    (INFERRED).
  - GoatCounter (free, cookie-less) is the alternative.

---

## 5. Measurements (throwaway deployments)

Every throwaway was torn down after measurement (§13).

### 5.1 Cloud Run, scale-to-zero (`coldprobe-276` in `uspv-api`)

**Configuration:** the API's own flags (`--min-instances 0 --max-instances 1 --memory 512Mi --cpu 1
--timeout 30 --no-cpu-boost --execution-environment gen1`), us-west1.

**Method:** samples ≥21 min apart, measured by `curl` TTFB. Each cold hit is confirmed cold by a
changed process-boot timestamp embedded in the page.

The series *planned* to alternate a "stacked" case (a fresh election year) with a "dashboard-only"
repeat of that year. **Because the HTML does not fetch its page's data (§4.5 note), that split did
not take effect.** Every row below measures a cold dashboard container, not the API.

| Time (UTC) | Case | Boost | Cold TTFB | Warm TTFB after |
|---|---|---|---|---|
| 07:52 | planned stacked (`/election/1824`) | off | 3.76 s | 0.20 s |
| 08:13 | planned dashboard-only (`/election/1824`) | off | 3.37 s | 0.18 s |
| 08:34 | planned stacked (`/election/1968`) | off | 2.08 s | 0.12 s |
| 08:55 | planned dashboard-only (`/election/1968`) | off | 2.33 s | 0.19 s |
| 09:16 | planned stacked (`/election/1904`) | **on** | 4.54 s | 0.17 s |
| 09:37 | planned dashboard-only (`/election/1904`) | **on** | 4.57 s | 0.16 s |

All six cold hits showed a new boot timestamp (REPRODUCED).

**Container cold start: 2.1–3.8 s.** `--cpu-boost` bought nothing measurable at n=2, which matches
Google's own silence on a latency figure, so the API's `--no-cpu-boost` stands.

The "Case" column records the plan, not what was measured (see above). The API's own cold cost is
measured only in the App Engine browser row of §4.5.

### 5.2 App Engine F1 and Firebase Hosting (`uspv-explore-276`, a throwaway project)

**Why a separate project.** It was measured in a separate project on the same billing account,
because creating an App Engine app fixes the project's region permanently (VERIFIED, above). The
app-management page offers only disabling an app; releasing its resources means shutting down the
project (VERIFIED, <https://cloud.google.com/appengine/docs/standard/managing-projects-apps-billing>).

**Results** are in §4.5.

**Measured locally in Docker, same image:**
- Resident memory **82.6 MiB** after six election pages, against F1's 384 MB.
- The index HTML is 8,011 B gzipped.
- The ten JS/CSS assets listed in it total 633,794 B gzipped, excluding lazily loaded component
  chunks.
- A browser first visit transferred 0.87–0.91 MB.

### 5.3 Browser-side builds (agent F, local, runtime from the production CDN)

| Build | Runtime (Python) | Cold bytes | Cold render | Warm |
|---|---|---|---|---|
| Vanilla JS | none | 0.02 MB | 0.10 s | 0.08 s |
| Raw Pyodide + pandas | 314.0.7 (3.14.2) | 13.9 MB | 10.6 s | 10.1 s |
| stlite 1.9.2 | 0.29.3 (3.13.2) | 23.1 MB | 16.6–19.0 s | 16.2 s |
| Shinylive 0.10.15 | 0.27.7 (3.12.7) | ≈22 MB gz | 13.3–14.0 s | 13.3 s |
| Panel 1.9.4 | 0.29.3 (3.13) | 22.4 MB | 0.9 s prerendered / 8.7 s live | 7.9 s |
| marimo 0.25.0 | 314.0.0 (3.14) | ≈23.6 MB | 19.2 s | 18.6 s |

**Conditions:** headless Chrome at 390×844 on a desktop CPU, unthrottled. **These are desktop-CPU
numbers.** A mid-range phone is slower.

---

## 6. Per-candidate characterization

Condensed. Each quote carries its URL.

### 6.1 Streamlit on Streamlit Community Cloud: ruled out

- **No custom domain.** VERIFIED: *"Every Community Cloud app is deployed to a subdomain on
  streamlit.app"*
  (<https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy>).
- **Sleep and wake.** VERIFIED:
  - *"All apps without traffic for 12 hours go to sleep."*
  - Waking takes a visitor's click on *"Yes, get this app back up!"*
    (<https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app>).
- **Cost.** *"Totally free"* (<https://streamlit.io/cloud>). There is no paid tier.
- **The iframe workaround** (ATTRIBUTED, forum moderator, 2025-12-14,
  <https://discuss.streamlit.io/t/custom-domain-menu-missing-in-app-settings-community-cloud/120316>):
  *"If you want a fully custom URL, you would have to embed your app in a iframe."*
  - Embedded apps reportedly cannot be woken (forum threads
    <https://discuss.streamlit.io/t/unable-to-wake-up-when-embedded/68397> and /86508).
- **Link previews.** MEASURED (agent A, curl as facebookexternalhit): the platform's OG tags are
  generic (`og:title "Streamlit"`) and strip the query string.
- **Shared egress IPs.** *"These IP addresses may change at any time without notice"*
  (<https://docs.streamlit.io/deploy/streamlit-community-cloud/status>).
- **Streamlit in Snowflake / Snowpark Container Services:** viewers need Snowflake authentication
  (VERIFIED); about $130/month (ATTRIBUTED, select.dev). Ruled out.

### 6.2 Dash on Render

- **Free-tier sleep.** VERIFIED (raw re-fetch, <https://render.com/docs/free>): *"Render spins down
  a Free web service that goes 15 minutes without receiving any inbound traffic… This process takes
  about one minute."*
- **Free-tier quota.** *"Render grants 750 Free instance hours to each workspace per calendar
  month"*.
- **Bandwidth exhaustion.** With no payment method, *"Render instead suspends all of your Free
  services for the remainder of the month"*.
- **Pricing.** VERIFIED (raw re-fetch, <https://render.com/pricing>):
  - *"$7/month 512 MB RAM 0.5c-512mb"*
  - *"Bandwidth 5 GB included per month then $0.15 per GB"*
  - *"Custom domains 2 included then $0.25/domain/month"*
- **Outbound IPs** are *"shared across _all_ services in the same region"*
  (<https://render.com/docs/outbound-ip-addresses>).
- **Callbacks are POSTs.** Dash callbacks POST to `_dash-update-component` (VERIFIED from source,
  <https://github.com/plotly/dash/blob/v4.4.1/dash/dash.py>). This confirms the issue's INFERRED
  claim.
- **Plotly Cloud:** custom domains are Pro-only at *"$29 per Creator seat / month"*
  (<https://plotly.com/pricing/>). Ruled out.

### 6.3 Gradio on Hugging Face Spaces

- **The issue's premise is CONTRADICTED.** CPU Basic is no longer free to create. VERIFIED: *"CPU
  Basic has no hourly cost, but creating a new Space that runs on compute (Gradio or Docker)
  requires a paid plan."* (<https://huggingface.co/docs/hub/spaces-gpus>)
- **PRO pricing.** *"$9 /month"* (<https://huggingface.co/pricing>).
- **Custom domain.** *"This feature is part of PRO or Team & Enterprise plans."*
  (<https://huggingface.co/docs/hub/spaces-custom-domain>)
- **URL state.** Gradio apps *"do not sync updated URL parameters with the parent page"*
  (<https://huggingface.co/docs/hub/spaces-handle-url-parameters>).

### 6.4 Shiny for Python on Posit

- **Connect Cloud:**
  - Custom domains start at *"Enhanced $59/month"*
    (<https://posit.co/blog/introducing-posit-connect-cloud-advanced-plan>).
  - The Cloudflare setup requires *"DNS only"* and *"Disable Universal SSL"*
    (<https://docs.posit.co/connect-cloud/user/share/custom-domains.html>).
  - Disabling Universal SSL removes the certificate *"from our network"* for the whole zone
    (<https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/disable-universal-ssl/>).
- **shinyapps.io:**
  - Custom domains only on *"Professional $349/month"* (<https://www.shinyapps.io/>), served in an
    iframe.
  - *"shinyapps.io supports python 3.7 to 3.12"*
    (<https://docs.posit.co/shinyapps.io/guide/getting_started/>).
  - Retiring: *"automatic migration will begin in early 2027"*
    (<https://posit.co/blog/migrating-connect-cloud-posits-unified-publishing-solution>).
- **Shiny the framework** is strong on sharing (§4.6) but has the smallest adoption of the five.
  On a self-managed host it is the websocket case in §6.5.

### 6.5 Self-hosting on Cloud Run (hypothesis (b))

- **The hypothesis clauses** are ruled on in §8.
- **Websocket frameworks.**
  - Streamlit and Shiny need websockets (VERIFIED).
  - Cloud Run caps a websocket at the request timeout: *"subject to request timeouts (currently up
    to 60 minutes and defaults to 5 minutes)"*
    (<https://docs.cloud.google.com/run/docs/triggering/websockets>).
  - An open websocket makes the instance *"considered active, so CPU is allocated and the service
    is billed as instance-based billing"*.
- **Dash** needs no websocket, which makes it the natural Cloud Run framework.
- **Load balancer front:** *"First 5 forwarding rules $0.025 / 1 hour"*, ≈ $18.25/month
  (<https://cloud.google.com/load-balancing/pricing>). Ruled out on cost.

### 6.6 Browser-side Python on static hosts

- **stlite** is the only option with marketable Streamlit authoring and top-level URL read and
  write (MEASURED). But it boots in 16.6–19.0 s.
- **Shinylive runs the app in an iframe.**
  - MEASURED: `url_search()` came back empty, and `update_query_string` wrote the iframe's URL
    rather than the page's.
  - A Posit maintainer, 2026-01-29: *"we don't have an easy or obvious path for connecting URL
    queries to the shinylive app instance"* (<https://github.com/posit-dev/shinylive/issues/208>).
  - The claim that "Shinylive has bookmarking" is CONTRADICTED: it is listed as "Coming soon"
    (<https://opensource.posit.co/blog/2025-04-15_shiny-python-1.4/>).
- **Panel** prerenders its initial view (0.9 s), but it overwrote `?state=Ohio` on load
  (MEASURED).
- **Every browser-side option spends the API's Workers quota**, at 10,000 × *k* requests on a viral
  day (§4.1).
- **Cloudflare Pages vs GitHub Pages.**
  - **Cloudflare Pages:**
    - static requests are free and unlimited;
    - *"500"* builds per month, 25 MiB per-file cap;
    - the custom domain's CNAME is auto-created on the same zone;
    - `Cache-Control` is configurable through `_headers`;
    - served with Brotli and gzip.

    All VERIFIED, <https://developers.cloudflare.com/pages/platform/limits/> and
    <https://developers.cloudflare.com/pages/configuration/custom-domains/>.
  - **GitHub Pages:**
    - Free plan: *"the repository must be public"*;
    - *"soft bandwidth limit of 100 GB per month"*;
    - fixed `cache-control: max-age=600` (MEASURED by curl);
    - proxied Cloudflare blocks its certificate (ATTRIBUTED, GitHub staff, 2020,
      <https://github.com/orgs/community/discussions/23632>);
    - Shinylive's self-hosted runtime would use ≈ 220 GB on one viral day.

    Sources: <https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits>.
  - **Verdict:** Cloudflare Pages is better on cost headroom, cache control and domain setup.

### 6.7 App Engine standard (recommended)

VERIFIED (parent raw re-fetch):
- *"28 hours per day of F1 instances . 9 hours per day of B1 instances . 1 GB of outbound data
  transfer per day."* (<https://cloud.google.com/free/docs/free-cloud-features>)
- *"F1 0 hour to 28 hour Free per 1 day / project 28 hour and above $0.05 / 1 hour, per 1 day /
  project"*; egress *"0 gibibyte to 1 gibibyte Free per 1 day / project 1 gibibyte and above
  $0.138948 / 1 gibibyte"* (<https://cloud.google.com/appengine/pricing>).
- Per-version scaling: `max_instances` for *"this module version"*; `min_instances` *"applies only
  if the version … is configured to receive traffic"*; `max_instances` defaults to 20 in new
  projects; `min_instances` requires warmup requests
  (<https://cloud.google.com/appengine/docs/standard/reference/app-yaml>).
- Websockets: standard *"No"*, flexible *"Yes"*
  (<https://cloud.google.com/appengine/docs/the-appengine-environments>).

VERIFIED (agent H):
- *"F1 (default) 384 MB 600 MHz automatic"*;
- *"Python 3.14 Ubuntu 24.04 python314 2030-10-10"*
  (<https://cloud.google.com/appengine/docs/standard/lifecycle/support-schedule>);
- *"Oregon (us-west1)"* in the pricing region list.

App Engine's free quota is listed separately from Cloud Run's, so it does not share the API's Cloud
Run free tier (INFERRED).

MEASURED: the probe was warm on every request made during the session (about ten over roughly 40
minutes). How often it recycles over days is UNVERIFIED.

### 6.8 Firebase Hosting in front of Cloud Run (runner-up)

VERIFIED (agent H, raw):
- Cloud Run's custom-domain page lists *"Use Firebase Hosting"* beside *"Use Cloud Run domain
  mapping (Limited availability and Preview)"*
  (<https://docs.cloud.google.com/run/docs/mapping-custom-domains>).
- *"subject to a 60-second request timeout"*; *"automatically upgraded to the Blaze pricing
  plan"*; rewrite regions include us-west1 (<https://firebase.google.com/docs/hosting/cloud-run>).
- *"By default, Firebase Hosting sets Cache-Control to private for dynamic content"*. The cache key
  includes the hostname, path and query string
  (<https://firebase.google.com/docs/hosting/manage-cache>).

The free transfer allowance is CONTRADICTED between Google's own pages:
- *"at no cost up to 10 GB/month"* (<https://firebase.google.com/docs/hosting/usage-quotas-pricing>);
- against *"No-cost up to 360 MB/day"* (<https://firebase.google.com/pricing>).

Websocket support through the rewrite is UNVERIFIED (the page is silent).

MEASURED:
- the rewrite forwards Dash's POST callbacks;
- with `public, s-maxage=3600`, the CDN returned `x-cache: HIT` in 0.15 s.

### 6.9 Other app hosts (agent H screen)

| Host | Finding | Source |
|---|---|---|
| Fly.io | no free tier for new customers (trial: *"2 hours of machine runtime or 7 days of access"*, card required); always-on shared-cpu-1x ≈ $1.94–3.80/mo, computed from the page's rate constants | <https://fly.io/docs/about/free-trial/>, <https://fly.io/docs/about/pricing/> |
| Railway | *"Custom domains 1 trial, then 0"* on Free; *"Hobby $5 / month"* | <https://railway.com/pricing>, <https://docs.railway.com/reference/pricing/plans> |
| Vercel Hobby | *"restricted to non-commercial personal use only"*; overage: *"you will have to wait until 30 days have passed"* | <https://vercel.com/docs/limits/fair-use-guidelines>, <https://vercel.com/docs/plans/hobby> |
| Cloudflare Containers | $5 Workers Paid + usage; *"cold starts can often be in the 1-3 second range"* | <https://developers.cloudflare.com/containers/faq/> |
| Netlify | functions are JS/TS/Go, so no server-side Python | <https://docs.netlify.com/build/functions/get-started/> |
| AWS App Runner | *"AWS App Runner is no longer open to new customers."* | <https://docs.aws.amazon.com/apprunner/latest/dg/what-is-apprunner.html> |
| Oracle Always Free | idle reclaim when p95 CPU is under 20% | <https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm> |
| Koyeb | *"Pro $ 29 /mo +compute"* | <https://www.koyeb.com/pricing> |
| Modal | *"Custom domains are available on the Team and Enterprise plans"* | <https://modal.com/docs/guide/webhook-urls> |
| PythonAnywhere | Free has *"restricted outbound Internet access"*; Developer $10 | <https://www.pythonanywhere.com/pricing/> |
| Heroku | Eco *"Sleeps after 30 minutes of inactivity"*; *"transitioning to a sustaining engineering model"* | <https://www.heroku.com/pricing/>, <https://www.heroku.com/blog/an-update-on-heroku/> |
| Northflank | *"Always-on-compute – no sleeping"* but *"should not be used for production applications"* | <https://northflank.com/pricing> |

---

## 7. Measured against quoted

For a reader re-weighting §2, this is which numbers came from a deployment and which from a page.

**MEASURED:**
- Cloud Run cold and warm TTFB;
- App Engine warm TTFB, its stacked case, and browser time-to-table;
- Firebase Hosting MISS/HIT behaviour and time-to-table, fresh and after idle;
- the Dash probe's memory and page weight;
- server-rendered OG tags on three hosts;
- agent F's six browser-side builds;
- agent D's one Connect Cloud interstitial;
- the live `api.` Origin probes.

**Quoted only:**
- everything about Render, HF, Posit hosting, Fly, Railway, Vercel and Cloudflare Containers;
- how often App Engine recycles instances;
- F1 capacity under load;
- certificate behaviour under a proxied CNAME.

---

## 8. Hypotheses, tested

| Hypothesis | Verdict | Label | Basis |
|---|---|---|---|
| **(a)** Streamlit Community Cloud serves only `*.streamlit.app`, no custom domain | **SUPPORTED** | VERIFIED (docs) + ATTRIBUTED (forum) | §6.1. The iframe workaround makes cold start worse (the embedded app reportedly cannot be woken) and sharing worse (generic OG; the address bar does not follow app state unless an unproven postMessage relay works) |
| **(b1)** A Cloud-Run dashboard at `explore.` does not pass through the API's Worker | **SUPPORTED** | VERIFIED | Custom Domains bind per hostname; the runbook binds only `api.` |
| **(b2)** …and hits D035's Host-routing 404 | **SUPPORTED** | ATTRIBUTED (repo, D035) | not re-tested |
| **(b3)** …so it needs its own front: a second Worker or domain mapping | **SUPPORTED, incomplete** | VERIFIED | domain mapping exists in us-west1 but is Preview. **Firebase Hosting is a third, GA option the hypothesis did not list** |
| **(b4)** A Worker can proxy websockets | **SUPPORTED** | VERIFIED | *"This establishes a WebSocket connection proxied through a Worker."* Billed once per connection |
| **(b5)** Cloud Run's timeout caps websocket sessions | **SUPPORTED** | VERIFIED | *"subject to request timeouts (currently up to 60 minutes…)"* |
| **(b6)** Dash callbacks are POSTs and not edge-cacheable | **SUPPORTED** | VERIFIED (source) / MEASURED | POST to `_dash-update-component`; they passed through the Firebase rewrite uncached |
| **(c)** Gradio is ML-oriented and weaker for a BI dashboard | **SUPPORTED, with nuance** | VERIFIED / ATTRIBUTED | self-described as for "machine learning apps"; it has dashboard components, but no URL write, a static head, and no cross-page interaction |
| **(d)** Browser-side dashboards get cached responses without CORS headers | **CONTRADICTED** | **MEASURED**; mechanism INFERRED | see below |

**Hypothesis (d) in full.**

The issue's reading of the app side is correct:
- Starlette sends no ACAO header on a request without an `Origin` (VERIFIED from source).
- The Worker caches `/v1` 200s through `caches.default` with `cache.match(request)` (VERIFIED,
  runbook §7).

**The measurement contradicts the conclusion.** MEASURED on 2026-09-28 at 05:14 UTC, in the SEA
and PDX colos, `/v1/meta` from one client:
1. A request with no `Origin` returned HIT, `age: 74475`, with no ACAO.
2. Seconds later, **in the same colo**, a request with `Origin: https://explore.…` returned HIT with
   `age: 23`, a **distinct** entry.
3. An apex-`Origin` entry carrying `access-control-allow-origin:
   https://us-presidential-election-center.org` and `vary: Origin` coexisted with both.

So both of (d)'s mechanisms fail. A no-`Origin` fill is never served to a browser that sends an
`Origin`, and two allowed origins never overwrite each other.

**The mechanism is INFERRED.** Cloudflare documents, for its CDN cache, that *"Cloudflare supports
CORS by: Identifying cached assets based on the Host Header, Origin Header, URL path, and query"*
(VERIFIED, raw fetch, <https://developers.cloudflare.com/cache/cache-security/cors/>). That this
applies to the Worker Cache API is INFERRED. The measurement carries the finding, not the page.

**Side effect, recorded.** The Origin-bearing probes filled per-Origin entries in two colos.
Per-Origin keying means no other client's entry was touched, and the next deploy's
`purge_everything` clears them.

**Why `explore.` gets no ACAO today:** it is not in `API_CORS_ORIGINS`. That matters only for a
browser-side dashboard, which the recommendation is not.

---

## 9. The API sub-question

### For the recommended option (server-side Dash on App Engine)

**CORS allow-list: no change.**
- Server-to-server fetches carry no `Origin` and are not subject to CORS.
- `API_CORS_ORIGINS` stays apex-only, and no `*` decision is needed.
- The stale comment at `src/usvote/api/config.py:24-26` ("the exact dashboard origin is deferred
  (frontend D001)") should say instead that the dashboard is server-side and needs no CORS origin.
  It is a one-line change; S2 or S1a carries it.
- **Hypothesis (d) needs no fix** (§8). If a browser-side component is ever added, adding its
  origin to `API_CORS_ORIGINS` is enough, since the edge keys on `Origin`.
- Server-side fetches share the canary's no-`Origin` cache entries, which helps.

**Rate limit (60/min/IP): no exemption needed, if the dashboard caches in-process.** S2 must make
all of the following guards, not conventions:
- **What to cache.** The API's data changes only per snapshot version (D034). So cache each
  distinct `/v1` URL and revalidate cheaply: key on `snapshot_version` from `/v1/meta`, rechecked on
  a short TTL (S3's AC requires ETag revalidation or a TTL). Calls to `api.` are then bounded by
  distinct URLs, not by visits.
- **One cache per instance.** The cache is per process, so run **one gunicorn worker with
  threads**. Otherwise each worker fills its own copy.
- **Throttle first fills.** On a new instance, spread the first fills below 60/min. App Engine's
  egress IPs are shared Google ranges (INFERRED).
- **Stacked cold start.** A never-fetched URL wakes the scale-to-zero API: MEASURED at 9.12 s
  against 1.13 s warm (§4.5). A throttled prefetch of the canonical URLs on warmup means visitors
  never pay that.

**Edge caching.** The server should fetch canonical URLs only (one resource per view, filtered
in-process), so the Worker's per-URL cache serves them. The query string is part of the cache
key.

**Origin secret.**
- The dashboard reaches the API **only through `https://api.us-presidential-election-center.org`**.
- It never calls `run.app` and never holds the secret (D070(b)). The secret stays in Cloudflare
  and Secret Manager.
- S2's guard asserts that no `run.app` string appears under `dashboard/`.

**Value vocabularies: no API change is required.**
- D070(b) forbids `usvote` imports **at runtime** only.
- S2's AC explicitly lets the dashboard's *tests* import the stdlib-only vocabulary modules
  (`usvote.snapshot_schema`, `usvote.count_status`, `usvote.pv.status`) to assert that every
  closed value has a label (`backlog-dashboard.md`, S2 AC).
- With the code in this repo, that is the vocabulary check, with no `openapi.json` dependency.

**Workers quota.** The recommended design spends a negligible share of it. **Workers Paid ($5) is
not required**, though it would protect the API independently (**#285**).

### For the runner-up (Cloud Run + Firebase Hosting)

The same, plus one dashboard-side change: the app sets `Cache-Control: public, s-maxage=…` on GET
HTML and on Dash's fingerprinted assets through a Flask `after_request` hook.

### Result: S1-lettered stories

| Story | Change | Must precede | Change surface and acceptance |
|---|---|---|---|
| **S1b, required** ([#283](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/283)) | **Scope the existing `uspv budget` to project `uspv-api`**. It has no project filter today (VERIFIED from the live config: no `projects` in `budgetFilter`), so dashboard spend would trip the API's kill-switch. **Give the dashboard project its own budget and kill-switch**: extend `deploy/killswitch/` (today Cloud-Run-only: `run_v2.ServicesClient`, `max_instance_count = 0`) with an App Engine action (disable the app, or `max_instances` → 0), or deploy a second function. Also a least-privilege runtime service account for the dashboard | Phase 0 go-live (#277) | **infra**: a PR for `deploy/killswitch/` plus a runbook entry, then a manual budget and function deploy. **Accepted by live probes:** the API budget's filter lists only `uspv-api`; a *below-threshold* test publish on the dashboard's topic logs and does **not** pause; an over-threshold publish targeted at the dashboard pauses **only** the dashboard, with the un-pause step run and documented |
| **S1a, optional** ([#284](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/284)) | Type `pv_status`, `electoral_count_status`, and the per-capita `coverage`, `boundary_basis` and `population_series` as `Literal[...]` in `src/usvote/api/models.py` (`:323`, `:339`, `:615`, `:622`, `:629`), so `openapi.json` carries the closed sets. Justified by D031 (OpenAPI as a deliverable) and by any future non-Python consumer, not by the dashboard. Note: a `Literal` turns an unexpected value into a response-validation 500, so it pins the snapshot vocabularies; consider an `API_VERSION` bump | none | **app code**: PR, CI, then a deploy run. Accepted by a live probe showing the enums in `/openapi.json` |

The architect's review (§12) is why S1b is required rather than optional. S2's settled AC already
says *"If it is on GCP, it is covered by the budget alert and kill-switch"*. The live budget's
missing project filter means the isolation this design relies on does not exist yet.

---

## 10. Where the dashboard code lives

**Recommendation:** this repo, `dashboard/` at the top level, under a dedicated `dashboard`
dependency group.

**Why this repo:**
- **The lock resolves.** Dash 4.4.1 + dash-ag-grid + gunicorn resolve wheels-only on manylinux
  cp314 (VERIFIED, agent B: `uv pip compile --python-version 3.14 --only-binary :all:`).
- **Pins overlap on one package.** Dash's pins (`Flask<3.2`, `plotly>=5.0.0`, `pydantic>=2.10`)
  overlap the `serve` group only on **pydantic**, as a lower bound. A future upper bound there
  would constrain the D033 image (INFERRED); watch it.
- **A group keeps D033's slim image untouched.** It is a group, not `serve` and not the base
  dependencies.
- **The vocabulary check works offline.** The dashboard's tests can import the stdlib-only
  vocabulary modules directly (S2 AC), with no API change.
- **The portfolio story** is one repository showing the whole system.
- **Nothing is duplicated.** The dev loop, CLAUDE.md conventions and CI are reused.

**Costs, each with its owner (S2 unless noted):**
- CI installs `--dev` only, so add `uv sync --group dashboard`. `mypy` `files` and pytest
  `testpaths` need extending (the `tooling/` precedent).
- **Deploy root.** Make `dashboard/` the deploy root, holding `app.yaml` and a `.gcloudignore`, so
  the upload physically excludes `src/usvote/` and any git-ignored snapshot.
- **`requirements.txt`** is exported from the lock in CI, either uncommitted or committed with a
  drift check.
- **The no-`usvote`-import guard is a static (AST) scan**, not an import test, because `usvote` is
  installed in the dev environment. It mirrors `test_api_import_graph.py`. Nothing goes under
  `src/usvote/` (D070(b)).
- **Accounts.** A WIF provider and deploy service account for the new project, plus a
  least-privilege runtime service account in place of App Engine's default (D034 §5).
- **No Dockerfile** is needed on App Engine. The runner-up or a paid fallback would need its own,
  since CI's `docker-build` job builds the root one.
- `loop.config.md` §3/§4 gain the `dashboard/` path and its deploy surface. That is the human's
  edit.

**For a separate repo:**
- There is no lock coupling.
- There is also no offline vocabulary check without S1a, because the vocabulary modules would not
  be importable.
- The conventions and dev loop would be duplicated.

Nothing found here justifies that cost. **The flip condition is a future Dash release whose pins
conflict with the pipeline's resolution.**

---

## 11. What this unblocks, story by story

### #277 (S2, walking skeleton)

**Host setup:**
- App Engine standard, F1, `python314`, us-west1, in a **new GCP project**.
- `min_instances: 1` and an explicit `max_instances: 1`, with warmup enabled.
- Delete the previous version after each promotion, confirmed by a live instance count (§1 item
  1).

**Domain:**
- App Engine domain mapping through a DNS-only CNAME, with Search Console verification of the
  apex.
- Redirect `*.appspot.com` to `explore.`, and set `og:url` and a canonical link.

**Deploy:** GitHub Actions + WIF, `workflow_dispatch`, deploy root `dashboard/`, and
`requirements.txt` exported from the lock.

**Guards:**
- no `run.app` string;
- the AST import scan;
- a single gunicorn worker;
- an in-process API cache keyed on `snapshot_version`, with a TTL or ETag recheck;
- a sub-60/min fill throttle and a throttled warmup prefetch.

**Links:** shareable views are paths (Dash Pages), so their OG cards render.

**Provenance** comes from `meta.provenance`, the carry-forward constraint.

**Verification:**
- A **load test** at a viral-day rate against `max_instances: 1`.
- A re-measure of the stacked cold case on the real app.
- The canary probes `explore.` as well.

**Needs S1b (#283) first.**

### #278 (S3)

- AG Grid with `ensureDomOrder` and virtualisation off for screen readers, pending a real
  screen-reader pass.
- `pv_status` and `electoral_count_status` labels tested against the vocabulary modules at test
  time.

### #279 / #280 (S4 / S5)

- Reuse S3's conventions.
- Histories are natural `/state/<usps>` and `/candidate/<slug>` paths.
- S5's per-capita vocabularies (`coverage`, `boundary_basis`, `population_series`) are tested the
  same way.

### S6–S8 (unfiled)

- **S6 (charts)** adds two loads to the F1 instance:
  - server-side figure building on a 600 MHz CPU;
  - plotly.js at 4.8 MB raw (VERIFIED, agent B). Load it only on chart pages, or set
    `serve_locally=False`.

  Both feed the first flip condition.
- **S8's apex question** can also be served by App Engine (INFERRED).

### Nothing here needs a new API endpoint

Any shape a chart needs later is a new snapshot table or `/v1` endpoint under D070(c), filed when
the chart is.

---

## 12. Architect review

**Reviewer:** the `architect` agent, 2026-09-28, read-only, on the draft of this document. It
produced a verdict on each of six questions, then **1 blocking, 6 important and 18 minor**
findings.

**Verdict:** *accept the recommendation, with one blocking fix and some go-live conditions*. Dash
on App Engine F1, pinned, wins under a strict reading of the priority order, and violates no repo
decision (D070(b), D030, D033, D035). D034 was under tension until S1b was made required.

**How each finding was dispositioned.** All were **adopted**; none was declined.

**Blocking and important:**

| Finding | Disposition |
|---|---|
| **B1**: App Engine pricing not re-fetched by the parent, and quoted without URLs | Adopted. Raw re-fetch of the free-tier page, pricing page, `app.yaml` reference and environments table, now quoted with URLs (§1, §6.7). The "verification limit" paragraph is updated |
| **I1**: "caps compute outright" is overstated | Adopted, sharpened by the re-fetch: `max_instances` is per version (VERIFIED) and `min_instances` applies only to the serving version (VERIFIED). Version cleanup goes into S2; a flip condition is added |
| **I2**: S1b "optional" conflicts with S2's AC, and the existing budget may not be isolated | Adopted **and confirmed**: the live budget has no project filter (VERIFIED). S1b is now required, with below- and over-threshold live-probe acceptance |
| **I3**: S1a's rationale is wrong for the in-repo verdict | Adopted. S1a is optional and justified by D031; it now covers the per-capita vocabularies; §10's separate-repo sentence is corrected |
| **I4**: the stacked cold start was not measured for the recommended option | Adopted: measured (§4.5), and a throttled warmup prefetch goes into S2 |
| **I5**: the DNS-only downside is unstated | Adopted: §1 item 4, §4.4, and a flip condition |
| **I6**: most pricing quotes have no URL | Adopted: URLs inline throughout §6 |

**Minor:**

| Finding | Disposition |
|---|---|
| M1–M6 (matrix scoring) | C1 is now cost-only on a stated scale; row 2 C5 → 2; row 13 re-scored; row 1 C7 → 5; the re-weighting list is complete; the dealbreaker column is cleaned up |
| M7 (the (d) label) | Now MEASURED; mechanism INFERRED |
| M8 (banner conditional) | Made conditional on *k* |
| M9 (LinkedIn label) | Now excluded, UNVERIFIED as a metric |
| M10 (pydantic overlap) | Reworded in §10 |
| M11 (cross-references) | Fixed; a GitHub Pages comparison is added to §6.6 |
| M12 (checklist D071) | Fixed |
| M13 (Streamlit on the recommended host) | VERIFIED: App Engine standard has no websockets |
| M14 ("≈ $0") | Adopted |
| M15–M17 (S2 items) | Added to §10 and §11 |
| M18 (lock-in) | A sentence in §1 item 2 and §4.2 |

**One suggestion is recorded here rather than acted on:** file Workers Paid as a separate
API-resilience issue. The owner chose to file it: **#285** (§4.1).

---

## 13. Throwaway deployments, and their teardown

| Resource | Where | Purpose | Torn down |
|---|---|---|---|
| Cloud Run `coldprobe-276`, and image `us-west1-docker.pkg.dev/uspv-api/usvote/coldprobe-276:throwaway` | project `uspv-api` | the Cloud Run cold series | **Yes**, 2026-09-28 ~09:45 UTC: service deleted, image deleted with its tags; `uspv-api` verified back to `usvote-api` + `budget-killswitch` and the `usvote-api` image only |
| Project `uspv-explore-276`: the App Engine app, Cloud Run `coldprobe-fb`, Artifact Registry `probe`, Firebase and its Hosting site | a new project on the same billing account | the App Engine and Firebase tests | **Yes**, 2026-09-28 ~10:10 UTC: `gcloud projects delete` → `DELETE_REQUESTED`. Billing stops at once; GCP purges the project after its 30-day recovery window, removing the App Engine app, Firebase and the Hosting site with it |

---

## 14. Checklist

| Item | Status |
|---|---|
| Status banner, date/method line, evidence-label legend | Done (top) |
| §1 Recommendation, readable on its own | Done |
| §2 head-to-head matrix, raw and unweighted | Done |
| Per-criterion (§4) and per-candidate (§6) sections | Done |
| "None of the above" scan | Done (§3, §6.6, §6.9) |
| Hypotheses (a)–(d), verdicts with labels | Done (§8) |
| API sub-question | Done (§9): S1b required, S1a optional |
| Per-story consequences | Done (§11) |
| Measured cold starts for the two finalists, including the stacked case | Done (§4.5, §5) |
| Pricing quoted verbatim with URL; parent re-fetch list stated | Done (top, §6) |
| Throwaway deployments torn down | Done (§13) |
| Architect review recorded | Done (§12) |
| Code location recommended | Done (§10) |
| Accepted verdict recorded as D071 | Done (`decisions.md`, this PR) |
| S1-lettered stories filed | Done on 2026-09-28, after the owner reviewed the list: S1b **#283**, S1a **#284**; and #285 (Workers Paid, under E8) |
