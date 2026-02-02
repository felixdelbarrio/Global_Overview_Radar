# FILES.md (EN / ES)

High-signal repository index.

Back to root: `../README.md`

---

## EN | Top-level

- `backend/` — Python backend services
  - `bugresolutionradar/` — incident ingestion + consolidation + API
  - `reputation/` — public signal collectors + reputation cache
- `frontend/brr-frontend/` — Next.js UI
- `data/` — configs, caches, assets
  - `reputation/` — active business configs (mergeable)
  - `reputation_samples/` — sample configs to copy from
  - `cache/` — generated caches
- `docs/` — technical documentation
- `tests/` — backend/frontend tests
- `Makefile` — common dev commands

---

## EN | Backend highlights

- `backend/bugresolutionradar/adapters/` — CSV/JSON/XLSX connectors
- `backend/bugresolutionradar/services/` — ingest + consolidate + reporting
- `backend/bugresolutionradar/api/` — FastAPI routers
- `backend/reputation/collectors/` — per-source collectors
- `backend/reputation/services/` — ingest + sentiment + merging
- `backend/*/logging_utils.py` — configurable logging with hot reload

## EN | Frontend highlights

- `frontend/brr-frontend/src/components/SentimentView.tsx` — unified Dashboard/Sentiment view
- `frontend/brr-frontend/src/components/Shell.tsx` — navigation (configurable via reputation meta)

---

## ES | Nivel raiz

- `backend/` — servicios backend en Python
  - `bugresolutionradar/` — ingesta de incidencias + consolidacion + API
  - `reputation/` — collectors de reputacion + cache
- `frontend/brr-frontend/` — UI en Next.js
- `data/` — configs, caches, assets
  - `reputation/` — configs activas (mergeables)
  - `reputation_samples/` — muestras
  - `cache/` — caches generados
- `docs/` — documentacion tecnica
- `tests/` — tests
- `Makefile` — comandos comunes

---

## ES | Backend (destacados)

- `backend/bugresolutionradar/adapters/` — conectores CSV/JSON/XLSX
- `backend/bugresolutionradar/services/` — ingesta + consolidacion + reporting
- `backend/bugresolutionradar/api/` — routers FastAPI
- `backend/reputation/collectors/` — collectors por fuente
- `backend/reputation/services/` — ingesta + sentimiento + merge
- `backend/*/logging_utils.py` — logging configurable con hot reload

## ES | Frontend (destacados)

- `frontend/brr-frontend/src/components/SentimentView.tsx` — vista unificada Dashboard/Sentimiento
- `frontend/brr-frontend/src/components/Shell.tsx` — navegacion (configurable via reputation meta)
