"""Assignment panel: complete the TODOs to start monitoring the field.

Complete the 3 TODOs in this file:

    TODO 1  (top of the file)       write your name and surname
    TODO 2  (top of the file)       the MQTT topic of the rain state of the zone
    TODO 3  (in read_temperature)   the HTTP request for the temperature

Until everything is correct the charts stay empty.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime

import dash_mantine_components as dmc
import paho.mqtt.client as mqtt
from dash import Input, Output, callback, dcc, html
from dash_iconify import DashIconify

from core import RADIUS

log = logging.getLogger("assignment")


# ============================================================================
# TODO 1 - your name and surname (strings, e.g. "Ada")
# ============================================================================
STUDENT_NAME = "Pat"
STUDENT_SURNAME = "Il Boss"

# ============================================================================
# TODO 2 - MQTT topic of the rain state of the zone (QoS 1, retained)
# Complete the f-string: field/<zone>/....
# The payload is {"state": "on" | "off"}
# ============================================================================
ZONE = "zone1"
RAIN_TOPIC = f"field/{ZONE}/rain/state"   # f"field/{ZONE}/...."


# ---------------------------------------------------------------------------
# Configuration (do not edit)
# ---------------------------------------------------------------------------

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
# base URL of the temperature service of the zone (inside docker: http://zone1:5001)
TEMPERATURE_URL = os.environ.get("TEMPERATURE_URL", "http://zone1:5001").rstrip("/")

POLL_S = 1.0
HTTP_TIMEOUT_S = 1.5
HISTORY_N = 120
_EXPECTED_RAIN_TOPIC = f"field/{ZONE}/rain/state"   # used only to validate the exercise


# ---------------------------------------------------------------------------
# Shared state (do not edit)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_temp_hist = collections.deque(maxlen=HISTORY_N)
_rain_hist = collections.deque(maxlen=HISTORY_N)
_state = {"rain": None, "rain_ok": False, "temp_ok": False}
_warned = set()
_started = False


def _warn_once(key, message):
    if key not in _warned:
        _warned.add(key)
        log.warning(message)


# ---------------------------------------------------------------------------
# MQTT (push)
# ---------------------------------------------------------------------------

def _on_connect(client, userdata, flags, reason_code, properties):
    log.info("assignment client connected (%s)", reason_code)
    client.subscribe(RAIN_TOPIC, qos=1)


def _on_message(client, userdata, msg):
    if msg.topic != _EXPECTED_RAIN_TOPIC:
        return
    try:
        state = json.loads(msg.payload)["state"]
    except (ValueError, KeyError, TypeError):
        return
    if state not in ("on", "off"):
        return
    with _lock:
        _state["rain"] = 1 if state == "on" else 0
        _state["rain_ok"] = True


_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="assignment")
_client.on_connect = _on_connect
_client.on_message = _on_message
_client.reconnect_delay_set(1, 10)


# ---------------------------------------------------------------------------
# HTTP (pull)
# ---------------------------------------------------------------------------

def read_temperature():
    """Return the current temperature (float) of the zone.

    The service answers GET /zones/<zone>/temperature with
    {"zone": ..., "sensor_id": ..., "value": 14.0, "unit": "C", "timestamp": ...}
    """
    # TODO 3: complete the URL of the request (replace the `....` at the end)
    #with urllib.request.urlopen(f"{TEMPERATURE_URL}/zones/{ZONE}/....", timeout=HTTP_TIMEOUT_S) as r:
    with urllib.request.urlopen(f"{TEMPERATURE_URL}/zones/{ZONE}/temperature", timeout=HTTP_TIMEOUT_S) as r:
        return float(json.load(r)["value"])


def _sampler():
    """Every POLL_S: read the temperature and sample the last known rain state."""
    while True:
        label = datetime.now().strftime("%H:%M:%S")

        try:
            value = read_temperature()
        except Exception as exc:
            _warn_once("http", f"temperature request failed: {exc!r}")
        else:
            with _lock:
                _temp_hist.append({"t": label, "temperature": value})
                _state["temp_ok"] = True

        with _lock:
            if _state["rain"] is not None:
                _rain_hist.append({"t": label, "rain": _state["rain"]})

        time.sleep(POLL_S)


def _start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_sampler, daemon=True, name="assignment-sampler").start()
    _client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    _client.loop_start()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _full_name():
    n, s = STUDENT_NAME, STUDENT_SURNAME
    if isinstance(n, str) and isinstance(s, str) and n.strip() and s.strip():
        return f"{n.strip()} {s.strip()}"
    return None


def assignment():
    _start()
    return dmc.Accordion(variant="contained", radius=RADIUS, className="lift", children=
        dmc.AccordionItem(value="fusion", children=[
            dmc.AccordionControl(dmc.Text("Assignment", fw=600, size="lg")),
            dmc.AccordionPanel(dmc.Stack(gap="md", children=[
                html.Div(id="asg-banner"),
                dmc.SimpleGrid(cols={"base": 1, "md": 2}, spacing="md", children=[
                    dmc.Stack(gap="xs", children=[
                        dmc.Text(f"Temperature ({ZONE})", fw=600, size="sm"),
                        dmc.LineChart(
                            id="asg-temp-chart", h=220, data=[], dataKey="t",
                            series=[{"name": "temperature", "color": "orange.6"}],
                            curveType="natural", withDots=False, withLegend=False,
                            unit="°C", gridAxis="y", yAxisProps={"domain": [0, 25]},
                            lineProps={"strokeWidth": 2, "isAnimationActive": False},
                        ),
                    ]),
                    dmc.Stack(gap="xs", children=[
                        dmc.Text(f"Rain ({ZONE}): 1 = raining, 0 = dry", fw=600, size="sm"),
                        dmc.LineChart(
                            id="asg-rain-chart", h=220, data=[], dataKey="t",
                            series=[{"name": "rain", "color": "cyan.6"}],
                            curveType="stepAfter", withDots=False, withLegend=False,
                            gridAxis="y", yAxisProps={"domain": [0, 1], "ticks": [0, 1]},
                            lineProps={"strokeWidth": 2, "isAnimationActive": False},
                        ),
                    ]),
                ]),
                dcc.Interval(id="asg-tick", interval=1000),
            ])),
        ]))


@callback(
    Output("asg-banner", "children"),
    Output("asg-temp-chart", "data"),
    Output("asg-rain-chart", "data"),
    Input("asg-tick", "n_intervals"),
)
def refresh_assignment(_):
    with _lock:
        temp = list(_temp_hist)
        rain = list(_rain_hist)
        done = _state["rain_ok"] and _state["temp_ok"]

    name = _full_name()
    banner = None
    if done and name:
        banner = dmc.Alert(
            f"{name} Good job, now you can monitor the field!",
            color="green", variant="light", radius=RADIUS, fw=600,
            icon=DashIconify(icon="tabler:circle-check", width=22),
        )
    return banner, temp, rain