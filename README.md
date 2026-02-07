# Global Overview Radar

[![Test back](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/backend.yml/badge.svg?branch=develop&label=Test%20back)](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/backend.yml)
[![Test front](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/frontend.yml/badge.svg?branch=develop&label=Test%20front)](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/frontend.yml)
[![typecheck](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/typecheck.yml/badge.svg?branch=develop)](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/typecheck.yml)
[![format](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/format.yml/badge.svg?branch=develop)](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/format.yml)
[![deploy_hooks](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/deploy_hooks.yml/badge.svg?branch=develop)](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/deploy_hooks.yml)
[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-2ea44f.svg)](https://github.com/sponsors/felixdelbarrio)
[![Donate](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/felixdelbarrio)

Global Overview Radar is a full-stack system for reputation signals and market perception.
It is designed to be configuration-driven, reproducible, and explainable by default.
The product focus is **sentiment-first** and exclusively reputation-oriented.

---

## EN | What is inside

- Backend (Python + FastAPI)
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
  - `backend/reputation`: collectors multi-fuente, normalizacion, sentimiento, cache, endpoints.
- Frontend (Next.js)
  - `frontend/brr-frontend`: UI + pipeline de logs del cliente.
- Data
  - `data/reputation/*.json`: configuracion de negocio (multi-archivo, mergeable).
  - `data/reputation_samples/*.json`: muestras para copiar.
  - `data/cache/`: caches generados.

---

## EN | Current state (product)

- **Dashboard (/) = sentiment-first.** It shows the sentiment trend and latest mentions.
- **Sentiment tab** includes filters + full listing and CSV downloads (chart + grid).
- **Ingest Center** (top-right) launches reputation ingests with live progress, without blocking other UI.
- **Noise control is strict by design:** actor presence is required for selected sources, actor must appear in text, guard actors block ambiguous context, and actor/geo allowlists discard mismatched items.

## ES | Estado actual (producto)

- **Dashboard (/) = sentimiento primero.** Muestra la tendencia de sentimiento y las ultimas menciones.
- **Pestana Sentimiento** con filtros + listado completo y descargas CSV (grafico + grid).
- **Centro de ingesta** (arriba a la derecha) permite lanzar ingestas de reputacion con progreso en vivo.
- **Control de ruido estricto:** requerimos actor para fuentes sensibles, el actor debe aparecer en el texto, usamos guard actors para evitar ambiguedad y descartamos items fuera de su geo permitido.

## EN | Rationale

- The main product value is **sentiment visibility** with minimal noise.
- The platform focuses exclusively on reputation signals and perception.
- Strict ingestion filters keep the customer experience clean and trustworthy.

## ES | Racional

- El valor principal es **visibilidad de sentimiento** con el menor ruido posible.
- La plataforma se centra exclusivamente en senales de reputacion y percepcion.
- Filtros estrictos en ingesta mantienen la experiencia limpia y confiable.

---

## EN | Quick start (local)

Backend:
```bash
make ensure-backend
make env
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
- Production: https://global-overview-radar.vercel.app

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
- Produccion: https://global-overview-radar.vercel.app

Modo produccion (frontend):
```bash
make build-front
make start-front
```

---

## EN | Configuration notes

- Backend env files are auto-created from examples if missing:
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

Noise control (reputation ingestion):
- `require_actor_sources` enforces actor presence for specific sources (e.g. news/forums).
- Actor must appear in title/text when required.
- Guard actors + geo allowlists drop mismatched items before they reach the cache.
- `require_context_sources` forces banking context terms for sensitive sources (e.g. downdetector RSS).
- Per-source RSS queries can be tightened with `rss_query_segment_mode`.

---

## ES | Notas de configuracion

- Los .env del backend se crean desde los ejemplos si faltan:
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

Control de ruido (ingesta reputacion):
- `require_actor_sources` obliga presencia de actor en fuentes sensibles (news/forums).
- El actor debe aparecer en titulo/texto cuando aplica.
- Guard actors + allowlist por geo descartan items fuera de contexto antes del cache.
- `require_context_sources` fuerza contexto bancario en fuentes sensibles (ej. RSS de downdetector).
- Las RSS por fuente pueden endurecerse con `rss_query_segment_mode`.

---

## EN | Logging

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

## EN | Support the author

If this project helps you, you can support its development:

[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-2ea44f.svg)](https://github.com/sponsors/felixdelbarrio)
[![Donate](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/felixdelbarrio)

---

## ES | Apoya al autor

Si este proyecto te resulta util, puedes apoyar su desarrollo:

[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-2ea44f.svg)](https://github.com/sponsors/felixdelbarrio)
[![Donate](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/felixdelbarrio)

---

## License

See `LICENSE`.
