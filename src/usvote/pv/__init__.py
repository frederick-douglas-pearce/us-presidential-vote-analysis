"""Source-agnostic popular-vote (PV) spine — the shared PV target table + loader.

The Electoral-College pipeline is the flat top-level ``usvote`` package (the
source-of-truth spine, D006); each popular-vote *source* nests as its own sibling
subpackage (``usvote/mit/``, later ``usvote/ucsb/`` — the source-namespacing
convention, D015). This ``usvote/pv/`` package is the third kind of thing: neither a
source nor the EC spine, but the **shared, source-neutral PV contract** both PV
sources conform to and load through.

It holds two things, deliberately owned by no single source:

- :mod:`usvote.pv.schema` — the D018 shared PV record shape (``SHARED_PV_COLUMNS``),
  the shared PV **target-table** DDL (``build_pv_column_defs``), and the boundary
  shape guard (``assert_pv_shape``).
- :mod:`usvote.pv.load` — ``load_pv_records``, the one write seam every PV source
  loads through, tagged by its own ``source`` value.

MIT (#66) is the first source to land, so per D018 ("DDL is finalized at the first
load story") it is #66 that *creates* this shared table; the UCSB load (#37) reuses
``build_pv_column_defs``/``load_pv_records`` verbatim rather than defining a rival
schema. The dependency direction is always **source -> pv** (a source imports the
shared contract); ``usvote.pv`` never imports from a source subpackage.

Explicitly *not* here: the ``pv_source`` reference table and the
``pv_preferred``/``pv_redistributable``/``pv_ucsb`` resolution views — those are the
E6 union story's concern (#68, D017), built over this raw per-source fact table.
"""
