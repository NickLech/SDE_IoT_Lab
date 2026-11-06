# IoT Monitoring with SOA

Laboratorio pratico (≈60 min di esempi + esercizi) su monitoraggio IoT service-oriented applicato all'**irrigazione di un campo diviso in zone**.

## Scelte di progetto (dai colloqui con i professori)

- Architettura **semplificata**: sensori che *vengono interrogati* (pull, HTTP) e sensori che *inviano* (push, MQTT).
- **Massimo 3 tipi di container sensore** diversi: `temperature`, `humidity`, `soil`.
- Nessun database: la dashboard tiene solo i dati della sessione corrente.
- Nessuna API esterna (niente OpenWeather).
- Protocolli: HTTP e MQTT. Linguaggio: Python. Dashboard: Dash.
- Algoritmi: VPD (Vapor Pressure Deficit) + fusione ridondante dei sensori del suolo (media pesata / Kalman).
- Gli esempi **completano la dashboard**: all'inizio i pannelli sono rossi, a ogni esercizio completato diventano verdi.
- Validatore automatico degli esercizi: non richiesto (opzionale, vedi `TASKS.md`).


## Struttura del repo

```
docker-compose.yml        orchestrazione (broker, sensori, attuatore, central, dashboard)
docs/
  architecture.md         dettagli e contratti (endpoint, topic, payload)
services/
  temperature/            sensori temperatura (HTTP)
  humidity/               sensori umidità aria (HTTP)
  soil/                   sensori umidità suolo (MQTT)
  sprinkler/              attuatore (MQTT subscribe)
  central/                nodo centrale: pull + subscribe + fusione + decisione
  dashboard/              Dash
TASKS.md                  backlog suddiviso per area
```

## Come lavorare

Leggere `docs/architecture.md`: i contratti sono la base per lavorare in parallelo --> scegliere task da `TASKS.md` e aprire un branch `featureX/`.
