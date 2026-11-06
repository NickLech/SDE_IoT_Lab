# services/central

Nodo centrale (porta 5000).

Moduli previsti:
- `pull.py` — polling HTTP di temperature/humidity. **ESERCIZIO 1** (gestione errori, richieste inutili).
- `subscribe.py` — client MQTT, `on_message` per `field/+/soil/+`. **ESERCIZIO 2**.
- `fusion.py` — livello 0, fusione ridondante suolo (media pesata/Kalman), scarto outlier, VPD.
- `decision.py` — `decide_irrigation(zone_state)`. **ESERCIZIO 3 / 4** (con TODO).
- `api.py` — `GET /state` (stato in memoria per la dashboard, inclusi flag esercizi).
- `main.py` — avvio dei thread.

Nessun database: tutto in memoria.
