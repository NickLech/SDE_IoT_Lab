# IoT Monitoring with SOA

Hands-on lab (≈60 min of examples + exercises) on service-oriented IoT monitoring, applied to **irrigation of a field split into zones**.

## Design choices (from the meetings with the professors)

- **Simplified** architecture: sensors that are *polled* (pull, HTTP) and sensors that *push* (MQTT).
- **At most 3 sensor container types**: `temperature`, `humidity`, `soil`.
- No database: the dashboard only keeps the current session's data.
- No external APIs (no OpenWeather).
- Protocols: HTTP and MQTT. Language: Python. Dashboard: Dash.
- Algorithms: VPD (Vapor Pressure Deficit) + redundant fusion of the soil sensors (weighted average / Kalman).
- The examples **complete the dashboard**: panels start red and turn green as each exercise is completed.
- Automatic exercise validator: not required (optional, see `TASKS.md`).


## Repo layout

```
docker-compose.yml        orchestration (broker, sensors, actuator, central, dashboard)
docs/
  architecture.md         details and contracts (endpoints, topics, payloads)
  cheatsheet.md           usefull commands for testing
  exercises.md            proposed exercise
services/
  temperature/            temperature sensors (HTTP)
  humidity/               air-humidity sensors (HTTP)
  soil/                   soil-moisture sensors (MQTT)
  sprinkler/              actuator (MQTT subscribe)
  central/                central node: pull + subscribe + fusion + decision
  dashboard/              Dash
TASKS.md                  backlog split by area
```

## How to work

Read `docs/architecture.md`: the contracts are what lets us work in parallel --> pick a task from `TASKS.md` and open a branch `featureX/`.
