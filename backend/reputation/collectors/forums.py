from __future__ import annotations

from typing import Any, Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import http_get_text, parse_datetime, parse_rss, rss_debug_enabled
from reputation.models import ReputationItem


class ForumsCollector(ReputationCollector):
    source_name = "forums"

    def __init__(
        self,
        rss_urls: list[str],
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
                raw = http_get_text(rss_url)
            except Exception:
                continue
            entries = parse_rss(raw)
            kept = 0
            for entry in entries:
                if self._is_relevant(entry):
                    items.append(self._map_entry(entry, rss_url))
                    kept += 1
                if len(items) >= self._max_items:
                    return items
            if rss_debug_enabled():
                print(f"[forums] {rss_url} items={len(entries)} kept={kept}")
        return items

    def _is_relevant(self, entry: dict[str, Any]) -> bool:
        if not self._keywords:
            return True
        text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
        return any(keyword in text for keyword in self._keywords)

    def _map_entry(self, entry: dict[str, Any], rss_url: str) -> ReputationItem:
        return ReputationItem(
            id=entry.get("link") or entry.get("title", ""),
            source=self.source_name,
            published_at=parse_datetime(entry.get("published")),
            url=entry.get("link"),
            title=entry.get("title"),
            text=entry.get("summary"),
            signals={"feed": rss_url},
        )
