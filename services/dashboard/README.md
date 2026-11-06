# services/dashboard

Dashboard Dash (porta 8050). Legge `GET /state` dal central a intervalli (`dcc.Interval`).

Pannelli: mappa del campo (3 zone), grafici per zona (grezzo vs fuso), stato sprinkler, **stato esercizi** (rosso/verde), evidenza sensori scartati come outlier.

Nessun DB: lo storico è quello restituito dal central al caricamento della pagina (finestra in memoria).
