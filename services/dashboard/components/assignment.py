"""Assignment panel: complete the TODOs to start monitoring the field.

Complete the 3 TODOs in this file:

    TODO 1  (top of the file)       write your name and surname
    TODO 2  (top of the file)       the MQTT topic of the rain state of the zone
    TODO 3  (in read_temperature)   the HTTP request for the temperature

Until everything is correct the banner lists what is missing and the header badge stays red;
when all three TODOs are done the charts fill in and the badge turns green.
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
# TODO 1: your name and surname (strings, e.g. "Ada")
# ============================================================================
STUDENT_NAME = "NAME"
STUDENT_SURNAME = "SURNAME"

# ============================================================================
# TODO 2: MQTT topic of the rain state of the zone (QoS 1, retained)
# Pattern: field/<zone>/rain/state — payload {"state": "on" | "off"}
# ============================================================================
ZONE = "zone1"
RAIN_TOPIC = f"field/{ZONE}/"

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
ZONE_TEXT = ZONE.replace("zone", "Zone #")

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
    # TODO 3: complete the URL of the request — GET /zones/<zone>/temperature
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
    """The student name once TODO 1 is filled; None while it is empty or still the placeholder."""
    parts = []
    for value in (STUDENT_NAME, STUDENT_SURNAME):
        if not isinstance(value, str):
            return None
        v = value.strip()
        if not v or v.upper() in ("NAME", "SURNAME"):       # still the scaffold value
            return None
        parts.append(v)
    return " ".join(parts)



_INSTRUCTIONS = (f"Your own monitoring panel for {ZONE_TEXT} which shows temperature over HTTP "
                 "and rain over MQTT. Complete the TODOs in the code and watch it update live.")

# fixed color thresholds (°C -> color) for the temperature line gradient
# hex values of red.6 / orange.6 / yellow.5 / lime.5 / cyan.5 / blue.5 (Mantine palette)
_STOP_TABLE = [(30, "#fa5252"), (25, "#fd7e14"), (20, "#fab005"),
               (15, "#94d82d"), (10, "#3bc9db"), (5, "#4dabf7")]


def _color_at(temp):
    """Color of the table piecewise-linearly interpolated at the given °C value."""
    temp = max(5.0, min(30.0, temp))
    for (t_hi, c_hi), (t_lo, c_lo) in zip(_STOP_TABLE, _STOP_TABLE[1:]):
        if t_lo <= temp <= t_hi:
            f = (temp - t_lo) / (t_hi - t_lo)
            lo = [int(c_lo[i:i + 2], 16) for i in (1, 3, 5)]
            hi = [int(c_hi[i:i + 2], 16) for i in (1, 3, 5)]
            return "#" + "".join(f"{round(lo[i] + f * (hi[i] - lo[i])):02x}" for i in range(3))
    return _STOP_TABLE[-1][1]


def _gradient_stops(values):
    """Stops that link the line color to the ABSOLUTE temperature.

    The SVG gradient has no gradientUnits, so it spans the curve's own
    bounding box: offset 0 is the window maximum, 100 the window minimum.
    To keep a pixel's color tied to its °C value, every threshold strictly
    inside the current window gets a stop at offset = 100 * (wmax - T) / (wmax - wmin),
    and the two window edges get the interpolated colors at wmax / wmin.
    """
    if not values:                                   # chart not fed yet: default ramp
        ramp = ["#fa5252", "#fd7e14", "#fab005", "#94d82d", "#3bc9db", "#4dabf7"]
        return [{"offset": o, "color": c} for o, c in zip([0, 25, 42, 62, 83, 100], ramp)]
    wmax, wmin = max(values), min(values)
    span = wmax - wmin
    if span < 0.05:                                  # flat line: one solid color for its value
        color = _color_at(wmax)
        return [{"offset": 0, "color": color}, {"offset": 100, "color": color}]
    stops = [(0.0, _color_at(wmax))]                 # color at the top of the curve
    stops += [(100.0 * (wmax - t) / span, c) for t, c in _STOP_TABLE if wmin < t < wmax]
    stops.append((100.0, _color_at(wmin)))           # color at the bottom of the curve
    return [{"offset": round(offset), "color": color} for offset, color in stops]


def _chart_paper(label, icon, chart):
    """Chart inside a gray Paper with an icon label, same style as the toolbar model steps."""
    return dmc.Paper(
        radius=RADIUS, p="md", shadow="sm", bg="var(--mantine-color-gray-1)",
        children=dmc.Stack(gap="xs", children=[
            dmc.Group(gap="xs", wrap="nowrap", align="center", children=[
                DashIconify(icon=icon, width=16),
                dmc.Text(label, size="xs", fw=600, c="dimmed", tt="uppercase"),
            ]),
            chart,
        ]),
    )


def assignment():
    _start()
    return dmc.Paper(shadow="sm", radius=RADIUS, p=0, className="lift", children=dmc.Accordion(variant="contained", radius=RADIUS, children=
        dmc.AccordionItem(value="assignment", children=[
            dmc.AccordionControl(dmc.Group(justify="space-between", wrap="nowrap", align="center",
                                           style={"width": "100%"}, children=[
                dmc.Text("Assignment", fw=700, size="lg"),
                dmc.Badge("Not completed", id="asg-badge", color="red", variant="light", size="lg", mr="md",
                          leftSection=DashIconify(icon="tabler:circle-x", width=16)),
            ])),
            dmc.AccordionPanel(dmc.Stack(gap="md", pb="0.3125rem", children=[
                dmc.Text(_INSTRUCTIONS, size="sm", c="dimmed"),
                html.Div(id="asg-banner"),
                dmc.SimpleGrid(cols={"base": 1, "md": 2}, spacing="md", children=[
                    _chart_paper(f"air temperature (°C)", "tabler:temperature",
                                 dmc.LineChart(
                                     id="asg-temp-chart", h=220, data=[], dataKey="t",
                                     series=[{"name": "temperature"}],
                                     type="gradient", strokeWidth=4,
                                     gradientStops=[
                                         {"offset": 0,  "color": "red.6"},     # >= 30 °C hot
                                         {"offset": 25, "color": "orange.6"},  # >= 25 °C
                                         {"offset": 42, "color": "yellow.5"},  # >= 20 °C
                                         {"offset": 62, "color": "lime.5"},    # >= 15 °C
                                         {"offset": 83, "color": "cyan.5"},    # >= 10 °C
                                         {"offset": 100, "color": "blue.5"},   #  =  5 °C cold
                                     ],
                                     curveType="natural", withDots=False, withLegend=False,
                                     unit="°C", gridAxis="y",
                                     yAxisProps={"domain": [5, 30], "ticks": [5, 10, 15, 20, 25, 30]},
                                     lineProps={"isAnimationActive": False}, p="xs"
                                 )),
                    _chart_paper(f"Rain sensor", "tabler:umbrella",
                                 dmc.AreaChart(
                                     id="asg-rain-chart", h=220, data=[], dataKey="t",
                                     series=[{"name": "rain", "color": "cyan.6"}],
                                     curveType="stepAfter", withDots=False, withLegend=False,
                                     withGradient=True, fillOpacity=0.6,
                                     gridAxis="y",
                                     yAxisProps={"domain": [0, 1], "ticks": [0, 1],
                                                 "tick": {"function": "rainTick"}},   # icons in assets/rain-tick.js
                                     areaProps={"strokeWidth": 2, "isAnimationActive": False}, p="xs"
                                 )),
                ]),
                dcc.Interval(id="asg-tick", interval=1000),
            ])),
        ])))


@callback(
    Output("asg-banner", "children"),
    Output("asg-temp-chart", "data"),
    Output("asg-temp-chart", "gradientStops"),
    Output("asg-rain-chart", "data"),
    Output("asg-badge", "children"),
    Output("asg-badge", "color"),
    Output("asg-badge", "leftSection"),
    Input("asg-tick", "n_intervals"),
)
def refresh_assignment(_):
    with _lock:
        temp = list(_temp_hist)
        rain = list(_rain_hist)
        rain_ok, temp_ok = _state["rain_ok"], _state["temp_ok"]

    stops = _gradient_stops([p["temperature"] for p in temp])

    name = _full_name()
    if name and rain_ok and temp_ok:
        banner = dmc.Alert(
            f"Well done {name}! You are now monitoring {ZONE_TEXT} over MQTT and HTTP.",
            color="green", variant="light", radius=RADIUS, fw=600,
            icon=DashIconify(icon="tabler:circle-check", width=22),
        )
        return banner, temp, stops, rain, "Completed", "green", DashIconify(icon="tabler:circle-check", width=16)

    missing = []
    if name is None:
        missing.append("TODO 1 (student name)")
    if not rain_ok:
        missing.append("TODO 2 (MQTT topic of the rain state)")
    if not temp_ok:
        missing.append("TODO 3 (HTTP endpoint of the temperature service)")
    banner = dmc.Alert(
        "Complete: " + ", ".join(missing),
        color="red", variant="light", radius=RADIUS, fw=600,
        icon=DashIconify(icon="tabler:tool", width=22),
    )
    return banner, temp, stops, rain, "Not completed", "red", DashIconify(icon="tabler:circle-x", width=16)