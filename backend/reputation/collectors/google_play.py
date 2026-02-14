from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from html import unescape
from typing import Any, Iterable
from urllib.request import Request, urlopen

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import build_url, http_get_json, http_get_text, parse_datetime
from reputation.logging_utils import get_logger
from reputation.models import ReputationItem

logger = get_logger(__name__)

_GOOGLE_PLAY_REVIEWS_RPC_URL = "https://play.google.com/_/PlayStoreUi/data/batchexecute"
_GOOGLE_PLAY_REVIEWS_RPC_ID = "oCPfdb"
_GOOGLE_PLAY_REVIEWS_RPC_SORT_NEWEST = 2
_GOOGLE_PLAY_REVIEWS_RPC_MAX_PER_CALL = 200
_GOOGLE_PLAY_REVIEWS_RPC_HEAD_RE = re.compile(r"\)\]\}'\n\n([\s\S]+)")
_GOOGLE_PLAY_REVIEWS_RPC_FIRST_PAGE = (
    "f.req=%5B%5B%5B%22oCPfdb%22%2C%22%5Bnull%2C%5B2%2C{sort}%2C%5B{count}%5D%2Cnull%2C"
    "%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%5D%5D%2C"
    "%5B%5C%22{app_id}%5C%22%2C7%5D%5D%22%2Cnull%2C%22generic%22%5D%5D%5D%0A"
)
_GOOGLE_PLAY_REVIEWS_RPC_NEXT_PAGE = (
    "f.req=%5B%5B%5B%22oCPfdb%22%2C%22%5Bnull%2C%5B2%2C{sort}%2C%5B{count}%2Cnull%2C"
    "%5C%22{token}%5C%22%5D%2Cnull%2C%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C"
    "null%2Cnull%5D%5D%2C%5B%5C%22{app_id}%5C%22%2C7%5D%5D%22%2Cnull%2C%22generic%22%5D%5D%5D%0A"
)

_REPLY_TEXT_KEYS = (
    "reply_text",
    "replyText",
    "replyContent",
    "developerReply",
    "developerResponse",
    "developerComment",
    "developer_comment",
    "developer_response",
    "reply",
    "response",
    "responseText",
)
_REPLY_AUTHOR_KEYS = (
    "reply_author",
    "replyAuthor",
    "developerName",
    "developer_name",
    "developer",
    "developerDisplayName",
    "ownerName",
    "owner_name",
    "responder",
)
_REPLY_DATE_KEYS = (
    "reply_at",
    "replyDate",
    "replyTime",
    "repliedAt",
    "responseDate",
    "responseTime",
    "lastModified",
    "lastModifiedAt",
    "updatedAt",
    "modifiedAt",
    "timestamp",
)
_REPLY_CONTAINER_KEYS = (
    "reply",
    "response",
    "developerReply",
    "developerResponse",
    "developerComment",
    "developer_comment",
    "developer_response",
    "ownerResponse",
    "merchantReply",
)


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
        rpc_enabled = _env_bool(os.getenv("GOOGLE_PLAY_RPC_ENABLED", "true"))
        if rpc_enabled and len(reviews) < self._max_reviews:
            remaining = self._max_reviews - len(reviews)
            try:
                rpc_reviews = _fetch_reviews_from_rpc(
                    package_id=self._package_id,
                    country=self._country,
                    language=self._language,
                    limit=remaining,
                    timeout=self._timeout,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Google Play RPC fetch failed: %s", exc)
                rpc_reviews = []
            if rpc_reviews:
                reviews = _merge_reviews_prefer_rpc(rpc_reviews, reviews, limit=self._max_reviews)
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


def _merge_reviews_prefer_rpc(
    rpc_reviews: list[dict[str, Any]],
    html_reviews: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def dedupe_key(review: dict[str, Any]) -> tuple[str, str]:
        review_id = str(review.get("id") or review.get("reviewId") or "").strip()
        if review_id:
            return ("id", review_id)
        content = str(review.get("text") or review.get("content") or "").strip()
        if content:
            return ("text", content)
        return ("none", "")

    for review in [*rpc_reviews, *html_reviews]:
        if len(merged) >= limit:
            break
        key = dedupe_key(review)
        if key in seen:
            continue
        seen.add(key)
        merged.append(review)
    return merged


def _fetch_reviews_from_rpc(
    *,
    package_id: str,
    country: str,
    language: str,
    limit: int,
    timeout: int,
) -> list[dict[str, Any]]:
    safe_limit = max(0, limit)
    if safe_limit <= 0:
        return []

    url = f"{_GOOGLE_PLAY_REVIEWS_RPC_URL}?hl={language}&gl={country}"
    out: list[dict[str, Any]] = []
    token: str | None = None

    while len(out) < safe_limit:
        batch_size = min(_GOOGLE_PLAY_REVIEWS_RPC_MAX_PER_CALL, safe_limit - len(out))
        payload = _build_reviews_rpc_payload(
            package_id=package_id,
            count=batch_size,
            token=token,
        )
        raw = _post_reviews_rpc(url, payload, timeout=timeout)
        if not raw:
            break
        parsed_reviews, next_token = _extract_reviews_from_rpc_response(raw, limit=batch_size)
        if not parsed_reviews:
            break
        out.extend(parsed_reviews)
        token = next_token
        if not token:
            break

    if len(out) > safe_limit:
        return out[:safe_limit]
    return out


def _build_reviews_rpc_payload(*, package_id: str, count: int, token: str | None) -> bytes:
    if token:
        encoded = _GOOGLE_PLAY_REVIEWS_RPC_NEXT_PAGE.format(
            sort=_GOOGLE_PLAY_REVIEWS_RPC_SORT_NEWEST,
            count=max(1, count),
            token=token,
            app_id=package_id,
        )
    else:
        encoded = _GOOGLE_PLAY_REVIEWS_RPC_FIRST_PAGE.format(
            sort=_GOOGLE_PLAY_REVIEWS_RPC_SORT_NEWEST,
            count=max(1, count),
            app_id=package_id,
        )
    return encoded.encode("utf-8")


def _post_reviews_rpc(url: str, payload: bytes, *, timeout: int) -> str:
    req = Request(
        url,
        data=payload,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urlopen(req, timeout=max(5, timeout)) as response:
        raw = response.read()
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        return raw
    return str(raw)


def _extract_reviews_from_rpc_response(
    raw: str, *, limit: int
) -> tuple[list[dict[str, Any]], str | None]:
    if not raw:
        return [], None
    match = _GOOGLE_PLAY_REVIEWS_RPC_HEAD_RE.search(raw)
    if not match:
        return [], None

    try:
        outer = json.loads(match.group(1))
    except json.JSONDecodeError:
        return [], None
    if not isinstance(outer, list):
        return [], None

    payload: str | None = None
    for entry in outer:
        if not isinstance(entry, list) or len(entry) < 3:
            continue
        if entry[0] != "wrb.fr" or entry[1] != _GOOGLE_PLAY_REVIEWS_RPC_ID:
            continue
        candidate = entry[2]
        if isinstance(candidate, str) and candidate:
            payload = candidate
            break
    if not payload:
        return [], None

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return [], None
    if not isinstance(decoded, list) or not decoded:
        return [], None

    raw_reviews = decoded[0]
    if not isinstance(raw_reviews, list):
        return [], None

    out: list[dict[str, Any]] = []
    for row in raw_reviews:
        mapped = _map_rpc_review(row)
        if mapped is None:
            continue
        out.append(mapped)
        if len(out) >= max(1, limit):
            break

    return out, _extract_rpc_next_token(decoded)


def _extract_rpc_next_token(decoded: list[Any]) -> str | None:
    if len(decoded) >= 2 and isinstance(decoded[1], list):
        tail = decoded[1][-1] if decoded[1] else None
        if isinstance(tail, str) and tail.strip():
            return tail.strip()
    if len(decoded) >= 2 and isinstance(decoded[-2], list):
        tail = decoded[-2][-1] if decoded[-2] else None
        if isinstance(tail, str) and tail.strip():
            return tail.strip()
    return None


def _nested_get(value: object, path: tuple[int, ...]) -> object | None:
    current = value
    for idx in path:
        if not isinstance(current, list) or idx >= len(current):
            return None
        current = current[idx]
    return current


def _timestamp_to_iso(value: object) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    ts = float(value)
    if ts > 10_000_000_000:
        ts /= 1000.0
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _map_rpc_review(row: object) -> dict[str, Any] | None:
    if not isinstance(row, list):
        return None
    review_id = _nested_get(row, (0,))
    text = _nested_get(row, (4,))
    if not isinstance(review_id, str) and not isinstance(text, str):
        return None

    author = _nested_get(row, (1, 0))
    score = _nested_get(row, (2,))
    created_ts = _nested_get(row, (5, 0))
    reply_text = _nested_get(row, (7, 1))
    reply_ts = _nested_get(row, (7, 2, 0))

    mapped: dict[str, Any] = {
        "reviewId": review_id if isinstance(review_id, str) else None,
        "userName": author if isinstance(author, str) else None,
        "content": text if isinstance(text, str) else None,
        "score": score,
        "date": _timestamp_to_iso(created_ts),
    }
    if isinstance(reply_text, str) and reply_text.strip():
        mapped["replyContent"] = reply_text.strip()
    reply_date = _timestamp_to_iso(reply_ts)
    if reply_date:
        mapped["repliedAt"] = reply_date
    return mapped


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
    if isinstance(value, list):
        for entry in value:
            nested = _extract_reply_text(entry)
            if nested:
                return nested
        return None
    if not isinstance(value, dict):
        return None
    for key in (
        "text",
        "content",
        "body",
        "message",
        "reply",
        "response",
        "comment",
        "value",
    ):
        candidate = _as_text(value.get(key))
        if candidate:
            return candidate
    for key in _REPLY_CONTAINER_KEYS:
        nested = _extract_reply_text(value.get(key))
        if nested:
            return nested
    for nested_value in value.values():
        nested = _extract_reply_text(nested_value)
        if nested:
            return nested
    return None


def _extract_reply_author(value: object) -> str | None:
    direct = _as_text(value)
    if direct:
        return direct
    if isinstance(value, list):
        for entry in value:
            nested = _extract_reply_author(entry)
            if nested:
                return nested
        return None
    if not isinstance(value, dict):
        return None
    for key in ("author", "name", "display_name", "developer", "owner", *_REPLY_AUTHOR_KEYS):
        candidate = _as_text(value.get(key))
        if candidate:
            return candidate
    for key in _REPLY_CONTAINER_KEYS:
        nested = _extract_reply_author(value.get(key))
        if nested:
            return nested
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
    if isinstance(value, list):
        for entry in value:
            parsed = _extract_reply_date(entry)
            if parsed:
                return parsed
        return None
    if isinstance(value, dict):
        for key in _REPLY_DATE_KEYS:
            parsed = _extract_reply_date(value.get(key))
            if parsed:
                return parsed
        for key in _REPLY_CONTAINER_KEYS:
            parsed = _extract_reply_date(value.get(key))
            if parsed:
                return parsed
        for nested_value in value.values():
            parsed = _extract_reply_date(nested_value)
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
        if not isinstance(container, (dict, list)):
            continue
        if reply_text is None:
            reply_text = _extract_reply_text(container)
        if reply_author is None:
            reply_author = _extract_reply_author(container)
        if reply_at is None:
            reply_at = _extract_reply_date(container)
    if reply_author is None:
        for key in _REPLY_AUTHOR_KEYS:
            reply_author = _extract_reply_author(review.get(key))
            if reply_author:
                break
    if reply_author is None:
        reply_author = _extract_reply_author(review)
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
        author=review.get("author")
        or review.get("userName")
        or review.get("author_name")
        or review.get("reviewerName"),
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


def _env_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
