# DECISION_LOG.md (EN / ES)

Back to architecture: `ARCHITECTURE.md`

---

## EN | ADR-001 — Relative metrics only
**Decision:** Insight metrics are relative to baselines/peers.  
**Why:** Absolutes mislead across contexts.  
**Consequence:** Baselines are required everywhere.

## EN | ADR-002 — Immutable raw events
**Decision:** Raw events are immutable.  
**Why:** Auditability + reproducibility.  
**Consequence:** Reprocessing produces derived artifacts.

## EN | ADR-003 — Explainability bias
**Decision:** Prefer explainable outputs over black-box gains.  
**Why:** Trust and adoption.  
**Consequence:** Every signal carries evidence + context.

## EN | ADR-004 — Multi-config reputation scope
**Decision:** Reputation configs are loaded from a directory and merged.  
**Why:** Allows composing scopes (e.g., Empresas + Retail) without monolithic files.  
**Consequence:** Merge rules defined (deep dict merge, list dedupe, scalar override if non-empty).

## EN | ADR-005 — Logging controlled by env
**Decision:** Logging is opt-in via env flags, with optional file output.  
**Why:** Performance and noise control by default.  
**Consequence:** `.env` files drive console vs file logging; logs go to `./logs/`.

## EN | ADR-006 — Sentiment-first UI
**Decision:** The dashboard centers on sentiment, with incidents as a secondary line and optional views.  
**Why:** Sentiment is the core signal for most scopes; incidents are only meaningful for IT/ops actors.  
**Consequence:** Incidents/Ops can be disabled per config (`ui.incidents_enabled`, `ui.ops_enabled`).

## EN | ADR-007 — Noise-control at ingestion
**Decision:** Apply strict actor presence checks + geo allowlists before caching reputation items.  
**Why:** Reduce irrelevant mentions and protect end-user experience.  
**Consequence:** Some sources require actor-in-text; mismatched actor/geo items are dropped.

## EN | ADR-008 — Incident scope gated by env + cache
**Decision:** Incident features are shown only when the frontend flag allows it and the incidents cache exists.  
**Why:** Incidents are contextual, and the UX should not expose empty scopes.  
**Consequence:** `NEXT_PUBLIC_INCIDENTS_ENABLED` + cache presence (`bugresolutionradar_cache.json`) jointly control visibility.

## EN | ADR-009 — Ingest triggered from UI with progress
**Decision:** Ingest can be launched from the UI via `/ingest/*`, with background jobs and progress.  
**Why:** Keeps workflows fast without blocking the rest of the dashboard.  
**Consequence:** Jobs are in-memory and reset on restart (unless persisted later).

---

## ES | ADR-001 — Metricas relativas
**Decision:** Metricas siempre relativas a baselines/peers.  
**Por que:** Los absolutos enganan sin contexto.  
**Consecuencia:** Baselines obligatorios.

## ES | ADR-002 — Raw inmutable
**Decision:** Los eventos raw son inmutables.  
**Por que:** auditoria + reproducibilidad.  
**Consecuencia:** reprocessing genera derivados.

## ES | ADR-003 — Sesgo hacia explicabilidad
**Decision:** Preferir outputs explicables a caja negra.  
**Por que:** confianza y adopcion.  
**Consecuencia:** evidencia + contexto en cada senal.

## ES | ADR-004 — Multi-config para reputacion
**Decision:** Configs de reputacion se cargan desde un directorio y se mezclan.  
**Por que:** Permite componer scopes sin ficheros monoliticos.  
**Consecuencia:** Reglas de merge definidas.

## ES | ADR-005 — Logging controlado por env
**Decision:** El logging es opt-in via env y opcionalmente a fichero.  
**Por que:** control de rendimiento y ruido.  
**Consecuencia:** `.env` gobierna consola vs fichero; logs en `./logs/`.

## ES | ADR-006 — UI centrada en sentimiento
**Decision:** El dashboard se centra en sentimiento, con incidencias como capa secundaria y opcional.  
**Por que:** El sentimiento es la senal principal; incidencias solo aplican a actores IT/ops.  
**Consecuencia:** Incidencias/Ops pueden deshabilitarse por config (`ui.incidents_enabled`, `ui.ops_enabled`).

## ES | ADR-007 — Control de ruido en ingesta
**Decision:** Aplicar checks estrictos de actor + allowlist por geo antes del cache.  
**Por que:** Reducir menciones irrelevantes y proteger la experiencia del cliente.  
**Consecuencia:** Algunas fuentes exigen actor en texto; items fuera de geo se descartan.

## ES | ADR-008 — Ambito de incidencias por env + cache
**Decision:** El ambito de incidencias solo se muestra si el flag de frontend lo permite y existe el cache.  
**Por que:** Incidencias son contextuales y no deben mostrarse sin datos.  
**Consecuencia:** `NEXT_PUBLIC_INCIDENTS_ENABLED` + presencia de `bugresolutionradar_cache.json` controlan visibilidad.

## ES | ADR-009 — Ingesta disparada desde UI con progreso
**Decision:** La ingesta se puede lanzar desde UI via `/ingest/*` con jobs en background y progreso.  
**Por que:** Mantiene fluidez sin bloquear el dashboard.  
**Consecuencia:** Los jobs son in-memory y se reinician al reiniciar el backend.
