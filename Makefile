SHELL := /bin/bash

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

HOST ?= 127.0.0.1
PORT ?= 8000

.DEFAULT_GOAL := help

help:
	@echo "Targets:"
	@echo "  make venv         - Create virtualenv"
	@echo "  make install      - Install runtime + tools (from requirements.txt) and project editable"
	@echo "  make env          - Create .env from .env.example if missing"
	@echo "  make ingest       - Run ingestion/consolidation"
	@echo "  make serve        - Run API server (uvicorn --reload)"
	@echo "  make format       - Format code (ruff format)"
	@echo "  make lint         - Lint (ruff check)"
	@echo "  make typecheck    - Type checks (mypy)"
	@echo "  make pyright      - Type checks (pyright) if Node is available"
	@echo "  make check        - format-check + lint + typecheck"
	@echo "  make pycheck      - Full checks (includes pyright if Node exists)"
	@echo "  make clean        - Remove venv and caches"

venv:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel

install: venv
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

env:
	@test -f .env || cp .env.example .env

ingest: env
	$(PY) -m bbva_bugresolutionradar.cli.main ingest

serve: env
	$(PY) -m uvicorn bbva_bugresolutionradar.api.main:app --reload --host $(HOST) --port $(PORT)

format:
	$(PY) -m ruff format .

format-check:
	$(PY) -m ruff format --check .

lint:
	$(PY) -m ruff check .

typecheck:
	$(PY) -m mypy .

pyright:
	@command -v node >/dev/null 2>&1 && $(PY) -m pyright || (echo "Skipping pyright: Node not found" && exit 0)

check: format-check lint typecheck

pycheck: check
	@command -v node >/dev/null 2>&1 && $(PY) -m pyright || echo "Skipping pyright: Node not found"

clean:
	rm -rf $(VENV) .mypy_cache .ruff_cache .pytest_cache
	rm -rf **/__pycache__