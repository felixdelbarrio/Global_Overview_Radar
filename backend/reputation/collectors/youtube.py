from __future__ import annotations

from typing import Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import build_url, http_get_json, parse_datetime
from reputation.models import ReputationItem


class YouTubeCollector(ReputationCollector):
    source_name = "youtube"

    def __init__(
        self,
        api_key: str,
        queries: list[str],
        max_results: int = 50,
    ) -> None:
        self._api_key = api_key
        self._queries = queries
        self._max_results = max(0, max_results)

    def collect(self) -> Iterable[ReputationItem]:
        if not self._api_key or not self._queries or self._max_results <= 0:
            return []

        items: list[ReputationItem] = []
        for query in self._queries:
            items.extend(self._collect_query(query))
            if len(items) >= self._max_results:
                break
        return items[: self._max_results]

    def _collect_query(self, query: str) -> list[ReputationItem]:
        collected: list[ReputationItem] = []
        page_token: str | None = None

        while len(collected) < self._max_results:
            remaining = self._max_results - len(collected)
            page_size = min(50, max(5, remaining))

            params = {
                "part": "snippet",
                "type": "video",
                "q": query,
                "maxResults": page_size,
                "key": self._api_key,
                "pageToken": page_token,
            }
            url = build_url("https://www.googleapis.com/youtube/v3/search", params)
            data = http_get_json(url)
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId")
                if not video_id:
                    continue

                collected.append(
                    ReputationItem(
                        id=video_id,
                        source=self.source_name,
                        published_at=parse_datetime(snippet.get("publishedAt")),
                        author=snippet.get("channelTitle"),
                        url=f"https://www.youtube.com/watch?v={video_id}",
                        title=snippet.get("title"),
                        text=snippet.get("description"),
                        signals={"query": query, "channel_id": snippet.get("channelId")},
                    )
                )

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return collected
