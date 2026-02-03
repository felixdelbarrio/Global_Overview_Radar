# DATA_CONTRACTS.md (EN / ES)

Storage-agnostic contracts used by the current codebase.

Back to architecture: `ARCHITECTURE.md`

---

## EN | BugResolutionRadar contracts

### ObservedIncident (adapter output)
Minimal fields (see `backend/bugresolutionradar/domain/models.py`):
- `source_id`, `source_key`, `observed_at`
- `title`, `status`, `severity`
- `opened_at`, `closed_at`, `updated_at`
- `clients_affected`, `product`, `feature`, `resolution_type`

### IncidentRecord (consolidated)
- `global_id`
- `current` (IncidentCurrent)
- `provenance` (list of SourceRef)
- `history` (list of IncidentHistoryEvent)

### CacheDocument (backend cache)
- `schema_version`, `generated_at`
- `runs` (metadata of ingest runs)
- `incidents` (dict of IncidentRecord)

---

## ES | Contratos de BugResolutionRadar

### ObservedIncident (salida de adapters)
Campos minimos (ver `backend/bugresolutionradar/domain/models.py`):
- `source_id`, `source_key`, `observed_at`
- `title`, `status`, `severity`
- `opened_at`, `closed_at`, `updated_at`
- `clients_affected`, `product`, `feature`, `resolution_type`

### IncidentRecord (consolidado)
- `global_id`
- `current` (IncidentCurrent)
- `provenance` (lista de SourceRef)
- `history` (lista de IncidentHistoryEvent)

### CacheDocument (cache del backend)
- `schema_version`, `generated_at`
- `runs` (metadata de ejecuciones)
- `incidents` (dict de IncidentRecord)

---

## EN | Reputation contracts

### ReputationItem
- `id`, `source`
- `geo`, `actor`, `language`
- `published_at`, `collected_at`
- `author`, `url`, `title`, `text`
- `signals` (dict with extra metadata, e.g. `sentiment_score`, `rating`)
- `sentiment`, `aspects`
- `manual_override` (geo/sentiment overrides + updated_at)

### ReputationCacheDocument
- `generated_at`, `config_hash`
- `sources_enabled`
- `items` (list of ReputationItem)
- `stats` (`count`, optional `note`)

### ReputationMeta (API)
- `actor_principal`, `geos`
- `otros_actores_por_geografia`, `otros_actores_globales`
- `sources_enabled`, `sources_available`, `source_counts`
- `incidents_available` (bool, derived from cache existence)
- `ui` (`incidents_enabled`, `ops_enabled`)

### IngestJob (API)
Used by `/ingest/*`:
- `id`, `kind` (`reputation|incidents`)
- `status` (`queued|running|success|error`)
- `progress` (0..100), `stage`
- `started_at`, `finished_at`, `error`
- `meta` (optional metrics like items/incidents/sources)

---

## ES | Contratos de Reputacion

### ReputationItem
- `id`, `source`
- `geo`, `actor`, `language`
- `published_at`, `collected_at`
- `author`, `url`, `title`, `text`
- `signals` (metadatos extra, ej. `sentiment_score`, `rating`)
- `sentiment`, `aspects`
- `manual_override` (overrides geo/sentimiento + updated_at)

### ReputationCacheDocument
- `generated_at`, `config_hash`
- `sources_enabled`
- `items` (lista de ReputationItem)
- `stats` (`count`, y `note` opcional)

### ReputationMeta (API)
- `actor_principal`, `geos`
- `otros_actores_por_geografia`, `otros_actores_globales`
- `sources_enabled`, `sources_available`, `source_counts`
- `incidents_available` (bool, si existe cache de incidencias)
- `ui` (`incidents_enabled`, `ops_enabled`)

### IngestJob (API)
Usado por `/ingest/*`:
- `id`, `kind` (`reputation|incidents`)
- `status` (`queued|running|success|error`)
- `progress` (0..100), `stage`
- `started_at`, `finished_at`, `error`
- `meta` (metricas opcionales: items/incidencias/fuentes)
