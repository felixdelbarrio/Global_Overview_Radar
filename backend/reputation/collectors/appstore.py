from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, cast
from urllib.request import Request

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import http_get_text, parse_datetime
from reputation.logging_utils import get_logger
from reputation.models import ReputationItem


class AppStoreCollector(ReputationCollector):
    source_name = "appstore"

    def __init__(
        self,
        country: str,
        app_id: str,
        max_reviews: int = 200,
        geo: str | None = None,
    ) -> None:
        self._country = country.lower()
        self._app_id = app_id
        self._max_reviews = max(0, max_reviews)
        self._geo = geo

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

    def _fetch_page(self, page: int) -> list[dict[str, Any]]:
        url = (
            f"https://itunes.apple.com/{self._country}/rss/"
            f"customerreviews/id={self._app_id}/page={page}/sortby=mostrecent/json"
        )
        req = Request(url, headers={"User-Agent": "global-overview-radar/0.1"})
        raw = http_get_text(req.full_url, headers=dict(req.header_items()), timeout=15)
        data = json.loads(raw) if raw else {}
        if not isinstance(data, dict):
            return []
        data_dict = cast(dict[str, object], data)
        feed = data_dict.get("feed")
        if not isinstance(feed, dict):
            return []
        feed_dict = cast(dict[str, object], feed)
        entries_raw = feed_dict.get("entry", [])
        if isinstance(entries_raw, dict):
            return [cast(dict[str, Any], entries_raw)]
        if not isinstance(entries_raw, list):
            return []
        items = cast(list[object], entries_raw)
        return [cast(dict[str, Any], entry) for entry in items if isinstance(entry, dict)]

    def _map_entry(self, entry: dict[str, Any]) -> ReputationItem | None:
        rating = self._get_label(entry, "im:rating")
        if not rating:
            return None

        review_id = (
            entry.get("id", {}).get("attributes", {}).get("im:id")
            or entry.get("id", {}).get("label")
            or entry.get("link", {}).get("attributes", {}).get("href")
        )
        if not review_id:
            review_id = f"{self._app_id}:{self._country}:{entry.get('title', {}).get('label', '')}"

        published_at = self._parse_datetime(self._get_label(entry, "updated"))

        return ReputationItem(
            id=str(review_id),
            source=self.source_name,
            geo=self._geo,
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
                "geo": self._geo,
            },
        )

    @staticmethod
    def _get_label(entry: dict[str, Any], key: str) -> str | None:
        raw = entry.get(key)
        if isinstance(raw, dict):
            raw_dict = cast(dict[str, object], raw)
            label = raw_dict.get("label")
            return label if isinstance(label, str) else None
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


logger = get_logger(__name__)


class AppStoreScraperCollector(ReputationCollector):
    source_name = "appstore"

    def __init__(
        self,
        country: str,
        app_id: str,
        max_reviews: int = 200,
        geo: str | None = None,
        timeout: int = 15,
    ) -> None:
        self._country = country.lower()
        self._app_id = app_id
        self._max_reviews = max(0, max_reviews)
        self._geo = geo
        self._timeout = max(5, timeout)

    def collect(self) -> Iterable[ReputationItem]:
        if self._max_reviews <= 0:
            return []

        url = f"https://apps.apple.com/{self._country}/app/id{self._app_id}?see-all=reviews"
        try:
            html = http_get_text(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self._timeout,
            )
        except Exception as exc:
            logger.warning("AppStore scrape failed: %s", exc)
            return []

        json_text = _extract_first_json_script(html)
        if not json_text:
            return []
        try:
            data = json.loads(json_text)
        except Exception as exc:
            logger.warning("AppStore scrape json parse failed: %s", exc)
            return []

        reviews = _extract_reviews(data, limit=self._max_reviews)
        items: list[ReputationItem] = []
        for review in reviews:
            item = self._map_review(review)
            if item is not None:
                items.append(item)
            if len(items) >= self._max_reviews:
                break
        return items

    def _map_review(self, review: dict[str, Any]) -> ReputationItem | None:
        review_id = review.get("id")
        title = review.get("title")
        contents = review.get("contents")
        rating = review.get("rating")
        reviewer = review.get("reviewerName")

        if not review_id and not contents and not title:
            return None

        published_at = parse_datetime(review.get("date"))
        if published_at is None and isinstance(review.get("date"), str):
            published_at = parse_datetime(review.get("date"))

        return ReputationItem(
            id=str(review_id or f"{self._app_id}:{self._country}:{title or ''}"),
            source=self.source_name,
            geo=self._geo,
            language=review.get("language"),
            published_at=published_at,
            author=reviewer,
            title=title,
            text=contents,
            signals={
                "rating": rating,
                "app_id": self._app_id,
                "country": self._country,
                "geo": self._geo,
            },
        )


def _extract_first_json_script(html: str) -> str | None:
    start = html.find('<script type="application/json">')
    if start == -1:
        return None
    start = html.find(">", start)
    if start == -1:
        return None
    end = html.find("</script>", start)
    if end == -1:
        return None
    return html[start + 1 : end].strip()


def _extract_reviews(data: object, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(node: object) -> None:
        if len(out) >= limit:
            return
        if isinstance(node, dict):
            if "review" in node and isinstance(node["review"], dict):
                review = node["review"]
                if _is_review_dict(review):
                    rid = str(review.get("id") or "")
                    if rid and rid not in seen:
                        seen.add(rid)
                        out.append(review)
            if _is_review_dict(node):
                rid = str(node.get("id") or "")
                if rid and rid not in seen:
                    seen.add(rid)
                    out.append(node)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(data)
    return out


def _is_review_dict(node: dict[str, Any]) -> bool:
    return bool(node.get("rating") and (node.get("contents") or node.get("title")))
