from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, cast

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Paths
REPO_ROOT = Path(__file__).resolve().parents[2]
REPUTATION_ENV_PATH = REPO_ROOT / "backend" / "reputation" / ".env.reputation"
REPUTATION_ENV_EXAMPLE = REPO_ROOT / "backend" / "reputation" / ".env.reputation.example"

DEFAULT_CONFIG_PATH = REPO_ROOT / "data" / "reputation" / "config.json"
DEFAULT_CACHE_PATH = REPO_ROOT / "data" / "cache" / "reputation_cache.json"


class ReputationSettings(BaseSettings):
    """Configuración de reputación (se carga desde .env.reputation)."""

    model_config = SettingsConfigDict(
        env_file=str(REPUTATION_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Feature toggle general
    reputation_enabled: bool = Field(default=False, alias="REPUTATION_ENABLED")

    # Rutas
    config_path: Path = Field(default=DEFAULT_CONFIG_PATH, alias="REPUTATION_CONFIG_PATH")
    cache_path: Path = Field(default=DEFAULT_CACHE_PATH, alias="REPUTATION_CACHE_PATH")

    # TTL por defecto (horas) si el config.json no define output.cache_ttl_hours
    cache_ttl_hours: int = Field(default=24, alias="REPUTATION_CACHE_TTL_HOURS")

    # Toggles de fuentes (Paso 1: todas false por defecto)
    source_reddit: bool = Field(default=False, alias="REPUTATION_SOURCE_REDDIT")
    source_twitter: bool = Field(default=False, alias="REPUTATION_SOURCE_TWITTER")
    source_news: bool = Field(default=False, alias="REPUTATION_SOURCE_NEWS")
    source_forums: bool = Field(default=False, alias="REPUTATION_SOURCE_FORUMS")
    source_blogs: bool = Field(default=False, alias="REPUTATION_SOURCE_BLOGS_RSS")
    source_appstore: bool = Field(default=False, alias="REPUTATION_SOURCE_APPSTORE")
    source_trustpilot: bool = Field(default=False, alias="REPUTATION_SOURCE_TRUSTPILOT")
    source_google_reviews: bool = Field(default=False, alias="REPUTATION_SOURCE_GOOGLE_REVIEWS")
    source_youtube: bool = Field(default=False, alias="REPUTATION_SOURCE_YOUTUBE")
    source_downdetector: bool = Field(default=False, alias="REPUTATION_SOURCE_DOWNDETECTOR")
    sources_allowlist: str = Field(default="", alias="REPUTATION_SOURCES_ALLOWLIST")

    def enabled_sources(self) -> List[str]:
        """Devuelve la lista de fuentes activas según los toggles."""
        result: List[str] = []
        if self.source_reddit:
            result.append("reddit")
        if self.source_twitter:
            result.append("twitter")
        if self.source_news:
            result.append("news")
        if self.source_forums:
            result.append("forums")
        if self.source_blogs:
            result.append("blogs")
        if self.source_appstore:
            result.append("appstore")
        if self.source_trustpilot:
            result.append("trustpilot")
        if self.source_google_reviews:
            result.append("google_reviews")
        if self.source_youtube:
            result.append("youtube")
        if self.source_downdetector:
            result.append("downdetector")
        allowlist = {s.strip().lower() for s in self.sources_allowlist.split(",") if s.strip()}
        if allowlist:
            return [source for source in result if source in allowlist]
        return result


def _ensure_env_file() -> None:
    env_path = REPUTATION_ENV_PATH
    example_path = REPUTATION_ENV_EXAMPLE
    if env_path.exists():
        return
    if not example_path.exists():
        return
    env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")


# Carga .env.reputation en variables de entorno para collectors que leen os.getenv
_ensure_env_file()
load_dotenv(str(REPUTATION_ENV_PATH), override=False)

# Singleton de settings
settings = ReputationSettings()


def load_business_config(path: Path | None = None) -> Dict[str, Any]:
    """Carga el JSON de negocio (geografías, otros actores del mercado, templates, etc.)."""
    cfg_path = path or settings.config_path
    if not cfg_path.exists():
        raise FileNotFoundError(f"Reputation config.json not found at {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)
    return data


def compute_config_hash(cfg: Mapping[str, Any]) -> str:
    """Hash estable del config para invalidar cache al cambiarlo."""
    serialized = json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def effective_ttl_hours(cfg: Mapping[str, Any]) -> int:
    """TTL efectivo: output.cache_ttl_hours del config si existe; si no, settings.

    Nota: Pylance tiende a marcar 'dict' sin parametrizar como Unknown.
    Por eso hacemos cast explícito a dict[str, Any] tras el isinstance.
    """
    raw_output = cfg.get("output")

    if isinstance(raw_output, dict):
        output = cast(Dict[str, Any], raw_output)
        ttl_value = output.get("cache_ttl_hours")

        if isinstance(ttl_value, int) and ttl_value > 0:
            return ttl_value

    return settings.cache_ttl_hours
