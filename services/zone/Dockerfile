# Immagine di zona. Build context = radice del progetto (vedi docker-compose.yml),
# così riusa gli app.py delle cartelle soil/ sprinkler/ temperature/ humidity/.
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

# stessi utenti dei Dockerfile originali: sensori = sensor, attuatore = actuator
# (supervisord resta root solo per poter far partire ogni processo col suo utente)
RUN useradd --system --no-create-home sensor \
    && useradd --system --no-create-home actuator \
    && printf '#!/bin/sh\nexec supervisorctl -c /etc/supervisord.conf "$@"\n' > /usr/local/bin/zonectl \
    && chmod +x /usr/local/bin/zonectl

EXPOSE 5001 5002
CMD ["supervisord", "-c", "/etc/supervisord.conf"]
