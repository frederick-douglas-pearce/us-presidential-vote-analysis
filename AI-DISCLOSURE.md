# AI use in this repository

This project publishes two things a reader is entitled to ask *"who checked this?"* about. One is
a blog series making **historical claims** about two centuries of presidential elections. The other
is a **public API** that serves numbers which sometimes disagree with what the National Archives
prints — 1872 is reported as 366 appointed electoral votes where the Archives page itself totals
352, and 1868's nine contested Georgia votes are marked disputed rather than silently counted.
Almost everything built since mid-2026 was built through a supervised agent loop.
This file is the answer to that question, in one place, instead of being implicit across sixty-odd
decision records.

In creating this repository, I collaborated with **Claude Code** (Anthropic's CLI, running Claude
models) to design and implement the data pipeline, the warehouse schema, and the read-only API;
to research primary sources and reconcile them against each other; to draft the blog series; and
to edit throughout. I affirm that all AI-generated and co-created content underwent review and
evaluation. The final output reflects my understanding, expertise, and intended meaning. While AI
assistance was instrumental, I retain full responsibility for the content, its accuracy, and its
presentation. This disclosure is made in the spirit of transparency and to acknowledge the role of
AI in the creation process.

## Where the line falls

The original work — `step1_electoral_college_data.ipynb` and `db_tools.py`, committed in December
2021 and January 2022 — was written by hand, before any of this. Everything added from July 2026
onward was built with Claude Code: the `usvote` package, the warehouse, the API and its
deployment, the docs, and the posts.

Most of that work runs through a **supervised dev loop** ([`claude-code-loop`](https://github.com/frederick-douglas-pearce/claude-code-loop)),
bound to this repository by [`.claude/loop.config.md`](.claude/loop.config.md). The loop plans,
implements, reviews, and verifies each issue against its acceptance criteria, and **stops for human
approval of every plan and every merge**. Not everything goes through it: small documentation and
metadata changes are driven directly, without the loop's routed gates. This file was one of them.

## What actually gets run, and on what

The distinction that matters in a diligence statement is between a gate that always runs and one
that runs when a rule fires. Both exist here.

**Unconditional.** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) carries no path filter, so
every pull request to `main` and every push to `main` runs all three of its jobs: `ruff` and `mypy`
and the offline unit suite with coverage; the live-Postgres integration tier in its own job against
a `postgres:16` service container; and a container build that boots the API image and curls
`/health`. Among the unit tests are the structural guards that hold this project's invariants —
[`tests/unit/test_layering.py`](tests/unit/test_layering.py), which proves the licensing firewall by
importing modules in a subprocess where `usvote.ucsb` is *unimportable* rather than by grepping for
it, and [`tests/unit/test_api_import_graph.py`](tests/unit/test_api_import_graph.py), which proves
the serving layer cannot reach a database.

**Conditional, and worth naming as such.** An architect design pass fires on the triggers in
`loop.config.md` §2 and is skipped for docs-only changes. A `/security-review` fires on the five
sensitive path surfaces in §4. The Open Graph card guard is path-filtered to `posts/`. So a given
change may be due none of these three.

**Cannot run in CI at all.** The UCSB / American Presidency Project corpus is not redistributable
(D022), so it is not in this repository and CI never sees it. The tests that need it —
`TestRealCorpus` in the UCSB parse and transform suites, and the cross-source popular-vote overlap
gates — **skip** when `USVOTE_UCSB_HTML_DIR` is unset. The census corpus behaves the same way under
`USVOTE_CENSUS_CORPUS_DIR`. These are the checks that exercise every real page against every header
layout, and running them locally is a merge precondition that no green checkmark will ever prove.
That gap is stated here rather than papered over.

## What that means per surface

**[`src/`](src/)** — the pipeline, the warehouse, the API. Built through the loop, gated as above.
The project's hardest correctness properties are not type errors but *plausible wrong numbers*, and
the design answer throughout has been to make each hazard visible as a column, a constant, or an
assert that fails loud rather than as a value that merely looks reasonable.

**[`posts/`](posts/)** — the "Counted, Not Assumed" series. Drafted by the `marketer` agent against
a brief, then edited by me; the raw agent draft is kept verbatim beside the edited one so the diff
stays inspectable, though `social/` is git-ignored, so that comparison is mine to make and not a
reader's. Two editorial guardrails are absolute and are enforced by review, not by CI: nothing
critical of a data source is ever published, and every historical claim is checked before it ships.
Each post ends with the one-line form of this disclosure, per
[`posts/README.md`](posts/README.md).

**[`docs/`](docs/)** — catalogs derived from the code and from primary sources.
[`docs/corrections.md`](docs/corrections.md) is the strongest of them: every anomaly row carries its
own citation — a statute, an Archives page, a constitutional amendment — rather than a general
appeal to the record.

**[`.claude/specs/`](.claude/specs/)** — the decision log and the research files, and the single
best diligence artifact this repository has. Research carries **load-bearing evidence labels**
(VERIFIED / ATTRIBUTED / UNVERIFIED / CONTRADICTED) that are never laundered from a weaker column
into a stronger one, and
[`research-faithless-electors.md`](.claude/specs/research-faithless-electors.md) ends with a
source-reliability section to read *before* citing anything above it: two `.gov` pages still serving
superseded pre-ECRA text, a CRS report that conflicts with the House historian, a domain that has
been hijacked since it was cited in a 2020 Supreme Court brief, a quote that must not be truncated
because its second sentence carries the motive, and a widely-repeated name that appears nowhere in
the legal record. Claims without evidence are marked, not asserted.

**The API and its snapshot** — every served number traces to a primary source, the provenance
travels in `meta.provenance` on every response, and the snapshot is versioned by a **content hash**
rather than a timestamp, so the artifact and the claim cannot drift apart unnoticed.

## Where the judgment is mine

What the series claims, which readings of the historical record are defensible, what is safe to
publish, and what ships on the public surface are mine. Claude Code drafts, implements, reviews,
and proposes. The gates are good at catching whether a thing was built as specified. They are much
weaker at catching whether a claim about the world is true — which is exactly why the two editorial
guardrails above are enforced by a human, and why the evidence labels exist.

## Errors

Mistakes here are mine. Corrections are welcome as
[issues](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues).
Where this project's reading differs from what a source prints, the difference is recorded with its
reasoning in [`docs/corrections.md`](docs/corrections.md); findings about a source's own data go to
that source privately rather than into a post.

## Why this file exists

The framing follows the Diligence competency in Anthropic's
[AI Fluency: Framework & Foundations](https://academy.claude.com/courses/ai-fluency-framework-foundations)
course, and specifically its guidance on
[writing an AI diligence statement](https://academy.claude.com/tutorials/writing-an-ai-diligence-statement):
name the tool, name the tasks, describe the review, and stand behind the result.

**This repository is not affiliated with, or endorsed by, Anthropic** — nor by the National
Archives, the MIT Election Lab, the UCSB American Presidency Project, or any election authority.
See the Disclaimer section of the [README](README.md#disclaimer).
