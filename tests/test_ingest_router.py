from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

from reputation.api.main import create_app
from reputation.api.routers import ingest as ingest_router


class DummyThread:
    def __init__(self, *, target, args, daemon) -> None:  # type: ignore[no-untyped-def]
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True


def _reset_jobs() -> None:
    ingest_router._JOBS.clear()


def test_create_job_and_find_active() -> None:
    _reset_jobs()
    job = ingest_router._create_job("reputation")
    assert job["status"] == "queued"
    assert job["kind"] == "reputation"

    active = ingest_router._find_active("reputation")
    assert active is not None
    assert active["id"] == job["id"]


def test_update_job_clamps_progress() -> None:
    _reset_jobs()
    job = ingest_router._create_job("reputation")

    ingest_router._update_job(job["id"], progress=120)
    refreshed = ingest_router._get_job(job["id"])
    assert refreshed is not None
    assert refreshed["progress"] == 100

    ingest_router._update_job(job["id"], progress=-5)
    refreshed = ingest_router._get_job(job["id"])
    assert refreshed is not None
    assert refreshed["progress"] == 0


def test_prune_jobs_keeps_recent(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_jobs()
    monkeypatch.setattr(ingest_router, "_MAX_JOBS", 1)

    first = ingest_router._create_job("reputation")
    ingest_router._update_job(first["id"], started_at="2025-01-01T00:00:00Z")

    second = ingest_router._create_job("reputation")
    ingest_router._update_job(second["id"], started_at="2025-01-02T00:00:00Z")

    assert len(ingest_router._JOBS) <= 1
    active = ingest_router._find_active("reputation")
    assert active is not None


def test_ingest_reputation_reuses_active(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_jobs()
    monkeypatch.setattr(ingest_router.threading, "Thread", DummyThread)
    client = TestClient(create_app())

    first = client.post("/ingest/reputation", json={}).json()
    second = client.post("/ingest/reputation", json={}).json()

    assert first["id"] == second["id"]
