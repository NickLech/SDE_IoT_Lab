"""Rain service: random periodic rain on all zones, single MQTT client.

Topics (QoS 1, retained):
- field/<zone>/rain/state   {"state": "on"|"off"}
- field/rain/mode           {"mode": "auto"|"dry"|"rain"}   (published by the dashboard)

In "auto" the service publishes the simulated state. In "dry"/"rain" the
dashboard owns the state: the cycle keeps running internally but nothing is
published, so the manual override is never overwritten. Switching back to
"auto" re-publishes the current simulated state immediately.

Each cycle lasts a random RAIN_MIN_S..RAIN_MAX_S seconds and starts dry; it
rains during the last RAIN_DURATION_S seconds.
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
MODE_TOPIC = "field/rain/mode"

TICK_S = 5
RAIN_MIN_S = int(os.environ.get("RAIN_MIN_S", 120))           # shortest cycle
RAIN_MAX_S = int(os.environ.get("RAIN_MAX_S", 300))           # longest cycle
RAIN_DURATION_S = int(os.environ.get("RAIN_DURATION_S", 30))  # rain length at the end of each cycle

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
        # None until the retained mode arrives; step() falls back to "auto"
        self.mode = None
        self.lock = threading.Lock()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="rain-service")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

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
        client.subscribe(MODE_TOPIC, qos=1)
        with self.lock:
            # Republish only if already in auto; otherwise on_message / step() decides.
            if self.mode == "auto":
                self.publish_all()

    def on_message(self, client, userdata, msg):
        try:
            mode = json.loads(msg.payload).get("mode")
        except (ValueError, AttributeError):
            return
        if mode not in ("auto", "dry", "rain"):
            return
        with self.lock:
            previous, self.mode = self.mode, mode
            print(f"mode: {previous} -> {mode}")
            if mode == "auto":
                self.publish_all()            # realign with the simulated state

    def step(self):
        with self.lock:
            if self.mode is None:             # no retained mode received: default to auto
                self.mode = "auto"
                self.publish_all()

            self.pos += 1
            if self.pos >= self.cycle_ticks:  # cycle over: start a new dry one with a new length
                self.pos = 0
                self.cycle_ticks = self.new_cycle()
            raining = self.pos >= self.cycle_ticks - DURATION_TICKS
            if raining != self.raining:
                self.raining = raining
                print(f"rain {'ON' if raining else 'OFF'} (mode={self.mode})")
                if self.mode == "auto":       # manual modes: the cycle advances, nothing is published
                    self.publish_all()

    def run(self, stop):
        self.client.connect_async(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()
        print(f"rain started: {ZONES}, cycle {RAIN_MIN_S}-{RAIN_MAX_S}s, rain for {RAIN_DURATION_S}s")
        while not stop.wait(TICK_S):
            self.step()
        with self.lock:
            # On shutdown reset to "off" only if we own the state (auto).
            if self.mode in (None, "auto"):
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