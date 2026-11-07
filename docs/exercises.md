# Exercises

## Example/Exercise 1 — HTTP pull
Complete `pull.py`: `GET` the temperature and humidity sensor of every zone.
1. Handle errors when a container is stopped (`docker compose stop temperature`): timeout, retry/backoff, "unavailable" value.
2. Count useless requests (unchanged value or sensor down) and log it.

**Done when**: the HTTP panel turns green and `central` survives stopping/restarting the sensor.

## Example/Exercise 2 — MQTT push
Complete `subscribe.py`: subscribe with a wildcard (`field/+/soil/+`) and fill in `on_message` (parse JSON, store the last reading per sensor).

**Done when**: the MQTT panel turns green and the 9 soil sensors show up.

## Example 3 — Irrigation decision (guided)
Fill in the TODOs of `decision.py::decide_irrigation(zone_state)` together: fused soil estimate + VPD → sprinkler command.

**Done when**: sprinklers switch on/off and the decision panel turns green.

## Final exercise — Tuning
Tune thresholds and duration in `decision.py` so each zone's soil moisture stays **above the minimum but below the maximum** (values in the file) for a given time (e.g. 3 minutes).
