from __future__ import annotations

from typing import Any, Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import build_url, http_get_json, parse_datetime
from reputation.logging_utils import get_logger
from reputation.models import ReputationItem

logger = get_logger(__name__)


class GuardianCollector(ReputationCollector):
    source_name = "guardian"

    def __init__(
        self,
        api_key: str,
        queries: list[str],
        max_items: int = 1200,
        page_size: int = 50,
        order_by: str = "newest",
        show_fields: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        section: str | None = None,
        tag: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._queries = [q for q in queries if q]
        self._max_items = max(0, max_items)
        self._page_size = max(1, min(200, page_size))
        self._order_by = order_by or "newest"
        self._show_fields = show_fields or "trailText,bodyText,byline"
        self._from_date = (from_date or "").strip()
        self._to_date = (to_date or "").strip()
        self._section = (section or "").strip()
        self._tag = (tag or "").strip()
        self._endpoint = endpoint or "https://content.guardianapis.com/search"

    def collect(self) -> Iterable[ReputationItem]:
        if not self._api_key or not self._queries or self._max_items <= 0:
            return []

        items: list[ReputationItem] = []
        for query in self._queries:
            page = 1
            while len(items) < self._max_items:
                remaining = self._max_items - len(items)
                page_size = min(self._page_size, max(1, remaining))

                params: dict[str, Any] = {
                    "q": query,
                    "api-key": self._api_key,
                    "page": page,
                    "page-size": page_size,
                    "order-by": self._order_by,
                    "show-fields": self._show_fields,
                }
                if self._from_date:
                    params["from-date"] = self._from_date
                if self._to_date:
                    params["to-date"] = self._to_date
                if self._section:
                    params["section"] = self._section
                if self._tag:
                    params["tag"] = self._tag

                url = build_url(self._endpoint, params)
                try:
                    data = http_get_json(url)
                except Exception as exc:
                    logger.warning("Guardian fetch failed: %s", exc)
                    break

                response = data.get("response") or {}
                results = response.get("results") or []
                if not results:
                    break

                for result in results:
                    item = self._map_result(result, query)
                    if item is not None:
                        items.append(item)
                    if len(items) >= self._max_items:
                        return items

                total_pages = response.get("pages") or page
                if page >= total_pages:
                    break
                page += 1

        return items

    def _map_result(self, result: dict[str, Any], query: str) -> ReputationItem | None:
        web_url = result.get("webUrl")
        web_title = result.get("webTitle")
        if not web_url and not web_title:
            return None

        fields = result.get("fields") or {}
        text = fields.get("trailText") or fields.get("bodyText") or ""
        author = fields.get("byline")
        published = parse_datetime(result.get("webPublicationDate"))

        item_id = result.get("id") or web_url or web_title
        return ReputationItem(
            id=str(item_id),
            source=self.source_name,
            language=result.get("language"),
            published_at=published,
            author=author,
            url=web_url,
            title=web_title,
            text=text or None,
            signals={
                "query": query,
                "sectionName": result.get("sectionName"),
                "sectionId": result.get("sectionId"),
                "type": result.get("type"),
                "apiUrl": result.get("apiUrl"),
            },
        )
