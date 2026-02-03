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

**Current product focus:** sentiment-first dashboard with incidents as a complementary layer (configurable).
Incidents are additionally gated by a frontend scope flag and the presence of the
incidents cache file.

---

## EN | Runtime flow

### BugResolutionRadar
1) Adapters read data from `data/assets` (CSV/JSON/XLSX).
2) `IngestService` emits `ObservedIncident` objects.
3) `ConsolidateService` merges into `IncidentRecord` and writes cache.
4) `ReportingService` computes KPIs from cache.
5) FastAPI exposes `/kpis`, `/incidents`, `/evolution`.
6) Optional: `/ingest/incidents` can trigger ingestion in the background.

### Reputation Radar
1) Load business config (all `*.json` in `data/reputation/`).
2) Build collectors based on `.env.reputation` toggles.
3) Collect items, normalize, add geo hints, run sentiment.
4) Apply noise control: actor presence, actor-in-text checks, guard actors, actor/geo allowlists.
5) Merge + cache to `data/cache/reputation_cache.json`.
6) FastAPI exposes `/reputation/items`, `/reputation/items/compare`, `/reputation/meta`.
7) Optional: `/ingest/reputation` can trigger ingestion in the background.

### Frontend (current navigation)
- **Dashboard (/)**
  - Sentiment trend + incident trend (if enabled)
  - 20 latest mentions (sentiment + incidents)
- **Sentimiento**
  - Filters, full list, manual overrides
  - CSV downloads (chart + grid)
- **Incidencias / Ops Executive**
  - Optional; hidden when `ui.incidents_enabled=false` or `ui.ops_enabled=false`
- **Ingest Center**
  - Top-right control that can launch reputation or incident ingests with live progress.

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

Noise-control knobs (reputation):
- `require_actor_sources`: list of sources that must contain an actor reference.
- `guard_actors` / `guard_context_terms`: block items with ambiguous actor mentions.
- `otros_actores_por_geografia` + `otros_actores_globales`: allowlist actors by geo (drops mismatched).
- `require_context_sources`: enforce context terms for specific sources (e.g., downdetector).
- `rss_query_segment_mode`: tighten RSS queries per source (e.g., set downdetector to `strict`).

UI flags:
- `ui.incidents_enabled` / `ui.ops_enabled`: enable or hide incident-related views.
Frontend scope flag:
- `NEXT_PUBLIC_INCIDENTS_ENABLED`: hide all incident scope (nav, ingest button, dashboard line).
Availability gate:
- If `data/cache/bugresolutionradar_cache.json` is missing, incident features are hidden regardless of flags.

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

**Foco actual del producto:** dashboard centrado en sentimiento, con incidencias como capa complementaria (configurable).
Las incidencias ademas dependen del flag del frontend y de la existencia del cache.

---

## ES | Flujo de ejecucion

### BugResolutionRadar
1) Adapters leen `data/assets` (CSV/JSON/XLSX).
2) `IngestService` produce `ObservedIncident`.
3) `ConsolidateService` genera `IncidentRecord` y escribe cache.
4) `ReportingService` calcula KPIs.
5) FastAPI expone `/kpis`, `/incidents`, `/evolution`.
6) Opcional: `/ingest/incidents` dispara la ingesta en segundo plano.

### Reputation Radar
1) Carga config (todos los `*.json` en `data/reputation/`).
2) Construye collectors segun `.env.reputation`.
3) Recolecta, normaliza, aplica geo, sentimiento.
4) Aplica control de ruido: actor obligatorio, actor en texto, guard actors, allowlist actor/geo.
5) Merge + cache en `data/cache/reputation_cache.json`.
6) FastAPI expone `/reputation/items`, `/reputation/items/compare`, `/reputation/meta`.
7) Opcional: `/ingest/reputation` dispara la ingesta en segundo plano.

### Frontend (navegacion actual)
- **Dashboard (/)**
  - Tendencia de sentimiento + incidencias (si estan habilitadas)
  - 20 menciones mas recientes (sentimiento + incidencias)
- **Sentimiento**
  - Filtros, listado completo, overrides manuales
  - Descargas CSV (grafico + grid)
- **Incidencias / Ops Executive**
  - Opcionales; se ocultan con `ui.incidents_enabled=false` o `ui.ops_enabled=false`
- **Centro de ingesta**
  - Control arriba a la derecha para lanzar ingestas con progreso en vivo.

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

Controles de ruido (reputacion):
- `require_actor_sources`: fuentes que exigen mencionar actor.
- `guard_actors` / `guard_context_terms`: bloquean contexto ambiguo.
- `otros_actores_por_geografia` + `otros_actores_globales`: allowlist de actores por geo (descarta mismatches).
- `require_context_sources`: fuerza contexto para fuentes concretas (ej. downdetector).
- `rss_query_segment_mode`: endurece consultas RSS por fuente (ej. downdetector en `strict`).

Flags de UI:
- `ui.incidents_enabled` / `ui.ops_enabled`: habilitan u ocultan vistas de incidencias.
Flag de scope en frontend:
- `NEXT_PUBLIC_INCIDENTS_ENABLED`: oculta todo el ambito de incidencias (nav, boton de ingesta y linea del dashboard).
Regla de disponibilidad:
- Si no existe `data/cache/bugresolutionradar_cache.json`, se oculta el ambito de incidencias aunque el flag este activo.

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
