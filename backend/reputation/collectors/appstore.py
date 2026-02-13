from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable, cast
from urllib.request import Request

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import http_get_text, parse_datetime
from reputation.logging_utils import get_logger
from reputation.models import ReputationItem

_REPLY_TEXT_KEYS = (
    "reply_text",
    "response_text",
    "developerResponse",
    "developer_response",
    "response",
    "reply",
)
_REPLY_AUTHOR_KEYS = ("reply_author", "response_author", "developer_name", "owner_name")
_REPLY_DATE_KEYS = ("reply_at", "response_at", "replied_at", "updated_at", "date")
_REPLY_CONTAINER_KEYS = ("response", "reply", "developerResponse", "developer_response")
_APPSTORE_JSON_SCRIPT_TYPES = {"application/json", "fastboot/shoebox"}
_REPLY_SIGNATURE_PREFIX = "sig:"


def _as_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _extract_reply_text(value: object) -> str | None:
    direct = _as_text(value)
    if direct:
        return direct
    if not isinstance(value, dict):
        return None
    for key in ("text", "content", "contents", "body", "message", "response", "reply"):
        candidate = _as_text(value.get(key))
        if candidate:
            return candidate
    return None


def _extract_reply_date(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return parse_datetime(value)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, dict):
        for key in _REPLY_DATE_KEYS:
            parsed = _extract_reply_date(value.get(key))
            if parsed:
                return parsed
    return None


def _normalize_signature_token(value: object, *, max_len: int) -> str:
    text = _as_text(value)
    if not text:
        return ""
    normalized = re.sub(r"[^0-9a-z]+", " ", text.lower())
    normalized = " ".join(normalized.split())
    if max_len <= 0:
        return normalized
    return normalized[:max_len]


def _date_signature_token(value: object) -> str:
    parsed: datetime | None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = parse_datetime(value)
    else:
        parsed = None
    if parsed is None:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.date().isoformat()


def _review_signature(
    *,
    author: object,
    title: object,
    text: object,
    published_at: object,
) -> str | None:
    author_token = _normalize_signature_token(author, max_len=48)
    title_token = _normalize_signature_token(title, max_len=80)
    text_token = _normalize_signature_token(text, max_len=120)
    anchor = title_token or text_token
    if not anchor:
        return None
    date_token = _date_signature_token(published_at)
    parts = [part for part in (author_token, anchor, date_token) if part]
    if not parts:
        return None
    return "|".join(parts)


def _extract_review_reply(review: dict[str, Any]) -> dict[str, str | None] | None:
    reply_text: str | None = None
    reply_author: str | None = None
    reply_at: datetime | None = None

    for key in _REPLY_TEXT_KEYS:
        reply_text = _extract_reply_text(review.get(key))
        if reply_text:
            break
    for key in _REPLY_CONTAINER_KEYS:
        container = review.get(key)
        if not isinstance(container, dict):
            continue
        if reply_text is None:
            reply_text = _extract_reply_text(container)
        if reply_author is None:
            for author_key in ("author", "name", *_REPLY_AUTHOR_KEYS):
                reply_author = _as_text(container.get(author_key))
                if reply_author:
                    break
        if reply_at is None:
            reply_at = _extract_reply_date(container)
    if reply_author is None:
        for key in _REPLY_AUTHOR_KEYS:
            reply_author = _as_text(review.get(key))
            if reply_author:
                break
    if reply_at is None:
        for key in _REPLY_DATE_KEYS:
            reply_at = _extract_reply_date(review.get(key))
            if reply_at:
                break

    if not reply_text:
        return None
    return {
        "text": reply_text,
        "author": reply_author,
        "replied_at": reply_at.isoformat() if reply_at else None,
    }


def _reply_signals(reply: dict[str, str | None]) -> dict[str, str | bool | None]:
    return {
        "has_reply": True,
        "reply_text": reply.get("text"),
        "reply_author": reply.get("author"),
        "reply_at": reply.get("replied_at"),
    }


def _extract_json_script_candidates(html: str) -> list[str]:
    prioritized: list[str] = []
    fallback: list[str] = []
    for match in re.finditer(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.S | re.I):
        attrs = match.group("attrs")
        body = match.group("body").strip()
        if not body:
            continue
        script_type_match = re.search(r'type=["\']([^"\']+)["\']', attrs, re.I)
        script_type = script_type_match.group(1).strip().lower() if script_type_match else ""
        if script_type not in _APPSTORE_JSON_SCRIPT_TYPES:
            continue
        script_id_match = re.search(r'id=["\']([^"\']+)["\']', attrs, re.I)
        script_id = script_id_match.group(1).strip().lower() if script_id_match else ""
        if script_id in {"serialized-server-data", "shoebox-media-api-cache-apps"}:
            prioritized.append(body)
            continue
        fallback.append(body)
    return prioritized + fallback


def _extract_reviews_from_html(html: str, limit: int) -> list[dict[str, Any]]:
    for json_text in _extract_json_script_candidates(html):
        try:
            data = json.loads(json_text)
        except Exception:
            continue
        reviews = _extract_reviews(data, limit=limit)
        if reviews:
            return reviews
    return []


def _env_true(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


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

        if items and _env_true("APPSTORE_REPLY_ENRICH_ENABLED", default=True):
            self._enrich_with_scraped_replies(items)

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
        reply = _extract_review_reply(entry)
        signals: dict[str, Any] = {
            "rating": self._to_int(rating),
            "version": self._get_label(entry, "im:version"),
            "app_id": self._app_id,
            "country": self._country,
            "geo": self._geo,
        }
        if reply:
            signals.update(_reply_signals(reply))

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
            signals=signals,
        )

    def _enrich_with_scraped_replies(self, items: list[ReputationItem]) -> None:
        replies = self._fetch_scraped_reply_map()
        if not replies:
            return

        for item in items:
            reply = replies.get(str(item.id))
            if reply is None:
                signature = _review_signature(
                    author=item.author,
                    title=item.title,
                    text=item.text,
                    published_at=item.published_at,
                )
                if signature:
                    reply = replies.get(f"{_REPLY_SIGNATURE_PREFIX}{signature}")
            if not reply:
                continue
            signals = dict(item.signals or {})
            if _as_text(signals.get("reply_text")):
                continue
            signals.update(_reply_signals(reply))
            item.signals = signals

    def _fetch_scraped_reply_map(self) -> dict[str, dict[str, str | None]]:
        url = f"https://apps.apple.com/{self._country}/app/id{self._app_id}?see-all=reviews"
        html = http_get_text(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if not html:
            return {}

        reviews = _extract_reviews_from_html(html, limit=self._max_reviews)
        if not reviews:
            return {}

        reply_map: dict[str, dict[str, str | None]] = {}
        for review in reviews:
            review_id = str(review.get("id") or "").strip()
            reply = _extract_review_reply(review)
            if reply is None:
                continue
            if review_id:
                reply_map[review_id] = reply
            signature = _review_signature(
                author=review.get("reviewerName"),
                title=review.get("title"),
                text=review.get("contents"),
                published_at=review.get("date"),
            )
            if signature:
                reply_map.setdefault(f"{_REPLY_SIGNATURE_PREFIX}{signature}", reply)
        return reply_map

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

        reviews = _extract_reviews_from_html(html, limit=self._max_reviews)
        if not reviews:
            return []
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
        reply = _extract_review_reply(review)
        signals: dict[str, Any] = {
            "rating": rating,
            "app_id": self._app_id,
            "country": self._country,
            "geo": self._geo,
        }
        if reply:
            signals.update(_reply_signals(reply))

        return ReputationItem(
            id=str(review_id or f"{self._app_id}:{self._country}:{title or ''}"),
            source=self.source_name,
            geo=self._geo,
            language=review.get("language"),
            published_at=published_at,
            author=reviewer,
            title=title,
            text=contents,
            signals=signals,
        )


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
