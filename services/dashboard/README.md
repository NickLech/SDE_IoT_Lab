# services/dashboard

Dash dashboard (port 8050). Polls `GET /state` from `central` (`dcc.Interval`).

Panels: field map (3 zones), per-zone charts (raw vs fused), sprinkler state, **exercise status** (red/green), sensors rejected as outliers.

No DB: history is the in-memory window `central` returns when the page loads.
