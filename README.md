# Global Overview Radar

[![CI / test_backend](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/backend.yml/badge.svg?branch=main)](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/backend.yml)
[![CI / test_frontend](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/frontend.yml/badge.svg?branch=main)](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/frontend.yml)
[![typecheck](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/typecheck.yml/badge.svg?branch=main)](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/typecheck.yml)
[![deploy_hooks](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/deploy_hooks.yml/badge.svg?branch=main)](https://github.com/felixdelbarrio/Global_Overview_Radar/actions/workflows/deploy_hooks.yml)

Global Overview Radar convierte señales publicas en **inteligencia accionable de reputacion y sentimiento**. Es un radar always-on: orquesta multiples fuentes, normaliza actores y geografias, enriquece con sentimiento y rating, y lo transforma en un panel que revela cambios reales, compara competidores con precision y activa alertas de riesgo antes de que escalen.

---

## EN | What it does

- Ingests multi-source public signals (news, reviews, forums, social, app stores).
- Normalizes entities, geographies, and time windows to compare like with like.
- Enriches every mention with sentiment and rating signals, ready to serve fast.
- Powers a high-signal dashboard that surfaces trends, competitors, and early shifts.

---

## ES | Qué hace

- Ingesta señales públicas multi-fuente (news, reviews, foros, social, app stores).
- Normaliza entidades, geografías y ventanas temporales para comparar con precision.
- Enriquece cada mencion con sentimiento y ratings, listo para servir rapido.
- Ofrece un dashboard que destapa tendencias, competidores y cambios tempranos.

---

## EN | How it works

- **Collect**: connectors gather raw mentions and ratings.
- **Normalize**: actor aliases and geo mappings unify the data.
- **Enrich**: sentiment + aspect + rating signals are computed.
- **Cache**: fast JSON snapshots feed the UI.
- **Analyze**: the frontend surfaces patterns, deltas, and rankings.

---

## ES | Cómo funciona

- **Recolecta**: conectores extraen menciones y ratings.
- **Normaliza**: alias de actores y geos unifican los datos.
- **Enriquece**: se calculan sentimiento, aspectos y señales de rating.
- **Cachea**: snapshots JSON rapidos alimentan la UI.
- **Analiza**: el frontend revela patrones, cambios y rankings.

---

## EN | What is inside

- Backend (Python + FastAPI)
  - `backend/reputation`: collectors, normalization, sentiment, caching, API endpoints.
- Frontend (Next.js)
  - `frontend/brr-frontend`: sentiment dashboard and analysis.
- Data
  - `data/reputation/*.json`: business configurations (mergeable, multi‑file).
  - `data/reputation_samples/*.json`: sample configs to copy from.
  - `data/cache/`: generated caches.

---

## ES | Qué contiene

- Backend (Python + FastAPI)
  - `backend/reputation`: colectores, normalización, sentimiento, cache, endpoints.
- Frontend (Next.js)
  - `frontend/brr-frontend`: dashboard y análisis de sentimiento.
- Data
  - `data/reputation/*.json`: configuración de negocio (multi‑archivo, mergeable).
  - `data/reputation_samples/*.json`: muestras para copiar.
  - `data/cache/`: caches generados.

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

Production start (frontend):
```bash
make build-front
make start-front
```

---

## ES | Arranque rápido (local)

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

Modo producción (frontend):
```bash
make build-front
make start-front
```

---

## EN | Configuration notes

- Backend env file is auto‑created from example if missing:
  - `backend/reputation/.env.reputation` from `.env.reputation.example`
- Frontend env file:
  - `frontend/brr-frontend/.env.local` from `.env.local.example`

Reputation config loading:
- `REPUTATION_CONFIG_PATH` points to a directory by default (`./data/reputation`).
- All `*.json` files in that directory are merged (load order: `config.json` first, then alphabetical).

---

## ES | Notas de configuración

- El .env del backend se crea desde el ejemplo si falta:
  - `backend/reputation/.env.reputation` desde `.env.reputation.example`
- Frontend:
  - `frontend/brr-frontend/.env.local` desde `.env.local.example`

Carga de configuración de reputación:
- `REPUTATION_CONFIG_PATH` apunta a un directorio por defecto (`./data/reputation`).
- Se mezclan todos los `*.json` (orden: `config.json` primero, luego alfabético).
