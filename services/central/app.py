"""Central node: data fusion (soil + air temperature/humidity -> VPD) and irrigation decisions.

Inputs
  MQTT (push)  field/<zone>/soil/<sensor_id>          {"value": %}            soil moisture
               field/<zone>/soil/<sensor_id>/status   "online" | "offline"    Last Will
               field/<zone>/sprinkler/state           {"state": "on"|"off"}   retained
               field/<zone>/sprinkler/cmd             {"action": "on"|"off"}  own and external commands
               field/<zone>/rain/state                {"state": "on"|"off"}
  HTTP (pull)  GET $TEMPERATURE_URL/zones/<zone>/temperature     every POLL_INTERVAL_S
               GET $HUMIDITY_URL/zones/<zone>/humidity

Outputs
  MQTT         field/<zone>/sprinkler/cmd   {"action": "on", "duration_s": N} | {"action": "off"}   (QoS 1, not retained)
  HTTP         GET /zones, /zones/<zone>, /health   (port PORT) -> read by the dashboard

Air fusion: median of the last AIR_WINDOW temperature/humidity samples (spike rejection), then VPD.
Fusion rule (all numbers are starting points, tune them on the real soil/crop):
  VPD       = SVP(leaf) - SVP(air) * RH/100                (kPa, Tetens/Magnus)
  threshold = SOIL_DRY_BASE + VPD_GAIN * (VPD - VPD_REF)   -> the drier the air, the earlier we irrigate
  duration  = IRRIGATION_S * (1 + max(0, VPD - VPD_REF))   -> ... and the longer
  Irrigate when soil median < threshold. Without VPD (temperature/humidity missing) it falls back to
  SOIL_DRY_BASE; without a valid soil reading it never irrigates (fail-safe).
"""
import collections
import json
import logging
import math
import os
import signal
import statistics
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paho.mqtt.client as mqtt

log = logging.getLogger("central")

# ----------------------------------------------------------------------------- config
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
TEMPERATURE_URL = os.environ.get("TEMPERATURE_URL", "http://localhost:5001").rstrip("/")
HUMIDITY_URL = os.environ.get("HUMIDITY_URL", "http://localhost:5002").rstrip("/")
ZONES = [z.strip() for z in os.environ.get("ZONES", "zone1,zone2,zone3").split(",") if z.strip()]
SENSORS_PER_ZONE = int(os.environ.get("SENSORS_PER_ZONE", 3))
PORT = int(os.environ.get("PORT", 5000))

POLL_INTERVAL_S = float(os.environ.get("POLL_INTERVAL_S", 5))
HTTP_TIMEOUT_S = float(os.environ.get("HTTP_TIMEOUT_S", 1.5))
TICK_S = float(os.environ.get("TICK_S", 1))                                   # fusion + decision cycle
STALE_AFTER_S = float(os.environ.get("STALE_AFTER_S", 8))                     # soil sensor silent -> offline
AIR_STALE_AFTER_S = float(os.environ.get("AIR_STALE_AFTER_S", 3 * POLL_INTERVAL_S))   # air value too old -> unusable
SUSPECT_DELTA = float(os.environ.get("SUSPECT_DELTA", 15))                    # distance from zone median (%)
AIR_WINDOW = int(os.environ.get("AIR_WINDOW", 3))                             # last N air samples -> median (spike filter)

VPD_LOW = float(os.environ.get("VPD_LOW", 0.4))
VPD_HIGH = float(os.environ.get("VPD_HIGH", 1.2))
VPD_STRESS = float(os.environ.get("VPD_STRESS", 1.6))
LEAF_TEMP_OFFSET = float(os.environ.get("LEAF_TEMP_OFFSET", 0))               # leaf is this many degC colder than air

SOIL_DRY_BASE = float(os.environ.get("SOIL_DRY_BASE", 35))                    # % : irrigate below this (VPD = VPD_REF)
SOIL_STOP = float(os.environ.get("SOIL_STOP", 70))                            # % : stop irrigating above this
VPD_REF = float(os.environ.get("VPD_REF", 0.8))
VPD_GAIN = float(os.environ.get("VPD_GAIN", 15))                              # % of threshold per kPa of VPD
IRRIGATION_S = float(os.environ.get("IRRIGATION_S", 20))
SPRINKLER_DEFAULT_S = float(os.environ.get("SPRINKLER_DEFAULT_S", 30))        # same as the sprinkler service
SPRINKLER_MAX_S = float(os.environ.get("SPRINKLER_MAX_S", 120))               # cap on our own commands
COOLDOWN_S = float(os.environ.get("COOLDOWN_S", 60))                          # min time between two commands per zone

SENSOR_IDS = {z: [f"soil-{z}-{i}" for i in range(1, SENSORS_PER_ZONE + 1)] for z in ZONES}

# ----------------------------------------------------------------------- shared state
lock = threading.Lock()
soil = {}                                   # (zone, sensor_id) -> (value, received_at)
status = {}                                 # (zone, sensor_id) -> "online" | "offline"
temp = {}                                   # zone -> deque[(degC, received_at)]   HTTP pull
humid = {}                                  # zone -> deque[(%RH, received_at)]    HTTP pull
sprinkler = {z: {"state": None, "until": None} for z in ZONES}
rain = {z: None for z in ZONES}
cmd_until = {}                              # zone -> expected end of the last "on" command
connected = threading.Event()
latest = None                               # last computed view, served over HTTP

last_cmd = {}                               # zone -> monotonic time of our last command (control thread only)
last_command = {}                           # zone -> {"action", "duration_s", "at"}   (control thread only)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ------------------------------------------------------------------------------- MQTT
def on_connect(client, userdata, flags, reason_code, properties):
    log.info("connected to broker (%s)", reason_code)
    client.subscribe([("field/+/soil/+", 1), ("field/+/soil/+/status", 1), ("field/+/sprinkler/state", 1),
                      ("field/+/sprinkler/cmd", 1), ("field/+/rain/state", 1)])
    connected.set()


def on_disconnect(client, userdata, flags, reason_code, properties):
    log.warning("disconnected from broker (%s)", reason_code)
    connected.clear()


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
                soil[(zone, parts[3])] = (float(data["value"]), now)
        elif kind == "soil" and len(parts) == 5 and parts[4] == "status":
            status[(zone, parts[3])] = text
        elif kind == "rain" and len(parts) == 4 and parts[3] == "state" and isinstance(data, dict):
            rain[zone] = data.get("state")
        elif kind == "sprinkler" and len(parts) == 4 and isinstance(data, dict):
            if parts[3] == "cmd":
                if data.get("action") == "on":
                    duration = data.get("duration_s", SPRINKLER_DEFAULT_S)
                    if is_number(duration):
                        cmd_until[zone] = now + float(duration)
                elif data.get("action") == "off":
                    cmd_until.pop(zone, None)
            elif parts[3] == "state":
                state = data.get("state")
                sprinkler[zone]["state"] = state
                # keep the known end time across repeated "on" states; clear it otherwise
                sprinkler[zone]["until"] = cmd_until.pop(zone, sprinkler[zone]["until"]) if state == "on" else None


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="central")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.reconnect_delay_set(1, 10)


def send_command(zone, action, duration_s=None):
    payload = {"action": action}
    if action == "on":
        payload["duration_s"] = round(duration_s)
    client.publish(f"field/{zone}/sprinkler/cmd", json.dumps(payload), qos=1)
    log.info("%s: command %s", zone, payload)


# ----------------------------------------------------------------------- HTTP pull (air)
def poll_loop():
    """Polls the temperature and humidity services and stores the last value per zone."""
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
                    store.setdefault(zone, collections.deque(maxlen=AIR_WINDOW)).append((value, time.monotonic()))
        time.sleep(POLL_INTERVAL_S)


# ------------------------------------------------------------------------ data fusion
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


def fresh(store, zone, lo, hi, now):
    """Air value used for the fusion: median of the recent, plausible samples.
    The median rejects an isolated spike (the temperature service injects them on purpose)."""
    samples = [v for v, t in store.get(zone, ()) if now - t <= AIR_STALE_AFTER_S and lo <= v <= hi]
    return round(statistics.median(samples), 2) if samples else None


def build_view(now, soil_c, status_c, temp_c, humid_c, sprinkler_c, rain_c):
    """Turns the raw state into one dict per zone (soil + air + VPD + sprinkler + rain)."""
    zones = {}
    for zone in ZONES:
        sensors = {}
        for sid in SENSOR_IDS[zone]:
            reading = soil_c.get((zone, sid))
            age = now - reading[1] if reading else None
            offline = status_c.get((zone, sid)) == "offline" or reading is None or age > STALE_AFTER_S
            sensors[sid] = {"state": "offline" if offline else "online",
                            "value": reading[0] if reading else None, "age_s": age}

        valid = [s["value"] for s in sensors.values() if s["state"] == "online" and 0 <= s["value"] <= 100]
        median = statistics.median(valid) if valid else None
        for s in sensors.values():
            s["suspect"] = s["state"] == "online" and (
                not 0 <= s["value"] <= 100 or (median is not None and abs(s["value"] - median) > SUSPECT_DELTA))
            s["age_s"] = None if s["age_s"] is None else round(s["age_s"], 1)

        t, rh = fresh(temp_c, zone, -40, 60, now), fresh(humid_c, zone, 0, 100, now)
        vpd = None
        if t is not None and rh is not None:
            kpa = vpd_kpa(t, rh, LEAF_TEMP_OFFSET)
            vpd = {"kpa": round(kpa, 3), "band": vpd_band(kpa), "leaf_offset_c": LEAF_TEMP_OFFSET}

        sp = sprinkler_c[zone]
        remaining = max(0.0, sp["until"] - now) if sp["state"] == "on" and sp["until"] else None
        zones[zone] = {
            "soil": {"median": None if median is None else round(median, 1),
                     "valid": len(valid), "expected": len(SENSOR_IDS[zone])},
            "air": {"temperature": t, "humidity": rh},
            "vpd": vpd,
            "sprinkler": {"state": sp["state"] or "unknown",
                          "remaining_s": None if remaining is None else round(remaining, 1)},
            "rain": rain_c.get(zone) or "unknown",
            "sensors": sensors,
        }
    return zones


def soil_threshold(kpa):
    if kpa is None:
        return SOIL_DRY_BASE
    return min(95.0, max(5.0, SOIL_DRY_BASE + VPD_GAIN * (kpa - VPD_REF)))


def decide(zone, view, now, mqtt_up):
    """Returns (action, reason, soil_threshold, duration_s); action is "on", "off" or None."""
    soil_v = view["soil"]["median"]
    kpa = view["vpd"]["kpa"] if view["vpd"] else None
    thr = soil_threshold(kpa)
    sp_state = view["sprinkler"]["state"]

    if not mqtt_up:
        return None, "MQTT disconnected: no commands", thr, None
    if soil_v is None:
        return None, "no valid soil reading: not irrigating", thr, None
    if sp_state == "on":
        if view["rain"] == "on":
            return "off", "raining: stop", thr, None
        if soil_v >= SOIL_STOP:
            return "off", f"soil {soil_v:.0f}% >= stop level {SOIL_STOP:.0f}%", thr, None
        return None, "sprinkler already on", thr, None
    if sp_state != "off":
        return None, f"sprinkler {sp_state}: no commands", thr, None
    if view["rain"] == "on":
        return None, "raining: not irrigating", thr, None
    if soil_v >= thr:
        return None, f"soil {soil_v:.0f}% >= threshold {thr:.0f}%", thr, None
    wait = COOLDOWN_S - (now - last_cmd.get(zone, -math.inf))
    if wait > 0:
        return None, f"soil {soil_v:.0f}% < threshold {thr:.0f}%, cooldown ({wait:.0f}s left)", thr, None
    duration = IRRIGATION_S if kpa is None else IRRIGATION_S * (1 + max(0.0, kpa - VPD_REF))
    duration = min(SPRINKLER_MAX_S, duration)
    basis = "soil only, no VPD" if kpa is None else f"VPD {kpa:.2f} kPa"
    return "on", f"soil {soil_v:.0f}% < threshold {thr:.0f}% ({basis})", thr, duration


def control_step():
    global latest
    now = time.monotonic()
    with lock:
        soil_c, status_c = dict(soil), dict(status)
        temp_c, humid_c = {z: list(d) for z, d in temp.items()}, {z: list(d) for z, d in humid.items()}
        sprinkler_c = {z: dict(v) for z, v in sprinkler.items()}
        rain_c = dict(rain)
    zones = build_view(now, soil_c, status_c, temp_c, humid_c, sprinkler_c, rain_c)
    mqtt_up = connected.is_set()

    for zone, view in zones.items():
        action, reason, thr, duration = decide(zone, view, now, mqtt_up)
        if action:
            send_command(zone, action, duration)
            last_cmd[zone] = now
            last_command[zone] = {"action": action, "duration_s": None if duration is None else round(duration),
                                  "at": now_iso()}
        view["decision"] = {"action": action, "reason": reason, "soil_threshold": round(thr, 1)}
        view["last_command"] = last_command.get(zone)

    links = {"mqtt": mqtt_up,
             "temperature": any(v["air"]["temperature"] is not None for v in zones.values()),
             "humidity": any(v["air"]["humidity"] is not None for v in zones.values())}
    with lock:
        latest = {"timestamp": now_iso(), "links": links, "zones": zones}


def control_loop():
    while True:
        try:
            control_step()
        except Exception:
            log.exception("control step failed")
        time.sleep(TICK_S)


# --------------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = self.path.split("?")[0].strip("/").split("/")
        with lock:
            view = latest
        if parts == ["health"]:
            self.reply(200, {"status": "ok", "mqtt": connected.is_set()})
        elif view is None:
            self.reply(503, {"error": "not ready"})
        elif parts == ["zones"]:
            self.reply(200, view)
        elif len(parts) == 2 and parts[0] == "zones" and parts[1] in ZONES:
            self.reply(200, {"zone": parts[1], "timestamp": view["timestamp"], "links": view["links"],
                             **view["zones"][parts[1]]})
        else:
            self.reply(404, {"error": "not found"})

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    threading.Thread(target=poll_loop, daemon=True).start()
    threading.Thread(target=control_loop, daemon=True).start()
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    log.info("central started: zones %s, port %d", ZONES, PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()