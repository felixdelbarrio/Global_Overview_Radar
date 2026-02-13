from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from reputation.actors import (
    actor_principal_terms,
    build_actor_alias_map,
    build_actor_aliases_by_canonical,
    canonicalize_actor,
    primary_actor_info,
)
from reputation.auth import require_google_user, require_mutation_access
from reputation.collectors.utils import match_keywords, normalize_text, tokenize
from reputation.config import (
    active_profile_key,
    active_profile_source,
    active_profiles,
    apply_sample_profiles_to_default,
    compute_config_hash,
    list_available_profiles,
    load_business_config,
    normalize_profile_source,
    reload_reputation_settings,
    set_profile_state,
    settings,
)
from reputation.models import (
    ReputationCacheDocument,
    ReputationCacheStats,
    ReputationItem,
    ReputationItemOverride,
)
from reputation.repositories.cache_repo import ReputationCacheRepo
from reputation.repositories.overrides_repo import ReputationOverridesRepo
from reputation.user_settings import (
    enable_advanced_settings,
    get_user_settings_snapshot,
    reset_user_settings_to_example,
    update_user_settings,
)

logger = logging.getLogger(__name__)


def _refresh_settings() -> None:
    reload_reputation_settings()


router = APIRouter(dependencies=[Depends(_refresh_settings), Depends(require_google_user)])

_ALLOWED_SENTIMENTS = {"positive", "negative", "neutral"}
_MANUAL_OVERRIDE_BLOCKED_SOURCES = {
    "appstore",
    "google_play",
    "google_reviews",
    "downdetector",
}
_STAR_SENTIMENT_SOURCES = {"appstore", "google_play", "google_reviews"}
_COMPARE_BODY = Body(...)


class OverrideRequest(BaseModel):
    ids: list[str]
    geo: str | None = None
    sentiment: str | None = None
    note: str | None = None


class SettingsUpdateRequest(BaseModel):
    values: dict[str, Any] = {}


class ProfilesUpdateRequest(BaseModel):
    source: str | None = None
    profiles: list[str] | None = None


def _is_manual_override_blocked_source(source: str | None) -> bool:
    if not isinstance(source, str):
        return False
    return source.strip().lower() in _MANUAL_OVERRIDE_BLOCKED_SOURCES


def _coerce_star_value(raw: object) -> float | None:
    value: float | None = None
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            value = None
    if value is None:
        return None
    if value <= 0:
        return None
    return min(5.0, max(0.0, value))


def _extract_star_rating(item: ReputationItem) -> float | None:
    signals = item.signals if isinstance(item.signals, dict) else {}
    candidates: list[object] = [
        signals.get("rating"),
        signals.get("score"),
        signals.get("stars"),
        signals.get("star_rating"),
        signals.get("user_rating"),
        signals.get("rating_value"),
        signals.get("reviewRating"),
    ]
    for candidate in candidates:
        if candidate in (None, ""):
            continue
        if isinstance(candidate, dict):
            for nested_key in ("value", "rating", "score", "stars"):
                nested = _coerce_star_value(candidate.get(nested_key))
                if nested is not None:
                    return nested
            continue
        value = _coerce_star_value(candidate)
        if value is not None:
            return value
    return None


def _sentiment_from_stars(stars: float) -> tuple[str, float]:
    if stars < 2.5:
        label = "negative"
    elif stars > 2.5:
        label = "positive"
    else:
        label = "neutral"

    if stars <= 2.5:
        score = (stars - 2.5) / 1.5
    else:
        score = (stars - 2.5) / 2.5
    score = max(-1.0, min(1.0, score))
    return label, score


def _enforce_star_sentiment(item: ReputationItem) -> None:
    source = (item.source or "").strip().lower()
    if source not in _STAR_SENTIMENT_SOURCES:
        return
    stars = _extract_star_rating(item)
    if stars is None:
        return
    label, score = _sentiment_from_stars(stars)
    if not isinstance(item.signals, dict):
        item.signals = {}
    item.sentiment = label
    item.signals["sentiment_score"] = score
    item.signals["sentiment_provider"] = "stars"
    item.signals["sentiment_scale"] = "1-5"
    item.signals["client_sentiment"] = True


def _load_cache() -> ReputationCacheDocument:
    repo = ReputationCacheRepo(settings.cache_path)
    doc = repo.load()
    if doc is None:
        raise HTTPException(status_code=404, detail="cache missing")
    return doc


def _load_cache_optional() -> ReputationCacheDocument | None:
    repo = ReputationCacheRepo(settings.cache_path)
    return repo.load()


def _build_empty_cache_document() -> ReputationCacheDocument:
    now = datetime.now(timezone.utc)
    try:
        cfg = load_business_config()
        cfg_hash = compute_config_hash(cfg)
    except Exception:
        cfg_hash = "empty"
    return ReputationCacheDocument(
        generated_at=now,
        config_hash=cfg_hash or "empty",
        sources_enabled=settings.enabled_sources(),
        items=[],
        market_ratings=[],
        market_ratings_history=[],
        stats=ReputationCacheStats(count=0, note="cache missing"),
    )


def _load_overrides() -> dict[str, dict[str, Any]]:
    repo = ReputationOverridesRepo(settings.overrides_path)
    return repo.load()


def _apply_overrides(
    items: Iterable[ReputationItem], overrides: dict[str, dict[str, Any]]
) -> list[ReputationItem]:
    result: list[ReputationItem] = []
    for item in items:
        item_copy = item.model_copy(deep=True)
        override_data = overrides.get(item_copy.id)
        if override_data:
            try:
                override = ReputationItemOverride.model_validate(override_data)
            except ValidationError:
                logger.warning(
                    "Skipping invalid override for item_id=%s",
                    item_copy.id,
                    exc_info=True,
                )
                _enforce_star_sentiment(item_copy)
                result.append(item_copy)
                continue
            if _is_manual_override_blocked_source(item_copy.source):
                _enforce_star_sentiment(item_copy)
                result.append(item_copy)
                continue
            item_copy.manual_override = override
            if override.geo:
                item_copy.geo = override.geo
            if override.sentiment:
                item_copy.sentiment = override.sentiment
        _enforce_star_sentiment(item_copy)
        result.append(item_copy)
    return result


def _parse_sources(value: object) -> list[str]:
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _safe_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _safe_dict_list(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        cleaned = key.strip()
        if not cleaned:
            continue
        items = _safe_list(raw)
        if items:
            result[cleaned] = items
    return result


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_date = date.fromisoformat(raw)
        except ValueError:
            return None
        return datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone.utc)
    if parsed_dt.tzinfo is None:
        return parsed_dt.replace(tzinfo=timezone.utc)
    return parsed_dt.astimezone(timezone.utc)


def _parse_datetime_bound(value: str | None, *, end_of_day: bool) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    parsed = _parse_datetime(raw)
    if parsed is None:
        return None
    # Date-only filters are interpreted as full-day windows.
    if "T" not in raw and " " not in raw:
        if end_of_day:
            return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed


def _item_datetime(item: ReputationItem) -> datetime | None:
    dt = item.published_at or item.collected_at
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_truthy_signal(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _reply_datetime(item: ReputationItem) -> datetime | None:
    reply = _extract_reply_payload(item)
    if not reply:
        return None
    return _parse_datetime_any(reply.get("replied_at"))


def _item_matches_date_range(
    item: ReputationItem,
    *,
    from_dt: datetime | None,
    to_dt: datetime | None,
    include_reply_datetime: bool = False,
) -> bool:
    if from_dt is None and to_dt is None:
        return True

    candidates: list[datetime] = []
    item_dt = _item_datetime(item)
    if item_dt is not None:
        candidates.append(item_dt)
    if include_reply_datetime:
        reply_dt = _reply_datetime(item)
        if reply_dt is not None:
            candidates.append(reply_dt)

    if not candidates:
        return False
    for candidate in candidates:
        if from_dt and candidate < from_dt:
            continue
        if to_dt and candidate > to_dt:
            continue
        return True
    return False


def _resolve_item_author(item: ReputationItem) -> str | None:
    raw_author = (item.author or "").strip()
    if raw_author:
        return raw_author
    signals = item.signals if isinstance(item.signals, dict) else {}
    for key in _ITEM_AUTHOR_SIGNAL_KEYS:
        candidate = _safe_text(signals.get(key))
        if candidate:
            return candidate
    return None


def _normalize_scalar(value: str | None) -> str:
    return value.strip().lower() if value else ""


def _item_text(item: ReputationItem) -> str:
    parts = [item.title or "", item.text or ""]
    return " ".join(part for part in parts if part).strip()


_MARKET_RECURRING_AUTHOR_LIMIT = 10
_MARKET_AUTHOR_OPINION_LIMIT = 12
_MARKET_FEATURE_LIMIT = 10
_MARKET_FEATURE_EVIDENCE_LIMIT = 3
_MARKET_NEWSLETTER_GEO_LIMIT = 6
_MARKET_ALERT_LIMIT = 8
_MARKET_SOURCES = {"appstore", "google_play", "downdetector"}
_RESPONSE_TRACKED_SOURCES = {"appstore", "google_play"}
_MARKET_GENERIC_FEATURE_KEYS = {
    "bbva",
    "banco",
    "bank",
    "cliente",
    "clientes",
    "usuario",
    "usuarios",
    "servicio",
    "servicios",
    "app",
}
_MARKET_FALLBACK_FEATURES = [
    "login",
    "acceso",
    "transferencias",
    "bizum",
    "tarjeta",
    "seguridad",
    "fraude",
    "phishing",
    "biometria",
    "face id",
    "huella",
    "token",
    "otp",
    "notificaciones",
    "rendimiento",
    "caidas",
    "errores",
    "comisiones",
    "soporte",
    "atencion al cliente",
]
_ITEM_AUTHOR_SIGNAL_KEYS = (
    "author",
    "author_name",
    "authorName",
    "user_name",
    "userName",
    "username",
    "reviewer_name",
    "reviewerName",
    "nickname",
    "nickName",
)


def _ratio(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round(float(part) / float(whole), 4)


def _safe_sentiment(value: str | None) -> str:
    normalized = _normalize_scalar(value)
    if normalized in _ALLOWED_SENTIMENTS:
        return normalized
    return "unknown"


def _safe_score(item: ReputationItem) -> float | None:
    signals = item.signals or {}
    raw = signals.get("sentiment_score")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return None
        try:
            return float(stripped.replace(",", "."))
        except ValueError:
            return None
    return None


def _safe_geo(value: str | None) -> str:
    cleaned = (value or "").strip()
    return cleaned or "Global"


def _safe_author(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return "Autor sin nombre"
    return cleaned


def _safe_excerpt(value: str | None, max_len: int = 180) -> str:
    text = " ".join((value or "").split())
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3].rstrip()}..."


def _feature_key(raw: str) -> tuple[str, str] | None:
    cleaned = " ".join(raw.split())
    if not cleaned:
        return None
    normalized = normalize_text(cleaned)
    tokens = [token for token in normalized.split() if len(token) >= 3]
    if not tokens:
        return None
    key = " ".join(tokens[:4])
    if key in _MARKET_GENERIC_FEATURE_KEYS:
        return None
    return key, cleaned


def _feature_candidates(
    cfg: dict[str, Any],
    principal_terms: list[str],
) -> list[tuple[str, str, list[str]]]:
    principal_tokens = {
        token for term in principal_terms for token in tokenize(term) if token and len(token) >= 3
    }
    raw_terms: list[str] = []
    raw_terms.extend(
        term.strip()
        for term in cfg.get("segment_terms", [])
        if isinstance(term, str) and term.strip()
    )
    raw_terms.extend(
        term.strip() for term in cfg.get("keywords", []) if isinstance(term, str) and term.strip()
    )
    raw_terms.extend(_MARKET_FALLBACK_FEATURES)

    seen: set[str] = set()
    result: list[tuple[str, str, list[str]]] = []
    for raw_term in raw_terms:
        maybe = _feature_key(raw_term)
        if not maybe:
            continue
        key, display = maybe
        tokens = key.split()
        if len(tokens) > 4:
            continue
        if all(token in principal_tokens for token in tokens):
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append((key, display, tokens))

    result.sort(key=lambda item: (-len(item[2]), item[0]))
    return result[:80]


def _market_actions(
    top_features: list[dict[str, Any]],
    recurring_authors: list[dict[str, Any]],
    negative_ratio: float,
    top_source: str | None,
) -> list[str]:
    actions: list[str] = []
    feature_keys = {normalize_text(str(entry.get("feature") or "")) for entry in top_features}

    if any("login" in key or "acceso" in key or "token" in key for key in feature_keys):
        actions.append(
            "Activar un plan de choque en autenticación (login, OTP y recuperación) con seguimiento diario."
        )
    if any(
        "caida" in key or "rendimiento" in key or "errores" in key or "transferencia" in key
        for key in feature_keys
    ):
        actions.append(
            "Priorizar estabilidad transaccional y rendimiento móvil con guardias técnicas 24/7."
        )
    if any("comision" in key or "tarjeta" in key for key in feature_keys):
        actions.append(
            "Publicar una nota proactiva de producto aclarando comisiones, límites y cambios recientes."
        )
    if recurring_authors:
        actions.append(
            "Contactar a los autores más recurrentes para cerrar el loop de feedback y validar mejoras."
        )
    if negative_ratio >= 0.4:
        actions.append(
            "Lanzar un war-room reputacional de 48h con revisión por fuente, severidad y geografía."
        )
    if top_source:
        actions.append(
            f"Reforzar moderación y respuesta en {top_source} para frenar la tracción de opiniones negativas."
        )

    unique_actions: list[str] = []
    seen: set[str] = set()
    for action in actions:
        if action in seen:
            continue
        seen.add(action)
        unique_actions.append(action)
    if not unique_actions:
        unique_actions.append(
            "Mantener vigilancia activa: no hay una señal dominante, pero conviene monitorizar tendencias diarias."
        )
    return unique_actions[:4]


def _compose_newsletter_markdown(
    *,
    geo: str,
    from_date: str | None,
    to_date: str | None,
    principal_actor: str,
    total_mentions: int,
    negative_mentions: int,
    recurring_authors: list[dict[str, Any]],
    top_features: list[dict[str, Any]],
    top_sources: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    actions: list[str],
) -> str:
    range_label = f"{from_date or 'inicio'} → {to_date or 'hoy'}"
    lines = [
        f"# Newsletter reputacional · {geo}",
        "",
        f"**Actor principal:** {principal_actor}",
        f"**Periodo:** {range_label}",
        "",
        "## Señales clave",
        f"- Menciones totales: **{total_mentions}**",
        f"- Menciones negativas: **{negative_mentions}**",
        f"- Autores recurrentes (2+ opiniones): **{len(recurring_authors)}**",
        "",
    ]

    lines.append("## Top funcionalidades penalizadas")
    if top_features:
        for idx, entry in enumerate(top_features[:_MARKET_FEATURE_LIMIT], start=1):
            lines.append(
                f"{idx}. {entry.get('feature', 'Sin etiqueta')} · {entry.get('count', 0)} menciones"
            )
    else:
        lines.append("- No hay señales negativas suficientes para ranking de funcionalidades.")
    lines.append("")

    lines.append("## Voces más insistentes")
    if recurring_authors:
        for idx, entry in enumerate(recurring_authors[:5], start=1):
            lines.append(
                f"{idx}. {entry.get('author', 'Autor')} · {entry.get('opinions_count', 0)} opiniones"
            )
    else:
        lines.append("- No se detectan autores con múltiples opiniones en el periodo.")
    lines.append("")

    lines.append("## Fuentes bajo presión")
    if top_sources:
        for entry in top_sources[:5]:
            ratio = float(entry.get("negative_ratio") or 0.0) * 100
            lines.append(
                f"- {entry.get('source', 'desconocida')}: {entry.get('negative', 0)}/{entry.get('total', 0)} negativas ({ratio:.1f}%)"
            )
    else:
        lines.append("- No hay fuentes con presión destacable.")
    lines.append("")

    lines.append("## Alertas calientes")
    if alerts:
        for alert in alerts[:5]:
            lines.append(
                f"- [{alert.get('severity', 'medium').upper()}] {alert.get('title', 'Alerta')} · {alert.get('summary', '')}"
            )
    else:
        lines.append("- Sin alertas críticas en este corte.")
    lines.append("")

    lines.append("## Acciones recomendadas (48h)")
    for idx, action in enumerate(actions, start=1):
        lines.append(f"{idx}. {action}")

    return "\n".join(lines).strip()


_REPLY_TEXT_KEYS = (
    "reply_text",
    "response_text",
    "developer_reply",
    "developer_response",
    "owner_response",
    "business_response",
    "response",
    "reply",
)
_REPLY_AUTHOR_KEYS = (
    "reply_author",
    "response_author",
    "developer_name",
    "owner_name",
    "author",
)
_REPLY_DATE_KEYS = (
    "reply_at",
    "response_at",
    "replied_at",
    "developer_response_at",
    "owner_response_at",
    "date",
    "time",
    "published_at",
    "updated_at",
)
_REPLY_CONTAINER_KEYS = (
    "reply",
    "response",
    "developer_reply",
    "developer_response",
    "owner_response",
    "business_response",
)
_RESPONSE_DETAIL_LIMIT_DEFAULT = 80
_RESPONSE_DETAIL_LIMIT_MAX = 250
_RESPONSE_REPEAT_LIMIT = 10


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _parse_datetime_any(value: object) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        return _parse_datetime(value)
    if isinstance(value, dict):
        for key in _REPLY_DATE_KEYS:
            candidate = _parse_datetime_any(value.get(key))
            if candidate is not None:
                return candidate
    return None


def _extract_reply_text(value: object) -> str | None:
    direct = _safe_text(value)
    if direct:
        return direct
    if not isinstance(value, dict):
        return None
    for key in ("text", "content", "body", "message", "reply", "response", "value"):
        candidate = _safe_text(value.get(key))
        if candidate:
            return candidate
    return None


def _extract_reply_author(value: object) -> str | None:
    direct = _safe_text(value)
    if direct:
        return direct
    if not isinstance(value, dict):
        return None
    for key in ("author", "name", "display_name", "developer", "owner"):
        candidate = _safe_text(value.get(key))
        if candidate:
            return candidate
    return None


def _extract_reply_payload(item: ReputationItem) -> dict[str, Any] | None:
    signals = item.signals if isinstance(item.signals, dict) else {}
    reply_text: str | None = None
    reply_author: str | None = None
    reply_at: datetime | None = None
    has_reply_flag = _is_truthy_signal(signals.get("has_reply"))

    for key in _REPLY_TEXT_KEYS:
        reply_text = _extract_reply_text(signals.get(key))
        if reply_text:
            break

    for key in _REPLY_CONTAINER_KEYS:
        container = signals.get(key)
        if not isinstance(container, dict):
            continue
        if reply_text is None:
            reply_text = _extract_reply_text(container)
        if reply_author is None:
            reply_author = _extract_reply_author(container)
        if reply_at is None:
            reply_at = _parse_datetime_any(container)

    if reply_author is None:
        for key in _REPLY_AUTHOR_KEYS:
            reply_author = _extract_reply_author(signals.get(key))
            if reply_author:
                break

    if reply_at is None:
        for key in _REPLY_DATE_KEYS:
            reply_at = _parse_datetime_any(signals.get(key))
            if reply_at:
                break

    if not reply_text and not has_reply_flag and reply_author is None and reply_at is None:
        return None

    return {
        "text": reply_text or "",
        "author": reply_author,
        "replied_at": reply_at.isoformat() if reply_at else None,
    }


def _secondary_actor_canonicals(
    cfg: dict[str, Any],
    alias_map: dict[str, str],
    principal_canonical: str | None,
) -> set[str]:
    configured: set[str] = set(_safe_list(cfg.get("otros_actores_globales")))
    for actors in _safe_dict_list(cfg.get("otros_actores_por_geografia")).values():
        configured.update(actors)
    canonicals = {
        canonicalize_actor(name, alias_map)
        for name in configured
        if isinstance(name, str) and name.strip()
    }
    canonicals.discard("")
    if principal_canonical:
        canonicals.discard(principal_canonical)
    return canonicals


def _build_response_summary(
    *,
    items: list[ReputationItem],
    alias_map: dict[str, str],
    principal_canonical: str | None,
    secondary_canonicals: set[str],
    detail_limit: int = _RESPONSE_DETAIL_LIMIT_DEFAULT,
) -> dict[str, Any]:
    bounded_limit = max(1, min(detail_limit, _RESPONSE_DETAIL_LIMIT_MAX))
    total = len(items)

    answered_total = 0
    answered_by_sentiment: Counter[str] = Counter()
    unanswered_by_sentiment: Counter[str] = Counter()
    answered_items: list[dict[str, Any]] = []

    actor_breakdown: dict[tuple[str, str], dict[str, Any]] = {}
    repeated_map: dict[str, dict[str, Any]] = {}

    for item in items:
        sentiment = _safe_sentiment(item.sentiment)
        item_dt = _item_datetime(item)
        item_actor_canonical = canonicalize_actor(item.actor, alias_map) if item.actor else ""

        reply = _extract_reply_payload(item)
        if reply is None:
            unanswered_by_sentiment[sentiment] += 1
            continue

        answered_total += 1
        answered_by_sentiment[sentiment] += 1

        responder_name = _safe_text(reply.get("author")) or item.actor or ""
        responder_canonical_from_author = (
            canonicalize_actor(responder_name, alias_map) if responder_name else ""
        )
        responder_canonical = (
            responder_canonical_from_author or item_actor_canonical or "Actor desconocido"
        )

        if principal_canonical and responder_canonical == principal_canonical:
            responder_type = "principal"
        elif responder_canonical in secondary_canonicals:
            responder_type = "secondary"
        else:
            responder_type = "unknown"

        item_actor_type = "unknown"
        if principal_canonical and item_actor_canonical == principal_canonical:
            item_actor_type = "principal"
        elif item_actor_canonical in secondary_canonicals:
            item_actor_type = "secondary"

        if responder_type == "unknown" and item_actor_type != "unknown":
            responder_type = item_actor_type
            responder_canonical = item_actor_canonical or responder_canonical

        actor_key = (responder_canonical, responder_type)
        actor_entry = actor_breakdown.setdefault(
            actor_key,
            {
                "actor": responder_canonical,
                "actor_type": responder_type,
                "answered": 0,
                "answered_positive": 0,
                "answered_neutral": 0,
                "answered_negative": 0,
            },
        )
        actor_entry["answered"] += 1
        actor_entry[f"answered_{sentiment}"] += 1

        reply_text = str(reply.get("text") or "")
        reply_key = normalize_text(reply_text)
        if reply_key:
            repeated_entry = repeated_map.setdefault(
                reply_key,
                {
                    "reply_text": reply_text,
                    "count": 0,
                    "actors": Counter(),
                    "sentiments": Counter(),
                    "sample_item_ids": [],
                },
            )
            repeated_entry["count"] += 1
            repeated_entry["actors"][responder_canonical] += 1
            repeated_entry["sentiments"][sentiment] += 1
            if len(repeated_entry["sample_item_ids"]) < 5:
                repeated_entry["sample_item_ids"].append(item.id)

        if len(answered_items) < bounded_limit:
            answered_items.append(
                {
                    "id": item.id,
                    "source": item.source,
                    "geo": _safe_geo(item.geo),
                    "sentiment": sentiment,
                    "actor": item.actor,
                    "actor_canonical": item_actor_canonical or None,
                    "responder_actor": responder_canonical,
                    "responder_actor_type": responder_type,
                    "reply_text": reply_text,
                    "reply_excerpt": _safe_excerpt(reply_text, max_len=220),
                    "reply_author": reply.get("author"),
                    "replied_at": reply.get("replied_at"),
                    "published_at": item_dt.isoformat() if item_dt else None,
                    "title": item.title or "",
                    "url": item.url,
                }
            )

    repeated_replies = sorted(
        repeated_map.values(),
        key=lambda entry: (-int(entry["count"]), str(entry["reply_text"])),
    )[:_RESPONSE_REPEAT_LIMIT]

    repeated_serialized = [
        {
            "reply_text": entry["reply_text"],
            "count": int(entry["count"]),
            "actors": [
                {"actor": actor_name, "count": count}
                for actor_name, count in Counter(entry["actors"]).most_common(5)
            ],
            "sentiments": {
                "positive": int(entry["sentiments"].get("positive", 0)),
                "neutral": int(entry["sentiments"].get("neutral", 0)),
                "negative": int(entry["sentiments"].get("negative", 0)),
                "unknown": int(entry["sentiments"].get("unknown", 0)),
            },
            "sample_item_ids": list(entry["sample_item_ids"]),
        }
        for entry in repeated_replies
    ]

    actor_breakdown_rows = sorted(
        actor_breakdown.values(),
        key=lambda entry: (-int(entry["answered"]), str(entry["actor"])),
    )

    return {
        "totals": {
            "opinions_total": total,
            "answered_total": answered_total,
            "answered_ratio": _ratio(answered_total, total),
            "answered_positive": int(answered_by_sentiment.get("positive", 0)),
            "answered_neutral": int(answered_by_sentiment.get("neutral", 0)),
            "answered_negative": int(answered_by_sentiment.get("negative", 0)),
            "unanswered_positive": int(unanswered_by_sentiment.get("positive", 0)),
            "unanswered_neutral": int(unanswered_by_sentiment.get("neutral", 0)),
            "unanswered_negative": int(unanswered_by_sentiment.get("negative", 0)),
        },
        "actor_breakdown": actor_breakdown_rows,
        "repeated_replies": repeated_serialized,
        "answered_items": answered_items,
    }


def _filter_response_tracked_sources(items: Iterable[ReputationItem]) -> list[ReputationItem]:
    return [item for item in items if item.source in _RESPONSE_TRACKED_SOURCES]


def _filter_response_items(
    items: Iterable[ReputationItem],
    group: dict[str, Any],
    alias_map: dict[str, str],
    aliases_by_canonical: dict[str, list[str]],
    principal_canonical: str | None,
    principal_terms: list[str],
) -> list[ReputationItem]:
    base_group = dict(group)
    base_group["from_date"] = None
    base_group["to_date"] = None
    filtered = _filter_items(
        items,
        base_group,
        alias_map,
        aliases_by_canonical,
        principal_canonical,
        principal_terms,
    )
    from_dt = _parse_datetime_bound(group.get("from_date"), end_of_day=False)
    to_dt = _parse_datetime_bound(group.get("to_date"), end_of_day=True)
    if from_dt is None and to_dt is None:
        return filtered
    return [
        item
        for item in filtered
        if _item_matches_date_range(
            item,
            from_dt=from_dt,
            to_dt=to_dt,
            include_reply_datetime=True,
        )
    ]


def _actor_terms_for_group(
    group: dict[str, Any],
    alias_map: dict[str, str],
    aliases_by_canonical: dict[str, list[str]],
    principal_canonical: str | None,
    principal_terms: list[str],
) -> tuple[str | None, list[str]]:
    entity = group.get("entity")
    if entity == "actor_principal":
        return principal_canonical, principal_terms
    actor = group.get("actor")
    if isinstance(actor, str) and actor.strip():
        canonical = canonicalize_actor(actor, alias_map)
        terms = [canonical]
        terms.extend(aliases_by_canonical.get(canonical, []))
        return canonical, terms
    return None, []


def _actor_matches(
    item: ReputationItem,
    canonical: str | None,
    terms: list[str],
    alias_map: dict[str, str],
) -> bool:
    if not canonical and not terms:
        return True
    item_actor = canonicalize_actor(item.actor, alias_map) if item.actor else ""
    if canonical and item_actor and item_actor == canonical:
        return True
    if terms:
        text = _item_text(item)
        if text and match_keywords(text, terms):
            return True
    return False


def _filter_items(
    items: Iterable[ReputationItem],
    group: dict[str, Any],
    alias_map: dict[str, str],
    aliases_by_canonical: dict[str, list[str]],
    principal_canonical: str | None,
    principal_terms: list[str],
) -> list[ReputationItem]:
    canonical, terms = _actor_terms_for_group(
        group=group,
        alias_map=alias_map,
        aliases_by_canonical=aliases_by_canonical,
        principal_canonical=principal_canonical,
        principal_terms=principal_terms,
    )
    geo_filter = _normalize_scalar(group.get("geo"))
    sentiment_filter = _normalize_scalar(group.get("sentiment"))
    sources_filter = _parse_sources(group.get("sources") or group.get("source"))
    from_dt = _parse_datetime_bound(group.get("from_date"), end_of_day=False)
    to_dt = _parse_datetime_bound(group.get("to_date"), end_of_day=True)

    filtered: list[ReputationItem] = []
    for item in items:
        if sources_filter and item.source not in sources_filter:
            continue
        if geo_filter:
            item_geo = _normalize_scalar(item.geo)
            if not item_geo or item_geo != geo_filter:
                continue
        if sentiment_filter:
            item_sentiment = _normalize_scalar(item.sentiment)
            if not item_sentiment or item_sentiment != sentiment_filter:
                continue
        if not _item_matches_date_range(item, from_dt=from_dt, to_dt=to_dt):
            continue
        if not _actor_matches(item, canonical, terms, alias_map):
            continue
        filtered.append(item)
    return filtered


@router.get("/items")
def reputation_items(
    entity: str | None = None,
    actor: str | None = None,
    geo: str | None = None,
    sentiment: str | None = None,
    sources: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    doc = _load_cache_optional() or _build_empty_cache_document()
    overrides = _load_overrides()
    items = _apply_overrides(doc.items, overrides)

    visible_sources = settings.enabled_sources()
    visible_sources_set = set(visible_sources)
    items = [item for item in items if item.source in visible_sources_set]

    try:
        cfg = load_business_config()
    except Exception:
        cfg = {}

    alias_map = build_actor_alias_map(cfg)
    aliases_by_canonical = build_actor_aliases_by_canonical(cfg)
    principal_info = primary_actor_info(cfg)
    principal_canonical = None
    if principal_info:
        principal_canonical = str(principal_info.get("canonical") or "").strip() or None
    principal_terms = actor_principal_terms(cfg)

    group = {
        "entity": entity,
        "actor": actor,
        "geo": geo,
        "sentiment": sentiment,
        "sources": sources,
        "from_date": from_date,
        "to_date": to_date,
    }
    filtered_items = _filter_items(
        items,
        group,
        alias_map,
        aliases_by_canonical,
        principal_canonical,
        principal_terms,
    )

    return {
        "generated_at": doc.generated_at.isoformat(),
        "config_hash": doc.config_hash,
        "sources_enabled": visible_sources,
        "items": [item.model_dump(mode="json") for item in filtered_items],
        "stats": {"count": len(filtered_items), "note": doc.stats.note},
    }


@router.post("/items/override")
def reputation_items_override(
    payload: OverrideRequest,
    _: None = Depends(require_mutation_access),
) -> dict[str, Any]:
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids is required")

    geo = payload.geo.strip() if isinstance(payload.geo, str) else None
    if geo is not None and not geo:
        raise HTTPException(status_code=400, detail="geo cannot be empty")

    sentiment = payload.sentiment.lower() if payload.sentiment else None
    if sentiment and sentiment not in _ALLOWED_SENTIMENTS:
        raise HTTPException(status_code=400, detail="invalid sentiment value")

    if not geo and not sentiment:
        raise HTTPException(status_code=400, detail="geo or sentiment is required")

    doc = _load_cache_optional()
    source_by_id: dict[str, str] = {}
    if doc is not None:
        source_by_id = {
            item.id: item.source
            for item in doc.items
            if isinstance(item.id, str) and isinstance(item.source, str)
        }
    blocked_ids = [
        item_id
        for item_id in payload.ids
        if _is_manual_override_blocked_source(source_by_id.get(item_id))
    ]
    if blocked_ids:
        sources = sorted({source_by_id.get(item_id, "") for item_id in blocked_ids})
        raise HTTPException(
            status_code=400,
            detail=(
                "manual overrides are not allowed for market/store sources "
                f"({', '.join(source for source in sources if source)}): {blocked_ids}"
            ),
        )

    repo = ReputationOverridesRepo(settings.overrides_path)
    overrides = repo.load()
    updated_at = datetime.now(timezone.utc).isoformat()
    for item_id in payload.ids:
        entry = overrides.get(item_id, {})
        if geo:
            entry["geo"] = geo
        if sentiment:
            entry["sentiment"] = sentiment
        if payload.note:
            entry["note"] = payload.note
        entry["updated_at"] = updated_at
        overrides[item_id] = entry
    repo.save(overrides)

    return {"updated": len(payload.ids), "ids": payload.ids, "updated_at": updated_at}


@router.post("/items/compare")
def reputation_items_compare(
    payload: list[dict[str, Any]] = _COMPARE_BODY,
) -> dict[str, Any]:
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="payload must be a list")

    doc = _load_cache_optional()
    if doc is None:
        empty_groups: list[dict[str, Any]] = []
        for group in payload:
            if isinstance(group, dict):
                empty_groups.append({"items": [], "stats": {"count": 0}})
        return {
            "groups": empty_groups,
            "combined": {"items": [], "stats": {"count": 0}},
        }

    overrides = _load_overrides()
    items = _apply_overrides(doc.items, overrides)

    visible_sources = settings.enabled_sources()
    visible_sources_set = set(visible_sources)
    items = [item for item in items if item.source in visible_sources_set]

    try:
        cfg = load_business_config()
    except Exception:
        cfg = {}
    alias_map = build_actor_alias_map(cfg)
    aliases_by_canonical = build_actor_aliases_by_canonical(cfg)
    principal_info = primary_actor_info(cfg)
    principal_canonical = None
    if principal_info:
        principal_canonical = str(principal_info.get("canonical") or "").strip() or None
    principal_terms = actor_principal_terms(cfg)

    groups: list[dict[str, Any]] = []
    combined_map: dict[str, ReputationItem] = {}

    for group in payload:
        group_items = _filter_items(
            items,
            group,
            alias_map,
            aliases_by_canonical,
            principal_canonical,
            principal_terms,
        )
        for item in group_items:
            if item.id not in combined_map:
                combined_map[item.id] = item
        groups.append(
            {
                "items": [item.model_dump(mode="json") for item in group_items],
                "stats": {"count": len(group_items)},
            }
        )

    combined_items = list(combined_map.values())
    return {
        "groups": groups,
        "combined": {
            "items": [item.model_dump(mode="json") for item in combined_items],
            "stats": {"count": len(combined_items)},
        },
    }


@router.get("/responses/summary")
def reputation_responses_summary(
    entity: str | None = None,
    actor: str | None = None,
    geo: str | None = None,
    sentiment: str | None = None,
    sources: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    detail_limit: int = _RESPONSE_DETAIL_LIMIT_DEFAULT,
) -> dict[str, Any]:
    doc = _load_cache_optional() or _build_empty_cache_document()
    overrides = _load_overrides()
    items = _apply_overrides(doc.items, overrides)

    visible_sources = settings.enabled_sources()
    visible_sources_set = set(visible_sources)
    items = [item for item in items if item.source in visible_sources_set]

    try:
        cfg = load_business_config()
    except Exception:
        cfg = {}

    alias_map = build_actor_alias_map(cfg)
    aliases_by_canonical = build_actor_aliases_by_canonical(cfg)
    principal_info = primary_actor_info(cfg)
    principal_canonical = None
    if principal_info:
        principal_canonical = str(principal_info.get("canonical") or "").strip() or None
    principal_terms = actor_principal_terms(cfg)
    secondary_canonicals = _secondary_actor_canonicals(cfg, alias_map, principal_canonical)

    response_group = {
        "entity": entity,
        "actor": actor,
        "geo": geo,
        "sentiment": sentiment,
        "sources": sources,
        "from_date": from_date,
        "to_date": to_date,
    }
    filtered_items = _filter_response_items(
        _filter_response_tracked_sources(items),
        response_group,
        alias_map,
        aliases_by_canonical,
        principal_canonical,
        principal_terms,
    )

    summary = _build_response_summary(
        items=filtered_items,
        alias_map=alias_map,
        principal_canonical=principal_canonical,
        secondary_canonicals=secondary_canonicals,
        detail_limit=detail_limit,
    )

    return {
        "generated_at": doc.generated_at.isoformat(),
        "filters": {
            "entity": entity or "all",
            "actor": actor,
            "geo": geo or "all",
            "sentiment": sentiment or "all",
            "sources": _parse_sources(sources),
            "from_date": from_date,
            "to_date": to_date,
            "detail_limit": max(1, min(detail_limit, _RESPONSE_DETAIL_LIMIT_MAX)),
        },
        **summary,
    }


@router.get("/markets/insights")
def reputation_markets_insights(
    geo: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    sources: str | None = None,
) -> dict[str, Any]:
    doc = _load_cache_optional() or _build_empty_cache_document()
    overrides = _load_overrides()
    items = _apply_overrides(doc.items, overrides)

    visible_sources = settings.enabled_sources()
    visible_sources_set = set(visible_sources)
    items = [item for item in items if item.source in visible_sources_set]
    items = [item for item in items if item.source in _MARKET_SOURCES]

    try:
        cfg = load_business_config()
    except Exception:
        cfg = {}

    alias_map = build_actor_alias_map(cfg)
    aliases_by_canonical = build_actor_aliases_by_canonical(cfg)
    principal_info = primary_actor_info(cfg)
    principal_canonical = None
    if principal_info:
        principal_canonical = str(principal_info.get("canonical") or "").strip() or None
    principal_terms = actor_principal_terms(cfg)
    secondary_canonicals = _secondary_actor_canonicals(cfg, alias_map, principal_canonical)

    normalized_geo = _normalize_scalar(geo)
    geo_filter = None if normalized_geo in {"", "all"} else geo

    scoped_items = _filter_items(
        items,
        {
            "entity": "actor_principal",
            "geo": geo_filter,
            "from_date": from_date,
            "to_date": to_date,
            "sources": sources,
        },
        alias_map,
        aliases_by_canonical,
        principal_canonical,
        principal_terms,
    )
    response_items = _filter_response_items(
        _filter_response_tracked_sources(items),
        {
            "entity": "actor_principal",
            "geo": geo_filter,
            "from_date": from_date,
            "to_date": to_date,
            "sources": sources,
        },
        alias_map,
        aliases_by_canonical,
        principal_canonical,
        principal_terms,
    )
    response_summary = _build_response_summary(
        items=response_items,
        alias_map=alias_map,
        principal_canonical=principal_canonical,
        secondary_canonicals=secondary_canonicals,
        detail_limit=120,
    )

    total_mentions = len(scoped_items)
    sentiment_counts: Counter[str] = Counter()
    score_total = 0.0
    score_count = 0
    daily_volume: Counter[str] = Counter()
    source_stats: dict[str, dict[str, int]] = {}
    geo_stats: dict[str, dict[str, int]] = {}
    author_stats: dict[str, dict[str, Any]] = {}
    id_to_item: dict[str, ReputationItem] = {}
    items_by_geo: dict[str, list[ReputationItem]] = defaultdict(list)

    feature_counts: Counter[str] = Counter()
    feature_display: dict[str, str] = {}
    feature_evidence: dict[str, list[str]] = defaultdict(list)
    source_feature_counts: dict[str, Counter[str]] = defaultdict(Counter)
    geo_feature_counts: dict[str, Counter[str]] = defaultdict(Counter)
    candidates = _feature_candidates(cfg, principal_terms)

    for item in scoped_items:
        id_to_item[item.id] = item
        source = item.source or "desconocida"
        item_geo = _safe_geo(item.geo)
        sentiment = _safe_sentiment(item.sentiment)
        item_dt = _item_datetime(item)
        items_by_geo[item_geo].append(item)

        source_bucket = source_stats.setdefault(
            source,
            {"total": 0, "positive": 0, "neutral": 0, "negative": 0, "unknown": 0},
        )
        source_bucket["total"] += 1
        source_bucket[sentiment] = source_bucket.get(sentiment, 0) + 1

        geo_bucket = geo_stats.setdefault(
            item_geo,
            {"total": 0, "positive": 0, "neutral": 0, "negative": 0, "unknown": 0},
        )
        geo_bucket["total"] += 1
        geo_bucket[sentiment] = geo_bucket.get(sentiment, 0) + 1

        sentiment_counts[sentiment] += 1
        score = _safe_score(item)
        if score is not None:
            score_total += score
            score_count += 1
        if item_dt:
            daily_volume[item_dt.date().isoformat()] += 1

        raw_author = (_resolve_item_author(item) or "").strip()
        if raw_author:
            author_key = normalize_text(raw_author)
            if author_key:
                author_bucket = author_stats.setdefault(
                    author_key,
                    {
                        "author": _safe_author(raw_author),
                        "opinions_count": 0,
                        "sentiments": {"positive": 0, "neutral": 0, "negative": 0, "unknown": 0},
                        "last_seen": None,
                        "opinions": [],
                    },
                )
                author_bucket["opinions_count"] += 1
                author_bucket["sentiments"][sentiment] = (
                    author_bucket["sentiments"].get(sentiment, 0) + 1
                )
                published_at_iso = item_dt.isoformat() if item_dt else None
                last_seen = author_bucket.get("last_seen")
                if published_at_iso and (not last_seen or published_at_iso > last_seen):
                    author_bucket["last_seen"] = published_at_iso
                opinions = author_bucket["opinions"]
                if len(opinions) < _MARKET_AUTHOR_OPINION_LIMIT:
                    opinions.append(
                        {
                            "id": item.id,
                            "source": source,
                            "geo": item_geo,
                            "sentiment": sentiment,
                            "published_at": published_at_iso,
                            "title": item.title or "",
                            "url": item.url,
                            "excerpt": _safe_excerpt(item.text),
                        }
                    )

        if sentiment != "negative":
            continue

        matched_features: set[str] = set()
        for aspect in item.aspects:
            maybe_feature = _feature_key(aspect)
            if not maybe_feature:
                continue
            key, display = maybe_feature
            matched_features.add(key)
            feature_display.setdefault(key, display)
            if len(matched_features) >= 3:
                break

        if not matched_features:
            tokens = set(tokenize(_item_text(item)))
            if tokens:
                for key, display, candidate_tokens in candidates:
                    if all(token in tokens for token in candidate_tokens):
                        matched_features.add(key)
                        feature_display.setdefault(key, display)
                    if len(matched_features) >= 3:
                        break

        for feature_key in matched_features:
            feature_counts[feature_key] += 1
            source_feature_counts[source][feature_key] += 1
            geo_feature_counts[item_geo][feature_key] += 1
            evidence = feature_evidence[feature_key]
            if len(evidence) < _MARKET_FEATURE_EVIDENCE_LIMIT:
                evidence.append(item.id)

    recurring_authors: list[dict[str, Any]] = []
    for bucket in author_stats.values():
        count = int(bucket.get("opinions_count") or 0)
        if count < 2:
            continue
        opinions = list(bucket.get("opinions") or [])
        opinions.sort(key=lambda entry: str(entry.get("published_at") or ""), reverse=True)
        recurring_authors.append(
            {
                "author": bucket.get("author") or "Autor sin nombre",
                "opinions_count": count,
                "sentiments": bucket.get("sentiments") or {},
                "last_seen": bucket.get("last_seen"),
                "opinions": opinions,
            }
        )
    recurring_authors.sort(
        key=lambda entry: (
            -int(entry.get("opinions_count") or 0),
            -int((entry.get("sentiments") or {}).get("negative") or 0),
            str(entry.get("author") or ""),
        )
    )
    recurring_authors = recurring_authors[:_MARKET_RECURRING_AUTHOR_LIMIT]

    top_penalized_features: list[dict[str, Any]] = []
    for feature_key, count in feature_counts.most_common(_MARKET_FEATURE_LIMIT):
        evidence_items = []
        for evidence_id in feature_evidence.get(feature_key, []):
            evidence_item = id_to_item.get(evidence_id)
            if evidence_item is None:
                continue
            evidence_dt = _item_datetime(evidence_item)
            evidence_items.append(
                {
                    "id": evidence_item.id,
                    "source": evidence_item.source,
                    "geo": _safe_geo(evidence_item.geo),
                    "sentiment": _safe_sentiment(evidence_item.sentiment),
                    "published_at": evidence_dt.isoformat() if evidence_dt else None,
                    "title": evidence_item.title or "",
                    "excerpt": _safe_excerpt(evidence_item.text),
                    "url": evidence_item.url,
                }
            )
        top_penalized_features.append(
            {
                "feature": feature_display.get(feature_key, feature_key),
                "key": feature_key,
                "count": count,
                "evidence": evidence_items,
            }
        )

    source_friction: list[dict[str, Any]] = []
    for source, stats in source_stats.items():
        total = int(stats.get("total") or 0)
        negative = int(stats.get("negative") or 0)
        source_friction.append(
            {
                "source": source,
                "total": total,
                "negative": negative,
                "positive": int(stats.get("positive") or 0),
                "neutral": int(stats.get("neutral") or 0),
                "negative_ratio": _ratio(negative, total),
                "top_features": [
                    {
                        "feature": feature_display.get(feature_key, feature_key),
                        "count": count,
                    }
                    for feature_key, count in source_feature_counts[source].most_common(3)
                ],
            }
        )
    source_friction.sort(
        key=lambda entry: (-float(entry["negative_ratio"]), -int(entry["total"]), entry["source"])
    )

    geo_summary: list[dict[str, Any]] = []
    for item_geo, stats in geo_stats.items():
        total = int(stats.get("total") or 0)
        negative = int(stats.get("negative") or 0)
        geo_summary.append(
            {
                "geo": item_geo,
                "total": total,
                "negative": negative,
                "positive": int(stats.get("positive") or 0),
                "neutral": int(stats.get("neutral") or 0),
                "negative_ratio": _ratio(negative, total),
                "share": _ratio(total, total_mentions),
            }
        )
    geo_summary.sort(key=lambda entry: (-int(entry["total"]), entry["geo"]))

    negative_mentions = int(sentiment_counts.get("negative", 0))
    negative_ratio = _ratio(negative_mentions, total_mentions)
    avg_score = round(score_total / score_count, 4) if score_count else None
    kpis = {
        "total_mentions": total_mentions,
        "negative_mentions": negative_mentions,
        "negative_ratio": negative_ratio,
        "positive_mentions": int(sentiment_counts.get("positive", 0)),
        "neutral_mentions": int(sentiment_counts.get("neutral", 0)),
        "unique_authors": len(author_stats),
        "recurring_authors": len(recurring_authors),
        "average_sentiment_score": avg_score,
    }

    alerts: list[dict[str, Any]] = []
    if total_mentions >= 15 and negative_ratio >= 0.45:
        alerts.append(
            {
                "id": "global-negative-ratio",
                "severity": "critical",
                "title": "Tensión reputacional elevada",
                "summary": (
                    f"El {negative_ratio * 100:.1f}% de las menciones del actor principal son negativas."
                ),
                "geo": "all",
                "source": None,
                "evidence_ids": [item.id for item in scoped_items[:3]],
            }
        )

    for source_row in source_friction[:3]:
        if int(source_row["total"]) < 6 or float(source_row["negative_ratio"]) < 0.5:
            continue
        alerts.append(
            {
                "id": f"source-{source_row['source']}",
                "severity": "high",
                "title": f"Fuente bajo presión: {source_row['source']}",
                "summary": (
                    f"{source_row['negative']}/{source_row['total']} menciones negativas "
                    f"({float(source_row['negative_ratio']) * 100:.1f}%)."
                ),
                "geo": "all",
                "source": source_row["source"],
                "evidence_ids": [],
            }
        )

    if top_penalized_features:
        top_feature = top_penalized_features[0]
        if int(top_feature.get("count") or 0) >= 3:
            alerts.append(
                {
                    "id": f"feature-{top_feature.get('key')}",
                    "severity": "high",
                    "title": f"Funcionalidad más penalizada: {top_feature.get('feature')}",
                    "summary": (
                        f"Acumula {top_feature.get('count', 0)} menciones negativas en el periodo."
                    ),
                    "geo": "all",
                    "source": None,
                    "evidence_ids": [
                        entry.get("id")
                        for entry in top_feature.get("evidence", [])
                        if isinstance(entry, dict) and entry.get("id")
                    ],
                }
            )

    for geo_row in geo_summary:
        if int(geo_row["total"]) < 8 or float(geo_row["negative_ratio"]) < 0.45:
            continue
        alerts.append(
            {
                "id": f"geo-{geo_row['geo']}",
                "severity": "medium",
                "title": f"Riesgo geográfico: {geo_row['geo']}",
                "summary": (
                    f"{geo_row['negative']}/{geo_row['total']} menciones negativas "
                    f"({float(geo_row['negative_ratio']) * 100:.1f}%)."
                ),
                "geo": geo_row["geo"],
                "source": None,
                "evidence_ids": [],
            }
        )

    if recurring_authors:
        top_author = recurring_authors[0]
        if int(top_author.get("opinions_count") or 0) >= 3:
            alerts.append(
                {
                    "id": "author-recurring",
                    "severity": "medium",
                    "title": "Autor muy recurrente",
                    "summary": (
                        f"{top_author.get('author')} acumula "
                        f"{top_author.get('opinions_count')} opiniones en el periodo."
                    ),
                    "geo": "all",
                    "source": None,
                    "evidence_ids": [
                        entry.get("id")
                        for entry in top_author.get("opinions", [])
                        if isinstance(entry, dict) and entry.get("id")
                    ][:3],
                }
            )

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(
        key=lambda entry: (
            severity_order.get(str(entry.get("severity")), 99),
            str(entry.get("id") or ""),
        )
    )
    alerts = alerts[:_MARKET_ALERT_LIMIT]

    available_geos = [entry["geo"] for entry in geo_summary]
    if geo_filter:
        newsletter_geos = [_safe_geo(geo_filter)]
    else:
        newsletter_geos = available_geos[:_MARKET_NEWSLETTER_GEO_LIMIT]

    newsletter_by_geo: list[dict[str, Any]] = []
    principal_label = principal_canonical or "Actor principal"
    top_source_name: str | None = None
    if source_friction:
        top_source_name = str(source_friction[0].get("source") or "") or None

    for newsletter_geo in newsletter_geos:
        geo_items = items_by_geo.get(newsletter_geo, [])
        geo_total = len(geo_items)
        geo_negative = sum(1 for item in geo_items if _safe_sentiment(item.sentiment) == "negative")
        geo_feature_counts_current = geo_feature_counts.get(newsletter_geo, Counter())
        geo_top_features = [
            {
                "feature": feature_display.get(feature_key, feature_key),
                "count": count,
            }
            for feature_key, count in geo_feature_counts_current.most_common(_MARKET_FEATURE_LIMIT)
        ]
        geo_sources_counter: Counter[str] = Counter()
        geo_sources_negative: Counter[str] = Counter()
        geo_authors_counter: Counter[str] = Counter()
        for item in geo_items:
            source = item.source or "desconocida"
            geo_sources_counter[source] += 1
            if _safe_sentiment(item.sentiment) == "negative":
                geo_sources_negative[source] += 1
            resolved_author = _resolve_item_author(item)
            if resolved_author:
                geo_authors_counter[_safe_author(resolved_author)] += 1
        geo_top_sources = [
            {
                "source": source,
                "total": total,
                "negative": int(geo_sources_negative.get(source, 0)),
                "negative_ratio": _ratio(int(geo_sources_negative.get(source, 0)), total),
            }
            for source, total in geo_sources_counter.most_common(5)
        ]
        geo_recurring_authors = [
            {"author": author, "opinions_count": count}
            for author, count in geo_authors_counter.most_common(5)
            if count >= 2
        ]
        geo_alerts = [entry for entry in alerts if entry.get("geo") in {"all", newsletter_geo}]
        selected_geo_top_source = (
            str(geo_top_sources[0].get("source") or "") if geo_top_sources else top_source_name
        )
        geo_actions = _market_actions(
            top_features=geo_top_features,
            recurring_authors=geo_recurring_authors,
            negative_ratio=_ratio(geo_negative, geo_total),
            top_source=selected_geo_top_source or None,
        )
        markdown = _compose_newsletter_markdown(
            geo=newsletter_geo,
            from_date=from_date,
            to_date=to_date,
            principal_actor=principal_label,
            total_mentions=geo_total,
            negative_mentions=geo_negative,
            recurring_authors=geo_recurring_authors,
            top_features=geo_top_features,
            top_sources=geo_top_sources,
            alerts=geo_alerts,
            actions=geo_actions,
        )
        subject = (
            f"[GOR] Radar reputacional {newsletter_geo} · "
            f"{datetime.now(timezone.utc).date().isoformat()}"
        )
        preview = (
            f"{geo_negative}/{geo_total} menciones negativas · "
            f"{len(geo_recurring_authors)} autores recurrentes"
        )
        newsletter_by_geo.append(
            {
                "geo": newsletter_geo,
                "subject": subject,
                "preview": preview,
                "markdown": markdown,
                "actions": geo_actions,
            }
        )

    return {
        "generated_at": doc.generated_at.isoformat(),
        "principal_actor": principal_label,
        "comparisons_enabled": False,
        "filters": {
            "geo": geo_filter or "all",
            "from_date": from_date,
            "to_date": to_date,
            "sources": _parse_sources(sources),
        },
        "kpis": kpis,
        "daily_volume": [
            {"date": day, "count": count}
            for day, count in sorted(daily_volume.items(), key=lambda entry: entry[0])
        ],
        "geo_summary": geo_summary,
        "recurring_authors": recurring_authors,
        "top_penalized_features": top_penalized_features,
        "source_friction": source_friction,
        "alerts": alerts,
        "responses": response_summary,
        "newsletter_by_geo": newsletter_by_geo,
    }


@router.get("/meta")
def reputation_meta() -> dict[str, Any]:
    try:
        cfg = load_business_config()
    except Exception:
        cfg = {}

    principal_info = primary_actor_info(cfg)
    geos = _safe_list(cfg.get("geografias"))
    otros_actores_por_geografia = _safe_dict_list(cfg.get("otros_actores_por_geografia"))
    otros_actores_globales = _safe_list(cfg.get("otros_actores_globales"))

    doc = _load_cache_optional()
    cache_available = doc is not None

    sources_enabled = settings.enabled_sources()
    visible_sources_set = set(sources_enabled)
    sources_available = sorted(visible_sources_set)

    source_counts: dict[str, int] = {}
    market_ratings: list[dict[str, Any]] = []
    market_ratings_history: list[dict[str, Any]] = []
    if doc:
        for item in doc.items:
            if not item.source:
                continue
            if item.source not in visible_sources_set:
                continue
            source_counts[item.source] = source_counts.get(item.source, 0) + 1
        market_ratings = [entry.model_dump(mode="json") for entry in doc.market_ratings]
        market_ratings_history = [
            entry.model_dump(mode="json") for entry in doc.market_ratings_history
        ]

    return {
        "actor_principal": principal_info,
        "geos": geos,
        "otros_actores_por_geografia": otros_actores_por_geografia,
        "otros_actores_globales": otros_actores_globales,
        "sources_enabled": sources_enabled,
        "sources_available": sources_available,
        "source_counts": source_counts,
        "cache_available": cache_available,
        "market_ratings": market_ratings,
        "market_ratings_history": market_ratings_history,
        "ui_show_comparisons": settings.ui_show_comparisons,
        "ui_show_dashboard_responses": settings.ui_show_dashboard_responses,
        "profiles_active": active_profiles(),
        "profile_key": active_profile_key(),
        "profile_source": active_profile_source(),
    }


@router.get("/profiles")
def reputation_profiles() -> dict[str, Any]:
    return {
        "active": {
            "source": active_profile_source(),
            "profiles": active_profiles(),
            "profile_key": active_profile_key(),
        },
        "options": {
            "default": list_available_profiles("default"),
            "samples": list_available_profiles("samples"),
        },
    }


@router.post("/profiles")
def reputation_profiles_update(
    payload: ProfilesUpdateRequest,
    _: None = Depends(require_mutation_access),
) -> dict[str, Any]:
    source = normalize_profile_source(payload.source)
    profiles = payload.profiles or []
    try:
        if source == "samples":
            result = apply_sample_profiles_to_default(profiles)
            active = result.get("active")
            response: dict[str, Any] = dict(result)
            response["active"] = active
            response["auto_ingest"] = {"started": False}
            return response
        active = set_profile_state(source, profiles)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"active": active, "auto_ingest": {"started": False}}


@router.get("/settings")
def reputation_settings() -> dict[str, Any]:
    # Read-only snapshot: safe to expose in bypass mode without admin key.
    return get_user_settings_snapshot()


@router.post("/settings")
def reputation_settings_update(
    payload: SettingsUpdateRequest,
    _: None = Depends(require_mutation_access),
) -> dict[str, Any]:
    try:
        return update_user_settings(payload.values or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/settings/reset")
def reputation_settings_reset(
    _: None = Depends(require_mutation_access),
) -> dict[str, Any]:
    return reset_user_settings_to_example()


@router.post("/settings/advanced/enable")
def reputation_settings_enable_advanced(
    _: None = Depends(require_mutation_access),
) -> dict[str, Any]:
    try:
        return enable_advanced_settings()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
