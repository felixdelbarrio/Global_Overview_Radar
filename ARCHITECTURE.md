# Arquitectura de Global Overview Radar

Este documento describe la arquitectura técnica y funcional de Global Overview Radar, incluyendo módulos, flujos de datos, puntos de integración y consideraciones de operación.

---

## 1) Visión general

Global Overview Radar es una plataforma full‑stack con dos grandes subsistemas:

- **Backend (Python/FastAPI)**: ingestión de fuentes, consolidación y API.
- **Frontend (Next.js)**: paneles ejecutivos y operativos.

El backend genera un **cache consolidado** (JSON) que sirve de base para los KPIs y vistas operativas. El frontend consume la API y ofrece la experiencia de usuario.

---

## 2) Arquitectura de alto nivel (C4 - Context)

```mermaid
flowchart LR
  U[Usuarios Ejecutivos/Operativos]
  FE[Frontend Next.js]
  API[Backend FastAPI]
  FS[(Assets CSV/JSON/XLSX)]
  CACHE[(Cache consolidado JSON)]

  U --> FE
  FE --> API
  FS --> API
  API --> CACHE
  CACHE --> API
```

---

## 3) Contenedores principales (C4 - Containers)

```mermaid
flowchart TB
  subgraph Frontend
    FE[Next.js UI
    - Dashboard Ejecutivo
    - Incidencias
    - Ops Executive]
  end

  subgraph Backend
    ING[Ingest Service]
    CONS[Consolidate Service]
    REP[Reporting Service]
    API[FastAPI Routers]
  end

  ASSETS[(Assets Dir)] --> ING
  ING --> CONS
  CONS --> CACHE[(Cache JSON)]
  CACHE --> REP
  REP --> API
  API --> FE
```

---

## 4) Dominios y módulos

### Backend
- **Adapters** (`adapters/*`): Lectura de fuentes CSV/JSON/XLSX.
- **Services** (`services/*`):
  - `IngestService`: Orquesta adaptadores y recopila observaciones.
  - `ConsolidateService`: Unifica incidencias, mantiene historial y procedencia.
  - `ReportingService`: Calcula KPIs, evolución y métricas.
- **Domain** (`domain/*`): Modelos, enums y lógica de KPI.
- **Repositories** (`repositories/*`): Persistencia del cache.
- **API** (`api/*`): Endpoints de KPIs, incidencias y evolución.

### Frontend
- **Pages** (`src/app/*`): Dashboard, incidencias y Ops.
- **Components** (`src/components/*`): Shell, cards, charts, etc.
- **Lib** (`src/lib/*`): API client y tipos compartidos.

---

## 5) Flujo de ingestión y consolidación

```mermaid
sequenceDiagram
  participant Cron as Scheduler/Manual
  participant Ingest as IngestService
  participant Adapters as Adapters CSV/JSON/XLSX
  participant Consolidate as ConsolidateService
  participant Cache as CacheRepo

  Cron->>Ingest: ingest()
  Ingest->>Adapters: read()
  Adapters-->>Ingest: ObservedIncident[]
  Ingest->>Consolidate: consolidate(observations)
  Consolidate-->>Cache: CacheDocument
  Cache-->>Cache: save(cache.json)
```

**Reglas clave de consolidación**
- `global_id` determinista (source_id + source_key).
- Se actualiza `current` en cada observación.
- Se agrega `history` si hay cambios relevantes.
- Se mantiene `provenance` por origen.

---

## 6) Flujo de lectura (API + Frontend)

```mermaid
sequenceDiagram
  participant FE as Frontend
  participant API as FastAPI
  participant Cache as CacheRepo
  participant Reporting as ReportingService

  FE->>API: GET /kpis
  API->>Cache: load()
  Cache-->>API: CacheDocument
  API->>Reporting: compute_kpis()
  Reporting-->>API: KPIResult
  API-->>FE: JSON KPIs

  FE->>API: GET /incidents
  API->>Cache: load()
  Cache-->>API: CacheDocument
  API-->>FE: Lista incidencias

  FE->>API: GET /evolution
  API->>Cache: load()
  Cache-->>API: CacheDocument
  API-->>FE: Serie temporal
```

---

## 7) Modelo de datos (resumen)

```mermaid
classDiagram
  class ObservedIncident {
    source_id
    source_key
    observed_at
    title
    status
    severity
    opened_at
    closed_at
    updated_at
    clients_affected
    product
    feature
  }

  class IncidentRecord {
    global_id
    current
    provenance[]
    history[]
  }

  class CacheDocument {
    generated_at
    runs[]
    incidents{}
  }

  ObservedIncident --> IncidentRecord : consolidates to
  CacheDocument --> IncidentRecord : contains
```

---

## 8) Configuración y parámetros

Controlados desde `.env`:
- `ASSETS_DIR`: origen de ficheros.
- `CACHE_PATH`: JSON consolidado.
- `SOURCES`: lista activa de fuentes.
- `MASTER_THRESHOLD_CLIENTS`, `STALE_DAYS_THRESHOLD`, `PERIOD_DAYS_DEFAULT`.

---

## 9) Testing y calidad

- Backend: `pytest` + `pytest-cov` (coverage >= 70%).
- Frontend: `vitest` + `@testing-library/*` (coverage >= 70%).
- Lint: `ruff` (backend) + `eslint` (frontend).
- Typecheck: `mypy`/`pyright` y `next build`.

---

## 10) Seguridad y cumplimiento

- CORS configurado para entornos locales/lan.
- Control de acceso aún no implementado (sugerido en roadmap).
- Recomendado: autenticación, auditoría y cifrado en repositorio si se integran datos sensibles.

---

## 11) Observabilidad (sugerido)

- Logging estructurado (JSON).
- Métricas de ingestión y tiempo de respuesta.
- Alertas sobre incidentes críticos y stale.

---

## 12) Roadmap técnico

- Persistencia en base de datos relacional o documental.
- Jobs de ingestión programados (cron/queue).
- Conectores corporativos (Jira/ServiceNow).
- Control de acceso y roles.
- Analítica avanzada (SLA, MTTR, cohortes).

---

## 13) FAQ

**¿Dónde se calcula la evolución temporal?**
En `api/routers/evolution.py` a partir del cache consolidado.

**¿Puedo añadir una nueva fuente?**
Sí, implementando un nuevo Adapter y activándolo en `SOURCES`.

**¿El cache es el único storage?**
Actualmente sí, pensado para prototipos y cargas medias. Para producción, se recomienda DB.
