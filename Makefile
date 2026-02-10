# Makefile - Fullstack: Global Overview Radar
# Uso: make <target>
SHELL := /bin/bash

# Carga opcional de variables locales para Cloud Run (no versionado)
# (Antes: .env.cloudrun y referencias a cloudrun.enc; ahora: .env.reputation)
-include backend/reputation/.env.reputation

# --- Configuración general ---
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(PY) -m pip

FRONTDIR := frontend/brr-frontend
NPM := npm
NODE := node
NPM_INSTALL_CMD ?= install

ifneq ($(CI),)
NPM_INSTALL_CMD := ci
endif

HOST ?= 127.0.0.1
API_PORT ?= 8000
FRONT_PORT ?= 3000

# --- Cloud Run defaults (override via env) ---
GCP_PROJECT ?= global-overview-radar
GCP_REGION ?= europe-southwest1
BACKEND_SERVICE ?= gor-backend
FRONTEND_SERVICE ?= gor-frontend
FRONTEND_SA ?= gor-frontend-sa@$(GCP_PROJECT).iam.gserviceaccount.com
BACKEND_MAX_INSTANCES ?= 1
FRONTEND_MAX_INSTANCES ?= 1
BACKEND_CONCURRENCY ?= 2
FRONTEND_CONCURRENCY ?= 2
BACKEND_MEMORY ?= 768Mi
FRONTEND_MEMORY ?= 768Mi
BACKEND_CPU ?= 1
FRONTEND_CPU ?= 1
BACKEND_PYTHON_RUNTIME ?= 3.13

AUTH_GOOGLE_CLIENT_ID ?=
AUTH_ALLOWED_EMAILS ?=
AUTH_ALLOWED_DOMAINS ?= gmail.com
AUTH_ALLOWED_GROUPS ?=
NEXT_PUBLIC_ALLOWED_EMAILS ?= $(AUTH_ALLOWED_EMAILS)
NEXT_PUBLIC_ALLOWED_DOMAINS ?= $(AUTH_ALLOWED_DOMAINS)
CALLER_SERVICE_ACCOUNT ?= gor-github-deploy@$(GCP_PROJECT).iam.gserviceaccount.com
INGEST_FORCE ?= true
INGEST_ALL_SOURCES ?= false
INGEST_POLL_SECONDS ?= 10
INGEST_POLL_ATTEMPTS ?= 60

# CORS (Cloud Run backend)
# Recomendación: setear en backend/reputation/.env.reputation
# Ejemplos:
#   CORS_ALLOWED_ORIGIN_REGEX=^https://.*\\.run\\.app$$
#   CORS_ALLOWED_ORIGIN_REGEX=^https://(gor-frontend-[a-z0-9-]+\\.a\\.run\\.app|tu-dominio\\.com)$$
CORS_ALLOWED_ORIGIN_REGEX ?=

BENCH_DIR ?= docs/benchmarks
BENCH_ITERATIONS ?= 40
BENCH_WARMUP ?= 5
BENCH_MAX_REGRESSION ?= 0.15
BENCH_OUT_BACK ?= $(BENCH_DIR)/backend.latest.json
BENCH_BASELINE_BACK ?= $(BENCH_DIR)/backend.baseline.json

VISUAL_QA_URL ?= http://localhost:$(FRONT_PORT)
VISUAL_QA_OUT ?= docs/visual-qa

.DEFAULT_GOAL := help

.PHONY: help venv install install-backend install-front env ensure-backend ensure-front ingest ingest-filtered reputation-ingest reputation-ingest-filtered serve serve-back dev-back dev-front build-front start-front lint lint-back lint-front typecheck typecheck-back typecheck-front format format-back format-front check test test-back test-front test-coverage test-coverage-back test-coverage-front bench bench-baseline visual-qa clean reset cloudrun-config cloudrun-env deploy-cloudrun-back deploy-cloudrun-front deploy-cloudrun ingest-cloudrun

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
	@echo "  make ingest-filtered - Ejecutar ingesta de reputación respetando toggles"
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
	@echo "  make bench           - Benchmark backend (comparacion baseline)"
	@echo "  make bench-baseline  - Generar baseline backend"
	@echo "  make visual-qa       - Capturas headless mobile (frontend)"
	@echo "  make clean           - Eliminar venv, caches, node_modules (frontend)"
	@echo "  make cloudrun-config - Crear backend/reputation/.env.reputation (preguntas interactivas)"
	@echo "  make cloudrun-env    - Generar backend/reputation/cloudrun.env desde .env.reputation"
	@echo "  make deploy-cloudrun-back  - Deploy backend en Cloud Run (usa env vars)"
	@echo "  make deploy-cloudrun-front - Deploy frontend en Cloud Run (usa env vars + proxy /api)"
	@echo "  make deploy-cloudrun       - Deploy backend + frontend (Cloud Run)"
	@echo "  make ingest-cloudrun       - Lanzar ingesta remota en Cloud Run y esperar resultado"
	@echo ""
	@echo "Notas:"
	@echo " - Fullstack Cloud Run con backend privado: el frontend usa proxy /api hacia el backend"
	@echo " - Login OAuth: revisa en Google Cloud que exista redirect URI: https://<frontend>/login/callback"

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
	@if [ -f requirements-dev.txt ]; then \
		echo "==> Instalando dependencias dev (requirements-dev.txt)..."; \
		$(PIP) install -r requirements-dev.txt; \
	fi
	$(PIP) install -e backend

install-front:
	@echo "==> Instalando dependencias frontend (cd $(FRONTDIR))..."
	cd $(FRONTDIR) && $(NPM) $(NPM_INSTALL_CMD)
	@echo "==> Instalación frontend completada."

env:
	@# Create per-module env files from examples if missing
	@test -f backend/reputation/.env.reputation || cp backend/reputation/.env.reputation.example backend/reputation/.env.reputation
	@echo "==> .env files prepared (edit if needed)."

ensure-backend: install-backend
ensure-front: install-front
	@true

# -------------------------
# Cloud Run helpers
# -------------------------

cloudrun-config:
	@echo "==> Configurando backend/reputation/.env.reputation (se guarda local; idealmente gitignored)..."
	@mkdir -p backend/reputation
	@read -r -p "GCP_PROJECT [$(GCP_PROJECT)]: " GCP_PROJECT_IN; \
	GCP_PROJECT_VAL=$${GCP_PROJECT_IN:-$(GCP_PROJECT)}; \
	read -r -p "GCP_REGION [$(GCP_REGION)]: " GCP_REGION_IN; \
	GCP_REGION_VAL=$${GCP_REGION_IN:-$(GCP_REGION)}; \
	read -r -p "BACKEND_SERVICE [$(BACKEND_SERVICE)]: " BACKEND_SERVICE_IN; \
	BACKEND_SERVICE_VAL=$${BACKEND_SERVICE_IN:-$(BACKEND_SERVICE)}; \
	read -r -p "FRONTEND_SERVICE [$(FRONTEND_SERVICE)]: " FRONTEND_SERVICE_IN; \
	FRONTEND_SERVICE_VAL=$${FRONTEND_SERVICE_IN:-$(FRONTEND_SERVICE)}; \
	DEFAULT_FRONTEND_SA="gor-frontend-sa@$${GCP_PROJECT_VAL}.iam.gserviceaccount.com"; \
	read -r -p "FRONTEND_SA [$${DEFAULT_FRONTEND_SA}]: " FRONTEND_SA_IN; \
	FRONTEND_SA_VAL=$${FRONTEND_SA_IN:-$${DEFAULT_FRONTEND_SA}}; \
	read -r -p "AUTH_GOOGLE_CLIENT_ID (required): " AUTH_GOOGLE_CLIENT_ID_VAL; \
	if [ -z "$$AUTH_GOOGLE_CLIENT_ID_VAL" ]; then \
		echo "Falta AUTH_GOOGLE_CLIENT_ID."; \
		exit 1; \
	fi; \
	read -r -p "AUTH_ALLOWED_EMAILS (coma separada, opcional): " AUTH_ALLOWED_EMAILS_VAL; \
	read -r -p "AUTH_ALLOWED_DOMAINS [$(AUTH_ALLOWED_DOMAINS)]: " AUTH_ALLOWED_DOMAINS_IN; \
	AUTH_ALLOWED_DOMAINS_VAL=$${AUTH_ALLOWED_DOMAINS_IN:-$(AUTH_ALLOWED_DOMAINS)}; \
	read -r -p "AUTH_ALLOWED_GROUPS (coma separada, opcional): " AUTH_ALLOWED_GROUPS_VAL; \
	read -r -p "CORS_ALLOWED_ORIGIN_REGEX (required para Cloud Run backend): " CORS_ALLOWED_ORIGIN_REGEX_VAL; \
	if [ -z "$$CORS_ALLOWED_ORIGIN_REGEX_VAL" ]; then \
		echo "Falta CORS_ALLOWED_ORIGIN_REGEX."; \
		exit 1; \
	fi; \
	{ printf '%s\n' \
		"GCP_PROJECT=$${GCP_PROJECT_VAL}" \
		"GCP_REGION=$${GCP_REGION_VAL}" \
		"BACKEND_SERVICE=$${BACKEND_SERVICE_VAL}" \
		"FRONTEND_SERVICE=$${FRONTEND_SERVICE_VAL}" \
		"FRONTEND_SA=$${FRONTEND_SA_VAL}" \
		"AUTH_GOOGLE_CLIENT_ID=$${AUTH_GOOGLE_CLIENT_ID_VAL}" \
		"AUTH_ALLOWED_EMAILS=$${AUTH_ALLOWED_EMAILS_VAL}" \
		"AUTH_ALLOWED_DOMAINS=$${AUTH_ALLOWED_DOMAINS_VAL}" \
		"AUTH_ALLOWED_GROUPS=$${AUTH_ALLOWED_GROUPS_VAL}" \
		"NEXT_PUBLIC_ALLOWED_EMAILS=$${AUTH_ALLOWED_EMAILS_VAL}" \
		"NEXT_PUBLIC_ALLOWED_DOMAINS=$${AUTH_ALLOWED_DOMAINS_VAL}" \
		"CORS_ALLOWED_ORIGIN_REGEX=$${CORS_ALLOWED_ORIGIN_REGEX_VAL}"; \
	} > backend/reputation/.env.reputation
	@echo "==> backend/reputation/.env.reputation generado. Ahora puedes ejecutar: make deploy-cloudrun"

cloudrun-env:
	@echo "==> Generando backend/reputation/cloudrun.env desde backend/reputation/.env.reputation..."
	@test -f backend/reputation/.env.reputation || (echo "Falta backend/reputation/.env.reputation (ejecuta: make env o make cloudrun-config)"; exit 1)
	@mkdir -p backend/reputation
	@awk -F= '$$0 !~ /^[[:space:]]*#/ && $$0 ~ /=/ {print $$0}' backend/reputation/.env.reputation > backend/reputation/cloudrun.env

	@if ! grep -qE '^AUTH_GOOGLE_CLIENT_ID=' backend/reputation/cloudrun.env && [ -z "$(AUTH_GOOGLE_CLIENT_ID)" ]; then \
		echo "Falta AUTH_GOOGLE_CLIENT_ID (ponlo en backend/reputation/.env.reputation o exporta la variable)."; \
		exit 1; \
	fi
	@if ! grep -qE '^CORS_ALLOWED_ORIGIN_REGEX=' backend/reputation/cloudrun.env && [ -z "$(CORS_ALLOWED_ORIGIN_REGEX)" ]; then \
		echo "Falta CORS_ALLOWED_ORIGIN_REGEX (ponlo en backend/reputation/.env.reputation o exporta la variable)."; \
		exit 1; \
	fi

	@grep -q '^AUTH_ENABLED=' backend/reputation/cloudrun.env || echo "AUTH_ENABLED=true" >> backend/reputation/cloudrun.env

	@if [ -n "$(AUTH_GOOGLE_CLIENT_ID)" ] && ! grep -q '^AUTH_GOOGLE_CLIENT_ID=' backend/reputation/cloudrun.env; then \
		echo "AUTH_GOOGLE_CLIENT_ID=$(AUTH_GOOGLE_CLIENT_ID)" >> backend/reputation/cloudrun.env; \
	fi
	@if [ -n "$(AUTH_ALLOWED_EMAILS)" ] && ! grep -q '^AUTH_ALLOWED_EMAILS=' backend/reputation/cloudrun.env; then \
		echo "AUTH_ALLOWED_EMAILS=$(AUTH_ALLOWED_EMAILS)" >> backend/reputation/cloudrun.env; \
	fi
	@if [ -n "$(AUTH_ALLOWED_DOMAINS)" ] && ! grep -q '^AUTH_ALLOWED_DOMAINS=' backend/reputation/cloudrun.env; then \
		echo "AUTH_ALLOWED_DOMAINS=$(AUTH_ALLOWED_DOMAINS)" >> backend/reputation/cloudrun.env; \
	fi
	@if [ -n "$(AUTH_ALLOWED_GROUPS)" ] && ! grep -q '^AUTH_ALLOWED_GROUPS=' backend/reputation/cloudrun.env; then \
		echo "AUTH_ALLOWED_GROUPS=$(AUTH_ALLOWED_GROUPS)" >> backend/reputation/cloudrun.env; \
	fi
	@if [ -n "$(CORS_ALLOWED_ORIGIN_REGEX)" ] && ! grep -q '^CORS_ALLOWED_ORIGIN_REGEX=' backend/reputation/cloudrun.env; then \
		echo "CORS_ALLOWED_ORIGIN_REGEX=$(CORS_ALLOWED_ORIGIN_REGEX)" >> backend/reputation/cloudrun.env; \
	fi

	@echo "==> cloudrun.env generado."

deploy-cloudrun-back: cloudrun-env
	@echo "==> Deploy backend en Cloud Run..."
	@set -euo pipefail; \
	BUILD_VARS="GOOGLE_RUNTIME_VERSION=$(BACKEND_PYTHON_RUNTIME),GOOGLE_ENTRYPOINT=python -m uvicorn reputation.api.main:app --host 0.0.0.0 --port 8080"; \
	gcloud run deploy $(BACKEND_SERVICE) \
		--project $(GCP_PROJECT) \
		--region $(GCP_REGION) \
		--source backend \
		--no-allow-unauthenticated \
		--min-instances 0 \
		--max-instances $(BACKEND_MAX_INSTANCES) \
		--concurrency $(BACKEND_CONCURRENCY) \
		--cpu $(BACKEND_CPU) \
		--memory $(BACKEND_MEMORY) \
		--cpu-throttling \
		--set-build-env-vars "$$BUILD_VARS" \
		--env-vars-file backend/reputation/cloudrun.env

deploy-cloudrun-front:
	@echo "==> Deploy frontend en Cloud Run (proxy /api -> backend)..."
	@if [ -z "$(AUTH_GOOGLE_CLIENT_ID)" ]; then \
		echo "Falta AUTH_GOOGLE_CLIENT_ID (ponlo en backend/reputation/.env.reputation o exporta la variable)."; \
		exit 1; \
	fi
	@if ! echo "$(AUTH_GOOGLE_CLIENT_ID)" | grep -q '\.apps\.googleusercontent\.com$$'; then \
		echo "ERROR: AUTH_GOOGLE_CLIENT_ID debe ser un OAuth Client ID (termina en .apps.googleusercontent.com). Valor actual: $(AUTH_GOOGLE_CLIENT_ID)"; \
		exit 1; \
	fi
	@BACKEND_URL=$$(gcloud run services describe $(BACKEND_SERVICE) --project $(GCP_PROJECT) --region $(GCP_REGION) --format 'value(status.url)'); \
	if [ -z "$$BACKEND_URL" ]; then \
		echo "No se pudo obtener BACKEND_URL. Deploy del backend primero."; \
		exit 1; \
	fi; \
	gcloud run deploy $(FRONTEND_SERVICE) \
		--project $(GCP_PROJECT) \
		--region $(GCP_REGION) \
		--source frontend/brr-frontend \
		--service-account $(FRONTEND_SA) \
		--allow-unauthenticated \
		--min-instances 0 \
		--max-instances $(FRONTEND_MAX_INSTANCES) \
		--concurrency $(FRONTEND_CONCURRENCY) \
		--cpu $(FRONTEND_CPU) \
		--memory $(FRONTEND_MEMORY) \
		--cpu-throttling \
		--set-env-vars USE_SERVER_PROXY=true,API_PROXY_TARGET=$$BACKEND_URL,NEXT_PUBLIC_API_BASE_URL=/api,NEXT_PUBLIC_AUTH_ENABLED=true,NEXT_PUBLIC_GOOGLE_CLIENT_ID=$(AUTH_GOOGLE_CLIENT_ID),NEXT_PUBLIC_ALLOWED_EMAILS=$(NEXT_PUBLIC_ALLOWED_EMAILS),NEXT_PUBLIC_ALLOWED_DOMAINS=$(NEXT_PUBLIC_ALLOWED_DOMAINS) \
		--set-build-env-vars USE_SERVER_PROXY=true,API_PROXY_TARGET=$$BACKEND_URL,NEXT_PUBLIC_API_BASE_URL=/api,NEXT_PUBLIC_AUTH_ENABLED=true,NEXT_PUBLIC_GOOGLE_CLIENT_ID=$(AUTH_GOOGLE_CLIENT_ID),NEXT_PUBLIC_ALLOWED_EMAILS=$(NEXT_PUBLIC_ALLOWED_EMAILS),NEXT_PUBLIC_ALLOWED_DOMAINS=$(NEXT_PUBLIC_ALLOWED_DOMAINS)

deploy-cloudrun: deploy-cloudrun-back deploy-cloudrun-front
	@true

ingest-cloudrun:
	@echo "==> Lanzando ingesta remota en Cloud Run ($(BACKEND_SERVICE))..."
	@set -euo pipefail; \
	if [ -z "$(AUTH_GOOGLE_CLIENT_ID)" ]; then \
		echo "Falta AUTH_GOOGLE_CLIENT_ID (ponlo en backend/reputation/.env.reputation o exporta la variable)."; \
		exit 1; \
	fi; \
	BACKEND_URL=$$(gcloud run services describe $(BACKEND_SERVICE) --project $(GCP_PROJECT) --region $(GCP_REGION) --format 'value(status.url)'); \
	if [ -z "$$BACKEND_URL" ]; then \
		echo "No se pudo obtener BACKEND_URL. Verifica deploy del backend y permisos."; \
		exit 1; \
	fi; \
	TOKEN_FLAGS=(); \
	if [ -n "$(CALLER_SERVICE_ACCOUNT)" ]; then \
		TOKEN_FLAGS+=(--impersonate-service-account "$(CALLER_SERVICE_ACCOUNT)"); \
		echo "Usando impersonacion SA: $(CALLER_SERVICE_ACCOUNT)"; \
	fi; \
	RUN_TOKEN=$$(gcloud auth print-identity-token "$${TOKEN_FLAGS[@]}" --audiences="$$BACKEND_URL"); \
	USER_TOKEN=$$(gcloud auth print-identity-token "$${TOKEN_FLAGS[@]}" --audiences="$(AUTH_GOOGLE_CLIENT_ID)" --include-email); \
	PAYLOAD="{\"force\":$(INGEST_FORCE),\"all_sources\":$(INGEST_ALL_SOURCES)}"; \
	RESPONSE=$$(curl -sS -f -X POST "$$BACKEND_URL/ingest/reputation" \
		-H "Authorization: Bearer $$RUN_TOKEN" \
		-H "x-user-id-token: $$USER_TOKEN" \
		-H "Content-Type: application/json" \
		-d "$$PAYLOAD"); \
	JOB_ID=$$(printf '%s' "$$RESPONSE" | python3 -c 'import json,sys; print((json.loads(sys.stdin.read() or "{}")).get("id",""))'); \
	if [ -z "$$JOB_ID" ]; then \
		echo "No se recibio job id. Respuesta:"; \
		echo "$$RESPONSE"; \
		exit 1; \
	fi; \
	echo "Ingest job id: $$JOB_ID"; \
	ATTEMPT=1; \
	while [ "$$ATTEMPT" -le "$(INGEST_POLL_ATTEMPTS)" ]; do \
		JOB=$$(curl -sS -f "$$BACKEND_URL/ingest/jobs/$$JOB_ID" \
			-H "Authorization: Bearer $$RUN_TOKEN" \
			-H "x-user-id-token: $$USER_TOKEN"); \
		STATUS=$$(printf '%s' "$$JOB" | python3 -c 'import json,sys; print((json.loads(sys.stdin.read() or "{}")).get("status",""))'); \
		PROGRESS=$$(printf '%s' "$$JOB" | python3 -c 'import json,sys; print((json.loads(sys.stdin.read() or "{}")).get("progress",""))'); \
		STAGE=$$(printf '%s' "$$JOB" | python3 -c 'import json,sys; print((json.loads(sys.stdin.read() or "{}")).get("stage",""))'); \
		echo "[$$ATTEMPT/$(INGEST_POLL_ATTEMPTS)] status=$$STATUS progress=$$PROGRESS stage=$$STAGE"; \
		if [ "$$STATUS" = "success" ]; then \
			echo "==> Ingesta completada."; \
			echo "$$JOB"; \
			exit 0; \
		fi; \
		if [ "$$STATUS" = "error" ]; then \
			echo "==> Ingesta fallida."; \
			echo "$$JOB"; \
			exit 1; \
		fi; \
		ATTEMPT=$$((ATTEMPT + 1)); \
		sleep $(INGEST_POLL_SECONDS); \
	done; \
	echo "Timeout esperando la ingesta remota."; \
	exit 1

# -------------------------
# Backend runtime
# -------------------------
ingest: reputation-ingest
	@echo "==> Ingesta reputacional finalizada."

reputation-ingest:
	@echo "==> Ejecutando ingesta de reputación..."
	$(PY) -m reputation.cli --all-sources

ingest-filtered: reputation-ingest-filtered
	@echo "==> Ingesta reputacional finalizada."

reputation-ingest-filtered:
	@echo "==> Ejecutando ingesta de reputación (toggles .env.reputation)..."
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
	$(PY) -m mypy --config-file backend/pyproject.toml backend
	$(PY) -m pyright

typecheck-front:
	@echo "==> Typecheck frontend (next / tsc)..."
	cd $(FRONTDIR) && NEXT_DISABLE_TURBOPACK=1 $(NPM) run build --if-present || true

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
	cd $(FRONTDIR) && CI=1 $(NPM) run test

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
	@echo "==> Benchmark backend..."
	@mkdir -p $(BENCH_DIR)
	$(PY) scripts/bench_backend.py --iterations $(BENCH_ITERATIONS) --warmup $(BENCH_WARMUP) --json $(BENCH_OUT_BACK) --baseline $(BENCH_BASELINE_BACK) --max-regression $(BENCH_MAX_REGRESSION)

bench-baseline:
	@echo "==> Generando baseline de benchmark..."
	@mkdir -p $(BENCH_DIR)
	$(PY) scripts/bench_backend.py --iterations $(BENCH_ITERATIONS) --warmup $(BENCH_WARMUP) --json $(BENCH_BASELINE_BACK)

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
	cd $(FRONTDIR) && rm -rf node_modules .next dist out || true
	@echo "==> Limpieza completada."

reset: clean install
	@echo "==> Reset completo finalizado."

dev:
	@echo "==> Para desarrollo fullstack abre 2 terminales y ejecuta:"
	@echo "- Terminal A: make dev-back"
	@echo "- Terminal B: make dev-front"
	@echo ""
	@echo "Si quieres hacerlo todo en un solo terminal instala 'concurrently' y ejecuta:"
	@echo "cd $(FRONTDIR) && npx concurrently \"$(PY) -m uvicorn reputation.api.main:app --reload --host $(HOST) --port $(API_PORT)\" \"npm run dev\""
