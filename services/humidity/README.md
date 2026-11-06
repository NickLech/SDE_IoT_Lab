# services/humidity

Container sensore **umidità dell'aria**. Simula 3 sensori (uno per zona), espone HTTP su porta 5002 (**pull**).

Contratto: `GET /zones/<zone>/humidity`, `GET /health`, `POST /debug/fault` (vedi `docs/architecture.md`).

Nota: umidità relativa correlata (inversamente) alla temperatura, così il VPD risulta realistico.
