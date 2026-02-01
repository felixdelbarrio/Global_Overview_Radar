from __future__ import annotations

import re
from html import unescape
from typing import Any, Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import build_url, http_get_json, http_get_text, parse_datetime
from reputation.logging_utils import get_logger
from reputation.models import ReputationItem

logger = get_logger(__name__)


class GooglePlayApiCollector(ReputationCollector):
    source_name = "google_play"

    def __init__(
        self,
        endpoint: str,
        api_key: str | None,
        api_key_param: str | None,
        package_id: str,
        country: str,
        language: str,
        max_reviews: int = 200,
        geo: str | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key or ""
        self._api_key_param = (api_key_param or "key").strip()
        self._package_id = package_id
        self._country = country.upper()
        self._language = language
        self._max_reviews = max(0, max_reviews)
        self._geo = geo

    def collect(self) -> Iterable[ReputationItem]:
        if not self._endpoint or self._max_reviews <= 0:
            return []

        params: dict[str, Any] = {
            "package": self._package_id,
            "country": self._country,
            "language": self._language,
            "limit": self._max_reviews,
        }
        if self._api_key and self._api_key_param:
            params[self._api_key_param] = self._api_key

        url = build_url(self._endpoint, params)
        try:
            data = http_get_json(url)
        except Exception as exc:
            logger.warning("Google Play API fetch failed: %s", exc)
            return []

        reviews = _extract_reviews_from_api(data)
        items: list[ReputationItem] = []
        for review in reviews[: self._max_reviews]:
            item = _map_play_review(
                review,
                source=self.source_name,
                package_id=self._package_id,
                country=self._country,
                language=self._language,
                geo=self._geo,
            )
            if item is not None:
                items.append(item)
        return items


class GooglePlayScraperCollector(ReputationCollector):
    source_name = "google_play"

    def __init__(
        self,
        package_id: str,
        country: str,
        language: str,
        max_reviews: int = 200,
        geo: str | None = None,
        timeout: int = 15,
    ) -> None:
        self._package_id = package_id
        self._country = country.upper()
        self._language = language
        self._max_reviews = max(0, max_reviews)
        self._geo = geo
        self._timeout = max(5, timeout)

    def collect(self) -> Iterable[ReputationItem]:
        if not self._package_id or self._max_reviews <= 0:
            return []

        url = (
            "https://play.google.com/store/apps/details"
            f"?id={self._package_id}&hl={self._language}&gl={self._country}&showAllReviews=true"
        )
        try:
            html = http_get_text(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self._timeout,
            )
        except Exception as exc:
            logger.warning("Google Play scrape failed: %s", exc)
            return []

        reviews = _extract_reviews_from_html(html, limit=self._max_reviews)
        items: list[ReputationItem] = []
        for review in reviews:
            item = _map_play_review(
                review,
                source=self.source_name,
                package_id=self._package_id,
                country=self._country,
                language=self._language,
                geo=self._geo,
            )
            if item is not None:
                items.append(item)
            if len(items) >= self._max_reviews:
                break
        return items


def _extract_reviews_from_api(data: object) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    for key in ("reviews", "data", "items", "results"):
        raw = data.get(key)
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
    return []


def _extract_reviews_from_html(html: str, limit: int) -> list[dict[str, Any]]:
    reviews: list[dict[str, Any]] = []
    headers = list(re.finditer(r"<header class=\"c1bOId\"[^>]*data-review-id=\"([^\"]+)\"", html))
    for idx, match in enumerate(headers):
        review_id = match.group(1)
        start = match.start()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else start + 8000
        block = html[start:end]

        author = _extract_text(block, r"<div class=\"X5PpBb\">(.*?)</div>")
        date_text = _extract_text(block, r"<span class=\"bp9Aid\">(.*?)</span>")
        rating = _extract_rating(block)
        content = _extract_text(block, r"<div class=\"h3YV2d\">(.*?)</div>", strip_tags=True)

        reviews.append(
            {
                "id": review_id,
                "author": author,
                "date_text": date_text,
                "rating": rating,
                "text": content,
            }
        )
        if len(reviews) >= limit:
            break

    return reviews


def _extract_text(block: str, pattern: str, strip_tags: bool = False) -> str | None:
    match = re.search(pattern, block, re.S)
    if not match:
        return None
    text = unescape(match.group(1))
    if strip_tags:
        text = re.sub(r"<[^>]+>", "", text)
    return text.strip() if text else None


def _extract_rating(block: str) -> float | None:
    patterns = [
        r"aria-label=\"Valoración:\\s*([0-9.,]+)",
        r"aria-label=\"Rated\\s*([0-9.,]+)\\s*stars",
        r"aria-label=\"([0-9.,]+)\\s*estrellas",
    ]
    for pattern in patterns:
        match = re.search(pattern, block)
        if match:
            return _to_float(match.group(1))
    return None


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _map_play_review(
    review: dict[str, Any],
    source: str,
    package_id: str,
    country: str,
    language: str,
    geo: str | None,
) -> ReputationItem | None:
    review_id = review.get("id") or review.get("reviewId")
    text = review.get("text") or review.get("content") or review.get("review")
    if not review_id and not text:
        return None

    published_at = parse_datetime(review.get("published_at")) or parse_datetime(review.get("date"))

    return ReputationItem(
        id=str(review_id or f"{package_id}:{country}:{text or ''}"),
        source=source,
        geo=geo,
        language=language,
        published_at=published_at,
        author=review.get("author") or review.get("userName"),
        url=review.get("url"),
        title=review.get("title"),
        text=text,
        signals={
            "rating": review.get("rating") or review.get("score"),
            "package_id": package_id,
            "country": country,
            "language": language,
            "geo": geo,
            "date_text": review.get("date_text"),
        },
    )
