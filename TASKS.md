# TASKS — Backlog del laboratorio

Legenda: **[P]** parallelizzabile subito dopo T0 · **Dip.** = dipendenze · **Done** = criterio di completamento.
Convenzione branch: `feat/<area>-<nome>`; un task = una PR con almeno una review.
Le slide sono escluse (le prepariamo in autonomia).

## Area 0 — Fondamenta (da fare per primi, insieme)

### T0.1 Validare i contratti in `docs/architecture.md`
Rivedere endpoint, topic, payload, porte, nomi zone/sensori; decidere punti aperti (API `GET /state` del central per la dashboard; hotkey di guasto via `POST /debug/fault` / topic debug).
**Done**: contratti approvati da tutti e congelati (modifiche solo via PR).

### T0.2 Libreria/convenzioni comuni
Decidere framework HTTP (Flask vs FastAPI), versione Python, formato timestamp (ISO 8601 UTC), logging, struttura Dockerfile standard, `requirements.txt` per servizio.
**Done**: template Dockerfile + guida in `docs/` o nel README.

## Area SENS — Sensori simulati (3 container)

### T1.1 Simulatore generico di segnale **[P]** — Dip. T0.2
Modulo riutilizzabile: andamento base (giornaliero/deriva) + rumore gaussiano (std configurabile) + spike/outlier con probabilità + modalità "guasto" (valori folli o bloccati).
**Done**: test unitari su statistiche del rumore; spike e guasto attivabili da parametro.

### T1.2 Servizio `temperature` (HTTP) **[P]** — Dip. T1.1
3 sensori (zone), endpoint `/zones/<z>/temperature`, `/health`, `/debug/fault`, 404 su zona sconosciuta, Dockerfile.
**Done**: `curl` restituisce JSON conforme al contratto; container avviabile da compose.

### T1.3 Servizio `humidity` (HTTP) **[P]** — Dip. T1.1
Come T1.2 ma con umidità anticorrelata alla temperatura per risultare realistica col VPD.
**Done**: idem T1.2; valori in range 0–100.

### T1.4 Servizio `soil` (MQTT push) **[P]** — Dip. T1.1, T2.1
> **Prima versione fatta** (`services/soil`, testata con `tests/smoke_mqtt.py`). Resta da fare: estrarre il simulatore in un modulo condiviso con T1.1 e provarlo con Docker/Mosquitto reali.
9 sensori (3 per zona), pubblicazione periodica su `field/<z>/soil/<id>`; il suolo si asciuga nel tempo con tasso per zona; sottoscrive stato sprinkler e risale quando è `on`; guasto via topic debug.
**Done**: `mosquitto_sub` mostra 9 flussi; l'umidità reagisce allo sprinkler.

## Area INFRA — Broker, attuatore, orchestrazione

### T2.1 Broker Mosquitto e compose funzionante **[P]** — Dip. T0.1
> **Parte MQTT fatta** (broker con healthcheck, soil, sprinkler, profilo `debug` con monitor). Resta: attivare i servizi `wip` quando esistono e verificare su macchina pulita (Linux/Mac/Windows).
Verificare `docker-compose.yml`, rete, healthcheck, `depends_on`, porte; aggiungere `.env` d'esempio.
**Done**: `docker compose up --build` parte da zero su macchina pulita (Linux/Mac/Windows).

### T2.2 Servizio `sprinkler` **[P]** — Dip. T0.1, T2.1
> **Fatto** (`services/sprinkler`): QoS 1, stato retained, Last Will, auto-off, idempotenza, comandi non validi ignorati. Verificato con `tests/smoke_mqtt.py` e con `kill -9`.
Sottoscrizione comandi QoS 1, stato **retained**, Last Will `offline`, spegnimento automatico dopo `duration_s`, gestione comando duplicato (idempotenza).
**Done**: pubblicando un comando lo stato cambia e un nuovo subscriber riceve l'ultimo stato retained; killando il container compare `offline`.

## Area CORE — Nodo centrale (versione di riferimento completa + versione con TODO)

### T3.1 Pull HTTP (soluzione completa) **[P]** — Dip. T1.2, T1.3
`pull.py`: polling per zona, timeout, retry con backoff, marcatura sensore non disponibile, contatore richieste inutili.
**Done**: fermando/riavviando un sensore il central non crasha e riprende.

### T3.2 Subscribe MQTT (soluzione completa) **[P]** — Dip. T1.4
`subscribe.py`: wildcard `field/+/soil/+`, `on_message`, validazione payload, ultima lettura per sensore, riconnessione.
**Done**: 9 sensori visibili nello stato interno.

### T3.3 Fusione dati — livello 0 e ridondante — Dip. T3.2
Scarto letture fuori range, scarto outlier (distanza dalla mediana > soglia), stima unica per zona (media pesata o Kalman), registrazione dei sensori scartati.
**Done**: con un sensore in guasto la stima di zona resta corretta e il sensore risulta scartato.

### T3.4 Fusione cooperativa VPD — Dip. T3.1
Calcolo VPD da temperatura e umidità aria (formula in `architecture.md`).
**Done**: test unitari con valori noti.

### T3.5 Decisione di irrigazione (soluzione completa) — Dip. T3.3, T3.4, T2.2
`decide_irrigation(zone_state)`: soglie su umidità fusa + VPD, durata proporzionale al deficit, isteresi per evitare oscillazioni, pubblicazione comando MQTT.
**Done**: le tre zone restano in banda per ≥ 10 minuti di simulazione.

### T3.6 API di stato `GET /state` — Dip. T3.1, T3.2
Stato in memoria: letture grezze, stime fuse, VPD, decisioni, sprinkler, sensori scartati, flag esercizi (`http_pull`, `mqtt_push`, `decision`), finestra storica recente.
**Done**: JSON documentato in `architecture.md`.

### T3.7 Derivare la versione "con TODO" per i partecipanti — Dip. T3.1, T3.2, T3.5
Estrarre `pull.py`, `subscribe.py`, `decision.py` con TODO guidati e commenti-suggerimento; i flag esercizio restano falsi finché i TODO non funzionano. Tenere la soluzione completa in un branch/cartella `solutions/`.
**Done**: stack con TODO parte, pannelli rossi; applicando la soluzione diventano verdi.

## Area DASH — Dashboard (Dash)

### T4.1 Scheletro e polling dello stato **[P]** — Dip. T0.1
App Dash, `dcc.Interval`, client verso `GET /state` (mock se il central non è pronto).
**Done**: pagina si carica e mostra dati mock.

### T4.2 Mappa del campo e stato sprinkler — Dip. T4.1
3 zone con colore per umidità fusa, icona sprinkler on/off.
**Done**: cambia in tempo reale con i dati.

### T4.3 Grafici per zona: grezzo vs fuso — Dip. T4.1
Serie dei 3 sensori suolo + stima fusa, temperatura/umidità aria/VPD; evidenza sensori scartati.
**Done**: un sensore in guasto è riconoscibile a colpo d'occhio.

### T4.4 Pannello stato esercizi (rosso → verde) — Dip. T3.6
Indicatori per HTTP pull, MQTT push, decisione; transizione visibile durante gli esempi.
**Done**: i flag del central cambiano colore senza ricaricare.

### T4.5 Controllo guasti (hotkey/pulsante) — Dip. T1.2, T1.4
Pulsante in dashboard per far impazzire un sensore e ripristinarlo.
**Done**: dimostrazione dell'esempio di fusione con scarto del sensore anomalo.

## Area DOC — Materiale per i partecipanti

### T5.1 Cheat-sheet definitivo — Dip. T2.1
Aggiornare `docs/cheatsheet.md` con comandi verificati su Linux/Mac/Windows e troubleshooting reale.
**Done**: una persona esterna avvia lo stack seguendo solo il cheat-sheet.

### T5.2 Testo esercizi definitivo — Dip. T3.7
Rifinire `docs/exercises.md`: tempi, suggerimenti graduali, risposte attese, soluzioni in `solutions/`.
**Done**: prova a freddo di un membro non coinvolto, tempi nei 60 min.

### T5.3 Scaletta dei 60 min (esempi + esercizi) — Dip. T5.2
Alternanza spiegazione/esercizio, momenti in cui la dashboard passa da rosso a verde, pausa prima della data fusion.
**Done**: scaletta con minuti per blocco.

## Area QA — Prove generali

### T6.1 Test dall'inizio alla fine su macchina pulita — Dip. tutto il resto
Clone → `docker compose up` → esercizi 1-2-3 → taratura finale.
**Done**: lista dei problemi aperta e risolta.

### T6.2 Prova generale cronometrata — Dip. T6.1
Un membro conduce, gli altri fanno i partecipanti.
**Done**: durata ≤ 60 min, feedback raccolto.

### T6.3 (opzionale) Validatore automatico della taratura — Dip. T3.5
Script che passa se l'umidità resta in banda per un intervallo. Non richiesto dai professori, ma utile.

## Proposta di suddivisione per 3 persone
- Persona A: T0.2, T1.1–T1.4 (sensori), T4.5
- Persona B: T2.1, T2.2, T3.1–T3.7 (core e fusione)
- Persona C: T4.1–T4.4 (dashboard), T5.1–T5.3 (materiale)
Tutti: T0.1, T6.1, T6.2.
