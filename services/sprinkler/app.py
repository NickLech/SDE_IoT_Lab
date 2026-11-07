"""Sprinkler service (simple version): one valve per zone, driven over MQTT.

- Command (QoS 1): field/<zone>/sprinkler/cmd
      {"action": "on", "duration_s": 30}   |   {"action": "off"}
- State (QoS 1, retained): field/<zone>/sprinkler/state
      {"state": "on"|"off"}   (LWT: {"state": "offline"})
- "on" auto-turns off after duration_s (safety net).
"""
import json
import os
import signal
import threading

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
ZONES = ["zone1", "zone2", "zone3"]
DEFAULT_DURATION_S = 30


class Valve:
    def __init__(self, zone):
        self.zone = zone
        self.cmd_topic = f"field/{zone}/sprinkler/cmd"
        self.state_topic = f"field/{zone}/sprinkler/state"
        self.state = "off"
        self.timer = None

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sprinkler-{zone}")
        self.client.will_set(self.state_topic, json.dumps({"state": "offline"}), qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def start(self):
        self.client.connect_async(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()

    def publish_state(self):
        self.client.publish(self.state_topic, json.dumps({"state": self.state}), qos=1, retain=True)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe(self.cmd_topic, qos=1)
        self.publish_state()

    def on_message(self, client, userdata, msg):
        try:
            cmd = json.loads(msg.payload)
            action = cmd["action"]
        except (ValueError, KeyError, TypeError):
            print(f"{self.zone}: invalid command {msg.payload!r}")
            return

        if action == "on":
            self.turn_on(cmd.get("duration_s", DEFAULT_DURATION_S))
        elif action == "off":
            self.turn_off()

    def turn_on(self, duration):
        if self.timer:
            self.timer.cancel()  # repeated "on" renews the duration
        self.timer = threading.Timer(duration, self.turn_off)
        self.timer.daemon = True
        self.timer.start()
        self.state = "on"
        self.publish_state()
        print(f"{self.zone}: ON for {duration}s")

    def turn_off(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None
        self.state = "off"
        self.publish_state()
        print(f"{self.zone}: OFF")

    def shutdown(self):
        self.turn_off()
        self.client.loop_stop()
        self.client.disconnect()


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    valves = [Valve(z) for z in ZONES]
    for v in valves:
        v.start()
    print(f"sprinkler started: {ZONES}")

    stop.wait()
    for v in valves:
        v.shutdown()


if __name__ == "__main__":
    main()