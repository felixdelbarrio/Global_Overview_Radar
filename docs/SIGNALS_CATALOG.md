# SIGNALS_CATALOG.md (EN / ES)

Catalog of explainable signal types (conceptual). Some signals are roadmap items.

Back to architecture: `ARCHITECTURE.md`

---

## EN | Current status

The current codebase focuses on ingestion, normalization, KPIs, and reputation item
collection. The UI already uses sentiment trends and comparative series as a
baseline, but a full signals engine (comparative triggers) is still planned.
Use this catalog as target behavior for the next iteration.

---

## EN | Signal types (target)

1) Acceleration
- Abnormal growth in topic velocity vs baseline.

2) Divergence
- Entity framing/exposure diverges from peers.

3) Emergence
- New topic crosses relevance thresholds.

4) Polarity / Framing Shift
- Structural change in tone or narrative lens.

5) Saturation / Fatigue (optional)
- Overexposure risk vs historical baseline.

Each signal should include:
- what changed
- compared to what (baseline/peers)
- since when (time window)
- evidence (top supporting content)
- confidence

---

## ES | Estado actual

El codigo actual se centra en ingesta, normalizacion, KPIs y recoleccion de items.
La UI ya usa tendencia de sentimiento y series comparativas como base, pero el
motor de senales comparativas sigue en roadmap. Este catalogo es el objetivo.

---

## ES | Tipos de senal (objetivo)

1) Aceleracion
- Crecimiento anomalo vs baseline.

2) Divergencia
- Framing/exposicion se separa de peers.

3) Emergencia
- Nuevo tema supera umbrales.

4) Cambio de polaridad / framing
- Cambio estructural en tono o narrativa.

5) Saturacion / fatiga (opcional)
- Riesgo de sobreexposicion.

Cada senal debe incluir:
- que cambio
- respecto a que (baseline/peers)
- desde cuando (ventana temporal)
- evidencia (top piezas)
- confianza
