# Prose License: CC-BY-4.0

**Grant.** Everything committed under [`posts/`](posts/) and [`docs/`](docs/), whatever its format, is licensed under the [Creative Commons Attribution 4.0 International License (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/) — **except third-party material quoted within it, which is not the licensor's to license onward**, as described under [Quoted material](#quoted-material) below.

Copyright (c) 2021-2026 Frederick Douglas Pearce.

That sentence is the whole of the grant. Everything below explains it; nothing below widens it.

## Summary

You are free to:

- **Share** — copy and redistribute the material in any medium or format
- **Adapt** — remix, transform, and build upon the material for any purpose, even commercially

Under the following terms:

- **Attribution** — You must give appropriate credit to Frederick Douglas Pearce, provide a link to this repository (https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis), link to this license (https://creativecommons.org/licenses/by/4.0/), and indicate if changes were made. You may do so in any reasonable manner, but not in any way that suggests the licensor endorses you or your use.
- **No additional restrictions** — You may not apply legal terms or technological measures that legally restrict others from doing anything the license permits.

The license link is part of the attribution, not a courtesy: CC BY 4.0 § 3(a)(1)(C) requires a reuser to indicate that the material is licensed under this Public License and to include its text, URI, or hyperlink.

## Full legal text

The complete license: https://creativecommons.org/licenses/by/4.0/legalcode

## Quoted material

This repository is a data project, and both directories it licenses quote from sources it does not own. The exclusion in the grant above is what keeps this license from claiming otherwise:

- **National Archives** (electoral-college results and their Notes sections) — a work of the U.S. Government, in the public domain under 17 U.S.C. § 105. Quoted freely; no grant from this repository is needed or offered.
- **MIT Election Lab** (popular-vote data) — CC0 1.0 at the source. Likewise unencumbered, and likewise not granted by this file.
- **UCSB / American Presidency Project** — **no reuse grant exists.** The project's snapshot is deliberately kept outside this repository for that reason, and the reasoning is recorded in the decision log as D014, D016, D022, and D030. Where a sentence of UCSB prose is quoted in a post to make a point about the source record, it is quoted for identification and commentary. It is not redistributed, and this license does not purport to let anyone else redistribute or adapt it.

## Why `docs/` is prose

`docs/` holds browsable catalogs written for a reader rather than for a parser — [`corrections.md`](docs/corrections.md) is a per-anomaly catalog with statutory citations, [`pv-coverage.md`](docs/pv-coverage.md) explains what a column measures and why. Two of them ([`canonical-keys.md`](docs/canonical-keys.md), [`api-snapshot.md`](docs/api-snapshot.md)) read partly as API contracts, and they are licensed as prose anyway: the contract that binds is the code in `src/`, which the MIT license covers.

[`posts/README.md`](posts/README.md) sits inside `posts/`, so the grant reaches it like anything else in that directory.

## What this license does not cover

Pointers, not carve-outs — the grant above is closed, so nothing here needs to subtract from it.

- Code and the material that documents it — `src/`, `tests/`, `tooling/`, `scripts/`, `deploy/`, the step-1 notebook, `db_tools.py`, the `Dockerfile`, the CI workflows, and the root `README.md` and `CLAUDE.md` — are under [MIT](LICENSE).
- `.claude/specs/` — the decision log, research files, and backlogs — is also under MIT. It documents the codebase, and adding a third licensing surface for it would buy nothing.
- `social/images/` holds the tracked Open Graph share cards and the TOML briefs they render from. They sit outside `posts/` and stay under MIT with the `tooling/` script that produces them, even though each card publishes alongside a CC-BY post.
