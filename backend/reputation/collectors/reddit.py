from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import praw

from reputation.collectors.base import ReputationCollector
from reputation.models import ReputationItem


class RedditCollector(ReputationCollector):
    source_name = "reddit"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        subreddits: list[str],
        queries: list[str],
        limit_per_query: int = 100,
        time_filter: str | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._user_agent = user_agent
        self._subreddits = subreddits
        self._queries = queries
        self._limit_per_query = limit_per_query
        self._time_filter = (time_filter or "").strip()

    def collect(self) -> Iterable[ReputationItem]:
        reddit = praw.Reddit(
            client_id=self._client_id,
            client_secret=self._client_secret,
            user_agent=self._user_agent,
        )
        items: list[ReputationItem] = []
        seen: set[str] = set()

        for subreddit in self._subreddits:
            for query in self._queries:
                search_kwargs = {
                    "sort": "new",
                    "limit": self._limit_per_query,
                }
                if self._time_filter:
                    search_kwargs["time_filter"] = self._time_filter
                for submission in reddit.subreddit(subreddit).search(query, **search_kwargs):
                    sid = str(submission.id)
                    if sid in seen:
                        continue
                    seen.add(sid)

                    published = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
                    author = submission.author.name if submission.author else None

                    items.append(
                        ReputationItem(
                            id=sid,
                            source=self.source_name,
                            published_at=published,
                            author=author,
                            url=f"https://www.reddit.com{submission.permalink}",
                            title=submission.title,
                            text=submission.selftext,
                            signals={
                                "score": submission.score,
                                "num_comments": submission.num_comments,
                                "subreddit": subreddit,
                                "query": query,
                            },
                        )
                    )

        return items
