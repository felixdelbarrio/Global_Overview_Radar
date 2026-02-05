from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from bugresolutionradar.config import BUG_ENV_EXAMPLE, BUG_ENV_PATH, reload_bugresolutionradar_settings

SettingKind = Literal["boolean", "string", "secret", "number", "select"]


@dataclass(frozen=True)
class UserSettingField:
    key: str
    group: str
    label: str
    description: str
    kind: SettingKind
    default: Any
    env: str | None = None
    placeholder: str | None = None


GROUPS: list[dict[str, str]] = [
    {
        "id": "bugs_ui",
        "label": "Incidencias · Visibilidad",
        "description": "Controla si el módulo de incidencias aparece en el frontend.",
    },
    {
        "id": "bugs_sources_public",
        "label": "Incidencias · Fuentes sin credenciales",
        "description": "Activa o desactiva conectores que leen ficheros locales (CSV/JSON/XLSX).",
    },
    {
        "id": "bugs_sources_credentials",
        "label": "Incidencias · Fuentes con credenciales",
        "description": "Conectores que requieren credenciales (ej. JIRA).",
    },
]


FIELDS: list[UserSettingField] = [
    UserSettingField(
        key="ui.incidents_enabled",
        env="INCIDENTS_UI_ENABLED",
        group="bugs_ui",
        label="Mostrar incidencias",
        description="Muestra u oculta navegación, dashboard y centro de ingesta de incidencias.",
        kind="boolean",
        default=True,
    ),
    UserSettingField(
        key="sources.filesystem_json",
        group="bugs_sources_public",
        label="Filesystem (JSON)",
        description="Lee ficheros *.json en ASSETS_DIR.",
        kind="boolean",
        default=True,
    ),
    UserSettingField(
        key="sources.filesystem_csv",
        group="bugs_sources_public",
        label="Filesystem (CSV)",
        description="Lee ficheros *.csv en ASSETS_DIR.",
        kind="boolean",
        default=True,
    ),
    UserSettingField(
        key="sources.filesystem_xlsx",
        group="bugs_sources_public",
        label="Filesystem (XLSX)",
        description="Lee ficheros *.xlsx en ASSETS_DIR.",
        kind="boolean",
        default=True,
    ),
    UserSettingField(
        key="sources.jira",
        group="bugs_sources_credentials",
        label="JIRA",
        description="Importa incidencias desde una vista (JQL / filtro guardado) vía API.",
        kind="boolean",
        default=False,
    ),
    UserSettingField(
        key="jira.base_url",
        env="JIRA_BASE_URL",
        group="bugs_sources_credentials",
        label="JIRA Base URL",
        description="Ej. https://tu-org.atlassian.net",
        kind="string",
        default="",
        placeholder="https://…",
    ),
    UserSettingField(
        key="jira.user_email",
        env="JIRA_USER_EMAIL",
        group="bugs_sources_credentials",
        label="JIRA Usuario (email)",
        description="Email del usuario (Jira Cloud).",
        kind="string",
        default="",
        placeholder="user@empresa.com",
    ),
    UserSettingField(
        key="jira.api_token",
        env="JIRA_API_TOKEN",
        group="bugs_sources_credentials",
        label="JIRA API Token",
        description="Token API (se guarda en .env).",
        kind="secret",
        default="",
        placeholder="••••••",
    ),
    UserSettingField(
        key="jira.jql",
        env="JIRA_JQL",
        group="bugs_sources_credentials",
        label="JIRA JQL",
        description="Consulta JQL para definir la vista de Bugs.",
        kind="string",
        default="",
        placeholder="project = MEXBMI1 AND issuetype = Bug ORDER BY created DESC",
    ),
    UserSettingField(
        key="jira.filter_id",
        env="JIRA_FILTER_ID",
        group="bugs_sources_credentials",
        label="JIRA Filter ID (opcional)",
        description="ID de filtro guardado (si no usas JQL directo).",
        kind="string",
        default="",
        placeholder="12345",
    ),
]

FIELDS_BY_KEY = {field.key: field for field in FIELDS}


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
    if not isinstance(value, str):
        return str(value)
    return value.strip()


def _split_sources(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _render_env_file(env_values: dict[str, str], extras: dict[str, str]) -> str:
    def pick(key: str, fallback: str = "") -> str:
        value = env_values.get(key)
        if value is None:
            return fallback
        return value

    lines: list[str] = []
    lines.append("# === BugResolutionRadar (.env) ===")
    lines.append("# Si falta este fichero, se copiará desde .env.example.")
    lines.append("")

    lines.append("# === App ===")
    lines.append("APP_NAME=" + pick("APP_NAME", "Empresas – Global Overview Radar"))
    lines.append("TZ=" + pick("TZ", "Europe/Madrid"))
    lines.append("")

    lines.append("# === Paths ===")
    lines.append("ASSETS_DIR=" + pick("ASSETS_DIR", "./data/assets"))
    lines.append("CACHE_PATH=" + pick("CACHE_PATH", "./data/cache/bugresolutionradar_cache.json"))
    lines.append(
        "INCIDENTS_OVERRIDES_PATH="
        + pick("INCIDENTS_OVERRIDES_PATH", "./data/cache/bugresolutionradar_incidents_overrides.json")
    )
    lines.append("")

    lines.append("# === Fuentes (conectores activos) ===")
    lines.append("# Lista separada por comas. Ejemplo: filesystem_xlsx,jira")
    lines.append("SOURCES=" + pick("SOURCES", "filesystem_json,filesystem_csv,filesystem_xlsx"))
    lines.append("")

    lines.append("# === UI ===")
    lines.append("# Controla si el módulo de incidencias aparece en el frontend.")
    lines.append("INCIDENTS_UI_ENABLED=" + pick("INCIDENTS_UI_ENABLED", "true"))
    lines.append("")

    lines.append("# === XLSX knobs (opcional) ===")
    lines.append("XLSX_IGNORE_FILES=" + pick("XLSX_IGNORE_FILES", ""))
    lines.append("XLSX_PREFERRED_SHEET=" + pick("XLSX_PREFERRED_SHEET", "Reportes"))
    lines.append("")

    lines.append("# === JIRA (opcional) ===")
    lines.append("JIRA_BASE_URL=" + pick("JIRA_BASE_URL", ""))
    lines.append("JIRA_USER_EMAIL=" + pick("JIRA_USER_EMAIL", ""))
    lines.append("JIRA_API_TOKEN=" + pick("JIRA_API_TOKEN", ""))
    lines.append("JIRA_JQL=" + pick("JIRA_JQL", ""))
    lines.append("JIRA_FILTER_ID=" + pick("JIRA_FILTER_ID", ""))
    lines.append("JIRA_MAX_RESULTS=" + pick("JIRA_MAX_RESULTS", "500"))
    lines.append("JIRA_PAGE_SIZE=" + pick("JIRA_PAGE_SIZE", "100"))
    lines.append("JIRA_TIMEOUT_SEC=" + pick("JIRA_TIMEOUT_SEC", "30.0"))
    lines.append("JIRA_VERIFY_SSL=" + pick("JIRA_VERIFY_SSL", "true"))
    lines.append("")

    lines.append("# === KPI / Reporting ===")
    lines.append("MASTER_THRESHOLD_CLIENTS=" + pick("MASTER_THRESHOLD_CLIENTS", "5"))
    lines.append("STALE_DAYS_THRESHOLD=" + pick("STALE_DAYS_THRESHOLD", "15"))
    lines.append("PERIOD_DAYS_DEFAULT=" + pick("PERIOD_DAYS_DEFAULT", "15"))
    lines.append("")

    lines.append("# === Logging ===")
    lines.append("LOG_ENABLED=" + pick("LOG_ENABLED", "false"))
    lines.append("LOG_TO_FILE=" + pick("LOG_TO_FILE", "false"))
    lines.append("LOG_FILE_NAME=" + pick("LOG_FILE_NAME", "bugresolutionradar.log"))
    lines.append("LOG_DEBUG=" + pick("LOG_DEBUG", "false"))
    lines.append("")

    if extras:
        lines.append("# === Variables adicionales ===")
        for key in sorted(extras.keys()):
            lines.append(f"{key}={extras[key]}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _ensure_example_file() -> None:
    if BUG_ENV_EXAMPLE.exists():
        return
    BUG_ENV_EXAMPLE.write_text(_render_env_file({}, {}), encoding="utf-8")


def _apply_env_to_os(env_values: dict[str, str]) -> None:
    for key, value in env_values.items():
        os.environ[key] = value


def get_user_settings_snapshot() -> dict[str, Any]:
    _ensure_example_file()
    env_values = _parse_env_file(BUG_ENV_PATH)
    sources_set = set(_split_sources(env_values.get("SOURCES")))
    extras = {k: v for k, v in env_values.items() if k not in {"SOURCES"} and k not in _known_envs()}

    values_by_key: dict[str, Any] = {}
    for field in FIELDS:
        if field.key.startswith("sources."):
            token = field.key.split(".", 1)[1].strip()
            values_by_key[field.key] = token in sources_set
            continue
        if not field.env:
            values_by_key[field.key] = field.default
            continue
        values_by_key[field.key] = _parse_value(env_values.get(field.env), field)

    groups_payload: list[dict[str, Any]] = []
    for group in GROUPS:
        group_fields = []
        for field in [f for f in FIELDS if f.group == group["id"]]:
            group_fields.append(
                {
                    "key": field.key,
                    "label": field.label,
                    "description": field.description,
                    "type": field.kind,
                    "value": values_by_key.get(field.key, field.default),
                    "options": None,
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
    if BUG_ENV_PATH.exists():
        updated_at = datetime.fromtimestamp(BUG_ENV_PATH.stat().st_mtime, tz=timezone.utc).isoformat()

    return {
        "groups": groups_payload,
        "updated_at": updated_at,
        "advanced_options": sorted(extras.keys()),
    }


def update_user_settings(values: dict[str, Any]) -> dict[str, Any]:
    _ensure_example_file()
    env_values = _parse_env_file(BUG_ENV_PATH)
    sources_set = set(_split_sources(env_values.get("SOURCES")))

    for key, value in values.items():
        field = FIELDS_BY_KEY.get(key)
        if not field:
            continue
        if key.startswith("sources."):
            token = key.split(".", 1)[1].strip()
            enabled = bool(_coerce_update(value, field))
            if enabled:
                sources_set.add(token)
            else:
                sources_set.discard(token)
            continue
        if not field.env:
            continue
        coerced = _coerce_update(value, field)
        env_values[field.env] = _format_env_value(coerced, field)

    # Normalize SOURCES order (stable, known-first)
    known_order = ["filesystem_json", "filesystem_csv", "filesystem_xlsx", "jira"]
    ordered = [s for s in known_order if s in sources_set] + sorted(
        [s for s in sources_set if s not in known_order]
    )
    env_values["SOURCES"] = ",".join(ordered)

    missing: list[str] = []
    if "jira" in sources_set:
        if not env_values.get("JIRA_BASE_URL"):
            missing.append("JIRA_BASE_URL")
        if not env_values.get("JIRA_USER_EMAIL"):
            missing.append("JIRA_USER_EMAIL")
        if not env_values.get("JIRA_API_TOKEN"):
            missing.append("JIRA_API_TOKEN")
        has_query = bool((env_values.get("JIRA_JQL") or "").strip()) or bool(
            (env_values.get("JIRA_FILTER_ID") or "").strip()
        )
        if not has_query:
            missing.append("JIRA_JQL|JIRA_FILTER_ID")
    if missing:
        raise ValueError("Faltan credenciales/configuración: " + ", ".join(missing))

    extras = {k: v for k, v in env_values.items() if k not in _known_envs()}
    rendered = _render_env_file(env_values, extras)
    BUG_ENV_PATH.write_text(rendered, encoding="utf-8")
    _apply_env_to_os(env_values)
    reload_bugresolutionradar_settings()
    return get_user_settings_snapshot()


def reset_user_settings_to_example() -> dict[str, Any]:
    _ensure_example_file()
    content = BUG_ENV_EXAMPLE.read_text(encoding="utf-8")
    BUG_ENV_PATH.write_text(content, encoding="utf-8")
    env_values = _parse_env_file(BUG_ENV_PATH)
    _apply_env_to_os(env_values)
    reload_bugresolutionradar_settings()
    return get_user_settings_snapshot()


def _known_envs() -> set[str]:
    return {
        "APP_NAME",
        "TZ",
        "ASSETS_DIR",
        "CACHE_PATH",
        "INCIDENTS_OVERRIDES_PATH",
        "SOURCES",
        "INCIDENTS_UI_ENABLED",
        "XLSX_IGNORE_FILES",
        "XLSX_PREFERRED_SHEET",
        "JIRA_BASE_URL",
        "JIRA_USER_EMAIL",
        "JIRA_API_TOKEN",
        "JIRA_JQL",
        "JIRA_FILTER_ID",
        "JIRA_MAX_RESULTS",
        "JIRA_PAGE_SIZE",
        "JIRA_TIMEOUT_SEC",
        "JIRA_VERIFY_SSL",
        "MASTER_THRESHOLD_CLIENTS",
        "STALE_DAYS_THRESHOLD",
        "PERIOD_DAYS_DEFAULT",
        "LOG_ENABLED",
        "LOG_TO_FILE",
        "LOG_FILE_NAME",
        "LOG_DEBUG",
    }
