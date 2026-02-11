from __future__ import annotations

import os

from fastapi import FastAPI

from reputation.api.routers.auth import router as auth_router
from reputation.api.routers.ingest import router as ingest_router
from reputation.api.routers.reputation import router as reputation_router


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def create_app() -> FastAPI:
    # Disable API docs by default on Cloud Run (public frontend proxy makes the backend reachable).
    # Can be overridden with API_DOCS_ENABLED=true for debugging.
    default_docs_enabled = not bool(os.environ.get("K_SERVICE"))
    docs_enabled = _env_flag("API_DOCS_ENABLED", default_docs_enabled)

    app = FastAPI(
        title="Global Overview Radar API",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(reputation_router, prefix="/reputation", tags=["reputation"])
    app.include_router(ingest_router, prefix="/ingest", tags=["ingest"])
    return app


app = create_app()
