"""Sprinkler valve of ONE zone: one MQTT connection, one Last Will.

Env: ZONE (e.g. zone1)

- Command (QoS 1): field/<zone>/sprinkler/cmd     {"action": "on", "duration_s": 30} | {"action": "off"}
- State (QoS 1, retained): field/<zone>/sprinkler/state   {"state": "on"|"off"}
- Liveness (QoS 1, retained): field/<zone>/sprinkler/status   "online" | "offline"
  "offline" is the Last Will (crash/kill/network cut) and is published by hand on graceful
  stop, where the broker does NOT fire the Will.
- "on" auto-turns off after duration_s (safety net); a repeated "on" renews it.
"""
import json
import os
import signal
import threading

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
ZONE = os.environ["ZONE"]
DEFAULT_DURATION_S = 30
KEEPALIVE_S = 10

CMD_TOPIC = f"field/{ZONE}/sprinkler/cmd"
STATE_TOPIC = f"field/{ZONE}/sprinkler/state"
STATUS_TOPIC = f"field/{ZONE}/sprinkler/status"


class Sprinkler:
    def __init__(self):
        self.timer = None
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sprinkler-{ZONE}")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.will_set(STATUS_TOPIC, "offline", qos=1, retain=True)

    def publish_state(self, state):
        return self.client.publish(STATE_TOPIC, json.dumps({"state": state}), qos=1, retain=True)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe(CMD_TOPIC, qos=1)
        client.publish(STATUS_TOPIC, "online", qos=1, retain=True)
        self.publish_state("off")

    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload)
            action = data["action"]
            duration = data.get("duration_s", DEFAULT_DURATION_S)
            if isinstance(duration, bool) or not isinstance(duration, (int, float)):
                raise TypeError("duration_s")
        except (ValueError, KeyError, TypeError, AttributeError):
            print(f"invalid command on {msg.topic}: {msg.payload!r}", flush=True)
            return
        if action == "on":
            self.turn_on(duration)
        elif action == "off":
            self.turn_off()

    def turn_on(self, duration):
        self.cancel_timer()
        self.timer = threading.Timer(duration, self.turn_off)
        self.timer.daemon = True
        self.timer.start()
        self.publish_state("on")
        print(f"{ZONE}: ON for {duration}s", flush=True)

    def turn_off(self):
        self.cancel_timer()
        self.publish_state("off")
        print(f"{ZONE}: OFF", flush=True)

    def cancel_timer(self):
        timer, self.timer = self.timer, None
        if timer:
            timer.cancel()

    def run(self, stop):
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=KEEPALIVE_S)
        self.client.loop_start()
        print(f"sprinkler started: {ZONE}", flush=True)
        stop.wait()
        self.cancel_timer()
        try:
            self.publish_state("off").wait_for_publish(2)
            self.client.publish(STATUS_TOPIC, "offline", qos=1, retain=True).wait_for_publish(2)
        except (RuntimeError, ValueError):
            pass
        self.client.loop_stop()
        self.client.disconnect()
        print(f"sprinkler stopped: {ZONE}", flush=True)


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    Sprinkler().run(stop)


if __name__ == "__main__":
    main()
