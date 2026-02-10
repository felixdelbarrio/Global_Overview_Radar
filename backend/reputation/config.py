from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, cast

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Paths
REPO_ROOT = Path(__file__).resolve().parents[2]
REPUTATION_ENV_PATH = REPO_ROOT / "backend" / "reputation" / ".env.reputation"
REPUTATION_ENV_EXAMPLE = REPO_ROOT / "backend" / "reputation" / ".env.reputation.example"

DEFAULT_CONFIG_PATH = REPO_ROOT / "data" / "reputation"
DEFAULT_LLM_CONFIG_PATH = REPO_ROOT / "data" / "reputation_llm"
DEFAULT_SAMPLE_CONFIG_PATH = REPO_ROOT / "data" / "reputation_samples"
DEFAULT_SAMPLE_LLM_CONFIG_PATH = REPO_ROOT / "data" / "reputation_llm_samples"
DEFAULT_CACHE_PATH = REPO_ROOT / "data" / "cache" / "reputation_cache.json"
DEFAULT_OVERRIDES_PATH = REPO_ROOT / "data" / "cache" / "reputation_overrides.json"
PROFILE_STATE_PATH = REPO_ROOT / "data" / "cache" / "reputation_profile.json"
DEFAULT_CACHE_TTL_HOURS = 24

logger = logging.getLogger(__name__)

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
    """Configuración de reputación (se carga desde .env.reputation)."""

    model_config = SettingsConfigDict(
        env_file=str(REPUTATION_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

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
    auth_enabled: bool = Field(default=False, alias="AUTH_ENABLED")
    # If true, the UI requires an end-user Google login (ID token).
    # If false, Cloud Run bypasses interactive login and impersonates an allowed email.
    google_cloud_login_requested: bool = Field(
        default=False,
        alias="GOOGLE_CLOUD_LOGIN_REQUESTED",
    )
    # If auth bypass is enabled, mutation endpoints stay blocked unless explicitly enabled.
    auth_bypass_allow_mutations: bool = Field(
        default=False,
        alias="AUTH_BYPASS_ALLOW_MUTATIONS",
    )
    # Shared secret required for mutation endpoints while auth bypass is enabled.
    auth_bypass_mutation_key: str = Field(
        default="",
        alias="AUTH_BYPASS_MUTATION_KEY",
    )
    auth_google_client_id: str = Field(default="", alias="AUTH_GOOGLE_CLIENT_ID")
    auth_allowed_emails: str = Field(default="", alias="AUTH_ALLOWED_EMAILS")

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
    return name.strip()


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
    parts = [_normalize_profile_name(part) for part in raw.split(",")]
    return [part for part in parts if part]


def _filter_profile_files(
    files: Sequence[Path],
    profiles: Sequence[str] | None,
) -> list[Path]:
    if not profiles:
        return list(files)
    profile_set = {p.lower() for p in profiles}
    selected = [file for file in files if file.stem.lower() in profile_set]
    missing = profile_set - {file.stem.lower() for file in files}
    if missing:
        raise FileNotFoundError(f"Reputation profile(s) not found: {', '.join(sorted(missing))}")
    return selected


def _resolve_config_files(cfg_path: Path, profiles: Sequence[str] | None = None) -> list[Path]:
    if cfg_path.exists():
        if cfg_path.is_dir():
            return _filter_profile_files(_sorted_config_files(cfg_path), profiles)
        if profiles:
            profile_set = {p.lower() for p in profiles}
            if cfg_path.stem.lower() not in profile_set:
                raise FileNotFoundError(
                    f"Reputation profile(s) not found: {', '.join(sorted(profile_set))}"
                )
        return [cfg_path]

    search_dir = cfg_path if cfg_path.suffix == "" else cfg_path.parent
    if search_dir.exists() and search_dir.is_dir():
        return _filter_profile_files(_sorted_config_files(search_dir), profiles)

    return []


def _resolve_paths_for_source(source: str) -> tuple[Path, Path]:
    if source == "samples":
        return (DEFAULT_SAMPLE_CONFIG_PATH, DEFAULT_SAMPLE_LLM_CONFIG_PATH)
    return (BASE_CONFIG_PATH, BASE_LLM_CONFIG_PATH)


def _load_profile_state() -> dict[str, Any]:
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
    if not llm_path.exists():
        return []
    if llm_path.is_file():
        return [llm_path]
    if not llm_path.is_dir():
        return []
    llm_files: list[Path] = []
    for cfg_file in cfg_files:
        candidate = llm_path / f"{cfg_file.stem}_llm.json"
        if candidate.exists() and candidate.is_file():
            llm_files.append(candidate)
    return llm_files


def _sorted_config_files(directory: Path) -> list[Path]:
    files = [p for p in directory.glob("*.json") if p.is_file()]

    def sort_key(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        return (0 if name == "config.json" else 1, name)

    return sorted(files, key=sort_key)


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
    profile_list: list[str] = []
    if profiles:
        for entry in profiles:
            if isinstance(entry, str) and entry.strip():
                profile_list.append(_normalize_profile_name(entry))

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
            removed.append(file_path.name)
    return removed


def _copy_files(files: Sequence[Path], dest_dir: Path) -> list[str]:
    """Copia ficheros a un directorio destino."""
    copied: list[str] = []
    dest_dir.mkdir(parents=True, exist_ok=True)
    for file_path in files:
        dest_path = dest_dir / file_path.name
        shutil.copy2(file_path, dest_path)
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

    removed_cfg = _clear_json_files(BASE_CONFIG_PATH)
    removed_llm = _clear_json_files(BASE_LLM_CONFIG_PATH)

    copied_cfg = _copy_files(cfg_files, BASE_CONFIG_PATH)
    copied_llm = _copy_files(llm_files, BASE_LLM_CONFIG_PATH)

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
    """Recarga settings desde .env.reputation y aplica normalizaciones."""
    global BASE_CONFIG_PATH, BASE_LLM_CONFIG_PATH
    new_settings = ReputationSettings()

    for field_name in settings.model_fields:
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
