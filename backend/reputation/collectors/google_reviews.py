from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import build_url, http_get_json
from reputation.models import ReputationItem

_REPLY_TEXT_KEYS = (
    "reply_text",
    "response_text",
    "owner_response",
    "ownerResponse",
    "response",
    "reply",
)
_REPLY_AUTHOR_KEYS = ("reply_author", "response_author", "owner_name", "ownerName")
_REPLY_DATE_KEYS = ("reply_at", "response_at", "replied_at", "time", "date")
_REPLY_CONTAINER_KEYS = ("reply", "response", "owner_response", "ownerResponse")


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
    for key in ("text", "content", "body", "message", "response", "reply"):
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
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in _REPLY_DATE_KEYS:
            parsed = _extract_reply_date(value.get(key))
            if parsed:
                return parsed
    return None


def _extract_review_reply(review: dict[str, object]) -> dict[str, str | None] | None:
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


class GoogleReviewsCollector(ReputationCollector):
    source_name = "google_reviews"

    def __init__(
        self,
        api_key: str,
        place_id: str,
        max_reviews: int = 200,
    ) -> None:
        self._api_key = api_key
        self._place_id = place_id
        self._max_reviews = max(0, max_reviews)

    def collect(self) -> Iterable[ReputationItem]:
        if not self._api_key or not self._place_id or self._max_reviews <= 0:
            return []

        params = {
            "place_id": self._place_id,
            "fields": "name,reviews",
            "key": self._api_key,
        }
        url = build_url("https://maps.googleapis.com/maps/api/place/details/json", params)
        data = http_get_json(url)
        reviews = data.get("result", {}).get("reviews", [])
        if not reviews:
            return []

        items: list[ReputationItem] = []
        for review in reviews[: self._max_reviews]:
            created_at = None
            if review.get("time"):
                created_at = datetime.fromtimestamp(review["time"], tz=timezone.utc)
            reply = _extract_review_reply(review)
            signals = {
                "rating": review.get("rating"),
                "relative_time": review.get("relative_time_description"),
                "place_id": self._place_id,
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

            items.append(
                ReputationItem(
                    id=str(review.get("time") or review.get("author_name")),
                    source=self.source_name,
                    language=review.get("language"),
                    published_at=created_at,
                    author=review.get("author_name"),
                    url=review.get("author_url"),
                    text=review.get("text"),
                    signals=signals,
                )
            )

        return items
