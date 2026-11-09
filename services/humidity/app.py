"""Humidity service (simple): air humidity exposed over HTTP (pull).

GET /zones/<zone>/humidity
    -> {"zone": "zone1", "value": 62.5, "unit": "%", "timestamp": "..."}

Same rule as the soil service (-DRY_STEP every tick, +WET_STEP for each active
source: sprinkler, rain), but the value stays between MIN_HUMIDITY and MAX_HUMIDITY.
Sprinkler/rain state comes from MQTT: field/+/sprinkler/state, field/+/rain/state.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paho.mqtt.client as mqtt

PORT = int(os.environ.get("PORT", 5002))
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
ZONES = ["zone1", "zone2", "zone3"]
SOURCES = ["sprinkler", "rain"]

TICK_S = 5
INITIAL_HUMIDITY = 65.0  # %
DRY_STEP = 1.0
WET_STEP = 2.0
MIN_HUMIDITY = 50.0
MAX_HUMIDITY = 80.0

humidity = {z: INITIAL_HUMIDITY for z in ZONES}
wet = {z: {s: False for s in SOURCES} for z in ZONES}
lock = threading.Lock()  # shared by MQTT thread, tick thread and HTTP threads


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe([(f"field/+/{s}/state", 1) for s in SOURCES])


def on_message(client, userdata, msg):
    try:
        _, zone, source, _ = msg.topic.split("/")
        state = json.loads(msg.payload).get("state")
    except (ValueError, AttributeError):
        return
    with lock:
        if zone in wet and source in wet[zone]:
            wet[zone][source] = (state == "on")


def tick_loop():
    while True:
        time.sleep(TICK_S)
        with lock:
            for zone in ZONES:
                delta = -DRY_STEP + WET_STEP * sum(wet[zone].values())
                value = humidity[zone] + delta
                humidity[zone] = min(MAX_HUMIDITY, max(MIN_HUMIDITY, value))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = self.path.strip("/").split("/")  # ["zones", "<zone>", "humidity"]
        if len(parts) == 3 and parts[0] == "zones" and parts[2] == "humidity" and parts[1] in ZONES:
            with lock:
                value = humidity[parts[1]]
            self.reply(200, {
                "zone": parts[1],
                "value": round(value, 2),
                "unit": "%",
                "timestamp": now_iso(),
            })
        else:
            self.reply(404, {"error": "not found"})

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # keep the console quiet


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="humidity-service")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(MQTT_HOST, MQTT_PORT)
    client.loop_start()

    threading.Thread(target=tick_loop, daemon=True).start()

    print(f"humidity started: zones {ZONES}, port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()