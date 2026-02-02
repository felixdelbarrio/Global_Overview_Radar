# Global Overview Radar

Global Overview Radar is a full-stack system that combines:
- a Bug Resolution Radar for incident/ops visibility
- a Reputation Radar for public signals and market perception

It is designed to be configuration-driven, reproducible, and explainable by default.
The current product focus is **sentiment-first** with incidents as a complementary layer.

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

## EN | Current state (product)

- **Dashboard (/) = sentiment-first.** It shows sentiment trend + incident trend (when enabled) and the latest 20 mixed mentions.
- **Sentiment tab** includes filters + full listing and CSV downloads (chart + grid).
- **Incidencias** and **Ops Executive** remain available but can be disabled per business config for non-IT actors.
- **Noise control is strict by design:** actor presence is required for selected sources, actor must appear in text, guard actors block ambiguous context, and actor/geo allowlists discard mismatched items.

## ES | Estado actual (producto)

- **Dashboard (/) = sentimiento primero.** Muestra tendencia de sentimiento + incidencias (si estan habilitadas) y las ultimas 20 menciones mezcladas.
- **Pestana Sentimiento** con filtros + listado completo y descargas CSV (grafico + grid).
- **Incidencias** y **Ops Executive** siguen disponibles pero pueden deshabilitarse por config cuando el actor no es tecnologico.
- **Control de ruido estricto:** requerimos actor para fuentes sensibles, el actor debe aparecer en el texto, usamos guard actors para evitar ambiguedad y descartamos items fuera de su geo permitido.

## EN | Rationale

- The main product value is **sentiment visibility** with minimal noise.
- Incidents are meaningful only for certain actors; therefore they are **configurable** and secondary.
- Strict ingestion filters keep the customer experience clean and trustworthy.

## ES | Racional

- El valor principal es **visibilidad de sentimiento** con el menor ruido posible.
- Incidencias solo aportan valor en actores IT/ops; por eso son **configurables** y secundarias.
- Filtros estrictos en ingesta mantienen la experiencia limpia y confiable.

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

Production start (frontend):
```bash
make build-front
make start-front
```

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

Modo produccion (frontend):
```bash
make build-front
make start-front
```

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

UI toggles (per config):
- `ui.incidents_enabled` and `ui.ops_enabled` allow hiding Incidents/Ops and turning the dashboard into sentiment-only.

Noise control (reputation ingestion):
- `require_actor_sources` enforces actor presence for specific sources (e.g. news/forums).
- Actor must appear in title/text when required.
- Guard actors + geo allowlists drop mismatched items before they reach the cache.

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

Toggles de UI (por config):
- `ui.incidents_enabled` y `ui.ops_enabled` permiten ocultar Incidencias/Ops y dejar el dashboard solo con sentimiento.

Control de ruido (ingesta reputacion):
- `require_actor_sources` obliga presencia de actor en fuentes sensibles (news/forums).
- El actor debe aparecer en titulo/texto cuando aplica.
- Guard actors + allowlist por geo descartan items fuera de contexto antes del cache.

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
