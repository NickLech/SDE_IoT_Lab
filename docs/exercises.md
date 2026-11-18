# Exercises

# EXERCISE 1 - HTTP pull
--> SDE_IoT_Lab\services\central\components\comms.py
            # Each sensor type is a tuple: (name, where to store the readings, base URL).
            # The temperature one is done. TODO: add the humidity one, following the same pattern
            # (it stores into `state.humid` and uses `HUMIDITY_URL`).
            # Done when: the HTTP panel is green for both temperature and humidity.

**Done when**: the HTTP panel turns green and `central` survives stopping/restarting the sensor.

**Solution**
for name, store, base in (("temperature", state.temp, TEMPERATURE_URL),
                          ("humidity", state.humid, HUMIDITY_URL)):

## Example/Exercise 2 — MQTT push
--> SDE_IoT_Lab\services\central\components\comms.py
    # EXERCISE 2 - MQTT push
    # The soil sensors publish by themselves on  field/<zone>/soil/<sensor_id>.
    # TODO: subscribe to the soil readings of ALL zones and ALL sensors with ONE topic,
    #       using the single-level wildcard "+" (QoS 1), as done for the other topics below.
    # Done when: the MQTT panel is green and the 9 soil sensors show up.

**Done when**: the MQTT panel turns green and the 9 soil sensors show up.

**Solution**
("field/+/soil/+", 1),

client.subscribe([("field/+/soil/+", 1), ("field/+/soil/+/status", 1), ("field/+/sprinkler/state", 1),
                  ("field/+/sprinkler/status", 1), ("field/+/sprinkler/cmd", 1), ("field/+/rain/state", 1)])

## Example 3 — Irrigation decision (guided)
Fill in the TODOs of `decision.py::decide_irrigation(zone_state)` together: fused soil estimate + VPD → sprinkler command.

**Done when**: sprinklers switch on/off and the decision panel turns green.

## Final exercise — Tuning
Tune thresholds and duration in `decision.py` so each zone's soil moisture stays **above the minimum but below the maximum** (values in the file) for a given time (e.g. 3 minutes).
