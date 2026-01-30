from __future__ import annotations

from typing import Any, Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import (
    http_get_text,
    match_keywords,
    parse_datetime,
    parse_rss,
    rss_debug_enabled,
    rss_is_query_feed,
    rss_source,
)
from reputation.models import ReputationItem


class ForumsCollector(ReputationCollector):
    source_name = "forums"

    def __init__(
        self,
        rss_urls: list[dict[str, str] | str],
        keywords: list[str],
        scraping_enabled: bool,
        max_items: int = 200,
    ) -> None:
        self._rss_urls = rss_urls
        self._keywords = [k.lower() for k in keywords if k]
        self._scraping_enabled = scraping_enabled
        self._max_items = max(0, max_items)

    def collect(self) -> Iterable[ReputationItem]:
        if not self._scraping_enabled or not self._rss_urls or self._max_items <= 0:
            return []

        items: list[ReputationItem] = []
        for rss_url in self._rss_urls:
            try:
                url_value, meta = rss_source(rss_url)
                raw = http_get_text(url_value)
            except Exception:
                continue
            entries = parse_rss(raw)
            kept = 0
            for entry in entries:
                if self._is_relevant(entry, url_value, meta):
                    items.append(self._map_entry(entry, url_value, meta))
                    kept += 1
                if len(items) >= self._max_items:
                    return items
            if rss_debug_enabled():
                print(f"[forums] {url_value} items={len(entries)} kept={kept}")
        return items

    def _is_relevant(
        self,
        entry: dict[str, Any],
        rss_url: str | None = None,
        meta: dict[str, str] | None = None,
    ) -> bool:
        if not self._keywords:
            return True
        if rss_url and rss_is_query_feed(rss_url):
            return True
        if meta and (meta.get("query") or meta.get("entity")):
            return True
        text = f"{entry.get('title', '')} {entry.get('summary', '')}"
        return match_keywords(text, self._keywords)

    def _map_entry(
        self, entry: dict[str, Any], rss_url: str, meta: dict[str, str]
    ) -> ReputationItem:
        meta_local = dict(meta) if meta else {}
        geo = meta_local.pop("geo", None)
        return ReputationItem(
            id=entry.get("link") or entry.get("title", ""),
            source=self.source_name,
            geo=geo,
            published_at=parse_datetime(entry.get("published")),
            url=entry.get("link"),
            title=entry.get("title"),
            text=entry.get("summary"),
            signals={"feed": rss_url, **meta_local},
        )
