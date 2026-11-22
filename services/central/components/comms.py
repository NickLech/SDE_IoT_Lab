import collections
import json
import logging
import threading
import time
import urllib.request

import paho.mqtt.client as mqtt

from components import state
from components.config import (AIR_WINDOW, HTTP_TIMEOUT_S, HUMIDITY_URL, MQTT_HOST, MQTT_PORT,
                               POLL_INTERVAL_S, SPRINKLER_DEFAULT_S, TEMPERATURE_URL, ZONES)
from components.state import is_number, lock

log = logging.getLogger("central.comms")


# ---- MQTT (push) ---------------------------------------------------------------
# Topics, all under field/<zone>/:
#   soil/<sensor_id>          {"value": %}
#   soil/<sensor_id>/status   "online" | "offline"      (Last Will)
#   sprinkler/state           {"state": "on" | "off"}   (retained)
#   sprinkler/status          "online" | "offline"      (Last Will)
#   sprinkler/cmd             {"action": "on" | "off", "duration_s": N}
#                             central adds "source": "central" to its own commands
#   rain/state                {"state": "on" | "off"}

def on_connect(client, userdata, flags, reason_code, properties):
    log.info("connected to broker (%s)", reason_code)
    # Exercise 2 - MQTT push
    # Soil sensors publish their readings on field/<zone>/soil/<sensor_id>.
    # TODO: subscribe to all soil readings with a single wildcard topic (QoS 1), following
    #       the pattern of the topics below.
    # Hint: "field/+/soil/+" has four levels; the /status topics are subscribed separately.
    # Done when: the MQTT panel is green and all 9 soil sensors appear.
    client.subscribe([
        ("field/+/soil/+", 1),          # solution
        ("field/+/soil/+/status", 1),
        ("field/+/sprinkler/state", 1),
        ("field/+/sprinkler/status", 1),
        ("field/+/sprinkler/cmd", 1),
        ("field/+/rain/state", 1),
    ])
    state.connected.set()


def on_disconnect(client, userdata, flags, reason_code, properties):
    log.warning("disconnected from broker (%s)", reason_code)
    state.connected.clear()


def on_message(client, userdata, msg):
    now = time.monotonic()
    parts = msg.topic.split("/")
    if len(parts) < 4 or parts[0] != "field" or parts[1] not in ZONES:
        return
    zone, kind = parts[1], parts[2]
    text = msg.payload.decode(errors="replace").strip()
    try:
        data = json.loads(text)
    except ValueError:
        data = None

    with lock:
        if kind == "soil" and len(parts) == 4:
            _store_soil_reading(zone, parts[3], data, now)
        elif kind == "soil" and len(parts) == 5 and parts[4] == "status":
            state.status[(zone, parts[3])] = text
        elif kind == "rain" and len(parts) == 4 and parts[3] == "state" and isinstance(data, dict):
            state.rain[zone] = data.get("state")
        elif kind == "sprinkler" and parts[3] == "status":
            state.sprinkler_status[zone] = text
        elif kind == "sprinkler" and len(parts) == 4 and isinstance(data, dict):
            if parts[3] == "cmd":
                _store_command(zone, data, now)
            elif parts[3] == "state":
                _store_sprinkler_state(zone, data)


def _store_soil_reading(zone, sensor_id, data, now):
    if isinstance(data, dict) and is_number(data.get("value")):
        state.soil[(zone, sensor_id)] = (float(data["value"]), now)


def _store_command(zone, data, now):
    """Track how long a command keeps the sprinkler on, and whether a person sent it."""
    manual = data.get("source") != "central"      # central tags its own commands
    action = data.get("action")
    if action == "on":
        duration = data.get("duration_s", SPRINKLER_DEFAULT_S)
        if is_number(duration):
            state.cmd_until[zone] = now + float(duration)
            if manual:
                state.manual_until[zone] = now + float(duration)
    elif action == "off":
        state.cmd_until.pop(zone, None)
        if manual:
            state.manual_until[zone] = now        # the override ends now, the cooldown starts


def _store_sprinkler_state(zone, data):
    new_state = data.get("state")
    sprinkler = state.sprinkler[zone]
    sprinkler["state"] = new_state
    # A repeated "on" keeps the end time already known; any other state clears it.
    if new_state == "on":
        sprinkler["until"] = state.cmd_until.pop(zone, sprinkler["until"])
    else:
        sprinkler["until"] = None


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="central")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.reconnect_delay_set(1, 10)


def send_command(zone, action, duration_s=None):
    """Publish a sprinkler command tagged source=central, so it is not taken for a manual one."""
    payload = {"action": action, "source": "central"}
    if action == "on":
        payload["duration_s"] = round(duration_s)
    client.publish(f"field/{zone}/sprinkler/cmd", json.dumps(payload), qos=1)
    log.info("%s: command %s", zone, payload)


def start_mqtt():
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()


def stop_mqtt():
    client.loop_stop()
    client.disconnect()


# ---- HTTP (pull) ---------------------------------------------------------------
#   GET $TEMPERATURE_URL/zones/<zone>/temperature   {"value": °C}
#   GET $HUMIDITY_URL/zones/<zone>/humidity         {"value": %RH}
# "{zone}" in a base URL is replaced by the zone name. Each value is appended to a small
# window of AIR_WINDOW samples; fusion.py takes its median.

def poll_loop():
    """Poll the temperature and humidity services and store the recent values per zone."""
    unreachable = set()
    while True:
        for zone in ZONES:
            # Exercise 1 - HTTP pull (humidity)
            # Each sensor type is a tuple (name, store, base URL).
            # TODO: add the humidity tuple, following the temperature one: it stores into
            #       `state.humid` and uses `HUMIDITY_URL`.
            # Done when: the HTTP panel is green for both temperature and humidity.
            sensors = (
                ("temperature", state.temp, TEMPERATURE_URL),
                ("humidity", state.humid, HUMIDITY_URL),        # solution
            )
            for name, store, base in sensors:
                _poll_sensor(zone, name, store, base, unreachable)
        time.sleep(POLL_INTERVAL_S)


def _poll_sensor(zone, name, store, base, unreachable):
    """Read one value over HTTP; log only when the service goes away and when it comes back."""
    url = f"{base.format(zone=zone)}/zones/{zone}/{name}"
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as response:
            value = float(json.load(response)["value"])
    except Exception as exc:       # network, HTTP status, bad JSON...
        if url not in unreachable:
            unreachable.add(url)
            log.warning("cannot read %s: %s", url, exc)
        return

    if url in unreachable:
        unreachable.discard(url)
        log.info("%s reachable again", url)
    with lock:
        window = store.setdefault(zone, collections.deque(maxlen=AIR_WINDOW))
        window.append((value, time.monotonic()))


def start_polling():
    threading.Thread(target=poll_loop, daemon=True, name="poll").start()