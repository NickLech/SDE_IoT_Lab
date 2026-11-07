# services/sprinkler

Actuator: one valve per zone, each an independent MQTT client.

- Command: `field/<zone>/sprinkler/cmd` (QoS 1, not retained) — `{"action":"on","duration_s":30}` or `{"action":"off"}`.
- State: `field/<zone>/sprinkler/state` (QoS 1, **retained**) — `{"state":"on|off","timestamp":"..."}`; Last Will `{"state":"offline"}`.
- A repeated `on` is idempotent: it renews the duration instead of adding to it.
- Auto-off after `duration_s` (capped by `MAX_DURATION_S`); invalid commands are ignored and logged.
- On (re)connect it republishes the real state, overriding a leftover Last Will `offline`.

| Variable | Default | Meaning |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | `localhost` / `1883` | broker |
| `ZONES` | `zone1,zone2,zone3` | valves to create |
| `DEFAULT_DURATION_S` | `30` | duration if the command has none |
| `MAX_DURATION_S` | `300` | safety cap |
