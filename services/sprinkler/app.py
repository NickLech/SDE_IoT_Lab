"""Sprinkler service (simple): one valve per zone, one MQTT connection per valve.

One connection per valve because an MQTT client has exactly ONE Last Will
(will_set overwrites), and each valve needs its own "offline" will.

- Command (QoS 1): field/<zone>/sprinkler/cmd
      {"action": "on", "duration_s": 30}   |   {"action": "off"}
- State (QoS 1, retained): field/<zone>/sprinkler/state
      {"state": "on"|"off"}
- Liveness (QoS 1, retained): field/<zone>/sprinkler/status
      "online" | "offline"   ("offline" is also the MQTT Last Will)
- "on" auto-turns off after duration_s (safety net); a repeated "on" renews it.

Liveness: state is published only on change, so silence cannot be used to
detect a dead service. We announce "online" on every connect and rely on two
mechanisms for "offline": the broker fires the Last Will when our TCP
connection dies without a clean DISCONNECT (crash, kill, network cut), and we
publish "offline" ourselves on graceful shutdown, where the Will is NOT sent.
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
KEEPALIVE_S = 10   # short keepalive: after a crash the broker fires the Will in ~1.5x this


class Sprinklers:
    def __init__(self):
        self.timers = {}  # zone -> running auto-off Timer
        self.clients = {}  # zone -> MQTT connection for that valve
        for zone in ZONES:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sprinkler-{zone}")
            client.on_connect = self.on_connect
            client.on_message = self.on_message
            # Last Will: if this connection dies without a clean DISCONNECT
            # (crash, kill, network cut), the broker publishes "offline" for us.
            client.will_set(f"field/{zone}/sprinkler/status", "offline", qos=1, retain=True)
            self.clients[zone] = client

    def publish_state(self, zone, state):
        self.clients[zone].publish(f"field/{zone}/sprinkler/state", json.dumps({"state": state}), qos=1,
                                   retain=True)

    def publish_status(self, zone, status):
        self.clients[zone].publish(f"field/{zone}/sprinkler/status", status, qos=1, retain=True)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        zone = next(z for z, c in self.clients.items() if c is client)
        client.subscribe(f"field/{zone}/sprinkler/cmd", qos=1)
        self.publish_status(zone, "online")
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
        for client in self.clients.values():
            client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=KEEPALIVE_S)
            client.loop_start()
        print(f"sprinkler started: {ZONES} (one connection per valve)")
        stop.wait()
        for zone in ZONES:
            self.cancel_timer(zone)
            self._publish_wait(zone, f"field/{zone}/sprinkler/state", json.dumps({"state": "off"}))
        # A clean DISCONNECT cancels the Will: announce the goodbye ourselves,
        # after flushing the "off" states.
        for zone in ZONES:
            self._publish_wait(zone, f"field/{zone}/sprinkler/status", "offline")
        for client in self.clients.values():
            client.loop_stop()
            client.disconnect()

    def _publish_wait(self, zone, topic, payload):
        """Retained QoS 1 publish, waiting briefly for the broker ACK.

        Only used during shutdown: the goodbye must reach the broker before
        the clean DISCONNECT cancels the Will.
        """
        try:
            self.clients[zone].publish(topic, payload, qos=1, retain=True).wait_for_publish(2)
        except (RuntimeError, ValueError):
            pass


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    Sprinklers().run(stop)


if __name__ == "__main__":
    main()