FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .
COPY assets assets
RUN useradd --system --no-create-home dash
USER dash

EXPOSE 8050
CMD ["python", "app.py"]
