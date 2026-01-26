from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = Field(default="BBVA BugResolutionRadar", alias="APP_NAME")
    tz: str = Field(default="Europe/Madrid", alias="TZ")

    assets_dir: str = Field(default="./data/assets", alias="ASSETS_DIR")
    cache_path: str = Field(default="./data/cache/cache.json", alias="CACHE_PATH")

    sources: str = Field(default="filesystem_json,filesystem_csv", alias="SOURCES")

    master_threshold_clients: int = Field(default=5, alias="MASTER_THRESHOLD_CLIENTS")
    stale_days_threshold: int = Field(default=15, alias="STALE_DAYS_THRESHOLD")
    period_days_default: int = Field(default=15, alias="PERIOD_DAYS_DEFAULT")

    def enabled_sources(self) -> list[str]:
        return [s.strip() for s in self.sources.split(",") if s.strip()]


settings = Settings()
