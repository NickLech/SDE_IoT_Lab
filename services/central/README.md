# services/central

Central node: collects soil readings over MQTT and air temperature/humidity over HTTP, fuses the data, decides irrigation commands, and serves the dashboard API.

The Compose build context is `services/central`. The Dockerfile copies `app.py` to `/app` and the `components` package to `/app/components`; the container starts with `python app.py`.

Modules:
- `app.py` — starts polling, MQTT, the control loop, and the HTTP API.
- `components/comms.py` — MQTT and HTTP communication.
- `components/state.py` — shared in-memory state.
- `components/fusion.py` — soil/air fusion and VPD calculations.
- `components/decision.py` — irrigation decision logic.
- `components/control.py` — control loop and published API view.
- `components/api.py` — HTTP endpoints.
- `components/config.py` — environment-based configuration.

HTTP endpoints on container port 5000:
- `GET /health`
- `GET /zones`
- `GET /zones/<zone>`

Compose publishes the API on host port 5100. No database is used; state lives in memory.
