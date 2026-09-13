"""US decennial census population source pipeline (E10-S2, #181).

The third source subpackage under the source-namespacing convention (D015), and the
first that is **not** a popular-vote source: the Electoral College / National Archives
pipeline stays flat at the top level, and each non-EC source nests as its own sibling
subpackage with its own fetch/parse/transform/load stages and a ``pipeline.py``.

What this ingests is state **resident** population by decennial census, 1790–2020, from
the Census Bureau's own published tables — the denominator E10 needs to express an
electoral vote in people. It conforms to no :mod:`usvote.pv` contract, writes no
``dwh.pv_votes``, and takes no part in the D017 popular-vote resolution views: those are
a popular-vote vocabulary and this is not a popular-vote source. What it borrows from
:mod:`usvote.mit` and :mod:`usvote.ucsb` is *structure*, not schema.

**Scope, settled by #180 (E10-S1) and narrowed by the human on 2026-09-11.** S1 resolved
the source fork to the structured-source case — the series is genuinely machine-readable
XLSX with no OCR stage — and resolved the licensing fork affirmatively: Census-authored
works are public domain by 17 U.S.C. §105, so unlike UCSB this source **may** reach the
snapshot and the public API (D030), and real Census bytes **may** be committed as test
fixtures (D022). The by-state **apportionment** series is deliberately out of scope; see
D059 and the acceptance criteria on #181 for the three reasons.

Two source files, overlapping on 1910–1990 at different vintages, are stitched by an
explicit rule so each census comes from exactly one of them — see
:mod:`usvote.census.transform`, which also carries the Virginia 1824–1860 boundary
correction, a hazard in this source that produces plausible wrong numbers rather than
a load error.
"""
