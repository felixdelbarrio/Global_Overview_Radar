# Makefile - Fullstack: Global Overview Radar
# Uso: make <target>
SHELL := /bin/bash

# Cloud Run targets read backend/reputation/cloudrun.env (dotenv format).
# Do NOT -include dotenv files in Make: values may contain `$` and would be expanded by Make.

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

# --- Cloud Run knobs (non-secret) ---
BACKEND_MAX_INSTANCES ?= 1
FRONTEND_MAX_INSTANCES ?= 1
BACKEND_CONCURRENCY ?= 2
FRONTEND_CONCURRENCY ?= 2
BACKEND_MEMORY ?= 768Mi
FRONTEND_MEMORY ?= 768Mi
BACKEND_CPU ?= 1
FRONTEND_CPU ?= 1
BACKEND_PYTHON_RUNTIME ?= 3.13

INGEST_FORCE ?= true
INGEST_ALL_SOURCES ?= false
INGEST_POLL_SECONDS ?= 10
INGEST_POLL_ATTEMPTS ?= 60

BENCH_DIR ?= docs/benchmarks
BENCH_ITERATIONS ?= 40
BENCH_WARMUP ?= 5
BENCH_MAX_REGRESSION ?= 0.15
BENCH_OUT_BACK ?= $(BENCH_DIR)/backend.latest.json
BENCH_BASELINE_BACK ?= $(BENCH_DIR)/backend.baseline.json

VISUAL_QA_URL ?= http://localhost:$(FRONT_PORT)
VISUAL_QA_OUT ?= docs/visual-qa

.DEFAULT_GOAL := help

.PHONY: help venv install install-backend install-front env ensure-backend ensure-front ensure-cloudrun-env ingest ingest-filtered reputation-ingest reputation-ingest-filtered serve serve-back dev-back dev-front build-front start-front lint lint-back lint-front typecheck typecheck-back typecheck-front format format-back format-front check codeql codeql-install codeql-python codeql-js codeql-clean test test-back test-front test-coverage test-coverage-back test-coverage-front bench bench-baseline visual-qa clean reset cloudrun-config cloudrun-env deploy-cloudrun-back deploy-cloudrun-front deploy-cloudrun ingest-cloudrun

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
	@echo "  make codeql          - Analisis CodeQL local (requiere CodeQL CLI)"
	@echo "  make test            - Ejecutar tests (si existen)"
	@echo "  make test-back       - Ejecutar tests backend (pytest + cobertura)"
	@echo "  make test-front      - Ejecutar tests frontend (vitest)"
	@echo "  make test-coverage   - Ejecutar cobertura backend + frontend (>=70%)"
	@echo "  make bench           - Benchmark backend (comparacion baseline)"
	@echo "  make bench-baseline  - Generar baseline backend"
	@echo "  make visual-qa       - Capturas headless mobile (frontend)"
	@echo "  make clean           - Eliminar venv, caches, node_modules (frontend)"
	@echo "  make cloudrun-config - Configurar backend/reputation/cloudrun.env (preguntas interactivas)"
	@echo "  make cloudrun-env    - Validar/normalizar backend/reputation/cloudrun.env"
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
	$(PIP) install -r requirements.txt
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

ensure-cloudrun-env:
	@mkdir -p backend/reputation
	@test -f backend/reputation/cloudrun.env || cp backend/reputation/cloudrun.env.example backend/reputation/cloudrun.env
	@echo "==> backend/reputation/cloudrun.env preparado."

cloudrun-config: ensure-cloudrun-env
	@echo "==> Configurando backend/reputation/cloudrun.env..."
	@set -euo pipefail; \
	ENV_FILE="backend/reputation/cloudrun.env"; \
	env_get() { awk -F= -v k="$$1" '$$0 ~ ("^"k"=") {print substr($$0,index($$0,"=")+1)}' "$$ENV_FILE" | tail -n1; }; \
	DEFAULT_GCP_PROJECT="global-overview-radar"; \
	DEFAULT_GCP_REGION="europe-southwest1"; \
	DEFAULT_BACKEND_SERVICE="gor-backend"; \
	DEFAULT_FRONTEND_SERVICE="gor-frontend"; \
	GCP_PROJECT_DEFAULT="$$(env_get GCP_PROJECT)"; \
	GCP_PROJECT_DEFAULT="$${GCP_PROJECT_DEFAULT:-$$DEFAULT_GCP_PROJECT}"; \
	read -r -p "GCP_PROJECT [$$GCP_PROJECT_DEFAULT]: " GCP_PROJECT_IN; \
	GCP_PROJECT_VAL="$${GCP_PROJECT_IN:-$$GCP_PROJECT_DEFAULT}"; \
	GCP_REGION_DEFAULT="$$(env_get GCP_REGION)"; \
	GCP_REGION_DEFAULT="$${GCP_REGION_DEFAULT:-$$DEFAULT_GCP_REGION}"; \
	read -r -p "GCP_REGION [$$GCP_REGION_DEFAULT]: " GCP_REGION_IN; \
	GCP_REGION_VAL="$${GCP_REGION_IN:-$$GCP_REGION_DEFAULT}"; \
	BACKEND_SERVICE_DEFAULT="$$(env_get BACKEND_SERVICE)"; \
	BACKEND_SERVICE_DEFAULT="$${BACKEND_SERVICE_DEFAULT:-$$DEFAULT_BACKEND_SERVICE}"; \
	read -r -p "BACKEND_SERVICE [$$BACKEND_SERVICE_DEFAULT]: " BACKEND_SERVICE_IN; \
	BACKEND_SERVICE_VAL="$${BACKEND_SERVICE_IN:-$$BACKEND_SERVICE_DEFAULT}"; \
	BACKEND_SA_DEFAULT="$$(env_get BACKEND_SA)"; \
	if [ -z "$$BACKEND_SA_DEFAULT" ]; then BACKEND_SA_DEFAULT="gor-backend-sa@$${GCP_PROJECT_VAL}.iam.gserviceaccount.com"; fi; \
	read -r -p "BACKEND_SA [$$BACKEND_SA_DEFAULT]: " BACKEND_SA_IN; \
	BACKEND_SA_VAL="$${BACKEND_SA_IN:-$$BACKEND_SA_DEFAULT}"; \
	FRONTEND_SERVICE_DEFAULT="$$(env_get FRONTEND_SERVICE)"; \
	FRONTEND_SERVICE_DEFAULT="$${FRONTEND_SERVICE_DEFAULT:-$$DEFAULT_FRONTEND_SERVICE}"; \
	read -r -p "FRONTEND_SERVICE [$$FRONTEND_SERVICE_DEFAULT]: " FRONTEND_SERVICE_IN; \
	FRONTEND_SERVICE_VAL="$${FRONTEND_SERVICE_IN:-$$FRONTEND_SERVICE_DEFAULT}"; \
	FRONTEND_SA_DEFAULT="$$(env_get FRONTEND_SA)"; \
	if [ -z "$$FRONTEND_SA_DEFAULT" ]; then FRONTEND_SA_DEFAULT="gor-frontend-sa@$${GCP_PROJECT_VAL}.iam.gserviceaccount.com"; fi; \
	read -r -p "FRONTEND_SA [$$FRONTEND_SA_DEFAULT]: " FRONTEND_SA_IN; \
	FRONTEND_SA_VAL="$${FRONTEND_SA_IN:-$$FRONTEND_SA_DEFAULT}"; \
	LOGIN_REQ_DEFAULT="$$(env_get GOOGLE_CLOUD_LOGIN_REQUESTED)"; \
	LOGIN_REQ_DEFAULT="$${LOGIN_REQ_DEFAULT:-false}"; \
	read -r -p "GOOGLE_CLOUD_LOGIN_REQUESTED (true/false) [$$LOGIN_REQ_DEFAULT]: " GOOGLE_CLOUD_LOGIN_REQUESTED_IN; \
	GOOGLE_CLOUD_LOGIN_REQUESTED_VAL="$$(echo "$${GOOGLE_CLOUD_LOGIN_REQUESTED_IN:-$$LOGIN_REQ_DEFAULT}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"; \
	if [ "$$GOOGLE_CLOUD_LOGIN_REQUESTED_VAL" != "true" ]; then GOOGLE_CLOUD_LOGIN_REQUESTED_VAL="false"; fi; \
	CLIENT_ID_DEFAULT="$$(env_get AUTH_GOOGLE_CLIENT_ID)"; \
	read -r -p "AUTH_GOOGLE_CLIENT_ID [$$CLIENT_ID_DEFAULT]: " AUTH_GOOGLE_CLIENT_ID_IN; \
	AUTH_GOOGLE_CLIENT_ID_VAL="$${AUTH_GOOGLE_CLIENT_ID_IN:-$$CLIENT_ID_DEFAULT}"; \
	ALLOWED_EMAILS_DEFAULT="$$(env_get AUTH_ALLOWED_EMAILS)"; \
	read -r -p "AUTH_ALLOWED_EMAILS (coma separada) [$$ALLOWED_EMAILS_DEFAULT]: " AUTH_ALLOWED_EMAILS_IN; \
	AUTH_ALLOWED_EMAILS_VAL="$${AUTH_ALLOWED_EMAILS_IN:-$$ALLOWED_EMAILS_DEFAULT}"; \
		STATE_BUCKET_DEFAULT="$$(env_get REPUTATION_STATE_BUCKET)"; \
		if [ -z "$$STATE_BUCKET_DEFAULT" ]; then STATE_BUCKET_DEFAULT="$${GCP_PROJECT_VAL}-reputation-state"; fi; \
		read -r -p "REPUTATION_STATE_BUCKET [$$STATE_BUCKET_DEFAULT]: " REPUTATION_STATE_BUCKET_IN; \
		REPUTATION_STATE_BUCKET_VAL="$${REPUTATION_STATE_BUCKET_IN:-$$STATE_BUCKET_DEFAULT}"; \
		REPUTATION_STATE_PREFIX_VAL="reputation-state"; \
	if [ "$$GOOGLE_CLOUD_LOGIN_REQUESTED_VAL" = "true" ] && [ -z "$$AUTH_GOOGLE_CLIENT_ID_VAL" ]; then \
		echo "Falta AUTH_GOOGLE_CLIENT_ID (required cuando GOOGLE_CLOUD_LOGIN_REQUESTED=true)."; \
		exit 1; \
	fi; \
	if [ "$$GOOGLE_CLOUD_LOGIN_REQUESTED_VAL" = "true" ] && [ -z "$$AUTH_ALLOWED_EMAILS_VAL" ]; then \
		echo "Falta AUTH_ALLOWED_EMAILS (required cuando GOOGLE_CLOUD_LOGIN_REQUESTED=true)."; \
		exit 1; \
	fi; \
	if [ -z "$$REPUTATION_STATE_BUCKET_VAL" ]; then \
		echo "Falta REPUTATION_STATE_BUCKET (persistencia durable requerida en Cloud Run)."; \
		exit 1; \
	fi; \
	TMP_FILE="$$ENV_FILE.tmp"; \
	grep -vE '^(GCP_PROJECT|GCP_REGION|BACKEND_SERVICE|BACKEND_SA|FRONTEND_SERVICE|FRONTEND_SA|GOOGLE_CLOUD_LOGIN_REQUESTED|AUTH_GOOGLE_CLIENT_ID|AUTH_ALLOWED_EMAILS|REPUTATION_STATE_BUCKET|REPUTATION_STATE_PREFIX)=' "$$ENV_FILE" > "$$TMP_FILE" || true; \
	mv "$$TMP_FILE" "$$ENV_FILE"; \
	{ printf '\n# --- Cloud Run (generated by make cloudrun-config) ---\n'; \
		printf '%s\n' \
			"GCP_PROJECT=$${GCP_PROJECT_VAL}" \
			"GCP_REGION=$${GCP_REGION_VAL}" \
			"BACKEND_SERVICE=$${BACKEND_SERVICE_VAL}" \
			"BACKEND_SA=$${BACKEND_SA_VAL}" \
			"FRONTEND_SERVICE=$${FRONTEND_SERVICE_VAL}" \
			"FRONTEND_SA=$${FRONTEND_SA_VAL}" \
			"GOOGLE_CLOUD_LOGIN_REQUESTED=$${GOOGLE_CLOUD_LOGIN_REQUESTED_VAL}" \
			"AUTH_GOOGLE_CLIENT_ID=$${AUTH_GOOGLE_CLIENT_ID_VAL}" \
			"AUTH_ALLOWED_EMAILS=$${AUTH_ALLOWED_EMAILS_VAL}" \
			"REPUTATION_STATE_BUCKET=$${REPUTATION_STATE_BUCKET_VAL}" \
			"REPUTATION_STATE_PREFIX=$${REPUTATION_STATE_PREFIX_VAL}"; \
		} >> "$$ENV_FILE"; \
		if [ "$$GOOGLE_CLOUD_LOGIN_REQUESTED_VAL" != "true" ]; then \
			echo "INFO: Modo bypass activo. No se requiere clave admin adicional."; \
		fi; \
		echo "==> backend/reputation/cloudrun.env actualizado. Ahora puedes ejecutar: make deploy-cloudrun"

cloudrun-env: ensure-cloudrun-env
	@echo "==> Validando backend/reputation/cloudrun.env..."
	@set -euo pipefail; \
	ENV_FILE="backend/reputation/cloudrun.env"; \
	env_get() { awk -F= -v k="$$1" '$$0 ~ ("^"k"=") {print substr($$0,index($$0,"=")+1)}' "$$ENV_FILE" | tail -n1; }; \
	LOGIN_REQUESTED_VAL="$$(env_get GOOGLE_CLOUD_LOGIN_REQUESTED)"; \
	LOGIN_REQUESTED_VAL="$$(echo "$$LOGIN_REQUESTED_VAL" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"; \
	if [ "$$LOGIN_REQUESTED_VAL" != "true" ]; then LOGIN_REQUESTED_VAL="false"; fi; \
	CLIENT_ID_VAL="$${AUTH_GOOGLE_CLIENT_ID:-$$(env_get AUTH_GOOGLE_CLIENT_ID)}"; \
	ALLOWED_EMAILS_VAL="$${AUTH_ALLOWED_EMAILS:-$$(env_get AUTH_ALLOWED_EMAILS)}"; \
	STATE_BUCKET_VAL="$${REPUTATION_STATE_BUCKET:-$$(env_get REPUTATION_STATE_BUCKET)}"; \
	CLIENT_ID_VAL="$$(printf '%s' "$$CLIENT_ID_VAL" | tr -d '\r')"; \
	ALLOWED_EMAILS_VAL="$$(printf '%s' "$$ALLOWED_EMAILS_VAL" | tr -d '\r')"; \
	STATE_BUCKET_VAL="$$(printf '%s' "$$STATE_BUCKET_VAL" | tr -d '\r')"; \
	STATE_PREFIX_VAL="reputation-state"; \
	if [ -z "$$STATE_BUCKET_VAL" ]; then \
		echo "Falta REPUTATION_STATE_BUCKET (ponlo en backend/reputation/cloudrun.env)."; \
		exit 1; \
	fi; \
		if [ "$$LOGIN_REQUESTED_VAL" = "true" ]; then \
		if [ -z "$$CLIENT_ID_VAL" ]; then \
			echo "Falta AUTH_GOOGLE_CLIENT_ID (ponlo en backend/reputation/cloudrun.env)."; \
			exit 1; \
		fi; \
		if [ -z "$$ALLOWED_EMAILS_VAL" ]; then \
			echo "Falta AUTH_ALLOWED_EMAILS (required cuando GOOGLE_CLOUD_LOGIN_REQUESTED=true)."; \
			exit 1; \
		fi; \
		if ! echo "$$CLIENT_ID_VAL" | grep -q '\\.apps\\.googleusercontent\\.com$$'; then \
			echo "ERROR: AUTH_GOOGLE_CLIENT_ID debe ser un OAuth Client ID (termina en .apps.googleusercontent.com). Valor actual: $$CLIENT_ID_VAL"; \
			exit 1; \
		fi; \
		else \
			echo "INFO: GOOGLE_CLOUD_LOGIN_REQUESTED=false; el backend operara en modo bypass."; \
		fi; \
	TMP_FILE="$$ENV_FILE.tmp"; \
	awk '$$0 !~ /^(AUTH_GOOGLE_CLIENT_ID|AUTH_ALLOWED_EMAILS|GOOGLE_CLOUD_LOGIN_REQUESTED|REPUTATION_STATE_BUCKET|REPUTATION_STATE_PREFIX)=/' "$$ENV_FILE" > "$$TMP_FILE"; \
	mv "$$TMP_FILE" "$$ENV_FILE"; \
	{ printf '\n# --- Auth/Cloud Run (normalized by make cloudrun-env) ---\n'; \
		printf '%s\n' \
			"GOOGLE_CLOUD_LOGIN_REQUESTED=$$LOGIN_REQUESTED_VAL"; \
		if [ -n "$$CLIENT_ID_VAL" ]; then printf '%s\n' "AUTH_GOOGLE_CLIENT_ID=$$CLIENT_ID_VAL"; fi; \
		if [ -n "$$ALLOWED_EMAILS_VAL" ]; then printf '%s\n' "AUTH_ALLOWED_EMAILS=$$ALLOWED_EMAILS_VAL"; fi; \
		printf '%s\n' "REPUTATION_STATE_BUCKET=$$STATE_BUCKET_VAL"; \
		printf '%s\n' "REPUTATION_STATE_PREFIX=$$STATE_PREFIX_VAL"; \
	} >> "$$ENV_FILE"

	@echo "==> cloudrun.env validado."

deploy-cloudrun-back: cloudrun-env
	@echo "==> Deploy backend en Cloud Run..."
	@set -euo pipefail; \
	ENV_FILE="backend/reputation/cloudrun.env"; \
	env_get() { awk -F= -v k="$$1" '$$0 ~ ("^"k"=") {print substr($$0,index($$0,"=")+1)}' "$$ENV_FILE" | tail -n1; }; \
	GCP_PROJECT="$${GCP_PROJECT:-$$(env_get GCP_PROJECT)}"; \
	GCP_PROJECT="$${GCP_PROJECT:-global-overview-radar}"; \
	GCP_REGION="$${GCP_REGION:-$$(env_get GCP_REGION)}"; \
	GCP_REGION="$${GCP_REGION:-europe-southwest1}"; \
	BACKEND_SERVICE="$${BACKEND_SERVICE:-$$(env_get BACKEND_SERVICE)}"; \
	BACKEND_SERVICE="$${BACKEND_SERVICE:-gor-backend}"; \
	BACKEND_SA="$${BACKEND_SA:-$$(env_get BACKEND_SA)}"; \
	if [ -z "$$BACKEND_SA" ]; then \
		PROJECT_NUMBER=$$(gcloud projects describe "$$GCP_PROJECT" --format='value(projectNumber)'); \
		BACKEND_SA="$$PROJECT_NUMBER-compute@developer.gserviceaccount.com"; \
	fi; \
	unset CLOUDSDK_RUN_DEPLOY_ENV_VARS_FILE CLOUDSDK_RUN_DEPLOY_SET_ENV_VARS CLOUDSDK_RUN_DEPLOY_UPDATE_ENV_VARS CLOUDSDK_RUN_DEPLOY_REMOVE_ENV_VARS CLOUDSDK_RUN_DEPLOY_CLEAR_ENV_VARS; \
	mkdir -p backend/data; \
	rsync -a --delete data/reputation/ backend/data/reputation/; \
	rsync -a --delete data/reputation_llm/ backend/data/reputation_llm/; \
	rsync -a --delete data/reputation_samples/ backend/data/reputation_samples/; \
	rsync -a --delete data/reputation_llm_samples/ backend/data/reputation_llm_samples/; \
	BUILD_VARS="GOOGLE_RUNTIME_VERSION=$(BACKEND_PYTHON_RUNTIME),GOOGLE_ENTRYPOINT=python -m uvicorn reputation.api.main:app --host 0.0.0.0 --port 8080"; \
	gcloud run deploy "$$BACKEND_SERVICE" \
	--project "$$GCP_PROJECT" \
	--region "$$GCP_REGION" \
	--source backend \
	--service-account "$$BACKEND_SA" \
	--no-allow-unauthenticated \
	--min-instances 0 \
	--max-instances $(BACKEND_MAX_INSTANCES) \
		--concurrency $(BACKEND_CONCURRENCY) \
		--cpu $(BACKEND_CPU) \
		--memory $(BACKEND_MEMORY) \
		--cpu-throttling \
		--set-build-env-vars "$$BUILD_VARS" \
		--env-vars-file "$$ENV_FILE"; \
	gcloud run services update-traffic "$$BACKEND_SERVICE" \
		--project "$$GCP_PROJECT" \
	--region "$$GCP_REGION" \
	--to-latest

deploy-cloudrun-front: cloudrun-env
	@echo "==> Deploy frontend en Cloud Run (proxy /api -> backend)..."
	@set -euo pipefail; \
	ENV_FILE="backend/reputation/cloudrun.env"; \
	test -f "$$ENV_FILE" || (echo "Falta $$ENV_FILE (ejecuta: make cloudrun-env)"; exit 1); \
	env_get() { awk -F= -v k="$$1" '$$0 ~ ("^"k"=") {print substr($$0,index($$0,"=")+1)}' "$$ENV_FILE" | tail -n1; }; \
	GCP_PROJECT="$${GCP_PROJECT:-$$(env_get GCP_PROJECT)}"; \
	GCP_PROJECT="$${GCP_PROJECT:-global-overview-radar}"; \
	GCP_REGION="$${GCP_REGION:-$$(env_get GCP_REGION)}"; \
	GCP_REGION="$${GCP_REGION:-europe-southwest1}"; \
	BACKEND_SERVICE="$${BACKEND_SERVICE:-$$(env_get BACKEND_SERVICE)}"; \
	BACKEND_SERVICE="$${BACKEND_SERVICE:-gor-backend}"; \
	FRONTEND_SERVICE="$${FRONTEND_SERVICE:-$$(env_get FRONTEND_SERVICE)}"; \
	FRONTEND_SERVICE="$${FRONTEND_SERVICE:-gor-frontend}"; \
	FRONTEND_SA="$${FRONTEND_SA:-$$(env_get FRONTEND_SA)}"; \
	if [ -z "$$FRONTEND_SA" ]; then FRONTEND_SA="gor-frontend-sa@$${GCP_PROJECT}.iam.gserviceaccount.com"; fi; \
	LOGIN_REQUESTED_VAL="$$(env_get GOOGLE_CLOUD_LOGIN_REQUESTED)"; \
	LOGIN_REQUESTED_VAL=$$(echo "$$LOGIN_REQUESTED_VAL" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]'); \
	if [ "$$LOGIN_REQUESTED_VAL" != "true" ]; then LOGIN_REQUESTED_VAL="false"; fi; \
	CLIENT_ID_VAL="$$(env_get AUTH_GOOGLE_CLIENT_ID)"; \
	CLIENT_ID_VAL=$$(printf '%s' "$$CLIENT_ID_VAL" | tr -d '\r'); \
	if [ "$$LOGIN_REQUESTED_VAL" = "true" ]; then \
		if [ -z "$$CLIENT_ID_VAL" ]; then \
			echo "Falta AUTH_GOOGLE_CLIENT_ID (ponlo en backend/reputation/cloudrun.env)."; \
			exit 1; \
		fi; \
		if ! echo "$$CLIENT_ID_VAL" | grep -q '\\.apps\\.googleusercontent\\.com$$'; then \
			echo "ERROR: AUTH_GOOGLE_CLIENT_ID debe ser un OAuth Client ID (termina en .apps.googleusercontent.com). Valor actual: $$CLIENT_ID_VAL"; \
			exit 1; \
		fi; \
	fi; \
	BACKEND_URL=$$(gcloud run services describe "$$BACKEND_SERVICE" --project "$$GCP_PROJECT" --region "$$GCP_REGION" --format 'value(status.url)'); \
	if [ -z "$$BACKEND_URL" ]; then \
		echo "No se pudo obtener BACKEND_URL. Deploy del backend primero."; \
		exit 1; \
	fi; \
	gcloud run deploy "$$FRONTEND_SERVICE" \
		--project "$$GCP_PROJECT" \
		--region "$$GCP_REGION" \
		--source frontend/brr-frontend \
		--service-account "$$FRONTEND_SA" \
		--allow-unauthenticated \
		--min-instances 0 \
		--max-instances $(FRONTEND_MAX_INSTANCES) \
		--concurrency $(FRONTEND_CONCURRENCY) \
		--cpu $(FRONTEND_CPU) \
		--memory $(FRONTEND_MEMORY) \
		--cpu-throttling \
		--set-env-vars USE_SERVER_PROXY=true,API_PROXY_TARGET=$$BACKEND_URL,NEXT_PUBLIC_API_BASE_URL=/api,NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED=$$LOGIN_REQUESTED_VAL,AUTH_GOOGLE_CLIENT_ID=$$CLIENT_ID_VAL,NEXT_PUBLIC_DISABLE_ADVANCED_SETTINGS=true \
		--set-build-env-vars USE_SERVER_PROXY=true,API_PROXY_TARGET=$$BACKEND_URL,NEXT_PUBLIC_API_BASE_URL=/api,NEXT_PUBLIC_GOOGLE_CLOUD_LOGIN_REQUESTED=$$LOGIN_REQUESTED_VAL,AUTH_GOOGLE_CLIENT_ID=$$CLIENT_ID_VAL,NEXT_PUBLIC_DISABLE_ADVANCED_SETTINGS=true

deploy-cloudrun: deploy-cloudrun-back deploy-cloudrun-front
	@true

ingest-cloudrun: cloudrun-env
	@set -euo pipefail; \
	ENV_FILE="backend/reputation/cloudrun.env"; \
	test -f "$$ENV_FILE" || (echo "Falta $$ENV_FILE (ejecuta: make cloudrun-env)"; exit 1); \
	env_get() { awk -F= -v k="$$1" '$$0 ~ ("^"k"=") {print substr($$0,index($$0,"=")+1)}' "$$ENV_FILE" | tail -n1; }; \
	GCP_PROJECT="$${GCP_PROJECT:-$$(env_get GCP_PROJECT)}"; \
	GCP_PROJECT="$${GCP_PROJECT:-global-overview-radar}"; \
	GCP_REGION="$${GCP_REGION:-$$(env_get GCP_REGION)}"; \
	GCP_REGION="$${GCP_REGION:-europe-southwest1}"; \
	BACKEND_SERVICE="$${BACKEND_SERVICE:-$$(env_get BACKEND_SERVICE)}"; \
	BACKEND_SERVICE="$${BACKEND_SERVICE:-gor-backend}"; \
		LOGIN_REQUESTED_VAL="$$(env_get GOOGLE_CLOUD_LOGIN_REQUESTED)"; \
		LOGIN_REQUESTED_VAL=$$(echo "$$LOGIN_REQUESTED_VAL" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]'); \
		if [ "$$LOGIN_REQUESTED_VAL" != "true" ]; then LOGIN_REQUESTED_VAL="false"; fi; \
		CLIENT_ID_VAL="$$(env_get AUTH_GOOGLE_CLIENT_ID)"; \
		CLIENT_ID_VAL=$$(printf '%s' "$$CLIENT_ID_VAL" | tr -d '\r'); \
		echo "==> Lanzando ingesta remota en Cloud Run ($$BACKEND_SERVICE)..."; \
		CALLER_SERVICE_ACCOUNT_VAL="$${CALLER_SERVICE_ACCOUNT:-gor-github-deploy@$${GCP_PROJECT}.iam.gserviceaccount.com}"; \
		if [ "$$LOGIN_REQUESTED_VAL" = "true" ]; then \
		if [ -z "$$CLIENT_ID_VAL" ]; then \
			echo "Falta AUTH_GOOGLE_CLIENT_ID (ponlo en backend/reputation/cloudrun.env)."; \
			exit 1; \
		fi; \
			if ! echo "$$CLIENT_ID_VAL" | grep -q '\\.apps\\.googleusercontent\\.com$$'; then \
				echo "ERROR: AUTH_GOOGLE_CLIENT_ID debe ser un OAuth Client ID (termina en .apps.googleusercontent.com). Valor actual: $$CLIENT_ID_VAL"; \
				exit 1; \
			fi; \
		fi; \
		BACKEND_URL=$$(gcloud run services describe "$$BACKEND_SERVICE" --project "$$GCP_PROJECT" --region "$$GCP_REGION" --format 'value(status.url)'); \
	if [ -z "$$BACKEND_URL" ]; then \
		echo "No se pudo obtener BACKEND_URL. Verifica deploy del backend y permisos."; \
		exit 1; \
	fi; \
	TOKEN_FLAGS=(); \
	if [ -n "$$CALLER_SERVICE_ACCOUNT_VAL" ]; then \
		TOKEN_FLAGS+=(--impersonate-service-account "$$CALLER_SERVICE_ACCOUNT_VAL"); \
		echo "Usando impersonacion SA: $$CALLER_SERVICE_ACCOUNT_VAL"; \
	fi; \
	RUN_TOKEN=$$(gcloud auth print-identity-token "$${TOKEN_FLAGS[@]}" --audiences="$$BACKEND_URL"); \
	USER_TOKEN=""; \
	if [ "$$LOGIN_REQUESTED_VAL" = "true" ]; then \
		USER_TOKEN=$$(gcloud auth print-identity-token "$${TOKEN_FLAGS[@]}" --audiences="$$CLIENT_ID_VAL" --include-email); \
		fi; \
		PAYLOAD="{\"force\":$(INGEST_FORCE),\"all_sources\":$(INGEST_ALL_SOURCES)}"; \
		CURL_HEADERS=(-H "Authorization: Bearer $$RUN_TOKEN"); \
		if [ -n "$$USER_TOKEN" ]; then CURL_HEADERS+=(-H "x-user-id-token: $$USER_TOKEN"); fi; \
		RESPONSE=$$(curl -sS -f -X POST "$$BACKEND_URL/ingest/reputation" \
			"$${CURL_HEADERS[@]}" \
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
			"$${CURL_HEADERS[@]}"); \
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
	cd $(FRONTDIR) && $(NPM) run lint

typecheck: typecheck-back typecheck-front

typecheck-back:
	@echo "==> Typecheck backend (mypy + pyright)..."
	$(PY) -m mypy --config-file backend/pyproject.toml backend
	$(PY) -m pyright

typecheck-front:
	@echo "==> Typecheck frontend (tsc --noEmit)..."
	cd $(FRONTDIR) && npx tsc --noEmit

check: format lint typecheck

# -------------------------
# CodeQL (SAST)
# -------------------------
CODEQL ?= codeql
CODEQL_DIR ?= .codeql
CODEQL_DB_DIR ?= $(CODEQL_DIR)/db
CODEQL_RESULTS_DIR ?= $(CODEQL_DIR)/results
CODEQL_THREADS ?= 0

CODEQL_PY_QUERIES ?= codeql/python-queries
CODEQL_JS_QUERIES ?= codeql/javascript-queries
CODEQL_JS_SOURCE_ROOT ?= $(FRONTDIR)/src
# Optional: for JS/TS extraction you can provide a build command:
#   make codeql-js CODEQL_JS_COMMAND='cd frontend/brr-frontend && npm run build'
CODEQL_JS_COMMAND ?=

codeql: codeql-python codeql-js
	@echo "==> CodeQL completado. Resultados en $(CODEQL_RESULTS_DIR)/"

codeql-install:
	@set -euo pipefail; \
	if command -v "$(CODEQL)" >/dev/null 2>&1; then \
		echo "==> CodeQL CLI ya esta instalado: $$(command -v "$(CODEQL)")"; \
		exit 0; \
	fi; \
	if command -v brew >/dev/null 2>&1; then \
		echo "==> Instalando CodeQL CLI via Homebrew..."; \
		brew install codeql; \
		exit 0; \
	fi; \
	echo "ERROR: CodeQL CLI no encontrado. Instala 'codeql' (macOS: brew install codeql)." >&2; \
	exit 1

codeql-python:
	@echo "==> CodeQL (python)..."
	@command -v $(CODEQL) >/dev/null 2>&1 || (echo "ERROR: falta CodeQL CLI. Ejecuta: make codeql-install (o brew install codeql)"; exit 1)
	@mkdir -p $(CODEQL_DB_DIR) $(CODEQL_RESULTS_DIR)
	@$(CODEQL) database create "$(CODEQL_DB_DIR)/python" \
		--language=python \
		--source-root=backend \
		--overwrite
	@$(CODEQL) database analyze "$(CODEQL_DB_DIR)/python" "$(CODEQL_PY_QUERIES)" \
		--format=sarif-latest \
		--output="$(CODEQL_RESULTS_DIR)/codeql-python.sarif" \
		--sarif-category=python \
		--threads="$(CODEQL_THREADS)" \
		--download

codeql-js:
	@echo "==> CodeQL (javascript-typescript)..."
	@command -v $(CODEQL) >/dev/null 2>&1 || (echo "ERROR: falta CodeQL CLI. Ejecuta: make codeql-install (o brew install codeql)"; exit 1)
	@mkdir -p $(CODEQL_DB_DIR) $(CODEQL_RESULTS_DIR)
	@if [ ! -d "$(FRONTDIR)/node_modules" ]; then \
		echo "==> node_modules no encontrado. Instalando frontend..."; \
		$(MAKE) install-front; \
	fi
	@if [ -n "$(CODEQL_JS_COMMAND)" ]; then \
		echo "==> Creando DB JS/TS con build command: $(CODEQL_JS_COMMAND)"; \
		$(CODEQL) database create "$(CODEQL_DB_DIR)/javascript-typescript" \
			--language=javascript-typescript \
			--source-root="$(CODEQL_JS_SOURCE_ROOT)" \
			--command="$(CODEQL_JS_COMMAND)" \
			--overwrite; \
	else \
		$(CODEQL) database create "$(CODEQL_DB_DIR)/javascript-typescript" \
			--language=javascript-typescript \
			--source-root="$(CODEQL_JS_SOURCE_ROOT)" \
			--overwrite; \
	fi
	@$(CODEQL) database analyze "$(CODEQL_DB_DIR)/javascript-typescript" "$(CODEQL_JS_QUERIES)" \
		--format=sarif-latest \
		--output="$(CODEQL_RESULTS_DIR)/codeql-javascript-typescript.sarif" \
		--sarif-category=javascript-typescript \
		--threads="$(CODEQL_THREADS)" \
		--download

codeql-clean:
	@echo "==> Eliminando artefactos CodeQL ($(CODEQL_DIR))..."
	@rm -rf "$(CODEQL_DIR)"

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
	rm -rf $(VENV) .mypy_cache .ruff_cache .pytest_cache
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
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
