# syntax=docker/dockerfile:1

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
COPY backend ./backend
COPY data ./data

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e backend \
    && (cp backend/reputation/.env.reputation.example backend/reputation/.env.reputation 2>/dev/null || true)

EXPOSE 8080

CMD ["sh", "-c", "uvicorn reputation.api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
