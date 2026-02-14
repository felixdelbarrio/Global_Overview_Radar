from __future__ import annotations

import time
from typing import Iterable

from reputation.collectors.base import ReputationCollector
from reputation.models import ReputationItem
from reputation.services.ingest_service import ReputationIngestService


class _SlowCollector(ReputationCollector):
    source_name = "google_play"

    def collect(self) -> Iterable[ReputationItem]:
        while True:
            time.sleep(0.2)


class _FastCollector(ReputationCollector):
    source_name = "news"

    def collect(self) -> Iterable[ReputationItem]:
        return [ReputationItem(id="news:1", source="news", text="ok")]


def test_collector_batch_with_timeout_raises_timeout() -> None:
    collector = _SlowCollector()

    started = time.perf_counter()
    try:
        ReputationIngestService._collector_batch_with_timeout(collector, timeout_sec=1)
    except TimeoutError as exc:
        elapsed = time.perf_counter() - started
        assert "timeout after 1s" in str(exc)
        assert elapsed < 2.2
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected TimeoutError")


def test_collect_items_continues_when_one_collector_times_out(monkeypatch) -> None:
    monkeypatch.setenv("REPUTATION_COLLECTOR_WORKERS", "2")
    monkeypatch.setenv("REPUTATION_COLLECTOR_TIMEOUT_SEC", "1")
    monkeypatch.setenv("REPUTATION_COLLECTOR_SLOW_SEC", "0")

    notes: list[str] = []
    progress_updates: list[tuple[int, int, str]] = []

    items = ReputationIngestService._collect_items(
        [_SlowCollector(), _FastCollector()],
        notes,
        progress=lambda done, total, source: progress_updates.append(
            (done, total, source)
        ),
    )

    assert len(items) == 1
    assert items[0].source == "news"
    assert any("google_play: error timeout after 1s" in note for note in notes)
    assert any(update[2] == "google_play" for update in progress_updates)
    assert progress_updates[-1][0] == 2
    assert progress_updates[-1][1] == 2
