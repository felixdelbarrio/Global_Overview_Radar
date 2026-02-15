FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# --- App code ---
COPY backend/ /app/backend/

# --- Template/data assets needed at runtime ---
# These folders live at repo root: ./data/...
# We copy them into /app/data so the backend can read them.
COPY data/reputation_samples/ /app/data/reputation_samples/
COPY data/reputation_llm_samples/ /app/data/reputation_llm_samples/

EXPOSE 8080
CMD ["python","-m","uvicorn","reputation.api.main:app","--host","0.0.0.0","--port","8080"]