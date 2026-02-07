from __future__ import annotations

from typing import Iterable

from reputation.collectors.base import ReputationCollector
from reputation.collectors.utils import build_url, http_get_json, parse_datetime
from reputation.models import ReputationItem


class TwitterCollector(ReputationCollector):
    source_name = "twitter"

    def __init__(
        self,
        bearer_token: str,
        queries: list[str],
        max_results: int = 100,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> None:
        self._bearer_token = bearer_token
        self._queries = queries
        self._max_results = max(0, max_results)
        self._start_time = (start_time or "").strip()
        self._end_time = (end_time or "").strip()

    def collect(self) -> Iterable[ReputationItem]:
        if not self._bearer_token or not self._queries or self._max_results <= 0:
            return []

        items: list[ReputationItem] = []
        for query in self._queries:
            items.extend(self._collect_query(query))
            if len(items) >= self._max_results:
                break
        return items[: self._max_results]

    def _collect_query(self, query: str) -> list[ReputationItem]:
        collected: list[ReputationItem] = []
        next_token: str | None = None

        while len(collected) < self._max_results:
            remaining = self._max_results - len(collected)
            page_size = min(100, max(10, remaining))

            params = {
                "query": query,
                "max_results": page_size,
                "tweet.fields": "created_at,lang,author_id",
                "expansions": "author_id",
                "user.fields": "username",
                "next_token": next_token,
            }
            if self._start_time:
                params["start_time"] = self._start_time
            if self._end_time:
                params["end_time"] = self._end_time
            url = build_url("https://api.twitter.com/2/tweets/search/recent", params)
            data = http_get_json(url, headers={"Authorization": f"Bearer {self._bearer_token}"})

            users = {u["id"]: u.get("username") for u in data.get("includes", {}).get("users", [])}
            tweets = data.get("data", [])
            if not tweets:
                break

            for tweet in tweets:
                created_at = parse_datetime(tweet.get("created_at"))
                author_id = tweet.get("author_id")
                author = users.get(author_id)

                collected.append(
                    ReputationItem(
                        id=str(tweet.get("id")),
                        source=self.source_name,
                        language=tweet.get("lang"),
                        published_at=created_at,
                        author=author or author_id,
                        url=f"https://twitter.com/i/web/status/{tweet.get('id')}",
                        text=tweet.get("text"),
                        signals={"query": query},
                    )
                )

            next_token = data.get("meta", {}).get("next_token")
            if not next_token:
                break

        return collected
