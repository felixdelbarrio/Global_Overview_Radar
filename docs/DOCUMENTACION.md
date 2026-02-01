# DOCUMENTACION.md (EN / ES)

System-level guide for the current codebase.

Related:
- `ARCHITECTURE.md`
- `DATA_CONTRACTS.md`
- `EXTENDING_THE_SYSTEM.md`
- `FILES.md`

---

## EN | Overview

Global Overview Radar is split into two operational domains:

1) BugResolutionRadar (incidents)
- Reads incidents from structured files in `data/assets`.
- Normalizes + consolidates into `data/cache/bugresolutionradar_cache.json`.
- Exposes KPIs, incidents, and evolution endpoints via FastAPI.

2) Reputation Radar (public perception)
- Collects public items from multiple sources (news, social, reviews, markets).
- Uses one or many JSON configs in `data/reputation/` (mergeable).
- Normalizes, applies geo hints, runs sentiment, caches to `data/cache/reputation_cache.json`.
- Exposes reputation items + comparison endpoints.

---

## EN | Runtime flow

### BugResolutionRadar
1) Adapters read data from `data/assets` (CSV/JSON/XLSX).
2) `IngestService` emits `ObservedIncident` objects.
3) `ConsolidateService` merges into `IncidentRecord` and writes cache.
4) `ReportingService` computes KPIs from cache.
5) FastAPI exposes `/kpis`, `/incidents`, `/evolution`.

### Reputation Radar
1) Load business config (all `*.json` in `data/reputation/`).
2) Build collectors based on `.env.reputation` toggles.
3) Collect items, normalize, add geo hints, run sentiment.
4) Merge + cache to `data/cache/reputation_cache.json`.
5) FastAPI exposes `/reputation/items`, `/reputation/items/compare`, `/reputation/meta`.

---

## EN | Configuration

### Env files (auto-created if missing)
- `backend/bugresolutionradar/.env`
- `backend/reputation/.env.reputation`
- `frontend/brr-frontend/.env.local`

### Reputation config (multi-file)
- Default path: `REPUTATION_CONFIG_PATH=./data/reputation`
- All `*.json` are merged (load order: `config.json` first, then alphabetical).
- Merge rules:
  - dicts: deep merge
  - lists: append + dedupe
  - scalars: override only if incoming value is non-empty

---

## EN | Running locally

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

---

## ES | Vision general

Global Overview Radar se divide en dos dominios:

1) BugResolutionRadar (incidencias)
- Lee incidencias desde `data/assets`.
- Normaliza + consolida en `data/cache/bugresolutionradar_cache.json`.
- Expone KPIs, incidencias y evolucion via FastAPI.

2) Reputation Radar (percepcion publica)
- Recolecta items desde multiples fuentes.
- Usa uno o varios JSON en `data/reputation/` (mergeable).
- Normaliza, aplica geos, calcula sentimiento, cachea.
- Expone endpoints de reputacion y comparativas.

---

## ES | Flujo de ejecucion

### BugResolutionRadar
1) Adapters leen `data/assets` (CSV/JSON/XLSX).
2) `IngestService` produce `ObservedIncident`.
3) `ConsolidateService` genera `IncidentRecord` y escribe cache.
4) `ReportingService` calcula KPIs.
5) FastAPI expone `/kpis`, `/incidents`, `/evolution`.

### Reputation Radar
1) Carga config (todos los `*.json` en `data/reputation/`).
2) Construye collectors segun `.env.reputation`.
3) Recolecta, normaliza, aplica geo, sentimiento.
4) Merge + cache en `data/cache/reputation_cache.json`.
5) FastAPI expone `/reputation/items`, `/reputation/items/compare`, `/reputation/meta`.

---

## ES | Configuracion

### Env files (se crean si no existen)
- `backend/bugresolutionradar/.env`
- `backend/reputation/.env.reputation`
- `frontend/brr-frontend/.env.local`

### Configuracion de reputacion (multi-archivo)
- Path por defecto: `REPUTATION_CONFIG_PATH=./data/reputation`
- Se mezclan todos los `*.json` (orden: `config.json` primero).
- Reglas de merge:
  - dicts: merge profundo
  - listas: append + dedupe
  - escalares: override solo si el valor entrante no esta vacio

---

## ES | Ejecucion local

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
