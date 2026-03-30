# Makefile - Fullstack: Global Overview Radar
# Uso: make <target>
SHELL := /bin/bash

# Cloud Run targets read backend/reputation/cloudrun.env (dotenv format).
# Do NOT -include dotenv files in Make: values may contain `$` and would be expanded by Make.

# --- Configuración general ---
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(PY) -m pip
PYTHON_BOOTSTRAP ?= $(shell \
	for p in python3.12 python3.11 python3.10 python3; do \
		if command -v $$p >/dev/null 2>&1 && $$p -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then \
			echo $$p; \
			break; \
		fi; \
	done)

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
RUN_WINDOW_TITLE ?= Global Overview Radar
RUN_WINDOW_WIDTH ?= 1600
RUN_WINDOW_HEIGHT ?= 1000
APPLE_DISTRIBUTION ?= auto

# --- Cloud Run knobs (non-secret) ---
BACKEND_MAX_INSTANCES ?= 1
FRONTEND_MAX_INSTANCES ?= 1
BACKEND_CONCURRENCY ?= 2
FRONTEND_CONCURRENCY ?= 2
BACKEND_MEMORY ?= 768Mi
FRONTEND_MEMORY ?= 768Mi
BACKEND_CPU ?= 1
FRONTEND_CPU ?= 1

BENCH_DIR ?= docs/benchmarks
BENCH_ITERATIONS ?= 40
BENCH_WARMUP ?= 5
BENCH_MAX_REGRESSION ?= 0.15
BENCH_OUT_BACK ?= $(BENCH_DIR)/backend.latest.json
BENCH_BASELINE_BACK ?= $(BENCH_DIR)/backend.baseline.json
BENCH_OUT_INGEST ?= $(BENCH_DIR)/ingest.latest.json
BENCH_BASELINE_INGEST ?= $(BENCH_DIR)/ingest.baseline.json

VISUAL_QA_URL ?= http://localhost:$(FRONT_PORT)
VISUAL_QA_OUT ?= docs/visual-qa

# --- GCS cache sync (reputation-state) ---
# Por defecto replica ./data/cache/*.json a gs://<bucket>/<prefix>/cache/
# y BORRA en destino los JSON que ya no existen localmente.
STATE_BUCKET ?= global-overview-radar-reputation-state
STATE_CACHE_PREFIX ?= reputation-state/data/cache

# -------------------------
# Cloud Run / Deploy identity
# -------------------------
# Deployer identity (impersonación) para deploys:
DEPLOY_SA ?= gor-github-deploy@global-overview-radar.iam.gserviceaccount.com

# Artifact Registry (repo usado por Cloud Run Source Deployments)
AR_REPO ?= cloud-run-source-deploy
AR_IMAGE_BACK_NAME ?= gor-backend
CLOUDRUN_ENV_INTERACTIVE ?= $(if $(filter cloudrun-env,$(MAKECMDGOALS)),true,false)

.DEFAULT_GOAL := help

.PHONY: help install clean build ensure-cloudrun-env run kill ci test-coverage bench visual-qa \
	cloudrun-env deploy-cloudrun \
	upload-cache-gcs gcloud-impersonate gcloud-unimpersonate ensure-ar-writer bundle-backend-data \
	_ci-codeql

help:
	@echo "Make targets disponibles:"
	@echo "  make install         - Ejecutar clean e instalar todo lo necesario para backend + frontend"
	@echo "                         Requiere Python >= 3.10 (autodetección: $(PYTHON_BOOTSTRAP))"
	@echo "  make clean           - Eliminar venv, caches, node_modules (frontend)"
	@echo "  make build           - Generar la build de escritorio para el sistema actual (macOS o Linux)"
	@echo "                         Apple opcional: APPLE_DISTRIBUTION=auto|required|off (default: auto)"
	@echo "  make run             - Levantar backend + frontend y abrir el frontend en una ventana contenedora"
	@echo "  make kill            - Cerrar cualquier instancia activa registrada de la aplicación"
	@echo "  make ci              - Ejecutar format-check, lint, typecheck y CodeQL local si está disponible"
	@echo "  make test-coverage   - Ejecutar cobertura backend + frontend (>=70%)"
	@echo "  make bench           - Benchmark backend + ingesta; crea baseline si falta y compara si existe"
	@echo "  make visual-qa       - Capturas headless mobile (frontend)"
	@echo "  make cloudrun-env    - Configurar, validar y normalizar backend/reputation/cloudrun.env"
	@echo "  make deploy-cloudrun       - Deploy backend + frontend (Cloud Run)"
	@echo "  make upload-cache-gcs      - Borra JSON huérfanos en GCS y sube todos los JSON de ./data/cache/"

# -------------------------
# Virtualenv + Instalación
# -------------------------
install: clean
	@echo "==> Instalando backend + frontend desde cero..."
	@if [ -z "$(PYTHON_BOOTSTRAP)" ]; then \
		echo "ERROR: No se encontró Python >= 3.10 en PATH."; \
		echo "       Candidatos probados: python3.12 python3.11 python3.10 python3"; \
		exit 1; \
	fi
	@echo "==> Creando virtualenv en $(VENV) con $(PYTHON_BOOTSTRAP)..."
	$(PYTHON_BOOTSTRAP) -m venv $(VENV)
	@$(PY) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || { \
		echo "ERROR: El virtualenv quedó con Python < 3.10. Revisa tu PATH."; \
		exit 1; \
	}
	$(PIP) install --upgrade pip setuptools wheel
	@echo "==> Instalando dependencias Python (requirements / pyproject editable)..."
	$(PIP) install -r requirements.txt
	@if [ -f requirements-dev.txt ]; then \
		echo "==> Instalando dependencias dev (requirements-dev.txt)..."; \
		$(PIP) install -r requirements-dev.txt; \
	fi
	$(PIP) install -e backend
	@echo "==> Instalando dependencias frontend (cd $(FRONTDIR))..."
	cd $(FRONTDIR) && $(NPM) $(NPM_INSTALL_CMD)
	@test -f backend/reputation/.env.reputation || cp backend/reputation/.env.reputation.example backend/reputation/.env.reputation
	@test -f frontend/brr-frontend/.env.local || cp frontend/brr-frontend/.env.local.example frontend/brr-frontend/.env.local
	@echo "==> .env files preparados (edítalos si lo necesitas)."
	@echo "==> Instalación frontend completada."
	@echo "==> Instalación completa."

clean:
	@echo "==> Limpiando entorno..."
	rm -rf $(VENV) .mypy_cache .ruff_cache .pytest_cache .coverage
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
	cd $(FRONTDIR) && rm -rf node_modules .next dist out coverage || true
	rm -rf build dist
	@echo "==> Limpieza completada."

# -------------------------
# GCS cache upload
# -------------------------
upload-cache-gcs:
	@echo "==> Borrando huérfanos en destino y subiendo TODOS los JSON de ./data/cache a GCS..."
	@set -euo pipefail; \
	if ! command -v gcloud >/dev/null 2>&1; then \
		echo "ERROR: gcloud no está instalado o no está en PATH."; \
		exit 1; \
	fi; \
	if [ ! -d "./data/cache" ]; then \
		echo "ERROR: No existe ./data/cache"; \
		exit 1; \
	fi; \
	shopt -s nullglob; \
	files=(./data/cache/*.json); \
	if [ "$${#files[@]}" -eq 0 ]; then \
		echo "ERROR: No hay .json en ./data/cache"; \
		exit 1; \
	fi; \
	dest="gs://$(STATE_BUCKET)/$(STATE_CACHE_PREFIX)/"; \
	echo "Destino: $$dest"; \
	echo "Ficheros locales: $${#files[@]}"; \
	remote_json="$$(gcloud storage ls "$$dest*.json" 2>/dev/null || true)"; \
	if [ -n "$$remote_json" ]; then \
		while IFS= read -r remote; do \
			[ -n "$$remote" ] || continue; \
			remote_name="$${remote##*/}"; \
			if [ ! -f "./data/cache/$$remote_name" ]; then \
				echo "==> Borrando JSON huérfano en destino: $$remote_name"; \
				gcloud storage rm "$$remote"; \
			fi; \
		done <<< "$$remote_json"; \
	else \
		echo "==> No hay JSON previos en destino."; \
	fi; \
	gcloud storage cp "$${files[@]}" "$$dest" --content-type=application/json; \
	echo "==> OK: cachés subidos."

# -------------------------
# Cloud Run helpers
# -------------------------
gcloud-impersonate:
	@echo "==> Activando impersonación: $(DEPLOY_SA)"
	@gcloud config set auth/impersonate_service_account "$(DEPLOY_SA)" >/dev/null
	@echo "==> impersonate_service_account=$$(gcloud config get-value auth/impersonate_service_account)"

gcloud-unimpersonate:
	@echo "==> Desactivando impersonación..."
	@gcloud config unset auth/impersonate_service_account >/dev/null || true
	@echo "==> impersonate_service_account=$$(gcloud config get-value auth/impersonate_service_account 2>/dev/null || echo "(unset)")"

ensure-cloudrun-env:
	@mkdir -p backend/reputation
	@test -f backend/reputation/cloudrun.env || cp backend/reputation/cloudrun.env.example backend/reputation/cloudrun.env
	@echo "==> backend/reputation/cloudrun.env preparado."

cloudrun-env: ensure-cloudrun-env
	@echo "==> Configurando y validando backend/reputation/cloudrun.env..."
	@set -euo pipefail; \
	ENV_FILE="backend/reputation/cloudrun.env"; \
	env_get() { awk -F= -v k="$$1" '$$0 ~ ("^"k"=") {print substr($$0,index($$0,"=")+1)}' "$$ENV_FILE" | tail -n1; }; \
	DEFAULT_GCP_PROJECT="global-overview-radar"; \
	DEFAULT_GCP_REGION="europe-southwest1"; \
	DEFAULT_BACKEND_SERVICE="gor-backend"; \
	DEFAULT_FRONTEND_SERVICE="gor-frontend"; \
	GCP_PROJECT_VAL="$$(env_get GCP_PROJECT)"; \
	GCP_PROJECT_VAL="$${GCP_PROJECT_VAL:-$$DEFAULT_GCP_PROJECT}"; \
	GCP_REGION_VAL="$$(env_get GCP_REGION)"; \
	GCP_REGION_VAL="$${GCP_REGION_VAL:-$$DEFAULT_GCP_REGION}"; \
	BACKEND_SERVICE_VAL="$$(env_get BACKEND_SERVICE)"; \
	BACKEND_SERVICE_VAL="$${BACKEND_SERVICE_VAL:-$$DEFAULT_BACKEND_SERVICE}"; \
	BACKEND_SA_VAL="$$(printf '%s' "$$(env_get BACKEND_SA)" | tr -d '\r')"; \
	FRONTEND_SERVICE_VAL="$$(env_get FRONTEND_SERVICE)"; \
	FRONTEND_SERVICE_VAL="$${FRONTEND_SERVICE_VAL:-$$DEFAULT_FRONTEND_SERVICE}"; \
	LOGIN_REQUESTED_VAL="$$(env_get GOOGLE_CLOUD_LOGIN_REQUESTED)"; \
	LOGIN_REQUESTED_VAL="$$(echo "$$LOGIN_REQUESTED_VAL" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"; \
	if [ "$$LOGIN_REQUESTED_VAL" != "true" ]; then LOGIN_REQUESTED_VAL="false"; fi; \
	CLIENT_ID_VAL="$$(env_get AUTH_GOOGLE_CLIENT_ID)"; \
	ALLOWED_EMAILS_VAL="$$(env_get AUTH_ALLOWED_EMAILS)"; \
	STATE_BUCKET_VAL="$$(env_get REPUTATION_STATE_BUCKET)"; \
	CLIENT_ID_VAL="$$(printf '%s' "$$CLIENT_ID_VAL" | tr -d '\r')"; \
	ALLOWED_EMAILS_VAL="$$(printf '%s' "$$ALLOWED_EMAILS_VAL" | tr -d '\r')"; \
	STATE_BUCKET_VAL="$$(printf '%s' "$$STATE_BUCKET_VAL" | tr -d '\r')"; \
	if [ -z "$$STATE_BUCKET_VAL" ]; then STATE_BUCKET_VAL="$${GCP_PROJECT_VAL}-reputation-state"; fi; \
	FRONTEND_SA_VAL="$$(printf '%s' "$$(env_get FRONTEND_SA)" | tr -d '\r')"; \
	if [ -z "$$FRONTEND_SA_VAL" ]; then FRONTEND_SA_VAL="gor-frontend-sa@$${GCP_PROJECT_VAL}.iam.gserviceaccount.com"; fi; \
	if [ "$(CLOUDRUN_ENV_INTERACTIVE)" = "true" ] && [ -t 0 ] && [ -t 1 ]; then \
		read -r -p "GCP_PROJECT [$$GCP_PROJECT_VAL]: " GCP_PROJECT_IN; \
		GCP_PROJECT_VAL="$${GCP_PROJECT_IN:-$$GCP_PROJECT_VAL}"; \
		read -r -p "GCP_REGION [$$GCP_REGION_VAL]: " GCP_REGION_IN; \
		GCP_REGION_VAL="$${GCP_REGION_IN:-$$GCP_REGION_VAL}"; \
		read -r -p "BACKEND_SERVICE [$$BACKEND_SERVICE_VAL]: " BACKEND_SERVICE_IN; \
		BACKEND_SERVICE_VAL="$${BACKEND_SERVICE_IN:-$$BACKEND_SERVICE_VAL}"; \
		read -r -p "BACKEND_SA (vacío => <projectNumber>-compute@developer.gserviceaccount.com) [$$BACKEND_SA_VAL]: " BACKEND_SA_IN; \
		BACKEND_SA_VAL="$${BACKEND_SA_IN:-$$BACKEND_SA_VAL}"; \
		read -r -p "FRONTEND_SERVICE [$$FRONTEND_SERVICE_VAL]: " FRONTEND_SERVICE_IN; \
		FRONTEND_SERVICE_VAL="$${FRONTEND_SERVICE_IN:-$$FRONTEND_SERVICE_VAL}"; \
		read -r -p "FRONTEND_SA [$$FRONTEND_SA_VAL]: " FRONTEND_SA_IN; \
		FRONTEND_SA_VAL="$${FRONTEND_SA_IN:-$$FRONTEND_SA_VAL}"; \
		read -r -p "GOOGLE_CLOUD_LOGIN_REQUESTED (true/false) [$$LOGIN_REQUESTED_VAL]: " LOGIN_REQUESTED_IN; \
		LOGIN_REQUESTED_VAL="$$(echo "$${LOGIN_REQUESTED_IN:-$$LOGIN_REQUESTED_VAL}" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"; \
		if [ "$$LOGIN_REQUESTED_VAL" != "true" ]; then LOGIN_REQUESTED_VAL="false"; fi; \
		read -r -p "AUTH_GOOGLE_CLIENT_ID [$$CLIENT_ID_VAL]: " CLIENT_ID_IN; \
		CLIENT_ID_VAL="$${CLIENT_ID_IN:-$$CLIENT_ID_VAL}"; \
		read -r -p "AUTH_ALLOWED_EMAILS (coma separada) [$$ALLOWED_EMAILS_VAL]: " ALLOWED_EMAILS_IN; \
		ALLOWED_EMAILS_VAL="$${ALLOWED_EMAILS_IN:-$$ALLOWED_EMAILS_VAL}"; \
		read -r -p "REPUTATION_STATE_BUCKET [$$STATE_BUCKET_VAL]: " STATE_BUCKET_IN; \
		STATE_BUCKET_VAL="$${STATE_BUCKET_IN:-$$STATE_BUCKET_VAL}"; \
	else \
		echo "==> Modo no interactivo: se reutiliza la configuración actual y solo se valida/normaliza."; \
	fi; \
	GCP_PROJECT_VAL="$$(printf '%s' "$$GCP_PROJECT_VAL" | tr -d '\r')"; \
	GCP_REGION_VAL="$$(printf '%s' "$$GCP_REGION_VAL" | tr -d '\r')"; \
	BACKEND_SERVICE_VAL="$$(printf '%s' "$$BACKEND_SERVICE_VAL" | tr -d '\r')"; \
	BACKEND_SA_VAL="$$(printf '%s' "$$BACKEND_SA_VAL" | tr -d '\r')"; \
	FRONTEND_SERVICE_VAL="$$(printf '%s' "$$FRONTEND_SERVICE_VAL" | tr -d '\r')"; \
	FRONTEND_SA_VAL="$$(printf '%s' "$$FRONTEND_SA_VAL" | tr -d '\r')"; \
	CLIENT_ID_VAL="$$(printf '%s' "$$CLIENT_ID_VAL" | tr -d '\r')"; \
	ALLOWED_EMAILS_VAL="$$(printf '%s' "$$ALLOWED_EMAILS_VAL" | tr -d '\r')"; \
	STATE_BUCKET_VAL="$$(printf '%s' "$$STATE_BUCKET_VAL" | tr -d '\r')"; \
	STATE_PREFIX_VAL="reputation-state"; \
	if [ -z "$$GCP_PROJECT_VAL" ] || [ -z "$$GCP_REGION_VAL" ] || [ -z "$$BACKEND_SERVICE_VAL" ] || [ -z "$$FRONTEND_SERVICE_VAL" ]; then \
		echo "Faltan valores base de Cloud Run (GCP_PROJECT/GCP_REGION/BACKEND_SERVICE/FRONTEND_SERVICE)."; \
		exit 1; \
	fi; \
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
	grep -vE '^(GCP_PROJECT|GCP_REGION|BACKEND_SERVICE|BACKEND_SA|FRONTEND_SERVICE|FRONTEND_SA|GOOGLE_CLOUD_LOGIN_REQUESTED|AUTH_GOOGLE_CLIENT_ID|AUTH_ALLOWED_EMAILS|REPUTATION_STATE_BUCKET|REPUTATION_STATE_PREFIX)=' "$$ENV_FILE" > "$$TMP_FILE" || true; \
	mv "$$TMP_FILE" "$$ENV_FILE"; \
	{ printf '\n# --- Cloud Run (generated by make cloudrun-env) ---\n'; \
		printf '%s\n' \
			"GCP_PROJECT=$$GCP_PROJECT_VAL" \
			"GCP_REGION=$$GCP_REGION_VAL" \
			"BACKEND_SERVICE=$$BACKEND_SERVICE_VAL" \
			"BACKEND_SA=$$BACKEND_SA_VAL" \
			"FRONTEND_SERVICE=$$FRONTEND_SERVICE_VAL" \
			"FRONTEND_SA=$$FRONTEND_SA_VAL" \
			"GOOGLE_CLOUD_LOGIN_REQUESTED=$$LOGIN_REQUESTED_VAL"; \
		if [ -n "$$CLIENT_ID_VAL" ]; then printf '%s\n' "AUTH_GOOGLE_CLIENT_ID=$$CLIENT_ID_VAL"; fi; \
		if [ -n "$$ALLOWED_EMAILS_VAL" ]; then printf '%s\n' "AUTH_ALLOWED_EMAILS=$$ALLOWED_EMAILS_VAL"; fi; \
		printf '%s\n' "REPUTATION_STATE_BUCKET=$$STATE_BUCKET_VAL"; \
		printf '%s\n' "REPUTATION_STATE_PREFIX=$$STATE_PREFIX_VAL"; \
	} >> "$$ENV_FILE"
	@echo "==> cloudrun.env configurado y validado."

# -------------------------
# Bundle backend data for container build
# -------------------------
bundle-backend-data:
	@echo "==> Bundle profile templates into backend source..."
	@set -euo pipefail; \
	mkdir -p backend/data; \
	rsync -a --delete data/reputation/ backend/data/reputation/; \
	rsync -a --delete data/reputation_llm/ backend/data/reputation_llm/; \
	rsync -a --delete data/reputation_samples/ backend/data/reputation_samples/; \
	rsync -a --delete data/reputation_llm_samples/ backend/data/reputation_llm_samples/; \
	echo "==> OK: backend/data actualizado."

# -------------------------------------------------------
# Cloud Run deploy (NUEVO): build -> image -> deploy image
# -------------------------------------------------------
ensure-ar-writer:
	@echo "==> Verificando (informativo) que Cloud Build builder SA pueda push a Artifact Registry (repo=$(AR_REPO))..."
	@set -euo pipefail; \
	ENV_FILE="backend/reputation/cloudrun.env"; \
	env_get() { awk -F= -v k="$$1" '$$0 ~ ("^"k"=") {print substr($$0,index($$0,"=")+1)}' "$$ENV_FILE" | tail -n1; }; \
	GCP_PROJECT="$${GCP_PROJECT:-$$(env_get GCP_PROJECT)}"; \
	GCP_PROJECT="$${GCP_PROJECT:-global-overview-radar}"; \
	PROJECT_NUMBER=$$(gcloud projects describe "$$GCP_PROJECT" --format='value(projectNumber)'); \
	BUILD_SA="$$PROJECT_NUMBER-compute@developer.gserviceaccount.com"; \
	echo "Cloud Build builder SA esperado: $$BUILD_SA"; \
	echo "Si vuelve a fallar docker push, asegura: roles/artifactregistry.writer en el repo para $$BUILD_SA"; \
	true

deploy-cloudrun: cloudrun-env gcloud-impersonate ensure-ar-writer bundle-backend-data
	@echo "==> Deploy backend + frontend en Cloud Run..."
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
	BACKEND_SA="$${BACKEND_SA:-$$(env_get BACKEND_SA)}"; \
	if [ -z "$$BACKEND_SA" ]; then \
		PROJECT_NUMBER=$$(gcloud projects describe "$$GCP_PROJECT" --format='value(projectNumber)'); \
		BACKEND_SA="$$PROJECT_NUMBER-compute@developer.gserviceaccount.com"; \
	fi; \
	CB_BUCKET="$${GCP_PROJECT}-cloudbuild"; \
	IMAGE="$${GCP_REGION}-docker.pkg.dev/$${GCP_PROJECT}/$(AR_REPO)/$(AR_IMAGE_BACK_NAME):$$(date +%Y%m%d-%H%M%S)"; \
	echo "GCP_PROJECT=$$GCP_PROJECT"; \
	echo "GCP_REGION=$$GCP_REGION"; \
	echo "BACKEND_SERVICE=$$BACKEND_SERVICE"; \
	echo "FRONTEND_SERVICE=$$FRONTEND_SERVICE"; \
	echo "BACKEND_RUNTIME_SA=$$BACKEND_SA"; \
	echo "BACKEND_IMAGE=$$IMAGE"; \
	echo "==> Deploy backend en Cloud Run (Cloud Build -> Artifact Registry -> Cloud Run)..."; \
	gcloud builds submit . \
		--project="$$GCP_PROJECT" --region="$$GCP_REGION" \
		--config=cloudbuild-backend.yaml \
		--substitutions=_IMAGE="$$IMAGE" \
		--gcs-source-staging-dir="gs://$$CB_BUCKET/source"; \
	gcloud run deploy "$$BACKEND_SERVICE" \
		--project "$$GCP_PROJECT" \
		--region "$$GCP_REGION" \
		--image "$$IMAGE" \
		--service-account "$$BACKEND_SA" \
		--no-allow-unauthenticated \
		--port 8080 \
		--min-instances 0 \
		--max-instances $(BACKEND_MAX_INSTANCES) \
		--concurrency $(BACKEND_CONCURRENCY) \
		--cpu $(BACKEND_CPU) \
		--memory $(BACKEND_MEMORY) \
		--cpu-throttling \
		--timeout 300 \
		--env-vars-file "$$ENV_FILE"; \
	gcloud run services update-traffic "$$BACKEND_SERVICE" \
		--project "$$GCP_PROJECT" \
		--region "$$GCP_REGION" \
		--to-latest; \
	echo "==> OK backend. Service URL:"; \
	gcloud run services describe "$$BACKEND_SERVICE" --project "$$GCP_PROJECT" --region "$$GCP_REGION" --format 'value(status.url)'; \
	echo "==> Redeploy frontend en Cloud Run con su imagen actual..."; \
	IMAGE_FRONT="$$(gcloud run services describe "$$FRONTEND_SERVICE" --project "$$GCP_PROJECT" --region "$$GCP_REGION" --format="value(spec.template.spec.containers[0].image)")"; \
	RUNTIME_SA_FRONT="$$(gcloud run services describe "$$FRONTEND_SERVICE" --project "$$GCP_PROJECT" --region "$$GCP_REGION" --format="value(spec.template.spec.serviceAccountName)")"; \
	if [ -z "$$IMAGE_FRONT" ] || [ -z "$$RUNTIME_SA_FRONT" ]; then \
		echo "ERROR: No pude leer imagen/runtime SA del servicio $$FRONTEND_SERVICE"; \
		exit 1; \
	fi; \
	echo "FRONTEND_IMAGE=$$IMAGE_FRONT"; \
	echo "FRONTEND_RUNTIME_SA=$$RUNTIME_SA_FRONT"; \
	gcloud run deploy "$$FRONTEND_SERVICE" \
		--project "$$GCP_PROJECT" \
		--region "$$GCP_REGION" \
		--image "$$IMAGE_FRONT" \
		--service-account "$$RUNTIME_SA_FRONT" \
		--allow-unauthenticated \
		--min-instances 0 \
		--max-instances $(FRONTEND_MAX_INSTANCES) \
		--concurrency $(FRONTEND_CONCURRENCY) \
		--cpu $(FRONTEND_CPU) \
		--memory $(FRONTEND_MEMORY) \
		--cpu-throttling; \
	echo "==> OK frontend. Service URL:"; \
	gcloud run services describe "$$FRONTEND_SERVICE" --project "$$GCP_PROJECT" --region "$$GCP_REGION" --format 'value(status.url)'

run:
	@if [ ! -x "$(PY)" ] || [ ! -d "$(FRONTDIR)/node_modules" ] || ! $(PY) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then \
		echo "==> Dependencias ausentes o Python < 3.10. Ejecutando make install..."; \
		$(MAKE) install; \
	fi
	@test -f backend/reputation/.env.reputation || cp backend/reputation/.env.reputation.example backend/reputation/.env.reputation
	@test -f frontend/brr-frontend/.env.local || cp frontend/brr-frontend/.env.local.example frontend/brr-frontend/.env.local
	@echo "==> Iniciando Global Overview Radar en ventana local..."
	$(PY) scripts/run_local.py \
		--host "$(HOST)" \
		--api-port "$(API_PORT)" \
		--front-port "$(FRONT_PORT)" \
		--title "$(RUN_WINDOW_TITLE)" \
		--width "$(RUN_WINDOW_WIDTH)" \
		--height "$(RUN_WINDOW_HEIGHT)"

kill:
	@echo "==> Cerrando instancias activas de Global Overview Radar..."
	@command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 no está disponible."; exit 1; }
	@python3 scripts/kill_app.py

build:
	@if [ ! -x "$(PY)" ] || [ ! -d "$(FRONTDIR)/node_modules" ] || ! $(PY) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1 || ! $(PY) -c "import PyInstaller, PIL" >/dev/null 2>&1; then \
		echo "==> Dependencias de build ausentes o Python < 3.10. Ejecutando make install..."; \
		$(MAKE) install; \
	fi
	@echo "==> Generando build de escritorio para el sistema actual..."
	$(PY) scripts/build_desktop.py --apple-distribution "$(APPLE_DISTRIBUTION)"

# -------------------------
# Calidad / CI local
# -------------------------
CODEQL ?= codeql
CODEQL_DIR ?= .codeql
CODEQL_DB_DIR ?= $(CODEQL_DIR)/db
CODEQL_RESULTS_DIR ?= $(CODEQL_DIR)/results
CODEQL_THREADS ?= 0
CODEQL_PY_QUERIES ?= codeql/python-queries
CODEQL_JS_QUERIES ?= codeql/javascript-queries
CODEQL_JS_SOURCE_ROOT ?= $(FRONTDIR)/src

ci:
	@echo "==> Ejecutando validaciones locales..."
	$(PY) -m ruff format --check .
	$(PY) -m ruff check .
	cd $(FRONTDIR) && $(NPM) run lint
	$(PY) -m mypy --config-file backend/pyproject.toml backend
	$(PY) -m pyright backend
	cd $(FRONTDIR) && npx tsc --noEmit
	@$(MAKE) _ci-codeql
	@echo "==> CI local completada."

_ci-codeql:
	@set -euo pipefail; \
	if ! command -v "$(CODEQL)" >/dev/null 2>&1; then \
		echo "==> CodeQL CLI no encontrado. Se omite el análisis SAST en make ci."; \
		exit 0; \
	fi; \
	echo "==> Ejecutando CodeQL local..."; \
	rm -rf "$(CODEQL_DB_DIR)/python" "$(CODEQL_DB_DIR)/javascript-typescript"; \
	mkdir -p "$(CODEQL_DB_DIR)" "$(CODEQL_RESULTS_DIR)"; \
	"$(CODEQL)" database create "$(CODEQL_DB_DIR)/python" \
		--language=python \
		--source-root=backend \
		--overwrite; \
	"$(CODEQL)" database analyze "$(CODEQL_DB_DIR)/python" "$(CODEQL_PY_QUERIES)" \
		--format=sarif-latest \
		--output="$(CODEQL_RESULTS_DIR)/codeql-python.sarif" \
		--sarif-category=python \
		--threads="$(CODEQL_THREADS)" \
		--download; \
	"$(CODEQL)" database create "$(CODEQL_DB_DIR)/javascript-typescript" \
		--language=javascript-typescript \
		--source-root="$(CODEQL_JS_SOURCE_ROOT)" \
		--overwrite; \
	"$(CODEQL)" database analyze "$(CODEQL_DB_DIR)/javascript-typescript" "$(CODEQL_JS_QUERIES)" \
		--format=sarif-latest \
		--output="$(CODEQL_RESULTS_DIR)/codeql-javascript-typescript.sarif" \
		--sarif-category=javascript-typescript \
		--threads="$(CODEQL_THREADS)" \
		--download

# -------------------------
# Tests
# -------------------------
test-coverage:
	@echo "==> Cobertura backend (pytest-cov >=70%)..."
	$(PY) -m pytest
	@echo "==> Cobertura frontend (vitest >=70%)..."
	cd $(FRONTDIR) && $(NPM) run test:coverage

# -------------------------
# Benchmarks / Visual QA
# -------------------------
bench:
	@mkdir -p $(BENCH_DIR)
	@echo "==> Benchmark backend..."
	@if [ ! -f "$(BENCH_BASELINE_BACK)" ]; then \
		echo "==> Baseline backend no encontrada. Creando $(BENCH_BASELINE_BACK)..."; \
		$(PY) scripts/bench_backend.py --iterations $(BENCH_ITERATIONS) --warmup $(BENCH_WARMUP) --json $(BENCH_BASELINE_BACK); \
	else \
		echo "==> Baseline backend encontrada. Comparando contra $(BENCH_BASELINE_BACK)..."; \
		$(PY) scripts/bench_backend.py --iterations $(BENCH_ITERATIONS) --warmup $(BENCH_WARMUP) --json $(BENCH_OUT_BACK) --baseline $(BENCH_BASELINE_BACK) --max-regression $(BENCH_MAX_REGRESSION); \
	fi
	@echo "==> Benchmark de ingesta..."
	@if [ ! -f "$(BENCH_BASELINE_INGEST)" ]; then \
		echo "==> Baseline de ingesta no encontrada. Creando $(BENCH_BASELINE_INGEST)..."; \
		$(PY) scripts/bench_ingest.py --iterations $(BENCH_ITERATIONS) --warmup $(BENCH_WARMUP) --json $(BENCH_BASELINE_INGEST); \
	else \
		echo "==> Baseline de ingesta encontrada. Comparando contra $(BENCH_BASELINE_INGEST)..."; \
		$(PY) scripts/bench_ingest.py --iterations $(BENCH_ITERATIONS) --warmup $(BENCH_WARMUP) --json $(BENCH_OUT_INGEST) --baseline $(BENCH_BASELINE_INGEST) --max-regression $(BENCH_MAX_REGRESSION); \
	fi

visual-qa:
	@echo "==> Visual QA mobile..."
	VISUAL_QA_URL=$(VISUAL_QA_URL) VISUAL_QA_OUT=$(VISUAL_QA_OUT) bash scripts/visual-qa.sh
