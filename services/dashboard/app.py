"""Dashboard: thin client of the central node + an MQTT message log.

All the "intelligence" (soil fusion, VPD, irrigation decision) lives in `central`.
The dashboard only displays it:

  HTTP  GET <CENTRAL_URL>/zones        every POLL_S   -> soil median, sensors, air, VPD, sprinkler, decision
  MQTT  field/#, debug/#                                -> ONLY the raw message log and the msg/s counter

Contracts: docs/architecture.md
"""
import collections
import json
import logging
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from dash import ALL, Dash, Input, Output, ctx, dcc, html
from waitress import serve

log = logging.getLogger("dashboard")

# ----------------------------------------------------------------------------- config
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
CENTRAL_URL = os.environ.get("CENTRAL_URL", "http://localhost:5000").rstrip("/")
ZONES = [z.strip() for z in os.environ.get("ZONES", "zone1,zone2,zone3").split(",") if z.strip()]
SENSORS_PER_ZONE = int(os.environ.get("SENSORS_PER_ZONE", 3))
LOG_TOPICS = [t.strip() for t in os.environ.get("LOG_TOPICS", "field/#,debug/#").split(",") if t.strip()]
MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", 300))
REFRESH_MS = int(os.environ.get("REFRESH_MS", 1000))
POLL_S = float(os.environ.get("POLL_S", 1))                      # how often central is polled
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", 1.5))
CENTRAL_STALE_S = float(os.environ.get("CENTRAL_STALE_S", 5))    # no answer from central for this long -> "unreachable"
PORT = int(os.environ.get("PORT", 8050))

SENSOR_IDS = {z: [f"soil-{z}-{i}" for i in range(1, SENSORS_PER_ZONE + 1)] for z in ZONES}
VPD_TEXT = {"low": "too humid", "ok": "optimal", "high": "high", "stress": "water stress"}
NO_SENSOR = {"state": "offline", "value": None, "age_s": None, "suspect": False}

# ----------------------------------------------------------------------- shared state
lock = threading.Lock()
arrivals = collections.deque()                        # arrival times of recent MQTT messages (msg/s tile)
log_all = collections.deque(maxlen=MAX_MESSAGES)      # every logged message
log_events = collections.deque(maxlen=MAX_MESSAGES)   # same without telemetry (commands, states, status)
central_view = None                                   # last JSON received from central GET /zones
central_at = None                                     # monotonic time of that answer
connected = threading.Event()                         # MQTT (log only)


# ------------------------------------------------------------------- MQTT (log only)
def on_connect(client, userdata, flags, reason_code, properties):
    log.info("connected to broker (%s)", reason_code)
    client.subscribe([(t, 1) for t in LOG_TOPICS])
    connected.set()


def on_disconnect(client, userdata, flags, reason_code, properties):
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
    line = (datetime.now(timezone.utc).strftime("%H:%M:%S"), "R" if msg.retain else " ",
            msg.topic, json.dumps(data, separators=(",", ":")) if data is not None else text)
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


# ------------------------------------------------------------------- HTTP pull (central)
def poll_central():
    """Reads the fused state from the central node (plain HTTP GET) and keeps the last answer."""
    global central_view, central_at
    failing = False
    while True:
        try:
            with urllib.request.urlopen(f"{CENTRAL_URL}/zones", timeout=HTTP_TIMEOUT_S) as resp:
                view = json.load(resp)
        except Exception as exc:                 # network, HTTP 503 (central not ready), bad JSON...
            if not failing:
                failing = True
                log.warning("cannot read %s/zones: %s", CENTRAL_URL, exc)
        else:
            if failing:
                failing = False
                log.info("central reachable again")
            with lock:
                central_view, central_at = view, time.monotonic()
        time.sleep(POLL_S)


# --------------------------------------------------------------------------- view model
def snapshot():
    """Returns (zones, lag_s, central_up, rate): central's per-zone view, its age, link status, msg/s."""
    now = time.monotonic()
    with lock:
        view, at = central_view, central_at
        while arrivals and now - arrivals[0] > 5:
            arrivals.popleft()
        rate = len(arrivals) / 5
    up = view is not None and now - at <= CENTRAL_STALE_S
    return (view["zones"] if up else {}), (now - at if up else 0.0), up, rate


def age_text(age):
    if age is None:
        return ""
    return f"{age:.0f}s ago" if age < 60 else ">1 min"


# --------------------------------------------------------------------------------- UI
# One water drop each: horizontal reach, peak height and fall distance (px), varied for a natural spray
DROPS = [(-108, -30, 78), (-88, -22, 92), (-68, -34, 70), (-50, -26, 100), (-32, -36, 84), (-14, -20, 108),
         (14, -20, 108), (32, -36, 84), (50, -26, 100), (68, -34, 70), (88, -22, 92), (108, -30, 78)]


def sprinkler_widget():
    jets = [html.Div(className="jet",
                     style={"--dx": f"{dx}px", "--lift": f"{lift}px", "--fall": f"{fall}px",
                            "--delay": f"{(i * 0.37) % 1.1:.2f}s"},
                     children=html.Div(className="drop"))
            for i, (dx, lift, fall) in enumerate(DROPS)]
    return html.Div(className="sprinkler", children=[
        html.Div(className="spray", children=jets),
        html.Div(className="head"),
        html.Div(className="riser"),
    ])


def zone_card(zone):
    rows = [html.Div(id={"type": "s-row", "sensor": sid}, className="srow offline", children=[
        html.Span(className="dot"),
        html.Span(sid, className="sname"),
        html.Div(className="bar", children=html.Div(id={"type": "s-bar", "sensor": sid}, className="bar-fill")),
        html.Span(id={"type": "s-value", "sensor": sid}, className="sval", children="–"),
        html.Span(id={"type": "s-age", "sensor": sid}, className="sage"),
    ]) for sid in SENSOR_IDS[zone]]
    return html.Div(id={"type": "zone", "zone": zone}, className="zone sp-unknown", children=[
        html.Div(className="zone-head", children=[
            html.Span(zone.replace("zone", "Zone "), className="zone-title"),
            html.Span(id={"type": "sp-label", "zone": zone}, className="sp-badge", children="sprinkler: –"),
        ]),
        html.Div(className="tile", children=[
            html.Div(id={"type": "zone-fill", "zone": zone}, className="fill", style={"height": "0%"}),
            sprinkler_widget(),
            html.Div(className="readout", children=[
                html.Div(id={"type": "zone-value", "zone": zone}, className="big", children="–"),
                html.Div(id={"type": "zone-note", "zone": zone}, className="note"),
            ]),
        ]),
        html.Div(id={"type": "zone-vpd", "zone": zone}, className="vpd none", children="VPD –"),
        html.Div(id={"type": "zone-decision", "zone": zone}, className="decision", children="–"),
        html.Div(className="sensors", children=rows),
    ])


app = Dash(__name__, title="Irrigation field")
app.layout = html.Div(className="page", children=[
    html.Div(className="header", children=[
        html.H1("Irrigation field"),
        html.Span(id="conn", className="pill off", children="connecting…"),
    ]),
    html.Div(className="zones", children=[zone_card(z) for z in ZONES]),
    html.Div(className="overview card", children=[
        html.Div(className="stats", children=[
            html.Div(className="stat", children=[html.Div(id="ov-sensors", className="stat-value"),
                                                 html.Div("soil sensors online", className="stat-label")]),
            html.Div(className="stat", children=[html.Div(id="ov-sprinklers", className="stat-value"),
                                                 html.Div("sprinklers on", className="stat-label")]),
            html.Div(className="stat", children=[html.Div(id="ov-rate", className="stat-value"),
                                                 html.Div("messages / s", className="stat-label")]),
        ]),
        html.Div(className="legend", children=[
            html.Span([html.Span(className="dot online"), "sensor online"]),
            html.Span([html.Span(className="dot offline"), "sensor offline"]),
            html.Span([html.Span("⚠", className="warn-mark"), "suspect reading"]),
        ]),
    ]),
    html.Div(className="logpanel card", children=[
        html.Div(className="log-head", children=[
            html.Span("MQTT log", className="log-title"),
            dcc.Checklist(id="show-telemetry", options=[{"label": " telemetry", "value": "t"}], value=[],
                          className="log-toggle", inline=True),
        ]),
        html.Pre(id="log"),
    ]),
    dcc.Interval(id="tick", interval=REFRESH_MS),
])


# ----------------------------------------------------------------------------- callbacks
@app.callback(
    Output({"type": "zone", "zone": ALL}, "className"),
    Output({"type": "zone-value", "zone": ALL}, "children"),
    Output({"type": "zone-note", "zone": ALL}, "children"),
    Output({"type": "zone-fill", "zone": ALL}, "style"),
    Output({"type": "sp-label", "zone": ALL}, "children"),
    Output({"type": "s-row", "sensor": ALL}, "className"),
    Output({"type": "s-bar", "sensor": ALL}, "style"),
    Output({"type": "s-value", "sensor": ALL}, "children"),
    Output({"type": "s-age", "sensor": ALL}, "children"),
    Output("ov-sensors", "children"),
    Output("ov-sprinklers", "children"),
    Output("ov-rate", "children"),
    Output("conn", "children"),
    Output("conn", "className"),
    Output({"type": "zone-vpd", "zone": ALL}, "children"),
    Output({"type": "zone-vpd", "zone": ALL}, "className"),
    Output({"type": "zone-decision", "zone": ALL}, "children"),
    Input("tick", "n_intervals"),
)
def refresh(_):
    zones, lag, central_up, rate = snapshot()
    zone_ids = [o["id"]["zone"] for o in ctx.outputs_list[0]]      # order Dash expects
    sensor_ids = [o["id"]["sensor"] for o in ctx.outputs_list[5]]

    sensors = {sid: s for info in zones.values() for sid, s in info["sensors"].items()}
    sensor = lambda sid: sensors.get(sid, NO_SENSOR)
    sp_state = lambda z: zones[z]["sprinkler"]["state"] if z in zones else "unknown"
    median = lambda z: zones[z]["soil"]["median"] if z in zones else None

    sp_text = {"on": "ON", "off": "OFF", "offline": "OFFLINE", "unknown": "–"}
    labels = []
    for z in zone_ids:
        text = f"sprinkler {sp_text.get(sp_state(z), sp_state(z))}"
        remaining = zones[z]["sprinkler"]["remaining_s"] if z in zones else None
        if remaining is not None:
            text += f" · {max(0, remaining - lag):.0f}s left"
        labels.append(text)

    def note(z):
        if z not in zones:
            return "central unreachable"
        soil_z = zones[z]["soil"]
        return "no valid reading" if soil_z["median"] is None else f"median of {soil_z['valid']} sensors"

    def vpd_text(z):
        info = zones.get(z)
        if info is None:
            return "VPD – (central unreachable)"
        v, air = info["vpd"], info["air"]
        if v is None:
            return "VPD – (no air reading)"
        return f"VPD {v['kpa']:.2f} kPa · {VPD_TEXT[v['band']]} · {air['temperature']:.1f}°C · {air['humidity']:.0f}% RH"

    def decision_text(z):
        info = zones.get(z)
        if info is None:
            return "–"
        d = info["decision"]
        return f"irrigate below {d['soil_threshold']:.0f}% · {d['reason']}"

    online = sum(sensor(s)["state"] == "online" for s in sensor_ids)
    suspects = sum(bool(sensor(s)["suspect"]) for s in sensor_ids)
    on = sum(sp_state(z) == "on" for z in zone_ids)
    offline = sum(sp_state(z) == "offline" for z in zone_ids)
    mqtt_up = connected.is_set()
    link = f"central {'OK' if central_up else 'UNREACHABLE'} · log {'connected' if mqtt_up else 'DISCONNECTED'}"

    def age(sid):
        a = sensor(sid)["age_s"]
        return age_text(None if a is None else a + lag)

    return (
        [f"zone sp-{sp_state(z) if sp_state(z) in sp_text else 'unknown'}" for z in zone_ids],
        ["–" if median(z) is None else f"{median(z):.0f}%" for z in zone_ids],
        [note(z) for z in zone_ids],
        [{"height": f"{0 if median(z) is None else min(100, max(0, median(z))):.1f}%"} for z in zone_ids],
        labels,
        [f"srow {sensor(s)['state']}" + (" suspect" if sensor(s)["suspect"] else "") for s in sensor_ids],
        [{"width": f"{0 if sensor(s)['value'] is None else min(100, max(0, sensor(s)['value'])):.1f}%"}
         for s in sensor_ids],
        ["–" if sensor(s)["value"] is None else f"{sensor(s)['value']:.1f}%" for s in sensor_ids],
        [age(s) for s in sensor_ids],
        [f"{online} / {len(sensor_ids)}"] + ([html.Small(f" · {suspects} suspect")] if suspects else []),
        [f"{on} / {len(zone_ids)}"] + ([html.Small(f" · {offline} offline")] if offline else []),
        f"{rate:.1f}",
        link,
        "pill on" if central_up else "pill off",
        [vpd_text(z) for z in zone_ids],
        ["vpd " + (zones[z]["vpd"]["band"] if z in zones and zones[z]["vpd"] else "none") for z in zone_ids],
        [decision_text(z) for z in zone_ids],
    )


@app.callback(Output("log", "children"), Input("tick", "n_intervals"), Input("show-telemetry", "value"))
def refresh_log(_, show):
    with lock:
        items = list(log_all if "t" in (show or []) else log_events)
    lines = [f"{stamp} {flag} {topic}  {payload}" for stamp, flag, topic, payload in reversed(items)]
    return "\n".join(lines) or "waiting for messages..."


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    threading.Thread(target=poll_central, daemon=True).start()
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    log.info("serving on port %d, central at %s", PORT, CENTRAL_URL)
    serve(app.server, host="0.0.0.0", port=PORT, threads=16)   # several participants may open the page
