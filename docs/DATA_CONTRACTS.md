# DATA_CONTRACTS.md (EN / ES)

Logical contracts used across the system. These are storage-agnostic schemas designed for traceability and reproducibility.

Back to architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)

---

## EN | Contract philosophy
- Raw content is **immutable**
- Derived artifacts are **reprocessable**
- Every insight must be **traceable** to evidence

## ES | Filosofía
- El contenido raw es **inmutable**
- Los derivados son **reprocesables**
- Todo insight debe ser **trazable** a evidencia

---

## Core objects (Mermaid)

```mermaid
classDiagram
  class ContentEvent{
    +event_id
    +source_type
    +source_name
    +published_at
    +ingested_at
    +raw_text
    +raw_metadata
  }

  class EnrichedContent{
    +event_id
    +language
    +entities[]
    +topics[]
    +embeddings
  }

  class ComparativeScore{
    +entity
    +topic
    +time_window
    +value
    +baseline
    +peer_group
  }

  class SignalEvent{
    +signal_id
    +signal_type
    +entities_affected[]
    +topic
    +trigger_reason
    +comparison_context
    +confidence
    +evidence_refs[]
  }

  ContentEvent --> EnrichedContent
  EnrichedContent --> ComparativeScore
  ComparativeScore --> SignalEvent
```

---

## EN | Minimal fields (recommended)

### ContentEvent
- `event_id`, `published_at`, `source_type`, `raw_text`, `raw_metadata`

### EnrichedContent
- `language`, `entities`, `topics`, `embeddings` (optional)

### ComparativeScore
- `value`, `baseline`, `peer_group`, `time_window`

### SignalEvent
- `signal_type`, `trigger_reason`, `comparison_context`, `evidence_refs`, `confidence`

---

## ES | Campos mínimos (recomendado)

### ContentEvent
- `event_id`, `published_at`, `source_type`, `raw_text`, `raw_metadata`

### EnrichedContent
- `language`, `entities`, `topics`, `embeddings` (opcional)

### ComparativeScore
- `value`, `baseline`, `peer_group`, `time_window`

### SignalEvent
- `signal_type`, `trigger_reason`, `comparison_context`, `evidence_refs`, `confidence`
