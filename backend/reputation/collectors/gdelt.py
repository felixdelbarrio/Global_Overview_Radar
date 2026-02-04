from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import build_url, http_get_json, parse_datetime
from reputation.logging_utils import get_logger
from reputation.models import ReputationItem

logger = get_logger(__name__)


class GdeltCollector(ReputationCollector):
    source_name = "gdelt"

    def __init__(
        self,
        queries: list[str],
        max_records: int = 250,
        max_items: int = 1200,
        timespan: str | None = "7d",
        sort: str = "HybridRel",
        query_suffix: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self._queries = [q for q in queries if q]
        self._max_records = max(1, max_records)
        self._max_items = max(0, max_items)
        self._timespan = timespan
        self._sort = sort
        self._query_suffix = (query_suffix or "").strip()
        self._start_datetime = (start_datetime or "").strip()
        self._end_datetime = (end_datetime or "").strip()
        self._endpoint = endpoint or "https://api.gdeltproject.org/api/v2/doc/doc"

    def collect(self) -> Iterable[ReputationItem]:
        if not self._queries or self._max_items <= 0:
            return []

        items: list[ReputationItem] = []
        max_queries = _env_int("GDELT_MAX_QUERIES", 80)
        max_errors = _env_int("GDELT_MAX_ERRORS", 8)
        error_count = 0
        for idx, query in enumerate(self._queries):
            if max_queries > 0 and idx >= max_queries:
                break
            query_value = self._merge_query(query)
            params: dict[str, Any] = {
                "query": query_value,
                "mode": "ArtList",
                "format": "json",
                "maxrecords": self._max_records,
                "sort": self._sort or "HybridRel",
            }
            if self._start_datetime and self._end_datetime:
                params["startdatetime"] = self._start_datetime
                params["enddatetime"] = self._end_datetime
            elif self._timespan:
                params["timespan"] = self._timespan

            url = build_url(self._endpoint, params)
            try:
                data = http_get_json(url)
            except Exception as exc:
                logger.warning("GDELT fetch failed: %s", exc)
                error_count += 1
                if max_errors > 0 and error_count >= max_errors:
                    logger.warning("GDELT skipped after %s errors", error_count)
                    break
                continue

            articles = data.get("articles") or []
            for article in articles:
                item = self._map_article(article, query_value)
                if item is not None:
                    items.append(item)
                if len(items) >= self._max_items:
                    return items

        return items

    def _merge_query(self, query: str) -> str:
        if not self._query_suffix:
            return query
        return f"{query} {self._query_suffix}".strip()

    def _map_article(self, article: dict[str, Any], query: str) -> ReputationItem | None:
        url = str(article.get("url") or "")
        title = str(article.get("title") or "")
        if not url and not title:
            return None
        published = _parse_gdelt_date(article.get("seendate"))
        if published is None:
            published = parse_datetime(article.get("datetime"))

        return ReputationItem(
            id=url or title,
            source=self.source_name,
            language=_as_str(article.get("language")),
            published_at=published,
            url=url or None,
            title=title or None,
            text=_as_str(article.get("summary")) or None,
            signals={
                "query": query,
                "domain": _as_str(article.get("domain")),
                "sourcecountry": _as_str(article.get("sourcecountry")),
                "tone": article.get("tone"),
                "image": _as_str(article.get("socialimage")),
            },
        )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_gdelt_date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return parse_datetime(text)
