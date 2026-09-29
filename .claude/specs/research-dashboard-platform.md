# Research: Dashboard Platform and Host (E9-S1)

> **Status: COMPLETE. Architect-reviewed, and revised after code review (§12).** This is the E9-S1 (issue #276) research
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
> - **Pinned, it stayed warm** for every request of a ~40-minute probe session. How often App
>   Engine recycles it over days is UNVERIFIED, and is a flip condition (§1). It serves the custom
>   domain through a **GA** mapping.
> - **Measured on a throwaway deployment:** a fresh browser rendered the election table in
>   **1.7 s** (2.2 s at 10 Mbps / 100 ms), and the server returned the page, with its per-URL Open
>   Graph tags, in **0.13–0.19 s**.
> - **MVP cold-start target** (set by the owner, 2026-09-28): Open Graph HTML in ≤ 1 s, and a cold
>   shared link to its first data cell in ≤ 3 s, with the dashboard cold and with the API's edge
>   cold. With both warm, the 2.2 s run at 10 Mbps / 100 ms is inside the 3 s data criterion, but
>   neither cold case is met by a measurement: a cold App Engine instance (after a deploy or a
>   recycle) was not measured, and the one run with the API cold (9.12 s) fails. That is why S2
>   must prefetch, and why #277 measures both cases (§4.5).
> - **Runner-up:** Dash on Cloud Run behind Firebase Hosting (§1).
>
> **Three findings change what later stories must do.**
> 1. **Hypothesis (d) is CONTRADICTED.** A live probe showed the API's edge keeping separate cache
>    entries for a request with no `Origin` and one with an `Origin` (MEASURED, §8). That two
>    *allowed* origins also get separate entries follows from that, but was not measured
>    (INFERRED). No Worker or CORS change is needed.
> 2. **The Cloudflare Workers free quota, not CORS, is the cross-cutting risk.** The quota is
>    100,000 requests/day, **account-wide**, and the API's Worker already spends it. A second Worker
>    in front of `explore.`, or a browser-side dashboard making about 10 or more API calls per
>    visit, could exhaust it on a viral day. How a Custom Domain Worker fails at exhaustion is not
>    documented (UNVERIFIED); the likely outcome is that the **public API** stops answering, for
>    example with 1027 errors, until midnight UTC (INFERRED, §4.1).
> 3. **The existing $5 budget covers the whole billing account.** It has no project filter,
>    VERIFIED from the live budget config on 2026-09-28 (the output was not preserved). Its
>    kill-switch pauses only the API. So a dashboard's
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

The parent independently re-fetched these pages as raw HTML, with curl and grep rather than
through a summarizing fetch tool:
- App Engine's free-tier and pricing pages, the `app.yaml` reference, the environments comparison,
  and the app-management page;
- App Engine's custom-domain mapping page, runtime support schedule and instance-class table.
  These three were re-fetched during code review (§12), after the first version of this paragraph
  wrongly listed every recommendation page as re-fetched;
- Cloud Run pricing and Cloud Run domain mapping;
- the Cloudflare Workers limits page, Pages Functions pricing, Custom Domains, and the
  CORS-and-cache page;
- Render's free-tier doc and pricing page.

**Not re-fetched by the parent:** every Firebase Hosting page the runner-up depends on (agent H's
raw fetch), and every ruled-out host in §6.

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
     The probe set Dash's `compress=True`; Dash defaults to `False`, so S2 must set it too.
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
   - Dash and Streamlit are the **top two in both JetBrains/PSF surveys that measure dashboard
     libraries**, in opposite order: 2024, Streamlit 33% and Plotly Dash 28%; 2023, Plotly Dash 31%
     and Streamlit 28% (both ATTRIBUTED, §4.3).
   - 6.25M PyPI downloads last month (ATTRIBUTED, pypistats).
   - **Host, scored by its parent platform** (the owner's rule, 2026-09-28): App Engine and Cloud
     Run are both Google Cloud, 24.6% in Stack Overflow 2025 (ATTRIBUTED), so the two GCP finalists
     tie. With the API already on Cloud Run, a dashboard on App Engine adds a second GCP compute
     product to the portfolio.
   - Streamlit has no path onto this host. App Engine standard supports no websockets
     (*"WebSockets No Yes"*, standard against flexible, VERIFIED,
     <https://cloud.google.com/appengine/docs/the-appengine-environments>), and Streamlit requires
     them (§6.5).
4. **Custom domain.**
   - App Engine's mapping carries **no Preview label**. Cloud Run's mapping is *"in the preview
     launch stage … not production-ready"* (both VERIFIED).
   - It needs the apex verified in Search Console: *"Even if you only want to map a subdomain …
     enter the naked domain name to verify ownership … Enter information in the Search Console
     window that appears"* (VERIFIED, raw re-fetch,
     <https://cloud.google.com/appengine/docs/standard/mapping-custom-domains>).
   - The same page says that *"if you are using Cloudflare CDN, you should turn off the 'Always use
     https' option"* (VERIFIED). A DNS-only (grey-cloud) record does not put `explore.` on
     Cloudflare's CDN, so it avoids that condition (INFERRED). **Take the DNS-only CNAME.** Do not
     change a zone-wide setting the API sits under.
   - **The cost of DNS-only, stated plainly:** `explore.` then has no Cloudflare rate limit, DDoS
     absorption or edge cache in front of it. Egress is the one uncapped cost line, so repeated
     abusive pulls of the 0.9 MB page are uncapped cost (INFERRED). S1b's budget and kill-switch
     are the backstop.
5. **Cold start: the dashboard stayed warm; the API behind it does not.**
   - The instance is pinned, and it stayed warm for every request of the ~40-minute probe session
     (MEASURED). Recycling over days is UNVERIFIED.
   - MEASURED: a fresh browser reached a rendered AG Grid table in 1.7 s. The same app on
     scale-to-zero Cloud Run took 2.1–3.8 s for the HTML alone after idle (§4.5).
   - **The API still scales to zero, and that is the cold start left.** MEASURED: with the
     dashboard warm and a never-fetched election, a fresh browser took **9.12 s** to render the
     table, against 1.13 s warm. The API had idled about 40 minutes, an interval that was not
     logged (INFERRED).
   - **That fails the MVP target** (§4.5): OG-bearing HTML in ≤ 1 s TTFB, and a cold shared link
     to its first data cell in ≤ 3 s at 390 px on 10 Mbps / 100 ms, with the dashboard cold and
     with the API's edge cold.
   - So S2 must prefetch the canonical `/v1` URLs, throttled, **on warmup and again whenever
     `snapshot_version` changes**. Each API deploy purges the edge while the pinned instance stays
     up, so a warmup-only prefetch would leave the gap open after every deploy. The prefetch is
     expected to bring the cold-API case within target (INFERRED); #277 measures it.
6. **Sharing.**
   - Dash Pages server-renders `og:title` / `og:description` / `og:image` into the **first HTML
     response per path**. VERIFIED from source; MEASURED on all three deployments.
   - Link scrapers do not run JavaScript (VERIFIED, Apple TN3156, §4.6). So a path-keyed view
     (`/election/<year>`) unfurls with its own card.
   - `dcc.Location` reads and writes the query string (VERIFIED).
   - A warm origin also meets Meta's *"within a few seconds"* crawl budget.
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
  - The same host marketability under the parent-platform rule (Google Cloud). It tells a
    container-and-CDN story rather than a second-product one.
- **But the CDN hides cold start from scrapers, not from visitors.** MEASURED after about 21 min
  idle (the interval was not logged; INFERRED): a scraper-style fetch of a cached page returned `x-cache: HIT` in **0.14 s**, while a fresh browser
  took **6.23 s** to render the table. The likeliest cause is that the page-content callback, a
  POST the CDN does not cache, had to wake Cloud Run. That cause is INFERRED: neither the instance's
  state nor the API edge's state was recorded.
- **More moving parts:** two deploys, and a `public` Cache-Control hook the app must add, because
  Firebase treats dynamic content as private by default (VERIFIED).

**Conditions that flip the choice to the runner-up** (D071 carries the same list):
- the real dashboard exceeds F1's 384 MB, or its callback latency on the 600 MHz CPU is
  unacceptable (an always-on F2 is not free);
- #277's load test shows `max_instances: 1` queuing or erroring at the peak rate that story
  states. The cap fixes cost but also fixes capacity;
- the pin turns out to be billed after all, through a free-tier change or versions that cannot be
  kept to one;
- App Engine recycles the pinned instance often enough that visitors see cold starts;
- abuse traffic makes the DNS-only origin's uncapped egress a real cost. The runner-up's CDN
  absorbs cached GETs;
- App Engine standard is deprecated, or its Python runtime starts to lag.

**The condition that flips the code location** (§10), not the host: a future Dash release whose
pins conflict with the pipeline's resolution moves the dashboard to a separate repository.

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

**Scale.** Raw scores 1–5 (5 best), **unweighted**, so a reader can re-weight. Every column has
its own rubric. A cell that needed judgment beyond its rubric says why in §§4–6. Risks such as
quota exhaustion sit in the last column, not in the scores.

| Column | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|
| **C1 cost**: a month holding one 10,000-visit day, otherwise idle (§4.1) | $0 at idle, and the viral day adds ≤ $2 of usage | ≤ $5 | $5–10 | — | > $10, over the ceiling |
| **C2 ease** | one service, one CI deploy, and none of the costs in the next column (no candidate reaches it) | one service and one CI deploy, with costs of the lock-in, new-integration or permanent-setting kind (listed per host in §4.2 and below) | two deploy surfaces, a hand-edited component, or high framework churn | a significant workaround: an iframe, or a runtime that cannot run Python 3.14 | no reproducible CI deploy |
| **C3 framework**: the JetBrains/PSF "dashboards" question (§4.3) | top two in both the 2023 and 2024 surveys | — | 10–12% | not in the survey's reported list | not Python |
| **C3 host**: the parent platform's share, Stack Overflow 2025 "cloud development" (§4.3) | ≥ 30% | 20–30% | 10–20% | listed, under 10% | not listed |
| **C4 custom domain** (§4.4) | GA on a tier inside the ceiling, through a DNS-only record, with no zone-wide change | — | Preview, or only on a paid tier of $9 or more | needs a zone-wide Cloudflare change | none inside the ceiling |
| **C5 cold start as a visitor sees it**: the dashboard's own. The API's is common to every design (§4.5) | no sleep by design | cold ≤ 3 s | 3–10 s | 10–30 s, or it sleeps or scales to zero with a wake time nobody measured or quoted | ≥ 30 s, or a click to wake |
| **C6 sharing** (§4.6). Then −1 where a scraper can find the origin asleep for more than a few seconds | per-URL Open Graph in the first HTML for paths and queries, plus URL read and write | per-path OG, plus URL read and write | per-URL OG only through a customization nobody demonstrated (INFERRED), plus URL read and write | OG per app or generic only, or URL restore failed when measured | no top-level URL state: an iframe, or no write API |
| **C7 forward compatibility** (§4.7) | a full server-side runtime on this host | a constrained or absent server side, so a server component needs a second host | the platform is retiring or pins an old Python | — | — |

**Columns.** C1 cost · C2 ease · C3 Python/marketable (framework / host) · C4 custom domain · C5
cold start as a *visitor* sees it · C6 sharing · C7 forward compatibility. Cells summarize §§4–6,
which carry the evidence labels.

| # | Candidate | C1 | C2 | C3 fw / host | C4 | C5 | C6 | C7 | Dealbreaker (bold) / main risk |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Dash on App Engine F1, pinned (recommended)** | 5 | 4 | 5 / 4 | 5 | 5 | 4 | 5 | F1 headroom and capacity under load (live risk); recycling over days UNVERIFIED |
| 2 | **Dash on Cloud Run + Firebase Hosting (runner-up)** | 5 | 3 | 5 / 4 | 5 | 3 | 4 | 5 | 6.2 s visitor wait after idle |
| 3 | Dash on Cloud Run + Cloud Run domain mapping | 5 | 4 | 5 / 4 | 3 | 3 | 4 | 5 | domain mapping is Preview, "not production-ready" |
| 4 | Dash on Cloud Run + a second Worker (on Workers Paid) | 3 | 3 | 5 / 4 | 5 | 3 | 4 | 5 | on the free plan it spends the API's quota |
| 5 | Streamlit / Shiny on Cloud Run | 4 | 3 | 5 or 2 / 4 | 3 | 3 | 3 | 5 | websockets need a Worker (Workers Paid) or the Preview mapping; 60-min session cap |
| 6 | Dash on Render Starter | 3 | 4 | 5 / 1 | 5 | 5 | 4 | 5 | card on file; bandwidth uncapped |
| 7 | Dash on Render Free | 5 | 4 | 5 / 1 | 5 | 1 | 3 | 5 | 15-min spin-down, about 1 min wake, robots disallow-all while asleep |
| 8 | Streamlit on Community Cloud | 5 | 3 | 5 / 1 | 1 | 1 | 1 | 4 | **no custom domain** |
| 9 | Gradio on HF Spaces (PRO $9) | 3 | 3 | 3 / 1 | 3 | 2 | 1 | 4 | no URL write |
| 10 | Shiny on Posit Connect Cloud | 1 | 4 | 2 / 1 | 1 | 3 | 2 | 5 | **$59/mo for a custom domain** |
| 11 | Shiny on shinyapps.io | 1 | 2 | 2 / 1 | 1 | 2 | 1 | 3 | **$349/mo, iframe, Py ≤3.12, retiring** |
| 12 | stlite on Cloudflare Pages | 5 | 3 | 5 / 4 | 5 | 2 | 3 | 4 | 16.6–19.0 s boot; browser API calls spend the Workers quota |
| 13 | Panel on Pyodide, Cloudflare Pages | 5 | 3 | 3 / 4 | 5 | 3 | 2 | 4 | 8.7 s to live; shared-URL restore failed |
| 14 | Shinylive on Cloudflare Pages | 5 | 3 | 2 / 4 | 5 | 2 | 1 | 4 | **no URL state** |
| 15 | marimo WASM on Cloudflare Pages | 5 | 3 | 2 / 4 | 5 | 2 | 3 | 4 | 19 s boot |
| 16 | Fly.io always-on | 4 | 4 | 5 / 1 | 5 | 5 | 4 | 5 | card required, no free tier |
| 17 | Railway Hobby | 4 | 4 | 5 / 2 | 5 | 5 | 4 | 5 | Free has no custom domain |
| 18 | Cloudflare Containers | 3 | 3 | 5 / 4 | 5 | 3 | 4 | 5 | uncapped usage; also lifts the API quota |
| 19 | Vercel Hobby | 5 | 4 | 5 / 3 | 5 | 2 | 4 | 4 | **overage is an outage of up to 30 days** |
| 20 | Non-Python static (control) | 5 | 4 | 1 / 4 | 5 | 5 | 3 | 4 | **not Python (C3)** |

**Scores that rest on an INFERRED input:**
- C1: rows 3–5 (Cloud Run egress, and websocket billing, on a viral day; row 5 is scored on its
  cheaper Preview-mapping path, since the Worker path would add $5); row 6 (bandwidth assumes
  compressed responses, §4.1); rows 16–18 (computed from rates, or agent H's estimate).
- C5: rows 3–5 and 18 (a visitor's wait inferred from a container start, measured for Cloud Run
  and vendor-quoted for Containers, so both score 3); rows 6, 16 and 17 (always on as configured,
  not measured). Rows 9, 11 and 19 take the rubric's unmeasured-wake level.
- C6: wherever the rubric's INFERRED level applies (rows 5, 10, 12, 15, 20).

**Judgment cells, explained.**
- **C2.** App Engine scores 4 with its costs listed in §4.2: a permanent region, a non-container
  deploy (lock-in), a `requirements.txt` export, a `max_instances` default to override, and
  version cleanup. They are well-documented costs of a mature platform, and the rubric's 4 covers
  them. Row 9 (HF Spaces) is 3: it deploys by pushing to a separate Space repository, a second
  deploy surface. Rows 12–15 are 3: the app's Python runs on a browser runtime (Pyodide) that the
  build pins separately, and §5.3's four builds use three Pyodide versions, which the rubric counts
  as churn. Row 20 is 4: one static build, with a new CI integration (Pages) as its cost.
- **C6, row 10.** Shiny's per-URL OG is at the INFERRED level (3), less 1 because agent D measured
  a cold Connect Cloud app serving a generic, `noindex` "Loading…" page (§4.5), which is what a
  scraper would see. Its sleep policy is UNVERIFIED, but a cold state was observed.

**Re-weighting check.** Row 1 scores at least as well as every other row on every column, with
C3's framework and host compared separately, and strictly better than each on at least one. So no
weighting of these columns ranks another row above it. Against the runner-up, row 1 is ahead on
C2 (one deploy against two) and C5 (pinned against scale-to-zero) and level everywhere else. Row 2
is kept because its failure modes differ from row 1's, which is what the flip conditions in §1
describe, not because any weighting prefers it.

---

## 3. "None of the above": what the scan covered

Both finalists came from this scan. Neither was on the issue's candidate list.

- **Browser-side Python on a static host:** stlite, Shinylive, Panel on Pyodide, marimo WASM,
  PyScript/raw Pyodide, and Quarto, on Cloudflare Pages or GitHub Pages.
  - Agent F built and measured stlite, Shinylive, Panel on Pyodide, marimo, and raw Pyodide,
    which stands in for PyScript because PyScript runs on it (§5.3).
  - Quarto was not built. Its interactive Python runs on Shinylive, so it inherits Shinylive's
    result, including the missing URL state (agent F).
  - Cloudflare Pages beats GitHub Pages on every axis compared (§6.6).
- **Other framework-on-Cloud-Run combinations:** Streamlit, Shiny and Dash on Cloud Run (§6.5).
- **A non-Python static control** (vanilla JS / Vite / Observable Framework). MEASURED at 0.02 MB
  and 0.10 s cold. It fails C3, a hard requirement for a portfolio project, and also scores
  lower than the recommendation on C6 (per-URL OG would need a per-path build, INFERRED) and C7
  (no server side).
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

The API is served through a Workers **Custom Domain**, not a route. The quoted fail-open and
fail-closed behaviour is documented for routes; how a Custom Domain behaves at exhaustion is not
(UNVERIFIED, agent E). A Custom Domain has no origin server of its own to fall open to: the Worker
*is* what answers `api.`, and it reaches Cloud Run only by fetching `run.app` itself (D035). So
the likely outcome is that `api.` stops answering, perhaps with a 1027 page, until the quota resets
(INFERRED). **Treat exhaustion as an API outage.** Exhausting the quota to observe it would take
the live API down.

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

**Per-host cost at the two traffic levels** (verbatim quotes in §6). C1 in §2 scores the month
holding the 10,000-visit day. A 10,000-visit day moves about 9 GB at the 0.9 MB first visit
measured in §5.2; browser-side builds move far more, but from a static host whose requests are
free.

| Host | Near-zero traffic | Month with a 10,000-visit day | Hard cap? | Card |
|---|---|---|---|---|
| App Engine F1, pinned | ≈ $0 | ≈ $1.1 egress | compute: per version (`max_instances`, VERIFIED); egress: none | already on file |
| Cloud Run + Firebase Hosting | ≈ $0 | ≈ $0–2 (Hosting transfer; the free allowance is CONTRADICTED between two Google pages) | none | on file |
| Cloud Run + domain mapping, or + a second Worker | ≈ $0; + $5 for Workers Paid | ≈ $1 egress (INFERRED) | none | on file |
| Streamlit or Shiny on Cloud Run, Preview mapping | ≈ $0 | an open websocket bills as instance time (VERIFIED, §6.5); ≲ $5 on the viral day (INFERRED) | none | on file |
| Render Starter | $7 | $7 + ≈ $0.60 if responses are compressed: about 9 GB against 5 GB included, at $0.15/GB. The 0.9 MB visit was measured with Dash's `compress=True` (the probe's `app.py`), and Dash defaults to `False`. Agent B's estimates, which include plotly.js: ≈ $2.85 compressed, ≈ $11.70 uncompressed, which is over the ceiling (INFERRED) | none | required |
| Render Free | $0 | $0; Free services are suspended if bandwidth runs out with no payment method (VERIFIED) | yes, by suspension | no |
| Fly.io always-on | ≈ $2–4 | + ≈ $0.30 egress | none | required |
| Railway Hobby | $5, including $5 of usage | ≈ $5 (INFERRED) | a hard-limit option (agent H) | UNVERIFIED |
| Cloudflare Containers | $5 Workers Paid + usage | ≈ $5–7 (agent H, INFERRED) | none | required for Workers Paid |
| Vercel Hobby | $0 | $0 | yes: over the limit, *"you will have to wait until 30 days have passed"* | UNVERIFIED |
| HF Spaces PRO | $9 | $9 | UNVERIFIED | UNVERIFIED |
| Posit Connect Cloud Enhanced / shinyapps.io Professional | $59 / $349 | same | UNVERIFIED | UNVERIFIED |
| Cloudflare Pages (static) | $0 | $0 | yes, but the API quota is the real limit | no |
| Streamlit Community Cloud | $0 | $0 (fails at resource limits) | yes | no |

UNVERIFIED cells are for ruled-out candidates, whose details were not pursued further (owner's
decision, 2026-09-28).

### 4.2 Ease of implementation and maintenance

Every server-side option can unit-test its view logic offline, all VERIFIED:
- Dash callbacks are plain importable functions;
- Streamlit has `AppTest`;
- Shiny has had `test_server()` since 1.8.0.

The differentiators are deploy topology, lock-in and churn:

- **App Engine** (C2 4; the bullets after the first are its costs):
  - One `app.yaml` and one `gcloud app deploy`, run from Actions with WIF.
  - Needs `requirements.txt`, exported via `uv export --only-group dashboard`.
  - The region is permanent.
  - `min_instances` and `max_instances` are set per version, so each deploy must delete the
    version it replaces (§1 item 1).
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
  - Streamlit shipped 12 releases between 2026-03-31 and 2026-09-15 (VERIFIED, PyPI's release
    list), including a Tornado→Starlette server swap in 1.57.0: *"Introducing Starlette as the
    default web server!"* (VERIFIED, Streamlit's 2026 release notes, agent A).

### 4.3 Python and marketable

Framework and host are scored separately, as the issue asked. All figures are dated 2026-09-28.

| Framework | PyPI downloads, last month (pypistats) | GitHub stars | JetBrains/PSF 2024 "dashboards" | JetBrains/PSF 2023 "dashboards" | HN "Who is hiring", Oct 2025–Sep 2026 (exact match) |
|---|---|---|---|---|---|
| Streamlit | 19,132,152 | 45,845 | 33% | 28% | 6 |
| Dash | 6,253,566 | 24,438 | 28% | 31% | 1 ("plotly") |
| Gradio | 5,227,393 | 43,633 | 11% | 12% | 0 |
| Panel | 1,378,386 | 5,779 | 10% | 12% | 0 |
| Shiny for Python | 222,825 | 1,754 | not in the reported list | not in the reported list | 0 |

Sources, all ATTRIBUTED: <https://pypistats.org/api/packages/dash/recent> (and the other
packages); the GitHub API; <https://lp.jetbrains.com/python-developers-survey-2024/> (agent A) and
<https://lp.jetbrains.com/python-developers-survey-2023/>, whose text reads *"Plotly Dash and
Streamlit are the top two choices"* (agent B); HN Algolia with typo tolerance off, since with it
on, "streamlit" matches "streamline". "Not in the reported list" means the agents' quoted survey
figures stop before it, not that the survey was searched for it.

Caveats:
- None of the five appears in the Stack Overflow 2025 survey (VERIFIED by absence,
  <https://survey.stackoverflow.co/2025/technology>).
- Raw downloads mostly count CI and transitive installs. Read them as an order of magnitude
  (INFERRED).
- The 2025 and 2026 JetBrains pages return 404. The 2026 survey's results are not yet published
  (VERIFIED).
- LinkedIn's guest job counts (for example "7,000+ holoviz jobs") are fuzzy-match noise and are
  **excluded as a signal** (CONTRADICTED as a usable metric, agent G).

**Hosts** (Stack Overflow 2025, "Cloud development", all respondents, ATTRIBUTED): AWS 43.3%,
Azure 26.3%, Google Cloud 24.6%, Cloudflare 20.1%, Firebase 13.1%, DigitalOcean 10.7%, Vercel
10.6%, Netlify 5.9%, Heroku 5.4%, Railway 1.5%. Render, Fly and App Engine are not listed
separately.

**The host rule: score the platform that runs the compute** (the owner's choice, 2026-09-28).
A compute product the survey does not list separately takes its parent platform's share. So App
Engine and Cloud Run score as Google Cloud (24.6%), and Cloudflare Pages and Containers as
Cloudflare (20.1%). The runner-up's compute is Cloud Run, so it scores as Google Cloud too,
although its front, Firebase, is listed separately (13.1%). The owner's reasoning: with the API already on Cloud Run, a dashboard on App
Engine shows breadth within GCP rather than repeating one product.

**Reading it.** Streamlit leads on downloads, stars and HN mentions, and led the 2024 survey. Dash
led the 2023 survey. The two are the top pair in both. The recommendation takes Dash because no
Streamlit hosting path meets the ceiling, the custom domain, per-URL link previews and an
acceptable cold start at once:
- on every server-side host, Streamlit serves a static index with no per-URL Open Graph tags, so
  its shared links unfurl generically; the experimental `st.App` middleware might change that
  (INFERRED, §4.6);
- Community Cloud also has no custom domain, and needs a click to wake;
- App Engine standard has no websockets, so Streamlit cannot run there at all;
- Cloud Run needs a Worker (Workers Paid, inside the ceiling) or the Preview domain mapping for
  websockets, and scales to zero;
- on a static host (stlite), per-path OG would need a per-path build nobody demonstrated
  (INFERRED), and it boots in 16–19 s;
- Render Starter, Fly and Railway fit the ceiling and carry websockets, but hit the first point.
  Render's websocket support is VERIFIED (its free-tier doc counts *"WebSocket messages from
  existing connections"* as traffic); Fly's and Railway's is INFERRED from their running
  long-lived containers.

It is not a judgment that Dash is the more marketable framework.

### 4.4 Custom domain

| Host | `explore.` on the recommended tier? | Cloudflare mechanics | Label |
|---|---|---|---|
| App Engine | yes, GA, managed cert; the apex verified in Search Console first | with Cloudflare's CDN, turn off zone-wide "Always use https"; a DNS-only CNAME avoids that | VERIFIED (raw re-fetch) / INFERRED (DNS-only) |
| Firebase Hosting | yes, GA | a TXT record kept present, plus A/AAAA records; proxied likely breaks cert issuance | VERIFIED / INFERRED |
| Cloud Run domain mapping | yes, but **Preview**; us-west1 supported | "turn off the 'Always use https' option" | VERIFIED (raw re-fetch) |
| Cloud Run via a second Worker | yes | spends the Workers quota | VERIFIED |
| Render | yes, even on Free | "DNS only" until the cert issues, then optionally Proxied | VERIFIED |
| Streamlit Community Cloud | **no** | only iframe embedding | VERIFIED (docs) / ATTRIBUTED (forum) |
| HF Spaces | PRO only ($9) | CNAME to `hf.space`; proxied unverified | VERIFIED |
| Posit Connect Cloud | Enhanced ($59) only | "DNS only" plus **"Disable Universal SSL"** zone-wide | VERIFIED |
| Cloudflare Pages | yes | CNAME auto-created on the same zone; no Host rewrite needed | VERIFIED |
| GitHub Pages | yes | DNS-only; proxied blocks the cert (GitHub staff, 2020) | VERIFIED / ATTRIBUTED |

**A correction to the issue's framing.** D035's 404 happened because Cloud Run knew only its
`run.app` hostname. Hosts that register the custom hostname themselves route a proxied CNAME
without any Host rewrite. Agent H names App Engine, Railway, Fly, Heroku and Northflank (INFERRED,
agent H). Render's own Cloudflare doc says to stay "DNS only" until the certificate issues and then
optionally proxy (VERIFIED, agent B). What proxying breaks on those hosts is **certificate issuance
and renewal**. That is why DNS-only is the safe default everywhere, and why no finalist needs a
Worker.

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

**MVP target** (set by the owner, 2026-09-28, on the architect's recommendation). #277 measures
against it:
- **Open Graph HTML:** any shareable path returns its OG-bearing HTML in **≤ 1 s TTFB**.
- **Cold shared link → first data cell in ≤ 3 s**, at a 390 px viewport on a 10 Mbps / 100 ms
  link, in **both** cases: the dashboard cold, and the API's edge cold for that URL.
- Later performance work goes only where it affects users most.

Against it: pinned App Engine meets the OG criterion (0.13–0.19 s, 0.82 s on the first hit) and,
with the API warm, the data criterion (2.20 s at 10 Mbps / 100 ms). The stacked case, 9.12 s
unthrottled, fails the data criterion. The dashboard-cold case on App Engine, a new instance after
a deploy or a recycle, was not measured; #277 measures it. The Cloud Run container's cold HTML
alone, 2.1–3.8 s, fails the 1 s OG criterion.

**Raw logs.** Rows marked *log not preserved* were read off the terminal during the session and
are not reproduced anywhere. The stacked App Engine row, the Firebase after-idle row and the Cloud
Run series are reproduced verbatim in §5.4.

| Host / state | Server TTFB | Browser: page → table rendered | Label |
|---|---|---|---|
| App Engine F1, pinned (warm throughout the session) | 0.13–0.19 s (first hit 0.82 s) | **1.72 s** fresh cache / 1.05 s warm; **2.20 s** / 1.12 s at 10 Mbps, 100 ms | MEASURED; log not preserved |
| App Engine F1, **stacked**: dashboard warm, a never-fetched election, API idle ~40 min (the interval is INFERRED: not logged) | 0.28 s (HTML only; see note) | **9.12 s** fresh cache / 1.13 s warm | MEASURED (§5.4) |
| Cloud Run, scale-to-zero, ≥21 min idle: dashboard container cold | 3.76, 3.37, 2.08, 2.33 s | — | MEASURED (§5.4) |
| Cloud Run, same, `--cpu-boost` | 4.54, 4.57 s (n=2: no improvement observed) | — | MEASURED (§5.4) |
| Cloud Run, warm | 0.12–0.20 s | — | MEASURED (§5.4) |
| Cloud Run behind Firebase Hosting, first hit (CDN MISS, instance cold) | 2.21 s | 1.78 s fresh / 0.77 s warm (instance now warm) | MEASURED; log not preserved |
| Firebase Hosting, cached URL, CDN HIT | 0.15 s | — | MEASURED; log not preserved |
| Firebase Hosting, cached URL, Cloud Run cold after about 21 min idle (the interval is INFERRED: not logged) | 0.14 s (`x-cache: HIT`, what a scraper sees) | **6.23 s** fresh / 0.75 s warm | MEASURED (§5.4) |
| Render Free | "about one minute" to wake | — | VERIFIED |
| Streamlit Community Cloud | sleeps after 12 h; a visitor must click to wake | — | VERIFIED |
| HF Spaces, CPU Basic on PRO | sleeps after 48 h without traffic, and a visit restarts it; wake time not measured | — | VERIFIED (agent C) |
| Posit Connect Cloud (a third-party app) | 2.23 s to a "Loading…" interstitial, 4.54 s total; sleep policy UNVERIFIED | — | MEASURED (agent D, n=1) |
| Fly.io, Railway Hobby | always on as configured; neither measured | — | INFERRED |
| Render Starter | no spin-down on a paid instance; not measured | — | INFERRED (agent B) |
| Cloudflare Containers | *"cold starts can often be in the 1-3 second range"*: a container start, not a visitor's wait; sleep policy UNVERIFIED | — | VERIFIED quote (agent H) |
| Vercel Hobby | serverless functions scale to zero; cold start neither measured nor quoted | — | INFERRED |
| shinyapps.io | sleep policy UNVERIFIED | — | UNVERIFIED |
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
six samples measured a cold dashboard container, plus, INFERRED, one fetch of the home view's data
that the API's edge had already cached.

**The true stacked cost is the browser row: 9.12 s against 1.13 s warm.** The API was idle about
40 minutes (INFERRED: the interval was not logged), and the Worker's edge had never cached that
URL. Attributing the ~8 s difference to the API's own cold start is INFERRED: the API's instance
state was not observed directly.

**Consequence for S2:** a throttled prefetch of the canonical `/v1` URLs (under 60/min, so about
150–250 URLs in about 4 minutes) fills the dashboard's in-process cache and the edge cache for its
colo. It must run **on warmup and again whenever `snapshot_version` changes**, swapping the new
cache in atomically. Each API deploy purges the edge while the pinned instance stays up, so a
warmup-only prefetch would leave visitors waking the API after every deploy. With both triggers,
visitors are expected not to wake the API at all (INFERRED); #277 measures that against the target
above.

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
| Dash | `dcc.Location.search`; Pages layout kwargs (VERIFIED) | yes, always `pushState` (VERIFIED) | **yes, per path** (Pages; VERIFIED from source, MEASURED); per query only through `hooks.index` (INFERRED) |
| Shiny for Python | `session.clientdata.url_search()` (VERIFIED) | `session.bookmark.update_query_string(mode="replace"/"push")` (VERIFIED) | the UI is a function of the request, plus `head_content` (VERIFIED); that this yields per-URL OG is INFERRED |
| Streamlit | `st.query_params` (VERIFIED) | yes; `bind="query-params"` on widgets (VERIFIED) | **no**: a static index (VERIFIED); only perhaps through the experimental `st.App` middleware (INFERRED) |
| Gradio | `gr.Request.query_params` (VERIFIED) | **no Python API** (VERIFIED) | per app only (VERIFIED) |
| Panel | `pn.state.location.query_params` (VERIFIED) | `location.sync` (VERIFIED) | through a custom Jinja template (INFERRED) |

Labels are per cell, from agent G's report. **Design consequence: make every shareable view a
path** (`/election/2000`, `/state/OH`) so Dash Pages emits its card, and keep the query string for
filters within a view.

MEASURED on all three deployments: the first response carries `og:title` = "1860 election —
explore" (and so on). App Engine also serves the same app at its `appspot.com` hostname. S2 must
redirect it to `explore.` and set `og:url` and a canonical link, so shares never carry the vendor
domain.

### 4.7 Forward compatibility (tie-breaker only)

- Hosts that give a full server-side runtime score 5. A sibling chat service on its own subdomain
  needs nothing from the dashboard's host, and the dashboard needs no secret.
- Hosts with a constrained or absent server side score 4: the browser-side options, Community
  Cloud, HF Spaces and Vercel's serverless functions. That is not for holding no secret, which the
  issue does not penalize; it is because a server-side component would need a second host.
- shinyapps.io scores 3: it is retiring, and it runs Python only up to 3.12.
- No candidate was decided on this criterion.

### 4.8 Also reported (not scored)

- **Phone width:**
  - Dash emits a viewport meta by default but has no responsive grid of its own. It needs
    dash-bootstrap-components or CSS (INFERRED).
  - Four of agent F's Pyodide builds (raw Pyodide, stlite, Shinylive, marimo) rendered their
    table at the 390 px viewport, the table wider than the screen and cut off at the right edge.
    Source: agent F's screenshots `bench/shot_{pyodide,stlite,shiny,marimo}.png`, read by the
    parent; they are not committed. A still image cannot show whether the table scrolls.
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

**Measured locally in Docker, same image** (log not preserved):
- Resident memory **82.6 MiB** after six election pages, against F1's 384 MB.
- The index HTML is 8,011 B gzipped.
- The ten JS/CSS assets listed in it total 633,794 B gzipped, excluding lazily loaded component
  chunks.
- A browser first visit transferred 0.87–0.91 MB.

### 5.3 Browser-side builds (agent F, local)

| Build | Runtime (Python) | Runtime served from | Cold bytes | Cold render | Warm |
|---|---|---|---|---|---|
| Vanilla JS | none | self | 0.02 MB | 0.10 s | 0.08 s |
| Raw Pyodide + pandas | 314.0.7 (3.14.2) | jsDelivr | 13.9 MB | 10.6 s | 10.1 s |
| stlite 1.9.2 | 0.29.3 (3.13.2) | jsDelivr | 23.1 MB | 16.6–19.0 s | 16.2 s |
| Shinylive 0.10.15 | 0.27.7 (3.12.7) | self-hosted | ≈22 MB gz | 13.3–14.0 s | 13.3 s |
| Panel 1.9.4 | 0.29.3 (3.13) | jsDelivr, plus the HoloViz/Bokeh CDN | 22.4 MB | 0.9 s prerendered / 8.7 s live | 7.9 s |
| marimo 0.25.0 | 314.0.0 (3.14) | self-hosted, plus jsDelivr | ≈23.6 MB | 19.2 s | 18.6 s |

**Conditions:** headless Chrome at 390×844 on a desktop CPU, unthrottled. **These are desktop-CPU
numbers.** A mid-range phone is slower.

### 5.4 Raw logs, verbatim

The three logs the session kept, reproduced so the numbers above can be checked. TTFB is curl's
`time_starttransfer`; `[boot …]` is the process-boot timestamp the probe app embeds in its page; a
browser line reports seconds from navigation until the first AG Grid data cell (`.ag-cell`) exists,
and the megabytes transferred. `"mode": "fast"` is an unthrottled run; the throttled mode emulates
10 Mbps down and 100 ms latency.

**Cloud Run cold series (§5.1)**, `coldprobe-276`:

```text
# series start 2026-09-28T07:31:20Z boost=off
2026-09-28T07:52:24Z cold-stacked /election/1824 200 ttfb=3.764380 total=3.788648 [boot 1790581944]
2026-09-28T07:52:24Z warm /election/1824 200 ttfb=0.203384 total=0.247277 [boot 1790581944]
2026-09-28T07:52:25Z warm-otherpage /election/2000 200 ttfb=0.122067 total=0.154628 [boot 1790581944]
2026-09-28T08:13:28Z cold-dashonly /election/1824 200 ttfb=3.368646 total=3.457423 [boot 1790583208]
2026-09-28T08:13:28Z warm /election/1824 200 ttfb=0.176776 total=0.202736 [boot 1790583208]
2026-09-28T08:13:28Z warm-otherpage /election/2000 200 ttfb=0.137672 total=0.164445 [boot 1790583208]
2026-09-28T08:34:31Z cold-stacked /election/1968 200 ttfb=2.076916 total=2.097362 [boot 1790584471]
2026-09-28T08:34:31Z warm /election/1968 200 ttfb=0.115190 total=0.154563 [boot 1790584471]
2026-09-28T08:34:31Z warm-otherpage /election/2000 200 ttfb=0.125124 total=0.222508 [boot 1790584471]
2026-09-28T08:55:33Z cold-dashonly /election/1968 200 ttfb=2.329202 total=2.358489 [boot 1790585733]
2026-09-28T08:55:34Z warm /election/1968 200 ttfb=0.185625 total=0.212218 [boot 1790585733]
2026-09-28T08:55:34Z warm-otherpage /election/2000 200 ttfb=0.170045 total=0.207926 [boot 1790585733]
# boost=on 2026-09-28T08:55:41Z
2026-09-28T09:16:46Z cold-boost-stacked /election/1904 200 ttfb=4.535752 total=4.566135 [boot 1790587005]
2026-09-28T09:16:46Z warm /election/1904 200 ttfb=0.172137 total=0.202467 [boot 1790587005]
2026-09-28T09:37:51Z cold-boost-dashonly /election/1904 200 ttfb=4.570193 total=4.595694 [boot 1790588270]
2026-09-28T09:37:51Z warm /election/1904 200 ttfb=0.163682 total=0.205647 [boot 1790588270]
# series end 2026-09-28T09:37:51Z
```

**App Engine stacked case (§4.5):**

```text
2026-09-28T10:00:00Z
gae-stacked-cold /election/1888 200 ttfb=0.277198
gae-api-now-warm-edge-miss /election/1876 200 ttfb=0.174071
{"url": "https://uspv-explore-276.uw.r.appspot.com/election/1880", "mode": "fast", "cold-browser": {"secs_to_table": 9.12, "MB": 0.91}, "warm-browser": {"secs_to_table": 1.13, "MB": 0.01}}
```

**Firebase Hosting after about 21 min idle (§4.5).** The log records the probe, not the request
before it, so the interval is INFERRED:

```text
2026-09-28T09:03:44Z
scraper-cached /election/1932 200 ttfb=0.135535
x-cache: HIT
{"url": "https://uspv-explore-276.web.app/election/1932", "mode": "fast", "cold-browser": {"secs_to_table": 6.23, "MB": 0.87}, "warm-browser": {"secs_to_table": 0.75, "MB": 0.0}}
```

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

VERIFIED (agent H; the first two re-fetched raw by the parent during code review):
- *"F1 (default) 384 MB 600 MHz automatic"* (<https://cloud.google.com/appengine/docs/standard>);
- *"Python 3.14 Ubuntu 24.04 python314 2030-10-10"*
  (<https://cloud.google.com/appengine/docs/standard/lifecycle/support-schedule>);
- *"Oregon (us-west1)"* in the pricing region list.
- Custom domains: the apex is verified in Search Console even to map a subdomain, and with
  Cloudflare's CDN "Always use https" must be off (parent raw re-fetch,
  <https://cloud.google.com/appengine/docs/standard/mapping-custom-domains>).
- `max_instances`: *"Specify a value between 0 and 2147483647, where zero disables the setting"*
  (parent raw re-fetch, `app.yaml` reference). So `max_instances: 0` removes the cap; it does not
  stop the app.

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
| DigitalOcean App Platform | the free tier covers *"3 apps with static sites"*; a service is *"1 vCPU 512 MiB … $ 5.00"* | agent H (URL not recorded) |
| Azure Container Apps | *"The first 180,000 vCPU-seconds, 360,000 GiB-seconds, and 2 million requests per subscription per month are free"*; but *"Mapping to an intermediate CNAME value blocks certificate issuance and renewal. Examples … Cloudflare"* | agent H (URL not recorded) |
| AWS Lambda function URLs | a custom domain needs CloudFront in front (agent H, INFERRED) | — |
| Leapcell | *"$ 0 per seat / month"*, *"100,000 / month included"* invocations: one viral day could spend a month's allowance | agent H (URL not recorded) |
| Zeabur | bring-your-own server; not pursued (UNVERIFIED) | — |

Rows without a URL are agent H's quotes, which its condensed report kept without their URLs.
They concern ruled-out hosts and are not a basis for the decision.

---

## 7. Measured against quoted

For a reader re-weighting §2, this is which numbers came from a deployment and which from a page.

**MEASURED** (raw log in §5.4 where one was kept; the rest were read off the terminal and are
marked *log not preserved* where they appear):
- Cloud Run cold and warm TTFB (§5.4);
- App Engine warm TTFB and browser time-to-table (log not preserved), and its stacked case (§5.4);
- Firebase Hosting's first hit and CDN HIT (log not preserved), and its after-idle case (§5.4);
- the Dash probe's memory and page weight (log not preserved);
- server-rendered OG tags on three hosts;
- agent F's six browser-side builds;
- agent D's one Connect Cloud interstitial;
- the live `api.` Origin probes.

**Not measured, though the text relies on it:**
- the ~40-minute API idle interval before the stacked case;
- the ~21-minute idle interval before the Firebase after-idle case, and the state of the API's
  instance and edge during it;
- a cold App Engine instance: every App Engine run had the dashboard warm.

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
| **(d)** Browser-side dashboards get cached responses without CORS headers | **CONTRADICTED** | first mechanism MEASURED; second INFERRED; cause INFERRED | see below |

**Hypothesis (d) in full.**

The issue's reading of the app side is correct:
- Starlette sends no ACAO header on a request without an `Origin` (VERIFIED from source).
- The Worker caches `/v1` 200s through `caches.default` with `cache.match(request)` (VERIFIED,
  runbook §7).

**The measurement contradicts the conclusion.** MEASURED on 2026-09-28 at about 05:14 UTC,
`/v1/meta` from one client:
1. In the SEA colo, a request with no `Origin` returned HIT, `age: 74475`, with no ACAO.
2. Seconds later, **in the same colo**, a request with `Origin: https://explore.…` returned HIT with
   `age: 23`: a **distinct** entry.
3. In the PDX colo, an apex-`Origin` request returned HIT with `age: 23`, carrying
   `access-control-allow-origin: https://us-presidential-election-center.org` and `vary: Origin`.

**Mechanism 1 is CONTRADICTED (MEASURED):** a no-`Origin` fill is not served to a request that
sends an `Origin`.

**Mechanism 2 was not measured, and is INFERRED false.** It concerns two *allowed* origins, and
`explore.` is not in `API_CORS_ORIGINS`, so no request above came from a second allowed origin; the
apex entry was also seen in a different colo from the `explore.` one. That two allowed origins get
separate entries follows from the per-`Origin` keying measured in step 2, and from Cloudflare's
CDN documentation below.

**Why the edge keys on `Origin` is INFERRED.** Cloudflare documents, for its CDN cache, that *"Cloudflare supports
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

**What this section states.** Each item is a requirement and the issue that owns it. How each is
guarded or tested is that issue's to design (the owner's decision, 2026-09-28, on the code review
in §12). For each S1-lettered story it also names the phase, the change surface, and what the live
probe must demonstrate, as #276 asks.

**CORS allow-list: no change.**
- Server-to-server fetches carry no `Origin` and are not subject to CORS.
- `API_CORS_ORIGINS` stays apex-only, and no `*` decision is needed.
- The stale comment at `src/usvote/api/config.py:24-26` ("the exact dashboard origin is deferred
  (frontend D001)") should say instead that the dashboard is server-side and needs no CORS origin.
  It is a one-line change, carried by #284 or #277, whichever lands first. #284's notes say so,
  and §11 lists it for #277.
- **Hypothesis (d) needs no fix** (§8). If a browser-side component is ever added, adding its
  origin to `API_CORS_ORIGINS` should be enough. A no-`Origin` fill was measured not to reach an
  `Origin`-bearing request; that two allowed origins get separate entries is INFERRED (§8), so
  that story's canary should assert it.
- Server-side fetches share the canary's no-`Origin` cache entries, which helps.

**Rate limit (60/min/IP): no exemption needed, if the dashboard caches in-process.**
- **Requests per view.** The server fetches one canonical `/v1` URL per view on a cache miss, and
  none on a hit, filtering in-process (INFERRED from the design). Calls to `api.` are then bounded
  by distinct URLs per snapshot version, not by visits: about 150–250 URLs, against 60 per minute.
- **Requirements, owned by #277:**
  - an in-process cache of API responses, keyed on `snapshot_version` from `/v1/meta`, rechecked
    on a short TTL or by ETag (S3's AC requires one of the two);
  - one cache per instance, so one process;
  - first fills throttled below 60/min, since App Engine's egress IPs are shared Google ranges
    (INFERRED);
  - a throttled prefetch of the canonical URLs **on warmup and on every `snapshot_version`
    change**, swapping the cache atomically. The stacked cold case (9.12 s, MEASURED, §4.5) fails
    the MVP target, so this is a requirement, not an optimization.

**Edge caching.** The server should fetch canonical URLs only, so the Worker's per-URL cache serves
them. The query string is part of the cache key.

**Origin secret.**
- The dashboard reaches the API **only through `https://api.us-presidential-election-center.org`**,
  never `run.app` (D070(b)).
- It never holds the origin secret, which stays in Cloudflare and Secret Manager. That is #276's
  own API sub-question, answered here; D070(b) does not speak to the secret.
- #277 owns the guard. A source-text search alone would not see a base URL supplied by
  configuration.

**Value vocabularies: no API change is required.**
- D070(b) forbids `usvote` imports **at runtime** only.
- S2's AC lets the dashboard's *tests* import the vocabulary modules (`usvote.snapshot_schema`,
  `usvote.count_status`, `usvote.pv.status`) to assert that every closed value has a label
  (`backlog-dashboard.md`, S2 AC). With the code in this repo, that is the vocabulary check, with
  no `openapi.json` dependency.
- The AC calls those modules stdlib-only. `usvote.pv.status` is not: it imports numpy and pandas
  (`src/usvote/pv/status.py`, lines 41–42), so such a test needs the base dependencies. #277
  settles the consequence; #287 corrects the AC's wording and the same claim in `CLAUDE.md`.

**Workers quota.** The recommended design spends a negligible share of it. **Workers Paid ($5) is
not required**, though it would protect the API independently (**#285**).

### For the runner-up (Cloud Run + Firebase Hosting)

The same, plus one dashboard-side change: the app sets `Cache-Control: public, s-maxage=…` on GET
HTML and on Dash's fingerprinted assets through a Flask `after_request` hook.

### Result: S1-lettered stories

| Story | Change | Must precede | Change surface | What the live probe must demonstrate |
|---|---|---|---|---|
| **S1b, required** ([#283](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/283)) | **Scope the existing `uspv budget` to project `uspv-api`**. It has no project filter today (VERIFIED from the live config: no `projects` in `budgetFilter`), so dashboard spend would trip the API's kill-switch. **Give the dashboard project its own budget and kill-switch.** The kill-switch action is to **disable the App Engine app** (`USER_DISABLED`), never `max_instances: 0`, which App Engine documents as removing the cap (§6.7). `deploy/killswitch/` is Cloud-Run-only today (`run_v2.ServicesClient`), so it gains an App Engine action or a second function is deployed. The dashboard's least-privilege runtime service account is also #283's | Phase 0 go-live (#277) | **infra**: a PR for `deploy/killswitch/` plus a runbook entry, then a manual budget and function deploy | the API budget's filter lists only `uspv-api`; a below-threshold event on the dashboard's budget changes nothing; an over-threshold one disables the dashboard (`explore.` stops serving, its instances reach 0) while `api.`'s `/health` still returns 200; the un-pause step is run and documented. #283 designs the probe so that the "only the dashboard" half can fail |
| **S1a, optional** ([#284](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/284)) | Type `pv_status`, `electoral_count_status`, and the per-capita `coverage`, `boundary_basis` and `population_series` as `Literal[...]` in `src/usvote/api/models.py`, so `openapi.json` carries the closed sets. Justified by D031 (OpenAPI as a deliverable) and by any future non-Python consumer, not by the dashboard. A `Literal` turns an unexpected value into a response-validation 500, so it pins the snapshot vocabularies; consider an `API_VERSION` bump | none | **app code**: PR, CI, then a deploy run | `/openapi.json` on the public host shows the enums. #284 owns the drift test that pins each `Literal` to its source vocabulary |

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
- **The vocabulary check works offline.** The dashboard's tests can import the vocabulary modules
  directly (S2 AC), with no API change. One of them, `usvote.pv.status`, needs pandas (§9).
- **The portfolio story** is one repository showing the whole system.
- **Nothing is duplicated.** The dev loop, CLAUDE.md conventions and CI are reused.

**Costs, each with its owner (S2 unless noted):**
- CI installs `--dev` only, so add `uv sync --group dashboard`. `mypy` `files` and pytest
  `testpaths` need extending (the `tooling/` precedent).
- **Deploy root.** Make `dashboard/` the deploy root, holding `app.yaml` and a `.gcloudignore`, so
  the upload physically excludes `src/usvote/` and any git-ignored snapshot.
- **`requirements.txt`** is exported from the lock in CI, either uncommitted or committed with a
  drift check.
- **A guard that no runtime module under `dashboard/` imports `usvote`** (D070(b)); nothing goes
  under `src/usvote/`. #277 designs it. Because `usvote` is installed in the dev environment, the
  guard cannot rely on an import failing; `tests/unit/test_layering.py` shows the repo's pattern
  for that (a subprocess in which the forbidden package is made unimportable).
- **Accounts.** A WIF provider and deploy service account for the new project (S2). The
  least-privilege runtime service account, in place of App Engine's default (D034 §5), is #283's.
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

Requirements this verdict adds to #277. How each is guarded or tested is #277's to design.

**Host setup:**
- App Engine standard, F1, `python314`, us-west1, in a **new GCP project**.
- `min_instances: 1` and an explicit `max_instances: 1`, with warmup enabled.
- Delete the previous version after each promotion, since both settings are per version (§1
  item 1).
- Compressed responses (Dash's `compress=True`, which the probe used), since the egress estimate
  assumes them.

**Domain:**
- App Engine domain mapping through a DNS-only CNAME, with Search Console verification of the
  apex.
- Redirect `*.appspot.com` to `explore.`, and set `og:url` and a canonical link.

**Deploy:** GitHub Actions + WIF, `workflow_dispatch`, deploy root `dashboard/`, and
`requirements.txt` exported from the lock.

**Data access (§9):**
- the API only through its public hostname; never `run.app`, never the origin secret;
- no `usvote` import in runtime code;
- one in-process cache per instance, keyed on `snapshot_version`, with a TTL or ETag recheck;
- first fills throttled below 60/min;
- a throttled prefetch of the canonical URLs on warmup **and** on every `snapshot_version`
  change, with an atomic cache swap;
- the `config.py` CORS comment (§9), unless #284 has already carried it.

**Links:** shareable views are paths (Dash Pages), so their OG cards render.

**Provenance** comes from `meta.provenance`, the carry-forward constraint.

**Verification:**
- **The MVP cold-start target** (§4.5): OG HTML in ≤ 1 s TTFB, and a cold shared link to its first
  data cell in ≤ 3 s at 390 px on 10 Mbps / 100 ms, with the dashboard cold and with the API's
  edge cold. The API-edge-cold case should be measured after an API deploy, since that is when the
  edge is purged.
- A load test against `max_instances: 1` at a peak rate #277 states.
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

## 12. Architect review and code review

### 12.1 Architect review of the draft

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
| **I4**: the stacked cold start was not measured for the recommended option | Adopted: measured (§4.5), and a throttled warmup prefetch goes into S2. Since code review, it runs on warmup and on every `snapshot_version` change (§12.2) |
| **I5**: the DNS-only downside is unstated | Adopted: §1 item 4, §4.4, and a flip condition |
| **I6**: most pricing quotes have no URL | Adopted: URLs inline throughout §6 |

**Minor:**

| Finding | Disposition |
|---|---|
| M1–M6 (matrix scoring) | C1 made cost-only on a stated scale; rows re-scored; the dealbreaker column cleaned up. Superseded by the per-column rubrics and re-scoring after code review (§12.2) |
| M7 (the (d) label) | Now MEASURED; mechanism INFERRED |
| M8 (banner conditional) | Made conditional on *k* |
| M9 (LinkedIn label) | Excluded as a signal. The label was first changed to UNVERIFIED; code review restored agent G's CONTRADICTED (§12.2) |
| M10 (pydantic overlap) | Reworded in §10 |
| M11 (cross-references) | Fixed; a GitHub Pages comparison is added to §6.6 |
| M12 (checklist D071) | Fixed |
| M13 (Streamlit on the recommended host) | VERIFIED: App Engine standard has no websockets |
| M14 ("≈ $0") | Adopted |
| M15–M17 (S2 items) | Added to §10 and §11 |
| M18 (lock-in) | A sentence in §1 item 2 and §4.2 |

**One further suggestion** was to file Workers Paid as a separate API-resilience issue. The owner
filed it as **#285** (§4.1).

### 12.2 Code review, round 1 (PR #286)

Three read-only finders reviewed the committed draft: internal consistency, guard efficacy, and
factual accuracy against the sources. They returned **42 findings, all blocking**, most of them about
a claim that was false, overstated or mislabelled. Several raised design questions, so the
architect gave a scope ruling and the owner decided them before any fix (2026-09-28). The ruling
kept the recommendation: none of the 42 changes the choice.

| Root cause | Findings | Disposition |
|---|---|---|
| Summary layers dropped their sections' qualifiers | "never cold-starts"; the 6.2 s cause stated as fact; hypothesis (d)'s second mechanism; the Custom Domain failure mode; the Streamlit reasons; the source for "never holds the secret"; flip lists that differed between §1 and D071; a warmup-only prefetch | Fixed in the banner, §1, §4, §8, §9 and D071. The prefetch now runs on warmup and on every `snapshot_version` change |
| Only C1 had a rubric | C3-host scores against their own source, uneven C4–C7 cells, §4.7's "every host scores 5", the viral-day cost of Render Starter | Every column has a rubric (§2); the matrix is re-scored. The owner set the C3-host rule to the parent platform's share, so App Engine and Cloud Run tie and the host-marketability flip condition is dropped |
| Section-level labels | §4.6 "all VERIFIED"; LinkedIn relabelled without new evidence; the parent re-fetch list; runtime sources in §5.3; the 390 px claim; §4.4's attribution; release-notes versus PyPI; unpreserved logs | Per-cell labels; CONTRADICTED restored; three App Engine pages re-fetched and the list corrected; logs reproduced in §5.4 or marked as not preserved |
| The doc re-specified other stories' guards, and three of those specifications were false | an import guard said to mirror `test_api_import_graph.py` (that test is a regex search, not an AST scan); `max_instances → 0` as a kill-switch (App Engine reads 0 as no cap); `usvote.pv.status` called stdlib-only (it imports pandas); mis-paired line numbers for #284's fields | The three claims are removed. §9 and §11 now state requirements and their owning issue. **Deferred by the ruling, as the owner accepted:** guard and probe designs to #277 (dashboard guards, version-cleanup check, load test, prefetch measurement), #283 (kill-switch action and probe design, runtime service account) and #284 (the `Literal` drift test). The `CLAUDE.md` and backlog "stdlib-only" wording goes to #287. The #283 and #284 bodies were corrected the same day |
| Coverage claims beyond the content | §3's "built each one"; hosts named in §3 but missing from §6.9; §14's "done" for the runner-up's stacked case; partial answers on hard caps, sleep policies and per-view requests | §3 and §6.9 corrected; §4.1 and §4.5 extended, with UNVERIFIED cells for ruled-out candidates (the owner's decision); §9 states requests per view; §14 marks the runner-up's case partial |
| No cold-start target | S2's AC measures "against S1's target", and S1 set none | The owner set the MVP target (§4.5) |

### 12.3 Code review, rounds 2 and 3

A fresh checker re-read the whole change after the fixes. It found the round-1 findings discharged
or deferred as ruled, and returned 12 new or residual ones (11 blocking, 1 editorial): an
overstated claim that measured runs met the cold-start target, a Streamlit rationale that named
different criteria from its reasons, stale or unlabelled statements in §3, §4.1 and §9, a host rule
whose wording excluded the runner-up, matrix cells that did not follow their rubrics, missing
sleep-policy rows, an unlogged idle interval shown as measured, and an uncheckable count in §12.2.
The owner authorized a third round, and chose to keep App Engine's ease score at 4 with its costs
listed (§2, §4.2). All 12 were fixed; a fresh checker reviews the fixes.

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
| Measured cold starts for the two finalists, including the stacked case | **Done for the recommendation** (§4.5, §5). **Partial for the runner-up:** its after-idle browser case (6.23 s) was measured, but the dashboard-cold and API-edge-cold parts were not isolated. By the owner's decision (2026-09-28) it is not re-deployed; it stays the pivot option |
| Cold-start target stated | Done (§4.5): the MVP target, set by the owner |
| Cost at both traffic levels, hard cap and card for every candidate | Done (§4.1), with UNVERIFIED cells for ruled-out candidates |
| Sleep policy per platform | Done (§4.5), with the same allowance |
| Per-view request count against the 60/min limit | Done (§9) |
| Pricing quoted verbatim with URL; parent re-fetch list stated | Done (top, §6) |
| Throwaway deployments torn down | Done (§13) |
| Architect review recorded | Done (§12.1) |
| Code review round 1 recorded, with dispositions | Done (§12.2) |
| Code location recommended | Done (§10) |
| Accepted verdict recorded as D071 | Done (`decisions.md`, this PR) |
| S1-lettered stories filed | Done on 2026-09-28, after the owner reviewed the list: S1b **#283**, S1a **#284**; and #285 (Workers Paid, under E8). Both S1 bodies were corrected after code review; #287 carries the `CLAUDE.md` and backlog wording |
