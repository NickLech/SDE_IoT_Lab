"""Soil service (simple): 9 soil-moisture sensors, one MQTT client, one loop.

- Publishes on field/<zone>/soil/<sensor_id>  (QoS 0)
  {"zone", "sensor_id", "value", "unit": "%", "timestamp"}
- Subscribes to field/+/sprinkler/state and field/+/rain/state  ({"state": "on"|"off"})
- Every sensor starts with a random value in [INITIAL_MIN, INITIAL_MAX].
- Every TICK_S seconds each sensor loses a random value in [DRY_MIN, DRY_MAX]
  and gains WET_STEP for each active source of its zone (sprinkler, rain).
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
ZONES = ["zone1", "zone2", "zone3"]
SENSORS_PER_ZONE = 3
SOURCES = ["sprinkler", "rain"]

TICK_S = 5
INITIAL_MIN = 45.0  # % initial value, random per sensor
INITIAL_MAX = 55.0
DRY_MIN = 1.0       # % lost every tick, random per sensor
DRY_MAX = 3.0
WET_STEP = 10.0      # % gained every tick for each active source
MIN_MOISTURE = 30.0
MAX_MOISTURE = 85.0


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SoilService:
    def __init__(self):
        # sensor_id -> zone, and sensor_id -> current moisture
        self.zone_of = {
            f"soil-{z}-{i}": z for z in ZONES for i in range(1, SENSORS_PER_ZONE + 1)
        }
        self.moisture = {s: random.uniform(INITIAL_MIN, INITIAL_MAX) for s in self.zone_of}
        self.wet = {z: {s: False for s in SOURCES} for z in ZONES}

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="soil-service")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe([(f"field/+/{s}/state", 1) for s in SOURCES])

    def on_message(self, client, userdata, msg):
        try:
            _, zone, source, _ = msg.topic.split("/")
            state = json.loads(msg.payload).get("state")
        except (ValueError, AttributeError):
            return
        if zone in self.wet and source in self.wet[zone]:
            self.wet[zone][source] = (state == "on")

    def step(self):
        for sensor_id, zone in self.zone_of.items():
            delta = -random.uniform(DRY_MIN, DRY_MAX) + WET_STEP * sum(self.wet[zone].values())
            value = self.moisture[sensor_id] + delta
            self.moisture[sensor_id] = min(MAX_MOISTURE, max(MIN_MOISTURE, value))

    def publish_readings(self):
        for sensor_id, zone in self.zone_of.items():
            payload = {
                "zone": zone,
                "sensor_id": sensor_id,
                "value": round(self.moisture[sensor_id], 2),
                "unit": "%",
                "timestamp": now_iso(),
            }
            self.client.publish(f"field/{zone}/soil/{sensor_id}", json.dumps(payload), qos=0)

    def run(self, stop):
        self.client.connect_async(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()
        print(f"soil started: {len(self.zone_of)} sensors on {ZONES}")
        while not stop.wait(TICK_S):
            self.step()
            self.publish_readings()
        self.client.loop_stop()
        self.client.disconnect()


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    SoilService().run(stop)


if __name__ == "__main__":
    main()