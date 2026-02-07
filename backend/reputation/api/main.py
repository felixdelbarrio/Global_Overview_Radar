from __future__ import annotations

from fastapi import FastAPI

from reputation.api.routers.auth import router as auth_router
from reputation.api.routers.ingest import router as ingest_router
from reputation.api.routers.reputation import router as reputation_router


def create_app() -> FastAPI:
    app = FastAPI(title="Global Overview Radar API")
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(reputation_router, prefix="/reputation", tags=["reputation"])
    app.include_router(ingest_router, prefix="/ingest", tags=["ingest"])
    return app


app = create_app()
