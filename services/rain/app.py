"""Rain service (simple): random periodic rain, one MQTT client.

- State (QoS 1, retained): field/<zone>/rain/state
      {"state": "on"|"off"}
- Mode (QoS 1, retained, published by the dashboard): field/rain/mode
      {"mode": "auto"|"dry"|"rain"}
  In "auto" the service drives the rain state from its random cycle.
  In "dry" / "rain" the dashboard owns the state: the service keeps its
  cycle running internally but publishes nothing, so it cannot overwrite
  the manual override. Switching back to "auto" re-publishes the current
  simulated state immediately.
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
MODE_TOPIC = "field/rain/mode"

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
        # None = retained mode not received yet (treated as "auto" after the first tick)
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
        # The retained mode message is delivered right after subscribing.
        client.subscribe(MODE_TOPIC, qos=1)
        with self.lock:
            # Publish only when we know we are in auto; if the mode is still
            # unknown, on_message / the first step will decide.
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
                self.publish_all()            # realign to the simulated state

    def step(self):
        with self.lock:
            if self.mode is None:             # no retained mode arrived: default to auto
                self.mode = "auto"
                self.publish_all()

            self.pos += 1
            if self.pos >= self.cycle_ticks:  # cycle over: start a new, dry one with a new random length
                self.pos = 0
                self.cycle_ticks = self.new_cycle()
            raining = self.pos >= self.cycle_ticks - DURATION_TICKS
            if raining != self.raining:
                self.raining = raining
                print(f"rain {'ON' if raining else 'OFF'} (mode={self.mode})")
                if self.mode == "auto":       # in manual modes the cycle advances but nothing is published
                    self.publish_all()

    def run(self, stop):
        self.client.connect_async(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()
        print(f"rain started: {ZONES}, cycle {RAIN_MIN_S}-{RAIN_MAX_S}s, rain for {RAIN_DURATION_S}s")
        while not stop.wait(TICK_S):
            self.step()
        with self.lock:
            # On shutdown, reset to "off" only if we own the state (auto).
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