from __future__ import annotations

from fastapi.testclient import TestClient

from reputation.api.main import create_app


def _build_client(monkeypatch, tmp_path):  # type: ignore[no-untyped-def]
    import reputation.config as rep_config
    from reputation.api.routers import ingest as ingest_router

    monkeypatch.setattr(rep_config.settings, "google_cloud_login_requested", False)
    monkeypatch.delenv("REPUTATION_STATE_BUCKET", raising=False)
    monkeypatch.setattr(
        ingest_router,
        "_INGEST_JOBS_STATE_PATH",
        tmp_path / "reputation_ingest_jobs.json",
    )
    monkeypatch.setattr(
        ingest_router,
        "_INGEST_JOBS_STATE_KEY",
        "tests/reputation_ingest_jobs.json",
    )
    with ingest_router._INGEST_LOCK:
        ingest_router._INGEST_JOBS.clear()

    app = create_app()
    app.dependency_overrides[ingest_router._refresh_settings] = lambda: None
    return TestClient(app), ingest_router


def test_ingest_job_is_loaded_from_persisted_state(
    monkeypatch,  # type: ignore[no-untyped-def]
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    client, ingest_router = _build_client(monkeypatch, tmp_path)
    ingest_router._record_job(
        {
            "id": "job-1",
            "kind": "reputation",
            "status": "running",
            "progress": 42,
            "stage": "collecting",
            "started_at": "2026-02-13T10:00:00+00:00",
            "meta": {"force": False, "all_sources": False},
        }
    )
    with ingest_router._INGEST_LOCK:
        ingest_router._INGEST_JOBS.clear()

    res = client.get("/ingest/jobs/job-1")

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "job-1"
    assert body["status"] == "running"
    assert body["progress"] == 42


def test_ingest_reuses_active_job_from_persisted_state(
    monkeypatch,  # type: ignore[no-untyped-def]
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    client, ingest_router = _build_client(monkeypatch, tmp_path)
    existing = ingest_router._record_job(
        {
            "id": "job-active",
            "kind": "reputation",
            "status": "running",
            "progress": 55,
            "stage": "classifying",
            "started_at": "2026-02-13T10:10:00+00:00",
            "meta": {"force": False, "all_sources": False},
        }
    )
    with ingest_router._INGEST_LOCK:
        ingest_router._INGEST_JOBS.clear()

    res = client.post("/ingest/reputation", json={"force": False, "all_sources": False})

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == existing["id"]
    assert body["status"] == "running"
