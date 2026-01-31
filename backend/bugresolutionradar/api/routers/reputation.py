"""Endpoints de reputacion/sentimiento (histórico)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List

from fastapi import APIRouter, Body, Query
from pydantic import BaseModel
from reputation.config import settings as reputation_settings
from reputation.models import ReputationCacheDocument, ReputationCacheStats, ReputationItem
from reputation.repositories.cache_repo import ReputationCacheRepo

router = APIRouter()
logger = logging.getLogger("bugresolutionradar.reputation")
COMPARE_BODY = Body(..., description="Lista de filtros a comparar")


@router.get("/items")
def reputation_items(
    sources: str | None = Query(default=None, description="Lista CSV de fuentes"),
    entity: str | None = Query(default=None, description="bbva|otros_actores|all"),
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
    # Note: temporary debug logging removed for production readiness.
    return ReputationCacheDocument(
        generated_at=doc.generated_at,
        config_hash=doc.config_hash,
        sources_enabled=doc.sources_enabled,
        items=items,
        stats=ReputationCacheStats(count=len(items), note=doc.stats.note),
    )


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
            item_actor = (item.actor or "").lower()
            if entity_lc == "bbva" and item_actor != "bbva":
                haystack = f"{item.title or ''} {item.text or ''}".lower()
                if "bbva" not in haystack:
                    continue
            if entity_lc == "otros_actores" and (not item_actor or item_actor == "bbva"):
                continue
        if geo_lc and (item.geo or "").lower() != geo_lc:
            continue
        if actor_lc and (item.actor or "").lower() != actor_lc:
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
