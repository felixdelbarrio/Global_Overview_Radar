# Project File Index (Exhaustive)

This file documents every tracked project file (source, config, tests, assets) so anyone can locate and understand it quickly.

Notes:
- Generated/cache content (e.g. `.venv`, `.mypy_cache`, `.next`, `node_modules`, `.git`) is not listed here.
- For module-level and function-level details, see `DOCUMENTATION.md`.

---

## Root

- `README.md` - High-level product overview, setup, commands, and entry points.
- `ARCHITECTURE.md` - Architecture and system flows with diagrams.
- `DOCUMENTATION.md` - Detailed module/function documentation.
- `FILES.md` - This file index (exhaustive list of project files).
- `Makefile` - Local dev, test, lint, typecheck, and build commands.
- `pyproject.toml` - Python project metadata, tooling config (ruff/mypy/pyright).
- `requirements.txt` - Python dependencies (runtime + quality + testing).
- `pytest.ini` - pytest config and coverage threshold.
- `.env.example` - Sample environment variables.
- `.env` - Local environment values (do not commit in production).
- `.github/workflows/ci.yml` - CI workflow (tests/coverage on push).
- `.gitignore` - Git ignore rules.
- `backend .env` - Legacy or misnamed env file placeholder (review if needed).
- `brr-frontend@0.1.0` - Placeholder file (no active use).
- `next` - Placeholder file (no active use).

---

## Data

- `data/assets/Canales Digitales Enterprise.xlsx` - Example/source XLSX for ingest.
- `data/assets/NPS- Mejoras.xlsx` - Example/source XLSX for ingest.
- `data/assets_sample/sample_issues.csv` - Sample CSV data for ingest/testing.
- `data/assets_sample/sample_issues.json` - Sample JSON data for ingest/testing.

---

## Backend Package

### Core package
- `backend/bbva_bugresolutionradar/__init__.py` - Package marker.
- `backend/bbva_bugresolutionradar/config.py` - Settings via pydantic-settings.

### Adapters (ingestion)
- `backend/bbva_bugresolutionradar/adapters/__init__.py` - Adapter exports.
- `backend/bbva_bugresolutionradar/adapters/base.py` - Adapter interface.
- `backend/bbva_bugresolutionradar/adapters/filesystem.py` - Filesystem adapter base.
- `backend/bbva_bugresolutionradar/adapters/utils.py` - Parsing helpers (to_str, to_int, to_date).
- `backend/bbva_bugresolutionradar/adapters/csv_adapter.py` - CSV ingestion adapter.
- `backend/bbva_bugresolutionradar/adapters/json_adapter.py` - JSON ingestion adapter.
- `backend/bbva_bugresolutionradar/adapters/xlsx_adapter.py` - XLSX ingestion adapter with robust header detection.

### Domain
- `backend/bbva_bugresolutionradar/domain/__init__.py` - Domain exports.
- `backend/bbva_bugresolutionradar/domain/enums.py` - Severity/Status enums.
- `backend/bbva_bugresolutionradar/domain/models.py` - Pydantic domain models.
- `backend/bbva_bugresolutionradar/domain/kpis.py` - KPI computation logic.
- `backend/bbva_bugresolutionradar/domain/merge.py` - Merge helper for observations.

### Services
- `backend/bbva_bugresolutionradar/services/__init__.py` - Service exports.
- `backend/bbva_bugresolutionradar/services/ingest_service.py` - Builds adapters and ingests observations.
- `backend/bbva_bugresolutionradar/services/consolidate_service.py` - Consolidates observations into cache.
- `backend/bbva_bugresolutionradar/services/reporting_service.py` - KPI wrapper service.

### Repositories
- `backend/bbva_bugresolutionradar/repositories/__init__.py` - Repository exports.
- `backend/bbva_bugresolutionradar/repositories/cache_repo.py` - Cache load/save JSON.

### API (FastAPI)
- `backend/bbva_bugresolutionradar/api/__init__.py` - API package marker.
- `backend/bbva_bugresolutionradar/api/main.py` - FastAPI app creation, CORS, routers, health.
- `backend/bbva_bugresolutionradar/api/routers/__init__.py` - Router exports.
- `backend/bbva_bugresolutionradar/api/routers/kpis.py` - `GET /kpis` endpoint.
- `backend/bbva_bugresolutionradar/api/routers/incidents.py` - `GET /incidents` and `GET /incidents/{id}`.
- `backend/bbva_bugresolutionradar/api/routers/evolution.py` - `GET /evolution` time series.

### CLI
- `backend/bbva_bugresolutionradar/cli/__init__.py` - CLI package marker.
- `backend/bbva_bugresolutionradar/cli/main.py` - CLI entrypoint (`brr ingest`).

### Packaging metadata (generated)
- `backend/bbva_bugresolutionradar.egg-info/PKG-INFO` - Package metadata.
- `backend/bbva_bugresolutionradar.egg-info/SOURCES.txt` - Source file list.
- `backend/bbva_bugresolutionradar.egg-info/entry_points.txt` - Console scripts.
- `backend/bbva_bugresolutionradar.egg-info/requires.txt` - Dependencies list.
- `backend/bbva_bugresolutionradar.egg-info/top_level.txt` - Top-level packages.
- `backend/bbva_bugresolutionradar.egg-info/dependency_links.txt` - Legacy dependency links.

---

## Tests (Backend)

- `tests/conftest.py` - Shared fixtures for domain + cache.
- `tests/test_adapters_utils.py` - Utility parser tests.
- `tests/test_adapters_csv_json.py` - CSV/JSON adapter tests.
- `tests/test_adapters_xlsx.py` - XLSX adapter tests.
- `tests/test_ingest_service.py` - Ingest orchestration tests.
- `tests/test_consolidate_service.py` - Consolidation and history tests.
- `tests/test_reporting_kpis.py` - KPI computation tests.
- `tests/test_cache_repo.py` - Cache repository tests.
- `tests/test_merge.py` - Merge logic tests.
- `tests/test_api.py` - FastAPI endpoints tests (using TestClient).

---

## Frontend (Next.js)

### Tooling/config
- `frontend/brr-frontend/package.json` - Frontend scripts and dependencies.
- `frontend/brr-frontend/package-lock.json` - Locked dependency tree.
- `frontend/brr-frontend/tsconfig.json` - TypeScript configuration.
- `frontend/brr-frontend/eslint.config.mjs` - ESLint configuration.
- `frontend/brr-frontend/tailwind.config.js` - Tailwind configuration.
- `frontend/brr-frontend/postcss.config.mjs` - PostCSS configuration.
- `frontend/brr-frontend/next.config.ts` - Next.js config.
- `frontend/brr-frontend/vitest.config.ts` - Vitest configuration.
- `frontend/brr-frontend/.gitignore` - Frontend-specific ignore rules.

### App entry
- `frontend/brr-frontend/src/app/layout.tsx` - Root layout for all pages.
- `frontend/brr-frontend/src/app/globals.css` - Global styles.
- `frontend/brr-frontend/src/app/favicon.ico` - App icon.

### Pages
- `frontend/brr-frontend/src/app/page.tsx` - Executive dashboard (KPIs + evolution).
- `frontend/brr-frontend/src/app/incidencias/page.tsx` - Incident list with filters.
- `frontend/brr-frontend/src/app/ops/page.tsx` - Ops executive panel.

### Components
- `frontend/brr-frontend/src/components/Shell.tsx` - Main layout + navigation.
- `frontend/brr-frontend/src/components/EvolutionChart.tsx` - Chart wrapper (Recharts).

### Lib
- `frontend/brr-frontend/src/lib/api.ts` - API client (`apiGet`).
- `frontend/brr-frontend/src/lib/types.ts` - Shared types (KPIs, severity, evolution).

### Frontend tests
- `frontend/brr-frontend/src/test/setup.ts` - Vitest setup (JSDOM, mocks).
- `frontend/brr-frontend/src/__tests__/api.test.ts` - API helper tests.
- `frontend/brr-frontend/src/__tests__/Shell.test.tsx` - Shell UI tests.
- `frontend/brr-frontend/src/__tests__/DashboardPage.test.tsx` - Dashboard tests.
- `frontend/brr-frontend/src/__tests__/IncidenciasPage.test.tsx` - Incidents page tests.
- `frontend/brr-frontend/src/__tests__/OpsPage.test.tsx` - Ops page tests.

---

## Generated/ignored (not documented here)

Examples: `.venv`, `.mypy_cache`, `.next`, `node_modules`, `.git`, `data/cache/*`, OS files (like `.DS_Store`).
