from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bbva_bugresolutionradar.api.routers.evolution import router as evolution_router
from bbva_bugresolutionradar.api.routers.incidents import router as incidents_router
from bbva_bugresolutionradar.api.routers.kpis import router as kpis_router
from bbva_bugresolutionradar.config import settings
from bbva_bugresolutionradar.repositories import CacheRepo
from bbva_bugresolutionradar.services import ReportingService


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    # CORS: permite llamadas desde frontend local y por IP (LAN)
    # - localhost / 127.0.0.1 para uso local
    # - 192.168.x.x para cuando abras el front por IP en la red
    app.add_middleware(  # pyright: ignore[reportUnknownMemberType]
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://192.168.1.53:3000",  # ajusta si tu IP cambia
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Simple DI via app.state
    app.state.settings = settings
    app.state.cache_repo = CacheRepo(settings.cache_path)
    app.state.reporting = ReportingService(settings)

    # Routers
    app.include_router(kpis_router, prefix="/kpis", tags=["kpis"])
    app.include_router(incidents_router, prefix="/incidents", tags=["incidents"])
    app.include_router(evolution_router, prefix="/evolution", tags=["evolution"])

    @app.get("/health", include_in_schema=False, status_code=200)
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok", "date": date.today().isoformat()}

    return app


app = create_app()
