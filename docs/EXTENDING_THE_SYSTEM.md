# EXTENDING_THE_SYSTEM.md (EN / ES)

Practical guide to extend the current codebase without breaking consistency.

Back to architecture: `ARCHITECTURE.md`

---

## EN | Add a new BugResolutionRadar adapter

1) Implement a new adapter under `backend/bugresolutionradar/adapters/`.
2) Extend adapter discovery in `backend/bugresolutionradar/services/ingest_service.py`.
3) Add config knobs in `backend/bugresolutionradar/.env.example` if needed.
4) Add tests for parsing + normalization + dedupe.

Checklist:
- consistent `ObservedIncident` output
- stable `source_id` / `source_key`
- idempotent ingestion

---

## EN | Add a new Reputation collector

1) Create a collector in `backend/reputation/collectors/` (see `base.py`).
2) Wire it in `backend/reputation/services/ingest_service.py`.
3) Add env toggles in `backend/reputation/config.py` and `.env.reputation.example`.
4) Update `docs` and add tests if parsing logic is complex.

If the source has an API + scraper fallback, follow the existing pattern in
`appstore.py` and `google_play.py` (API enabled => API collector, else scraper).

---

## EN | Add a new business scope (multi-config)

1) Drop a new JSON config into `data/reputation/`.
2) Keep it focused (only the extra keywords/actors/sources you need).
3) The loader will merge it with other configs automatically.

Example: combine `banking_bbva_empresas.json` + `banking_bbva_retail.json`.

---

## ES | Anadir un adapter de BugResolutionRadar

1) Implementa un adapter en `backend/bugresolutionradar/adapters/`.
2) Extiende el discovery en `backend/bugresolutionradar/services/ingest_service.py`.
3) Anade variables en `.env.example` si son necesarias.
4) Tests: parsing + normalizacion + dedupe.

Checklist:
- salida consistente de `ObservedIncident`
- `source_id` / `source_key` estables
- ingesta idempotente

---

## ES | Anadir un collector de Reputacion

1) Crea el collector en `backend/reputation/collectors/`.
2) Conecta en `backend/reputation/services/ingest_service.py`.
3) Anade toggles en `backend/reputation/config.py` y `.env.reputation.example`.
4) Actualiza docs y tests si hay parsing complejo.

Si hay API + scraper, sigue el patron de `appstore.py` y `google_play.py`.

---

## ES | Anadir un nuevo scope de negocio (multi-config)

1) Coloca un JSON nuevo en `data/reputation/`.
2) Mantenlo pequeno y especifico.
3) El loader lo combinara automaticamente con el resto.

Ejemplo: `banking_bbva_empresas.json` + `banking_bbva_retail.json`.
