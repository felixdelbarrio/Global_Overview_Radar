from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import build_url, http_get_json
from reputation.models import ReputationItem


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

            items.append(
                ReputationItem(
                    id=str(review.get("time") or review.get("author_name")),
                    source=self.source_name,
                    language=review.get("language"),
                    published_at=created_at,
                    author=review.get("author_name"),
                    url=review.get("author_url"),
                    text=review.get("text"),
                    signals={
                        "rating": review.get("rating"),
                        "relative_time": review.get("relative_time_description"),
                        "place_id": self._place_id,
                    },
                )
            )

        return items
