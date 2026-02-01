from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, cast

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Paths
REPO_ROOT = Path(__file__).resolve().parents[2]
REPUTATION_ENV_PATH = REPO_ROOT / "backend" / "reputation" / ".env.reputation"
REPUTATION_ENV_EXAMPLE = REPO_ROOT / "backend" / "reputation" / ".env.reputation.example"

DEFAULT_CONFIG_PATH = REPO_ROOT / "data" / "reputation"
DEFAULT_CACHE_PATH = REPO_ROOT / "data" / "cache" / "reputation_cache.json"
DEFAULT_OVERRIDES_PATH = REPO_ROOT / "data" / "cache" / "reputation_overrides.json"

logger = logging.getLogger(__name__)


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
    overrides_path: Path = Field(
        default=DEFAULT_OVERRIDES_PATH,
        alias="REPUTATION_OVERRIDES_PATH",
    )

    # TTL por defecto (horas) si el config.json no define output.cache_ttl_hours
    cache_ttl_hours: int = Field(default=24, alias="REPUTATION_CACHE_TTL_HOURS")

    # Logging
    log_enabled: bool = Field(default=False, alias="REPUTATION_LOG_ENABLED")
    log_to_file: bool = Field(default=False, alias="REPUTATION_LOG_TO_FILE")
    log_file_name: str = Field(default="reputation.log", alias="REPUTATION_LOG_FILE_NAME")
    log_debug: bool = Field(default=False, alias="REPUTATION_LOG_DEBUG")

    # Toggles de fuentes (Paso 1: todas false por defecto)
    source_reddit: bool = Field(default=False, alias="REPUTATION_SOURCE_REDDIT")
    source_twitter: bool = Field(default=False, alias="REPUTATION_SOURCE_TWITTER")
    source_news: bool = Field(default=False, alias="REPUTATION_SOURCE_NEWS")
    source_newsapi: bool = Field(default=False, alias="REPUTATION_SOURCE_NEWSAPI")
    source_gdelt: bool = Field(default=False, alias="REPUTATION_SOURCE_GDELT")
    source_guardian: bool = Field(default=False, alias="REPUTATION_SOURCE_GUARDIAN")
    source_forums: bool = Field(default=False, alias="REPUTATION_SOURCE_FORUMS")
    source_blogs: bool = Field(default=False, alias="REPUTATION_SOURCE_BLOGS_RSS")
    source_appstore: bool = Field(default=False, alias="REPUTATION_SOURCE_APPSTORE")
    source_trustpilot: bool = Field(default=False, alias="REPUTATION_SOURCE_TRUSTPILOT")
    source_google_reviews: bool = Field(default=False, alias="REPUTATION_SOURCE_GOOGLE_REVIEWS")
    source_google_play: bool = Field(default=False, alias="REPUTATION_SOURCE_GOOGLE_PLAY")
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
        if self.source_newsapi:
            result.append("newsapi")
        if self.source_gdelt:
            result.append("gdelt")
        if self.source_guardian:
            result.append("guardian")
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
        if self.source_google_play:
            result.append("google_play")
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

# Normaliza rutas relativas (si las variables de entorno usan rutas como './data/...')
if not settings.config_path.is_absolute():
    settings.config_path = (REPO_ROOT / settings.config_path).resolve()

if not settings.cache_path.is_absolute():
    settings.cache_path = (REPO_ROOT / settings.cache_path).resolve()

if not settings.overrides_path.is_absolute():
    settings.overrides_path = (REPO_ROOT / settings.overrides_path).resolve()


def load_business_config(path: Path | None = None) -> Dict[str, Any]:
    """Carga uno o varios JSON de negocio (geografías, actores, templates, etc.)."""
    cfg_path = path or settings.config_path
    if not cfg_path.is_absolute():
        cfg_path = (REPO_ROOT / cfg_path).resolve()

    config_files = _resolve_config_files(cfg_path)
    if not config_files:
        raise FileNotFoundError(
            f"Reputation config files not found at {cfg_path} (searched *.json)"
        )

    merged: Dict[str, Any] = {}
    for file_path in config_files:
        data = _load_config_file(file_path)
        merged = _merge_configs(merged, data, file_path)

    if len(config_files) > 1:
        logger.info(
            "Loaded %s reputation config files: %s",
            len(config_files),
            ", ".join(str(p) for p in config_files),
        )

    return merged


def _resolve_config_files(cfg_path: Path) -> list[Path]:
    if cfg_path.exists():
        if cfg_path.is_dir():
            return _sorted_config_files(cfg_path)
        return [cfg_path]

    search_dir = cfg_path if cfg_path.suffix == "" else cfg_path.parent
    if search_dir.exists() and search_dir.is_dir():
        return _sorted_config_files(search_dir)

    return []


def _sorted_config_files(directory: Path) -> list[Path]:
    files = [p for p in directory.glob("*.json") if p.is_file()]

    def sort_key(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        return (0 if name == "config.json" else 1, name)

    return sorted(files, key=sort_key)


def _load_config_file(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Reputation config at {path} must be a JSON object")
    return cast(Dict[str, Any], data)


def _merge_configs(
    base: Dict[str, Any],
    incoming: Dict[str, Any],
    source: Path,
) -> Dict[str, Any]:
    return _merge_dicts(base, incoming, path=source.name)


def _merge_dicts(
    base: Dict[str, Any],
    incoming: Dict[str, Any],
    path: str,
) -> Dict[str, Any]:
    for key, value in incoming.items():
        if key not in base:
            base[key] = _clone_value(value)
            continue
        base[key] = _merge_values(base[key], value, f"{path}.{key}")
    return base


def _merge_values(existing: Any, incoming: Any, path: str) -> Any:
    if isinstance(existing, dict) and isinstance(incoming, dict):
        return _merge_dicts(existing, incoming, path)
    if isinstance(existing, list) and isinstance(incoming, list):
        return _merge_lists(existing, incoming)

    if _is_empty_value(incoming):
        return existing
    if _is_empty_value(existing):
        return incoming
    if existing != incoming:
        logger.debug("Config override at %s: %r -> %r", path, existing, incoming)
    return incoming


def _merge_lists(base: list[Any], incoming: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[tuple[str, str]] = set()

    def add(item: Any) -> None:
        key = _list_item_key(item)
        if key in seen:
            return
        seen.add(key)
        merged.append(item)

    for item in base:
        add(item)
    for item in incoming:
        add(item)
    return merged


def _list_item_key(item: Any) -> tuple[str, str]:
    if isinstance(item, (dict, list)):
        try:
            return ("json", json.dumps(item, sort_keys=True, ensure_ascii=False))
        except TypeError:
            return ("repr", repr(item))
    try:
        return ("value", str(item))
    except Exception:
        return ("repr", repr(item))


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return isinstance(value, (list, dict)) and not value


def _clone_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clone_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clone_value(v) for v in value]
    return value


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
