from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from reputation.auth import require_google_user, require_mutation_access
from reputation.config import (
    REPO_ROOT,
    compute_config_hash,
    load_business_config,
    reload_reputation_settings,
    settings,
)
from reputation.models import ReputationCacheDocument, ReputationCacheStats
from reputation.repositories.cache_repo import ReputationCacheRepo
from reputation.services.ingest_service import ReputationIngestService
from reputation.state_store import state_store_enabled, sync_from_state, sync_to_state


def _refresh_settings() -> None:
    reload_reputation_settings()


router = APIRouter(dependencies=[Depends(_refresh_settings), Depends(require_google_user)])

_INGEST_JOBS: dict[str, dict[str, Any]] = {}
_INGEST_LOCK = Lock()
_INGEST_JOBS_STATE_PATH = REPO_ROOT / "data" / "cache" / "reputation_ingest_jobs.json"
_INGEST_JOBS_STATE_KEY = "data/cache/reputation_ingest_jobs.json"
_MAX_INGEST_JOBS = 240
_INGEST_PROGRESS_PERSIST_EVERY_SEC = 4.0
_INGEST_PROGRESS_PERSIST_DELTA = 10
_INGEST_LAST_PERSIST_AT_MONO: dict[str, float] = {}
_INGEST_LAST_PERSIST_PROGRESS: dict[str, int] = {}
_INGEST_LAST_PERSIST_STAGE: dict[str, str] = {}

logger = logging.getLogger(__name__)


class IngestRequest(BaseModel):
    force: bool | None = None
    all_sources: bool | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_timestamp(job: dict[str, Any]) -> str:
    for key in ("updated_at", "finished_at", "started_at"):
        value = job.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _job_is_newer(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _job_timestamp(left) >= _job_timestamp(right)


def _read_jobs_from_state() -> dict[str, dict[str, Any]]:
    if state_store_enabled():
        sync_from_state(
            _INGEST_JOBS_STATE_PATH,
            key=_INGEST_JOBS_STATE_KEY,
            repo_root=REPO_ROOT,
        )
    if not _INGEST_JOBS_STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(_INGEST_JOBS_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to parse ingest jobs state at %s", _INGEST_JOBS_STATE_PATH)
        return {}
    if isinstance(payload, dict):
        raw_jobs = payload.get("jobs")
        if isinstance(raw_jobs, dict):
            return {
                str(job_id): dict(job_data)
                for job_id, job_data in raw_jobs.items()
                if isinstance(job_id, str) and isinstance(job_data, dict)
            }
        return {
            str(job_id): dict(job_data)
            for job_id, job_data in payload.items()
            if isinstance(job_id, str) and isinstance(job_data, dict)
        }
    return {}


def _write_jobs_to_state(jobs: dict[str, dict[str, Any]]) -> None:
    _INGEST_JOBS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": _now_iso(), "jobs": jobs}
    tmp_path = Path(f"{_INGEST_JOBS_STATE_PATH}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(_INGEST_JOBS_STATE_PATH)
    if state_store_enabled():
        sync_to_state(
            _INGEST_JOBS_STATE_PATH,
            key=_INGEST_JOBS_STATE_KEY,
            repo_root=REPO_ROOT,
        )


def _prune_jobs_locked() -> None:
    if len(_INGEST_JOBS) <= _MAX_INGEST_JOBS:
        return
    ordered = sorted(
        _INGEST_JOBS.items(),
        key=lambda pair: _job_timestamp(pair[1]),
        reverse=True,
    )
    keep_ids = {job_id for job_id, _ in ordered[:_MAX_INGEST_JOBS]}
    for job_id in list(_INGEST_JOBS):
        if job_id not in keep_ids:
            _INGEST_JOBS.pop(job_id, None)
            _INGEST_LAST_PERSIST_AT_MONO.pop(job_id, None)
            _INGEST_LAST_PERSIST_PROGRESS.pop(job_id, None)
            _INGEST_LAST_PERSIST_STAGE.pop(job_id, None)


def _mark_persisted_locked(job: dict[str, Any]) -> None:
    job_id = str(job.get("id") or "")
    if not job_id:
        return
    _INGEST_LAST_PERSIST_AT_MONO[job_id] = time.monotonic()
    _INGEST_LAST_PERSIST_PROGRESS[job_id] = int(job.get("progress") or 0)
    _INGEST_LAST_PERSIST_STAGE[job_id] = str(job.get("stage") or "")


def _should_persist_job_update_locked(
    job: dict[str, Any],
    *,
    previous_status: str,
) -> bool:
    status = str(job.get("status") or "")
    if status in {"queued", "success", "error"}:
        return True
    if status != previous_status:
        return True

    job_id = str(job.get("id") or "")
    if not job_id:
        return False

    last_persist = _INGEST_LAST_PERSIST_AT_MONO.get(job_id)
    if last_persist is None:
        return True

    progress = int(job.get("progress") or 0)
    stage = str(job.get("stage") or "")
    if stage != _INGEST_LAST_PERSIST_STAGE.get(job_id, ""):
        return True
    if abs(progress - _INGEST_LAST_PERSIST_PROGRESS.get(job_id, progress)) >= (
        _INGEST_PROGRESS_PERSIST_DELTA
    ):
        return True
    return (time.monotonic() - last_persist) >= _INGEST_PROGRESS_PERSIST_EVERY_SEC


def _sync_jobs_from_state_locked() -> None:
    jobs_from_state = _read_jobs_from_state()
    if not jobs_from_state:
        return
    for job_id, incoming in jobs_from_state.items():
        current = _INGEST_JOBS.get(job_id)
        if current is None or _job_is_newer(incoming, current):
            _INGEST_JOBS[job_id] = incoming


def _persist_jobs_locked(*, merge_remote: bool = False) -> None:
    # Merge before persist only when needed (job creation) to avoid extra
    # remote reads on every progress update.
    if merge_remote:
        _sync_jobs_from_state_locked()
    _prune_jobs_locked()
    _write_jobs_to_state(_INGEST_JOBS)


def _record_job(job: dict[str, Any]) -> dict[str, Any]:
    with _INGEST_LOCK:
        job_copy = {**job, "updated_at": _now_iso()}
        _INGEST_JOBS[job_copy["id"]] = job_copy
        _persist_jobs_locked(merge_remote=True)
        _mark_persisted_locked(job_copy)
    return job_copy


def _update_job(job_id: str, **fields: Any) -> None:
    with _INGEST_LOCK:
        job = _INGEST_JOBS.get(job_id)
        if job is None:
            # Fallback para procesos reciclados: intenta recuperar el estado remoto una vez.
            _sync_jobs_from_state_locked()
            job = _INGEST_JOBS.get(job_id)
        if not job:
            return
        previous_status = str(job.get("status") or "")
        job.update(fields)
        job["updated_at"] = _now_iso()
        if _should_persist_job_update_locked(job, previous_status=previous_status):
            _persist_jobs_locked()
            _mark_persisted_locked(job)


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
def ingest_reputation(
    payload: IngestRequest,
    _: None = Depends(require_mutation_access),
) -> dict[str, Any]:
    force = bool(payload.force)
    all_sources = bool(payload.all_sources)
    with _INGEST_LOCK:
        _sync_jobs_from_state_locked()
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
        _sync_jobs_from_state_locked()
        job = _INGEST_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job
