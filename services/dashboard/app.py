"""Dashboard: live view of the field (soil sensors, sprinklers) + an MQTT message log.

Everything is built from the MQTT messages seen since startup (no DB, no `central` yet):
  field/<zone>/soil/<sensor_id>          telemetry   -> sensor value and freshness
  field/<zone>/soil/<sensor_id>/status   Last Will   -> online / offline
  field/<zone>/sprinkler/state           retained    -> sprinkler on / off / offline
  field/<zone>/sprinkler/cmd             commands    -> countdown while a sprinkler is on
  GET <TEMPERATURE_URL>/zones/<zone>/temperature   (HTTP pull)  -> air temperature  } VPD per zone
  GET <HUMIDITY_URL>/zones/<zone>/humidity         (HTTP pull)  -> air humidity     }

Contracts: docs/architecture.md
"""
import collections
import json
import logging
import math
import os
import statistics
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
ZONES = [z.strip() for z in os.environ.get("ZONES", "zone1,zone2,zone3").split(",") if z.strip()]
SENSORS_PER_ZONE = int(os.environ.get("SENSORS_PER_ZONE", 3))
LOG_TOPICS = [t.strip() for t in os.environ.get("LOG_TOPICS", "field/#,debug/#").split(",") if t.strip()]
MAX_MESSAGES = int(os.environ.get("MAX_MESSAGES", 300))
REFRESH_MS = int(os.environ.get("REFRESH_MS", 1000))
STALE_AFTER_S = float(os.environ.get("STALE_AFTER_S", 8))        # no reading for this long -> sensor offline
SUSPECT_DELTA = float(os.environ.get("SUSPECT_DELTA", 15))       # distance from zone median (%) -> "suspect"
SPRINKLER_DEFAULT_S = float(os.environ.get("SPRINKLER_DEFAULT_S", 30))   # keep equal to the sprinkler service
SPRINKLER_MAX_S = float(os.environ.get("SPRINKLER_MAX_S", 300))          # idem
# VPD (kPa). Bands are generic: tune them per crop / growth stage.
VPD_LOW = float(os.environ.get("VPD_LOW", 0.4))                  # below -> too humid (fungal risk)
VPD_HIGH = float(os.environ.get("VPD_HIGH", 1.2))                # above -> high
VPD_STRESS = float(os.environ.get("VPD_STRESS", 1.6))            # above -> water stress
TEMPERATURE_URL = os.environ.get("TEMPERATURE_URL", "http://localhost:5001").rstrip("/")
HUMIDITY_URL = os.environ.get("HUMIDITY_URL", "http://localhost:5002").rstrip("/")
POLL_S = float(os.environ.get("POLL_S", 2))                      # how often the temperature/humidity services are polled
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", 1.5))
AIR_STALE_AFTER_S = float(os.environ.get("AIR_STALE_AFTER_S", 15))   # no temperature/humidity for this long -> no VPD
LEAF_TEMP_OFFSET = float(os.environ.get("LEAF_TEMP_OFFSET", 0))  # leaf is this many degC colder than air (0 = air VPD)
PORT = int(os.environ.get("PORT", 8050))

SENSOR_IDS = {z: [f"soil-{z}-{i}" for i in range(1, SENSORS_PER_ZONE + 1)] for z in ZONES}

# ----------------------------------------------------------------------- shared state
lock = threading.Lock()
soil = {}                                   # sensor_id -> (value, received_at)
status = {}                                 # sensor_id -> "online" | "offline"
sprinkler = {z: {"state": None, "until": None} for z in ZONES}
cmd_until = {}                              # zone -> expected end of the last "on" command
arrivals = collections.deque()              # arrival times of recent messages (msg/s tile)
log_all = collections.deque(maxlen=MAX_MESSAGES)      # every logged message
log_events = collections.deque(maxlen=MAX_MESSAGES)   # same without telemetry (commands, states, status)
temp = {}                                   # zone -> (degC, received_at)   (HTTP pull)
humid = {}                                  # zone -> (%RH, received_at)    (HTTP pull)
connected = threading.Event()


# ------------------------------------------------------------------------------- MQTT
def on_connect(client, userdata, flags, reason_code, properties):
    log.info("connected to broker (%s)", reason_code)
    client.subscribe("field/#", qos=1)
    client.subscribe("debug/#", qos=1)
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

    with lock:
        arrivals.append(now)
        if is_telemetry and isinstance(data, dict) and isinstance(data.get("value"), (int, float)):
            soil[parts[3]] = (float(data["value"]), now)
        elif len(parts) == 5 and parts[2] == "soil" and parts[4] == "status":
            status[parts[3]] = text
        elif len(parts) == 4 and parts[2] == "sprinkler" and parts[1] in sprinkler and isinstance(data, dict):
            zone = parts[1]
            if parts[3] == "cmd" and data.get("action") == "on":
                try:
                    cmd_until[zone] = now + min(float(data.get("duration_s", SPRINKLER_DEFAULT_S)), SPRINKLER_MAX_S)
                except (TypeError, ValueError):
                    pass
            elif parts[3] == "state":
                state = data.get("state")
                sprinkler[zone]["state"] = state
                # keep the known end time across repeated "on" states; clear it otherwise
                sprinkler[zone]["until"] = cmd_until.pop(zone, sprinkler[zone]["until"]) if state == "on" else None

        if any(mqtt.topic_matches_sub(f, msg.topic) for f in LOG_TOPICS):
            line = (datetime.now(timezone.utc).strftime("%H:%M:%S"), "R" if msg.retain else " ",
                    msg.topic, json.dumps(data, separators=(",", ":")) if data is not None else text)
            log_all.append(line)
            if not is_telemetry:
                log_events.append(line)


# ------------------------------------------------------------------- HTTP pull (air)
def poll_loop():
    """Polls the temperature and humidity services (plain HTTP, no MQTT) and stores the last value per zone."""
    failing = set()
    while True:
        for zone in ZONES:
            for name, store, base in (("temperature", temp, TEMPERATURE_URL), ("humidity", humid, HUMIDITY_URL)):
                url = f"{base}/zones/{zone}/{name}"
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
                    store[zone] = (value, time.monotonic())
        time.sleep(POLL_S)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dashboard")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.reconnect_delay_set(1, 10)


# --------------------------------------------------------------------------- view model
def svp_kpa(t_c):
    """Saturation vapor pressure (kPa), Tetens/Magnus formula."""
    return 0.6108 * math.exp(17.27 * t_c / (t_c + 237.3))


def vpd_kpa(t_c, rh, leaf_offset=0.0):
    """Vapor pressure deficit (kPa) = SVP(leaf) - actual vapor pressure of the air."""
    return max(0.0, svp_kpa(t_c - leaf_offset) - svp_kpa(t_c) * rh / 100)


def vpd_band(vpd):
    if vpd < VPD_LOW:
        return "low"
    if vpd <= VPD_HIGH:
        return "ok"
    return "high" if vpd <= VPD_STRESS else "stress"


VPD_TEXT = {"low": "too humid", "ok": "optimal", "high": "high", "stress": "water stress"}


def snapshot():
    """Turns the shared state into what the UI shows."""
    now = time.monotonic()
    with lock:
        soil_c, status_c = dict(soil), dict(status)
        temp_c, humid_c = dict(temp), dict(humid)
        sprinkler_c = {z: dict(v) for z, v in sprinkler.items()}
        while arrivals and now - arrivals[0] > 5:
            arrivals.popleft()
        rate = len(arrivals) / 5

    zones, sensors = {}, {}
    for zone in ZONES:
        rows = {}
        for sid in SENSOR_IDS[zone]:
            reading = soil_c.get(sid)
            age = now - reading[1] if reading else None
            # offline = Last Will received, no reading yet, or nothing for STALE_AFTER_S
            if status_c.get(sid) == "offline" or reading is None or age > STALE_AFTER_S:
                state = "offline"
            else:
                state = "online"
            rows[sid] = {"state": state, "value": reading[0] if reading else None, "age": age}

        valid = [r["value"] for r in rows.values() if r["state"] == "online" and 0 <= r["value"] <= 100]
        median = statistics.median(valid) if valid else None
        for r in rows.values():
            r["suspect"] = r["state"] == "online" and (
                not 0 <= r["value"] <= 100 or (median is not None and abs(r["value"] - median) > SUSPECT_DELTA))
        sensors.update(rows)

        sp = sprinkler_c[zone]
        remaining = max(0, sp["until"] - now) if sp["state"] == "on" and sp["until"] else None
        vpd = None
        t_r, h_r = temp_c.get(zone), humid_c.get(zone)
        if (t_r and h_r and now - min(t_r[1], h_r[1]) <= AIR_STALE_AFTER_S
                and -40 <= t_r[0] <= 60 and 0 <= h_r[0] <= 100):
            v = vpd_kpa(t_r[0], h_r[0], LEAF_TEMP_OFFSET)
            vpd = {"temp": t_r[0], "rh": h_r[0], "kpa": v, "band": vpd_band(v)}
        zones[zone] = {"median": median, "n": len(valid), "sprinkler": sp["state"] or "unknown",
                       "remaining": remaining, "vpd": vpd}
    return zones, sensors, rate


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
    Input("tick", "n_intervals"),
)
def refresh(_):
    zones, sensors, rate = snapshot()
    zone_ids = [o["id"]["zone"] for o in ctx.outputs_list[0]]      # order Dash expects
    sensor_ids = [o["id"]["sensor"] for o in ctx.outputs_list[5]]

    sp_text = {"on": "ON", "off": "OFF", "offline": "OFFLINE", "unknown": "–"}
    labels = []
    for z in zone_ids:
        info = zones[z]
        text = f"sprinkler {sp_text.get(info['sprinkler'], info['sprinkler'])}"
        if info["remaining"] is not None:
            text += f" · {info['remaining']:.0f}s left"
        labels.append(text)

    def pct(z):
        return zones[z]["median"]

    online = sum(s["state"] == "online" for s in sensors.values())
    suspects = sum(s["suspect"] for s in sensors.values())
    on = sum(i["sprinkler"] == "on" for i in zones.values())
    offline = sum(i["sprinkler"] == "offline" for i in zones.values())
    is_up = connected.is_set()

    def vpd_text(z):
        v = zones[z]["vpd"]
        if v is None:
            return "VPD – (no air reading)"
        return f"VPD {v['kpa']:.2f} kPa · {VPD_TEXT[v['band']]} · {v['temp']:.1f}°C · {v['rh']:.0f}% RH"

    return (
        [f"zone sp-{zones[z]['sprinkler'] if zones[z]['sprinkler'] in sp_text else 'unknown'}" for z in zone_ids],
        ["–" if pct(z) is None else f"{pct(z):.0f}%" for z in zone_ids],
        ["no valid reading" if pct(z) is None else f"median of {zones[z]['n']} sensors" for z in zone_ids],
        [{"height": f"{0 if pct(z) is None else min(100, max(0, pct(z))):.1f}%"} for z in zone_ids],
        labels,
        [f"srow {sensors[s]['state']}" + (" suspect" if sensors[s]["suspect"] else "") for s in sensor_ids],
        [{"width": f"{0 if sensors[s]['value'] is None else min(100, max(0, sensors[s]['value'])):.1f}%"}
         for s in sensor_ids],
        ["–" if sensors[s]["value"] is None else f"{sensors[s]['value']:.1f}%" for s in sensor_ids],
        [age_text(sensors[s]["age"]) for s in sensor_ids],
        [f"{online} / {len(sensors)}"] + ([html.Small(f" · {suspects} suspect")] if suspects else []),
        [f"{on} / {len(zones)}"] + ([html.Small(f" · {offline} offline")] if offline else []),
        f"{rate:.1f}",
        f"{'connected' if is_up else 'DISCONNECTED'} · {MQTT_HOST}:{MQTT_PORT}",
        "pill on" if is_up else "pill off",
        [vpd_text(z) for z in zone_ids],
        ["vpd " + (zones[z]["vpd"]["band"] if zones[z]["vpd"] else "none") for z in zone_ids],
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
    threading.Thread(target=poll_loop, daemon=True).start()
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()
    log.info("serving on port %d", PORT)
    serve(app.server, host="0.0.0.0", port=PORT, threads=16)   # several participants may open the page