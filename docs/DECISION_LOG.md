# DECISION_LOG.md (EN / ES)

Back to architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)

---

## EN | ADR-001 — Relative metrics only
**Decision:** All insight metrics are relative to baselines/peers.  
**Why:** Absolutes mislead across contexts.  
**Consequence:** Baselines are required everywhere.

## EN | ADR-002 — Immutable raw events
**Decision:** `ContentEvent` is immutable.  
**Why:** Auditability + reproducibility.  
**Consequence:** Reprocessing produces derived artifacts.

## EN | ADR-003 — Explainability bias
**Decision:** Prefer explainable outputs over black-box gains.  
**Why:** Trust and adoption.  
**Consequence:** Every signal carries evidence + context.

---

## ES | ADR-001 — Métricas relativas
**Decisión:** Métricas siempre relativas a baselines/peers.  
**Por qué:** Los absolutos engañan sin contexto.  
**Consecuencia:** Baselines obligatorios.

## ES | ADR-002 — Raw inmutable
**Decisión:** `ContentEvent` es inmutable.  
**Por qué:** auditoría + reproducibilidad.  
**Consecuencia:** reprocessing genera derivados.

## ES | ADR-003 — Sesgo hacia explicabilidad
**Decisión:** Preferir outputs explicables a “caja negra”.  
**Por qué:** confianza y adopción.  
**Consecuencia:** evidencia + contexto en cada señal.
