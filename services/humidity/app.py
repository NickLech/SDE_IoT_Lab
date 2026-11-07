"""Soil service: 9 soil-moisture sensors that PUSH readings over MQTT.

- Each sensor is an independent MQTT client (client_id = sensor_id) with its own
  send rhythm and calibration offset, so data reaches the central node asynchronously.
- Each zone has a hidden physical model: soil dries over time and gets wetter
  while the zone's sprinkler is on (state read from MQTT).
- Sensors add Gaussian noise and random spikes, and can be broken on demand via
  debug/<sensor_id>/fault (used in the data-fusion example).

Contracts: docs/architecture.md
"""
import json
import logging
import os
import random
import signal
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

log = logging.getLogger("soil")


# ----------------------------------------------------------------------------- config
def env_float(name, default):
    return float(os.environ.get(name, default))


MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
ZONES = [z.strip() for z in os.environ.get("ZONES", "zone1,zone2,zone3").split(",") if z.strip()]
SENSORS_PER_ZONE = int(os.environ.get("SENSORS_PER_ZONE", 3))
PUBLISH_INTERVAL_S = env_float("PUBLISH_INTERVAL_S", 2)
NOISE_STD = env_float("NOISE_STD", 0.8)        # noise standard deviation (%)
SPIKE_PROB = env_float("SPIKE_PROB", 0.03)     # spike probability per reading
BIAS_STD = env_float("BIAS_STD", 0.5)          # per-sensor calibration offset (%)
TIME_SCALE = env_float("TIME_SCALE", 1)        # >1 speeds up the physics (tests/demos)


def per_zone(name, default):
    """Comma-separated env list, one value per zone in ZONES order."""
    raw = os.environ.get(name)
    values = [float(v) for v in raw.split(",")] if raw else list(default)
    return {z: values[i % len(values)] for i, z in enumerate(ZONES)}


INITIAL_MOISTURE = per_zone("INITIAL_MOISTURE", [45, 50, 40])   # %
DRY_RATE = per_zone("DRY_RATE", [6.0])                          # %/min lost by evapotranspiration (6 = 1% every 10 s)
IRRIGATION_GAIN = env_float("IRRIGATION_GAIN", 18.0)            # %/min while the sprinkler is on (net +12 after drying)
SATURATION = env_float("SATURATION", 80.0)                      # max reachable moisture (%)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_client(client_id):
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)


# ------------------------------------------------------------------------ zone physics
class ZoneModel:
    """True (hidden) soil moisture of one zone."""

    def __init__(self, name):
        self.name = name
        self.moisture = INITIAL_MOISTURE[name]
        self.irrigating = False
        self._lock = threading.Lock()

    def step(self, dt_min):
        with self._lock:
            delta = -DRY_RATE[self.name] * dt_min
            if self.irrigating:
                delta += IRRIGATION_GAIN * dt_min
            self.moisture = min(SATURATION, max(0.0, self.moisture + delta))

    def set_irrigating(self, value):
        with self._lock:
            self.irrigating = value

    def read(self):
        with self._lock:
            return self.moisture


class Environment(threading.Thread):
    """Advances the zone models and listens to sprinkler states."""

    def __init__(self, zones, stop):
        super().__init__(daemon=True, name="environment")
        self.zones = {z: ZoneModel(z) for z in zones}
        self.stop = stop
        self.client = new_client("soil-environment")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(1, 10)

    def start_mqtt(self):
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        log.info("environment connected to broker (%s)", reason_code)
        client.subscribe("field/+/sprinkler/state", qos=1)

    def _on_message(self, client, userdata, msg):
        try:
            zone = msg.topic.split("/")[1]
            state = json.loads(msg.payload).get("state")
        except (ValueError, IndexError, AttributeError):
            log.warning("invalid sprinkler state on %s", msg.topic)
            return
        model = self.zones.get(zone)
        if model:
            on = state == "on"
            if on != model.irrigating:
                log.info("%s: sprinkler %s", zone, "ON" if on else "off")
            model.set_irrigating(on)

    def run(self):
        last = time.monotonic()
        while not self.stop.wait(1.0):
            t = time.monotonic()
            dt_min = (t - last) / 60.0 * TIME_SCALE
            last = t
            for model in self.zones.values():
                model.step(dt_min)

    def shutdown(self):
        self.client.loop_stop()
        self.client.disconnect()


# ------------------------------------------------------------------------------ sensor
class SoilSensor(threading.Thread):
    FAULT_MODES = ("none", "crazy", "stuck", "drift")

    def __init__(self, sensor_id, zone_model, stop):
        super().__init__(daemon=True, name=sensor_id)
        self.sensor_id = sensor_id
        self.zone = zone_model
        self.stop = stop
        self.bias = random.gauss(0, BIAS_STD)
        self.fault = "none"
        self._stuck_value = None
        self._drift = 0.0

        self.topic = f"field/{zone_model.name}/soil/{sensor_id}"
        self.status_topic = f"{self.topic}/status"   # 5 levels: does NOT match field/+/soil/+
        self.fault_topic = f"debug/{sensor_id}/fault"

        self.client = new_client(sensor_id)
        # Last Will: the broker marks the sensor offline if it vanishes without a clean disconnect
        self.client.will_set(self.status_topic, "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(1, 10)

    # --- MQTT
    def start_mqtt(self):
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        log.debug("%s connected (%s)", self.sensor_id, reason_code)
        client.publish(self.status_topic, "online", qos=1, retain=True)
        client.subscribe(self.fault_topic, qos=1)

    def _on_message(self, client, userdata, msg):
        if msg.topic != self.fault_topic:   # only react to our own debug topic
            return
        raw = msg.payload.decode(errors="replace").strip()
        try:
            mode = json.loads(raw).get("mode") if raw.startswith("{") else raw
        except ValueError:
            mode = None
        if mode not in self.FAULT_MODES:
            log.warning("%s: unknown fault mode %r (valid: %s)",
                        self.sensor_id, raw, ", ".join(self.FAULT_MODES))
            return
        self.fault = mode
        self._stuck_value = None
        self._drift = 0.0
        log.info("%s: fault = %s", self.sensor_id, mode)

    # --- reading simulation
    def measure(self):
        true_value = self.zone.read()
        if self.fault == "crazy":
            return random.uniform(-20, 120)          # may be physically impossible
        if self.fault == "stuck":
            if self._stuck_value is None:
                self._stuck_value = true_value + self.bias
            return self._stuck_value
        if self.fault == "drift":
            self._drift += 0.5                       # growing drift
        value = true_value + self.bias + self._drift + random.gauss(0, NOISE_STD)
        if random.random() < SPIKE_PROB:
            value += random.choice((-1, 1)) * random.uniform(10, 25)
        return min(100.0, max(0.0, value))

    def run(self):
        # random initial offset + jitter: sensors publish asynchronously
        self.stop.wait(random.uniform(0, PUBLISH_INTERVAL_S))
        while not self.stop.is_set():
            if self.client.is_connected():
                payload = {
                    "zone": self.zone.name,
                    "sensor_id": self.sensor_id,
                    "value": round(self.measure(), 2),
                    "unit": "%",
                    "timestamp": now_iso(),
                }
                self.client.publish(self.topic, json.dumps(payload), qos=0, retain=False)
                log.debug("%s -> %s", self.topic, payload["value"])
            self.stop.wait(PUBLISH_INTERVAL_S * random.uniform(0.9, 1.1))

    def shutdown(self):
        if self.client.is_connected():
            self.client.publish(self.status_topic, "offline", qos=1, retain=True).wait_for_publish(2)
        self.client.loop_stop()
        self.client.disconnect()


# ------------------------------------------------------------------------------- main
def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    env = Environment(ZONES, stop)
    sensors = [
        SoilSensor(f"soil-{zone}-{i}", env.zones[zone], stop)
        for zone in ZONES
        for i in range(1, SENSORS_PER_ZONE + 1)
    ]
    log.info("starting: %d zones, %d sensors, broker %s:%d, interval %.1fs",
             len(ZONES), len(sensors), MQTT_HOST, MQTT_PORT, PUBLISH_INTERVAL_S)

    env.start_mqtt()
    env.start()
    for s in sensors:
        s.start_mqtt()
        s.start()

    stop.wait()
    log.info("shutting down")
    for s in sensors:
        s.shutdown()
    env.shutdown()


if __name__ == "__main__":
    main()