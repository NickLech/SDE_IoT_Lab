# Exercises

# EXERCISE 1 - HTTP pull
--> SDE_IoT_Lab\services\central\components\comms.py
            # Each sensor type is a tuple: (name, where to store the readings, base URL).
            # The temperature one is done. TODO: add the humidity one, following the same pattern
            # (it stores into `state.humid` and uses `HUMIDITY_URL`).
            # Done when: the HTTP panel is green for both temperature and humidity.

**Done when**: the HTTP panel turns green and `central` survives stopping/restarting the sensor.

## Example/Exercise 2 — MQTT push
Complete `subscribe.py`: subscribe with a wildcard (`field/+/soil/+`) and fill in `on_message` (parse JSON, store the last reading per sensor).

**Done when**: the MQTT panel turns green and the 9 soil sensors show up.

## Example 3 — Irrigation decision (guided)
Fill in the TODOs of `decision.py::decide_irrigation(zone_state)` together: fused soil estimate + VPD → sprinkler command.

**Done when**: sprinklers switch on/off and the decision panel turns green.

## Final exercise — Tuning
Tune thresholds and duration in `decision.py` so each zone's soil moisture stays **above the minimum but below the maximum** (values in the file) for a given time (e.g. 3 minutes).
