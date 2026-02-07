from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from reputation.auth import require_google_user
from reputation.config import (
    compute_config_hash,
    load_business_config,
    reload_reputation_settings,
    settings,
)
from reputation.models import ReputationCacheDocument, ReputationCacheStats
from reputation.repositories.cache_repo import ReputationCacheRepo
from reputation.services.ingest_service import ReputationIngestService


def _refresh_settings() -> None:
    reload_reputation_settings()


router = APIRouter(dependencies=[Depends(_refresh_settings), Depends(require_google_user)])

_INGEST_JOBS: dict[str, dict[str, Any]] = {}
_INGEST_LOCK = Lock()


class IngestRequest(BaseModel):
    force: bool | None = None
    all_sources: bool | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_job(job: dict[str, Any]) -> dict[str, Any]:
    with _INGEST_LOCK:
        _INGEST_JOBS[job["id"]] = job
    return job


def _update_job(job_id: str, **fields: Any) -> None:
    with _INGEST_LOCK:
        job = _INGEST_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)


def _find_active_job(kind: str) -> dict[str, Any] | None:
    for job in _INGEST_JOBS.values():
        if job.get("kind") != kind:
            continue
        if job.get("status") in {"queued", "running"}:
            return job
    return None


def _seed_reputation_cache() -> None:
    repo = ReputationCacheRepo(settings.cache_path)
    if repo.load() is not None:
        return
    try:
        cfg = load_business_config()
        cfg_hash = compute_config_hash(cfg)
    except Exception:
        cfg_hash = "empty"
    doc = ReputationCacheDocument(
        generated_at=datetime.now(timezone.utc),
        config_hash=cfg_hash or "empty",
        sources_enabled=settings.enabled_sources(),
        items=[],
        market_ratings=[],
        market_ratings_history=[],
        stats=ReputationCacheStats(count=0, note="cache seeded"),
    )
    repo.save(doc)


def _run_reputation_job(job_id: str, force: bool, all_sources: bool) -> None:
    try:
        _update_job(job_id, status="running", progress=2, stage="starting")
        service = ReputationIngestService()

        def _progress(stage: str, pct: int, meta: dict[str, Any] | None) -> None:
            _update_job(
                job_id,
                status="running",
                progress=pct,
                stage=stage,
                meta=meta or {},
            )

        sources_override = settings.all_sources() if all_sources else None
        doc = service.run(force=force, progress=_progress, sources_override=sources_override)
        _update_job(
            job_id,
            status="success",
            progress=100,
            stage="completed",
            finished_at=_now_iso(),
            meta={
                "items": doc.stats.count,
                "generated_at": doc.generated_at.isoformat(),
                "sources_enabled": doc.sources_enabled,
            },
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="error",
            progress=100,
            stage="error",
            finished_at=_now_iso(),
            error=str(exc),
        )


@router.post("/reputation")
def ingest_reputation(payload: IngestRequest) -> dict[str, Any]:
    force = bool(payload.force)
    all_sources = bool(payload.all_sources)
    with _INGEST_LOCK:
        active = _find_active_job("reputation")
        if active:
            meta = active.get("meta")
            if not isinstance(meta, dict):
                meta = {}
            meta.setdefault("note", "ingest already running")
            active["meta"] = meta
            return dict(active)
    job_id = uuid4().hex
    job = {
        "id": job_id,
        "kind": "reputation",
        "status": "queued",
        "progress": 0,
        "stage": "queued",
        "started_at": _now_iso(),
        "meta": {"force": force, "all_sources": all_sources},
    }
    _record_job(job)
    try:
        _seed_reputation_cache()
    except Exception as exc:
        job.update(
            {
                "status": "error",
                "progress": 100,
                "stage": "error",
                "finished_at": _now_iso(),
                "error": str(exc),
            }
        )
        return _record_job(job)

    worker = Thread(target=_run_reputation_job, args=(job_id, force, all_sources), daemon=True)
    worker.start()
    return job


@router.get("/jobs/{job_id}")
def ingest_job(job_id: str) -> dict[str, Any]:
    with _INGEST_LOCK:
        job = _INGEST_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job
