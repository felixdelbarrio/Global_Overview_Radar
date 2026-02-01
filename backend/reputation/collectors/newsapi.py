from __future__ import annotations

from typing import Any, Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import build_url, http_get_json, parse_datetime
from reputation.logging_utils import get_logger
from reputation.models import ReputationItem

logger = get_logger(__name__)


class NewsApiCollector(ReputationCollector):
    source_name = "newsapi"

    def __init__(
        self,
        api_key: str,
        queries: list[str],
        language: str = "es",
        max_articles: int = 1200,
        sources: str | None = None,
        domains: str | None = None,
        sort_by: str | None = None,
        search_in: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._queries = [q for q in queries if q]
        self._language = language or "es"
        self._max_articles = max(0, max_articles)
        self._sources = sources
        self._domains = domains
        self._sort_by = sort_by
        self._search_in = search_in
        self._endpoint = endpoint or "https://newsapi.org/v2/everything"

    def collect(self) -> Iterable[ReputationItem]:
        if not self._api_key or not self._queries or self._max_articles <= 0:
            return []

        items: list[ReputationItem] = []
        for query in self._queries:
            items.extend(self._collect_query(query))
            if len(items) >= self._max_articles:
                break
        return items[: self._max_articles]

    def _collect_query(self, query: str) -> list[ReputationItem]:
        page = 1
        collected: list[ReputationItem] = []

        while len(collected) < self._max_articles:
            remaining = self._max_articles - len(collected)
            page_size = min(100, max(10, remaining))

            params: dict[str, Any] = {
                "q": query,
                "language": self._language,
                "pageSize": page_size,
                "page": page,
                "apiKey": self._api_key,
                "sources": self._sources or None,
                "domains": self._domains or None,
                "sortBy": self._sort_by or None,
                "searchIn": self._search_in or None,
            }
            url = build_url(self._endpoint, params)
            try:
                data = http_get_json(url)
            except Exception as exc:
                logger.warning("NewsAPI fetch failed: %s", exc)
                break

            if data.get("status") == "error":
                logger.warning("NewsAPI error: %s", data.get("message"))
                break

            articles = data.get("articles", [])
            if not articles:
                break

            for article in articles:
                published = parse_datetime(article.get("publishedAt"))
                source_name = article.get("source", {}).get("name")
                url_value = article.get("url")

                collected.append(
                    ReputationItem(
                        id=url_value or article.get("title", ""),
                        source=self.source_name,
                        language=self._language,
                        published_at=published,
                        author=article.get("author"),
                        url=url_value,
                        title=article.get("title"),
                        text=article.get("description") or article.get("content"),
                        signals={"source": source_name, "query": query},
                    )
                )

            page += 1

        return collected
