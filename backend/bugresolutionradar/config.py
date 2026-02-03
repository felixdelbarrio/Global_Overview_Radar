"""Configuracion central del backend.

Lee variables de entorno y expone parametros usados por ingest, reporting y API.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo / env paths
REPO_ROOT = Path(__file__).resolve().parents[2]
BUG_ENV_PATH = REPO_ROOT / "backend" / "bugresolutionradar" / ".env"
BUG_ENV_EXAMPLE = REPO_ROOT / "backend" / "bugresolutionradar" / ".env.example"


def _ensure_env_file() -> None:
    """Crear `backend/bugresolutionradar/.env` desde su `.env.example` si falta."""
    if BUG_ENV_PATH.exists():
        return
    if not BUG_ENV_EXAMPLE.exists():
        return
    BUG_ENV_PATH.write_text(BUG_ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")


# Ensure backend env exists before pydantic reads it
_ensure_env_file()


class Settings(BaseSettings):
    """Parametros de configuracion de la aplicacion.

    Se cargan desde entorno/.env con pydantic-settings. extra="forbid" evita
    variables desconocidas por error de escritura.
    """

    model_config = SettingsConfigDict(
        env_file=str(BUG_ENV_PATH),
        env_file_encoding="utf-8",
        extra="allow",
    )

    ########################################
    # App
    ########################################
    app_name: str = Field(default="Empresas - Global Overview Radar", validation_alias="APP_NAME")
    tz: str = Field(default="Europe/Madrid", validation_alias="TZ")

    ########################################
    # Paths
    ########################################
    assets_dir: str = Field(default="./data/assets", validation_alias="ASSETS_DIR")
    cache_path: str = Field(
        default="./data/cache/bugresolutionradar_cache.json", validation_alias="CACHE_PATH"
    )
    incidents_overrides_path: str = Field(
        default="./data/cache/bugresolutionradar_incidents_overrides.json",
        validation_alias="INCIDENTS_OVERRIDES_PATH",
    )

    ########################################
    # Ingest sources
    ########################################
    sources: str = Field(
        default="filesystem_json,filesystem_csv",
        validation_alias="SOURCES",
        description="Comma-separated list of enabled sources.",
    )

    # XLSX-specific knobs (optional)
    xlsx_ignore_files: str = Field(default="", validation_alias="XLSX_IGNORE_FILES")
    xlsx_preferred_sheet: str = Field(default="Reportes", validation_alias="XLSX_PREFERRED_SHEET")

    ########################################
    # KPI / Reporting settings
    ########################################
    master_threshold_clients: int = Field(default=5, validation_alias="MASTER_THRESHOLD_CLIENTS")
    stale_days_threshold: int = Field(default=15, validation_alias="STALE_DAYS_THRESHOLD")
    period_days_default: int = Field(default=15, validation_alias="PERIOD_DAYS_DEFAULT")

    ########################################
    # Logging
    ########################################
    log_enabled: bool = Field(default=False, validation_alias="LOG_ENABLED")
    log_to_file: bool = Field(default=False, validation_alias="LOG_TO_FILE")
    log_file_name: str = Field(
        default="bugresolutionradar.log",
        validation_alias="LOG_FILE_NAME",
    )
    log_debug: bool = Field(default=False, validation_alias="LOG_DEBUG")

    def enabled_sources(self) -> List[str]:
        """Devuelve la lista de fuentes habilitadas en SOURCES."""
        return [s.strip() for s in self.sources.split(",") if s.strip()]

    def xlsx_ignore_list(self) -> List[str]:
        """Devuelve la lista de ficheros XLSX a ignorar."""
        return [s.strip() for s in self.xlsx_ignore_files.split(",") if s.strip()]


settings = Settings()
