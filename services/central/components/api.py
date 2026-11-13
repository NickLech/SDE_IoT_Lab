"""HTTP API read by the dashboard (JSON format unchanged):
  GET /health          -> {"status": "ok", "mqtt": bool}
  GET /zones           -> {"timestamp", "links", "zones": {<zone>: {...}}}
  GET /zones/<zone>    -> one zone, with "zone", "timestamp" and "links" added
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from components import state
from components.config import PORT, ZONES


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parts = self.path.split("?")[0].strip("/").split("/")
        with state.lock:
            view = state.latest
        if parts == ["health"]:
            self.reply(200, {"status": "ok", "mqtt": state.connected.is_set()})
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


def make_server():
    return ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
