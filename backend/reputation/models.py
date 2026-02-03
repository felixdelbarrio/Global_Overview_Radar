from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from typing_extensions import Annotated


class ReputationItemOverride(BaseModel):
    geo: str | None = None
    sentiment: str | None = None
    updated_at: datetime | None = None
    note: str | None = None


class ReputationItem(BaseModel):
    """Mención / review / post normalizado."""

    id: str
    source: str
    geo: str | None = None
    actor: str | None = None
    language: str | None = None
    published_at: datetime | None = None
    collected_at: datetime | None = None

    author: str | None = None
    url: str | None = None
    title: str | None = None
    text: str | None = None

    signals: dict[str, Any] = Field(default_factory=dict)
    sentiment: str | None = None
    aspects: list[str] = Field(default_factory=list)
    manual_override: ReputationItemOverride | None = None


class ReputationCacheStats(BaseModel):
    count: int = 0
    note: str | None = None


# Ratings oficiales de stores por app/package.
class MarketRating(BaseModel):
    source: str
    actor: str | None = None
    geo: str | None = None
    app_id: str | None = None
    package_id: str | None = None
    rating: float
    rating_count: int | None = None
    url: str | None = None
    name: str | None = None
    collected_at: datetime | None = None


# 🔑 Truco clave: tipar explícitamente el default_factory
ReputationItemList = Annotated[list[ReputationItem], Field(default_factory=list)]
MarketRatingList = Annotated[list[MarketRating], Field(default_factory=list)]
MarketRatingHistoryList = Annotated[list[MarketRating], Field(default_factory=list)]


class ReputationCacheDocument(BaseModel):
    generated_at: datetime
    config_hash: str
    sources_enabled: list[str] = Field(default_factory=list)

    items: ReputationItemList
    market_ratings: MarketRatingList
    market_ratings_history: MarketRatingHistoryList = Field(default_factory=list)

    stats: ReputationCacheStats = Field(default_factory=ReputationCacheStats)
