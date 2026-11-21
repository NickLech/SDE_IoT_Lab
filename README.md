# IoT Monitoring with SOA

Hands-on lab (≈60 min of examples + exercises) on service-oriented IoT monitoring, applied to the **irrigation of a field split into zones**.

A simulated field has 3 zones. In each zone, sensors measure the air and the soil and a sprinkler waters the crops.
A central node collects the data, fuses it and decides when to irrigate, and a dashboard shows what is going on.
Your job: complete a few small pieces of code and watch the dashboard come alive.

## Design choices

- **Simplified** architecture: sensors that are *polled* (pull, HTTP) and sensors that *push* (MQTT).
- **3 sensor types**: `temperature` and `humidity` (HTTP), `soil` (MQTT), plus a `sprinkler` actuator and a global `rain` simulator (MQTT).
- No database: the dashboard only keeps the current session's data.
- No external APIs.
- Protocols: HTTP and MQTT. Language: Python. Dashboard: Dash.
- Algorithms: **VPD** (Vapor Pressure Deficit) from air temperature and humidity, and **redundant fusion** of the 3 soil sensors of each zone (median, with outlier flagging).
- Everything runs in Docker containers: one per zone (6 independent processes each), plus broker, rain, central and dashboard.

## Quick start

Requirements: Docker + Docker Compose (Docker Desktop must be running). On Windows use Git Bash or WSL.

```bash
git clone <URL> && cd <repo>
docker compose up --build
```

Then open the dashboard at http://localhost:8050.

| What | Address |
|---|---|
| Dashboard | http://localhost:8050 |
| Central API | http://localhost:5100/zones |
| MQTT broker | `localhost:1883` |
| Temperature / humidity of zone1, zone2, zone3 | ports 5001/5002, 5011/5012, 5021/5022 |

Switch single devices on and off (to test failures) with `./ctl.sh`, for example `./ctl.sh zone2 stop soil-2`. See the cheat-sheet for all commands.

## How to work

1. Read `docs/architecture.md`: it describes the services and the contracts (endpoints, topics, payloads) that connect them.
2. Keep `docs/cheatsheet.md` open: commands, URLs and MQTT topics you need for the exercises.
3. Follow `docs/exercises.md`. After every change run `docker compose up --build` and check the dashboard.

| # | Topic | File |
|---|---|---|
| 1 | HTTP pull | `services/central/components/comms.py` → `poll_loop()` |
| 2 | MQTT push | `services/central/components/comms.py` → `on_connect()` |
| 3 | Data fusion (VPD) | `services/central/components/fusion.py` → `vpd_kpa()` |
| Assignment | Monitor one zone | `services/dashboard/assignment/monitor.py` |

## Repo layout

```
docker-compose.yml        orchestration (broker, 3 zones, rain, central, dashboard, monitor)
ctl.sh                    switch single devices on/off from the host
docs/
  architecture.md         services, contracts (endpoints, topics, payloads), simulation, decision rules
  cheatsheet.md           useful commands, URLs and MQTT topics
  exercises.md            the exercises
services/
  broker/                 Mosquitto configuration
  zone/                   zone image: Dockerfile + supervisord.conf (6 processes per zone)
  temperature/            temperature sensor (HTTP)
  humidity/               air-humidity sensor (HTTP)
  soil/                   soil-moisture sensor (MQTT)
  sprinkler/              actuator (MQTT)
  rain/                   global rain simulator (MQTT)
  central/                central node: pull + subscribe + fusion + decision + HTTP API
  dashboard/              Dash web UI
```

The `temperature`, `humidity`, `soil` and `sprinkler` folders are not separate containers: they are copied into the zone image and run as processes inside each `zoneN` container.