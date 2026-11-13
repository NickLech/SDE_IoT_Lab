"""Single soil-moisture sensor (one process, one MQTT connection, one Last Will).

Env: ZONE (e.g. zone1), SENSOR_INDEX (1..N)  ->  sensor_id = soil-<zone>-<index>

- Publishes field/<zone>/soil/<sensor_id>         (QoS 0)  {"zone","sensor_id","value","unit","timestamp"}
- Liveness   field/<zone>/soil/<sensor_id>/status (QoS 1, retained)  "online" | "offline"
  "offline" is the Last Will (crash/kill) and is also published on graceful stop (SIGTERM),
  because a clean DISCONNECT does not fire the Will.
- Subscribes to field/<zone>/sprinkler/state and field/<zone>/rain/state.
"""
import json
import os
import random
import signal
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
ZONE = os.environ["ZONE"]
INDEX = int(os.environ["SENSOR_INDEX"])
SENSOR_ID = f"soil-{ZONE}-{INDEX}"
SOURCES = ["sprinkler", "rain"]

TICK_S = 5
KEEPALIVE_S = 10
INITIAL_MIN, INITIAL_MAX = 45.0, 55.0
DRY_MIN, DRY_MAX = 1.0, 3.0
WET_STEP = 10.0
MIN_MOISTURE, MAX_MOISTURE = 30.0, 85.0

STATUS_TOPIC = f"field/{ZONE}/soil/{SENSOR_ID}/status"
VALUE_TOPIC = f"field/{ZONE}/soil/{SENSOR_ID}"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SoilSensor:
    def __init__(self):
        self.moisture = random.uniform(INITIAL_MIN, INITIAL_MAX)
        self.wet = {s: False for s in SOURCES}
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=SENSOR_ID)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.will_set(STATUS_TOPIC, "offline", qos=1, retain=True)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe([(f"field/{ZONE}/{s}/state", 1) for s in SOURCES])
        client.publish(STATUS_TOPIC, "online", qos=1, retain=True)

    def on_message(self, client, userdata, msg):
        try:
            source = msg.topic.split("/")[2]
            state = json.loads(msg.payload).get("state")
        except (ValueError, AttributeError, IndexError):
            return
        if source in self.wet:
            self.wet[source] = (state == "on")

    def step(self):
        delta = -random.uniform(DRY_MIN, DRY_MAX) + WET_STEP * sum(self.wet.values())
        self.moisture = min(MAX_MOISTURE, max(MIN_MOISTURE, self.moisture + delta))

    def publish_reading(self):
        payload = {"zone": ZONE, "sensor_id": SENSOR_ID, "value": round(self.moisture, 2),
                   "unit": "%", "timestamp": now_iso()}
        self.client.publish(VALUE_TOPIC, json.dumps(payload), qos=0)

    def run(self, stop):
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=KEEPALIVE_S)
        self.client.loop_start()
        print(f"{SENSOR_ID} started", flush=True)
        while not stop.wait(TICK_S):
            self.step()
            self.publish_reading()
        try:
            self.client.publish(STATUS_TOPIC, "offline", qos=1, retain=True).wait_for_publish(2)
        except (RuntimeError, ValueError):
            pass
        self.client.loop_stop()
        self.client.disconnect()
        print(f"{SENSOR_ID} stopped", flush=True)


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    SoilSensor().run(stop)


if __name__ == "__main__":
    main()
