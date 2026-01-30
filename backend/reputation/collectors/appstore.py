from __future__ import annotations

from datetime import datetime
import json
from typing import Iterable
from urllib.request import Request, urlopen

from reputation.collectors.base import ReputationCollector
from reputation.models import ReputationItem


class AppStoreCollector(ReputationCollector):
    source_name = "appstore"

    def __init__(self, country: str, app_id: str, max_reviews: int = 200) -> None:
        self._country = country.lower()
        self._app_id = app_id
        self._max_reviews = max(0, max_reviews)

    def collect(self) -> Iterable[ReputationItem]:
        if self._max_reviews <= 0:
            return []

        items: list[ReputationItem] = []
        page = 1
        while len(items) < self._max_reviews:
            entries = self._fetch_page(page)
            if not entries:
                break

            for entry in entries:
                item = self._map_entry(entry)
                if item is None:
                    continue
                items.append(item)
                if len(items) >= self._max_reviews:
                    break

            page += 1

        return items

    def _fetch_page(self, page: int) -> list[dict]:
        url = (
            f"https://itunes.apple.com/{self._country}/rss/"
            f"customerreviews/id={self._app_id}/page={page}/sortby=mostrecent/json"
        )
        req = Request(url, headers={"User-Agent": "bbva-brr-reputation/0.1"})
        with urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        feed = data.get("feed", {})
        entries = feed.get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            return []
        return entries

    def _map_entry(self, entry: dict) -> ReputationItem | None:
        rating = self._get_label(entry, "im:rating")
        if not rating:
            return None

        review_id = (
            entry.get("id", {})
            .get("attributes", {})
            .get("im:id")
            or entry.get("id", {}).get("label")
            or entry.get("link", {}).get("attributes", {}).get("href")
        )
        if not review_id:
            review_id = f"{self._app_id}:{self._country}:{entry.get('title', {}).get('label', '')}"

        published_at = self._parse_datetime(self._get_label(entry, "updated"))

        return ReputationItem(
            id=str(review_id),
            source=self.source_name,
            language=self._get_label(entry, "im:language"),
            published_at=published_at,
            author=self._get_label(entry.get("author", {}), "name"),
            url=entry.get("link", {}).get("attributes", {}).get("href"),
            title=self._get_label(entry, "title"),
            text=self._get_label(entry, "content"),
            signals={
                "rating": self._to_int(rating),
                "version": self._get_label(entry, "im:version"),
                "app_id": self._app_id,
                "country": self._country,
            },
        )

    @staticmethod
    def _get_label(entry: dict, key: str) -> str | None:
        raw = entry.get(key)
        if isinstance(raw, dict):
            return raw.get("label")
        if isinstance(raw, str):
            return raw
        return None

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _to_int(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None
