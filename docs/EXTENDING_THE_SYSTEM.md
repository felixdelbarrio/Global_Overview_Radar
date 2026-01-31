# EXTENDING_THE_SYSTEM.md (EN / ES)

How to extend Global Overview Radar safely without breaking comparability and explainability.

Back to architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)

---

## EN | Add a new source

1) Implement connector in `ingestion/`
2) Map content to `ContentEvent`
3) Add configuration entry (no secrets in repo)
4) Add tests:
   - parsing/normalization
   - dedupe behavior
   - timestamp correctness

Checklist:
- traceability preserved
- idempotent ingestion
- consistent metadata fields

---

## EN | Add a new signal

1) Define trigger logic (metric + threshold)
2) Define baseline and peer group context
3) Implement in `alerts/`
4) Emit `SignalEvent` with:
   - trigger_reason
   - comparison_context
   - evidence_refs
   - confidence
5) Add to [`SIGNALS_CATALOG.md`](SIGNALS_CATALOG.md)
6) Add golden tests (expected triggers)

---

## EN | Add a new metric / score

1) Define what it measures (relative only)
2) Define baseline (historical) + peer group (market)
3) Ensure time window semantics are explicit
4) Implement in `intelligence/`
5) Document in `METRICS_AND_SCORES.md`

---

## ES | Añadir una nueva fuente

1) Implementa conector en `ingestion/`
2) Mapea a `ContentEvent`
3) Añade entrada de config (sin secretos en repo)
4) Tests:
   - parsing/normalización
   - dedupe
   - timestamps

Checklist:
- trazabilidad intacta
- ingesta idempotente
- metadatos consistentes

---

## ES | Añadir una nueva señal

1) Define trigger (métrica + umbral)
2) Define baseline y contexto de peer group
3) Implementa en `alerts/`
4) Emite `SignalEvent` con:
   - trigger_reason
   - comparison_context
   - evidence_refs
   - confidence
5) Añade al [`SIGNALS_CATALOG.md`](SIGNALS_CATALOG.md)
6) Golden tests (triggers esperados)

---

## ES | Añadir una nueva métrica / score

1) Define qué mide (solo relativo)
2) Define baseline (histórico) + peer group (mercado)
3) Ventana temporal explícita
4) Implementa en `intelligence/`
5) Documenta en `METRICS_AND_SCORES.md`
