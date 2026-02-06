"""Factory de la aplicacion FastAPI para Global Overview Radar."""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from reputation.api.routers.ingest import router as ingest_router
from reputation.api.routers.reputation import router as reputation_router
from reputation.config import settings
from reputation.logging_utils import configure_logging, get_logger
from reputation.repositories.cache_repo import ReputationCacheRepo

APP_TITLE = "Global Overview Radar"


def create_app() -> FastAPI:
    """Crea y configura la instancia de FastAPI."""
    configure_logging(force=True)
    logger = get_logger(__name__)

    app = FastAPI(title=APP_TITLE)

    app.add_middleware(  # pyright: ignore[reportUnknownMemberType]
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://192.168.1.53:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.cache_repo = ReputationCacheRepo(settings.cache_path)

    app.include_router(reputation_router, prefix="/reputation", tags=["reputation"])
    app.include_router(ingest_router, prefix="/ingest", tags=["ingest"])

    logger.debug("FastAPI app created with cache at %s", settings.cache_path)

    @app.get("/health", include_in_schema=False, status_code=200)
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok", "date": date.today().isoformat()}

    return app


app = create_app()
