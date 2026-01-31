# METRICS_AND_SCORES.md (EN / ES)

Back to signals: [`SIGNALS_CATALOG.md`](SIGNALS_CATALOG.md)

---

## EN | Philosophy
We avoid raw counts. Metrics must be:
- comparative
- time-bound
- baseline-aware
- explainable

## ES | Filosofía
Evitamos counts brutos. Las métricas deben ser:
- comparativas
- acotadas en tiempo
- con baseline
- explicables

---

## EN | Example formulas (conceptual)

### Exposure Index
`Exposure(entity, topic, window) / AvgExposure(peers, topic, window)`

### Velocity
`d(Exposure)/dt`

### Acceleration
`d(Velocity)/dt`

### Sensitivity-weighted impact
`Exposure * SensitivityWeight(topic)`

---

## ES | Fórmulas ejemplo (conceptual)

### Exposure Index
`Exposición(entidad, tema, ventana) / ExposiciónMedia(peers, tema, ventana)`

### Velocidad
`d(Exposición)/dt`

### Aceleración
`d(Velocidad)/dt`

### Impacto ponderado por sensibilidad
`Exposición * PesoSensibilidad(tema)`
