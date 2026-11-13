"""Air-humidity sensor of ONE zone, exposed over HTTP (pull).

Env: ZONE (e.g. zone1), PORT (default 5002)

GET /zones/<zone>/humidity -> {"zone": "zone1", "value": 62.5, "unit": "%", "timestamp": "..."}

-DRY_STEP every tick, +WET_STEP for each active source (sprinkler of this zone, rain),
clamped to MIN_HUMIDITY..MAX_HUMIDITY. Sources come from MQTT:
field/<zone>/sprinkler/state and field/<zone>/rain/state.
"""
import json
import os
import signal
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import paho.mqtt.client as mqtt

PORT = int(os.environ.get("PORT", 5002))
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
ZONE = os.environ["ZONE"]
SOURCES = ["sprinkler", "rain"]

TICK_S = 5
INITIAL_HUMIDITY = 65.0
DRY_STEP = 1.0
WET_STEP = 2.0
MIN_HUMIDITY = 50.0
MAX_HUMIDITY = 80.0

humidity = INITIAL_HUMIDITY
wet = {s: False for s in SOURCES}
lock = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe([(f"field/{ZONE}/{s}/state", 1) for s in SOURCES])


def on_message(client, userdata, msg):
    try:
        source = msg.topic.split("/")[2]
        state = json.loads(msg.payload).get("state")
    except (ValueError, AttributeError, IndexError):
        return
    with lock:
        if source in wet:
            wet[source] = (state == "on")


def tick_loop():
    global humidity
    while True:
        time.sleep(TICK_S)
        with lock:
            delta = -DRY_STEP + WET_STEP * sum(wet.values())
            humidity = min(MAX_HUMIDITY, max(MIN_HUMIDITY, humidity + delta))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = self.path.strip("/").split("/")
        if parts == ["health"]:
            self.reply(200, {"status": "ok"})
        elif parts == ["zones", ZONE, "humidity"]:
            with lock:
                value = humidity
            self.reply(200, {"zone": ZONE, "value": round(value, 2), "unit": "%", "timestamp": now_iso()})
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
        pass


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"humidity-{ZONE}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(MQTT_HOST, MQTT_PORT)
    client.loop_start()
    threading.Thread(target=tick_loop, daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    print(f"humidity started: {ZONE}, port {PORT}", flush=True)
    server.serve_forever()
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
