import collections
import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime

import paho.mqtt.client as mqtt

import core

log = logging.getLogger("assignment")


# ============================================================================
# TODO 1 - Insert name and surname.
# ============================================================================
STUDENT_NAME = "gianluca"
STUDENT_SURNAME = "rigatti"

ZONE = "zone1"
ZONE_TEXT = ZONE.replace("zone", "Zone #")      # "zone1" -> "Zone #1"
POLL_S = 1.0                                    # seconds between samples
HISTORY_N = 120                                 # samples kept per chart


# ============================================================================
# TODO 2 - Rain over MQTT (push)
# Topic of the zone's rain state. Payload {"state": "on" | "off"}.
# Hint: the topic has four levels, field/<zone>/<data type>/<detail>,
# find the rain messages in the MQTT log (terminal button).
# ============================================================================
RAIN_TOPIC = f"field/{ZONE}/rain/state"


# ============================================================================
# TODO 3 - Temperature over HTTP (pull)
# Read the zone's current temperature from its service with a GET request.
# The service answers with
# {"zone": ..., "sensor_id": ..., "value": 14.0, "unit": "C", "timestamp": ...}
# Hint: the path has the form /zones/<zone>/<measurement>.
# ============================================================================
TEMPERATURE_URL = os.environ.get("TEMPERATURE_URL", "http://zone1:5001").rstrip("/")
HTTP_TIMEOUT_S = 1.5


def read_temperature():
    """Return the current temperature of the zone, in degrees Celsius."""
    # TODO 3: Complete the URL of the request.
    url = f"{TEMPERATURE_URL}/zones/{ZONE}/temperature"
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as response:
        return float(json.load(response)["value"])


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_temp_history = collections.deque(maxlen=HISTORY_N)
_rain_history = collections.deque(maxlen=HISTORY_N)
_state = {"rain": None, "temp_ok": False}
_warned = set()
_started = False


def _on_connect(client, userdata, flags, reason_code, properties):
    log.info("assignment client connected (%s)", reason_code)
    client.subscribe(RAIN_TOPIC, qos=1)


def _on_message(client, userdata, msg):
    try:
        state = json.loads(msg.payload)["state"]
    except (ValueError, KeyError, TypeError):
        return
    if state in ("on", "off"):
        with _lock:
            _state["rain"] = 1 if state == "on" else 0


_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="assignment")
_client.on_connect = _on_connect
_client.on_message = _on_message
_client.reconnect_delay_set(1, 10)


def _warn_once(key, message):
    if key not in _warned:
        _warned.add(key)
        log.warning(message)


def _sampler():
    """Every POLL_S seconds, sample the temperature and the last known rain state."""
    while True:
        stamp = datetime.now().strftime("%H:%M:%S")

        try:
            temperature = read_temperature()
        except Exception as exc:
            _warn_once("http", f"temperature request failed: {exc!r}")
        else:
            with _lock:
                _temp_history.append({"t": stamp, "temperature": temperature})
                _state["temp_ok"] = True

        with _lock:
            if _state["rain"] is not None:
                _rain_history.append({"t": stamp, "rain": _state["rain"]})

        time.sleep(POLL_S)


def start():
    """Start the sampler thread and the MQTT client. Safe to call more than once."""
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_sampler, daemon=True, name="assignment-sampler").start()
    _client.connect_async(core.MQTT_HOST, core.MQTT_PORT, keepalive=30)
    _client.loop_start()


def snapshot():
    """Return (temperature history, rain history, temp_ok)."""
    with _lock:
        return list(_temp_history), list(_rain_history), _state["temp_ok"]