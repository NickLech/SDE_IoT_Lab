"""Temperature sensor of ONE zone, exposed over HTTP (pull).

Env: ZONE (e.g. zone1), ZONE_INDEX (0-based, sets the +0.5 degC per zone offset), PORT (default 5001)

GET /zones/<zone>/temperature
    -> {"zone": "zone1", "sensor_id": "temp-zone1", "value": 14.0, "unit": "C", "timestamp": "..."}

Daily sine cycle, one "day" = DAY_PERIOD_S seconds since the process started:
    14 + 0.5 * ZONE_INDEX + 5 * sin(2*pi*elapsed/DAY_PERIOD_S)   (clamped to 5..20)
"""
import json
import math
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", 5001))
ZONE = os.environ["ZONE"]
ZONE_INDEX = int(os.environ.get("ZONE_INDEX", 0))
DAY_PERIOD_S = float(os.environ.get("DAY_PERIOD_S", 600))

MIN_TEMPERATURE = 5.0
MAX_TEMPERATURE = 20.0
INITIAL_TEMPERATURE = 14.0
TEMPERATURE_AMPLITUDE = 5.0
ZONE_OFFSET = 0.5

if DAY_PERIOD_S <= 0:
    raise ValueError("DAY_PERIOD_S must be greater than zero")

START = time.monotonic()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def temperature():
    elapsed = time.monotonic() - START
    daily_cycle = math.sin(2 * math.pi * elapsed / DAY_PERIOD_S)
    value = INITIAL_TEMPERATURE + ZONE_OFFSET * ZONE_INDEX + TEMPERATURE_AMPLITUDE * daily_cycle
    return round(min(MAX_TEMPERATURE, max(MIN_TEMPERATURE, value)), 2)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = self.path.strip("/").split("/")
        if parts == ["health"]:
            self.reply(200, {"status": "ok"})
        elif parts == ["zones", ZONE, "temperature"]:
            self.reply(200, {"zone": ZONE, "sensor_id": f"temp-{ZONE}", "value": temperature(),
                             "unit": "C", "timestamp": now_iso()})
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
    print(f"temperature started: {ZONE}, port {PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
