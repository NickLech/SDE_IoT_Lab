"""Temperature service: simulated field temperatures exposed over HTTP (pull).

GET /zones/<zone>/temperature
    -> {"zone": "zone1", "sensor_id": "temp-zone1", "value": 14.0,
        "unit": "C", "timestamp": "..."}

The temperature follows a daily sine wave cicle based on how long the service has been running.
Example for zone2: 14° + (5° * sin(2*pi * elapsed_seconds/600)) + 0.5° * 1
0 min:         14°   6 AM
2 min 30 sec:  19°   12 AM
5 min:         14°   6 PM 
7 min 30 sec:  7.5°  12 PM  
10 min:        14°   6 AM next day
The offset increases by 0.5° for every zone. 
"""
import json
import math
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", 5001))
ZONES = [z.strip() for z in os.environ.get("ZONES", "zone1,zone2,zone3").split(",") if z.strip()]
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


def temperature(zone):
    elapsed = time.monotonic() - START
    daily_cycle = math.sin(2 * math.pi * elapsed / DAY_PERIOD_S)
    zone_offset = ZONE_OFFSET * ZONES.index(zone)
    value = INITIAL_TEMPERATURE + zone_offset + TEMPERATURE_AMPLITUDE * daily_cycle
    return round(min(MAX_TEMPERATURE, max(MIN_TEMPERATURE, value)), 2)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = self.path.strip("/").split("/")
        if parts == ["health"]:
            self.reply(200, {"status": "ok"})
        elif len(parts) == 3 and parts[0] == "zones" and parts[2] == "temperature" and parts[1] in ZONES:
            zone = parts[1]
            self.reply(200, {
                "zone": zone,
                "sensor_id": f"temp-{zone}",
                "value": temperature(zone),
                "unit": "C",
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
        pass


def main():
    print(f"temperature started: zones {ZONES}, port {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
