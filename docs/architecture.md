# Architettura e contratti

Il campo ha **3 zone** (`zone1`, `zone2`, `zone3`). Ogni zona ha:
- 1 sensore temperatura, 1 sensore umidità aria (pull HTTP)
- 3 sensori umidità suolo ridondanti (push MQTT)
- 1 sprinkler

## Servizi

| Servizio | Ruolo | Comunicazione |
|---|---|---|
| `broker` | Mosquitto | MQTT 1883 |
| `temperature` | simula 3 sensori (uno per zona) | espone HTTP (porta 5001) |
| `humidity` | simula 3 sensori (uno per zona) | espone HTTP (porta 5002) |
| `soil` | simula 9 sensori (3 per zona) | pubblica su MQTT |
| `sprinkler` | attuatore, 3 valvole | sottoscrive comandi MQTT, pubblica stato |
| `central` | pull + subscribe, fusione, decisione | HTTP client, MQTT client |
| `dashboard` | visualizza dati e stato esercizi | legge dal central (vedi sotto) |

> Dashboard ↔ central: il central espone una piccola API HTTP (`GET /state`) con lo stato corrente (nessun DB, solo memoria). Da confermare nei task.

## Contratti HTTP (pull)

`GET /health` → `{"status":"ok"}`

`GET /zones/<zone>/temperature` (servizio temperature) →
```json
{"zone":"zone1","sensor_id":"temp-zone1","value":24.3,"unit":"C","timestamp":"2026-01-01T10:00:00Z"}
```

`GET /zones/<zone>/humidity` (servizio humidity) →
```json
{"zone":"zone1","sensor_id":"hum-zone1","value":55.2,"unit":"%","timestamp":"2026-01-01T10:00:00Z"}
```

Errori: `404` zona inesistente. Container fermato → il client riceve errore di connessione (da gestire, esercizio 1).

## Contratti MQTT (push)

Telemetria suolo, QoS 0, non retained:
`field/<zone>/soil/<sensor_id>` →
```json
{"zone":"zone1","sensor_id":"soil-zone1-1","value":31.5,"unit":"%","timestamp":"2026-01-01T10:00:00Z"}
```
Sottoscrizione con wildcard (esercizio 2): `field/+/soil/+`.

Comando sprinkler, QoS 1, **non retained**:
`field/<zone>/sprinkler/cmd` → `{"action":"on","duration_s":30}` oppure `{"action":"off"}`

Stato sprinkler, QoS 1, **retained**:
`field/<zone>/sprinkler/state` → `{"state":"on|off","timestamp":"..."}`

Liveness: Last Will su `field/<zone>/sprinkler/state` = `{"state":"offline"}`.

## Simulazione sensori

- Valore = andamento base + rumore gaussiano (std configurabile via env `NOISE_STD`).
- Spike/outlier occasionali (probabilità `SPIKE_PROB`).
- Hotkey/endpoint di debug: `POST /debug/fault` (HTTP) o topic `debug/<sensor_id>/fault` (MQTT) fa impazzire un sensore; usato nell'esempio sulla fusione.
- Il suolo si asciuga col tempo e risale quando lo sprinkler della zona è acceso (il simulatore soil ascolta lo stato dello sprinkler).

## Data fusion

1. **Livello 0**: scarto letture impossibili (fuori range fisico).
2. **Ridondante (suolo)**: 3 sensori per zona → un'unica stima (media pesata o Kalman) con scarto outlier tramite soglia sulla distanza dalla mediana.
3. **Cooperativo**: temperatura + umidità aria → **VPD**.
4. **Feature → decisione**: stima suolo + VPD → `decide_irrigation(zone_state)` (feature in, decision out).

VPD (kPa): `es = 0.6108 * exp(17.27*T/(T+237.3))`, `VPD = es * (1 - RH/100)`.

## Stato degli esercizi nella dashboard

Il central espone per ogni esercizio un flag (`http_pull`, `mqtt_push`, `decision`). Pannello **rosso** finché la parte TODO non funziona, **verde** quando i dati/azioni arrivano.
