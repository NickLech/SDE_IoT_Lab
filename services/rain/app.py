"""Rain service (simple): random periodic rain, one MQTT client.

- State (QoS 1, retained): field/<zone>/rain/state
      {"state": "on"|"off"}
- Cycles have a random length between RAIN_MIN_S and RAIN_MAX_S seconds. In each cycle it rains for
  RAIN_DURATION_S seconds, on all zones, at the end of the cycle.
  The cycle starts dry, so the first rain begins after (cycle length - RAIN_DURATION_S).
"""
import json
import os
import random
import signal
import threading

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
ZONES = ["zone1", "zone2", "zone3"]

TICK_S = 5
RAIN_MIN_S = int(os.environ.get("RAIN_MIN_S", 120))           # shortest cycle
RAIN_MAX_S = int(os.environ.get("RAIN_MAX_S", 300))           # longest cycle
RAIN_DURATION_S = int(os.environ.get("RAIN_DURATION_S", 30))  # rain length inside each cycle

MIN_TICKS = RAIN_MIN_S // TICK_S
MAX_TICKS = RAIN_MAX_S // TICK_S
DURATION_TICKS = RAIN_DURATION_S // TICK_S
assert MIN_TICKS <= MAX_TICKS, "RAIN_MIN_S must not be greater than RAIN_MAX_S"
assert 0 < DURATION_TICKS < MIN_TICKS, "RAIN_DURATION_S must be shorter than RAIN_MIN_S"


class Rain:
    def __init__(self):
        self.pos = 0                          # ticks elapsed in the current cycle
        self.cycle_ticks = self.new_cycle()
        self.raining = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="rain-service")
        self.client.on_connect = self.on_connect

    def new_cycle(self):
        ticks = random.randint(MIN_TICKS, MAX_TICKS)
        print(f"next cycle: {ticks * TICK_S}s (rain in the last {DURATION_TICKS * TICK_S}s)")
        return ticks

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
        self.pos += 1
        if self.pos >= self.cycle_ticks:      # cycle over: start a new, dry one with a new random length
            self.pos = 0
            self.cycle_ticks = self.new_cycle()
        raining = self.pos >= self.cycle_ticks - DURATION_TICKS
        if raining != self.raining:
            self.raining = raining
            self.publish_all()
            print(f"rain {'ON' if raining else 'OFF'}")

    def run(self, stop):
        self.client.connect_async(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()
        print(f"rain started: {ZONES}, cycle {RAIN_MIN_S}-{RAIN_MAX_S}s, rain for {RAIN_DURATION_S}s")
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