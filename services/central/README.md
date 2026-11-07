# services/central

Central node (port 5000).

Planned modules:
- `pull.py` — HTTP polling of temperature/humidity. **EXERCISE 1** (error handling, useless requests).
- `subscribe.py` — MQTT client, `on_message` for `field/+/soil/+`. **EXERCISE 2**.
- `fusion.py` — level 0, redundant soil fusion (weighted average/Kalman), outlier rejection, VPD.
- `decision.py` — `decide_irrigation(zone_state)`. **EXERCISE 3 / 4** (with TODOs).
- `api.py` — `GET /state` (in-memory state for the dashboard, including exercise flags).
- `main.py` — starts the threads.

No database: everything lives in memory.
