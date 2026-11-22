import collections
import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

log = logging.getLogger("dashboard")


def _env(name, default, cast=str):
    return cast(os.environ.get(name, default))


def _env_list(name, default):
    return [item.strip() for item in _env(name, default).split(",") if item.strip()]


MQTT_HOST = _env("MQTT_HOST", "localhost")
MQTT_PORT = _env("MQTT_PORT", 1883, int)
CENTRAL_URL = _env("CENTRAL_URL", "http://localhost:5100").rstrip("/")

ZONES = _env_list("ZONES", "zone1,zone2,zone3")
LOG_TOPICS = _env_list("LOG_TOPICS", "field/#,debug/#")
SENSORS_PER_ZONE = _env("SENSORS_PER_ZONE", 3, int)

MAX_MESSAGES = _env("MAX_MESSAGES", 300, int)
HISTORY_N = _env("HISTORY_N", 150, int)
REFRESH_MS = _env("REFRESH_MS", 1000, int)
POLL_S = _env("POLL_S", 1, float)
HTTP_TIMEOUT_S = _env("HTTP_TIMEOUT_S", 1.5, float)
CENTRAL_STALE_S = _env("CENTRAL_STALE_S", 5, float)
PORT = _env("PORT", 8050, int)

RADIUS = _env("RADIUS", "xl")

SENSOR_IDS = {
    zone: [f"soil-{zone}-{i}" for i in range(1, SENSORS_PER_ZONE + 1)] for zone in ZONES
}


lock = threading.Lock()
connected = threading.Event()

log_all = collections.deque(maxlen=MAX_MESSAGES)        # every MQTT message
log_events = collections.deque(maxlen=MAX_MESSAGES)     # without the soil telemetry
history = collections.defaultdict(lambda: collections.deque(maxlen=HISTORY_N))
water_s = collections.defaultdict(float)                # seconds of irrigation per zone

_central_view = None        # latest answer of central's GET /zones
_central_at = None          # when it arrived, on the monotonic clock
_central_wall = None        # and on the UTC wall clock
_last_sample_at = None


def _on_connect(client, userdata, flags, reason_code, properties):
    log.info("connected to broker (%s)", reason_code)
    client.subscribe([(topic, 1) for topic in LOG_TOPICS])
    connected.set()


def _on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    log.warning("disconnected from broker (%s)", reason_code)
    connected.clear()


def _on_message(client, userdata, msg):
    text = msg.payload.decode(errors="replace")
    try:
        data = json.loads(text)
    except ValueError:
        data = None

    parts = msg.topic.split("/")
    is_soil_telemetry = len(parts) == 4 and parts[0] == "field" and parts[2] == "soil"
    line = (
        datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "R" if msg.retain else " ",
        msg.topic,
        text if data is None else json.dumps(data, separators=(",", ":")),
    )

    with lock:
        log_all.append(line)
        if not is_soil_telemetry:
            log_events.append(line)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dashboard")
client.on_connect = _on_connect
client.on_disconnect = _on_disconnect
client.on_message = _on_message
client.reconnect_delay_set(1, 10)


def recent_log(telemetry):
    """Return the MQTT log as text, newest first; `telemetry` includes the soil readings."""
    with lock:
        items = list(log_all if telemetry else log_events)
    return "\n".join(
        f"{stamp} {flag} {topic}  {payload}"
        for stamp, flag, topic, payload in reversed(items)
    )


def _record_history(view):
    """Append one sample per zone and count the sprinkler time. Call with the lock held."""
    global _last_sample_at
    now = time.time()
    # Capped, so that a long gap (central unreachable) is not counted as watering time.
    elapsed = 0.0 if _last_sample_at is None else min(now - _last_sample_at, 5.0)
    _last_sample_at = now

    for zone, info in (view.get("zones") or {}).items():
        sensors = info.get("sensors") or {}
        sprinkler_on = (info.get("sprinkler") or {}).get("state") == "on"
        if sprinkler_on:
            water_s[zone] += elapsed
        history[zone].append({
            "t": now,
            "median": (info.get("soil") or {}).get("median"),
            "thr": (info.get("decision") or {}).get("soil_threshold"),
            "on": sprinkler_on,
            "s": {sid: reading.get("value") for sid, reading in sensors.items()
                  if reading.get("state") == "online"},
        })


def clear_history():
    """Forget the chart history and the sprinkler time of every zone."""
    global _last_sample_at
    with lock:
        history.clear()
        water_s.clear()
        _last_sample_at = None


def _poll_central():
    """Every POLL_S seconds, read the fused state from central (HTTP GET /zones)."""
    global _central_view, _central_at, _central_wall
    url = f"{CENTRAL_URL}/zones"
    unreachable = False

    while True:
        try:
            with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as response:
                view = json.load(response)
        except Exception as exc:
            if not unreachable:
                unreachable = True
                log.warning("cannot read %s: %s", url, exc)
        else:
            if unreachable:
                unreachable = False
                log.info("central reachable again")
            with lock:
                _central_view = view
                _central_at = time.monotonic()
                _central_wall = datetime.now(timezone.utc)
                _record_history(view)

        time.sleep(max(0.05, POLL_S))


def snapshot():
    """Return (zones, central_up, last_update): central's latest view and its freshness."""
    with lock:
        view, at, wall = _central_view, _central_at, _central_wall
    up = at is not None and time.monotonic() - at <= CENTRAL_STALE_S
    return (view.get("zones", {}) if up else {}), up, wall


def start():
    """Start the central poller thread and the MQTT client."""
    threading.Thread(target=_poll_central, daemon=True, name="central-poller").start()
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()