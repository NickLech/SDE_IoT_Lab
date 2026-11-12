from __future__ import annotations

import collections
import json
import logging
import math
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
import plotly.graph_objects as go
from dash import ALL, Dash, Input, Output, ctx, dcc, html
from waitress import serve


log = logging.getLogger("dashboard")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))

CENTRAL_URL = os.environ.get(
    "CENTRAL_URL", "http://localhost:5100"
).rstrip("/")

ZONES = [
    z.strip()
    for z in os.environ.get("ZONES", "zone1,zone2,zone3").split(",")
    if z.strip()
]

SENSORS_PER_ZONE = int(os.environ.get("SENSORS_PER_ZONE", 3))

LOG_TOPICS = [
    t.strip()
    for t in os.environ.get(
        "LOG_TOPICS", "field/#,debug/#"
    ).split(",")
    if t.strip()
]

MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", 300))
REFRESH_MS = int(os.environ.get("REFRESH_MS", 1000))
POLL_S = float(os.environ.get("POLL_S", 1))
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", 1.5))
CENTRAL_STALE_S = float(os.environ.get("CENTRAL_STALE_S", 5))
PORT = int(os.environ.get("PORT", 8050))

SENSOR_IDS = {
    z: [f"soil-{z}-{i}" for i in range(1, SENSORS_PER_ZONE + 1)]
    for z in ZONES
}

VPD_TEXT = {
    "low": "too humid",
    "ok": "optimal",
    "high": "high",
    "stress": "water stress",
}

# Minimal chart palette.
C_WATER = "#2f7ed8"
C_WARN = "#d6911f"
C_IDLE = "#b8bec7"
C_LINE = "#8a94a0"
C_THRESHOLD = "#d6911f"


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

lock = threading.Lock()

arrivals = collections.deque()
log_all = collections.deque(maxlen=MAX_MESSAGES)
log_events = collections.deque(maxlen=MAX_MESSAGES)

central_view = None
central_at = None

connected = threading.Event()

HISTORY_N = int(os.environ.get("HISTORY_N", 150))
history = collections.defaultdict(lambda: collections.deque(maxlen=HISTORY_N))
water_s = collections.defaultdict(float)
_last_rec = None


# ---------------------------------------------------------------------------
# MQTT (message log only)
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

    is_telemetry = (
        len(parts) == 4
        and parts[0] == "field"
        and parts[2] == "soil"
    )

    payload = (
        json.dumps(data, separators=(",", ":"))
        if data is not None
        else text
    )

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


client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id="dashboard",
)

client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.reconnect_delay_set(1, 10)


# ---------------------------------------------------------------------------
# HTTP pull (central)
# ---------------------------------------------------------------------------

def poll_central():
    """Read fused state from central using HTTP GET /zones."""

    global central_view, central_at

    failing = False

    while True:
        try:
            with urllib.request.urlopen(
                f"{CENTRAL_URL}/zones",
                timeout=HTTP_TIMEOUT_S,
            ) as response:
                view = json.load(response)
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
                record_history(view)

        time.sleep(max(0.05, POLL_S))


def record_history(view):
    """Append one sample per zone (called with the lock held)."""
    global _last_rec
    now = time.time()
    dt = 0.0 if _last_rec is None else min(now - _last_rec, 5.0)
    _last_rec = now
    for z, info in (view.get("zones") or {}).items():
        sensors = info.get("sensors", {}) or {}
        on = (info.get("sprinkler") or {}).get("state") == "on"
        if on:
            water_s[z] += dt
        history[z].append({
            "t": now,
            "median": (info.get("soil") or {}).get("median"),
            "thr": (info.get("decision") or {}).get("soil_threshold"),
            "vpd": (info.get("vpd") or {}).get("kpa"),
            "on": on,
            "s": {k: v.get("value") for k, v in sensors.items()
                  if v.get("state") == "online"},
        })



# ---------------------------------------------------------------------------
# View model
# ---------------------------------------------------------------------------

def snapshot():
    """Return zones, lag, central status and MQTT messages/second."""

    now = time.monotonic()

    with lock:
        view = central_view
        at = central_at

        while arrivals and now - arrivals[0] > 5:
            arrivals.popleft()

        rate = len(arrivals) / 5

    up = (
        view is not None
        and at is not None
        and now - at <= CENTRAL_STALE_S
    )

    zones = view.get("zones", {}) if up else {}
    lag = now - at if up else 0.0

    return zones, lag, up, rate


def age_text(age):
    if age is None:
        return ""
    return f"{age:.0f}s ago" if age < 60 else ">1 min"


# ---------------------------------------------------------------------------
# Per-zone chart
# ---------------------------------------------------------------------------

def zone_figure(zone, info):
    """Soil moisture over time: sensors, fused median, threshold, irrigation bands."""
    with lock:
        pts = list(history.get(zone, []))

    figure = go.Figure()
    figure.update_layout(
        height=190,
        margin={"l": 34, "r": 10, "t": 6, "b": 22},
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font={"family": "inherit", "size": 10, "color": "#626e81"},
        hovermode="x unified",
        yaxis={"range": [0, 100], "ticksuffix": "%", "zeroline": False,
               "gridcolor": "rgba(98,110,129,.14)", "ticks": "", "fixedrange": True},
        xaxis={"showgrid": False, "zeroline": False, "ticks": "",
               "tickformat": "%H:%M:%S", "fixedrange": True},
    )

    if len(pts) < 2:
        figure.add_annotation(text="collecting data…", showarrow=False,
                              font={"size": 11})
        return figure

    xs = [datetime.fromtimestamp(p["t"]) for p in pts]

    # irrigation bands
    start = None
    for x, p in zip(xs, pts):
        if p["on"] and start is None:
            start = x
        elif not p["on"] and start is not None:
            figure.add_vrect(x0=start, x1=x, fillcolor=C_WATER, opacity=0.10,
                             line_width=0, layer="below")
            start = None
    if start is not None:
        figure.add_vrect(x0=start, x1=xs[-1], fillcolor=C_WATER, opacity=0.10,
                         line_width=0, layer="below")

    # raw sensors (thin) -> shows the redundancy that fusion works on
    for sid in SENSOR_IDS[zone]:
        figure.add_trace(go.Scatter(
            x=xs, y=[p["s"].get(sid) for p in pts], mode="lines",
            name=sid.replace(f"soil-{zone}-", "s"), opacity=0.45,
            line={"width": 1, "color": C_LINE},
            hovertemplate=sid.replace(f"soil-{zone}-", "s") + " %{y:.0f}%<extra></extra>",
        ))

    # fused median
    figure.add_trace(go.Scatter(
        x=xs, y=[p["median"] for p in pts], mode="lines", name="median",
        line={"width": 2.5, "color": C_WATER, "shape": "spline", "smoothing": 0.6},
        fill="tozeroy", fillcolor="rgba(47,126,216,0.12)",
        hovertemplate="median %{y:.0f}%<extra></extra>",
    ))

    # threshold
    figure.add_trace(go.Scatter(
        x=xs, y=[p["thr"] for p in pts], mode="lines", name="threshold",
        line={"width": 1.5, "color": C_THRESHOLD, "dash": "dot"},
        hovertemplate="irrigate below %{y:.0f}%<extra></extra>",
    ))

    # latest value of each sensor; amber = suspect (outlier flagged by central)
    sensors = info.get("sensors", {})
    for sid in SENSOR_IDS[zone]:
        s = sensors.get(sid, {})
        v = s.get("value")
        if v is None or s.get("state") != "online":
            continue
        figure.add_trace(go.Scatter(
            x=[xs[-1]], y=[v], mode="markers", hoverinfo="skip",
            marker={"size": 7, "color": C_WARN if s.get("suspect") else C_WATER,
                    "line": {"width": 1.5, "color": "#fff"}},
        ))

    return figure


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def fact(label, value, klass="fact"):
    return html.Div(
        className=klass,
        children=[
            html.Span(label, className="fact-label"),
            html.Span(value, className="fact-value"),
        ],
    )


def air_text(info):
    air = info.get("air", {})
    t, rh = air.get("temperature"), air.get("humidity")
    if t is None and rh is None:
        return "missing"
    if t is None:
        return f"{rh:.0f}% RH · temperature missing"
    if rh is None:
        return f"{t:.1f}°C · humidity missing"
    return f"{t:.1f}°C · {rh:.0f}% RH"


def vpd_text(info):
    vpd = info.get("vpd")
    if not vpd or vpd.get("kpa") is None:
        return "– (no air reading)"
    band = vpd.get("band", "unknown")
    return f"{vpd['kpa']:.2f} kPa · {VPD_TEXT.get(band, band)}"


def decision_info(info):
    """Return (text, css-class) for the zone decision bar."""

    decision = info.get("decision", {}) or {}
    action = decision.get("action")
    reason = decision.get("reason")
    threshold = decision.get("soil_threshold")

    if action == "on":
        text = f"Irrigating — {reason}" if reason else "Irrigating"
        return text, "decision on"
    if action == "off":
        text = f"Irrigation stopped — {reason}" if reason else "Irrigation stopped"
        return text, "decision off"
    if threshold is not None:
        return f"Hold — irrigate below {threshold:.0f}%", "decision"
    return str(reason or "No decision yet"), "decision"


def command_text(info):
    last = info.get("last_command")
    if not last:
        return "none"
    duration = last.get("duration_s")
    action = last.get("action", "?")
    if duration is None:
        return f"{action} · {last.get('at')}"
    return f"{action} · {duration}s · {last.get('at')}"


def sensor_text(zone, info):
    sensors = info.get("sensors", {})
    expected = len(SENSOR_IDS.get(zone, [])) or SENSORS_PER_ZONE
    online = sum(1 for s in sensors.values() if s.get("state") == "online")
    suspects = sum(1 for s in sensors.values() if s.get("suspect"))
    text = f"{online}/{expected} online"
    if suspects:
        text += f" · {suspects} suspect"
    return text


def spread_text(info):
    vals = [
        s["value"] for s in (info.get("sensors") or {}).values()
        if s.get("state") == "online" and s.get("value") is not None
    ]
    if len(vals) < 2:
        return "–"
    return f"±{(max(vals) - min(vals)) / 2:.1f} pts"


def zone_facts(zone, info):
    with lock:
        watered = water_s.get(zone, 0.0)
    return [
        fact("air", air_text(info)),
        fact("VPD", vpd_text(info)),
        fact("sensors", sensor_text(zone, info)),
        fact("agreement", spread_text(info)),
        fact("watered", f"{watered / 60:.1f} min"),
        fact("last cmd", command_text(info)),
    ]


def zone_hero(info):
    """Big readout: fused soil moisture and distance from the irrigation threshold."""
    median = (info.get("soil") or {}).get("median")
    thr = (info.get("decision") or {}).get("soil_threshold")
    if median is None:
        return [html.Div([html.Div("–", className="hero-value"),
                          html.Div("soil moisture", className="hero-label")])]
    gap = None if thr is None else median - thr
    if gap is None:
        delta = html.Div("no threshold", className="hero-delta")
    elif gap >= 0:
        delta = html.Div(f"{gap:.0f} pts above threshold", className="hero-delta ok")
    else:
        delta = html.Div(f"{-gap:.0f} pts below threshold", className="hero-delta low")
    return [
        html.Div([
            html.Div([html.Span(f"{median:.0f}", className="hero-value"),
                      html.Span("%", className="hero-unit")]),
            html.Div("median soil moisture", className="hero-label"),
        ]),
        delta,
    ]


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def stat(value_id, label):
    return html.Div(
        className="stat",
        children=[
            html.Div(id=value_id, className="stat-value", children="–"),
            html.Div(label, className="stat-label"),
        ],
    )


def status_chip(value_id, label):
    return html.Div(
        className="status-chip",
        children=[
            html.Span(id=value_id, className="dot bad"),
            html.Span(label),
        ],
    )


def zone_card(zone):
    return html.Div(
        id={"type": "zone-card", "zone": zone},
        className="zone card",
        children=[
            html.Div(className="rain-layer"),
            html.Div(
                className="zone-head",
                children=[
                    html.Span(zone.replace("zone", "Zone "), className="zone-title"),
                    html.Div(
                        className="zone-tags",
                        children=[
                            html.Span(id={"type": "rain-chip", "zone": zone},
                                      className="rain-chip", children="rain –"),
                            html.Span(id={"type": "zone-badge", "zone": zone},
                                      className="badge idle",
                                      children=[html.Span(className="sp-icon"),
                                                "sprinkler –"]),
                        ],
                    ),
                ],
            ),
            html.Div(id={"type": "zone-hero", "zone": zone}, className="hero",
                     children=zone_hero({})),
            dcc.Graph(
                id={"type": "zone-graph", "zone": zone},
                figure=zone_figure(zone, {}),
                config={"displayModeBar": False},
                style={"height": "190px"},
            ),
            html.Div(id={"type": "zone-decision", "zone": zone},
                     className="decision", children="–"),
            html.Div(id={"type": "zone-facts", "zone": zone},
                     className="facts", children=zone_facts(zone, {})),
        ],
    )


app = Dash(
    __name__,
    title="Irrigation field",
    enable_mcp=True,
    mcp_path="/_mcp",
    health_endpoint="health",
)

try:
    from dash.mcp import configure_mcp_server
    configure_mcp_server(expose_callback_docstrings=True)
except ImportError:
    pass


app.layout = html.Div(
    children=[
        html.Div(
            className="topbar",
            children=[
                html.Div(
                    className="topbar-inner",
                    children=[
                        html.Div(
                            className="brand",
                            children=[
                                html.Div(
                                    children=[
                                        html.Div(
                                            "LAB 6 - IoT monitoring with SOA",
                                            className="brand-title",
                                        ),
                                        html.Div(style={"height": "0.1em"}),
                                        html.Div(
                                            "Service Design & Engineering @UniTN",
                                            className="brand-sub",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        html.Div(
                            className="topbar-actions",
                            children=[
                                html.Button(
                                    "Clear history",
                                    id="clear-history",
                                    className="clear-btn",
                                    title="Reset the zone charts and counters",
                                ),
                                html.Span(
                                    id="clear-note", className="clear-note"
                                ),
                                html.Span(
                                    id="conn",
                                    className="pill off",
                                    children="connecting…",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        html.Div(
            className="page",
            children=[
                html.Div(
                    className="strip card",
                    children=[
                        stat("ov-soil", "avg soil moisture"),
                        stat("ov-water", "irrigation time"),
                        stat("ov-sensors", "soil sensors"),
                        stat("ov-sprinklers", "sprinklers on"),
                        stat("ov-rain", "zones raining"),
                        stat("ov-rate", "messages / s"),
                        html.Div(className="strip-divider"),
                        html.Div(
                            className="pipeline",
                            children=[
                                html.Span(
                                    "Pipeline",
                                    className="pipeline-title",
                                ),
                                status_chip("ex-pull", "HTTP pull"),
                                status_chip("ex-push", "MQTT push"),
                                status_chip("ex-decision", "Irrigation"),
                            ],
                        ),
                    ],
                ),

                html.Div(
                    className="zones",
                    children=[zone_card(z) for z in ZONES],
                ),

                html.Div(
                    className="bottom",
                    children=[
                        html.Div(
                            className="control card",
                            children=[
                                html.Div(
                                    "Rain source",
                                    className="section-label",
                                ),
                                dcc.RadioItems(
                                    id="rain-mode",
                                    options=[
                                        {"label": "Auto", "value": "auto"},
                                        {"label": "Manual · dry", "value": "dry"},
                                        {"label": "Manual · raining", "value": "rain"},
                                    ],
                                    value="auto",
                                    className="rain-toggle",
                                ),
                                html.Div(id="rain-note", className="note"),

                                html.Details(
                                    className="about",
                                    children=[
                                        html.Summary(
                                            "How central fuses the data"
                                        ),
                                        html.Ul(
                                            className="about-list",
                                            children=[
                                                html.Li(
                                                    "Level 0: drop physically "
                                                    "impossible readings "
                                                    "(outside 0–100%)."
                                                ),
                                                html.Li(
                                                    "Redundant soil: median of "
                                                    "3 sensors per zone; "
                                                    "outliers are flagged."
                                                ),
                                                html.Li(
                                                    "Cooperative air: "
                                                    "temperature + humidity "
                                                    "→ VPD (kPa)."
                                                ),
                                                html.Li(
                                                    "Decision: soil median vs "
                                                    "a VPD-adjusted threshold, "
                                                    "with a cooldown."
                                                ),
                                            ],
                                        ),
                                        html.P(
                                            className="about-note",
                                            children=[
                                                "Manual rain override publishes "
                                                "the retained ",
                                                html.Code(
                                                    "field/<zone>/rain/state"
                                                ),
                                                " from the dashboard; the rain "
                                                "service may overwrite it on "
                                                "its next cycle.",
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),

                        html.Div(
                            className="logpanel card",
                            children=[
                                html.Div(
                                    className="log-head",
                                    children=[
                                        html.Span(
                                            "MQTT log",
                                            className="section-label",
                                        ),
                                        dcc.Checklist(
                                            id="show-telemetry",
                                            options=[
                                                {
                                                    "label": " show telemetry",
                                                    "value": "t",
                                                }
                                            ],
                                            value=[],
                                            className="log-toggle",
                                        ),
                                    ],
                                ),
                                html.Pre(
                                    id="log",
                                    children="waiting for messages…",
                                ),
                            ],
                        ),
                    ],
                ),

                dcc.Interval(
                    id="tick",
                    interval=REFRESH_MS,
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Dashboard callbacks
# ---------------------------------------------------------------------------

@app.callback(
    Output({"type": "zone-badge", "zone": ALL}, "className"),
    Output({"type": "zone-badge", "zone": ALL}, "children"),
    Output({"type": "zone-graph", "zone": ALL}, "figure"),
    Output({"type": "zone-facts", "zone": ALL}, "children"),
    Output({"type": "zone-decision", "zone": ALL}, "children"),
    Output({"type": "zone-decision", "zone": ALL}, "className"),
    Output({"type": "rain-chip", "zone": ALL}, "children"),
    Output({"type": "rain-chip", "zone": ALL}, "className"),
    Output("ov-sensors", "children"),
    Output("ov-sprinklers", "children"),
    Output("ov-rate", "children"),
    Output("ov-rain", "children"),
    Output("conn", "children"),
    Output("conn", "className"),
    Output("ex-pull", "className"),
    Output("ex-push", "className"),
    Output("ex-decision", "className"),
    Output({"type": "zone-card", "zone": ALL}, "className"),
    Output({"type": "zone-hero", "zone": ALL}, "children"),
    Output("ov-soil", "children"),
    Output("ov-water", "children"),
    Input("tick", "n_intervals"),
)
def refresh(_):
    zones, lag, central_up, rate = snapshot()

    zone_ids = [output["id"]["zone"] for output in ctx.outputs_list[0]]

    def info(z):
        if central_up:
            return zones.get(z) or {"zone": z}
        return {"zone": z}

    def sensor_count(z):
        sensors = info(z).get("sensors", {})
        return sum(1 for s in sensors.values() if s.get("state") == "online")

    total_sensors = sum(len(SENSOR_IDS[z]) for z in zone_ids)

    sprinkler_text = {"on": "ON", "off": "OFF", "offline": "OFFLINE", "unknown": "–"}

    (
        badges,
        badge_children,
        figures,
        facts,
        decisions,
        decision_classes,
        rains,
        rain_classes,
    ) = [], [], [], [], [], [], [], []
    cards, heroes = [], []

    for z in zone_ids:
        i = info(z)
        sp = i.get("sprinkler", {}).get("state", "unknown")
        remaining = i.get("sprinkler", {}).get("remaining_s")

        badges.append(f"badge sp-{sp if sp in sprinkler_text else 'unknown'}")

        label = f"sprinkler {sprinkler_text.get(sp, sp)}"
        if remaining is not None:
            label += f" · {max(0, remaining - lag):.0f}s left"
        badge_children.append([html.Span(className="sp-icon"), label])

        figures.append(zone_figure(z, i))

        facts.append(zone_facts(z, i))

        text, klass = decision_info(i)
        decisions.append(text)
        decision_classes.append(klass)

        rain = i.get("rain", "unknown")
        rains.append(f"rain {rain}")
        rain_classes.append("rain-chip on" if rain == "on" else "rain-chip")
        heroes.append(zone_hero(i))
        cards.append(
            "zone card"
            + (" raining" if rain == "on" else "")
            + (" watering" if sp == "on" else "")
        )

    online = sum(sensor_count(z) for z in zone_ids)
    sprinklers_on = sum(info(z).get("sprinkler", {}).get("state") == "on" for z in zone_ids)
    raining = sum(info(z).get("rain") == "on" for z in zone_ids)
    medians = [
        m for m in ((info(z).get("soil") or {}).get("median") for z in zone_ids)
        if m is not None
    ]
    avg_soil = f"{sum(medians) / len(medians):.0f}%" if medians else "–"
    with lock:
        water_min = sum(water_s.values()) / 60

    mqtt_up = connected.is_set()

    link = (
        f"central {'OK' if central_up else 'UNREACHABLE'} · "
        f"log {'connected' if mqtt_up else 'DISCONNECTED'}"
    )

    # Exercise status, inferred from the data (central has no exercise flags in this contract).
    links = (central_view or {}).get("links", {}) if central_up else {}
    pull_ok = bool(links.get("temperature")) and bool(links.get("humidity"))
    pull_warn = bool(links.get("temperature")) or bool(links.get("humidity"))

    push_ok = mqtt_up and all(
        len(info(z).get("sensors", {})) >= len(SENSOR_IDS[z])
        and all(s.get("state") == "online" for s in info(z).get("sensors", {}).values())
        for z in zone_ids
    )
    push_warn = mqtt_up and any(
        any(s.get("state") == "online" for s in info(z).get("sensors", {}).values())
        for z in zone_ids
    )

    decision_ok = any(info(z).get("last_command") for z in zone_ids)
    decision_warn = any(
        (info(z).get("decision", {}) or {}).get("soil_threshold") is not None
        for z in zone_ids
    )

    def chip(ok, warn):
        return "dot ok" if ok else "dot warn" if warn else "dot bad"

    return (
        badges,
        badge_children,
        figures,
        facts,
        decisions,
        decision_classes,
        rains,
        rain_classes,
        f"{online} / {total_sensors}",
        f"{sprinklers_on} / {len(zone_ids)}",
        f"{rate:.1f}",
        f"{raining} / {len(zone_ids)}",
        link,
        "pill on" if central_up else "pill off",
        chip(pull_ok, pull_warn),
        chip(push_ok, push_warn),
        chip(decision_ok, decision_warn),
        cards,
        heroes,
        avg_soil,
        f"{water_min:.1f} min",
    )


# ---------------------------------------------------------------------------
# Clear plot history (lecture reset)
# ---------------------------------------------------------------------------

@app.callback(
    Output("clear-note", "children"),
    Input("clear-history", "n_clicks"),
    prevent_initial_call=True,
)
def clear_history(_):
    """Drop buffered samples so the zone charts start fresh.

    The next refresh redraws the charts empty ("collecting data…") and they
    refill from the live polling stream.
    """

    global _last_rec

    with lock:
        history.clear()
        water_s.clear()
        _last_rec = None

    return f"cleared at {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"


# ---------------------------------------------------------------------------
# Rain override (lecture demo)
# ---------------------------------------------------------------------------

@app.callback(
    Output("rain-note", "children"),
    Input("rain-mode", "value"),
)
def rain_override(mode):
    if mode == "auto":
        return "rain: automatic, set by the rain service"

    state = "on" if mode == "rain" else "off"

    if not connected.is_set():
        return "rain: manual selected, but the dashboard is not connected to the broker"

    payload = json.dumps({"state": state})
    for z in ZONES:
        client.publish(
            f"field/{z}/rain/state",
            payload,
            qos=1,
            retain=True,
        )

    return f"rain: manual {state} published to {len(ZONES)} zones"


# ---------------------------------------------------------------------------
# MQTT log callback
# ---------------------------------------------------------------------------

@app.callback(
    Output("log", "children"),
    Input("tick", "n_intervals"),
    Input("show-telemetry", "value"),
    prevent_initial_call=True,
)
def refresh_log(_, show):
    with lock:
        items = list(log_all if "t" in (show or []) else log_events)

    lines = [
        f"{stamp} {flag} {topic}  {payload}"
        for stamp, flag, topic, payload in reversed(items)
    ]

    return "\n".join(lines) or "waiting for messages..."


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    threading.Thread(
        target=poll_central,
        daemon=True,
        name="central-poller",
    ).start()

    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()

    log.info(
        "serving on port %d, central at %s, MCP enabled at /_mcp",
        PORT,
        CENTRAL_URL,
    )

    serve(
        app.server,
        host="0.0.0.0",
        port=PORT,
        threads=16,
    )
