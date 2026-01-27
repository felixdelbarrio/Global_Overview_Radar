# Makefile - Fullstack: BBVA BugResolutionRadar
# Uso: make <target>
SHELL := /bin/bash

# --- Configuración general ---
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

FRONTDIR := frontend/brr-frontend
NPM := npm
NODE := node

HOST ?= 127.0.0.1
API_PORT ?= 8000
FRONT_PORT ?= 3000

.DEFAULT_GOAL := help

.PHONY: help venv install install-backend install-front env ingest serve serve-back dev-back dev-front build-front start-front lint lint-back lint-front typecheck typecheck-back typecheck-front format format-back format-front check test test-back test-front test-coverage test-coverage-back test-coverage-front clean

help:
	@echo "Make targets disponibles:"
	@echo "  make venv            - Crear virtualenv Python"
	@echo "  make install         - Instalar backend + frontend"
	@echo "  make install-backend - Instalar dependencias Python y paquete editable"
	@echo "  make install-front   - Instalar dependencias Node (frontend)"
	@echo "  make env             - Crear .env desde .env.example si falta"
	@echo "  make ingest          - Ejecutar ingestion/consolidación (backend)"
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
	@echo "  make clean           - Eliminar venv, caches, node_modules (frontend)"
	@echo ""
	@echo "Notas:"
	@echo " - Levanta backend: make venv && make install-backend && make env && make dev-back"
	@echo " - Levanta frontend: cd $(FRONTDIR) && npm run dev"
	@echo " - Para desarrollo fullstack usa dos terminales (backend + frontend)."

# -------------------------
# Virtualenv + Instalación
# -------------------------
venv:
	@echo "==> Creando virtualenv en $(VENV) (si no existe)..."
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel

install: install-backend install-front
	@echo "==> Instalación completa (backend + frontend)."

install-backend: venv
	@echo "==> Instalando dependencias Python (requirements / pyproject editable)..."
	$(PIP) install -r requirements.txt || true
	$(PIP) install -e .

install-front:
	@echo "==> Instalando dependencias frontend (cd $(FRONTDIR))..."
	cd $(FRONTDIR) && $(NPM) install
	@echo "==> Instalación frontend completada."

env:
	@test -f .env || cp .env.example .env
	@echo "==> .env preparado (no olvides editarlo si procede)."

# -------------------------
# Backend runtime
# -------------------------
ingest: env
	@echo "==> Ejecutando ingestion/consolidación (backend)..."
	$(PY) -m bbva_bugresolutionradar.cli.main ingest

serve: env serve-back
	@true

serve-back: env
	@echo "==> Iniciando API (uvicorn) en http://$(HOST):$(API_PORT)..."
	$(PY) -m uvicorn bbva_bugresolutionradar.api.main:app --reload --host $(HOST) --port $(API_PORT)

dev-back: env
	@echo "==> Desarrollo backend (uvicorn --reload). Usa otra terminal para frontend."
	$(PY) -m uvicorn bbva_bugresolutionradar.api.main:app --reload --host $(HOST) --port $(API_PORT)

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
	@test -x $(FRONTDIR)/node_modules/.bin/vitest || (echo "==> Instalando deps frontend..." && cd $(FRONTDIR) && $(NPM) install --include=dev)
	cd $(FRONTDIR) && $(NPM) run test

test-coverage: test-coverage-back test-coverage-front

test-coverage-back:
	@echo "==> Cobertura backend (pytest-cov >=70%)..."
	$(PY) -m pytest

test-coverage-front:
	@echo "==> Cobertura frontend (vitest >=70%)..."
	@test -x $(FRONTDIR)/node_modules/.bin/vitest || (echo "==> Instalando deps frontend..." && cd $(FRONTDIR) && $(NPM) install --include=dev)
	cd $(FRONTDIR) && $(NPM) run test:coverage

# -------------------------
# Limpieza
# -------------------------
clean:
	@echo "==> Limpiando entorno..."
	rm -rf $(VENV) .mypy_cache .ruff_cache .pytest_cache .pytest_cache
	rm -rf **/__pycache__ **/.pycache__
	rm -rf data/cache/cache.json || true
	# frontend
	cd $(FRONTDIR) && rm -rf node_modules .next dist out || true
	@echo "==> Limpieza completada."

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
	@echo "cd $(FRONTDIR) && npx concurrently \"$(PY) -m uvicorn bbva_bugresolutionradar.api.main:app --reload --host $(HOST) --port $(API_PORT)\" \"npm run dev\""
