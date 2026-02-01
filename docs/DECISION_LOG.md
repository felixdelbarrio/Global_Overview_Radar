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
