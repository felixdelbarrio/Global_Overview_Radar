# DOCUMENTACION.md — Global Overview Radar (EN / ES)

This is the **system-level guide**: modules, flows, extension points, and operational mental models.

> Architecture & diagrams / Arquitectura y diagramas: [`ARCHITECTURE.md`](ARCHITECTURE.md)  
> File index / Índice de archivos: [`FILES.md`](FILES.md)

---

## EN | What this system is (in one paragraph)

Global Overview Radar turns public discourse into **comparative, explainable intelligence**. It detects **narrative change** and surfaces **early reputational signals** by comparing an organization’s exposure and framing against peers, baselines, and historical patterns.

## ES | Qué es este sistema (en un párrafo)

Global Overview Radar transforma el discurso público en **inteligencia comparativa y explicable**. Detecta **cambios narrativos** y saca a la luz **señales reputacionales tempranas** comparando la exposición y el framing de una organización contra peers, baselines y patrones históricos.

---

## EN | Layer responsibilities (practical)

### Ingestion
Capture content with traceability → emit `ContentEvent`.

### Processing & Enrichment
Normalize + dedupe + semantics (language, entities, topics, embeddings) → emit `EnrichedContent`.

### Intelligence
Baselines + clustering + trends + **relative** metrics → emit `ComparativeScore`, `NarrativeTrend`.

### Signals
Detect change (acceleration/divergence/emergence/polarity shifts) → emit explainable `SignalEvent`.

### API/Dashboards
Query, explore, and drill down to evidence.

---

## ES | Responsabilidades por capa (práctico)

### Ingesta
Captura contenido con trazabilidad → emite `ContentEvent`.

### Procesamiento y enriquecimiento
Normaliza + dedupe + semántica (idioma, entidades, temas, embeddings) → emite `EnrichedContent`.

### Inteligencia
Baselines + clustering + tendencias + métricas **relativas** → emite `ComparativeScore`, `NarrativeTrend`.

### Señales
Detecta cambio (aceleración/divergencia/emergencia/cambios de framing) → emite `SignalEvent` explicable.

### API/Dashboards
Consulta, exploración y drill-down a evidencia.

---

## EN | Day-in-the-life walkthrough (mock)

Scenario: a regulatory narrative suddenly accelerates around a topic in your sector.

1) A set of articles appears in multiple outlets.
2) Ingestion stores each as `ContentEvent` (immutable).
3) Enrichment tags entities (companies/regulators) and topics (taxonomy).
4) Intelligence computes velocity vs baseline + peer group divergence.
5) Signals engine triggers `Acceleration + Divergence` with:
   - compared-to context (peer group, last 30 days baseline)
   - supporting evidence (top articles/posts)
   - confidence score
6) Users see the signal with drill-down sources and timeline.

See signal definitions: [`SIGNALS_CATALOG.md`](SIGNALS_CATALOG.md)

---

## ES | Walkthrough “day-in-the-life” (mock)

Escenario: una narrativa regulatoria acelera de forma abrupta en tu sector.

1) Aparecen artículos en múltiples medios.
2) La ingesta guarda cada uno como `ContentEvent` (inmutable).
3) El enriquecimiento etiqueta entidades (empresas/reguladores) y temas (taxonomía).
4) La inteligencia calcula velocidad vs baseline + divergencia vs peers.
5) Se dispara `Aceleración + Divergencia` con:
   - contexto comparativo (peer group, baseline 30 días)
   - evidencia (top piezas)
   - score de confianza
6) El usuario ve la señal con drill-down y timeline.

Ver señales: [`SIGNALS_CATALOG.md`](SIGNALS_CATALOG.md)

---

## EN | Extension points
See the step-by-step guide in [`EXTENDING_THE_SYSTEM.md`](EXTENDING_THE_SYSTEM.md).

## ES | Puntos de extensión
Guía paso a paso en [`EXTENDING_THE_SYSTEM.md`](EXTENDING_THE_SYSTEM.md).
