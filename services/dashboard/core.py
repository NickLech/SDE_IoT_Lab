"""Configuration, shared state, MQTT log client and the central poller."""

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _env_list(name, default):
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
CENTRAL_URL = os.environ.get("CENTRAL_URL", "http://localhost:5100").rstrip("/")

ZONES = _env_list("ZONES", "zone1,zone2,zone3")
LOG_TOPICS = _env_list("LOG_TOPICS", "field/#,debug/#")
SENSORS_PER_ZONE = int(os.environ.get("SENSORS_PER_ZONE", 3))

MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", 300))
HISTORY_N = int(os.environ.get("HISTORY_N", 150))
REFRESH_MS = int(os.environ.get("REFRESH_MS", 1000))
POLL_S = float(os.environ.get("POLL_S", 1))
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", 1.5))
CENTRAL_STALE_S = float(os.environ.get("CENTRAL_STALE_S", 5))
PORT = int(os.environ.get("PORT", 8050))

# Global corner-radius token applied to every surface (cards, panels, overlays).
# app.py's MantineProvider theme maps this token to a size; change either here
# (which token) or the theme there (the px) to retune every corner at once.
RADIUS = os.environ.get("RADIUS", "xl")

SENSOR_IDS = {
    z: [f"soil-{z}-{i}" for i in range(1, SENSORS_PER_ZONE + 1)] for z in ZONES
}


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

lock = threading.Lock()

arrivals = collections.deque()
log_all = collections.deque(maxlen=MAX_MESSAGES)
log_events = collections.deque(maxlen=MAX_MESSAGES)

history = collections.defaultdict(lambda: collections.deque(maxlen=HISTORY_N))
water_s = collections.defaultdict(float)
_last_rec = None

central_view = None
central_at = None
central_wall = None

connected = threading.Event()


# ---------------------------------------------------------------------------
# MQTT (message log + rain override publisher)
# ---------------------------------------------------------------------------

def on_connect(client, userdata, flags, reason_code, properties):
    log.info("connected to broker (%s)", reason_code)
    client.subscribe([(topic, 1) for topic in LOG_TOPICS])
    connected.set()


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    log.warning("disconnected from broker (%s)", reason_code)
    connected.clear()


def on_message(client, userdata, msg):
    now = time.monotonic()
    parts = msg.topic.split("/")
    text = msg.payload.decode(errors="replace")

    try:
        data = json.loads(text)
    except ValueError:
        data = None

    is_telemetry = len(parts) == 4 and parts[0] == "field" and parts[2] == "soil"
    payload = json.dumps(data, separators=(",", ":")) if data is not None else text
    line = (
        datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "R" if msg.retain else " ",
        msg.topic,
        payload,
    )

    with lock:
        arrivals.append(now)
        log_all.append(line)
        if not is_telemetry:
            log_events.append(line)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dashboard")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.reconnect_delay_set(1, 10)


def recent_log(telemetry: bool) -> str:
    with lock:
        items = list(log_all if telemetry else log_events)
    return "\n".join(
        f"{stamp} {flag} {topic}  {payload}"
        for stamp, flag, topic, payload in reversed(items)
    )


# ---------------------------------------------------------------------------
# HTTP pull (central) + history
# ---------------------------------------------------------------------------

def record_history(view):
    """Append one sample per zone (called with the lock held)."""
    global _last_rec
    now = time.time()
    dt = 0.0 if _last_rec is None else min(now - _last_rec, 5.0)
    _last_rec = now

    for z, info in (view.get("zones") or {}).items():
        sensors = info.get("sensors") or {}
        on = (info.get("sprinkler") or {}).get("state") == "on"
        if on:
            water_s[z] += dt
        history[z].append({
            "t": now,
            "median": (info.get("soil") or {}).get("median"),
            "thr": (info.get("decision") or {}).get("soil_threshold"),
            "on": on,
            "s": {k: v.get("value") for k, v in sensors.items()
                  if v.get("state") == "online"},
        })


def clear_history():
    global _last_rec
    with lock:
        history.clear()
        water_s.clear()
        _last_rec = None


def poll_central():
    """Read fused state from central using HTTP GET /zones."""
    global central_view, central_at, central_wall
    failing = False

    while True:
        try:
            with urllib.request.urlopen(f"{CENTRAL_URL}/zones", timeout=HTTP_TIMEOUT_S) as r:
                view = json.load(r)
        except Exception as exc:
            if not failing:
                failing = True
                log.warning("cannot read %s/zones: %s", CENTRAL_URL, exc)
        else:
            if failing:
                failing = False
                log.info("central reachable again")
            with lock:
                central_view = view
                central_at = time.monotonic()
                central_wall = datetime.now(timezone.utc)
                record_history(view)

        time.sleep(max(0.05, POLL_S))


def snapshot():
    """Return zones, lag, central status, messages/second and last update time."""
    now = time.monotonic()

    with lock:
        view, at, wall = central_view, central_at, central_wall
        while arrivals and now - arrivals[0] > 5:
            arrivals.popleft()
        rate = len(arrivals) / 5

    up = view is not None and at is not None and now - at <= CENTRAL_STALE_S
    zones = view.get("zones", {}) if up else {}
    lag = now - at if up else 0.0
    return zones, lag, up, rate, wall
