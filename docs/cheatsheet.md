# Participant cheat-sheet

Everything you need to run the lab and to do the exercises: commands, URLs, MQTT topics.
For the full details (payloads, simulation, decision rules) see `architecture.md`.

## Prerequisites

- Docker + Docker Compose (`docker --version`, `docker compose version`); Docker Desktop must be running.
- Repository cloned: `git clone <URL> && cd <repo>`.
- On Windows use Git Bash (or WSL) for `./ctl.sh` and for the commands with JSON quotes below (PowerShell quoting breaks them).

## What runs where

| Container | Contains |
|---|---|
| `broker` | Mosquitto MQTT broker (port 1883) |
| `zone1`, `zone2`, `zone3` | one per zone, 6 independent processes each: `soil-1`, `soil-2`, `soil-3`, `temperature`, `humidity`, `sprinkler` |
| `rain` | global rain, drives all zones |
| `central` | data fusion + irrigation decisions + HTTP API |
| `dashboard` | web UI |

## Docker commands

```bash
docker compose up --build          # start everything (also applies your code changes)
docker compose up -d --build       # same, in background
docker compose ps                  # container status
docker compose logs -f central     # follow a service's logs (also: zone1, zone2, zone3, rain, dashboard)
docker compose restart central     # restart after editing code
docker compose stop zone2          # stop a WHOLE zone (all its devices)
docker compose start zone2
docker compose down                # stop everything
```

## Switch single devices on/off

Devices of a zone: `soil-1` `soil-2` `soil-3` `temperature` `humidity` `sprinkler`.

```bash
./ctl.sh status                    # all devices of all zones
./ctl.sh zone2 status              # devices of one zone
./ctl.sh zone2 stop soil-2         # switch one sensor OFF
./ctl.sh zone2 start soil-2        # ... and back ON
./ctl.sh zone1 stop temperature    # test HTTP errors (air value lost after ~15 s)
./ctl.sh zone3 stop sprinkler      # sprinkler offline: central sends no commands
./ctl.sh zone3 stop all            # every device of the zone (container stays up)
./ctl.sh rain stop                 # global rain: stop | start | restart
```

Without the script: `docker compose exec zone2 zonectl stop soil-2`.

- A stopped soil sensor or sprinkler publishes `offline` (retained), so the dashboard shows it immediately.
- Temperature and humidity are pulled over HTTP: they become unavailable after ~15 s.
- A crashed process restarts by itself; one you stopped by hand stays stopped.
- `permission denied` on `ctl.sh`: run `chmod +x ctl.sh`. `bad interpreter` or `\r` errors: run `dos2unix ctl.sh`.

## Addresses and ports

| What | Address |
|---|---|
| Dashboard | http://localhost:8050 |
| Central API | http://localhost:5100/zones (also `/zones/zone1`, `/health`) |
| MQTT broker | `localhost:1883` |

| Zone | Temperature (host port) | Humidity (host port) |
|---|---|---|
| zone1 | 5001 | 5002 |
| zone2 | 5011 | 5012 |
| zone3 | 5021 | 5022 |

Inside Docker (what `central` uses) every zone container answers on **5001** (temperature) and **5002** (humidity):
`http://zone1:5001`, `http://zone2:5001`, `http://zone3:5001`, ...

## HTTP calls (pull)

Only `GET`. Each zone container answers **only for its own zone**.

| Call | Returns |
|---|---|
| `GET /health` | `{"status":"ok"}` |
| `GET /zones/<zone>/temperature` | `{"zone","sensor_id":"temp-<zone>","value":24.3,"unit":"C","timestamp"}` |
| `GET /zones/<zone>/humidity` | `{"zone","value":55.2,"unit":"%","timestamp"}` (no `sensor_id`) |

URL pattern used by `central`: `<base URL of the zone>/zones/<zone>/<temperature|humidity>`.
Unknown path or zone → `404 {"error":"not found"}`.

```bash
# from your computer (host ports)
curl http://localhost:5001/zones/zone1/temperature
curl http://localhost:5002/zones/zone1/humidity
curl http://localhost:5011/zones/zone2/temperature
curl http://localhost:5012/zones/zone2/humidity
curl http://localhost:5021/zones/zone3/temperature
curl http://localhost:5022/zones/zone3/humidity
curl http://localhost:5001/health
```

Central API (what the dashboard reads):

```bash
curl -s http://localhost:5100/health
curl -s http://localhost:5100/zones | python3 -m json.tool          # all zones
curl -s http://localhost:5100/zones/zone1 | python3 -m json.tool    # one zone
```

Useful fields in a zone: `soil.median`, `soil.valid`, `air.temperature`, `air.humidity`, `vpd.kpa`, `vpd.band`,
`sprinkler.state`, `rain`, `decision.reason`. `air` and `vpd` are `null` when the HTTP data is missing.

Python (standard library only):

```python
import json, urllib.request
with urllib.request.urlopen(url, timeout=1.5) as r:
    value = float(json.load(r)["value"])
```

## MQTT topics (push)

`<zone>` = `zone1` | `zone2` | `zone3` · `<sensor_id>` = `soil-<zone>-<n>`, `n` = 1..3 (e.g. `soil-zone1-1`).

| Topic | Who publishes | QoS | Retained | Payload |
|---|---|---|---|---|
| `field/<zone>/soil/<sensor_id>` | soil sensor, every 5 s | 0 | no | `{"zone","sensor_id","value":31.5,"unit":"%","timestamp"}` |
| `field/<zone>/soil/<sensor_id>/status` | soil sensor (+ Last Will) | 1 | yes | text `online` / `offline` |
| `field/<zone>/sprinkler/cmd` | `central` or you | 1 | no | `{"action":"on","duration_s":20}` or `{"action":"off"}` |
| `field/<zone>/sprinkler/state` | sprinkler | 1 | yes | `{"state":"on"}` / `{"state":"off"}` |
| `field/<zone>/sprinkler/status` | sprinkler (+ Last Will) | 1 | yes | text `online` / `offline` |
| `field/<zone>/rain/state` | `rain` | 1 | yes | `{"state":"on"}` / `{"state":"off"}` |
| `field/rain/mode` | dashboard toggle or you | 1 | yes | `{"mode":"auto"}` / `{"mode":"dry"}` / `{"mode":"rain"}` |

Wildcards:
- `+` = exactly **one** level, `#` = everything below.
- `field/+/soil/+` has 4 levels: it matches **all soil readings** but **not** the `/status` topics (5 levels).
- `field/+/soil/+/status` = the liveness of every soil sensor; `field/zone1/#` = everything about zone1.

Notes:
- Retained messages are delivered as soon as you subscribe (current sprinkler state, rain state, sensor status).
- `duration_s` is optional (default 30 s); the sprinkler turns itself off when it expires.
- A command without `"source":"central"` is a *manual* command: while it lasts, `central` does not interfere.

### Try MQTT by hand

The Mosquitto tools are inside the `broker` container, so nothing to install:

```bash
# watch all readings (Ctrl+C to stop)
docker compose exec broker mosquitto_sub -t 'field/+/soil/+' -v

# watch everything (or: docker compose --profile debug up monitor)
docker compose exec broker mosquitto_sub -t 'field/#' -v

# current retained state of sprinklers, rain and sensors (waits 2 s, then exits)
docker compose exec broker mosquitto_sub -t 'field/+/sprinkler/state' -t 'field/+/sprinkler/status' -t 'field/+/rain/state' -t 'field/+/soil/+/status' -W 2 -v

# sprinkler of zone1 on for 20 s, then off now
docker compose exec broker mosquitto_pub -q 1 -t field/zone1/sprinkler/cmd -m '{"action":"on","duration_s":20}'
docker compose exec broker mosquitto_pub -q 1 -t field/zone1/sprinkler/cmd -m '{"action":"off"}'

# force rain on all zones: auto | dry | rain (same as the dashboard toggle)
docker compose exec broker mosquitto_pub -q 1 -r -t field/rain/mode -m '{"mode":"rain"}'
docker compose exec broker mosquitto_pub -q 1 -r -t field/rain/mode -m '{"mode":"auto"}'
```

Python (`pip install paho-mqtt`, version 2.x):

```python
import paho.mqtt.client as mqtt

def on_message(client, userdata, msg):
    print(msg.topic, msg.payload.decode())

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message
client.connect("localhost", 1883)
client.subscribe("some/+/topic", qos=1)      # your topic here
client.loop_forever()
```

## Exercise quick guide

| Exercise | You need | File | Check |
|---|---|---|---|
| 1 — HTTP pull | URL pattern `…/zones/<zone>/humidity`, field `value` | `services/central/components/comms.py` → `poll_loop()` | `air.humidity` is not `null` in `curl -s localhost:5100/zones` |
| 2 — MQTT push | topic of the soil readings, wildcard `+`, QoS 1 | `services/central/components/comms.py` → `on_connect()` | `soil.valid` is 3 in every zone (9 sensors) |
| 3 — Data fusion | VPD formula (see `exercises.md`) | `services/central/components/fusion.py` → `vpd_kpa()` | T = 25 °C, RH = 50 % gives `1.584` kPa |
| Assignment | rain topic of one zone, temperature URL | `services/dashboard/assignment/monitor.py` | green banner, charts moving |

After every edit: `docker compose up --build`.

Quick checks:

```bash
docker compose logs -f central                       # "cannot read <url>" lines = HTTP problem; "connected to broker" = MQTT ok
curl -s http://localhost:5100/zones/zone1 | python3 -m json.tool
docker compose exec broker mosquitto_sub -t 'field/+/soil/+' -v     # are the sensors really publishing?
```

Things to try once the exercises work:
- `./ctl.sh zone1 stop temperature` → `air` becomes `null` after ~15 s, `central` keeps running and recovers after `start`.
- `./ctl.sh zone2 stop soil-2` → that sensor shows `offline`, `soil.valid` drops to 2.
- Switch rain to `rain` and watch the soil and humidity values go up.
- Send a manual sprinkler command and read `decision.reason` in the API.

## Common problems

- _"failed to connect to the docker API"_: Docker Desktop is not running.
- _Port already in use_: stop whatever uses 8050, 5100, 5001, 5002, 5011, 5012, 5021, 5022 or 1883.
- _Dashboard shows "n issues" / "humidity missing" at the start_: expected, it is the exercise to complete.
- _A device shows offline after `ctl.sh … stop`_: expected; `./ctl.sh <zone> start <device>` brings it back.
- _`curl` on a zone port returns 404_: each zone container only answers for its own zone (port 5011 → `zone2`, not `zone1`).
- _`/zones` returns 503 "not ready"_: `central` has just started, wait a few seconds.
- _Changes not applied_: run `docker compose up --build`.

## Files to edit

- Exercise 1 (HTTP pull): `services/central/components/comms.py` → `poll_loop()`
- Exercise 2 (MQTT push): `services/central/components/comms.py` → `on_connect()`
- Exercise 3 (data fusion): `services/central/components/fusion.py` → `vpd_kpa()`
- Assignment: `services/dashboard/assignment/monitor.py`