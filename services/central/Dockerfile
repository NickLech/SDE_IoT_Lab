FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .
COPY components/ ./components/
RUN useradd --system --no-create-home sensor
USER sensor

EXPOSE 5000
CMD ["python", "app.py"]
