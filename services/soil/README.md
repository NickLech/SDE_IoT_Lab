# services/soil

**Soil-moisture** sensor container: 9 simulated sensors (3 redundant per zone), **push** over MQTT.

- Telemetry topic: `field/<zone>/soil/<sensor_id>` (QoS 0, not retained), payload in `docs/architecture.md`.
- Each sensor is an independent MQTT client with a Last Will on `.../<sensor_id>/status`.
- The zone's true moisture dries over time and rises while `field/<zone>/sprinkler/state` is `on`.
- Each sensor adds calibration offset, Gaussian noise and random spikes; break one with `debug/<sensor_id>/fault`.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | `localhost` / `1883` | broker (`broker` in compose) |
| `ZONES` | `zone1,zone2,zone3` | simulated zones |
| `SENSORS_PER_ZONE` | `3` | redundant sensors per zone |
| `PUBLISH_INTERVAL_S` | `2` | mean publish interval (±10%) |
| `NOISE_STD` | `0.8` | noise standard deviation (%) |
| `SPIKE_PROB` | `0.03` | spike probability per reading (±10–25 %) |
| `BIAS_STD` | `0.5` | per-sensor calibration offset (%) |
| `INITIAL_MOISTURE` | `45,50,40` | starting moisture per zone (%) |
| `DRY_RATE` | `3.0,4.5,2.0` | loss per zone (%/min) |
| `IRRIGATION_GAIN` | `12` | gain while the sprinkler is on (%/min) |
| `SATURATION` | `80` | max reachable moisture (%) |
| `TIME_SCALE` | `1` | physics speed multiplier (tests/demos) |
| `LOG_LEVEL` | `INFO` | `DEBUG` prints every message |

## Run without Docker
```bash
pip install -r requirements.txt
MQTT_HOST=localhost python app.py
```
