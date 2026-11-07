"""Humidity service (simple version): air humidity sensor exposed over HTTP (pull).

GET /zones/<zone>/humidity
    -> {"zone": "zone1", "value": 62.5, "unit": "%", "timestamp": "..."}

Humidity follows a simple daily cycle (cosine) whose length is DAY_PERIOD_S.
Keep DAY_PERIOD_S equal to the temperature service.
No external dependencies (standard library only).
"""
import json
import math
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", 5002))
ZONES = [z.strip() for z in os.environ.get("ZONES", "zone1,zone2,zone3").split(",") if z.strip()]
DAY_PERIOD_S = float(os.environ.get("DAY_PERIOD_S", 600))

BASE = 60.0       # % mean humidity
AMPLITUDE = 15.0  # % swing around the mean
ZONE_OFFSET = 2.0 # % added per zone index, so zones differ a little

START = time.monotonic()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def humidity(zone):
    t = time.monotonic() - START
    cycle = math.cos(2 * math.pi * t / DAY_PERIOD_S)
    value = BASE + ZONE_OFFSET * ZONES.index(zone) + AMPLITUDE * cycle
    return round(value, 2)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = self.path.strip("/").split("/")  # ["zones", "<zone>", "humidity"]
        if len(parts) == 3 and parts[0] == "zones" and parts[2] == "humidity" and parts[1] in ZONES:
            body = {
                "zone": parts[1],
                "value": humidity(parts[1]),
                "unit": "%",
                "timestamp": now_iso(),
            }
            self.reply(200, body)
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
    print(f"humidity started: zones {ZONES}, port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()