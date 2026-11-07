"""Sprinkler service: actuator with one valve per zone, driven over MQTT.

- Each valve is an independent MQTT client, so it has its own Last Will (offline).
- Command (QoS 1, NOT retained): field/<zone>/sprinkler/cmd
      {"action": "on", "duration_s": 30}   |   {"action": "off"}
- State (QoS 1, retained):       field/<zone>/sprinkler/state
      {"state": "on"|"off", "timestamp": "..."}   (LWT: {"state": "offline"})
- Repeated "on" is idempotent: it renews the duration instead of stacking.
- Auto-off after duration_s (safety net against lost "off" commands).

Contracts: docs/architecture.md
"""
import json
import logging
import os
import signal
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

log = logging.getLogger("sprinkler")

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
ZONES = [z.strip() for z in os.environ.get("ZONES", "zone1,zone2,zone3").split(",") if z.strip()]
DEFAULT_DURATION_S = float(os.environ.get("DEFAULT_DURATION_S", 30))
MAX_DURATION_S = float(os.environ.get("MAX_DURATION_S", 300))


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Valve:
    def __init__(self, zone):
        self.zone = zone
        self.cmd_topic = f"field/{zone}/sprinkler/cmd"
        self.state_topic = f"field/{zone}/sprinkler/state"
        self.state = "off"
        self._timer = None
        self._lock = threading.Lock()

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sprinkler-{zone}")
        self.client.will_set(self.state_topic, json.dumps({"state": "offline"}), qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(1, 10)

    def start(self):
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        self.client.loop_start()

    def _publish_state(self):
        payload = {"state": self.state, "timestamp": now_iso()}
        self.client.publish(self.state_topic, json.dumps(payload), qos=1, retain=True)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        log.info("%s connected to broker (%s)", self.zone, reason_code)
        client.subscribe(self.cmd_topic, qos=1)
        # After a reconnect the broker may hold the LWT "offline": republish the real state
        with self._lock:
            self._publish_state()

    def _on_message(self, client, userdata, msg):
        try:
            cmd = json.loads(msg.payload)
            action = cmd["action"]
        except (ValueError, KeyError, TypeError):
            log.warning("%s: invalid command %r", self.zone, msg.payload[:100])
            return
        if action == "on":
            try:
                duration = float(cmd.get("duration_s", DEFAULT_DURATION_S))
            except (TypeError, ValueError):
                log.warning("%s: invalid duration_s, using %ss", self.zone, DEFAULT_DURATION_S)
                duration = DEFAULT_DURATION_S
            if duration <= 0:
                log.warning("%s: duration_s <= 0, ignoring", self.zone)
                return
            self._turn_on(min(duration, MAX_DURATION_S))
        elif action == "off":
            self._turn_off("command")
        else:
            log.warning("%s: unknown action %r", self.zone, action)

    def _turn_on(self, duration):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(duration, self._turn_off, args=("timeout",))
            self._timer.daemon = True
            self._timer.start()
            if self.state != "on":
                log.info("%s: ON for %.0fs", self.zone, duration)
            else:
                log.info("%s: already ON, duration renewed to %.0fs", self.zone, duration)
            self.state = "on"
            self._publish_state()

    def _turn_off(self, reason):
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            if self.state != "off":
                log.info("%s: OFF (%s)", self.zone, reason)
            self.state = "off"
            self._publish_state()

    def shutdown(self):
        self._turn_off("shutdown")
        self.client.loop_stop()
        self.client.disconnect()


def main():
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    valves = [Valve(z) for z in ZONES]
    log.info("starting: valves %s, broker %s:%d", ", ".join(ZONES), MQTT_HOST, MQTT_PORT)
    for v in valves:
        v.start()
    stop.wait()
    log.info("shutting down")
    for v in valves:
        v.shutdown()


if __name__ == "__main__":
    main()
