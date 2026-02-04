"""Tests de utilidades y endpoints de ingesta."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

from bugresolutionradar.api.routers import ingest as ingest_router


class DummyStats:
    def __init__(self, count: int, note: str | None = None) -> None:
        self.count = count
        self.note = note


class DummyDoc:
    def __init__(self, count: int, note: str | None = None) -> None:
        self.stats = DummyStats(count=count, note=note)
        self.sources_enabled = ["a", "b"]


class DummyService:
    def __init__(self, doc: DummyDoc) -> None:
        self._doc = doc

    def run(self, force: bool, progress: Any | None = None) -> DummyDoc:
        if progress:
            progress("Recoleccion", 55, {"items": 2})
        return self._doc


class DummyAdapter:
    def __init__(self, source_id: str, rows: list[dict[str, Any]]) -> None:
        self._source_id = source_id
        self._rows = rows

    def read(self) -> list[dict[str, Any]]:
        return self._rows

    def source_id(self) -> str:
        return self._source_id


class DummyIngestService:
    def __init__(self, *_: Any, **__: Any) -> None:
        self._adapters = [
            DummyAdapter("src-a", [{"id": 1}, {"id": 2}]),
            DummyAdapter("src-b", [{"id": 3}]),
        ]

    def build_adapters(self) -> list[DummyAdapter]:
        return self._adapters


class DummyCacheDoc:
    def __init__(self, incidents: list[dict[str, Any]]) -> None:
        self.incidents = incidents


class DummyCacheRepo:
    def __init__(self, *_: Any, **__: Any) -> None:
        self.saved: DummyCacheDoc | None = None

    def load(self) -> None:
        return None

    def save(self, doc: DummyCacheDoc) -> None:
        self.saved = doc


class DummyConsolidateService:
    def consolidate_incremental(self, *_: Any, **__: Any) -> DummyCacheDoc:
        return DummyCacheDoc(incidents=[{"id": "inc-1"}, {"id": "inc-2"}])


@pytest.fixture(autouse=True)
def _clear_jobs() -> None:
    ingest_router._JOBS.clear()


def test_job_helpers_and_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest_router, "_MAX_JOBS", 1)

    assert ingest_router._find_active("reputation") is None
    ingest_router._update_job("missing", progress=10)

    first = ingest_router._create_job("reputation")
    second = ingest_router._create_job("reputation")
    assert len(ingest_router._JOBS) == 1
    assert ingest_router._find_active("reputation")

    ingest_router._update_job(second["id"], progress=160, stage="Testing")
    stored = ingest_router._get_job(second["id"])
    assert stored
    assert stored["progress"] == 100
    ingest_router._update_job(second["id"], progress=-5)
    stored = ingest_router._get_job(second["id"])
    assert stored
    assert stored["progress"] == 0

    warning = ingest_router._extract_llm_warning("cache hit; LLM: disabled; other")
    assert warning == "LLM: disabled"
    assert ingest_router._extract_llm_warning(None) is None


def test_run_reputation_job(monkeypatch: pytest.MonkeyPatch) -> None:
    job = ingest_router._create_job("reputation")
    doc = DummyDoc(count=4, note="LLM: disabled")
    monkeypatch.setattr(ingest_router, "ReputationIngestService", lambda: DummyService(doc))

    ingest_router._run_reputation_job(job["id"], force=True)
    stored = ingest_router._get_job(job["id"])
    assert stored
    assert stored["status"] == "success"
    assert stored["meta"]["items"] == 4
    assert stored["meta"]["warning"] == "LLM: disabled"


def test_run_incidents_job(monkeypatch: pytest.MonkeyPatch) -> None:
    job = ingest_router._create_job("incidents")
    repo = DummyCacheRepo()
    monkeypatch.setattr(ingest_router, "CacheRepo", lambda *_: repo)
    monkeypatch.setattr(ingest_router, "IngestService", lambda *_: DummyIngestService())
    monkeypatch.setattr(ingest_router, "ConsolidateService", lambda: DummyConsolidateService())

    ingest_router._run_incidents_job(job["id"])
    stored = ingest_router._get_job(job["id"])
    assert stored
    assert stored["status"] == "success"
    assert stored["meta"]["incidents"] == 2
    assert repo.saved is not None


def test_ingest_job_endpoints() -> None:
    job = ingest_router._create_job("reputation")

    payload = ingest_router.ingest_job(job["id"])
    assert payload["id"] == job["id"]

    jobs = ingest_router.list_jobs()
    assert len(jobs) == 1

    with pytest.raises(HTTPException) as exc:
        ingest_router.ingest_job("missing")
    assert exc.value.status_code == 404


def test_start_reputation_ingest_returns_active(monkeypatch: pytest.MonkeyPatch) -> None:
    job = ingest_router._create_job("reputation")
    ingest_router._update_job(job["id"], status="running")

    def _noop_thread(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(ingest_router.threading, "Thread", _noop_thread)
    active = ingest_router.start_reputation_ingest(force=False)
    assert active["id"] == job["id"]


def test_ingest_reputation_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = DummyDoc(count=1)
    monkeypatch.setattr(ingest_router, "ReputationIngestService", lambda: DummyService(doc))

    class DummyThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            self._target = target
            self._args = args
            self.daemon = daemon

        def start(self) -> None:
            self._target(*self._args)

    monkeypatch.setattr(ingest_router.threading, "Thread", DummyThread)

    payload = ingest_router.ingest_reputation(None)
    assert payload["status"] == "success"
    assert ingest_router._find_active("reputation") is None


def test_ingest_incidents_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(job_id: str) -> None:
        ingest_router._update_job(job_id, status="success", progress=100)

    class DummyThread:
        def __init__(self, target: Any, args: tuple[Any, ...], daemon: bool) -> None:
            self._target = target
            self._args = args
            self.daemon = daemon

        def start(self) -> None:
            self._target(*self._args)

    monkeypatch.setattr(ingest_router, "_run_incidents_job", _fake_run)
    monkeypatch.setattr(ingest_router.threading, "Thread", DummyThread)

    payload = ingest_router.ingest_incidents()
    assert payload["status"] == "success"

    ingest_router._update_job(payload["id"], status="running")
    again = ingest_router.ingest_incidents()
    assert again["id"] == payload["id"]
