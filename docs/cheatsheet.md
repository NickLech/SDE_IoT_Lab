# Participant cheat-sheet

## Prerequisites
- Docker + Docker Compose (`docker --version`, `docker compose version`); Docker Desktop must be running
- Repository cloned: `git clone <URL> && cd <repo>`
- On Windows use Git Bash (or WSL) to run `./ctl.sh`

## What runs where
| Container | Contains |
|---|---|
| `broker` | Mosquitto MQTT broker |
| `zone1`, `zone2`, `zone3` | one per zone: `soil-1`, `soil-2`, `soil-3`, `temperature`, `humidity`, `sprinkler` (6 independent processes) |
| `rain` | global rain, drives all zones |
| `central` | data fusion + irrigation decisions |
| `dashboard` | web UI |

## Commands
```bash
docker compose up --build          # start everything
docker compose up -d --build       # in background
docker compose ps                  # container status
docker compose logs -f central     # follow a service's logs (also: zone1, rain, ...)
docker compose restart central     # after editing code
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
./ctl.sh zone1 stop temperature    # test pull errors (air value lost after ~15 s)
./ctl.sh zone3 stop sprinkler      # sprinkler offline: central sends no commands
./ctl.sh zone3 stop all            # every device of the zone (container stays up)
./ctl.sh rain stop                 # global rain: stop | start | restart
```
Without the script: `docker compose exec zone2 zonectl stop soil-2`.

A stopped soil sensor or sprinkler publishes `offline` (retained), so the dashboard shows it immediately. Temperature and humidity are pulled over HTTP: they become unavailable after ~15 s. A crashed process restarts by itself; one you stopped by hand stays stopped.

## Addresses
- Dashboard (field view + MQTT log): http://localhost:8050 — try the sprinkler command below and watch zone 1
- Central API: http://localhost:5100/zones (also `/zones/zone1`, `/health`)
- Temperature / humidity of each zone (host ports):

| Zone | Temperature | Humidity |
|---|---|---|
| zone1 | http://localhost:5001/zones/zone1/temperature | http://localhost:5002/zones/zone1/humidity |
| zone2 | http://localhost:5011/zones/zone2/temperature | http://localhost:5012/zones/zone2/humidity |
| zone3 | http://localhost:5021/zones/zone3/temperature | http://localhost:5022/zones/zone3/humidity |

- MQTT broker: localhost:1883

## MQTT part (working)
```bash
docker compose up --build                       # broker + 3 zones (9 soil sensors, 3 sprinklers) + rain
docker compose --profile debug up monitor       # (other terminal) all field/# and debug/# messages

# sprinkler of zone1 on for 20 s, or off now
docker compose exec broker mosquitto_pub -q 1 -t field/zone1/sprinkler/cmd -m '{"action":"on","duration_s":20}'
docker compose exec broker mosquitto_pub -q 1 -t field/zone1/sprinkler/cmd -m '{"action":"off"}'

# break / fix a sensor (crazy | stuck | drift | none)
docker compose exec broker mosquitto_pub -q 1 -t debug/soil-zone1-1/fault -m crazy
docker compose exec broker mosquitto_pub -q 1 -t debug/soil-zone1-1/fault -m none

# force rain on all zones: auto | dry | rain (same as the dashboard toggle)
docker compose exec broker mosquitto_pub -q 1 -r -t field/rain/mode -m '{"mode":"rain"}'

# current retained state of sprinklers and sensors
docker compose exec broker mosquitto_sub -t 'field/+/sprinkler/state' -t 'field/+/sprinkler/status' -t 'field/+/soil/+/status' -W 2 -v

# automatic check (pip install paho-mqtt); start the stack with a fast simulation:
TIME_SCALE=8 docker compose up --build
python tests/smoke_mqtt.py
```

## Trying HTTP and MQTT by hand
```bash
curl http://localhost:5002/zones/zone1/humidity
curl -X POST http://localhost:5002/debug/fault -H "Content-Type: application/json" -d '{"sensor_id":"hum-zone1","mode":"crazy"}'
python tests/smoke_humidity.py                  # automatic check of the humidity service
curl http://localhost:5001/zones/zone1/temperature
mosquitto_sub -h localhost -t 'field/+/soil/+' -v
```

## Common problems
- _"failed to connect to the docker API"_: Docker Desktop is not running.
- _Port already in use_: stop whatever uses 8050/5100/5001/5002/5011/5012/5021/5022/1883.
- _Dashboard all red_: expected at the start, it is the exercise to complete.
- _A device shows offline after `ctl.sh ... stop`_: expected; `./ctl.sh <zone> start <device>` brings it back.
- _`ctl.sh`: "bad interpreter" or `\r` errors_: the file has Windows line endings, run `dos2unix ctl.sh`.
- _Changes not applied_: `docker compose up --build`.

## Files to edit
- Exercise 1: `services/central/pull.py`
- Exercise 2: `services/central/subscribe.py`
- Exercise 3/4: `services/central/decision.py`
