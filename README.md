# Global Overview Radar

Global Overview Radar is a full-stack system that combines:
- a Bug Resolution Radar for incident/ops visibility
- a Reputation Radar for public signals and market perception

It is designed to be configuration-driven, reproducible, and explainable by default.

---

## EN | What is inside

- Backend (Python + FastAPI)
  - `backend/bugresolutionradar`: ingestion of incidents (CSV/JSON/XLSX), consolidation, KPIs, API.
  - `backend/reputation`: multi-source collectors, normalization, sentiment, caching, API endpoints.
- Frontend (Next.js)
  - `frontend/brr-frontend`: UI + client logging pipeline.
- Data
  - `data/reputation/*.json`: business configurations (mergeable, multi-file).
  - `data/reputation_samples/*.json`: sample configs to copy from.
  - `data/cache/`: generated caches.

---

## ES | Que contiene

- Backend (Python + FastAPI)
  - `backend/bugresolutionradar`: ingesta de incidencias (CSV/JSON/XLSX), consolidacion, KPIs, API.
  - `backend/reputation`: collectors multi-fuente, normalizacion, sentimiento, cache, endpoints.
- Frontend (Next.js)
  - `frontend/brr-frontend`: UI + pipeline de logs del cliente.
- Data
  - `data/reputation/*.json`: configuracion de negocio (multi-archivo, mergeable).
  - `data/reputation_samples/*.json`: muestras para copiar.
  - `data/cache/`: caches generados.

---

## EN | Quick start (local)

Backend:
```bash
make ensure-backend
make env
make bugs-ingest
make reputation-ingest
make dev-back
```

Frontend:
```bash
make ensure-front
make dev-front
```

Open:
- API: http://127.0.0.1:8000
- Frontend: http://localhost:3000

---

## ES | Arranque rapido (local)

Backend:
```bash
make ensure-backend
make env
make bugs-ingest
make reputation-ingest
make dev-back
```

Frontend:
```bash
make ensure-front
make dev-front
```

Abrir:
- API: http://127.0.0.1:8000
- Frontend: http://localhost:3000

---

## EN | Configuration notes

- Backend env files are auto-created from examples if missing:
  - `backend/bugresolutionradar/.env` from `.env.example`
  - `backend/reputation/.env.reputation` from `.env.reputation.example`
- Frontend env file:
  - `frontend/brr-frontend/.env.local` from `.env.local.example`

Reputation config loading:
- `REPUTATION_CONFIG_PATH` points to a directory by default (`./data/reputation`).
- All `*.json` files in that directory are merged (load order: `config.json` first, then alphabetical).
- Merge rules:
  - dicts: deep merge
  - lists: concatenated with de-duplication
  - scalars: override only when incoming value is not empty

---

## ES | Notas de configuracion

- Los .env del backend se crean desde los ejemplos si faltan:
  - `backend/bugresolutionradar/.env` desde `.env.example`
  - `backend/reputation/.env.reputation` desde `.env.reputation.example`
- Frontend:
  - `frontend/brr-frontend/.env.local` desde `.env.local.example`

Carga de configuracion de reputacion:
- `REPUTATION_CONFIG_PATH` apunta a un directorio por defecto (`./data/reputation`).
- Se mezclan todos los `*.json` (orden: `config.json` primero, luego alfabetico).
- Reglas de merge:
  - diccionarios: merge profundo
  - listas: concatenadas con deduplicado
  - escalares: override solo si el valor entrante no esta vacio

---

## EN | Logging

BugResolutionRadar:
- `LOG_ENABLED`, `LOG_TO_FILE`, `LOG_FILE_NAME`, `LOG_DEBUG`

Reputation:
- `REPUTATION_LOG_ENABLED`, `REPUTATION_LOG_TO_FILE`, `REPUTATION_LOG_FILE_NAME`, `REPUTATION_LOG_DEBUG`

Frontend:
- `NEXT_PUBLIC_LOG_ENABLED`, `NEXT_PUBLIC_LOG_TO_FILE`, `NEXT_PUBLIC_LOG_DEBUG`, `LOG_FILE_NAME`
- If `NEXT_PUBLIC_LOG_TO_FILE=true`, logs are batched to `/api/log` and written to `./logs/`.

All log files live under `./logs/` (ignored by git).

---

## Documentation

- Architecture: `docs/ARCHITECTURE.md`
- System guide: `docs/DOCUMENTACION.md`
- Data contracts: `docs/DATA_CONTRACTS.md`
- Signals: `docs/SIGNALS_CATALOG.md`
- Metrics: `docs/METRICS_AND_SCORES.md`
- Governance & security: `docs/GOVERNANCE_SECURITY.md`
- Extending: `docs/EXTENDING_THE_SYSTEM.md`
- File index: `docs/FILES.md`
- Decision log: `docs/DECISION_LOG.md`

---

## License

See `LICENSE`.
