"""Smoke test for the MQTT part (broker + soil + sprinkler must already be running).

    pip install paho-mqtt
    python tests/smoke_mqtt.py            # broker on localhost:1883
    BROKER_HOST=... BROKER_PORT=... python tests/smoke_mqtt.py

Checks the contracts in docs/architecture.md: telemetry, status, retained state,
on/off command, soil reaction and injected fault. Exits with code 1 on any failure.
The soil-reaction check needs a fast simulation: start the stack with TIME_SCALE=8.
"""
import json
import os
import statistics
import sys
import threading
import time
from collections import defaultdict

import paho.mqtt.client as mqtt

HOST = os.environ.get("BROKER_HOST", "localhost")
PORT = int(os.environ.get("BROKER_PORT", 1883))
ZONES = ["zone1", "zone2", "zone3"]

soil = defaultdict(list)          # sensor_id -> [value, ...]
soil_msgs = {}                    # sensor_id -> last full payload
sprinkler_state = {}              # zone -> state
status = {}                       # sensor_id -> online/offline
retained_seen = {}                # topic -> retain flag of the received message
lock = threading.Lock()


def on_message(client, userdata, msg):
    with lock:
        parts = msg.topic.split("/")
        if len(parts) == 4 and parts[2] == "soil":
            d = json.loads(msg.payload)
            soil[d["sensor_id"]].append(d["value"])
            soil_msgs[d["sensor_id"]] = d
        elif len(parts) == 5 and parts[4] == "status":
            status[parts[3]] = msg.payload.decode()
        elif len(parts) == 4 and parts[2] == "sprinkler" and parts[3] == "state":
            sprinkler_state[parts[1]] = json.loads(msg.payload).get("state")
            retained_seen[msg.topic] = msg.retain


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smoke-test")
client.on_message = on_message
client.connect(HOST, PORT)
client.subscribe([("field/+/soil/+", 0), ("field/+/soil/+/status", 1), ("field/+/sprinkler/state", 1)])
client.loop_start()

failures = []


def check(name, ok, detail=""):
    print(f"[{'OK' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        failures.append(name)


def wait_for(cond, timeout):
    end = time.time() + timeout
    while time.time() < end:
        with lock:
            if cond():
                return True
        time.sleep(0.2)
    return False


def zone_mean(zone):
    with lock:
        vals = [v[-1] for s, v in soil.items() if s.startswith(f"soil-{zone}-") and v]
    return statistics.mean(vals) if vals else float("nan")


# 1. telemetry from all 9 sensors
ok = wait_for(lambda: len(soil_msgs) >= 9, 20)
check("9 soil sensors publish", ok, f"({len(soil_msgs)}/9)")
if ok:
    sample = next(iter(soil_msgs.values()))
    check("payload matches contract",
          set(sample) == {"zone", "sensor_id", "value", "unit", "timestamp"} and sample["unit"] == "%", str(sample))
    check("values in range", all(0 <= m["value"] <= 100 for m in soil_msgs.values()))

# 2. retained status (seen by a subscriber that joins later)
check("sensor status online (retained)",
      wait_for(lambda: len(status) >= 9 and all(v == "online" for v in status.values()), 10), str(dict(status)))

# 3. retained sprinkler state
check("sprinkler state retained 'off' for all zones",
      wait_for(lambda: all(sprinkler_state.get(z) == "off" for z in ZONES), 10)
      and all(retained_seen.get(f"field/{z}/sprinkler/state") for z in ZONES))

# 4. on command -> state on, soil rises, auto-off at timeout
before = zone_mean("zone1")
client.publish("field/zone1/sprinkler/cmd", json.dumps({"action": "on", "duration_s": 6}), qos=1)
check("zone1 sprinkler turns 'on'", wait_for(lambda: sprinkler_state.get("zone1") == "on", 5))
time.sleep(5)
after = zone_mean("zone1")
check("zone1 moisture rises while sprinkler is on", after > before + 3,
      f"({before:.1f} -> {after:.1f}; needs TIME_SCALE=8 on soil)")
check("auto-off after duration_s", wait_for(lambda: sprinkler_state.get("zone1") == "off", 8))
check("other zones untouched", sprinkler_state.get("zone2") == "off" and sprinkler_state.get("zone3") == "off")

# 5. invalid commands are ignored
client.publish("field/zone2/sprinkler/cmd", "not-json", qos=1)
client.publish("field/zone2/sprinkler/cmd", json.dumps({"action": "on", "duration_s": -5}), qos=1)
time.sleep(1.5)
check("invalid commands ignored", sprinkler_state.get("zone2") == "off")

# 6. injected fault: a 'crazy' sensor diverges from its siblings (medians resist random spikes)
client.publish("debug/soil-zone3-1/fault", json.dumps({"mode": "crazy"}), qos=1)
time.sleep(12)
with lock:
    crazy = soil["soil-zone3-1"][-6:]
    h2 = statistics.median(soil["soil-zone3-2"][-7:])
    h3 = statistics.median(soil["soil-zone3-3"][-7:])
spread_crazy = max(crazy) - min(crazy)
check("'crazy' sensor gives inconsistent readings", spread_crazy > 15, f"(spread {spread_crazy:.0f})")
check("healthy sensors stay consistent", abs(h2 - h3) < 6, f"(medians {h2:.1f} / {h3:.1f})")
client.publish("debug/soil-zone3-1/fault", "none", qos=1)
time.sleep(10)
with lock:
    rec = statistics.median(soil["soil-zone3-1"][-5:])
    h2 = statistics.median(soil["soil-zone3-2"][-5:])
check("sensor recovers", abs(rec - h2) < 6, f"(median {rec:.1f} vs healthy {h2:.1f})")

client.loop_stop()
print("\nRESULT:", "ALL OK" if not failures else f"{len(failures)} checks failed: {failures}")
sys.exit(1 if failures else 0)
