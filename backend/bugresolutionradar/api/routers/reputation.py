"""Endpoints de reputacion/sentimiento (histórico)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, List

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel
from reputation.actors import (
    actor_principal_canonicals,
    actor_principal_terms,
    build_actor_alias_map,
    primary_actor_info,
)
from reputation.collectors.utils import match_keywords, normalize_text
from reputation.config import (
    active_profile_key,
    active_profile_source,
    active_profiles,
    list_available_profiles,
    load_business_config,
    set_profile_state,
)
from reputation.config import settings as reputation_settings
from reputation.models import (
    ReputationCacheDocument,
    ReputationCacheStats,
    ReputationItem,
    ReputationItemOverride,
)
from reputation.repositories.cache_repo import ReputationCacheRepo
from reputation.repositories.overrides_repo import ReputationOverridesRepo

from bugresolutionradar.config import settings as brr_settings
from bugresolutionradar.logging_utils import get_logger

router = APIRouter()
logger = get_logger(__name__)
COMPARE_BODY = Body(..., description="Lista de filtros a comparar")
MANUAL_OVERRIDE_BLOCKED_SOURCES = {"appstore", "googlereviews"}


def _normalize_source(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in value.lower() if ch.isalnum())


@router.get("/items")
def reputation_items(
    sources: str | None = Query(default=None, description="Lista CSV de fuentes"),
    entity: str | None = Query(default=None, description="actor_principal|otros_actores|all"),
    geo: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    sentiment: str | None = Query(default=None),
    from_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    to_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    period_days: int | None = Query(default=None, ge=1, le=3650),
    q: str | None = Query(default=None, description="Busqueda en titulo/texto"),
) -> ReputationCacheDocument:
    repo = ReputationCacheRepo(reputation_settings.cache_path)
    doc = repo.load()
    if doc is None:
        return ReputationCacheDocument(
            generated_at=datetime.now(timezone.utc),
            config_hash="empty",
            sources_enabled=[],
            items=[],
            market_ratings=[],
            market_ratings_history=[],
            stats=ReputationCacheStats(count=0, note="cache empty"),
        )

    overrides = _load_overrides()
    items = list(
        _filter_items(
            _apply_overrides(doc.items, overrides),
            sources,
            entity,
            geo,
            actor,
            sentiment,
            from_date,
            to_date,
            period_days,
            q,
        )
    )
    logger.debug("Reputation items filtered: %s -> %s", len(doc.items), len(items))
    return ReputationCacheDocument(
        generated_at=doc.generated_at,
        config_hash=doc.config_hash,
        sources_enabled=doc.sources_enabled,
        items=items,
        market_ratings=doc.market_ratings,
        market_ratings_history=doc.market_ratings_history,
        stats=ReputationCacheStats(count=len(items), note=doc.stats.note),
    )


@router.get("/meta")
def reputation_meta() -> dict[str, Any]:
    cfg = load_business_config()
    principal = primary_actor_info(cfg)
    geos = [g for g in cfg.get("geografias", []) if isinstance(g, str) and g.strip()]
    otros_actores_por_geografia = cfg.get("otros_actores_por_geografia") or {}
    otros_actores_globales = cfg.get("otros_actores_globales") or []
    ui_cfg = cfg.get("ui") or {}
    ui_flags = {
        "incidents_enabled": _parse_bool(ui_cfg.get("incidents_enabled"), True),
        "ops_enabled": _parse_bool(ui_cfg.get("ops_enabled"), True),
    }
    repo = ReputationCacheRepo(reputation_settings.cache_path)
    doc = repo.load()
    cache_available = doc is not None
    market_ratings = doc.market_ratings if doc else []
    market_ratings_history = doc.market_ratings_history if doc else []
    profiles_active = active_profiles()
    profile_key = active_profile_key()
    profile_source = active_profile_source()
    source_counts: dict[str, int] = {}
    if doc:
        for item in doc.items:
            if item.source:
                source_counts[item.source] = source_counts.get(item.source, 0) + 1
    sources_enabled = list(reputation_settings.enabled_sources())
    for source in sources_enabled:
        source_counts.setdefault(source, 0)
    sources_available = sorted([s for s, count in source_counts.items() if count > 0])
    incidents_available = Path(brr_settings.cache_path).exists()
    return {
        "actor_principal": principal,
        "geos": geos,
        "otros_actores_por_geografia": otros_actores_por_geografia,
        "otros_actores_globales": otros_actores_globales,
        "sources_enabled": sources_enabled,
        "sources_available": sources_available,
        "source_counts": source_counts,
        "incidents_available": incidents_available,
        "cache_available": cache_available,
        "market_ratings": market_ratings,
        "market_ratings_history": market_ratings_history,
        "profiles_active": profiles_active,
        "profile_key": profile_key,
        "profile_source": profile_source,
        "ui": ui_flags,
    }


class ProfileSelection(BaseModel):
    source: str | None = None
    profiles: list[str] | None = None


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
def reputation_profiles_set(payload: ProfileSelection) -> dict[str, Any]:
    source = payload.source or "default"
    profiles = payload.profiles or []
    active = set_profile_state(source, profiles)
    return {"active": active}


class CompareFilter(BaseModel):
    sources: str | None = None
    entity: str | None = None
    geo: str | None = None
    actor: str | None = None
    sentiment: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    period_days: int | None = None
    q: str | None = None


class OverrideRequest(BaseModel):
    ids: List[str]
    geo: str | None = None
    sentiment: str | None = None
    note: str | None = None


@router.post("/items/override")
def reputation_override(payload: OverrideRequest):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids is required")
    if payload.geo is None and payload.sentiment is None:
        raise HTTPException(status_code=400, detail="geo or sentiment is required")

    geo_value = payload.geo.strip() if isinstance(payload.geo, str) else None
    if payload.geo is not None and not geo_value:
        raise HTTPException(status_code=400, detail="geo cannot be empty")

    sentiment_value = payload.sentiment.lower() if payload.sentiment else None
    if sentiment_value and sentiment_value not in {"positive", "neutral", "negative"}:
        raise HTTPException(status_code=400, detail="invalid sentiment value")

    overrides_repo = ReputationOverridesRepo(reputation_settings.overrides_path)
    overrides = overrides_repo.load()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    doc = ReputationCacheRepo(reputation_settings.cache_path).load()
    source_by_id = {item.id: item.source for item in doc.items} if doc else {}
    updated_ids: list[str] = []
    skipped_ids: list[str] = []

    for item_id in payload.ids:
        source = _normalize_source(source_by_id.get(item_id))
        if source in MANUAL_OVERRIDE_BLOCKED_SOURCES:
            skipped_ids.append(item_id)
            continue
        entry: dict[str, Any] = overrides.get(item_id, {})
        if geo_value is not None:
            entry["geo"] = geo_value
        if sentiment_value is not None:
            entry["sentiment"] = sentiment_value
        if payload.note:
            entry["note"] = payload.note
        entry["updated_at"] = now_iso
        overrides[item_id] = entry
        updated_ids.append(item_id)

    overrides_repo.save(overrides)
    return {
        "updated": len(updated_ids),
        "ids": updated_ids,
        "updated_at": now_iso,
        "skipped": skipped_ids,
    }


@router.post("/items/compare")
def reputation_compare(filters: List[CompareFilter] = COMPARE_BODY):
    """Comparar múltiples filtros en una sola llamada.

    Devuelve los items por grupo y un conjunto combinado deduplicado (por id).
    """
    repo = ReputationCacheRepo(reputation_settings.cache_path)
    doc = repo.load()
    if doc is None:
        return {
            "groups": [],
            "combined": {"items": [], "stats": {"count": 0, "note": "cache empty"}},
        }

    overrides = _load_overrides()
    base_items = _apply_overrides(doc.items, overrides)
    groups = []
    combined_map: dict[str, ReputationItem] = {}

    for idx, f in enumerate(filters):
        items = list(
            _filter_items(
                base_items,
                f.sources,
                f.entity,
                f.geo,
                f.actor,
                f.sentiment,
                f.from_date,
                f.to_date,
                f.period_days,
                f.q,
            )
        )
        # collect into combined map for dedup
        for it in items:
            combined_map[it.id] = it

        groups.append(
            {
                "id": f"group_{idx}",
                "filter": f.model_dump(exclude_none=True),
                "items": [it.model_dump() for it in items],
                "stats": {"count": len(items)},
            }
        )

    combined_items = [v.model_dump() for v in combined_map.values()]
    return {
        "groups": groups,
        "combined": {"items": combined_items, "stats": {"count": len(combined_items)}},
    }


def _filter_items(
    items: Iterable[ReputationItem],
    sources: str | None,
    entity: str | None,
    geo: str | None,
    actor: str | None,
    sentiment: str | None,
    from_date: str | None,
    to_date: str | None,
    period_days: int | None,
    q: str | None,
) -> Iterable[ReputationItem]:
    sources_set = _split_csv(sources)
    entity_lc = entity.lower() if entity else None
    geo_lc = geo.lower() if geo else None
    actor_lc = actor.lower() if actor else None
    sentiment_lc = sentiment.lower() if sentiment else None
    text_query = q.lower() if q else None
    actor_filter = actor_lc

    alias_map: dict[str, str] = {}
    principal_canonicals: set[str] = set()
    principal_terms: list[str] = []

    needs_actor_meta = entity_lc in {"actor_principal", "otros_actores"} or actor_lc is not None
    if needs_actor_meta:
        cfg = load_business_config()
        alias_map = build_actor_alias_map(cfg)
        principal_canonicals = set(actor_principal_canonicals(cfg))
        principal_terms = _principal_terms_from_cfg(cfg)
        if actor_lc:
            actor_filter = alias_map.get(normalize_text(actor or ""), actor or "").lower()

    from_dt: datetime | None
    to_dt: datetime | None
    if period_days is not None:
        today = date.today()
        from_dt = datetime.combine(
            today - timedelta(days=period_days),
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
        to_dt = datetime.combine(
            today,
            datetime.max.time(),
            tzinfo=timezone.utc,
        )
    else:
        from_dt = _parse_date(from_date, start=True)
        to_dt = _parse_date(to_date, start=False)

    for item in items:
        if sources_set and item.source.lower() not in sources_set:
            continue
        if entity_lc and entity_lc != "all":
            is_principal = _item_is_principal(
                item,
                principal_canonicals,
                alias_map,
                principal_terms,
            )
            if entity_lc == "actor_principal" and not is_principal:
                continue
            if entity_lc == "otros_actores" and (is_principal or not item.actor):
                continue
        if geo_lc and (item.geo or "").lower() != geo_lc:
            continue
        if actor_filter:
            item_actor = item.actor or ""
            if alias_map:
                item_actor = alias_map.get(normalize_text(item_actor), item_actor)
            matched = item_actor.lower() == actor_filter
            if not matched:
                signals = item.signals or {}
                actors_signal = signals.get("actors")
                if isinstance(actors_signal, list):
                    for value in actors_signal:
                        if not isinstance(value, str) or not value.strip():
                            continue
                        candidate = value
                        if alias_map:
                            candidate = alias_map.get(normalize_text(candidate), candidate)
                        if candidate.lower() == actor_filter:
                            matched = True
                            break
            if not matched:
                continue
        if sentiment_lc and (item.sentiment or "").lower() != sentiment_lc:
            continue

        compare_dt = item.published_at or item.collected_at
        if from_dt and compare_dt and compare_dt < from_dt:
            continue
        if to_dt and compare_dt and compare_dt > to_dt:
            continue

        if text_query:
            haystack = f"{item.title or ''} {item.text or ''}".lower()
            if text_query not in haystack:
                continue

        yield item


def _load_overrides() -> dict[str, dict[str, Any]]:
    repo = ReputationOverridesRepo(reputation_settings.overrides_path)
    return repo.load()


def _apply_overrides(
    items: Iterable[ReputationItem],
    overrides: dict[str, dict[str, Any]],
) -> list[ReputationItem]:
    if not overrides:
        return list(items)

    for item in items:
        entry = overrides.get(item.id)
        if not entry:
            continue

        override = ReputationItemOverride(
            geo=entry.get("geo"),
            sentiment=entry.get("sentiment"),
            updated_at=_parse_datetime(entry.get("updated_at")),
            note=entry.get("note"),
        )

        if isinstance(override.geo, str) and override.geo.strip():
            item.geo = override.geo.strip()
        if override.sentiment in {"positive", "neutral", "negative"}:
            item.sentiment = override.sentiment

        item.manual_override = override

    return list(items)


def _split_csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {v.strip().lower() for v in value.split(",") if v.strip()}


def _parse_date(value: str | None, start: bool) -> datetime | None:
    if not value:
        return None
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return None
    time_value = datetime.min.time() if start else datetime.max.time()
    return datetime.combine(d, time_value, tzinfo=timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "si"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return default


def _principal_terms_from_cfg(cfg: dict[str, Any]) -> list[str]:
    terms = actor_principal_terms(cfg)
    keywords = [k.strip() for k in cfg.get("keywords", []) if isinstance(k, str) and k.strip()]
    if terms:
        for term in keywords:
            if term and match_keywords(term, terms) and term not in terms:
                terms.append(term)
    return terms


def _item_is_principal(
    item: ReputationItem,
    principal_canonicals: set[str],
    alias_map: dict[str, str],
    principal_terms: list[str],
) -> bool:
    item_actor = item.actor or ""
    if item_actor:
        canonical = alias_map.get(normalize_text(item_actor), item_actor)
        if canonical in principal_canonicals:
            return True
    signals = item.signals or {}
    actors_signal = signals.get("actors")
    if isinstance(actors_signal, list):
        for actor in actors_signal:
            if not isinstance(actor, str) or not actor.strip():
                continue
            canonical = alias_map.get(normalize_text(actor), actor)
            if canonical in principal_canonicals:
                return True
    haystack = f"{item.title or ''} {item.text or ''}".strip()
    if haystack and principal_terms:
        return match_keywords(haystack, principal_terms)
    return False
