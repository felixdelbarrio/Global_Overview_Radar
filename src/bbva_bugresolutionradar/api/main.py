from __future__ import annotations

from datetime import date
from typing import Dict

from fastapi import FastAPI

from bbva_bugresolutionradar.api.routers.kpis import router as kpis_router
from bbva_bugresolutionradar.config import settings
from bbva_bugresolutionradar.repositories import CacheRepo
from bbva_bugresolutionradar.services import ReportingService


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    # Simple DI via app.state
    app.state.settings = settings
    app.state.cache_repo = CacheRepo(settings.cache_path)
    app.state.reporting = ReportingService(settings)

    app.include_router(kpis_router, prefix="/kpis", tags=["kpis"])

    @app.get("/health")
    def health() -> Dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {
            "status": "ok",
            "date": date.today().isoformat(),
        }

    return app


app = create_app()
