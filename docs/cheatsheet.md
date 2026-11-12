# Participant cheat-sheet

## Prerequisites
- Docker + Docker Compose (`docker --version`, `docker compose version`); Docker Desktop must be running
- Repository cloned: `git clone <URL> && cd <repo>`

## Commands
```bash
docker compose up --build          # start everything
docker compose up -d --build       # in background
docker compose ps                  # container status
docker compose logs -f central     # follow a service's logs
docker compose stop temperature    # stop a sensor (to test pull errors)
docker compose start temperature   # start it again
docker compose restart central     # after editing code
docker compose down                # stop everything
```

## Addresses
- Dashboard (field view + MQTT log): http://localhost:8050 — try the sprinkler command below and watch zone 1
- Central API: http://localhost:5100/state
- Temperature: http://localhost:5001/zones/zone1/temperature
- Humidity: http://localhost:5002/zones/zone1/humidity
- MQTT broker: localhost:1883

## MQTT part (working)
```bash
docker compose up --build                       # broker + soil (9 sensors) + sprinkler
docker compose --profile debug up monitor       # (other terminal) all field/# and debug/# messages

# sprinkler of zone1 on for 20 s, or off now
docker compose exec broker mosquitto_pub -q 1 -t field/zone1/sprinkler/cmd -m '{"action":"on","duration_s":20}'
docker compose exec broker mosquitto_pub -q 1 -t field/zone1/sprinkler/cmd -m '{"action":"off"}'

# break / fix a sensor (crazy | stuck | drift | none)
docker compose exec broker mosquitto_pub -q 1 -t debug/soil-zone1-1/fault -m crazy
docker compose exec broker mosquitto_pub -q 1 -t debug/soil-zone1-1/fault -m none

# current retained state of sprinklers and sensors
docker compose exec broker mosquitto_sub -t 'field/+/sprinkler/state' -t 'field/+/soil/+/status' -W 2 -v

# automatic check (pip install paho-mqtt); start the stack with a fast simulation:
TIME_SCALE=8 docker compose up --build
python tests/smoke_mqtt.py
```

## Trying HTTP and MQTT by hand
```bash
curl http://localhost:5002/zones/zone1/humidity
curl -X POST http://localhost:5002/debug/fault -H "Content-Type: application/json" -d '{"sensor_id":"hum-zone1","mode":"crazy"}'
python tests/smoke_humidity.py                  # automatic check of the humidity service
curl http://localhost:5001/zones/zone1/temperature   # once the temperature service exists
mosquitto_sub -h localhost -t 'field/+/soil/+' -v
```

## Common problems
- _"failed to connect to the docker API"_: Docker Desktop is not running.
- _Port already in use_: stop whatever uses 8050/5000/5001/5002/1883.
- _Dashboard all red_: expected at the start, it is the exercise to complete.
- _Changes not applied_: `docker compose up --build`.

## Files to edit
- Exercise 1: `services/central/pull.py`
- Exercise 2: `services/central/subscribe.py`
- Exercise 3/4: `services/central/decision.py`
