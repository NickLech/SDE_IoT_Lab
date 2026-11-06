# services/temperature

Container sensore **temperatura**. Simula 3 sensori (uno per zona), espone HTTP su porta 5001 (**pull**).

Contratto: vedi `docs/architecture.md` (`GET /zones/<zone>/temperature`, `GET /health`, `POST /debug/fault`).

Da implementare (vedi `TASKS.md`, area SENS): app Flask/FastAPI, simulatore con andamento giornaliero + rumore gaussiano + spike, Dockerfile, requirements.txt.
