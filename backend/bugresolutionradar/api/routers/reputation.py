"""Endpoints de reputacion/sentimiento (histórico)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, List

from fastapi import APIRouter, Body, Query
from pydantic import BaseModel
from reputation.actors import (
    actor_principal_canonicals,
    actor_principal_terms,
    build_actor_alias_map,
    primary_actor_info,
)
from reputation.collectors.utils import match_keywords, normalize_text
from reputation.config import load_business_config
from reputation.config import settings as reputation_settings
from reputation.models import ReputationCacheDocument, ReputationCacheStats, ReputationItem
from reputation.repositories.cache_repo import ReputationCacheRepo

from bugresolutionradar.logging_utils import get_logger

router = APIRouter()
logger = get_logger(__name__)
COMPARE_BODY = Body(..., description="Lista de filtros a comparar")


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
            stats=ReputationCacheStats(count=0, note="cache empty"),
        )

    items = list(
        _filter_items(
            doc.items,
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
        stats=ReputationCacheStats(count=len(items), note=doc.stats.note),
    )


@router.get("/meta")
def reputation_meta() -> dict[str, Any]:
    cfg = load_business_config()
    principal = primary_actor_info(cfg)
    return {"actor_principal": principal}


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

    groups = []
    combined_map: dict[str, ReputationItem] = {}

    for idx, f in enumerate(filters):
        items = list(
            _filter_items(
                doc.items,
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
                "filter": f.dict(exclude_none=True),
                "items": [it.dict() for it in items],
                "stats": {"count": len(items)},
            }
        )

    combined_items = [v.dict() for v in combined_map.values()]
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
            if item_actor.lower() != actor_filter:
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


def _principal_terms_from_cfg(cfg: dict[str, Any]) -> list[str]:
    terms = actor_principal_terms(cfg)
    keywords = [k.strip() for k in cfg.get("keywords", []) if isinstance(k, str) and k.strip()]
    for term in keywords:
        if term and term not in terms:
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
    haystack = f"{item.title or ''} {item.text or ''}".strip()
    if haystack and principal_terms:
        return match_keywords(haystack, principal_terms)
    return False
