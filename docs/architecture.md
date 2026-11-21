# Architecture and contracts

A field is split into **3 zones** (`zone1`, `zone2`, `zone3`). Each zone has:

- 1 air-temperature sensor (**HTTP**, pull)
- 1 air-humidity sensor (**HTTP**, pull)
- 3 redundant soil-moisture sensors (**MQTT**, push)
- 1 sprinkler (**MQTT**, actuator)

One **rain** service is global and drives all zones. The `central` node collects everything, fuses the data,
decides when to irrigate and serves the result to the `dashboard`.

```
                     HTTP pull (every 5 s)
   zoneN: temperature :5001  <------------------+
   zoneN: humidity    :5002  <------------------+
                                                |
   zoneN: soil-1..3  --publish--> [ broker ] --subscribe--> central --GET /zones--> dashboard
   zoneN: sprinkler  <--cmd------ [ MQTT   ] <--cmd-------- central
                     --state----> [ 1883   ] --state------> central, soil, humidity
   rain              --state----> [       ] --state------> central, soil, humidity
   dashboard         --mode-----> [       ] --mode-------> rain
```

## Containers

| Container | Image / build | What it runs | Host port(s) |
|---|---|---|---|
| `broker` | `eclipse-mosquitto:2` | MQTT broker, anonymous, no persistence | 1883 |
| `zone1`, `zone2`, `zone3` | `services/zone` | **6 independent processes** managed by supervisord: `soil-1`, `soil-2`, `soil-3`, `temperature`, `humidity`, `sprinkler` | zone1: 5001, 5002 · zone2: 5011, 5012 · zone3: 5021, 5022 |
| `rain` | `services/rain` | global rain simulator | none |
| `central` | `services/central` | pull + subscribe, fusion, decision, HTTP API | 5100 (container port 5000) |
| `dashboard` | `services/dashboard` | Dash web UI | 8050 |
| `monitor` | `eclipse-mosquitto:2` | prints `field/#` and `debug/#` (only with `--profile debug`) | none |

Inside a zone container, `temperature` listens on port **5001** and `humidity` on **5002**.
`central` reaches them as `http://zone1:5001`, `http://zone1:5002`, `http://zone2:5001`, ... (Docker network, no host port needed).

Every soil sensor, every sprinkler, the humidity sensor, the rain service, `central` and the assignment panel is a **separate MQTT client**
(a client has only one Last Will). Client ids: `soil-<zone>-<n>`, `sprinkler-<zone>`, `humidity-<zone>`, `rain-service`, `central`, `assignment`.
The `temperature` service does not use MQTT.

## HTTP contracts (pull)

Served by each zone container. Only `GET` is supported. Unknown paths or zones → `404 {"error":"not found"}`.

| Request | Response |
|---|---|
| `GET /health` | `{"status":"ok"}` |
| `GET /zones/<zone>/temperature` | `{"zone":"zone1","sensor_id":"temp-zone1","value":24.3,"unit":"C","timestamp":"2026-01-01T10:00:00Z"}` |
| `GET /zones/<zone>/humidity` | `{"zone":"zone1","value":55.2,"unit":"%","timestamp":"2026-01-01T10:00:00Z"}` |

Notes:
- A zone container only answers for **its own** zone (`zone1` container → `/zones/zone1/...`; asking it for `zone2` gives `404`).
- The humidity response has **no** `sensor_id` (the temperature one does).
- If a service is stopped, the client gets a connection error (handled in Exercise 1).

### Central API (read by the dashboard)

| Request | Response |
|---|---|
| `GET /health` | `{"status":"ok","mqtt":true}` |
| `GET /zones` | `{"timestamp","links","zones":{<zone>:{...}}}` |
| `GET /zones/<zone>` | the zone object with `zone`, `timestamp` and `links` added at the top level |

Before the first control cycle `/zones` answers `503 {"error":"not ready"}`; unknown zone → `404`.

```json
{
  "timestamp": "2026-01-01T10:00:00Z",
  "links": {"mqtt": true, "temperature": true, "humidity": true},
  "zones": {
    "zone1": {
      "soil":      {"median": 47.3, "valid": 3, "expected": 3},
      "air":       {"temperature": 24.3, "humidity": 55.2},
      "vpd":       {"kpa": 1.361, "band": "ok"},
      "sprinkler": {"state": "off", "remaining_s": null, "manual": false},
      "rain":      "off",
      "sensors":   {"soil-zone1-1": {"state": "online", "value": 47.9, "age_s": 2.1, "suspect": false}},
      "decision":  {"action": null, "reason": "soil 47% >= threshold 43%", "soil_threshold": 43.4},
      "last_command": null
    }
  }
}
```

(Values are illustrative; `sensors` lists all 3 soil sensors.) `air` values are `null` when the HTTP data is missing or too old, and then `vpd` is `null` too.
`sprinkler.state` is `on`, `off`, `offline` or `unknown`; `rain` is `on`, `off` or `unknown`.

## MQTT contracts (push)

All topics start with `field/`. `<zone>` is `zone1`, `zone2` or `zone3`; `<sensor_id>` is `soil-<zone>-<n>` with `n` = 1..3.

| Topic | Published by | Read by | QoS | Retained | Payload |
|---|---|---|---|---|---|
| `field/<zone>/soil/<sensor_id>` | soil sensor (every 5 s) | `central` | 0 | no | `{"zone":"zone1","sensor_id":"soil-zone1-1","value":31.5,"unit":"%","timestamp":"..."}` |
| `field/<zone>/soil/<sensor_id>/status` | soil sensor (+ Last Will) | `central` | 1 | yes | plain text `online` / `offline` |
| `field/<zone>/sprinkler/cmd` | `central`, or you by hand | sprinkler, `central` | 1 | **no** | `{"action":"on","duration_s":30}` or `{"action":"off"}` |
| `field/<zone>/sprinkler/state` | sprinkler | `central`, soil, humidity | 1 | yes | `{"state":"on"}` / `{"state":"off"}` |
| `field/<zone>/sprinkler/status` | sprinkler (+ Last Will) | `central` | 1 | yes | plain text `online` / `offline` |
| `field/<zone>/rain/state` | `rain` (all zones together) | `central`, soil, humidity | 1 | yes | `{"state":"on"}` / `{"state":"off"}` |
| `field/rain/mode` | dashboard toggle, or you by hand | `rain` | 1 | yes | `{"mode":"auto"}` / `{"mode":"dry"}` / `{"mode":"rain"}` |

Details:
- **Wildcards.** `+` matches exactly one level. `field/+/soil/+` has 4 levels, so it matches the readings but **not** the `/status` topics (5 levels).
  `#` matches everything below.
- **Sprinkler command.** `duration_s` is optional (default 30 s). A sprinkler turns itself off after `duration_s`; a repeated `on` renews the timer.
  Invalid commands are ignored (and logged). `central` adds `"source":"central"` to its own commands; any command **without** it is a *manual* command:
  while it lasts, `central` does not interfere.
- **Liveness (Last Will).** If a soil sensor or a sprinkler dies, the broker publishes `offline` on its `.../status` topic. A device stopped gracefully also publishes `offline` by hand.
  When it starts again it publishes `online`.
- **Rain mode.** `auto` = random cycle driven by the rain service. `dry` / `rain` = the state is forced (the service stops publishing, so it cannot overwrite the override).
  Going back to `auto` re-publishes the simulated state immediately.
- **Debug.** `monitor` (profile `debug`) also listens on `debug/#`, but no device publishes there in the current version.

## Simulation

All sensors move with a tick of **5 s**.

| Device | Behaviour |
|---|---|
| `temperature` | daily sine cycle, one "day" = 600 s: `17 + 0.5·ZONE_INDEX + 12·sin(2π·t/600)`, clamped to **5..30 °C** (zone2 +0.5 °C, zone3 +1 °C) |
| `humidity` | starts at 65 %; each tick **−1**, and **+2 for each active source** (this zone's sprinkler, rain); clamped to **50..80 %** |
| `soil` (×3 per zone) | starts at a random value in 45..55 %; each tick **−(1..3)** at random and **+10 for each active source** (sprinkler, rain); clamped to **30..85 %**. Each sensor has its own random start and noise, so the 3 sensors of a zone differ slightly |
| `sprinkler` | on command: `on` for `duration_s`, then back to `off`; publishes `off` when it connects |
| `rain` | cycles of random length 120..300 s; in each cycle it rains during the **last 30 s**, on all zones at once. The first cycle starts dry |

Sensors do **not** inject faults, noise spikes or bias in this version.

## What `central` does

Every `TICK_S` = 1 s the control loop takes a snapshot of the state, fuses it, decides and publishes the view served by the API.

1. **Collect.** MQTT: soil readings, sensor/sprinkler status, sprinkler state and commands, rain. HTTP: temperature and humidity of every zone every `POLL_INTERVAL_S` = 5 s (timeout 1.5 s).
2. **Level 0, plausibility.** Soil values outside 0..100 are dropped. Air values outside -40..60 °C (temperature) or 0..100 % (humidity) are dropped.
3. **Soil sensors.** A sensor is `offline` if its status is `offline`, if it never reported, or if it has been silent for more than 8 s. The zone value is the **median** of the online, valid sensors.
   A sensor is flagged `suspect` if it is more than 15 % away from that median.
4. **Air.** The value used is the **median of the last 3 samples**, and only samples younger than 15 s count (this filters isolated spikes). If no recent sample exists the value is `null`.
5. **VPD** (kPa), cooperative fusion of temperature and humidity:

   ```
   es  = 0.6108 * exp(17.27 * T / (T + 237.3))
   VPD = es * (1 - RH / 100)
   ```

   Band: `< 0.4` low · `0.4–0.8` ok · `0.8–1.2` optimal · `1.2–1.6` ok · `> 1.6` stress.
6. **Decision.** Checked in this order, the first rule that matches wins:

   | # | Condition | Result |
   |---|---|---|
   | 1 | MQTT disconnected | no command |
   | 2 | manual sprinkler command active | no command (rules bypassed) |
   | 3 | no valid soil reading | no command (fail-safe) |
   | 4 | sprinkler `on` and raining | send `off` |
   | 5 | sprinkler `on` and soil ≥ 70 % | send `off` |
   | 6 | sprinkler `on` | no command |
   | 7 | sprinkler not `off` (`offline`, `unknown`) | no command |
   | 8 | raining | no command |
   | 9 | soil ≥ threshold | no command |
   | 10 | last command less than 60 s ago (cooldown) | no command |
   | 11 | otherwise | send `on` |

   ```
   threshold = 35 + 15 * (VPD - 0.8)            (clamped to 5..95; 35 if VPD is missing)
   duration  = 20 * (1 + max(0, VPD - 0.8))     (seconds, at most 120; 20 if VPD is missing)
   ```

   The drier the air, the earlier and the longer it irrigates.

All values above are environment variables of `central` (`services/central/components/config.py`).

## Exercises and where they live

| # | Topic | File | What it feeds |
|---|---|---|---|
| 1 | HTTP pull | `services/central/components/comms.py` → `poll_loop()` | air temperature and humidity of each zone |
| 2 | MQTT push | `services/central/components/comms.py` → `on_connect()` | soil readings of the 9 sensors |
| 3 | Data fusion | `services/central/components/fusion.py` → `vpd_kpa()` | VPD and its band |
| Assignment | Monitor one zone | `services/dashboard/assignment/monitor.py` | temperature (HTTP) and rain (MQTT) charts of one zone |

## Dashboard

- Reads `GET /zones` from `central` (`CENTRAL_URL`), no database: only the current session is kept.
- One card per zone: soil median, air, VPD, agreement of the soil sensors, sprinkler state, decision and watered time.
- A status panel with health checks and a pill that says `LIVE` or `n issue(s)` (red when something is missing, e.g. humidity data).
- An MQTT log (`field/#`, `debug/#`) and a rain toggle that publishes `field/rain/mode`.
- The **Assignment** panel runs its own MQTT client and its own HTTP polling (zone1), independent from `central`. Its code is self-contained in `services/dashboard/assignment/`: `monitor.py` (the student TODOs inside that HTTP/MQTT client), `grading.py` (validation).

## Repository layout

```
docker-compose.yml        orchestration (broker, 3 zones, rain, central, dashboard, monitor)
ctl.sh                    switch single devices on/off from the host
docs/
  architecture.md         this file: services, contracts, simulation, decision rules
  cheatsheet.md           commands, URLs and MQTT topics for the exercises
  exercises.md            the exercises
services/
  broker/                 mosquitto.conf
  zone/                   zone image: Dockerfile + supervisord.conf (6 processes per zone)
  temperature/            temperature sensor (HTTP)      -- copied into the zone image
  humidity/               air-humidity sensor (HTTP)     -- copied into the zone image
  soil/                   soil-moisture sensor (MQTT)    -- copied into the zone image
  sprinkler/              actuator (MQTT)                -- copied into the zone image
  rain/                   global rain simulator (MQTT)
  central/                app.py + components/ (comms, state, fusion, decision, control, api, config)
  dashboard/              Dash app (assignment/, components/, callbacks.py, viewmodel.py, assets/)
```