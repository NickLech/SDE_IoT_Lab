"""Communication with the other nodes, in one file but two separate sections:

  1. MQTT  (push)  soil sensors, sprinkler state/commands, rain  +  our own sprinkler commands
  2. HTTP  (pull)  air temperature and humidity services

It only moves data in and out of `state`; no fusion or decision logic here.
"""
import collections
import json
import logging
import threading
import time
import urllib.request

import paho.mqtt.client as mqtt

from components import state
from components.config import (AIR_WINDOW, HTTP_TIMEOUT_S, HUMIDITY_URL, MQTT_HOST, MQTT_PORT, POLL_INTERVAL_S,
                               SPRINKLER_DEFAULT_S, TEMPERATURE_URL, ZONES)
from components.state import is_number, lock

log = logging.getLogger("central.comms")

# =============================================================================== 1. MQTT
#   field/<zone>/soil/<sensor_id>          {"value": %}
#   field/<zone>/soil/<sensor_id>/status   "online" | "offline"   (Last Will)
#   field/<zone>/sprinkler/state           {"state": "on"|"off"}  (retained)
#   field/<zone>/sprinkler/status          "online" | "offline"   (Last Will)
#   field/<zone>/sprinkler/cmd             {"action": "on"|"off", "duration_s": N, "source": "central"?}
#   field/<zone>/rain/state                {"state": "on"|"off"}


def on_connect(client, userdata, flags, reason_code, properties):
    log.info("connected to broker (%s)", reason_code)
    client.subscribe([("field/+/soil/+", 1), ("field/+/soil/+/status", 1), ("field/+/sprinkler/state", 1),
                      ("field/+/sprinkler/status", 1), ("field/+/sprinkler/cmd", 1), ("field/+/rain/state", 1)])
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
            if isinstance(data, dict) and is_number(data.get("value")):
                state.soil[(zone, parts[3])] = (float(data["value"]), now)
        elif kind == "soil" and len(parts) == 5 and parts[4] == "status":
            state.status[(zone, parts[3])] = text
        elif kind == "rain" and len(parts) == 4 and parts[3] == "state" and isinstance(data, dict):
            state.rain[zone] = data.get("state")
        elif kind == "sprinkler" and parts[3] == "status":     # field/<zone>/sprinkler/status (plain text)
            state.sprinkler_status[zone] = text
        elif kind == "sprinkler" and len(parts) == 4 and isinstance(data, dict):
            if parts[3] == "cmd":
                manual = data.get("source") != "central"      # our own commands are tagged, anything else is manual
                if data.get("action") == "on":
                    duration = data.get("duration_s", SPRINKLER_DEFAULT_S)
                    if is_number(duration):
                        state.cmd_until[zone] = now + float(duration)
                        if manual:
                            state.manual_until[zone] = now + float(duration)
                elif data.get("action") == "off":
                    state.cmd_until.pop(zone, None)
                    if manual:
                        state.manual_until[zone] = now      # override ends now (the cooldown starts)
            elif parts[3] == "state":
                new_state = data.get("state")
                sp = state.sprinkler[zone]
                sp["state"] = new_state
                # keep the known end time across repeated "on" states; clear it otherwise
                sp["until"] = state.cmd_until.pop(zone, sp["until"]) if new_state == "on" else None


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="central")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.reconnect_delay_set(1, 10)


def send_command(zone, action, duration_s=None):
    """Publishes a sprinkler command tagged with source=central (so it is not mistaken for a manual one)."""
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


# ================================================================================ 2. HTTP
#   GET $TEMPERATURE_URL/zones/<zone>/temperature   {"value": degC}   ("{zone}" in the URL -> zone name)
#   GET $HUMIDITY_URL/zones/<zone>/humidity         {"value": %RH}
#   Each value is appended to a small window (AIR_WINDOW samples); fusion.py takes the median.


def poll_loop():
    """Polls the temperature and humidity services and stores the last value per zone."""
    failing = set()
    while True:
        for zone in ZONES:
            for name, store, base in (("temperature", state.temp, TEMPERATURE_URL),
                                      ("humidity", state.humid, HUMIDITY_URL)):
                url = f"{base.format(zone=zone)}/zones/{zone}/{name}"
                try:
                    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as resp:
                        value = float(json.load(resp)["value"])
                except Exception as exc:       # network, HTTP status, bad JSON...
                    if url not in failing:
                        failing.add(url)
                        log.warning("cannot read %s: %s", url, exc)
                    continue
                if url in failing:
                    failing.discard(url)
                    log.info("%s reachable again", url)
                with lock:
                    store.setdefault(zone, collections.deque(maxlen=AIR_WINDOW)).append((value, time.monotonic()))
        time.sleep(POLL_INTERVAL_S)


def start_polling():
    threading.Thread(target=poll_loop, daemon=True, name="poll").start()
