"""Endpoints de reputacion (items, meta, perfiles, settings)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from reputation.actors import (
    actor_principal_terms,
    build_actor_alias_map,
    canonicalize_actor,
    primary_actor_info,
)
from reputation.collectors.utils import normalize_text
from reputation.config import (
    active_profile_key,
    active_profile_source,
    active_profiles,
    apply_sample_profiles_to_default,
    list_available_profiles,
    load_business_config,
    set_profile_state,
    settings,
)
from reputation.models import ReputationItem, ReputationItemOverride
from reputation.repositories.cache_repo import ReputationCacheRepo
from reputation.user_settings import (
    FIELDS,
    get_user_settings_snapshot,
    reset_user_settings_to_example,
    update_user_settings,
)

router = APIRouter()


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


class ProfileApplyRequest(BaseModel):
    source: str = "default"
    profiles: list[str] | None = None


class OverrideRequest(BaseModel):
    ids: list[str]
    geo: str | None = None
    sentiment: str | None = None
    note: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _build_geo_alias_map(cfg: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    geos = cfg.get("geografias") or []
    if isinstance(geos, list):
        for geo in geos:
            if isinstance(geo, str) and geo.strip():
                mapping[normalize_text(geo)] = geo.strip()
    aliases = cfg.get("geografias_aliases") or {}
    if isinstance(aliases, dict):
        for canonical, alias_list in aliases.items():
            if not isinstance(canonical, str):
                continue
            canonical_clean = canonical.strip()
            if not canonical_clean:
                continue
            mapping[normalize_text(canonical_clean)] = canonical_clean
            if isinstance(alias_list, list):
                for alias in alias_list:
                    if isinstance(alias, str) and alias.strip():
                        mapping[normalize_text(alias)] = canonical_clean
    return mapping


def _canonical_geo(value: str | None, geo_map: dict[str, str]) -> str | None:
    if not value:
        return None
    key = normalize_text(value)
    return geo_map.get(key, value.strip())


def _parse_sources(value: Any) -> set[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        raw = value.split(",")
    else:
        return set()
    return {str(v).strip().lower() for v in raw if str(v).strip()}


def _load_overrides(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _load_override_items(path: Path) -> tuple[dict[str, Any], str | None]:
    data = _load_overrides(path)
    items = data.get("items") if isinstance(data.get("items"), dict) else {}
    updated_at = data.get("updated_at") if isinstance(data.get("updated_at"), str) else None
    return items, updated_at


def _save_overrides(path: Path, items: dict[str, Any], updated_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": updated_at,
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_overrides(items: list[ReputationItem], overrides: dict[str, Any]) -> list[ReputationItem]:
    for item in items:
        override = overrides.get(item.id)
        if not isinstance(override, dict):
            continue
        override_model = ReputationItemOverride(
            geo=override.get("geo"),
            sentiment=override.get("sentiment"),
            updated_at=_parse_datetime(override.get("updated_at")),
            note=override.get("note"),
        )
        item.manual_override = override_model
        if override_model.geo:
            item.geo = override_model.geo
        if override_model.sentiment:
            item.sentiment = override_model.sentiment
    return items


def _item_date(item: ReputationItem) -> date | None:
    if item.published_at:
        return item.published_at.date()
    if item.collected_at:
        return item.collected_at.date()
    return None


def _normalize_actor(value: str | None, alias_map: dict[str, str]) -> str:
    if not value:
        return ""
    return canonicalize_actor(value, alias_map) if alias_map else value.strip()


def _actor_matches(item: ReputationItem, actor_value: str, alias_map: dict[str, str]) -> bool:
    if not item.actor:
        return False
    normalized_item = _normalize_actor(item.actor, alias_map)
    normalized_target = _normalize_actor(actor_value, alias_map)
    return normalize_text(normalized_item) == normalize_text(normalized_target)


def _text_mentions(item: ReputationItem, terms: Iterable[str]) -> bool:
    if not terms:
        return False
    chunks = [item.title or "", item.text or ""]
    for chunk in chunks:
        if not chunk:
            continue
        normalized = normalize_text(chunk)
        if not normalized:
            continue
        for term in terms:
            if term and term in normalized:
                return True
    return False


def _filter_items(
    items: list[ReputationItem],
    filt: dict[str, Any],
    cfg: dict[str, Any],
    alias_map: dict[str, str],
    principal_terms: list[str],
    geo_map: dict[str, str],
) -> list[ReputationItem]:
    from_date = _parse_date(filt.get("from_date"))
    to_date = _parse_date(filt.get("to_date"))
    sentiment = str(filt.get("sentiment") or "").strip().lower() or None
    geo_filter = _canonical_geo(str(filt.get("geo") or "").strip(), geo_map) if filt.get("geo") else None
    sources = _parse_sources(filt.get("sources"))
    entity = str(filt.get("entity") or "").strip().lower()
    actor_value = filt.get("actor")

    principal = primary_actor_info(cfg) or {}
    principal_canonical = str(principal.get("canonical") or "").strip()

    use_principal_text = False
    actor_filter: str | None = None
    if entity == "actor_principal" and principal_canonical:
        actor_filter = principal_canonical
        use_principal_text = True
    elif actor_value:
        actor_filter = _normalize_actor(str(actor_value), alias_map)

    results: list[ReputationItem] = []
    for item in items:
        item_dt = _item_date(item)
        if from_date and (item_dt is None or item_dt < from_date):
            continue
        if to_date and (item_dt is None or item_dt > to_date):
            continue
        if sentiment and (item.sentiment or "").lower() != sentiment:
            continue
        if sources and (item.source or "").strip().lower() not in sources:
            continue
        if geo_filter:
            item_geo = _canonical_geo(item.geo, geo_map)
            if not item_geo or normalize_text(item_geo) != normalize_text(geo_filter):
                continue
        if actor_filter:
            if _actor_matches(item, actor_filter, alias_map):
                results.append(item)
                continue
            if use_principal_text and _text_mentions(item, principal_terms):
                results.append(item)
                continue
            continue
        results.append(item)
    return results


def _available_sources() -> list[str]:
    sources: list[str] = []
    for field in FIELDS:
        if field.key.startswith("sources."):
            sources.append(field.key.split(".", 1)[1])
    return sources


@router.get("/settings")
def reputation_settings_get() -> dict[str, Any]:
    return get_user_settings_snapshot()


@router.post("/settings")
def reputation_settings_update(payload: SettingsUpdate = Body(...)) -> dict[str, Any]:
    try:
        return update_user_settings(payload.values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/settings/reset")
def reputation_settings_reset() -> dict[str, Any]:
    return reset_user_settings_to_example()


@router.get("/profiles")
def reputation_profiles() -> dict[str, Any]:
    try:
        default_profiles = list_available_profiles("default")
    except Exception:
        default_profiles = []
    try:
        sample_profiles = list_available_profiles("samples")
    except Exception:
        sample_profiles = []

    return {
        "active": {
            "source": active_profile_source(),
            "profiles": active_profiles(),
            "profile_key": active_profile_key(),
        },
        "options": {
            "default": default_profiles,
            "samples": sample_profiles,
        },
    }


@router.post("/profiles")
def reputation_profiles_apply(payload: ProfileApplyRequest = Body(...)) -> dict[str, Any]:
    try:
        if payload.source == "samples":
            result = apply_sample_profiles_to_default(payload.profiles)
            active = result.get("active") if isinstance(result, dict) else None
        else:
            active = set_profile_state(payload.source, payload.profiles)
        return {"active": active}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/meta")
def reputation_meta() -> dict[str, Any]:
    try:
        cfg = load_business_config()
    except FileNotFoundError:
        cfg = {}

    repo = ReputationCacheRepo(settings.cache_path)
    try:
        doc = repo.load()
    except Exception:
        doc = None

    cache_available = doc is not None
    sources_enabled = settings.enabled_sources() if hasattr(settings, "enabled_sources") else []
    sources_available = _available_sources()

    source_counts: dict[str, int] = {}
    market_ratings = []
    market_ratings_history = []
    if doc is not None:
        counts = Counter(
            (item.source or "").strip().lower()
            for item in doc.items
            if item.source and str(item.source).strip()
        )
        source_counts = dict(counts)
        market_ratings = [rating.model_dump(mode="json") for rating in doc.market_ratings]
        market_ratings_history = [rating.model_dump(mode="json") for rating in doc.market_ratings_history]

    return {
        "actor_principal": primary_actor_info(cfg),
        "geos": cfg.get("geografias"),
        "otros_actores_por_geografia": cfg.get("otros_actores_por_geografia"),
        "otros_actores_globales": cfg.get("otros_actores_globales"),
        "sources_enabled": sources_enabled,
        "sources_available": sources_available,
        "source_counts": source_counts,
        "incidents_available": False,
        "cache_available": cache_available,
        "market_ratings": market_ratings,
        "market_ratings_history": market_ratings_history,
        "profiles_active": active_profiles(),
        "profile_key": active_profile_key(),
        "profile_source": active_profile_source(),
        "ui": {
            "incidents_enabled": False,
            "ops_enabled": False,
        },
    }


@router.get("/items")
def reputation_items(
    from_date: date | None = None,
    to_date: date | None = None,
    sentiment: str | None = None,
    entity: str | None = None,
    geo: str | None = None,
    sources: str | None = None,
) -> dict[str, Any]:
    try:
        cfg = load_business_config()
    except FileNotFoundError:
        cfg = {}

    repo = ReputationCacheRepo(settings.cache_path)
    doc = repo.load()
    if doc is None:
        return {
            "generated_at": _now_iso(),
            "config_hash": "",
            "sources_enabled": settings.enabled_sources() if hasattr(settings, "enabled_sources") else [],
            "items": [],
            "market_ratings": [],
            "market_ratings_history": [],
            "stats": {"count": 0, "note": "cache missing"},
        }

    overrides, _ = _load_override_items(settings.overrides_path)
    items = _apply_overrides([item.model_copy() for item in doc.items], overrides)

    alias_map = build_actor_alias_map(cfg)
    principal_terms = [normalize_text(term) for term in actor_principal_terms(cfg)]
    geo_map = _build_geo_alias_map(cfg)
    filt = {
        "from_date": from_date,
        "to_date": to_date,
        "sentiment": sentiment,
        "entity": entity,
        "geo": geo,
        "sources": sources,
    }

    filtered = _filter_items(items, filt, cfg, alias_map, principal_terms, geo_map)

    return {
        "generated_at": doc.generated_at.isoformat(),
        "config_hash": doc.config_hash,
        "sources_enabled": doc.sources_enabled,
        "items": [item.model_dump(mode="json") for item in filtered],
        "market_ratings": [rating.model_dump(mode="json") for rating in doc.market_ratings],
        "market_ratings_history": [rating.model_dump(mode="json") for rating in doc.market_ratings_history],
        "stats": {
            "count": len(filtered),
            "note": doc.stats.note,
        },
    }


@router.post("/items/compare")
def reputation_items_compare(payload: list[dict[str, Any]] = Body(...)) -> dict[str, Any]:
    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="payload must be a list")

    try:
        cfg = load_business_config()
    except FileNotFoundError:
        cfg = {}

    repo = ReputationCacheRepo(settings.cache_path)
    doc = repo.load()
    if doc is None:
        return {"groups": [], "combined": {"items": [], "stats": {"count": 0}}}

    overrides, _ = _load_override_items(settings.overrides_path)
    items = _apply_overrides([item.model_copy() for item in doc.items], overrides)

    alias_map = build_actor_alias_map(cfg)
    principal_terms = [normalize_text(term) for term in actor_principal_terms(cfg)]
    geo_map = _build_geo_alias_map(cfg)

    groups = []
    combined: dict[str, ReputationItem] = {}
    for idx, filt in enumerate(payload, start=1):
        if not isinstance(filt, dict):
            continue
        filtered = _filter_items(items, filt, cfg, alias_map, principal_terms, geo_map)
        for item in filtered:
            combined[item.id] = item
        groups.append(
            {
                "id": f"group_{idx}",
                "filter": filt,
                "items": [item.model_dump(mode="json") for item in filtered],
                "stats": {"count": len(filtered)},
            }
        )

    combined_items = [item.model_dump(mode="json") for item in combined.values()]
    return {
        "groups": groups,
        "combined": {"items": combined_items, "stats": {"count": len(combined_items)}},
    }


@router.post("/items/override")
def reputation_items_override(payload: OverrideRequest) -> dict[str, Any]:
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids is required")
    if payload.geo is None and payload.sentiment is None:
        raise HTTPException(status_code=400, detail="geo or sentiment is required")
    if payload.sentiment is not None:
        value = payload.sentiment.strip().lower()
        if value not in {"positive", "neutral", "negative"}:
            raise HTTPException(status_code=400, detail="invalid sentiment value")
        payload.sentiment = value
    if payload.geo is not None and not payload.geo.strip():
        raise HTTPException(status_code=400, detail="geo cannot be empty")

    overrides, _ = _load_override_items(settings.overrides_path)
    updated_at = _now_iso()

    for item_id in payload.ids:
        entry = overrides.get(item_id)
        if not isinstance(entry, dict):
            entry = {}
        if payload.geo is not None:
            entry["geo"] = payload.geo.strip()
        if payload.sentiment is not None:
            entry["sentiment"] = payload.sentiment
        if payload.note is not None:
            entry["note"] = payload.note
        entry["updated_at"] = updated_at
        overrides[item_id] = entry

    _save_overrides(settings.overrides_path, overrides, updated_at)

    return {"updated": len(payload.ids), "ids": payload.ids, "updated_at": updated_at}
