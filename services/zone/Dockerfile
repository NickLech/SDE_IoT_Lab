# Per-zone image. Build context is the project root (see docker-compose.yml),
# so it can reuse the app.py of each service folder.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY services/zone/requirements.txt .
RUN pip install -r requirements.txt

COPY services/soil/app.py ./soil/app.py
COPY services/temperature/app.py ./temperature/app.py
COPY services/humidity/app.py ./humidity/app.py
COPY services/sprinkler/app.py ./sprinkler/app.py
COPY services/zone/supervisord.conf /etc/supervisord.conf

# Sensors run as "sensor", the actuator as "actuator"; supervisord stays root
# only to start each process under its own user.
# zonectl is a supervisorctl wrapper (used by ctl.sh).
RUN useradd --system --no-create-home sensor \
    && useradd --system --no-create-home actuator \
    && printf '#!/bin/sh\nexec supervisorctl -c /etc/supervisord.conf "$@"\n' > /usr/local/bin/zonectl \
    && chmod +x /usr/local/bin/zonectl

EXPOSE 5001 5002
CMD ["supervisord", "-c", "/etc/supervisord.conf"]