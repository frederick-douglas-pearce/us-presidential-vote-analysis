"""The dashboard's recorded public API responses, by API path.

Stdlib-only on purpose: the e2e server (``tests/e2e/serve.py``) imports it into the
dashboard's own process, so it loads nothing there the deployed app lacks. That is why it
is not in ``tests/_helpers.py``, which imports ``usvote`` and pandas.
``test_dashboard_app.py`` reads the same map. Every ``*.json`` file directly in
:data:`FIXTURE_DIR` has an entry, which the e2e server checks at start-up.
"""

from __future__ import annotations

from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "dashboard"

#: API path → recorded file name under :data:`FIXTURE_DIR`.
RECORDED_FILES: dict[str, str] = {
    "/v1/meta": "v1_meta.json",
    "/v1/elections": "v1_elections.json",
    **{
        f"/v1/elections/{year}": f"v1_elections_{year}.json"
        for year in (1824, 1860, 1868, 1872, 1896, 2016, 2024)
    },
    "/v1/states/GA": "v1_states_GA.json",
    # The per-capita tables, T6 and T7 (#280).
    **{
        f"/v1/elections/{year}/per-capita": f"v1_elections_{year}_per_capita.json"
        for year in (1824, 1848, 1860, 1864, 1868, 1872, 1896, 2016, 2024)
    },
    **{
        f"/v1/states/{usps}/per-capita": f"v1_states_{usps}_per_capita.json"
        for usps in ("GA", "TX")
    },
    # The candidate index (#330) and one candidate's history, T5 (#331).
    "/v1/candidates": "v1_candidates.json",
    "/v1/candidates/andrew-jackson": "v1_candidates_andrew-jackson.json",
}
