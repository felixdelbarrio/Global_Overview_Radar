# Makefile - Fullstack: Global Overview Radar
# Uso: make <target>
SHELL := /bin/bash

# --- Configuración general ---
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(PY) -m pip

FRONTDIR := frontend/brr-frontend
NPM := npm
NODE := node

HOST ?= 127.0.0.1
API_PORT ?= 8000
FRONT_PORT ?= 3000
FRONT_BENCH_URL ?= http://localhost:$(FRONT_PORT)

BENCH_DIR ?= docs/benchmarks
BENCH_ITERATIONS ?= 40
BENCH_WARMUP ?= 5
BENCH_MAX_REGRESSION ?= 0.15
BENCH_OUT_BACK ?= $(BENCH_DIR)/backend.latest.json
BENCH_BASELINE_BACK ?= $(BENCH_DIR)/backend.baseline.json
BENCH_OUT_FRONT ?= $(BENCH_DIR)/frontend.latest.json
BENCH_BASELINE_FRONT ?= $(BENCH_DIR)/frontend.baseline.json

VISUAL_QA_URL ?= http://localhost:$(FRONT_PORT)
VISUAL_QA_OUT ?= docs/visual-qa

.DEFAULT_GOAL := help

.PHONY: help venv install install-backend install-front env ensure-backend ensure-front ingest reputation-ingest serve serve-back dev-back dev-front build-front start-front lint lint-back lint-front typecheck typecheck-back typecheck-front format format-back format-front check test test-back test-front test-coverage test-coverage-back test-coverage-front bench bench-back bench-front bench-baseline visual-qa clean reset

help:
	@echo "Make targets disponibles:"
	@echo "  make venv            - Crear virtualenv Python"
	@echo "  make install         - Instalar backend + frontend"
	@echo "  make install-backend - Instalar dependencias Python y paquete editable"
	@echo "  make install-front   - Instalar dependencias Node (frontend)"
	@echo "  make env             - Crear .env desde .env.example si falta"
	@echo "  make ensure-backend  - Preparar entorno backend (venv + deps)"
	@echo "  make ensure-front    - Preparar entorno frontend (deps)"
	@echo "  make reset           - Limpieza total + instalación completa"
	@echo "  make ingest          - Ejecutar ingesta de reputación"
	@echo "  make reputation-ingest - Ejecutar ingesta de reputación (backend)"
	@echo "  make serve-back      - Iniciar API (uvicorn) en $(HOST):$(API_PORT)"
	@echo "  make dev-back        - Atender solo backend (uvicorn --reload)"
	@echo "  make dev-front       - Atender solo frontend (next dev en $(FRONT_PORT))"
	@echo "  make dev             - (Manual) Ejecuta dev-back y dev-front en 2 terminales"
	@echo "  make build-front     - Build de producción del frontend (next build)"
	@echo "  make start-front     - Iniciar frontend en modo producción (next start)"
	@echo "  make lint            - Lint backend + frontend"
	@echo "  make typecheck       - Type checks backend + frontend"
	@echo "  make format          - Formatear código (backend + frontend)"
	@echo "  make check           - format-check + lint + typecheck"
	@echo "  make test            - Ejecutar tests (si existen)"
	@echo "  make test-back       - Ejecutar tests backend (pytest + cobertura)"
	@echo "  make test-front      - Ejecutar tests frontend (vitest)"
	@echo "  make test-coverage   - Ejecutar cobertura backend + frontend (>=70%)"
	@echo "  make bench           - Benchmark backend + frontend (comparacion baseline)"
	@echo "  make bench-back      - Benchmark backend (API reputacion)"
	@echo "  make bench-front     - Benchmark frontend (requiere frontend levantado)"
	@echo "  make bench-baseline  - Generar baselines (backend + frontend)"
	@echo "  make visual-qa       - Capturas headless mobile (frontend)"
	@echo "  make clean           - Eliminar venv, caches, node_modules (frontend)"
	@echo ""
	@echo "Notas:"
	@echo " - Levanta backend: make venv && make install-backend && make env && make dev-back"
	@echo " - Para ingestas: prepara el backend una vez (make ensure-backend) y luego ejecuta reputation-ingest"
	@echo " - Levanta frontend: cd $(FRONTDIR) && npm run dev"
	@echo " - Para desarrollo fullstack usa dos terminales (backend + frontend)."

# -------------------------
# Virtualenv + Instalación
# -------------------------
venv:
	@echo "==> Creando virtualenv en $(VENV) (si no existe)..."
	@if [ ! -x $(VENV)/bin/python ] || [ ! -x $(VENV)/bin/pip ]; then \
		rm -rf $(VENV); \
		python3 -m venv $(VENV); \
	fi
	$(PIP) install --upgrade pip setuptools wheel

install: install-backend install-front
	@echo "==> Instalación completa (backend + frontend)."

install-backend: venv
	@echo "==> Instalando dependencias Python (requirements / pyproject editable)..."
	$(PIP) install -r requirements.txt || true
	$(PIP) install -e backend

install-front:
	@echo "==> Instalando dependencias frontend (cd $(FRONTDIR))..."
	cd $(FRONTDIR) && $(NPM) install
	@echo "==> Instalación frontend completada."

env:
	@# Create per-module env files from examples if missing
	@test -f backend/reputation/.env.reputation || cp backend/reputation/.env.reputation.example backend/reputation/.env.reputation
	@echo "==> .env files prepared (edit if needed)."

ensure-backend: install-backend

ensure-front: install-front
	@true

# -------------------------
# Backend runtime
# -------------------------
ingest: reputation-ingest
	@echo "==> Ingesta reputacional finalizada."

reputation-ingest:
	@echo "==> Ejecutando ingesta de reputación..."
	$(PY) -m reputation.cli

serve: serve-back
	@true

serve-back:
	@echo "==> Iniciando API (uvicorn) en http://$(HOST):$(API_PORT)..."
	$(PY) -m uvicorn reputation.api.main:app --reload --host $(HOST) --port $(API_PORT)

dev-back:
	@echo "==> Desarrollo backend (uvicorn --reload). Usa otra terminal para frontend."
	$(PY) -m uvicorn reputation.api.main:app --reload --host $(HOST) --port $(API_PORT)

# -------------------------
# Frontend runtime
# -------------------------
dev-front:
	@echo "==> Iniciando frontend (Next dev) en http://localhost:$(FRONT_PORT)..."
	cd $(FRONTDIR) && $(NPM) run dev

build-front:
	@echo "==> Build de frontend (production)..."
	cd $(FRONTDIR) && $(NPM) run build

start-front:
	@echo "==> Iniciando frontend en modo producción (next start)..."
	cd $(FRONTDIR) && $(NPM) run start

# -------------------------
# Lint / Format / Typecheck
# -------------------------
format: format-back format-front

format-back:
	@echo "==> Format backend (ruff format)..."
	$(PY) -m ruff format .

format-front:
	@echo "==> Format frontend (prettier / eslint --fix si configurado)..."
	cd $(FRONTDIR) && $(NPM) run lint -- --fix || true

lint: lint-back lint-front

lint-back:
	@echo "==> Lint backend (ruff check)..."
	$(PY) -m ruff check .

lint-front:
	@echo "==> Lint frontend (eslint)..."
	cd $(FRONTDIR) && $(NPM) run lint || true

typecheck: typecheck-back typecheck-front

typecheck-back:
	@echo "==> Typecheck backend (mypy + pyright)..."
	$(PY) -m mypy .
	$(PY) -m pyright

typecheck-front:
	@echo "==> Typecheck frontend (next / tsc)..."
	cd $(FRONTDIR) && $(NPM) run build --if-present || true
	# si tienes tsc configurado: cd $(FRONTDIR) && $(NPM) run typecheck

check: format lint typecheck

# -------------------------
# Tests
# -------------------------
test:
	@echo "==> Ejecutando tests backend + frontend..."
	@$(MAKE) test-back
	@$(MAKE) test-front

test-back:
	@echo "==> Tests backend (pytest + cobertura)..."
	$(PY) -m pytest

test-front:
	@echo "==> Tests frontend (vitest)..."
	cd $(FRONTDIR) && $(NPM) run test

test-coverage: test-coverage-back test-coverage-front

test-coverage-back:
	@echo "==> Cobertura backend (pytest-cov >=70%)..."
	$(PY) -m pytest

test-coverage-front:
	@echo "==> Cobertura frontend (vitest >=70%)..."
	cd $(FRONTDIR) && $(NPM) run test:coverage

# -------------------------
# Benchmarks / Visual QA
# -------------------------
bench:
	@$(MAKE) bench-back
	@$(MAKE) bench-front

bench-back:
	@echo "==> Benchmark backend..."
	@mkdir -p $(BENCH_DIR)
	$(PY) scripts/bench_backend.py --iterations $(BENCH_ITERATIONS) --warmup $(BENCH_WARMUP) --json $(BENCH_OUT_BACK) --baseline $(BENCH_BASELINE_BACK) --max-regression $(BENCH_MAX_REGRESSION)

bench-front:
	@echo "==> Benchmark frontend..."
	@mkdir -p $(BENCH_DIR)
	$(PY) scripts/bench_frontend.py --url $(FRONT_BENCH_URL) --iterations $(BENCH_ITERATIONS) --warmup $(BENCH_WARMUP) --json $(BENCH_OUT_FRONT) --baseline $(BENCH_BASELINE_FRONT) --max-regression $(BENCH_MAX_REGRESSION)

bench-baseline:
	@echo "==> Generando baselines de benchmarks..."
	@mkdir -p $(BENCH_DIR)
	$(PY) scripts/bench_backend.py --iterations $(BENCH_ITERATIONS) --warmup $(BENCH_WARMUP) --json $(BENCH_BASELINE_BACK)
	$(PY) scripts/bench_frontend.py --url $(FRONT_BENCH_URL) --iterations $(BENCH_ITERATIONS) --warmup $(BENCH_WARMUP) --json $(BENCH_BASELINE_FRONT)

visual-qa:
	@echo "==> Visual QA mobile..."
	VISUAL_QA_URL=$(VISUAL_QA_URL) VISUAL_QA_OUT=$(VISUAL_QA_OUT) bash scripts/visual-qa.sh

# -------------------------
# Limpieza
# -------------------------
clean:
	@echo "==> Limpiando entorno..."
	rm -rf $(VENV) .mypy_cache .ruff_cache .pytest_cache .pytest_cache
	rm -rf **/__pycache__ **/.pycache__
	@true
	# frontend
	cd $(FRONTDIR) && rm -rf node_modules .next dist out || true
	@echo "==> Limpieza completada."

# -------------------------
# Reset (clean + install)
# -------------------------
reset: clean install
	@echo "==> Reset completo finalizado."

# -------------------------
# Utilidades / helpers
# -------------------------
# Dev fullstack: sugerencia de uso (no ejecuta ambos en background)
dev:
	@echo "==> Para desarrollo fullstack abre 2 terminales y ejecuta:"
	@echo "- Terminal A: make dev-back"
	@echo "- Terminal B: make dev-front"
	@echo ""
	@echo "Si quieres hacerlo todo en un solo terminal instala 'concurrently' y ejecuta:"
	@echo "cd $(FRONTDIR) && npx concurrently \"$(PY) -m uvicorn reputation.api.main:app --reload --host $(HOST) --port $(API_PORT)\" \"npm run dev\""
