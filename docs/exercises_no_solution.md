# Exercises

Three implementation exercises plus one assignment. Each one feeds a panel of the dashboard
(`http://localhost:8050`): a panel turns **green** when its data is flowing correctly, and
**red** while it is missing. All of them are small local edits — no new files are needed.

| # | Topic | File | Where |
|---|-------|------|-------|
| 1 | HTTP pull | `services/central/components/comms.py` | `poll_loop()` |
| 2 | MQTT push | `services/central/components/comms.py` | `on_connect()` |
| 3 | Data fusion | `services/central/components/fusion.py` | `vpd_kpa()` |
| Assignment | Monitor one zone | `services/dashboard/assignment/monitor.py` | TODOs 1–3 |

Apply every change by rebuilding the stack:

```sh
docker compose up --build
```

---

## Exercise 1 — HTTP pull (humidity)

**File**: `services/central/components/comms.py` → `poll_loop()`

The loop already pulls the air temperature of each zone from the temperature service.
Each sensor type is one tuple `(name, where to store the readings, base URL)`:

```python
for name, store, base in (("temperature", state.temp, TEMPERATURE_URL),
                          # <-- your humidity tuple goes here
                          ):
```

Add the humidity tuple: it must store into `state.humid` and use `HUMIDITY_URL`.
The URL is then built as `f"{base.format(zone=zone)}/zones/{zone}/{name}"`.

**Done when**: the HTTP panel is green for both temperature and humidity, and `central`
survives a sensor being stopped and restarted (the loop logs the outage and recovers).

---

## Exercise 2 — MQTT push (soil sensors)

**File**: `services/central/components/comms.py` → `on_connect()`

The soil sensors publish on their own on `field/<zone>/soil/<sensor_id>`. We must subscribe
to the readings of **all zones and all sensors** with a single topic, using the
single-level wildcard `+`, and QoS 1 — same pattern as the topics already listed:

```python
client.subscribe([("field/+/soil/+/status", 1), ("field/+/sprinkler/state", 1), ... ])
```

Hint: `field/+/soil/+` has four levels; the `/status` topics stay separate because they are
plain-text Last-Will messages, not JSON readings.

**Done when**: the MQTT panel is green and all 9 soil sensors show up.

---

## Exercise 3 — Data fusion (VPD)

**File**: `services/central/components/fusion.py` → `vpd_kpa()`

The vapour pressure deficit combines air temperature and relative humidity into one number:

$$
es(T) = 0.6108 \cdot \exp\!\left(\frac{17.27 \cdot T}{T + 237.3}\right) \quad [\text{kPa}]
$$

$$
VPD = es(T) \cdot \left(1 - \frac{RH}{100}\right) \quad [\text{kPa}]
$$

where $T$ is the air temperature in °C and $RH$ the relative humidity in %.

The file currently contains a **placeholder** that ignores the temperature
(`2.0 * (1 - RH/100)`), so the dashboard keeps working before the exercise is done.
Replace it with the real model: compute $es(T)$ from `t_c` (`math.exp` is already imported),
then subtract the actual vapour pressure of the air, $es(T)\cdot RH/100$.

**Expected values** (the fake sensors move in 5–30 °C and 50–80 % RH):

| T (°C) | RH (%) | es (kPa) | VPD (kPa) | band |
|--------|--------|----------|-----------|------|
| 15 | 60 | 1.705 | 0.682 | ok |
| 20 | 50 | 2.338 | 1.169 | optimal |
| 25 | 50 | 3.168 | 1.584 | ok |
| 25 | 70 | 3.168 | 0.950 | optimal |
| 30 | 40 | 4.243 | 2.546 | stress |
| 30 | 80 | 4.243 | 0.849 | optimal |

Bands come from `vpd_band()` in the same file: `< 0.4 low`, `0.4–0.8 ok`, `0.8–1.2 optimal`,
`1.2–1.6 ok`, `> 1.6 stress`.

**Done when**: the VPD fact on the zone cards changes with the air temperature and matches the
formula — e.g. `T = 25 °C, RH = 50 %` gives `1.584 kPa` (the placeholder gives `1.000 kPa`).
Check on the host:

```sh
curl -s localhost:5100/zones | python3 -m json.tool
```

---

## Assignment — monitor one zone

**File**: `services/dashboard/assignment/monitor.py` (the TODOs are marked inside this one file)

This panel watches a **single** zone: temperature over HTTP and rain over MQTT, each in its
own chart. Three TODOs:

**TODO 1 — identity** (top of the file): your name and surname as strings.

```python
STUDENT_NAME = "Ada"
STUDENT_SURNAME = "Lovelace"
```

**TODO 2 — rain topic** (in the *Rain over MQTT* section): the retained rain-state topic of the zone, payload
`{"state": "on" | "off"}`.

Hint: `RAIN_TOPIC` must be exactly that topic — the panel ignores messages received on
any other topic, so with a wrong `RAIN_TOPIC` the rain chart stays empty.

**TODO 3 — temperature URL**: complete the request inside `read_temperature()`.

Hint: the service answers `GET /zones/<zone>/temperature` with a JSON object; the reading is
in its `value` field, and the function must return it as a `float`.

**Done when**: the green banner appears, the temperature line moves,
and the rain line follows the rain service being switched on/off.

---

## Check the whole lab

```sh
docker compose up --build
```

Then open `http://localhost:8050`: HTTP, MQTT, fusion and decision panels green, every zone
card populated (soil ×3, air, VPD, sprinkler, rain), and the Assignment panel banner shown.