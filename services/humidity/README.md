# services/humidity

**Air-humidity** sensor container. Simulates 3 sensors (one per zone), serves HTTP on port 5002 (**pull**).

Contract: `GET /zones/<zone>/humidity`, `GET /health`, `POST /debug/fault` (see `docs/architecture.md`).

Note: relative humidity is inversely correlated with temperature, so the VPD looks realistic.
