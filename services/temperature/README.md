# services/temperature

**Temperature** sensor container. Simulates 3 sensors (one per zone), serves HTTP on port 5001 (**pull**).

Contract: see `docs/architecture.md` (`GET /zones/<zone>/temperature`, `GET /health`, `POST /debug/fault`).

To do (see `TASKS.md`, area SENS): Flask/FastAPI app, simulator with daily trend + Gaussian noise + spikes, Dockerfile, requirements.txt.
