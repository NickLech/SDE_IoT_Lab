"""Sprinkler service (simple): one valve per zone, one MQTT client.

- Command (QoS 1): field/<zone>/sprinkler/cmd
      {"action": "on", "duration_s": 30}   |   {"action": "off"}
- State (QoS 1, retained): field/<zone>/sprinkler/state
      {"state": "on"|"off"}
- "on" auto-turns off after duration_s (safety net); a repeated "on" renews it.
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


class Sprinklers:
    def __init__(self):
        self.timers = {}  # zone -> running auto-off Timer
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sprinkler-service")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def publish_state(self, zone, state):
        self.client.publish(f"field/{zone}/sprinkler/state", json.dumps({"state": state}), qos=1, retain=True)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe("field/+/sprinkler/cmd", qos=1)
        for zone in ZONES:
            self.publish_state(zone, "off")

    def on_message(self, client, userdata, msg):
        try:
            zone = msg.topic.split("/")[1]
            action = json.loads(msg.payload)["action"]
            duration = json.loads(msg.payload).get("duration_s", DEFAULT_DURATION_S)
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            print(f"invalid command on {msg.topic}: {msg.payload!r}")
            return
        if zone not in ZONES:
            return

        if action == "on":
            self.turn_on(zone, duration)
        elif action == "off":
            self.turn_off(zone)

    def turn_on(self, zone, duration):
        self.cancel_timer(zone)
        timer = threading.Timer(duration, self.turn_off, args=(zone,))
        timer.daemon = True
        timer.start()
        self.timers[zone] = timer
        self.publish_state(zone, "on")
        print(f"{zone}: ON for {duration}s")

    def turn_off(self, zone):
        self.cancel_timer(zone)
        self.publish_state(zone, "off")
        print(f"{zone}: OFF")

    def cancel_timer(self, zone):
        timer = self.timers.pop(zone, None)
        if timer:
            timer.cancel()

    def run(self, stop):
        self.client.connect_async(MQTT_HOST, MQTT_PORT)
        self.client.loop_start()
        print(f"sprinkler started: {ZONES}")
        stop.wait()
        for zone in ZONES:
            self.cancel_timer(zone)
            self.publish_state(zone, "off")
        self.client.loop_stop()
        self.client.disconnect()


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    Sprinklers().run(stop)


if __name__ == "__main__":
    main()