"""The public dashboard's app package (E9, D071): Plotly Dash on App Engine standard.

``dashboard/`` is the App Engine deploy root and this package's import root. Runtime
code reads data **only** from the public API, over HTTPS, through ``explore.api`` —
never the Cloud Run origin, never a file, and never ``usvote`` (D070(b)).
"""
