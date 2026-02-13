from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from reputation.config import (
    CLOUDRUN_ONLY_ENV_KEYS,
    REPUTATION_ADVANCED_ENV_EXAMPLE,
    REPUTATION_ADVANCED_ENV_PATH,
    REPUTATION_ENV_EXAMPLE,
    REPUTATION_ENV_PATH,
    persist_reputation_env_files_to_state,
    reload_reputation_settings,
    sync_reputation_env_files_from_state,
)
from reputation.env_crypto import decrypt_env_secret, encrypt_env_secret

SettingKind = Literal["boolean", "string", "secret", "number", "select"]


@dataclass(frozen=True)
class UserSettingField:
    key: str
    env: str
    group: str
    label: str
    description: str
    kind: SettingKind
    default: Any
    options: list[str] | None = None
    placeholder: str | None = None


GROUPS: list[dict[str, str]] = [
    {
        "id": "language",
        "label": "Idioma",
        "description": "Selecciona el idioma general para noticias y traducciones de opiniones.",
    },
    {
        "id": "sources_markets",
        "label": "Fuentes Markets",
        "description": ("Activa o desactiva fuentes de marketplaces y reseñas de producto."),
    },
    {
        "id": "sources_press",
        "label": "Fuentes Prensa OPEN",
        "description": ("Activa o desactiva fuentes abiertas (prensa, social, foros y blogs)."),
    },
    {
        "id": "sources_credentials",
        "label": "Fuentes Prensa API KEY REQUESTED",
        "description": "Configura API Keys y activación de las fuentes que las requieren.",
    },
    {
        "id": "news",
        "label": "Noticias",
        "description": "Preferencias rápidas para fuentes de noticias.",
    },
    {
        "id": "llm",
        "label": "IA (LLM)",
        "description": "Activa la clasificación con IA y configura el proveedor.",
    },
    {
        "id": "advanced",
        "label": "Avanzado",
        "description": "Variables técnicas (solo si sabes lo que haces).",
    },
]

LANGUAGE_OPTIONS = [
    "es",
    "en",
    "fr",
    "de",
    "it",
    "pt",
    "ar",
    "ru",
    "zh",
    "nl",
    "no",
    "sv",
    "he",
    "ud",
]


FIELDS: list[UserSettingField] = [
    UserSettingField(
        key="language.preference",
        env="NEWS_LANG",
        group="language",
        label="Idioma general",
        description="Se aplica a RSS, NewsAPI y traducciones.",
        kind="select",
        default="es",
        options=LANGUAGE_OPTIONS,
    ),
    UserSettingField(
        key="visualization.show_comparisons",
        env="REPUTATION_UI_SHOW_COMPARISONS",
        group="language",
        label="Comparar con otros actores",
        description=(
            "Si está desactivado, el frontend oculta la comparación con otros actores "
            "y muestra solo el actor principal."
        ),
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="visualization.show_dashboard_responses",
        env="REPUTATION_UI_SHOW_DASHBOARD_RESPONSES",
        group="language",
        label="Opiniones contestadas en Dashboard",
        description=("Si está activado, el Dashboard muestra el bloque de opiniones contestadas."),
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.news",
        env="REPUTATION_SOURCE_NEWS",
        group="sources_press",
        label="Noticias (RSS)",
        description="Agregadores y RSS.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.newsapi",
        env="REPUTATION_SOURCE_NEWSAPI",
        group="sources_credentials",
        label="NewsAPI",
        description="Proveedor NewsAPI.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.gdelt",
        env="REPUTATION_SOURCE_GDELT",
        group="sources_press",
        label="GDELT",
        description="Global Database of Events.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.guardian",
        env="REPUTATION_SOURCE_GUARDIAN",
        group="sources_credentials",
        label="The Guardian",
        description="Open Platform.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.forums",
        env="REPUTATION_SOURCE_FORUMS",
        group="sources_press",
        label="Foros",
        description="Foros y comunidades.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.blogs",
        env="REPUTATION_SOURCE_BLOGS_RSS",
        group="sources_press",
        label="Blogs",
        description="Blogs RSS.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.appstore",
        env="REPUTATION_SOURCE_APPSTORE",
        group="sources_markets",
        label="App Store",
        description="Opiniones en App Store.",
        kind="boolean",
        default=True,
    ),
    UserSettingField(
        key="sources.trustpilot",
        env="REPUTATION_SOURCE_TRUSTPILOT",
        group="sources_press",
        label="Trustpilot",
        description="Reseñas Trustpilot.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.google_reviews",
        env="REPUTATION_SOURCE_GOOGLE_REVIEWS",
        group="sources_credentials",
        label="Google Reviews",
        description="Reseñas de Google.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.google_play",
        env="REPUTATION_SOURCE_GOOGLE_PLAY",
        group="sources_markets",
        label="Google Play",
        description="Opiniones en Google Play.",
        kind="boolean",
        default=True,
    ),
    UserSettingField(
        key="sources.youtube",
        env="REPUTATION_SOURCE_YOUTUBE",
        group="sources_credentials",
        label="YouTube",
        description="Comentarios y menciones en YouTube.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.reddit",
        env="REPUTATION_SOURCE_REDDIT",
        group="sources_credentials",
        label="Reddit",
        description="Conversaciones en Reddit.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.twitter",
        env="REPUTATION_SOURCE_TWITTER",
        group="sources_credentials",
        label="X / Twitter",
        description="Conversaciones en X (Twitter).",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="sources.downdetector",
        env="REPUTATION_SOURCE_DOWNDETECTOR",
        group="sources_markets",
        label="Downdetector",
        description="Incidencias y caídas.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="keys.news",
        env="NEWS_API_KEY",
        group="news",
        label="API Key News (opcional)",
        description="Clave para proveedor News si quieres usar API además de RSS.",
        kind="secret",
        default="",
        placeholder="sk-...",
    ),
    UserSettingField(
        key="advanced.log_enabled",
        env="REPUTATION_LOG_ENABLED",
        group="advanced",
        label="Log habilitado",
        description="Activa la salida de logs técnicos.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="advanced.log_to_file",
        env="REPUTATION_LOG_TO_FILE",
        group="advanced",
        label="Log a fichero",
        description="Guarda los logs en un fichero local.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="advanced.log_file_name",
        env="REPUTATION_LOG_FILE_NAME",
        group="advanced",
        label="Nombre del fichero de log",
        description="Nombre del fichero donde se guardan los logs.",
        kind="string",
        default="reputation.log",
    ),
    UserSettingField(
        key="advanced.log_debug",
        env="REPUTATION_LOG_DEBUG",
        group="advanced",
        label="Log en modo debug",
        description="Incluye detalles adicionales de diagnóstico.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="keys.newsapi",
        env="NEWSAPI_API_KEY",
        group="sources_credentials",
        label="API Key NewsAPI",
        description="Clave oficial de NewsAPI.",
        kind="secret",
        default="",
        placeholder="api-key",
    ),
    UserSettingField(
        key="keys.guardian",
        env="GUARDIAN_API_KEY",
        group="sources_credentials",
        label="API Key Guardian",
        description="Clave de The Guardian.",
        kind="secret",
        default="",
        placeholder="guardian-key",
    ),
    UserSettingField(
        key="keys.reddit_id",
        env="REDDIT_CLIENT_ID",
        group="sources_credentials",
        label="Reddit Reader API Key",
        description="Credencial de lectura de Reddit.",
        kind="secret",
        default="",
    ),
    UserSettingField(
        key="keys.twitter_bearer",
        env="TWITTER_BEARER_TOKEN",
        group="sources_credentials",
        label="X / Twitter Bearer",
        description="Token Bearer de X.",
        kind="secret",
        default="",
    ),
    UserSettingField(
        key="keys.google_places",
        env="GOOGLE_PLACES_API_KEY",
        group="sources_credentials",
        label="Google Places API Key",
        description="Clave para Google Places.",
        kind="secret",
        default="",
    ),
    UserSettingField(
        key="keys.google_play",
        env="GOOGLE_PLAY_API_KEY",
        group="advanced",
        label="Google Play API Key",
        description="Clave para Google Play API.",
        kind="secret",
        default="",
    ),
    UserSettingField(
        key="keys.youtube",
        env="YOUTUBE_API_KEY",
        group="sources_credentials",
        label="YouTube API Key",
        description="Clave para YouTube Data API.",
        kind="secret",
        default="",
    ),
    UserSettingField(
        key="llm.enabled",
        env="LLM_ENABLED",
        group="llm",
        label="IA activa",
        description="Activa la clasificación con IA.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="llm.provider",
        env="LLM_PROVIDER",
        group="llm",
        label="Proveedor",
        description="Proveedor de IA principal.",
        kind="select",
        default="openai",
        options=["openai", "gemini"],
    ),
    UserSettingField(
        key="llm.openai_key",
        env="OPENAI_API_KEY",
        group="llm",
        label="OpenAI API Key",
        description="Clave de OpenAI.",
        kind="secret",
        default="",
    ),
    UserSettingField(
        key="llm.gemini_key",
        env="GEMINI_API_KEY",
        group="llm",
        label="Gemini API Key",
        description="Clave de Gemini.",
        kind="secret",
        default="",
    ),
]

FIELDS_BY_KEY = {field.key: field for field in FIELDS}
FIELDS_BY_ENV = {field.env: field for field in FIELDS}
ADVANCED_GROUP_ID = "advanced"
ADVANCED_FIELDS = [field for field in FIELDS if field.group == ADVANCED_GROUP_ID]
ADVANCED_FIELD_ENVS = {field.env for field in ADVANCED_FIELDS}

SOURCE_CREDENTIAL_REQUIREMENTS: dict[str, list[str]] = {
    "REPUTATION_SOURCE_NEWSAPI": ["NEWSAPI_API_KEY"],
    "REPUTATION_SOURCE_GUARDIAN": ["GUARDIAN_API_KEY"],
    "REPUTATION_SOURCE_REDDIT": ["REDDIT_CLIENT_ID"],
    "REPUTATION_SOURCE_TWITTER": ["TWITTER_BEARER_TOKEN"],
    "REPUTATION_SOURCE_GOOGLE_REVIEWS": ["GOOGLE_PLACES_API_KEY"],
    "REPUTATION_SOURCE_YOUTUBE": ["YOUTUBE_API_KEY"],
}

ADVANCED_ENV_CANDIDATES = {
    "APPSTORE_API_ENABLED",
    "APPSTORE_COUNTRY",
    "APPSTORE_MAX_REVIEWS",
    "APPSTORE_RATING_TIMEOUT",
    "APPSTORE_SCRAPE_TIMEOUT",
    "BLOGS_MAX_ITEMS",
    "BLOGS_RSS_ONLY",
    "BLOGS_RSS_QUERY_ENABLED",
    "DOWNDETECTOR_MAX_ITEMS",
    "DOWNDETECTOR_RSS_QUERY_ENABLED",
    "DOWNDETECTOR_SCRAPING",
    "FORUMS_MAX_THREADS",
    "FORUMS_RSS_QUERY_ENABLED",
    "FORUMS_SCRAPING",
    "GDELT_END_DATETIME",
    "GDELT_MAX_ERRORS",
    "GDELT_MAX_ITEMS",
    "GDELT_MAX_QUERIES",
    "GDELT_MAX_RECORDS",
    "GDELT_QUERY_SUFFIX",
    "GDELT_SORT",
    "GDELT_START_DATETIME",
    "GDELT_TIMESPAN",
    "GOOGLE_MAX_REVIEWS",
    "GOOGLE_PLACES_API_KEY",
    "GOOGLE_PLAY_API_ENABLED",
    "GOOGLE_PLAY_API_ENDPOINT",
    "GOOGLE_PLAY_API_KEY",
    "GOOGLE_PLAY_API_KEY_PARAM",
    "GOOGLE_PLAY_DEFAULT_COUNTRY",
    "GOOGLE_PLAY_DEFAULT_LANGUAGE",
    "GOOGLE_PLAY_MAX_REVIEWS",
    "GOOGLE_PLAY_PACKAGE_IDS",
    "GOOGLE_PLAY_RATING_TIMEOUT",
    "GOOGLE_PLAY_SCRAPE_TIMEOUT",
    "GUARDIAN_API_KEY",
    "GUARDIAN_FROM_DATE",
    "GUARDIAN_MAX_ITEMS",
    "GUARDIAN_ORDER_BY",
    "GUARDIAN_PAGE_SIZE",
    "GUARDIAN_SECTION",
    "GUARDIAN_SHOW_FIELDS",
    "GUARDIAN_TAG",
    "GUARDIAN_TO_DATE",
    "LLM_API_KEY_ENV",
    "LLM_API_KEY_HEADER",
    "LLM_API_KEY_PARAM",
    "LLM_API_KEY_PREFIX",
    "LLM_API_KEY_REQUIRED",
    "LLM_BASE_URL",
    "LLM_ENDPOINT",
    "LLM_PROVIDER",
    "LLM_REQUEST_FORMAT",
    "LLM_TIMEOUT_SEC",
    "NEWSAPI_API_KEY",
    "NEWSAPI_DOMAINS",
    "NEWSAPI_ENDPOINT",
    "NEWSAPI_MAX_ARTICLES",
    "NEWSAPI_SEARCH_IN",
    "NEWSAPI_SORT_BY",
    "NEWSAPI_SOURCES",
    "NEWS_API_ENDPOINT",
    "NEWS_API_KEY",
    "NEWS_LANG",
    "NEWS_MAX_ARTICLES",
    "NEWS_RSS_ONLY",
    "NEWS_RSS_QUERY_ENABLED",
    "NEWS_SITE_QUERY_ENABLED",
    "NEWS_SITE_QUERY_GEO_MODE",
    "NEWS_SITE_QUERY_INCLUDE_UNQUOTED",
    "NEWS_SITE_QUERY_MAX_PER_GEO",
    "NEWS_SITE_QUERY_MAX_TOTAL",
    "NEWS_SITE_QUERY_MODE",
    "NEWS_SITE_QUERY_PER_SITE",
    "NEWS_SOURCES",
    "REDDIT_CLIENT_ID",
    "REDDIT_LIMIT_PER_QUERY",
    "REDDIT_USER_AGENT",
    "REPUTATION_BALANCE_ENABLED",
    "REPUTATION_BALANCE_MAX_ACTORES",
    "REPUTATION_BALANCE_MAX_GEOS",
    "REPUTATION_BALANCE_MAX_ITEMS_PER_PASS",
    "REPUTATION_BALANCE_MAX_PASSES",
    "REPUTATION_BALANCE_MAX_QUERIES_PER_PASS",
    "REPUTATION_BALANCE_MIN_PER_ACTOR",
    "REPUTATION_BALANCE_MIN_PER_GEO",
    "REPUTATION_BALANCE_RSS_QUERY_GEO_MODE",
    "REPUTATION_BALANCE_RSS_QUERY_MAX_PER_ENTITY",
    "REPUTATION_BALANCE_RSS_QUERY_MAX_PER_GEO",
    "REPUTATION_BALANCE_RSS_QUERY_MAX_TOTAL",
    "REPUTATION_BALANCE_RSS_QUERY_ORDER",
    "REPUTATION_BALANCE_SEGMENT_QUERY_MODE",
    "REPUTATION_BALANCE_SEGMENT_TERMS",
    "REPUTATION_BALANCE_SOURCES",
    "REPUTATION_COLLECTOR_WORKERS",
    "REPUTATION_DEFAULT_MAX_ITEMS",
    "REPUTATION_HTTP_BLOCK_TTL_SEC",
    "REPUTATION_HTTP_CACHE_MAX_ENTRIES",
    "REPUTATION_HTTP_CACHE_TTL_SEC",
    "REPUTATION_HTTP_RETRIES",
    "REPUTATION_HTTP_RETRY_BACKOFF_SEC",
    "REPUTATION_SEGMENT_QUERY_MODE",
    "REPUTATION_SSL_VERIFY",
    "TRUSTPILOT_MAX_ITEMS",
    "TRUSTPILOT_RSS_QUERY_ENABLED",
    "TRUSTPILOT_SCRAPING",
    "TWITTER_BEARER_TOKEN",
    "TWITTER_MAX_RESULTS",
    "YOUTUBE_API_KEY",
    "YOUTUBE_MAX_RESULTS",
}


_SENSITIVE_ENV_MARKERS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PRIVATE",
    "CREDENTIAL",
    "API_KEY",
)
_SENSITIVE_ENV_EXACT_ALLOWLIST = {
    "AUTH_GOOGLE_CLIENT_ID",
}
_SECRET_MASK = "********"


def _is_cloud_run_runtime() -> bool:
    return bool(os.getenv("K_SERVICE") or os.getenv("K_REVISION") or os.getenv("CLOUD_RUN_JOB"))


def _is_sensitive_env_name(name: str) -> bool:
    normalized = name.strip().upper()
    if not normalized:
        return False
    if normalized in _SENSITIVE_ENV_EXACT_ALLOWLIST:
        return False
    return any(marker in normalized for marker in _SENSITIVE_ENV_MARKERS)


def _field_payload(field: UserSettingField, value: Any) -> dict[str, Any]:
    is_secret = field.kind == "secret"
    raw_text = str(value).strip() if value is not None else ""
    payload: dict[str, Any] = {
        "key": field.key,
        "label": field.label,
        "description": field.description,
        "type": field.kind,
        "value": (_SECRET_MASK if raw_text else "") if is_secret else value,
        "options": field.options,
        "placeholder": field.placeholder,
    }
    if is_secret:
        payload["configured"] = bool(raw_text)
    return payload


def _strip_quotes(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        values[key.strip()] = decrypt_env_secret(_strip_quotes(raw_value.strip()))
    return values


def _format_env_value(value: Any, field: UserSettingField) -> str:
    if value is None:
        return ""
    if field.kind == "boolean":
        return "true" if bool(value) else "false"
    return str(value)


def _parse_value(raw: str | None, field: UserSettingField) -> Any:
    if raw is None or raw == "":
        return field.default
    if field.kind == "boolean":
        return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
    if field.kind == "number":
        try:
            return int(raw)
        except ValueError:
            return field.default
    if field.kind == "select":
        value = raw.strip()
        if field.options and value not in field.options:
            return field.default
        return value
    return raw


def _coerce_update(value: Any, field: UserSettingField) -> Any:
    if value is None:
        return field.default if field.kind != "secret" else ""
    if field.kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)
    if field.kind == "number":
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return field.default
        return field.default
    if field.kind == "select":
        if not isinstance(value, str):
            return field.default
        value = value.strip()
        if field.options and value not in field.options:
            return field.default
        return value
    if not isinstance(value, str):
        return str(value)
    return value.strip()


def _env_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_language_preference(env_values: dict[str, str], default: str) -> str:
    preferred = env_values.get("NEWS_LANG")
    if preferred and preferred.strip():
        return preferred.strip()
    fallback = env_values.get("NEWSAPI_LANGUAGE")
    if fallback and fallback.strip():
        return fallback.strip()
    return default


def _llm_provider(env_values: dict[str, str]) -> str:
    raw_provider = (env_values.get("LLM_PROVIDER") or "openai").strip().lower()
    return "gemini" if raw_provider == "gemini" else "openai"


def _active_llm_api_key_env(env_values: dict[str, str]) -> str:
    return "GEMINI_API_KEY" if _llm_provider(env_values) == "gemini" else "OPENAI_API_KEY"


def _render_main_env_file(values: dict[str, str]) -> str:
    lines: list[str] = []
    lines.append("# === Configuracion reputacional (cliente final) ===")
    lines.append("# Si falta .env.reputation, se copiará este archivo.")
    lines.append("")

    for group in GROUPS:
        group_id = group["id"]
        if group_id == ADVANCED_GROUP_ID:
            continue
        lines.append(f"# === {group['label'].upper()} ===")
        description = group.get("description")
        if description:
            lines.append(f"# {description}")
        for field in [f for f in FIELDS if f.group == group_id]:
            if field.label and field.description:
                lines.append(f"# {field.label}. {field.description}")
            elif field.label:
                lines.append(f"# {field.label}")
            elif field.description:
                lines.append(f"# {field.description}")
            value = values.get(field.env)
            if value is None:
                value = _format_env_value(field.default, field)
            elif field.kind == "secret":
                value = encrypt_env_secret(value)
            lines.append(f"{field.env}={value}")
            if field.key == "language.preference":
                lines.append(f"NEWSAPI_LANGUAGE={value}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_advanced_env_file(values: dict[str, str], extras: dict[str, str]) -> str:
    lines: list[str] = []
    lines.append("# === AVANZADO ===")
    lines.append("# Variables técnicas (solo si sabes lo que haces).")
    for field in ADVANCED_FIELDS:
        if field.label and field.description:
            lines.append(f"# {field.label}. {field.description}")
        elif field.label:
            lines.append(f"# {field.label}")
        elif field.description:
            lines.append(f"# {field.description}")
        value = values.get(field.env)
        if value is None:
            value = _format_env_value(field.default, field)
        elif field.kind == "secret":
            value = encrypt_env_secret(value)
        lines.append(f"{field.env}={value}")
    if extras:
        lines.append("# Variables adicionales (solo si sabes lo que haces)")
        for key in sorted(extras.keys()):
            if key in CLOUDRUN_ONLY_ENV_KEYS:
                continue
            if key in FIELDS_BY_ENV and key not in ADVANCED_FIELD_ENVS:
                continue
            raw_value = extras[key]
            if _is_sensitive_env_name(key):
                raw_value = encrypt_env_secret(raw_value)
            lines.append(f"{key}={raw_value}")
    return "\n".join(lines).rstrip() + "\n"


def _render_env_example() -> str:
    values: dict[str, str] = {}
    for field in FIELDS:
        if field.group == ADVANCED_GROUP_ID:
            continue
        if field.kind == "secret":
            values[field.env] = ""
        else:
            values[field.env] = _format_env_value(field.default, field)
    return _render_main_env_file(values)


def _render_advanced_env_example() -> str:
    values: dict[str, str] = {}
    for field in ADVANCED_FIELDS:
        if field.kind == "secret":
            values[field.env] = ""
        else:
            values[field.env] = _format_env_value(field.default, field)
    return _render_advanced_env_file(values, {})


def _ensure_example_file() -> None:
    if not REPUTATION_ENV_EXAMPLE.exists():
        REPUTATION_ENV_EXAMPLE.write_text(_render_env_example(), encoding="utf-8")
    else:
        existing = _parse_env_file(REPUTATION_ENV_EXAMPLE)
        values: dict[str, str] = {}
        for field in FIELDS:
            if field.group == ADVANCED_GROUP_ID:
                continue
            if field.env in existing:
                values[field.env] = existing[field.env]
            elif field.kind == "secret":
                values[field.env] = ""
            else:
                values[field.env] = _format_env_value(field.default, field)
        content = _render_main_env_file(values)
        if REPUTATION_ENV_EXAMPLE.read_text(encoding="utf-8") != content:
            REPUTATION_ENV_EXAMPLE.write_text(content, encoding="utf-8")

    if not REPUTATION_ADVANCED_ENV_EXAMPLE.exists():
        REPUTATION_ADVANCED_ENV_EXAMPLE.write_text(_render_advanced_env_example(), encoding="utf-8")


def _advanced_option_defaults(options: list[str]) -> dict[str, str]:
    example_values = _parse_env_file(REPUTATION_ADVANCED_ENV_EXAMPLE)
    return {option: example_values.get(option, "") for option in options}


def get_user_settings_snapshot() -> dict[str, Any]:
    sync_reputation_env_files_from_state()
    _ensure_example_file()
    cloud_run_runtime = _is_cloud_run_runtime()
    main_env_values = _parse_env_file(REPUTATION_ENV_PATH)
    advanced_env_exists = REPUTATION_ADVANCED_ENV_PATH.exists()
    advanced_env_values = _parse_env_file(REPUTATION_ADVANCED_ENV_PATH)
    advanced_example_values = _parse_env_file(REPUTATION_ADVANCED_ENV_EXAMPLE)
    advanced_extras = {
        k: v
        for k, v in advanced_env_values.items()
        if (k not in FIELDS_BY_ENV and k != "NEWSAPI_LANGUAGE" and k not in CLOUDRUN_ONLY_ENV_KEYS)
    }
    values_by_key: dict[str, Any] = {}
    for field in FIELDS:
        raw = (
            advanced_env_values.get(field.env)
            if field.group == ADVANCED_GROUP_ID
            else main_env_values.get(field.env)
        )
        values_by_key[field.key] = _parse_value(raw, field)
    language_field = FIELDS_BY_KEY.get("language.preference")
    if language_field:
        values_by_key[language_field.key] = _resolve_language_preference(
            main_env_values, language_field.default
        )
    llm_enabled_field = FIELDS_BY_KEY.get("llm.enabled")
    if llm_enabled_field:
        llm_key_env = _active_llm_api_key_env(main_env_values)
        if not main_env_values.get(llm_key_env, "").strip():
            values_by_key[llm_enabled_field.key] = False

    groups_payload: list[dict[str, Any]] = []
    for group in GROUPS:
        if cloud_run_runtime and group["id"] == "advanced":
            continue
        group_fields = []
        if group["id"] == "advanced":
            for field in [f for f in FIELDS if f.group == group["id"]]:
                group_fields.append(
                    _field_payload(field, values_by_key.get(field.key, field.default))
                )
            for env_key in sorted(advanced_extras.keys()):
                raw_value = advanced_extras.get(env_key, "")
                is_secret_extra = _is_sensitive_env_name(env_key)
                payload: dict[str, Any] = {
                    "key": f"advanced.{env_key}",
                    "label": env_key,
                    "description": "Variable avanzada",
                    "type": "secret" if is_secret_extra else "string",
                    "value": (_SECRET_MASK if str(raw_value).strip() else "")
                    if is_secret_extra
                    else raw_value,
                    "options": None,
                    "placeholder": "",
                }
                if is_secret_extra:
                    payload["configured"] = bool(str(raw_value).strip())
                group_fields.append(payload)
        else:
            for field in [f for f in FIELDS if f.group == group["id"]]:
                group_fields.append(
                    _field_payload(field, values_by_key.get(field.key, field.default))
                )
        groups_payload.append(
            {
                "id": group["id"],
                "label": group["label"],
                "description": group.get("description"),
                "fields": group_fields,
            }
        )

    updated_at = None
    updated_candidates: list[datetime] = []
    for path in (REPUTATION_ENV_PATH, REPUTATION_ADVANCED_ENV_PATH):
        if path.exists():
            updated_candidates.append(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc))
    if updated_candidates:
        updated_at = max(updated_candidates).isoformat()

    advanced_options = (
        []
        if cloud_run_runtime
        else sorted(
            {
                key
                for key in ADVANCED_ENV_CANDIDATES
                if key not in FIELDS_BY_ENV and key not in CLOUDRUN_ONLY_ENV_KEYS
            }
            | {key for key in advanced_extras if key not in CLOUDRUN_ONLY_ENV_KEYS}
            | {
                key
                for key in advanced_example_values
                if key not in FIELDS_BY_ENV and key not in CLOUDRUN_ONLY_ENV_KEYS
            }
        )
    )

    advanced_option_defaults = (
        {} if cloud_run_runtime else _advanced_option_defaults(advanced_options)
    )

    return {
        "groups": groups_payload,
        "updated_at": updated_at,
        "advanced_options": advanced_options,
        "advanced_option_defaults": advanced_option_defaults,
        "advanced_env_exists": advanced_env_exists and not cloud_run_runtime,
    }


def update_user_settings(values: dict[str, Any]) -> dict[str, Any]:
    sync_reputation_env_files_from_state()
    _ensure_example_file()
    cloud_run_runtime = _is_cloud_run_runtime()
    main_env_values = _parse_env_file(REPUTATION_ENV_PATH)
    advanced_env_values = _parse_env_file(REPUTATION_ADVANCED_ENV_PATH)
    advanced_example_values = _parse_env_file(REPUTATION_ADVANCED_ENV_EXAMPLE)
    allowed_advanced_dynamic_keys = (
        set(ADVANCED_ENV_CANDIDATES)
        | {
            key
            for key in advanced_env_values
            if key not in FIELDS_BY_ENV and key not in CLOUDRUN_ONLY_ENV_KEYS
        }
        | {
            key
            for key in advanced_example_values
            if key not in FIELDS_BY_ENV and key not in CLOUDRUN_ONLY_ENV_KEYS
        }
    )
    base_advanced_env_values = advanced_env_values.copy()
    advanced_touched = False

    if not cloud_run_runtime and not REPUTATION_ADVANCED_ENV_PATH.exists():
        wants_advanced_change = False
        for key in values:
            field = FIELDS_BY_KEY.get(key)
            if (field and field.group == ADVANCED_GROUP_ID) or key.startswith("advanced."):
                wants_advanced_change = True
                break
        if wants_advanced_change:
            REPUTATION_ADVANCED_ENV_PATH.write_text(
                REPUTATION_ADVANCED_ENV_EXAMPLE.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            advanced_env_values = _parse_env_file(REPUTATION_ADVANCED_ENV_PATH)
            base_advanced_env_values = advanced_env_values.copy()
            advanced_touched = True

    for key, value in values.items():
        field = FIELDS_BY_KEY.get(key)
        if not field:
            if key.startswith("advanced."):
                if cloud_run_runtime:
                    raise ValueError("La configuración avanzada está deshabilitada en Cloud Run.")
                env_key = key.split(".", 1)[1].strip()
                if not env_key:
                    continue
                if env_key in CLOUDRUN_ONLY_ENV_KEYS:
                    raise ValueError(
                        f"{env_key} se gestiona solo desde backend/reputation/cloudrun.env."
                    )
                if env_key in FIELDS_BY_ENV and env_key not in ADVANCED_FIELD_ENVS:
                    raise ValueError(
                        f"{env_key} no es una variable avanzada y se gestiona desde .env.reputation."
                    )
                if (
                    env_key not in ADVANCED_FIELD_ENVS
                    and env_key not in allowed_advanced_dynamic_keys
                ):
                    raise ValueError(f"{env_key} no está permitido en configuración avanzada.")
                if _is_sensitive_env_name(env_key) and str(value).strip() == _SECRET_MASK:
                    # Keep current secret value when client sends masked marker.
                    continue
                if value is None or (isinstance(value, str) and not value.strip()):
                    advanced_env_values.pop(env_key, None)
                else:
                    advanced_env_values[env_key] = str(value).strip()
                advanced_touched = True
            continue
        if cloud_run_runtime and field.group == "advanced":
            raise ValueError("La configuración avanzada está deshabilitada en Cloud Run.")
        if field.env in CLOUDRUN_ONLY_ENV_KEYS:
            raise ValueError(f"{field.env} se gestiona solo desde backend/reputation/cloudrun.env.")
        if field.kind == "secret" and isinstance(value, str) and value.strip() == _SECRET_MASK:
            # Keep current secret value when client sends masked marker.
            continue
        coerced = _coerce_update(value, field)
        if field.group == ADVANCED_GROUP_ID:
            advanced_env_values[field.env] = _format_env_value(coerced, field)
            advanced_touched = True
        else:
            main_env_values[field.env] = _format_env_value(coerced, field)
        if field.key == "language.preference":
            main_env_values["NEWSAPI_LANGUAGE"] = main_env_values[field.env]

    llm_key_env = _active_llm_api_key_env(main_env_values)
    if not main_env_values.get(llm_key_env, "").strip():
        main_env_values["LLM_ENABLED"] = "false"

    log_enabled = _env_truthy(advanced_env_values.get("REPUTATION_LOG_ENABLED"))
    if not log_enabled:
        for field in ADVANCED_FIELDS:
            if field.key == "advanced.log_enabled":
                continue
            if field.env in base_advanced_env_values:
                advanced_env_values[field.env] = base_advanced_env_values[field.env]
            else:
                advanced_env_values.pop(field.env, None)
        for env_key in list(advanced_env_values.keys()):
            if env_key in FIELDS_BY_ENV or env_key == "NEWSAPI_LANGUAGE":
                continue
            if env_key in base_advanced_env_values:
                advanced_env_values[env_key] = base_advanced_env_values[env_key]
            else:
                advanced_env_values.pop(env_key, None)

    advanced_extras = {
        k: v
        for k, v in advanced_env_values.items()
        if (k not in FIELDS_BY_ENV and k != "NEWSAPI_LANGUAGE" and k not in CLOUDRUN_ONLY_ENV_KEYS)
    }

    merged_field_values: dict[str, str] = {}
    for field in FIELDS:
        source_values = advanced_env_values if field.group == ADVANCED_GROUP_ID else main_env_values
        if field.env in source_values:
            merged_field_values[field.env] = source_values[field.env]

    missing_sources: list[str] = []
    for source_env, required_envs in SOURCE_CREDENTIAL_REQUIREMENTS.items():
        if not _env_truthy(merged_field_values.get(source_env)):
            continue
        missing = [env for env in required_envs if not merged_field_values.get(env)]
        if missing:
            source_label = FIELDS_BY_ENV.get(source_env)
            missing_sources.append(source_label.label if source_label else source_env)

    if missing_sources:
        raise ValueError("Faltan credenciales para: " + ", ".join(sorted(set(missing_sources))))

    REPUTATION_ENV_PATH.write_text(_render_main_env_file(main_env_values), encoding="utf-8")
    if REPUTATION_ADVANCED_ENV_PATH.exists() or advanced_touched:
        REPUTATION_ADVANCED_ENV_PATH.write_text(
            _render_advanced_env_file(advanced_env_values, advanced_extras),
            encoding="utf-8",
        )
    persist_reputation_env_files_to_state()

    reload_reputation_settings()
    _ensure_example_file()

    return get_user_settings_snapshot()


def reset_user_settings_to_example() -> dict[str, Any]:
    sync_reputation_env_files_from_state()
    _ensure_example_file()
    if not REPUTATION_ENV_EXAMPLE.exists():
        raise FileNotFoundError("Reputation example env file not found")
    content = REPUTATION_ENV_EXAMPLE.read_text(encoding="utf-8")
    REPUTATION_ENV_PATH.write_text(content, encoding="utf-8")
    if REPUTATION_ADVANCED_ENV_PATH.exists():
        advanced_content = REPUTATION_ADVANCED_ENV_EXAMPLE.read_text(encoding="utf-8")
        REPUTATION_ADVANCED_ENV_PATH.write_text(advanced_content, encoding="utf-8")
    persist_reputation_env_files_to_state()
    reload_reputation_settings()
    return get_user_settings_snapshot()


def enable_advanced_settings() -> dict[str, Any]:
    sync_reputation_env_files_from_state()
    _ensure_example_file()
    if _is_cloud_run_runtime():
        raise ValueError("La configuración avanzada está deshabilitada en Cloud Run.")
    if not REPUTATION_ADVANCED_ENV_PATH.exists():
        REPUTATION_ADVANCED_ENV_PATH.write_text(
            REPUTATION_ADVANCED_ENV_EXAMPLE.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        persist_reputation_env_files_to_state()
    reload_reputation_settings()
    return get_user_settings_snapshot()
