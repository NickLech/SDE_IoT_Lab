"""Shared in-memory state. Written by comms.py (MQTT/HTTP threads), read by control.py and api.py.
Always take `lock` when touching these dicts from more than one thread."""
import threading
from datetime import datetime, timezone

from components.config import ZONES

lock = threading.Lock()
soil = {}                                   # (zone, sensor_id) -> (value, received_at)
status = {}                                 # (zone, sensor_id) -> "online" | "offline"
temp = {}                                   # zone -> deque[(degC, received_at)]   HTTP pull
humid = {}                                  # zone -> deque[(%RH, received_at)]    HTTP pull
sprinkler = {z: {"state": None, "until": None} for z in ZONES}
sprinkler_status = {z: None for z in ZONES}   # "online"|"offline": liveness, independent of on/off
rain = {z: None for z in ZONES}
cmd_until = {}                              # zone -> expected end of the last "on" command
manual_until = {}                           # zone -> end of the last MANUAL command (central does not interfere)
connected = threading.Event()               # MQTT link up
latest = None                               # last computed view, served over HTTP (set by control.py)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)
