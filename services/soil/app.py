"""Soil service (simple version): 9 soil-moisture sensors pushing readings over MQTT.

- Topic: field/<zone>/soil/<sensor_id>   (QoS 0)
  {"zone", "sensor_id", "value", "unit": "%", "timestamp"}
- Status (retained, LWT): field/<zone>/soil/<sensor_id>/status  -> "online" / "offline"
- Each zone has a simple moisture model: it dries at a constant rate and
  gets wetter while the zone's sprinkler is on.
"""
import json
import os
import signal
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
ZONES = ["zone1", "zone2", "zone3"]
SENSORS_PER_ZONE = 3
PUBLISH_INTERVAL_S = 2

INITIAL_MOISTURE = 50.0  # %
DRY_RATE = 3.0           # %/min
IRRIGATION_GAIN = 12.0   # %/min while the sprinkler is on
SATURATION = 80.0        # %


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_client(client_id):
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)


class Environment(threading.Thread):
    """Holds the moisture of each zone and updates it every second."""

    def __init__(self, stop):
        super().__init__(daemon=True)
        self.stop = stop
        self.moisture = {z: INITIAL_MOISTURE for z in ZONES}
        self.irrigating = {z: False for z in ZONES}

        self.client = new_client("soil-environment")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def start_mqtt(self):
        self.client.connect_async(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe("field/+/sprinkler/state", qos=1)

    def on_message(self, client, userdata, msg):
        try:
            zone = msg.topic.split("/")[1]
            state = json.loads(msg.payload).get("state")
        except (ValueError, IndexError, AttributeError):
            return
        if zone in self.irrigating:
            self.irrigating[zone] = (state == "on")

    def run(self):
        last = time.monotonic()
        while not self.stop.wait(1.0):
            now = time.monotonic()
            dt_min = (now - last) / 60.0
            last = now
            for zone in ZONES:
                delta = -DRY_RATE * dt_min
                if self.irrigating[zone]:
                    delta += IRRIGATION_GAIN * dt_min
                self.moisture[zone] = min(SATURATION, max(0.0, self.moisture[zone] + delta))

    def shutdown(self):
        self.client.loop_stop()
        self.client.disconnect()


class SoilSensor(threading.Thread):
    def __init__(self, sensor_id, zone, env, stop):
        super().__init__(daemon=True)
        self.sensor_id = sensor_id
        self.zone = zone
        self.env = env
        self.stop = stop
        self.topic = f"field/{zone}/soil/{sensor_id}"
        self.status_topic = f"{self.topic}/status"

        self.client = new_client(sensor_id)
        self.client.will_set(self.status_topic, "offline", qos=1, retain=True)
        self.client.on_connect = self.on_connect

    def start_mqtt(self):
        self.client.connect_async(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.publish(self.status_topic, "online", qos=1, retain=True)

    def run(self):
        while not self.stop.is_set():
            if self.client.is_connected():
                payload = {
                    "zone": self.zone,
                    "sensor_id": self.sensor_id,
                    "value": round(self.env.moisture[self.zone], 2),
                    "unit": "%",
                    "timestamp": now_iso(),
                }
                self.client.publish(self.topic, json.dumps(payload), qos=0)
            self.stop.wait(PUBLISH_INTERVAL_S)

    def shutdown(self):
        if self.client.is_connected():
            self.client.publish(self.status_topic, "offline", qos=1, retain=True).wait_for_publish(2)
        self.client.loop_stop()
        self.client.disconnect()


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    env = Environment(stop)
    sensors = [
        SoilSensor(f"soil-{zone}-{i}", zone, env, stop)
        for zone in ZONES
        for i in range(1, SENSORS_PER_ZONE + 1)
    ]
    print(f"soil started: {len(sensors)} sensors on {ZONES}")

    env.start_mqtt()
    env.start()
    for s in sensors:
        s.start_mqtt()
        s.start()

    stop.wait()
    for s in sensors:
        s.shutdown()
    env.shutdown()


if __name__ == "__main__":
    main()