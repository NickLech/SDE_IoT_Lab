FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .
RUN useradd --system --no-create-home sensor
USER sensor

EXPOSE 5001
CMD ["python", "app.py"]