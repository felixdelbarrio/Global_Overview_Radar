from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from html import unescape
from typing import Any, Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import build_url, http_get_json, http_get_text, parse_datetime
from reputation.logging_utils import get_logger
from reputation.models import ReputationItem

logger = get_logger(__name__)

_REPLY_TEXT_KEYS = (
    "reply_text",
    "replyText",
    "replyContent",
    "developerReply",
    "developer_response",
    "responseText",
)
_REPLY_AUTHOR_KEYS = ("reply_author", "replyAuthor", "developerName", "ownerName")
_REPLY_DATE_KEYS = (
    "reply_at",
    "replyDate",
    "replyTime",
    "repliedAt",
    "responseDate",
    "responseTime",
)
_REPLY_CONTAINER_KEYS = ("reply", "response", "developerReply", "developer_response")


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

        reviews = _extract_reviews_from_html(
            html,
            limit=self._max_reviews,
            language=self._language,
        )
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


def _extract_reviews_from_html(
    html: str, limit: int, language: str | None = None
) -> list[dict[str, Any]]:
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
        reply = _extract_reply_from_block(block, language=language)
        reply_author = reply.get("replyAuthor") if reply else None
        reply_date = reply.get("replyDate") if reply else None
        reply_text = reply.get("replyText") if reply else None

        reviews.append(
            {
                "id": review_id,
                "author": author,
                "date_text": date_text,
                "rating": rating,
                "text": content,
                "replyText": reply_text,
                "replyAuthor": reply_author,
                "replyDate": reply_date,
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
        r'aria-label="[^"]*?([0-9]+(?:[.,][0-9]+)?)\s*(?:estrellas?|stars?)',
        r'aria-label="(?:Valoración|Rated):?\s*([0-9]+(?:[.,][0-9]+)?)',
        r'data-rating="([0-9]+(?:[.,][0-9]+)?)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, block)
        if match:
            return _to_float(match.group(1))
    return None


def _extract_reply_from_block(block: str, language: str | None) -> dict[str, str] | None:
    # Google Play renders developer answers in a dedicated block (`ocpBU`).
    reply_text = _extract_text(
        block,
        r'<div class="ras4vb">\s*<div>(.*?)</div>\s*</div>',
        strip_tags=True,
    ) or _extract_text(block, r'<div class="ras4vb">(.*?)</div>', strip_tags=True)
    if not reply_text:
        return None

    reply_author = _extract_text(block, r'<div class="I6j64d">(.*?)</div>', strip_tags=True)
    reply_date_text = _extract_text(block, r'<div class="I9Jtec">(.*?)</div>', strip_tags=True)
    reply_date = parse_datetime(reply_date_text) or _parse_google_play_date(
        reply_date_text, language
    )

    payload: dict[str, str] = {"replyText": reply_text}
    if reply_author:
        payload["replyAuthor"] = reply_author
    if reply_date:
        payload["replyDate"] = reply_date.isoformat()
    elif reply_date_text:
        payload["replyDate"] = reply_date_text
    return payload


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


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
    for key in ("text", "content", "body", "message", "reply", "response"):
        candidate = _as_text(value.get(key))
        if candidate:
            return candidate
    return None


def _extract_reply_date(value: object) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        return parse_datetime(value)
    if isinstance(value, dict):
        for key in _REPLY_DATE_KEYS:
            parsed = _extract_reply_date(value.get(key))
            if parsed:
                return parsed
    return None


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
            for author_key in ("author", "name", *(_REPLY_AUTHOR_KEYS)):
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


def _extract_review_rating(review: dict[str, Any]) -> float | int | str | None:
    candidates: list[object] = [
        review.get("rating"),
        review.get("score"),
        review.get("stars"),
        review.get("starRating"),
        review.get("user_rating"),
        review.get("rating_value"),
        review.get("reviewRating"),
    ]
    for candidate in candidates:
        if candidate in (None, ""):
            continue
        if isinstance(candidate, (int, float, str)):
            return candidate
        if isinstance(candidate, dict):
            for key in ("value", "rating", "score", "stars"):
                nested = candidate.get(key)
                if nested in (None, ""):
                    continue
                if isinstance(nested, (int, float, str)):
                    return nested
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
    if published_at is None:
        published_at = _parse_google_play_date(review.get("date_text"), language)

    reply = _extract_review_reply(review)
    rating = _extract_review_rating(review)
    signals: dict[str, Any] = {
        "rating": rating,
        "package_id": package_id,
        "country": country,
        "language": language,
        "geo": geo,
        "date_text": review.get("date_text"),
    }
    if reply:
        signals.update(
            {
                "has_reply": True,
                "reply_text": reply.get("text"),
                "reply_author": reply.get("author"),
                "reply_at": reply.get("replied_at"),
            }
        )

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
        signals=signals,
    )


def _normalize_month_token(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = unicodedata.normalize("NFKD", cleaned)
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    return cleaned


def _parse_google_play_date(date_text: str | None, language: str | None) -> datetime | None:
    if not date_text:
        return None
    text = date_text.strip().lower()
    text = re.sub(r"[.,]", " ", text)
    text = re.sub(r"\bde\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    months_es = {
        "ene": 1,
        "enero": 1,
        "feb": 2,
        "febrero": 2,
        "mar": 3,
        "marzo": 3,
        "abr": 4,
        "abril": 4,
        "may": 5,
        "mayo": 5,
        "jun": 6,
        "junio": 6,
        "jul": 7,
        "julio": 7,
        "ago": 8,
        "agosto": 8,
        "sep": 9,
        "sept": 9,
        "set": 9,
        "septiembre": 9,
        "oct": 10,
        "octubre": 10,
        "nov": 11,
        "noviembre": 11,
        "dic": 12,
        "diciembre": 12,
    }
    months_en = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }

    def parse_day_month_year(value: str) -> datetime | None:
        match = re.match(r"^(\d{1,2})\s+([a-záéíóúñ]+)\s+(\d{4})$", value)
        if not match:
            return None
        day = int(match.group(1))
        month_token = _normalize_month_token(match.group(2))
        year = int(match.group(3))
        month = months_es.get(month_token) or months_en.get(month_token)
        if not month:
            return None
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None

    def parse_month_day_year(value: str) -> datetime | None:
        match = re.match(r"^([a-záéíóúñ]+)\s+(\d{1,2})\s+(\d{4})$", value)
        if not match:
            return None
        month_token = _normalize_month_token(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        month = months_en.get(month_token) or months_es.get(month_token)
        if not month:
            return None
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None

    lang = (language or "").lower()
    if lang.startswith("es"):
        return parse_day_month_year(text) or parse_month_day_year(text)
    return parse_month_day_year(text) or parse_day_month_year(text)
