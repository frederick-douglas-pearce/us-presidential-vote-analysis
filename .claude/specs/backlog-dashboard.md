# US Presidential Vote Analysis — Public Dashboard Backlog (E9, re-scoped)

> **Status: REVIEWED — scoped by the `pm` agent from Fred's product calls, reviewed by the
> `architect` agent (verdict: file after edits, all applied), open questions settled by Fred
> 2026-09-27.**
>
> This backlog re-scopes **E9**. `docs/ROADMAP.md` named it "Analytical explorer data mart";
> it never had an epic label or issues [F11]. The mart is **deferred under YAGNI** (D070).
> E9 becomes the **public dashboard**, the front end of D001's what-if explorer, and it
> consumes the **live public API** rather than a copy of the data.
>
> **The whole backlog is gated on E9-S1**, a platform research spike, in the way #180 gated
> the census epic. S2–S5 are specified in full because their *product* shape does not depend
> on the platform, but their *implementation notes* are provisional until S1 lands.
> S6–S8 are placeholders, **shape gated on the research spike and Phase 1**, and stay
> **unfiled tracker rows** until Phase 1 ships.
>
> S1's accepted verdict is recorded as **D071** (confirm the free slot at recording time —
> the census backlog drifted by six slots between drafting and recording).

Each `E9-SN` section below is a GitHub issue body ready to paste. Citations like [F5]
point to the [Repo facts](#repo-facts) table at the bottom of this file. **R** in that table
means the fact was read in the repo; **I** means it was inferred and not checked.

---

## Label conventions

- Epic label: **`epic:dashboard`** (new).
- Type labels (existing): `research`, `enhancement`, `infrastructure`, `documentation`, `testing`.
- Priority labels (existing): `priority:high` / `priority:medium` / `priority:low`.

---

## Product frame (settled by Fred, 2026-09-27)

1. **No data mart now (YAGNI).** New data shapes are built only when a concrete chart or
   table needs them. Because the serving side never touches Postgres (D028), "mart objects"
   in practice means **new snapshot tables or new `/v1` endpoints**, each filed as its own
   story that names the chart that needs it.
2. **The dashboard reads the public API.** It ships no copy of the data. There is one
   source of truth, and the project's own API is its first real consumer. This meets
   D002's MVP bar, "the API powers our app", literally.
3. **Audience: non-technical readers first.** Sharing is the goal: a link that opens fast,
   reads plainly, unfurls with a preview card and reopens the exact view the sender saw.
4. **Phases:** 0 walking skeleton → 1 raw data tables with filtering (which also serve as
   the debugging view for later charts) → 2 charts and metrics → 3 narrative tabs →
   4 landing page.
5. **Settled answers:**
   - Epic number: **reuse E9**, label `epic:dashboard`.
   - Cost: **target $0/month, hard ceiling $10/month.**
   - Host name: **`explore.us-presidential-election-center.org`**. Further sibling
     subdomains may come later (for example a possible AI chat feature).
   - E9 is the dev loop's next active epic: S1 `priority:high`, S2–S5 `priority:medium`.
   - Python is a weighted criterion, third in order, **with the caveat that this is a
     portfolio project**: Python is Fred's primary language and the choice must be
     marketable for his career.
   - Filing: the epic plus S1–S5 as issues; S6–S8 stay unfiled tracker rows.

### Carry-forward constraints (apply to every story)

- **Provenance on every public surface.** NARA / US-PD (Electoral College), MIT Election
  Lab / CC0 (popular vote), USCB / US-PD (census). Render it from `meta.provenance` [F8]
  rather than hardcoding it, so it cannot drift from the snapshot being served.
- **A null popular vote is never shown bare.** Every `ec_pv` row carries `pv_status`
  [F7]; year-level views use `has_popular_vote` / `coverage` [F9]. Popular vote exists
  only 1976–2024 on the public surface; EC data covers 1824–2024. Take both windows from
  `meta.provenance.coverage`, never from literals.
- **UCSB never appears, and this is structural.** The dashboard's only data input is the
  public API, whose snapshot is redistributable-only at the source (D030). A dashboard
  that bundles no data and reaches no data source but the API has no route to a UCSB byte.
  S2 makes this a guard, not a convention.
- **Editorial guardrail:** nothing critical of a data source is published, including in
  column help text, empty-state wording and narrative tabs. The wording describes what the
  dataset holds ("not in this dataset before 1976"), not a fault in a source.
- **Public-facing copy** (labels, help text, narrative) gets a `marketer` draft/review
  pass per the repo's convention. The label tables below are functional specs, not final
  copy.

---

## Epic tracker

The tracker issue is `Epic: public dashboard over the live API — the what-if explorer's
front end (E9)`.

**Dependency graph:** S1 gates everything. Any API or infrastructure changes S1 identifies
are filed as **S1a, S1b, …** and sequenced before the phase that needs them. Then
S2 → S3 → {S4, S5} (S4 and S5 are independent of each other once S3 sets the shared
conventions) → S6 → S7 → S8.

---

### E9-S1: Platform research spike

**Issue title:** Research the dashboard platform: cost, custom domain, cold start, shareable URLs, and API fit
**Labels:** `epic:dashboard`, `research`, `priority:high`

**Body:**

### Summary

Choose the dashboard platform and host **before any dashboard code is written**. D001
deferred the frontend host; D070(e) lifts that deferral *pending this spike's verdict*.
The deliverable is a written recommendation at
`.claude/specs/research-dashboard-platform.md`, in the house style of
`research-census-source.md` / `research-pv-source.md`. **This story gates every other E9
story**, and its finding may re-cut S2's implementation notes in particular.

**This is a research spike, not code.** Like #180 and #13, its deliverable is a written
finding. It is accepted when the document answers the questions below with labelled
evidence, not when a test suite passes. **The architect agent reviews the recommendation
before it is accepted.**

### Acceptance Criteria

**Document shape**
- The doc lands at `.claude/specs/research-dashboard-platform.md` with: a status banner; a
  date/method line; an evidence-label legend; **§1 Recommendation, readable on its own**;
  §2 head-to-head matrix; per-criterion and per-candidate sections; a "none of the above"
  scan; a hypotheses verdict section; the API sub-question section; per-story consequences
  ("what this unblocks"); and a closing checklist.
- **Evidence labels** follow `research-faithless-electors.md`: **VERIFIED** (primary source
  fetched and read — vendor docs, pricing page, changelog; URL plus retrieval date) /
  **ATTRIBUTED** (a named secondary source says so) / **UNVERIFIED** / **CONTRADICTED**. A
  claim is never moved from one label to another without new evidence. Pricing and
  free-tier limits are **quoted verbatim** with URL and date, like the §3 licensing table
  in `research-pv-source.md`, because they change.

**Candidates (each evaluated, none assumed)**
- Streamlit on Streamlit Community Cloud; Dash on Render; Gradio on Hugging Face Spaces;
  Shiny for Python on Posit (shinyapps.io and any newer Posit hosted offering);
  **self-hosting on the existing Cloud Run + Cloudflare setup**, reusing `deploy.yml`'s
  WIF pipeline and the budget kill-switch [F16].
- **"None of the above"** is scanned seriously, including at least: Python-in-the-browser
  builds served from a static host (e.g. stlite, Shinylive, PyScript/Panel-on-Pyodide) on
  **Cloudflare Pages** (same zone as the API, no Host-rewrite problem) or **GitHub Pages**,
  which change the cost and cold-start picture completely; framework-on-Cloud-Run
  combinations other than the named pairing (e.g. Streamlit or Dash on Cloud Run); and a
  non-Python static-site option, as a control.

**Criteria, in Fred's priority order, each scored per candidate**
1. **Cost (primary). Target $0/month, hard ceiling $10/month.** Monthly cost (a) at
   near-zero traffic and (b) on a viral day, e.g. a shared link getting ~10k visits (the
   spike picks and states the number). State whether a **hard cap** exists or overage is
   possible, and what card-on-file exposure a free tier carries. Include the cost of any
   mitigation the other criteria force, such as paying to avoid sleep. **Size the viral day
   against the Cloudflare Workers free-plan daily request quota, which the API proxy
   (`usvote-api-proxy`) already consumes** [F5]. State what happens when it is exhausted:
   a Custom-Domain Worker has no origin to fall back to, so running out could take down the
   public API, not only the dashboard. Include any second Worker the dashboard needs.
2. **Ease of implementation and maintenance.** Deploy path (CI, reproducible, not tied to
   a laptop), whether the view logic can be unit-tested offline in CI, dependency weight,
   upgrade churn and lock-in.
3. **Python-based and marketable — this is a portfolio project.** Score the **authoring
   framework** and the **runtime/host** in separate columns: what goes on a CV is the
   framework (stlite is Streamlit code on a niche runtime). Adoption and marketability
   claims must be **ATTRIBUTED** to a named source (a survey, job-board counts, the
   vendor's customer list), not asserted.
4. **Custom domain.** Can it serve `explore.us-presidential-election-center.org` on the
   tier being recommended? Verify the mechanics with **Cloudflare DNS** specifically,
   proxied vs DNS-only. D035 is the precedent: a proxied CNAME to a platform that routes by
   `Host` 404s unless the Host is rewritten, and the free plan paywalls the Host override.
5. **Cold start.** Sleep policy per platform, with source. A **measured**
   time-to-first-meaningful-render for a cold shared link **for the two finalists**, and for
   any other candidate that can be stood up for free in minutes. Measure the *stacked* case
   too: a sleeping dashboard **and** an API URL not yet in the edge cache (the API is
   scale-to-zero, and each uncached URL wakes its origin [F5][F6]). State what it would cost
   to buy the cold start away.
6. **Sharing: shareable URLs and link previews.** Can the framework read and write the
   query string to restore state, and does that survive the hosting setup (iframe
   embedding in particular tends to break it)? Can a page set **Open Graph tags per URL**,
   so a shared link unfurls with a card? The posts already invest in OG cards, and
   non-technical sharing happens mostly in chat and social apps.
7. **Forward compatibility (low weight — a tie-breaker only).** A possible AI chat feature
   would live on a **sibling subdomain as its own service**. Does this platform prevent
   adding a server-side component later, and would a separate chat service need anything
   from this choice (a shared backend, auth, the same API quota)? A static or browser-side
   platform is **not** penalized for holding no secret, because the chat is expected to be
   its own service.

**Also report (not scored):** phone-width rendering, keyboard and screen-reader support in
the table widget (a platform property that is hard to change later), and whether the
platform supports cookie-less usage analytics.

**Hypotheses to test, not findings.** Each gets an explicit verdict and label.
- (a) Streamlit Community Cloud serves only `*.streamlit.app`, with no custom domain. If
  true, evaluate the iframe-embed workaround's effect on criteria 5 and 6.
- (b) A Cloud-Run-hosted dashboard at `explore.` does **not** pass through the API's
  Worker, which is bound to `api.` [F5]. It hits D035's Host-routing 404 again and needs
  its own Host-rewriting front (a second Worker, or Cloud Run domain mapping if available
  in-region). Verify that such a front proxies websockets (Streamlit), and whether Cloud
  Run's request timeout caps websocket session length (the API service runs with
  `--timeout=30` [F6]). Dash's layout and assets are cacheable GETs, but its callbacks are
  believed to be POSTs, which are not edge-cacheable (INFERRED).
- (c) Gradio is oriented to ML demos and is a weaker fit for a BI-style dashboard.
- (d) **Expected for any browser-side option: a cached response without CORS headers.**
  Starlette's `CORSMiddleware` adds no `Access-Control-Allow-Origin` and no `Vary` to a
  request that carries no `Origin` [F4], and the Worker caches `/v1` 200s by URL [F5]. The
  deploy smoke test (`deploy.yml`) and the daily canary (`api-canary.yml`) fill canonical
  `/v1/meta` and `/v1/elections/2000/summary` without an `Origin` [F17] — and `/v1/meta`
  is the URL S2's skeleton plans to call. A second mechanism: with two allowed origins
  (apex plus `explore.`), Starlette echoes the specific caller's origin, so whichever origin
  fills a URL first breaks it for the other. `caches.default` is local to each data center,
  so the failure depends on geography. Verify with
  `curl -H 'Origin: https://explore.us-presidential-election-center.org' -D- <canonical URL>`.
  **None of this applies to a server-side dashboard**, where no CORS is involved.

**The API sub-question (required section).** For the recommended option, and briefly for
the runner-up: what API or infrastructure change, if any, is needed? Cover at least:
- **CORS allow-list:** add the dashboard origin to `API_CORS_ORIGINS` [F4] (today it holds
  the apex only), or decide on an explicit `*` for this unauthenticated, read-only,
  no-credentials API. **`*` alone does not fix (d)**: the fix must apply on cache hits as
  well as misses — the Worker sets the header on every `/v1` response, or `Origin` joins
  the cache key, or the app emits the header unconditionally. Choosing `*` is a recorded
  decision (D031 forbids a *silent* wildcard) and means amending the runbook §7 "never `*`"
  row and the `config.py` comment.
- **Rate limit (60/min/IP [F5]):** a server-side dashboard on shared hosting sends every
  visitor's requests from a few egress IPs, while a browser-side dashboard bursts from each
  visitor. Size the per-view request count against the limit, and say whether the dashboard
  needs an exemption or server-side caching.
- **Edge caching:** the query string is part of the cache key [F5], so filtering inside the
  dashboard on one fetched resource beats a request per filter change. Also hypothesis (d).
- **Origin secret:** confirm the dashboard reaches the API **only through the public
  hostname**, never `run.app` with the secret. The secret stays in Cloudflare and Secret
  Manager.
- **Value vocabularies:** `pv_status` and `electoral_count_status` are typed `str` in the
  API models, not `Literal` [F18], so `openapi.json` does not carry their closed value
  sets. Say whether the dashboard needs them to (see S2's guards and the code-location
  question).
- **Result:** a list of zero or more changes, each filed as its own story **S1a, S1b, …**
  naming the phase it must precede and **its change surface**:
  - app code: PR, CI, then a deploy run;
  - a GitHub variable (e.g. `API_CORS_ORIGINS`): a deploy run with no PR, which purges the
    edge;
  - the Cloudflare Worker: a manual edit whose only record is the runbook §7 snippet, so
    **the same PR updates that snippet**.
  Each S1-lettered story is accepted by a **live probe**, not by merge. The stale
  "exact dashboard origin is deferred (frontend D001)" comment in `src/usvote/api/config.py`
  is updated by whichever story settles the origin.

**Verdict**
- A recommended platform and host, a runner-up, and **the condition that would flip the
  choice**.
- A recommendation on **where the dashboard code lives**, weighing:
  - **In this repo:** one universal `uv.lock` with `uv sync --locked` in CI on Python 3.14,
    so a framework's pins or missing 3.14 wheels constrain the pipeline's resolution; a
    dedicated dependency group, never `serve` or the base dependencies (D033); no dashboard
    code under `src/usvote/`; `mypy files` and `testpaths` need extending (the `tooling/`
    precedent); CI's `--dev` does not install a new group; its own Dockerfile if it has a
    container, since CI's `docker-build` job builds the root one.
  - **In a separate repo:** no lock coupling, but no offline vocabulary check unless an
    S1-lettered story turns the API's `pv_status`/`electoral_count_status` into `Literal`
    types; CLAUDE.md conventions and the dev-loop setup to be duplicated.
- **Architect review is recorded** as a comment on this issue or a section of the doc, and
  the accepted verdict is recorded as **D071** in `decisions.md`.

### Implementation Notes

- Reuse the census spike's method: parallel read-only research per candidate plus one
  cross-cutting pass, each returning per-claim URLs and a label. The parent independently
  re-fetches the pricing pages the recommendation depends on, and the doc says which
  artifacts were re-fetched (the census doc's "verification limit" paragraph is the model).
- A **measured** cold start beats a quoted one. Throwaway deployments are fine; tear them
  down and say so.
- Keep criteria scoring separate from the recommendation. A reader should be able to
  re-weight the matrix and see whether the verdict survives.
- Timebox: two working sessions plus the architect review.

### Dependencies

- None. **Gates E9-S2 through E9-S8.**

_Story of epic #N (E9 — public dashboard)._

---

### E9-S2: Phase 0 — walking skeleton

**Issue title:** Deploy a walking-skeleton dashboard at explore.us-presidential-election-center.org that reads the live API
**Labels:** `epic:dashboard`, `infrastructure`, `priority:medium`

**Body:**

> **Implementation gated on E9-S1.** The product ACs below are settled. The host, deploy
> mechanism and code location come from S1's verdict and will be filled in when it lands.

### Summary

Stand up the thinnest possible dashboard **end to end**: a bare page on the chosen host,
served at `explore.us-presidential-election-center.org` over HTTPS, deployed by CI, making
**one live call to the public API** and rendering the result. The point of a walking
skeleton is to prove the riskiest integration first: custom domain, deploy pipeline, and
the browser-or-server → Cloudflare → API path, with its CORS, rate-limit and cache
behavior. That comes before any table or chart depends on it.

### Acceptance Criteria

- **Given** a reader opens `https://explore.us-presidential-election-center.org`, **then**
  the page loads over valid HTTPS at that hostname. There is no redirect to a vendor
  domain, and the vendor domain does not show in the address bar.
- The page makes **one live request** to the public API (`/v1/meta`, or `/v1/elections`
  if S1 prefers) and renders:
  - the three provenance lines, each naming the source and linking its license, built
    from `meta.provenance` [F8];
  - the two coverage windows (EC 1824–2024; popular vote 1976–2024), read from
    `meta.provenance.coverage`, not literals;
  - the `snapshot_version` (small print, for debugging).
- **Degraded state:** **given** the API is unreachable or errors, **when** the page loads,
  **then** it shows a plain-language message, not a stack trace or a blank page.
- **The page renders legibly at phone width.**
- **Deploy is automated and reproducible:** merging to `main`, or a documented one-click
  workflow per S1, deploys, with no laptop step. If the host is GCP, the human-gated
  `production` environment pattern from `deploy.yml` is followed or explicitly declined in
  the runbook.
- **Structural "one source of truth" guards** (in whichever repo S1 chooses):
  - Runtime code's **only data input is HTTPS to one configured API base URL**.
  - No `run.app` reference anywhere in the dashboard.
  - **No data files** (`.sqlite`, `.csv`, `.json` data, snapshot copies) in the runtime
    tree. Recorded API responses used as test fixtures are allowed, and a test asserts that
    runtime code never reads them (the `ec_state_roster_by_year.json` precedent).
  - For a Python frontend, **no `usvote` import in runtime code**, guarded on the
    `tests/unit/test_api_import_graph.py` pattern. Tests *may* import the vocabulary
    modules to assert that every closed value has a label: `usvote.snapshot_schema` and
    `usvote.count_status`, which are stdlib-only, and `usvote.pv.status`, which imports
    numpy and pandas, so a test importing it needs the base dependencies installed (#287).
- **API prerequisites from S1 have landed:** every S1-lettered change marked "before
  Phase 0" (e.g. the dashboard origin in `API_CORS_ORIGINS`, the CORS/cache fix if
  hypothesis (d) is confirmed) is merged, deployed, and for Cloudflare-side changes applied
  with the runbook updated — each verified by a live probe, which the skeleton's own live
  call also exercises.
- **Cold start is measured and recorded:** time-to-first-render for a cold shared link,
  covering both dashboard-cold and API-edge-cold, against S1's target, in the PR
  description.
- **Cost guardrails in place:** the deployment sits inside the $10/month ceiling. If it is
  on GCP, it is covered by the budget alert and kill-switch [F16]; if it is on a vendor
  free tier, the runbook states the overage exposure.
- **Monitoring:** the existing daily canary [F17], or an equivalent, also probes the
  dashboard URL. The #148 lesson is that a public surface nobody probes can stay broken for
  weeks. **For a browser-side dashboard**, the canary also sends
  `Origin: https://explore.us-presidential-election-center.org` to the canonical API URLs
  and asserts the returned `Access-Control-Allow-Origin`, which turns hypothesis (d) and a
  blank-variable fallback to the localhost list [F4] into a guarded regression.
- **Runbook:** `docs/deploy-dashboard.md` covers provisioning, DNS/Cloudflare wiring,
  redeploy and rollback, in the style of `docs/deploy-cloud-run.md`.

### Implementation Notes

- The skeleton carries no tables. Resist adding "just one": the next story owns that.
- Do not rename or restructure anything on the API side here. API changes arrive only as
  the separately filed S1-lettered stories.
- `docs/deploy-cloud-run.md` §0 expected the dashboard at the apex or `www` on GitHub
  Pages [F12]. Update that sentence in the same PR.
- Avoid editing CLAUDE.md in this story while a dev-loop run is active (prompt-cache
  invalidation). File the CLAUDE.md pointer as a follow-up docs issue, as #271 did for
  D069.

### Dependencies

- E9-S1 (platform verdict); any S1-lettered story marked "before Phase 0".

_Story of epic #N (E9 — public dashboard)._

---

### E9-S3: Phase 1a — elections index and one-election tables

> **Filed as #278, then split (2026-10-02).** #278 is closed as superseded; the body below is
> the pre-split text, kept for reference. The live stories are:
> - #305 (S3a): cache and routing for pages that read more than one path. Merged via PR #313.
>   Its canonical-link item moved to #312, and its function-derived prefetch to #310.
> - #312: canonical link, `og:url` and 404 from the matched page, and validating a path
>   variable before it reaches an API path. Lands before #306 and #307.
> - #306 (S3b): the elections index (T1) and the shared table conventions.
> - #307 (S3c): the one-election view (T2 + T3) at `/election/<year>`.
> - #308 (S3d): the election panel and T3's hybrid columns.
> - #309: CSV download of the filtered table, for every table.
> - #310: measure cold year-page links, and widen the prefetch if they miss D071(g).

**Issue title:** Add filterable election tables: the elections index and the one-election view
**Labels:** `epic:dashboard`, `enhancement`, `priority:medium`

**Body:**

> **Implementation gated on E9-S1 and E9-S2.** Table content and ACs are settled here;
> widget and state mechanics follow the platform.

### Summary

The first real content: raw, filterable tables for **the list of elections** and **one
election in full**. They are deliberately close to data dumps. They let a reader look up
any election, and they are the **debugging view** every Phase 2 chart will be checked
against. This story also sets the **shared table conventions** (null labelling, count
status, provenance footer, shareable URL state, column glossary) that S4 and S5 reuse.
It sets them as a working vertical slice, not a separate framework story.

**Tables and endpoints** [F1]

| View | Table | Endpoint | Filters |
|---|---|---|---|
| Elections | T1 — elections index (year, candidate count, has popular vote) | `GET /v1/elections` | year range; "has popular vote" toggle |
| One election | T2 — state-by-candidate results | `GET /v1/elections/{year}` → `data` | **year (required)**; state; candidate; `pv_status`; electoral count status |
| One election | T3 — national results per candidate | same response → `summary` | year (inherited) |
| One election | Election panel — winners under each method, flips, margins, EC majority | same response → `election` | year (inherited) |

All of the one-election view comes from **one API call** [F1]. Clicking a year in T1
opens that election's view.

### Acceptance Criteria

**Content**
- T1 lists every served year. T2, T3 and the election panel render for any served year,
  1824–2024.
- **Plain-language column headers**, with the raw API field name available to a reader who
  wants it (tooltip or toggle), because these tables double as the debugging view. Headers
  follow the public field names (`state_electoral_votes`, `electoral_votes`,
  `electoral_votes_counted`, `popular_votes`, …), not internal snapshot column names.

**A null is never bare.** Popular-vote cell labelling (functional spec; final copy goes
through the marketer pass and the editorial guardrail):

| `pv_status` | year vs. `pv_year_min` | `popular_votes` | cell shows (proposed) |
|---|---|---|---|
| `legislature_chosen` | any | null | "No popular vote: the state legislature chose the electors" |
| `not_participating` | any | null | "Did not take part in this election" |
| `popular_vote` | before window | null | "Popular vote held; not in this dataset before 1976" (year from `coverage`) |
| `popular_vote` | inside window | null | "No popular-vote figure for this candidate in this state" |
| `popular_vote` | inside window | value | the number |

- **Given** 1860, **when** T2 renders, **then** South Carolina's rows show the legislature
  label and New York's rows show the before-window label. The two nulls read
  differently [F7].
- **Given** 2016, **when** T2 renders, **then** each row for a candidate who received
  electoral votes but has no MIT figure shows the inside-window null label, never `0`,
  never blank.
- **Given** a pre-1976 year, **when** T3 renders, **then** the popular-vote columns carry
  a **year-level** explanation from `has_popular_vote`/`coverage` (T3 has no `pv_status`,
  by design [F9]).
- `party` is NULL outside the popular-vote window **or where the popular-vote source has
  no figure** [F7]. It shows a labelled empty state, not a blank.

**Electoral count status**
- **Given** 1872 or 1868, **when** T2 renders, **then** every row whose electoral count
  status is not `counted` shows the status and the Archives' reason sentence verbatim. T3
  shows both cast and counted national totals against the appointed denominator (e.g.
  1872 Grant, 300 cast / 286 counted of 366 appointed).

**Election panel**
- Flips, the popular-vote and hybrid winners, and `pv_margin` / `hybrid_margin` that are
  null (pre-1976) show "not applicable: no popular vote in this dataset for this year".
  They are **never** rendered as "No", `false` or `0`.
- `pv_coverage` is populated for **every** year (D053). It measures the share of electoral
  votes appointed by popular-vote states, not this dataset's coverage, and its label says
  so.
- **Given** 1824, **then** the EC-majority field reads as "no candidate reached a majority
  of electors appointed", a real answer, not a missing value.

**Shared conventions (reused by S4/S5)**
- **Shareable URL:** every filter and the selected year live in the URL. **Given** a URL
  copied from a filtered view, **when** it is opened in a fresh browser session, **then**
  the same table with the same filters renders.
- **Provenance footer** on every view, from `meta.provenance` (S2's component).
- **Request budget:** changing a filter within a view issues **no new API request**. The
  dashboard filters the resource it already fetched, which keeps edge-cache hits high and
  stays under the per-IP rate limit [F5]. A server-side cache revalidates by ETag or has a
  time limit, so a D034 snapshot cutover reaches the dashboard.
- *(Should)* **CSV download** of the currently filtered table, with an attribution line
  or columns carrying source and license.
- Offline tests cover label derivation and the URL-state round trip, against recorded API
  fixtures. No test hits the live API in CI.

### Implementation Notes

- Derive the popular-vote window from `meta.provenance.coverage.pv_year_min`, never the
  literal 1976. The same goes for the EC window. A new election cycle must not need a code
  edit.
- `party` is empty before 1976 because the public surface takes party from the
  popular-vote source [F7]. Non-technical readers will expect a party. **Surface the gap
  honestly in Phase 1. Do not fix it here.** If a Phase 2 chart needs pre-1976 party, that
  becomes the first concrete-need API addition under D070(c), filed as its own story.
- The API's `state`/`candidate` query filters exist, but prefer in-dashboard filtering of
  the full year payload (see Request budget). A year is well under `MAX_ROWS` [F3].
- Streamlit re-runs its script on every interaction, so the request budget implies
  explicit caching there.

### Dependencies

- E9-S2. Any S1-lettered story marked "before Phase 1".

_Story of epic #N (E9 — public dashboard)._

---

### E9-S4: Phase 1b — state and candidate histories

**Issue title:** Add filterable state-history and candidate-history tables
**Labels:** `epic:dashboard`, `enhancement`, `priority:medium`

**Body:**

> **Implementation gated on E9-S1; reuses E9-S3's conventions.**

### Summary

Two views across years, reusing S3's labelling and URL conventions:

| View | Table | Endpoint | Filters |
|---|---|---|---|
| One state | T4 — the state's rows across every election | `GET /v1/states/{usps}` | **state (required)**; year range; candidate; `pv_status` |
| One candidate | T5 — the candidate's rows across every election | `GET /v1/candidates/{slug}` | **candidate (required)**; year range; state |

### Acceptance Criteria

- T4 renders for any state or DC, across its served elections, with S3's null and
  count-status labelling. **Given Georgia**, **then** 1864 shows the not-participating
  label and 1868 shows `disputed` with the Archives' reason sentence verbatim (D044).
- T5 renders for any candidate slug. The candidate picker needs **no API change**: the
  reader picks a year, then a candidate from that year's T3 list. Deep links by slug work
  directly.
- The state picker is derived from the latest election's payload (`year_max` from
  `meta.provenance.coverage`), since every state and DC takes part in it. There is no
  second copy of the state roster (D006).
- Shareable URLs and the request budget behave as in S3. The year range is carried in the
  URL.
- Offline tests as in S3.

### Implementation Notes

- **No candidate-index endpoint exists** [F2]. The year-first picker avoids needing one. If
  readers need to search candidates by name across all years, a `/v1/candidates` index is a
  legitimate concrete-need addition under D070(c). File it then, not now.
- The API's `year_from`/`year_to` filters reject an inverted range with a 422 [F1]. The
  dashboard should prevent an inverted range rather than surface the error.

### Dependencies

- E9-S3.

_Story of epic #N (E9 — public dashboard)._

---

### E9-S5: Phase 1c — per-capita tables

**Issue title:** Add filterable per-capita tables by election and by state
**Labels:** `epic:dashboard`, `enhancement`, `priority:medium`

**Body:**

> **Implementation gated on E9-S1; reuses E9-S3's conventions.**

### Summary

Persons per electoral vote, from the census series shipped in #245:

| View | Table | Endpoint | Filters |
|---|---|---|---|
| One election | T6 — every state's persons per electoral vote | `GET /v1/elections/{year}/per-capita` | year (required); state |
| One state | T7 — one state across elections | `GET /v1/states/{usps}/per-capita` | state (required); year range |

T6 sits as a tab or section of S3's one-election view, and T7 of S4's one-state view, so a
shared link lands where a reader expects it.

### Acceptance Criteria

- Columns show governing census year, electoral votes (state total), population, boundary
  basis, coverage and persons per electoral vote, with plain-language headers.
- **A null ratio is never bare** [F10]:
  - **Given** 1848, **then** Texas shows "no census figure governs this election" (from
    `coverage='no_governing_figure'`).
  - **Given** 1864, **then** each zero-allotment state shows "no electoral votes this
    election", not a blank or an infinity.
- `governing_census_year` is shown, so a reader can see that 2020's figure comes from the
  2010 census and 1924/1928's from 1910. The help text says why in one line.
- The **Census Bureau** attribution appears in the provenance footer on these views.
- Shareable URLs, request budget and offline tests as in S3.

### Implementation Notes

- `boundary_basis` values (`at_election` / `present_day`) need plain-language help text
  that states what the figure describes without faulting the Bureau's tabulation
  (editorial guardrail).
- These tables are the debugging base for the Post 4 sequel chart
  (`APPORT-per-capita-drift`) in Phase 2.

### Dependencies

- E9-S3 (conventions). Independent of E9-S4.

_Story of epic #N (E9 — public dashboard)._

---

### E9-S6: Phase 2 — charts and metrics (placeholder — unfiled)

> **Shape gated on the research spike (E9-S1) and Phase 1 (E9-S3–S5).** Not ready to
> implement, and not filed as an issue until Phase 1 ships. This will likely split into one
> story per chart. The gate is Fred's judgment of what Phase 1 shows is worth charting,
> informed by analytics if S1 finds cookie-less analytics available.

Individual charts and headline metrics, each checkable against its Phase 1 table.
Candidates to evaluate, not commitments: EC share vs PV share per election; the
three-method winners and flips across 1976–2024; margins under each method; a state map
per election; persons-per-electoral-vote drift over time (the Post 4 sequel).

- Each chart names the Phase 1 table it reconciles against, and states which window it
  uses (EC 1824+ or popular vote 1976+).
- Any new data shape a chart needs is filed as its **own** story under D070(c), naming the
  chart.

### E9-S7: Phase 3 — narrative tabs (placeholder — unfiled)

> **Shape gated on the research spike and Phase 1** (and, in practice, Phase 2's charts).

Tabs that walk a non-technical reader through one finding each, built on Phase 2 charts and
linking to the matching "Counted, Not Assumed" post.

- Findings, not arguments: the series posture applies. **The hybrid thesis, if it ever
  appears, is a clearly labelled opinion tab**, never mixed into the neutral tabs.
- Every claim is checked before publishing and nothing critical of a source is published,
  as with posts. Copy gets the marketer pass.
- Open: whether narrative text lives in the dashboard or is pulled from the published
  posts. Decide when this story is shaped.

### E9-S8: Phase 4 — landing page (placeholder — unfiled)

> **Shape gated on the research spike and Phase 1** (in practice, on S6/S7 existing to
> summarize).

A front door that summarizes each tab in a sentence and a thumbnail, and is the URL most
worth sharing. Open at shaping time: whether the apex domain should serve or redirect to
it.

---

## Filing notes

- File the epic tracker plus S1–S5. S6–S8 stay unfiled tracker rows until Phase 1 ships:
  filed issues with placeholder ACs are poor dev-loop candidates. S2–S5 carry banners, as
  #181–#184 did.
- CLAUDE.md is left to a follow-up docs issue, timed outside an active loop run.

---

## Repo facts

| # | Fact | Label |
|---|---|---|
| F1 | Data routes in `src/usvote/api/routes.py`: `GET /v1/elections` (`year_from`/`year_to`); `/v1/elections/{year}` (`state`, `candidate` filters; one response carries `data` + `summary` + `election`); `/v1/elections/{year}/summary`; `/v1/states/{usps}` (year range); `/v1/candidates/{slug}` (year range); `/v1/elections/{year}/per-capita` (`state`); `/v1/states/{usps}/per-capita` (year range). `/v1/meta` and `/health` live in `app.py`. An inverted year range returns 422. | R |
| F2 | There is no endpoint that lists states or candidates. | R |
| F3 | `MAX_ROWS = 5000` in `repository.py`. The cap fails loudly rather than truncating. | R |
| F4 | CORS uses Starlette's `CORSMiddleware` with the origin list from `USVOTE_API_CORS_ORIGINS`, GET only, no credentials, defaulting to localhost when unset. A request with no `Origin` passes through with no CORS header and no `Vary`. `deploy.yml` sets the variable on every deploy from the GitHub variable `API_CORS_ORIGINS`, currently `https://us-presidential-election-center.org`. `config.py` says "the exact dashboard origin is deferred (frontend D001)". | R |
| F5 | Per the runbook, the `usvote-api-proxy` Worker is bound to `api.`, rewrites Host, injects the origin secret, and caches `GET /v1` 200s in `caches.default` (local to each data center) with `s-maxage=2592000`; the cache key includes the query string (`deploy.yml` relies on it). The WAF limits `/v1` to 60 requests per minute per IP. That the live config matches the runbook, and whether WAF rate limiting counts cache hits, are I. | R (runbook, `deploy.yml`) |
| F6 | The API's Cloud Run flags are `--min-instances=0 --max-instances=1 --timeout=30 --concurrency=80 --no-cpu-boost --execution-environment=gen1`. | R (`deploy.yml`) |
| F7 | Each row's `pv_status` is one of three values. Popular vote covers 1976–2024 and EC covers 1824–2024. A candidate with electoral votes but no MIT figure in 1976+ keeps a null popular vote. `party` is NULL outside the popular-vote window and where MIT has no figure. | R (`docs/api-snapshot.md`) |
| F8 | `meta.provenance` carries `source`/`source_name`/`license`/`license_url`, the `ec_*` and `census_*` equivalents, `coverage` (`year_min`/`max`, `pv_year_min`/`max`) and `redistributable_note`. | R (`models.py`) |
| F9 | `national_rollup` has no `pv_status`. Year-level popular-vote coverage is shown by `has_popular_vote` and `coverage`. | R |
| F10 | A null per-capita ratio has two causes, both visible in the row: `coverage='no_governing_figure'` (1848 Texas) or a zero allotment (1864/1868). | R |
| F11 | E9 has no epic label and no issues. E12 = #179, E13 = #216. | R |
| F12 | `docs/deploy-cloud-run.md` §0 expected "a future dashboard (`<domain>` / `www` on GitHub Pages)". | R |
| F13 | The newest decision at drafting was D069; this backlog's decision is D070. | R |
| F14 | Old issue #10, "Notebook for Creating Data Mart Object(s)", is closed. | R (title only) |
| F15 | Epic E10 (#129) has no open child issues. | R |
| F16 | A budget kill-switch exists at `deploy/killswitch/`; it pauses Cloud Run only. Cloud Run has no native hard cost cap (D034). | R |
| F17 | The daily canary (`api-canary.yml`) probes `/v1/meta` and `/v1/elections/2000/summary` on the public host, and the raw `run.app` URL, using curl with no `Origin`. The deploy smoke test hits `/v1/meta` right after the edge purge. | R |
| F18 | `pv_status` and `electoral_count_status` are typed `str`, not `Literal`, in `src/usvote/api/models.py`. | R |
