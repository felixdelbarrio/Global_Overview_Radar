from __future__ import annotations

from typing import Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import (
    build_url,
    http_get_json,
    http_get_text,
    match_keywords,
    parse_datetime,
    parse_rss,
    rss_debug_enabled,
    rss_is_query_feed,
    rss_source,
)
from reputation.models import ReputationItem


class NewsCollector(ReputationCollector):
    source_name = "news"

    def __init__(
        self,
        api_key: str,
        queries: list[str],
        language: str = "es",
        max_articles: int = 200,
        sources: str | None = None,
        endpoint: str | None = None,
        rss_urls: list[dict[str, str] | str] | None = None,
        rss_only: bool = False,
        filter_terms: list[str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._queries = queries
        self._filter_terms = filter_terms or queries
        self._language = language
        self._max_articles = max(0, max_articles)
        self._sources = sources
        self._endpoint = endpoint or "https://newsapi.org/v2/everything"
        self._rss_urls = rss_urls or []
        self._rss_only = rss_only

    def collect(self) -> Iterable[ReputationItem]:
        if self._max_articles <= 0:
            return []

        if self._rss_only or not self._api_key:
            return self._collect_rss()

        items: list[ReputationItem] = []
        for query in self._queries:
            items.extend(self._collect_query(query))
            if len(items) >= self._max_articles:
                break
        return items[: self._max_articles]

    def _collect_rss(self) -> list[ReputationItem]:
        if not self._rss_urls:
            return []

        items: list[ReputationItem] = []
        for rss_url in self._rss_urls:
            try:
                url_value, meta = rss_source(rss_url)
                raw = http_get_text(url_value)
            except Exception as exc:
                if rss_debug_enabled():
                    print(f"[news] error {rss_url}: {exc}")
                continue
            entries = parse_rss(raw)
            kept = 0
            for entry in entries:
                if self._is_relevant(entry, url_value, meta):
                    items.append(self._map_entry(entry, url_value, meta))
                    kept += 1
                if len(items) >= self._max_articles:
                    return items
            if rss_debug_enabled():
                print(f"[news] {url_value} items={len(entries)} kept={kept}")
        return items

    def _collect_query(self, query: str) -> list[ReputationItem]:
        page = 1
        collected: list[ReputationItem] = []

        while len(collected) < self._max_articles:
            remaining = self._max_articles - len(collected)
            page_size = min(100, max(10, remaining))

            params = {
                "q": query,
                "language": self._language,
                "pageSize": page_size,
                "page": page,
                "apiKey": self._api_key,
                "sources": self._sources or None,
            }
            url = build_url(self._endpoint, params)
            data = http_get_json(url)
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

    def _is_relevant(
        self,
        entry: dict,
        rss_url: str | None = None,
        meta: dict[str, str] | None = None,
    ) -> bool:
        if not self._filter_terms:
            return True
        if rss_url and rss_is_query_feed(rss_url):
            return True
        if meta and (meta.get("query") or meta.get("entity")):
            return True
        text = f"{entry.get('title', '')} {entry.get('summary', '')}"
        return match_keywords(text, self._filter_terms)

    def _map_entry(self, entry: dict, rss_url: str, meta: dict[str, str]) -> ReputationItem:
        meta_local = dict(meta) if meta else {}
        geo = meta_local.pop("geo", None)
        return ReputationItem(
            id=entry.get("link") or entry.get("title", ""),
            source=self.source_name,
            geo=geo,
            language=self._language,
            published_at=parse_datetime(entry.get("published")),
            url=entry.get("link"),
            title=entry.get("title"),
            text=entry.get("summary"),
            signals={"feed": rss_url, **meta_local},
        )
