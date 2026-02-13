from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, cast

from dotenv import dotenv_values
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from reputation.env_crypto import decrypt_env_secret, is_encrypted_value
from reputation.state_store import (
    delete_from_state,
    state_store_enabled,
    sync_from_state,
    sync_to_state,
)


def _is_cloud_run_runtime() -> bool:
    return bool(os.getenv("K_SERVICE") or os.getenv("K_REVISION") or os.getenv("CLOUD_RUN_JOB"))


# Paths
PACKAGE_DIR = Path(__file__).resolve().parent
if PACKAGE_DIR.parent.name == "backend":
    REPO_ROOT = PACKAGE_DIR.parent.parent
else:
    REPO_ROOT = PACKAGE_DIR.parent

_SOURCE_ENV_DIR = REPO_ROOT / "backend" / "reputation"
if not _SOURCE_ENV_DIR.exists():
    _SOURCE_ENV_DIR = PACKAGE_DIR

_CLOUD_RUN_RUNTIME = _is_cloud_run_runtime()
_RUNTIME_ENV_DIR = Path(os.getenv("REPUTATION_RUNTIME_ENV_DIR", "/tmp/reputation"))
_ACTIVE_ENV_DIR = _RUNTIME_ENV_DIR if _CLOUD_RUN_RUNTIME else _SOURCE_ENV_DIR

REPUTATION_ENV_PATH = _ACTIVE_ENV_DIR / ".env.reputation"
REPUTATION_ENV_EXAMPLE = _ACTIVE_ENV_DIR / ".env.reputation.example"
REPUTATION_ADVANCED_ENV_PATH = _ACTIVE_ENV_DIR / ".env.reputation.advanced"
REPUTATION_ADVANCED_ENV_EXAMPLE = _ACTIVE_ENV_DIR / ".env.reputation.advanced.example"

_SOURCE_REPUTATION_ENV_PATH = _SOURCE_ENV_DIR / ".env.reputation"
_SOURCE_REPUTATION_ENV_EXAMPLE = _SOURCE_ENV_DIR / ".env.reputation.example"
_SOURCE_REPUTATION_ADVANCED_ENV_PATH = _SOURCE_ENV_DIR / ".env.reputation.advanced"
_SOURCE_REPUTATION_ADVANCED_ENV_EXAMPLE = _SOURCE_ENV_DIR / ".env.reputation.advanced.example"

STATE_KEY_REPUTATION_ENV = "backend/reputation/.env.reputation"
STATE_KEY_REPUTATION_ENV_EXAMPLE = "backend/reputation/.env.reputation.example"
STATE_KEY_REPUTATION_ADVANCED_ENV = "backend/reputation/.env.reputation.advanced"
STATE_KEY_REPUTATION_ADVANCED_ENV_EXAMPLE = "backend/reputation/.env.reputation.advanced.example"
STATE_KEY_PROFILE_STATE = "data/cache/reputation_profile.json"

DEFAULT_CONFIG_PATH = REPO_ROOT / "data" / "reputation"
DEFAULT_LLM_CONFIG_PATH = REPO_ROOT / "data" / "reputation_llm"
_IMMUTABLE_SAMPLE_CONFIG_PATH = REPO_ROOT / "backend" / "data" / "reputation_samples"
_IMMUTABLE_SAMPLE_LLM_CONFIG_PATH = REPO_ROOT / "backend" / "data" / "reputation_llm_samples"
_FALLBACK_SAMPLE_CONFIG_PATH = REPO_ROOT / "data" / "reputation_samples"
_FALLBACK_SAMPLE_LLM_CONFIG_PATH = REPO_ROOT / "data" / "reputation_llm_samples"
DEFAULT_SAMPLE_CONFIG_PATH = (
    _IMMUTABLE_SAMPLE_CONFIG_PATH
    if _IMMUTABLE_SAMPLE_CONFIG_PATH.exists()
    else _FALLBACK_SAMPLE_CONFIG_PATH
)
DEFAULT_SAMPLE_LLM_CONFIG_PATH = (
    _IMMUTABLE_SAMPLE_LLM_CONFIG_PATH
    if _IMMUTABLE_SAMPLE_LLM_CONFIG_PATH.exists()
    else _FALLBACK_SAMPLE_LLM_CONFIG_PATH
)
DEFAULT_CACHE_PATH = REPO_ROOT / "data" / "cache" / "reputation_cache.json"
DEFAULT_OVERRIDES_PATH = REPO_ROOT / "data" / "cache" / "reputation_overrides.json"
PROFILE_STATE_PATH = REPO_ROOT / "data" / "cache" / "reputation_profile.json"
DEFAULT_CACHE_TTL_HOURS = 24

logger = logging.getLogger(__name__)

CLOUDRUN_ONLY_ENV_KEYS = {
    "AUTH_ALLOWED_EMAILS",
    "AUTH_BYPASS_MUTATION_KEY",
    "AUTH_GOOGLE_CLIENT_ID",
    "GOOGLE_CLOUD_LOGIN_REQUESTED",
    "REPUTATION_STATE_BUCKET",
    "REPUTATION_STATE_PREFIX",
    "REPUTATION_RUNTIME_ENV_DIR",
}

_DOTENV_MANAGED_KEYS: set[str] = set()

ALL_SOURCES = [
    "reddit",
    "twitter",
    "news",
    "newsapi",
    "gdelt",
    "guardian",
    "forums",
    "blogs",
    "appstore",
    "trustpilot",
    "google_reviews",
    "google_play",
    "youtube",
    "downdetector",
]


class ReputationSettings(BaseSettings):
    """Configuración de reputación (se carga desde .env.reputation + .advanced)."""

    model_config = SettingsConfigDict(extra="ignore")

    # Rutas
    config_path: Path = Field(default=DEFAULT_CONFIG_PATH, alias="REPUTATION_CONFIG_PATH")
    llm_config_path: Path = Field(
        default=DEFAULT_LLM_CONFIG_PATH,
        alias="REPUTATION_LLM_CONFIG_PATH",
    )
    cache_path: Path = Field(default=DEFAULT_CACHE_PATH, alias="REPUTATION_CACHE_PATH")
    overrides_path: Path = Field(
        default=DEFAULT_OVERRIDES_PATH,
        alias="REPUTATION_OVERRIDES_PATH",
    )
    # Perfil/es de negocio: por defecto carga todos los JSON del directorio.
    # Puede ser un nombre (banking_empresas) o varios separados por coma.
    profiles: str = Field(default="", alias="REPUTATION_PROFILE")

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

    # UI
    ui_show_comparisons: bool = Field(
        default=False,
        alias="REPUTATION_UI_SHOW_COMPARISONS",
    )

    # Auth (Google ID tokens)
    # If true, the UI requires an end-user Google login (ID token).
    # If false, Cloud Run bypasses interactive login and impersonates an allowed email.
    google_cloud_login_requested: bool = Field(
        default=False,
        alias="GOOGLE_CLOUD_LOGIN_REQUESTED",
    )
    # Shared secret required for mutation endpoints while auth bypass is enabled
    # (GOOGLE_CLOUD_LOGIN_REQUESTED=false).
    auth_bypass_mutation_key: str = Field(
        default="",
        alias="AUTH_BYPASS_MUTATION_KEY",
    )
    auth_google_client_id: str = Field(default="", alias="AUTH_GOOGLE_CLIENT_ID")
    auth_allowed_emails: str = Field(default="", alias="AUTH_ALLOWED_EMAILS")
    reputation_state_bucket: str = Field(default="", alias="REPUTATION_STATE_BUCKET")
    reputation_state_prefix: str = Field(
        default="reputation-state", alias="REPUTATION_STATE_PREFIX"
    )

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

    def all_sources(self) -> List[str]:
        """Devuelve todas las fuentes conocidas, ignorando toggles y allowlist."""
        return list(ALL_SOURCES)


def _ensure_env_file() -> None:
    if _CLOUD_RUN_RUNTIME:
        _ACTIVE_ENV_DIR.mkdir(parents=True, exist_ok=True)
        if not state_store_enabled():
            logger.warning(
                "Cloud Run without REPUTATION_STATE_BUCKET: runtime state will be ephemeral."
            )
        sync_reputation_env_files_from_state()

        if not REPUTATION_ENV_EXAMPLE.exists() and _SOURCE_REPUTATION_ENV_EXAMPLE.exists():
            REPUTATION_ENV_EXAMPLE.write_text(
                _SOURCE_REPUTATION_ENV_EXAMPLE.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        if (
            not REPUTATION_ADVANCED_ENV_EXAMPLE.exists()
            and _SOURCE_REPUTATION_ADVANCED_ENV_EXAMPLE.exists()
        ):
            REPUTATION_ADVANCED_ENV_EXAMPLE.write_text(
                _SOURCE_REPUTATION_ADVANCED_ENV_EXAMPLE.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        if (
            not REPUTATION_ADVANCED_ENV_PATH.exists()
            and _SOURCE_REPUTATION_ADVANCED_ENV_PATH.exists()
        ):
            REPUTATION_ADVANCED_ENV_PATH.write_text(
                _SOURCE_REPUTATION_ADVANCED_ENV_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        if not REPUTATION_ENV_PATH.exists() and _SOURCE_REPUTATION_ENV_PATH.exists():
            REPUTATION_ENV_PATH.write_text(
                _SOURCE_REPUTATION_ENV_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
    env_path = REPUTATION_ENV_PATH
    example_path = REPUTATION_ENV_EXAMPLE
    if env_path.exists():
        return
    if not example_path.exists():
        return
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
    persist_reputation_env_files_to_state()


def sync_reputation_env_files_from_state() -> None:
    if not state_store_enabled():
        return
    sync_from_state(REPUTATION_ENV_EXAMPLE, key=STATE_KEY_REPUTATION_ENV_EXAMPLE)
    sync_from_state(REPUTATION_ADVANCED_ENV_EXAMPLE, key=STATE_KEY_REPUTATION_ADVANCED_ENV_EXAMPLE)
    sync_from_state(REPUTATION_ENV_PATH, key=STATE_KEY_REPUTATION_ENV)
    sync_from_state(REPUTATION_ADVANCED_ENV_PATH, key=STATE_KEY_REPUTATION_ADVANCED_ENV)


def persist_reputation_env_files_to_state() -> None:
    if not state_store_enabled():
        return
    sync_to_state(REPUTATION_ENV_EXAMPLE, key=STATE_KEY_REPUTATION_ENV_EXAMPLE)
    sync_to_state(REPUTATION_ADVANCED_ENV_EXAMPLE, key=STATE_KEY_REPUTATION_ADVANCED_ENV_EXAMPLE)
    sync_to_state(REPUTATION_ENV_PATH, key=STATE_KEY_REPUTATION_ENV)
    sync_to_state(REPUTATION_ADVANCED_ENV_PATH, key=STATE_KEY_REPUTATION_ADVANCED_ENV)


def _load_reputation_env_to_os() -> None:
    """Carga .env.reputation + .env.reputation.advanced en `os.environ`."""
    global _DOTENV_MANAGED_KEYS

    env_files = [REPUTATION_ENV_PATH, REPUTATION_ADVANCED_ENV_PATH]
    parsed_sources = [(path, dotenv_values(str(path))) for path in env_files if path.exists()]
    if not parsed_sources:
        for key in list(_DOTENV_MANAGED_KEYS):
            os.environ.pop(key, None)
        _DOTENV_MANAGED_KEYS.clear()
        return

    allowed_values: dict[str, str] = {}
    # Merge order: base env first, advanced env second (advanced overrides base on conflicts).
    for source_path, parsed in parsed_sources:
        for raw_key, raw_value in parsed.items():
            if not raw_key:
                continue
            key = str(raw_key).strip()
            if not key or key in CLOUDRUN_ONLY_ENV_KEYS:
                continue
            value = "" if raw_value is None else str(raw_value)
            decrypted = decrypt_env_secret(value)
            if is_encrypted_value(value) and decrypted == value:
                logger.warning("Unable to decrypt %s from %s; keeping raw value.", key, source_path)
            allowed_values[key] = decrypted

    # Clear keys previously managed by dotenv but removed from file.
    for key in list(_DOTENV_MANAGED_KEYS):
        if key not in allowed_values:
            os.environ.pop(key, None)
            _DOTENV_MANAGED_KEYS.discard(key)

    for key, value in allowed_values.items():
        # Respect externally injected env vars unless this key is already managed from dotenv.
        if key in os.environ and key not in _DOTENV_MANAGED_KEYS:
            continue
        os.environ[key] = value
        _DOTENV_MANAGED_KEYS.add(key)


# Carga .env.reputation + .env.reputation.advanced en variables de entorno para
# collectors que leen os.getenv, excluyendo claves cloud-only.
_ensure_env_file()
_load_reputation_env_to_os()

# Singleton de settings
settings = ReputationSettings()
BASE_CONFIG_PATH = settings.config_path
BASE_LLM_CONFIG_PATH = settings.llm_config_path
_ACTIVE_PROFILE_SOURCE = "default"

# Normaliza rutas relativas (si las variables de entorno usan rutas como './data/...')
if not settings.config_path.is_absolute():
    settings.config_path = (REPO_ROOT / settings.config_path).resolve()

if not settings.llm_config_path.is_absolute():
    settings.llm_config_path = (REPO_ROOT / settings.llm_config_path).resolve()

BASE_CONFIG_PATH = settings.config_path
BASE_LLM_CONFIG_PATH = settings.llm_config_path

if not settings.cache_path.is_absolute():
    settings.cache_path = (REPO_ROOT / settings.cache_path).resolve()

if not settings.overrides_path.is_absolute():
    settings.overrides_path = (REPO_ROOT / settings.overrides_path).resolve()


def load_business_config(path: Path | None = None) -> Dict[str, Any]:
    """Carga uno o varios JSON de negocio (geografías, actores, templates, etc.)."""
    cfg_path = path or settings.config_path
    if not cfg_path.is_absolute():
        cfg_path = (REPO_ROOT / cfg_path).resolve()

    profiles = _parse_profile_selector(settings.profiles)
    config_files = _resolve_config_files(cfg_path, profiles)
    if not config_files:
        raise FileNotFoundError(
            f"Reputation config files not found at {cfg_path} (searched *.json)"
        )

    merged: Dict[str, Any] = {}
    for file_path in config_files:
        data = _load_config_file(file_path)
        merged = _merge_configs(merged, data, file_path)

    llm_files = _resolve_llm_config_files(config_files, settings.llm_config_path)
    for file_path in llm_files:
        data = _load_config_file(file_path)
        merged = _merge_configs(merged, data, file_path)
    merged["_llm_config_loaded"] = bool(llm_files) and len(llm_files) == len(config_files)

    if len(config_files) > 1:
        logger.info(
            "Loaded %s reputation config files: %s",
            len(config_files),
            ", ".join(str(p) for p in config_files),
        )
    if llm_files:
        logger.info(
            "Loaded %s reputation llm config files: %s",
            len(llm_files),
            ", ".join(str(p) for p in llm_files),
        )

    return merged


def _normalize_profile_name(value: str) -> str:
    name = value.strip()
    if name.lower().endswith(".json"):
        name = name[:-5]
    name = name.strip()
    if not name:
        return ""
    # Reject path-like or potentially dangerous profile selectors.
    if name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError(f"Invalid profile name: {value!r}")
    if re.fullmatch(r"[A-Za-z0-9_-]+", name) is None:
        raise ValueError(f"Invalid profile name: {value!r}")
    return name


def _normalize_profile_source(value: str | None) -> str:
    if not value:
        return "default"
    cleaned = value.strip().lower()
    if cleaned in {"sample", "samples", "plantillas"}:
        return "samples"
    return "default"


def normalize_profile_source(value: str | None) -> str:
    """Normaliza el origen del perfil (default vs samples)."""
    return _normalize_profile_source(value)


def _parse_profile_selector(value: str | None) -> list[str]:
    if not value:
        return []
    raw = value.strip()
    if not raw or raw.lower() in {"all", "*", "todos"}:
        return []
    parts: list[str] = []
    for raw_part in raw.split(","):
        normalized = _normalize_profile_name(raw_part)
        if normalized:
            parts.append(normalized)
    return parts


def _filter_profile_files(
    files: Sequence[Path],
    profiles: Sequence[str] | None,
) -> list[Path]:
    selected, missing = _select_profile_files(files, profiles)
    if missing:
        raise FileNotFoundError(f"Reputation profile(s) not found: {', '.join(sorted(missing))}")
    return selected


def _select_profile_files(
    files: Sequence[Path],
    profiles: Sequence[str] | None,
) -> tuple[list[Path], set[str]]:
    if not profiles:
        return list(files), set()
    profile_set = {
        _normalize_profile_name(p).lower() for p in profiles if _normalize_profile_name(p)
    }
    selected = [file for file in files if file.stem.lower() in profile_set]
    missing = profile_set - {file.stem.lower() for file in files}
    return selected, missing


def _sync_missing_profiles_from_state(cfg_dir: Path, missing_profiles: set[str]) -> bool:
    if not missing_profiles or not state_store_enabled():
        return False
    sample_cfg_by_profile, _ = _sample_profile_file_maps()
    synced_any = False
    for profile in sorted(missing_profiles):
        sample_cfg = sample_cfg_by_profile.get(profile.lower())
        if sample_cfg is None:
            continue
        target = cfg_dir / sample_cfg.name
        synced = sync_from_state(target, repo_root=REPO_ROOT)
        synced_any = synced_any or synced
    return synced_any


def _seed_missing_profiles_from_samples(
    cfg_dir: Path,
    missing_profiles: set[str],
) -> bool:
    if not missing_profiles:
        return False
    if not DEFAULT_SAMPLE_CONFIG_PATH.exists() or not DEFAULT_SAMPLE_CONFIG_PATH.is_dir():
        return False

    sample_cfg_by_profile, sample_llm_by_profile = _sample_profile_file_maps()
    seeded_any = False
    for profile in sorted(missing_profiles):
        sample_cfg = sample_cfg_by_profile.get(profile.lower())
        if sample_cfg is None:
            continue

        cfg_dir.mkdir(parents=True, exist_ok=True)
        dst_cfg = cfg_dir / sample_cfg.name
        shutil.copy2(sample_cfg, dst_cfg)
        if state_store_enabled():
            sync_to_state(dst_cfg, repo_root=REPO_ROOT)
        seeded_any = True

        sample_llm = sample_llm_by_profile.get(profile.lower())
        if sample_llm is not None:
            BASE_LLM_CONFIG_PATH.mkdir(parents=True, exist_ok=True)
            dst_llm = BASE_LLM_CONFIG_PATH / sample_llm.name
            shutil.copy2(sample_llm, dst_llm)
            if state_store_enabled():
                sync_to_state(dst_llm, repo_root=REPO_ROOT)

    return seeded_any


def _resolve_profile_files_with_recovery(
    cfg_dir: Path,
    profiles: Sequence[str] | None,
) -> list[Path]:
    files = _sorted_config_files(cfg_dir)
    selected, missing = _select_profile_files(files, profiles)
    if not missing:
        return selected

    if _sync_missing_profiles_from_state(cfg_dir, missing):
        files = _sorted_config_files(cfg_dir)
        selected, missing = _select_profile_files(files, profiles)
        if not missing:
            return selected

    is_default_runtime_dir = cfg_dir.resolve() == BASE_CONFIG_PATH.resolve()
    if is_default_runtime_dir and _seed_missing_profiles_from_samples(cfg_dir, missing):
        files = _sorted_config_files(cfg_dir)
        selected, missing = _select_profile_files(files, profiles)
        if not missing:
            return selected

    raise FileNotFoundError(f"Reputation profile(s) not found: {', '.join(sorted(missing))}")


def _resolve_config_files(cfg_path: Path, profiles: Sequence[str] | None = None) -> list[Path]:
    if cfg_path.exists():
        if cfg_path.is_dir():
            return _resolve_profile_files_with_recovery(cfg_path, profiles)
        if profiles:
            profile_set = {
                _normalize_profile_name(p).lower() for p in profiles if _normalize_profile_name(p)
            }
            if cfg_path.stem.lower() not in profile_set:
                raise FileNotFoundError(
                    f"Reputation profile(s) not found: {', '.join(sorted(profile_set))}"
                )
        return [cfg_path]

    search_dir = cfg_path if cfg_path.suffix == "" else cfg_path.parent
    if profiles and not search_dir.exists():
        expected = {
            _normalize_profile_name(p).lower() for p in profiles if _normalize_profile_name(p)
        }
        _sync_missing_profiles_from_state(search_dir, expected)
        if search_dir.resolve() == BASE_CONFIG_PATH.resolve():
            _seed_missing_profiles_from_samples(search_dir, expected)
    if search_dir.exists() and search_dir.is_dir():
        return _resolve_profile_files_with_recovery(search_dir, profiles)

    return []


def _resolve_paths_for_source(source: str) -> tuple[Path, Path]:
    if source == "samples":
        return (DEFAULT_SAMPLE_CONFIG_PATH, DEFAULT_SAMPLE_LLM_CONFIG_PATH)
    return _resolve_default_workspace_paths()


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _resolve_default_workspace_paths() -> tuple[Path, Path]:
    cfg_path = BASE_CONFIG_PATH
    llm_path = BASE_LLM_CONFIG_PATH

    if _path_is_within(cfg_path, DEFAULT_SAMPLE_CONFIG_PATH):
        logger.warning(
            "REPUTATION_CONFIG_PATH points to samples (%s); using default workspace path (%s).",
            cfg_path,
            DEFAULT_CONFIG_PATH,
        )
        cfg_path = DEFAULT_CONFIG_PATH

    if _path_is_within(llm_path, DEFAULT_SAMPLE_LLM_CONFIG_PATH):
        logger.warning(
            "REPUTATION_LLM_CONFIG_PATH points to sample llm (%s); using default workspace "
            "path (%s).",
            llm_path,
            DEFAULT_LLM_CONFIG_PATH,
        )
        llm_path = DEFAULT_LLM_CONFIG_PATH

    return cfg_path, llm_path


def _load_profile_state() -> dict[str, Any]:
    if state_store_enabled():
        sync_from_state(
            PROFILE_STATE_PATH,
            key=STATE_KEY_PROFILE_STATE,
            repo_root=REPO_ROOT,
        )
    if not PROFILE_STATE_PATH.exists():
        return {}
    try:
        data = json.loads(PROFILE_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _save_profile_state(source: str, profiles: Sequence[str]) -> None:
    PROFILE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": source, "profiles": list(profiles)}
    PROFILE_STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if state_store_enabled():
        sync_to_state(
            PROFILE_STATE_PATH,
            key=STATE_KEY_PROFILE_STATE,
            repo_root=REPO_ROOT,
        )


def _profile_key_from_files(files: Sequence[Path]) -> str:
    stems = sorted({file.stem for file in files})
    if not stems:
        return "empty"
    return "__".join(stems)


def _apply_profile_cache_paths(cfg_settings: ReputationSettings) -> None:
    profiles = _parse_profile_selector(cfg_settings.profiles)
    try:
        config_files = _resolve_config_files(cfg_settings.config_path, profiles)
    except FileNotFoundError as exc:
        logger.warning("Profile cache paths skipped: %s", exc)
        return
    if not config_files:
        return
    profile_key = _profile_key_from_files(config_files)
    if _ACTIVE_PROFILE_SOURCE != "default":
        profile_key = f"{_ACTIVE_PROFILE_SOURCE}__{profile_key}"

    cache_base = cfg_settings.cache_path
    if (
        cache_base.name.startswith("reputation_cache__")
        and "{profile" not in str(cache_base)
        and cache_base != DEFAULT_CACHE_PATH
    ):
        cache_base = DEFAULT_CACHE_PATH
    cfg_settings.cache_path = _apply_profile_path_template(
        cache_base,
        DEFAULT_CACHE_PATH,
        f"reputation_cache__{profile_key}.json",
        profile_key,
    )
    overrides_base = cfg_settings.overrides_path
    if (
        overrides_base.name.startswith("reputation_overrides__")
        and "{profile" not in str(overrides_base)
        and overrides_base != DEFAULT_OVERRIDES_PATH
    ):
        overrides_base = DEFAULT_OVERRIDES_PATH
    cfg_settings.overrides_path = _apply_profile_path_template(
        overrides_base,
        DEFAULT_OVERRIDES_PATH,
        f"reputation_overrides__{profile_key}.json",
        profile_key,
    )


def _resolve_llm_config_files(cfg_files: list[Path], llm_path: Path) -> list[Path]:
    if llm_path.exists() and llm_path.is_file():
        return [llm_path]
    if llm_path.suffix:
        if state_store_enabled():
            sync_from_state(llm_path, repo_root=REPO_ROOT)
        if llm_path.exists() and llm_path.is_file():
            return [llm_path]
        return []

    llm_files: list[Path] = []
    for cfg_file in cfg_files:
        candidate = llm_path / f"{cfg_file.stem}_llm.json"
        if not candidate.exists() and state_store_enabled():
            sync_from_state(candidate, repo_root=REPO_ROOT)
        if candidate.exists() and candidate.is_file():
            llm_files.append(candidate)
    return llm_files


def _sorted_config_files(directory: Path) -> list[Path]:
    files = [p for p in directory.glob("*.json") if p.is_file()]

    def sort_key(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        return (0 if name == "config.json" else 1, name)

    return sorted(files, key=sort_key)


def _sample_profile_file_maps() -> tuple[dict[str, Path], dict[str, Path]]:
    sample_cfg_by_profile: dict[str, Path] = {}
    if DEFAULT_SAMPLE_CONFIG_PATH.exists() and DEFAULT_SAMPLE_CONFIG_PATH.is_dir():
        for sample_cfg in _sorted_config_files(DEFAULT_SAMPLE_CONFIG_PATH):
            sample_cfg_by_profile[sample_cfg.stem.lower()] = sample_cfg

    sample_llm_by_profile: dict[str, Path] = {}
    if DEFAULT_SAMPLE_LLM_CONFIG_PATH.exists() and DEFAULT_SAMPLE_LLM_CONFIG_PATH.is_dir():
        for sample_llm in _sorted_config_files(DEFAULT_SAMPLE_LLM_CONFIG_PATH):
            stem = sample_llm.stem
            if not stem.lower().endswith("_llm"):
                continue
            profile_stem = stem[:-4]
            if profile_stem:
                sample_llm_by_profile[profile_stem.lower()] = sample_llm

    return sample_cfg_by_profile, sample_llm_by_profile


def active_profiles() -> list[str]:
    profiles = _parse_profile_selector(settings.profiles)
    try:
        files = _resolve_config_files(settings.config_path, profiles)
    except FileNotFoundError:
        return []
    return [file.stem for file in files]


def active_profile_key() -> str:
    profiles = _parse_profile_selector(settings.profiles)
    try:
        files = _resolve_config_files(settings.config_path, profiles)
    except FileNotFoundError:
        files = []
    key = _profile_key_from_files(files)
    if _ACTIVE_PROFILE_SOURCE != "default":
        return f"{_ACTIVE_PROFILE_SOURCE}__{key}"
    return key


def active_profile_source() -> str:
    return _ACTIVE_PROFILE_SOURCE


def list_available_profiles(source: str) -> list[str]:
    source_key = _normalize_profile_source(source)
    cfg_path, _ = _resolve_paths_for_source(source_key)
    if not cfg_path.exists():
        return []
    if cfg_path.is_file():
        return [cfg_path.stem]
    return [file.stem for file in _sorted_config_files(cfg_path)]


def set_profile_state(source: str, profiles: Sequence[str] | None) -> dict[str, Any]:
    global _ACTIVE_PROFILE_SOURCE
    source_key = _normalize_profile_source(source)
    cfg_path, llm_path = _resolve_paths_for_source(source_key)

    available_profiles = list_available_profiles(source_key)
    available_map = {name.lower(): name for name in available_profiles}
    profile_list: list[str] = []
    missing_profiles: list[str] = []
    seen_profiles: set[str] = set()
    if profiles:
        for entry in profiles:
            if isinstance(entry, str) and entry.strip():
                normalized = _normalize_profile_name(entry)
                canonical = available_map.get(normalized.lower())
                if canonical is None:
                    missing_profiles.append(normalized)
                    continue
                lower_canonical = canonical.lower()
                if lower_canonical in seen_profiles:
                    continue
                seen_profiles.add(lower_canonical)
                profile_list.append(canonical)
    if missing_profiles:
        raise FileNotFoundError(
            f"Reputation profile(s) not found: {', '.join(sorted(set(missing_profiles)))}"
        )

    settings.config_path = cfg_path.resolve()
    settings.llm_config_path = llm_path.resolve()
    settings.profiles = ",".join(profile_list)
    _ACTIVE_PROFILE_SOURCE = source_key

    _resolve_config_files(settings.config_path, profile_list)
    _apply_profile_cache_paths(settings)
    _save_profile_state(source_key, profile_list)

    return {
        "source": _ACTIVE_PROFILE_SOURCE,
        "profiles": active_profiles(),
        "profile_key": active_profile_key(),
    }


def _clear_json_files(directory: Path) -> list[str]:
    """Elimina ficheros .json de un directorio."""
    removed: list[str] = []
    directory.mkdir(parents=True, exist_ok=True)
    for file_path in directory.glob("*.json"):
        if file_path.is_file():
            file_path.unlink()
            if state_store_enabled():
                delete_from_state(file_path, repo_root=REPO_ROOT)
            removed.append(file_path.name)
    return removed


def _copy_files(files: Sequence[Path], dest_dir: Path) -> list[str]:
    """Copia ficheros a un directorio destino."""
    copied: list[str] = []
    dest_dir.mkdir(parents=True, exist_ok=True)
    for file_path in files:
        dest_path = dest_dir / file_path.name
        shutil.copy2(file_path, dest_path)
        if state_store_enabled():
            sync_to_state(dest_path, repo_root=REPO_ROOT)
        copied.append(dest_path.name)
    return copied


def _resolve_llm_candidates(
    cfg_files: Sequence[Path],
    llm_dir: Path,
) -> tuple[list[Path], list[str]]:
    llm_files: list[Path] = []
    missing: list[str] = []
    for cfg_file in cfg_files:
        candidate = llm_dir / f"{cfg_file.stem}_llm.json"
        if candidate.exists() and candidate.is_file():
            llm_files.append(candidate)
        else:
            missing.append(candidate.name)
    return llm_files, missing


def apply_sample_profiles_to_default(
    profiles: Sequence[str] | None,
) -> dict[str, Any]:
    """Copia plantillas (samples) a carpetas de ejecucion y activa esos perfiles."""
    profile_list: list[str] = []
    if profiles:
        for entry in profiles:
            if isinstance(entry, str) and entry.strip():
                profile_list.append(_normalize_profile_name(entry))

    if not profile_list:
        raise FileNotFoundError("No sample profiles selected")

    cfg_files = _resolve_config_files(DEFAULT_SAMPLE_CONFIG_PATH, profile_list)
    if not cfg_files:
        raise FileNotFoundError(
            f"Sample profiles not found at {DEFAULT_SAMPLE_CONFIG_PATH} (searched *.json)"
        )
    llm_files, llm_missing = _resolve_llm_candidates(cfg_files, DEFAULT_SAMPLE_LLM_CONFIG_PATH)

    default_cfg_path, default_llm_path = _resolve_default_workspace_paths()

    removed_cfg = _clear_json_files(default_cfg_path)
    removed_llm = _clear_json_files(default_llm_path)

    copied_cfg = _copy_files(cfg_files, default_cfg_path)
    copied_llm = _copy_files(llm_files, default_llm_path)

    active = set_profile_state("default", profile_list)
    return {
        "active": active,
        "copied": {
            "config": copied_cfg,
            "llm": copied_llm,
        },
        "removed": {
            "config": removed_cfg,
            "llm": removed_llm,
        },
        "missing": {
            "llm": llm_missing,
        },
    }


def _apply_profile_path_template(
    value: Path,
    default_value: Path,
    default_filename: str,
    profile_key: str,
) -> Path:
    value_str = str(value)
    if "{profile}" in value_str or "{profiles}" in value_str or "{profile_key}" in value_str:
        replaced = (
            value_str.replace("{profile}", profile_key)
            .replace("{profiles}", profile_key)
            .replace("{profile_key}", profile_key)
        )
        return Path(replaced)
    if value == default_value:
        return value.with_name(default_filename)
    return value


def _apply_profile_state(cfg_settings: ReputationSettings) -> None:
    global _ACTIVE_PROFILE_SOURCE
    state = _load_profile_state()
    if not state:
        return
    source_key = _normalize_profile_source(state.get("source"))
    profiles = state.get("profiles")
    profile_list: list[str] = []
    if isinstance(profiles, str):
        profile_list = _parse_profile_selector(profiles)
    elif isinstance(profiles, list):
        for entry in profiles:
            if isinstance(entry, str) and entry.strip():
                profile_list.append(_normalize_profile_name(entry))
    cfg_path, llm_path = _resolve_paths_for_source(source_key)
    cfg_settings.config_path = cfg_path.resolve()
    cfg_settings.llm_config_path = llm_path.resolve()
    cfg_settings.profiles = ",".join(profile_list)
    _ACTIVE_PROFILE_SOURCE = source_key


_apply_profile_state(settings)
_apply_profile_cache_paths(settings)


def reload_reputation_settings() -> None:
    """Recarga settings desde .env.reputation y .env.reputation.advanced."""
    global BASE_CONFIG_PATH, BASE_LLM_CONFIG_PATH
    sync_reputation_env_files_from_state()
    _load_reputation_env_to_os()
    new_settings = ReputationSettings()

    for field_name in type(settings).model_fields:
        setattr(settings, field_name, getattr(new_settings, field_name))

    if not settings.config_path.is_absolute():
        settings.config_path = (REPO_ROOT / settings.config_path).resolve()
    if not settings.llm_config_path.is_absolute():
        settings.llm_config_path = (REPO_ROOT / settings.llm_config_path).resolve()
    if not settings.cache_path.is_absolute():
        settings.cache_path = (REPO_ROOT / settings.cache_path).resolve()
    if not settings.overrides_path.is_absolute():
        settings.overrides_path = (REPO_ROOT / settings.overrides_path).resolve()

    BASE_CONFIG_PATH = settings.config_path
    BASE_LLM_CONFIG_PATH = settings.llm_config_path

    _apply_profile_state(settings)
    _apply_profile_cache_paths(settings)


def _load_config_file(path: Path) -> Dict[str, Any]:
    if state_store_enabled():
        sync_from_state(path, repo_root=REPO_ROOT)
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
    """TTL efectivo: output.cache_ttl_hours del config si existe; si no, fallback interno.

    Nota: Pylance tiende a marcar 'dict' sin parametrizar como Unknown.
    Por eso hacemos cast explícito a dict[str, Any] tras el isinstance.
    """
    raw_output = cfg.get("output")

    if isinstance(raw_output, dict):
        output = cast(Dict[str, Any], raw_output)
        ttl_value = output.get("cache_ttl_hours")

        if isinstance(ttl_value, int) and ttl_value > 0:
            return ttl_value

    return DEFAULT_CACHE_TTL_HOURS
