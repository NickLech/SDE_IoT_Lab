"""Rain service (simple): periodic rain, one MQTT client.

- State (QoS 1, retained): field/<zone>/rain/state
      {"state": "on"|"off"}
- Every RAIN_EVERY_S seconds it rains for RAIN_DURATION_S seconds, on all zones.
  The cycle starts dry, so the first rain begins after RAIN_EVERY_S - RAIN_DURATION_S.
"""
import json
import os
import signal
import threading

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
ZONES = ["zone1", "zone2", "zone3"]

TICK_S = 5
RAIN_EVERY_S = int(os.environ.get("RAIN_EVERY_S", 120))      # period of the cycle
RAIN_DURATION_S = int(os.environ.get("RAIN_DURATION_S", 30))  # rain length inside each cycle

PERIOD_TICKS = RAIN_EVERY_S // TICK_S
DURATION_TICKS = RAIN_DURATION_S // TICK_S
assert 0 < DURATION_TICKS < PERIOD_TICKS, "RAIN_DURATION_S must be shorter than RAIN_EVERY_S"


class Rain:
    def __init__(self):
        self.tick = 0
        self.raining = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="rain-service")
        self.client.on_connect = self.on_connect

    def publish_state(self, zone, state):
        return self.client.publish(
            f"field/{zone}/rain/state", json.dumps({"state": state}), qos=1, retain=True
        )

    def publish_all(self):
        state = "on" if self.raining else "off"
        for zone in ZONES:
            self.publish_state(zone, state)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.publish_all()

    def step(self):
        self.tick += 1
        raining = (self.tick % PERIOD_TICKS) >= PERIOD_TICKS - DURATION_TICKS
        if raining != self.raining:
            self.raining = raining
            self.publish_all()
            print(f"rain {'ON' if raining else 'OFF'}")

    def run(self, stop):
        self.client.connect_async(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()
        print(f"rain started: {ZONES}, every {RAIN_EVERY_S}s for {RAIN_DURATION_S}s")
        while not stop.wait(TICK_S):
            self.step()
        self.raining = False
        for zone in ZONES:
            self.publish_state(zone, "off").wait_for_publish(2)
        self.client.loop_stop()
        self.client.disconnect()


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    Rain().run(stop)


if __name__ == "__main__":
    main()