from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from reputation.actors import (
    actor_principal_terms,
    build_actor_alias_map,
    build_actor_aliases_by_canonical,
    canonicalize_actor,
    primary_actor_info,
)
from reputation.auth import require_google_user, require_mutation_access
from reputation.collectors.utils import match_keywords
from reputation.config import (
    active_profile_key,
    active_profile_source,
    active_profiles,
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


def _refresh_settings() -> None:
    reload_reputation_settings()


router = APIRouter(dependencies=[Depends(_refresh_settings), Depends(require_google_user)])

_ALLOWED_SENTIMENTS = {"positive", "negative", "neutral"}
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
            override = ReputationItemOverride.model_validate(override_data)
            item_copy.manual_override = override
            if override.geo:
                item_copy.geo = override.geo
            if override.sentiment:
                item_copy.sentiment = override.sentiment
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


def _item_datetime(item: ReputationItem) -> datetime | None:
    dt = item.published_at or item.collected_at
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_scalar(value: str | None) -> str:
    return value.strip().lower() if value else ""


def _item_text(item: ReputationItem) -> str:
    parts = [item.title or "", item.text or ""]
    return " ".join(part for part in parts if part).strip()


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
    from_dt = _parse_datetime(group.get("from_date"))
    to_dt = _parse_datetime(group.get("to_date"))

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
        if from_dt or to_dt:
            item_dt = _item_datetime(item)
            if item_dt is None:
                continue
            if from_dt and item_dt < from_dt:
                continue
            if to_dt and item_dt > to_dt:
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
