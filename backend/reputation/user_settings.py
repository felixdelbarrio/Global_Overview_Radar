from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from reputation.config import (
    REPUTATION_ENV_EXAMPLE,
    REPUTATION_ENV_PATH,
    reload_reputation_settings,
)

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
        "id": "sources_public",
        "label": "Fuentes sin credenciales",
        "description": "Activa o desactiva fuentes que no requieren API Key.",
    },
    {
        "id": "sources_credentials",
        "label": "Fuentes con credenciales",
        "description": "Activa fuentes que requieren API Key.",
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
        key="sources.news",
        env="REPUTATION_SOURCE_NEWS",
        group="sources_public",
        label="Noticias (RSS)",
        description="Agregadores y RSS.",
        kind="boolean",
        default=True,
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
        group="sources_public",
        label="GDELT",
        description="Global Database of Events.",
        kind="boolean",
        default=True,
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
        group="sources_public",
        label="Foros",
        description="Foros y comunidades.",
        kind="boolean",
        default=True,
    ),
    UserSettingField(
        key="sources.blogs",
        env="REPUTATION_SOURCE_BLOGS_RSS",
        group="sources_public",
        label="Blogs",
        description="Blogs RSS.",
        kind="boolean",
        default=True,
    ),
    UserSettingField(
        key="sources.appstore",
        env="REPUTATION_SOURCE_APPSTORE",
        group="sources_public",
        label="App Store",
        description="Opiniones en App Store.",
        kind="boolean",
        default=True,
    ),
    UserSettingField(
        key="sources.trustpilot",
        env="REPUTATION_SOURCE_TRUSTPILOT",
        group="sources_public",
        label="Trustpilot",
        description="Reseñas Trustpilot.",
        kind="boolean",
        default=True,
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
        group="sources_public",
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
        group="sources_public",
        label="Downdetector",
        description="Incidencias y caídas.",
        kind="boolean",
        default=True,
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
        label="Reddit Client ID",
        description="Credencial de Reddit.",
        kind="secret",
        default="",
    ),
    UserSettingField(
        key="keys.reddit_secret",
        env="REDDIT_CLIENT_SECRET",
        group="sources_credentials",
        label="Reddit Client Secret",
        description="Secreto de Reddit.",
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

SOURCE_CREDENTIAL_REQUIREMENTS: dict[str, list[str]] = {
    "REPUTATION_SOURCE_NEWSAPI": ["NEWSAPI_API_KEY"],
    "REPUTATION_SOURCE_GUARDIAN": ["GUARDIAN_API_KEY"],
    "REPUTATION_SOURCE_REDDIT": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"],
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
    "REDDIT_CLIENT_SECRET",
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
        values[key.strip()] = _strip_quotes(raw_value.strip())
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


def _render_env_file(values: dict[str, str], extras: dict[str, str]) -> str:
    lines: list[str] = []
    lines.append("# === Configuracion reputacional (cliente final) ===")
    lines.append("# Si falta .env.reputation, se copiará este archivo.")
    lines.append("")

    for group in GROUPS:
        group_id = group["id"]
        lines.append(f"# === {group['label'].upper()} ===")
        description = group.get("description")
        if description:
            lines.append(f"# {description}")

        if group_id == "advanced":
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
                lines.append(f"{field.env}={value}")
            if extras:
                lines.append("# Variables adicionales (solo si sabes lo que haces)")
                for key in sorted(extras.keys()):
                    lines.append(f"{key}={extras[key]}")
            lines.append("")
            continue

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
            lines.append(f"{field.env}={value}")
            if field.key == "language.preference":
                lines.append(f"NEWSAPI_LANGUAGE={value}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_env_example() -> str:
    values: dict[str, str] = {}
    for field in FIELDS:
        if field.kind == "secret":
            values[field.env] = ""
        else:
            values[field.env] = _format_env_value(field.default, field)
    return _render_env_file(values, {})


def _ensure_example_file() -> None:
    if not REPUTATION_ENV_EXAMPLE.exists():
        REPUTATION_ENV_EXAMPLE.write_text(_render_env_example(), encoding="utf-8")
        return

    existing = _parse_env_file(REPUTATION_ENV_EXAMPLE)
    extras = {k: v for k, v in existing.items() if k not in FIELDS_BY_ENV}
    values: dict[str, str] = {}
    for field in FIELDS:
        if field.env in existing:
            values[field.env] = existing[field.env]
        elif field.kind == "secret":
            values[field.env] = ""
        else:
            values[field.env] = _format_env_value(field.default, field)
    content = _render_env_file(values, extras)
    if REPUTATION_ENV_EXAMPLE.read_text(encoding="utf-8") != content:
        REPUTATION_ENV_EXAMPLE.write_text(content, encoding="utf-8")


def _apply_env_to_os(values: dict[str, str]) -> None:
    for field in FIELDS:
        value = values.get(field.env)
        if value is None or value == "":
            os.environ.pop(field.env, None)
        else:
            os.environ[field.env] = value
        if field.key == "language.preference":
            if value is None or value == "":
                os.environ.pop("NEWSAPI_LANGUAGE", None)
            else:
                os.environ["NEWSAPI_LANGUAGE"] = value


def get_user_settings_snapshot() -> dict[str, Any]:
    _ensure_example_file()
    env_values = _parse_env_file(REPUTATION_ENV_PATH)
    extras = {
        k: v for k, v in env_values.items() if k not in FIELDS_BY_ENV and k != "NEWSAPI_LANGUAGE"
    }
    values_by_key: dict[str, Any] = {}
    for field in FIELDS:
        raw = env_values.get(field.env)
        values_by_key[field.key] = _parse_value(raw, field)
    language_field = FIELDS_BY_KEY.get("language.preference")
    if language_field:
        values_by_key[language_field.key] = _resolve_language_preference(
            env_values, language_field.default
        )

    groups_payload: list[dict[str, Any]] = []
    for group in GROUPS:
        group_fields = []
        if group["id"] == "advanced":
            for field in [f for f in FIELDS if f.group == group["id"]]:
                group_fields.append(
                    {
                        "key": field.key,
                        "label": field.label,
                        "description": field.description,
                        "type": field.kind,
                        "value": values_by_key.get(field.key, field.default),
                        "options": field.options,
                        "placeholder": field.placeholder,
                    }
                )
            for env_key in sorted(extras.keys()):
                group_fields.append(
                    {
                        "key": f"advanced.{env_key}",
                        "label": env_key,
                        "description": "Variable avanzada",
                        "type": "string",
                        "value": extras.get(env_key, ""),
                        "options": None,
                        "placeholder": "",
                    }
                )
        else:
            for field in [f for f in FIELDS if f.group == group["id"]]:
                group_fields.append(
                    {
                        "key": field.key,
                        "label": field.label,
                        "description": field.description,
                        "type": field.kind,
                        "value": values_by_key.get(field.key, field.default),
                        "options": field.options,
                        "placeholder": field.placeholder,
                    }
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
    if REPUTATION_ENV_PATH.exists():
        updated_at = datetime.fromtimestamp(
            REPUTATION_ENV_PATH.stat().st_mtime, tz=timezone.utc
        ).isoformat()

    advanced_options = sorted(
        {key for key in ADVANCED_ENV_CANDIDATES if key not in FIELDS_BY_ENV} | set(extras.keys())
    )

    return {
        "groups": groups_payload,
        "updated_at": updated_at,
        "advanced_options": advanced_options,
    }


def update_user_settings(values: dict[str, Any]) -> dict[str, Any]:
    _ensure_example_file()
    env_values = _parse_env_file(REPUTATION_ENV_PATH)
    base_env_values = env_values.copy()

    for key, value in values.items():
        field = FIELDS_BY_KEY.get(key)
        if not field:
            if key.startswith("advanced."):
                env_key = key.split(".", 1)[1].strip()
                if not env_key:
                    continue
                if value is None or (isinstance(value, str) and not value.strip()):
                    env_values.pop(env_key, None)
                else:
                    env_values[env_key] = str(value).strip()
            continue
        coerced = _coerce_update(value, field)
        env_values[field.env] = _format_env_value(coerced, field)
        if field.key == "language.preference":
            env_values["NEWSAPI_LANGUAGE"] = env_values[field.env]

    log_enabled = _env_truthy(env_values.get("REPUTATION_LOG_ENABLED"))
    if not log_enabled:
        for field in FIELDS:
            if field.group != "advanced" or field.key == "advanced.log_enabled":
                continue
            if field.env in base_env_values:
                env_values[field.env] = base_env_values[field.env]
            else:
                env_values.pop(field.env, None)
        for key in list(env_values.keys()):
            if key in FIELDS_BY_ENV or key == "NEWSAPI_LANGUAGE":
                continue
            if key in base_env_values:
                env_values[key] = base_env_values[key]
            else:
                env_values.pop(key, None)

    extras = {
        k: v for k, v in env_values.items() if k not in FIELDS_BY_ENV and k != "NEWSAPI_LANGUAGE"
    }

    missing_sources: list[str] = []
    for source_env, required_envs in SOURCE_CREDENTIAL_REQUIREMENTS.items():
        if not _env_truthy(env_values.get(source_env)):
            continue
        missing = [env for env in required_envs if not env_values.get(env)]
        if missing:
            source_label = FIELDS_BY_ENV.get(source_env)
            missing_sources.append(source_label.label if source_label else source_env)

    if missing_sources:
        raise ValueError("Faltan credenciales para: " + ", ".join(sorted(set(missing_sources))))
    rendered = _render_env_file(env_values, extras)
    REPUTATION_ENV_PATH.write_text(rendered, encoding="utf-8")

    _apply_env_to_os(env_values)
    reload_reputation_settings()
    _ensure_example_file()

    return get_user_settings_snapshot()


def reset_user_settings_to_example() -> dict[str, Any]:
    _ensure_example_file()
    if not REPUTATION_ENV_EXAMPLE.exists():
        raise FileNotFoundError("Reputation example env file not found")
    content = REPUTATION_ENV_EXAMPLE.read_text(encoding="utf-8")
    REPUTATION_ENV_PATH.write_text(content, encoding="utf-8")
    env_values = _parse_env_file(REPUTATION_ENV_PATH)
    _apply_env_to_os(env_values)
    reload_reputation_settings()
    return get_user_settings_snapshot()
