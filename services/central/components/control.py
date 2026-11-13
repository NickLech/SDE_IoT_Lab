"""Control loop: every TICK_S snapshot the state -> fusion -> decision -> command -> publish the view for the API."""
import logging
import math
import time

from components import comms, state
from components.config import TICK_S
from components.decision import decide
from components.fusion import build_view
from components.state import lock, now_iso

log = logging.getLogger("central.control")

last_cmd = {}                               # zone -> monotonic time of our last command (control thread only)
last_command = {}                           # zone -> {"action", "duration_s", "at"}   (control thread only)


def control_step():
    now = time.monotonic()
    with lock:                              # copy under the lock, compute outside it
        soil_c, status_c = dict(state.soil), dict(state.status)
        temp_c = {z: list(d) for z, d in state.temp.items()}       # deques -> lists (copy under the lock)
        humid_c = {z: list(d) for z, d in state.humid.items()}
        sprinkler_c = {z: dict(v) for z, v in state.sprinkler.items()}
        sprinkler_status_c = dict(state.sprinkler_status)
        rain_c, manual_c = dict(state.rain), dict(state.manual_until)
    zones = build_view(now, soil_c, status_c, temp_c, humid_c, sprinkler_c, sprinkler_status_c, rain_c, manual_c)
    mqtt_up = state.connected.is_set()
    for zone, until in manual_c.items():       # the cooldown also counts from the end of a manual command
        last_cmd[zone] = max(last_cmd.get(zone, -math.inf), until)

    for zone, view in zones.items():
        action, reason, thr, duration = decide(zone, view, now, mqtt_up, last_cmd)
        if action:
            comms.send_command(zone, action, duration)
            last_cmd[zone] = now
            last_command[zone] = {"action": action, "duration_s": None if duration is None else round(duration),
                                  "at": now_iso()}
        view["decision"] = {"action": action, "reason": reason, "soil_threshold": round(thr, 1)}
        view["last_command"] = last_command.get(zone)

    links = {"mqtt": mqtt_up,
             "temperature": any(v["air"]["temperature"] is not None for v in zones.values()),
             "humidity": any(v["air"]["humidity"] is not None for v in zones.values())}
    with lock:
        state.latest = {"timestamp": now_iso(), "links": links, "zones": zones}


def control_loop():
    while True:
        try:
            control_step()
        except Exception:
            log.exception("control step failed")
        time.sleep(TICK_S)
