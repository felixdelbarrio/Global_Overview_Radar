# Documentación Exhaustiva — BBVA BugResolutionRadar

Esta guía explica **todos los módulos, funciones y flujos** del proyecto para que cualquier persona pueda comprenderlo sin ambigüedades. Está organizada por capas: dominio, servicios, API y UI.

> Para una vision arquitectonica con diagramas y flujos: ver `ARCHITECTURE.md`.
> Para un inventario exhaustivo de archivos: ver `FILES.md`.

---

## 1) Mapa rápido del proyecto

```
backend/
  bbva_bugresolutionradar/
    adapters/              # Lectores CSV/JSON/XLSX
    api/                   # FastAPI + routers
    cli/                   # CLI de ingestión
    domain/                # Modelos y lógica de negocio
    repositories/          # Persistencia de cache
    services/              # Orquestación y reporting
frontend/brr-frontend/
  src/app/                 # Páginas Next.js
  src/components/          # UI reusable
  src/lib/                 # API client y tipos
  src/test/                # setup de testing
  src/__tests__/           # tests unitarios
ARCHITECTURE.md
README.md
```

---

## 2) Backend (Python)

### 2.1 `config.py`
**Responsabilidad:** centraliza configuración desde variables de entorno (via `pydantic-settings`).

- **Clase `Settings`**
  - `app_name`: nombre de app (default: “BBVA BugResolutionRadar”).
  - `tz`: zona horaria.
  - `assets_dir`: carpeta de fuentes (CSV/JSON/XLSX).
  - `cache_path`: ruta del JSON consolidado.
  - `sources`: lista activa (`filesystem_json,filesystem_csv,filesystem_xlsx`).
  - `xlsx_ignore_files`, `xlsx_preferred_sheet`: ajustes XLSX (no usados en lógica actual).
  - `master_threshold_clients`: umbral para “master incidents”.
  - `stale_days_threshold`: días para marcar incidencias stale.
  - `period_days_default`: ventana default para KPIs.
- **Métodos**
  - `enabled_sources()`: devuelve la lista de fuentes activas.
  - `xlsx_ignore_list()`: parseo de ignores XLSX.

### 2.2 `domain/enums.py`
**Responsabilidad:** enums oficiales del dominio.
- `Severity`: CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN.
- `Status`: OPEN, IN_PROGRESS, BLOCKED, CLOSED, UNKNOWN.

### 2.3 `domain/models.py`
**Responsabilidad:** modelos canónicos (Pydantic).

- `SourceRef`: procedencia por source_id/source_key + timestamps.
- `IncidentCurrent`: estado actual de una incidencia.
  - Propiedades: `is_open` (OPEN/IN_PROGRESS/BLOCKED), `is_master(threshold)`.
- `IncidentHistoryEvent`: cambios relevantes a lo largo del tiempo.
- `IncidentRecord`: incidencia consolidada con `current`, `provenance`, `history`.
- `RunSource`: metadata de la fuente usada en una ejecución.
- `RunInfo`: metadata global de una ejecución.
- `CacheDocument`: documento consolidado (JSON) con `incidents`.
- `ObservedIncident`: observación canónica procedente de adaptadores.

### 2.4 `domain/kpis.py`
**Responsabilidad:** cálculo de KPIs.

- `KPIResult` (dataclass): resultados agregados.
- `compute_kpis(incidents, today, period_days, master_threshold_clients, stale_days_threshold)`
  - Calcula totals de abiertos, nuevos, cerrados, promedios de resolución y stale list.
  - **Reglas clave:**
    - `open_items` = incidencias con `current.is_open`.
    - `new_items` = abiertas dentro de `period_days`.
    - `closed_items` = cerradas dentro de `period_days`.
    - `mean_resolution_days_*` solo si hay datos válidos.
    - `open_over_threshold_list` = abiertas con antigüedad > `stale_days_threshold`.

### 2.5 `domain/merge.py`
**Responsabilidad:** merge granular de observaciones (no usado por `ConsolidateService`, pero disponible).

- `compute_global_id(source_id, source_key)`: hash determinista.
- `_diff_current(old, new)`: diff de campos relevantes.
- `merge_observation(existing, obs, global_id, run_id)`:
  - Si no existe, crea `IncidentRecord` y evento “CREATED”.
  - Si existe, actualiza `provenance`, `current` y `history` si hay cambios.

### 2.6 `adapters/`
**Responsabilidad:** leer ficheros y generar `ObservedIncident`.

- `base.py`
  - `Adapter`: interfaz con `source_id()` y `read()`.
- `filesystem.py`
  - `FilesystemAdapter`: base para adapters de filesystem.
- `utils.py`
  - `to_str`, `to_int`, `to_date`: normalización de datos.
- `csv_adapter.py`
  - `FilesystemCSVAdapter.read()`: recorre `*.csv`.
  - `_parse_status`, `_parse_severity`: heurísticas para textos.
- `json_adapter.py`
  - `FilesystemJSONAdapter.read()`: recorre `*.json` con lista de dicts.
  - Valida formato (si no es lista → `ValueError`).
- `xlsx_adapter.py`
  - `XlsxAdapter.read()`: recorre todos los `.xlsx`.
  - `_read_sheet()`: detecta columnas por headers aproximados.
  - Reglas destacadas:
    - Si no hay fecha → fila se ignora.
    - Si no hay ID → genera `AUTO-<hash>`.
    - `status` UNKNOWN → OPEN por defecto.

### 2.7 `services/`
**Responsabilidad:** lógica de alto nivel.

- `ingest_service.py`
  - `build_adapters()`: construye adaptadores según `Settings.sources`.
  - `ingest()`: ejecuta `read()` en cada adapter y concatena observaciones.
- `consolidate_service.py`
  - `consolidate(observations, sources)`:
    - Genera `CacheDocument` nuevo.
    - Normaliza `global_id = f"{source_id}:{source_key}"`.
    - Actualiza `current`, `provenance` y `history`.
  - `_touch_provenance()`: asegura `last_seen_at` y añade nuevos orígenes.
- `reporting_service.py`
  - `kpis(doc, today, period_days)`: wrapper sobre `compute_kpis`.

### 2.8 `repositories/cache_repo.py`
**Responsabilidad:** persistencia del JSON consolidado.

- `load()`: si no existe cache → devuelve `CacheDocument` vacío.
- `save(doc)`: crea carpetas y escribe JSON con indentación.

### 2.9 `api/`
**Responsabilidad:** exposición de datos a través de FastAPI.

- `api/main.py`
  - `create_app()`:
    - Configura CORS.
    - Inserta `settings`, `cache_repo`, `reporting` en `app.state`.
    - Incluye routers de KPIs, incidencias y evolución.
    - Endpoint `/health`.

- `api/routers/kpis.py`
  - `GET /kpis`
    - Query param `period_days` (opcional).
    - Respuesta con KPIs agregados.

- `api/routers/incidents.py`
  - `GET /incidents`
    - Filtros: `q`, `status`, `severity`, `opened_from`, `opened_to`, `only_open`.
    - Orden: `updated_desc`, `updated_asc`, `opened_desc`, `opened_asc`, `severity_desc`.
  - `GET /incidents/{global_id}`
    - Detalle completo con `current`, `provenance`, `history`.

- `api/routers/evolution.py`
  - `GET /evolution?days=N`
    - Serie temporal diaria con `open`, `new`, `closed`.

### 2.10 `cli/main.py`
**Responsabilidad:** CLI para ingesta desde terminal.

- `brr ingest`:
  - Ejecuta ingestión → consolidación → guarda cache.
  - Imprime métricas en consola.

---

## 3) Frontend (Next.js)

### 3.1 `src/app/layout.tsx`
- Layout global, importa estilos base (`globals.css`).

### 3.2 `src/app/page.tsx` (Dashboard Ejecutivo)
- KPIs principales y gráfico de evolución temporal.
- Usa `apiGet` para `/kpis` y `/evolution`.

### 3.3 `src/app/incidencias/page.tsx`
- Tabla con filtros por query, severidad y estado.
- Filtra en cliente sobre dataset cargado desde `/incidents`.

### 3.4 `src/app/ops/page.tsx`
- Vista operativa con filtros, ordenación y paginación.
- Resumen ejecutivo y “Top stale incidents”.
- Acciones rápidas demo (`alert`).

### 3.5 `src/components/Shell.tsx`
- Layout principal con topbar y sidebar.
- Destaca ruta activa según `usePathname()`.

### 3.6 `src/components/EvolutionChart.tsx`
- Wrapper del gráfico Recharts.
- Se carga dinámicamente (SSR off) desde `page.tsx`.

### 3.7 `src/lib/api.ts`
- `API_BASE`: usa `NEXT_PUBLIC_API_BASE_URL` o `/api`.
- `apiGet(path)`: fetch con `no-store` y manejo de errores.

### 3.8 `src/lib/types.ts`
- Tipos compartidos de dominio para frontend (KPIs, severidad, evolución).

---

## 4) Tests y calidad

### Backend
- `pytest` + `pytest-cov`.
- Cobertura mínima requerida: 70%.
- Tests en `tests/` cubren adapters, services, repos, API y dominio.

### Frontend
- `vitest` + Testing Library.
- Tests en `src/__tests__/` para páginas y componentes.
- Setup en `src/test/setup.ts`.

### Lint + typecheck
- `make lint` ejecuta `ruff` y `eslint`.
- `make typecheck` ejecuta `mypy`, `pyright` y `next build`.

---

## 5) CI/CD

En cada `push` GitHub Actions ejecuta:
- `make test-coverage-back`
- `make test-coverage-front`

---

## 6) Extender el proyecto (guía rápida)

### Añadir nuevo adapter
1) Crear nuevo módulo en `adapters/` implementando `Adapter`.
2) Añadir fuente en `Settings.sources`.
3) Actualizar `IngestService.build_adapters()`.

### Añadir KPI nuevo
1) Implementar cálculo en `domain/kpis.py`.
2) Exponerlo en `api/routers/kpis.py`.
3) Añadirlo al frontend (tipos + UI).

### Añadir nueva vista en frontend
1) Crear página en `src/app/`.
2) Reutilizar `Shell` y `apiGet`.
3) Añadir acceso en `Shell.tsx`.

---

## 7) Glosario
- **ObservedIncident**: incidente tal como lo ve un origen.
- **IncidentRecord**: incidente consolidado (vista única).
- **Provenance**: trazabilidad de fuentes.
- **Stale**: incidencia abierta más allá del umbral definido.

---

## 8) Dudas frecuentes

**¿Por qué usamos cache JSON?**
Para simplificar prototipos y acelerar consultas. Es reemplazable por DB.

**¿Cómo cambio la ventana de KPIs?**
`PERIOD_DAYS_DEFAULT` en `.env`.

**¿Cómo se calcula la evolución?**
Se cuenta por día en base a fechas de apertura/cierre del cache consolidado.
