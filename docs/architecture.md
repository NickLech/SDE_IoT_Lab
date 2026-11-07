# Architecture and contracts

The field has **3 zones** (`zone1`, `zone2`, `zone3`). Each zone has:
- 1 temperature sensor, 1 air-humidity sensor (HTTP pull)
- 3 redundant soil-moisture sensors (MQTT push)
- 1 sprinkler

## Services

| Service | Role | Communication |
|---|---|---|
| `broker` | Mosquitto | MQTT 1883 |
| `temperature` | simulates 3 sensors (one per zone) | serves HTTP (port 5001) |
| `humidity` | simulates 3 sensors (one per zone) | serves HTTP (port 5002) |
| `soil` | simulates 9 sensors (3 per zone) | publishes on MQTT |
| `sprinkler` | actuator, 3 valves | subscribes to commands, publishes state (MQTT) |
| `central` | pull + subscribe, fusion, decision | HTTP client, MQTT client |
| `dashboard` | shows data and exercise status | reads from `central` |

> Dashboard ↔ central: `central` exposes a small HTTP API (`GET /state`) with the current in-memory state (no DB). To be confirmed in the tasks.

## HTTP contracts (pull)

`GET /health` → `{"status":"ok"}`

`GET /zones/<zone>/temperature` →
```json
{"zone":"zone1","sensor_id":"temp-zone1","value":24.3,"unit":"C","timestamp":"2026-01-01T10:00:00Z"}
```

`GET /zones/<zone>/humidity` →
```json
{"zone":"zone1","sensor_id":"hum-zone1","value":55.2,"unit":"%","timestamp":"2026-01-01T10:00:00Z"}
```

Errors: `404` unknown zone. Stopped container → connection error on the client (to handle in exercise 1).

## MQTT contracts (push)

Soil telemetry, QoS 0, not retained: `field/<zone>/soil/<sensor_id>`
```json
{"zone":"zone1","sensor_id":"soil-zone1-1","value":31.5,"unit":"%","timestamp":"2026-01-01T10:00:00Z"}
```
Wildcard subscription (exercise 2): `field/+/soil/+`

Sprinkler command, QoS 1, **not retained**: `field/<zone>/sprinkler/cmd`
`{"action":"on","duration_s":30}` or `{"action":"off"}`

Sprinkler state, QoS 1, **retained**: `field/<zone>/sprinkler/state`
`{"state":"on|off","timestamp":"..."}`

Liveness (Last Will, retained, QoS 1):
- sprinkler: if a valve vanishes, the broker publishes `{"state":"offline"}` on its state topic.
- soil sensors: `field/<zone>/soil/<sensor_id>/status` = `online` / `offline` (plain text). It has 5 levels, so `field/+/soil/+` does **not** match it.

Every soil sensor and every valve is a **separate MQTT client** (client_id `soil-<zone>-<n>` / `sprinkler-<zone>`), because a client has a single Last Will. One container hosts several clients. Clean sessions: no stale commands after a reconnect.

Injected fault (demo only): `debug/<sensor_id>/fault`, QoS 1, payload `{"mode":"crazy|stuck|drift|none"}` or plain text (`crazy`).
- `crazy`: random values, even outside the physical range (-20..120) → dropped by fusion level 0
- `stuck`: frozen value · `drift`: growing drift · `none`: back to normal

## Sensor simulation

- Value = base trend + Gaussian noise (`NOISE_STD`).
- Occasional spikes/outliers (`SPIKE_PROB`).
- Debug fault: `POST /debug/fault` (HTTP) or `debug/<sensor_id>/fault` (MQTT, see above); used in the fusion example.
- Soil dries over time and gets wetter while the zone's sprinkler is on (`soil` listens to the sprinkler state).
- Each soil sensor has a fixed calibration offset (`BIAS_STD`) and its own send rhythm (interval ±10%, random start): data reaches `central` **asynchronously**.

Soil model (per zone, see `services/soil/README.md`): start 45/50/40 %, loss 3.0/4.5/2.0 %/min, +12 %/min while the sprinkler is on, saturation 80 %. All parameters are environment variables.

## Data fusion

1. **Level 0**: drop impossible readings (outside the physical range).
2. **Redundant (soil)**: 3 sensors per zone → one estimate (weighted average or Kalman), outliers dropped by distance from the median.
3. **Cooperative**: temperature + air humidity → **VPD**.
4. **Feature → decision**: soil estimate + VPD → `decide_irrigation(zone_state)`.

VPD (kPa): `es = 0.6108 * exp(17.27*T/(T+237.3))`, `VPD = es * (1 - RH/100)`.

## Exercise status on the dashboard

`central` exposes one flag per exercise (`http_pull`, `mqtt_push`, `decision`). The panel is **red** until the TODO works, **green** once data/actions arrive.
