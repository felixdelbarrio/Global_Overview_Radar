"""Endpoints para disparar ingestas desde el frontend."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field
from reputation.services import ReputationIngestService

from bugresolutionradar.config import settings
from bugresolutionradar.domain.models import RunSource
from bugresolutionradar.logging_utils import get_logger
from bugresolutionradar.repositories import CacheRepo
from bugresolutionradar.services import ConsolidateService, IngestService

router = APIRouter()
logger = get_logger(__name__)

IngestKind = Literal["reputation", "incidents"]
IngestStatus = Literal["queued", "running", "success", "error"]


class IngestRequest(BaseModel):
    force: bool = Field(default=False, description="Forzar ingesta (ignora cache)")


class IngestJob(BaseModel):
    id: str
    kind: IngestKind
    status: IngestStatus
    progress: int
    stage: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_MAX_JOBS = 50
_INGEST_BODY = Body(default=None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prune_jobs() -> None:
    with _LOCK:
        if len(_JOBS) <= _MAX_JOBS:
            return
        ordered = sorted(
            _JOBS.items(),
            key=lambda pair: pair[1].get("finished_at") or pair[1].get("started_at") or "",
        )
        for job_id, _ in ordered[: max(0, len(_JOBS) - _MAX_JOBS)]:
            _JOBS.pop(job_id, None)


def _create_job(kind: IngestKind) -> dict[str, Any]:
    job_id = str(uuid4())
    job: dict[str, Any] = {
        "id": job_id,
        "kind": kind,
        "status": "queued",
        "progress": 0,
        "stage": "En cola",
        "started_at": None,
        "finished_at": None,
        "error": None,
        "meta": {},
    }
    with _LOCK:
        _JOBS[job_id] = job
    _prune_jobs()
    return job


def _find_active(kind: IngestKind) -> dict[str, Any] | None:
    with _LOCK:
        for job in _JOBS.values():
            if job["kind"] == kind and job["status"] in {"queued", "running"}:
                return dict(job)
    return None


def _get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def _update_job(job_id: str, **fields: Any) -> None:
    with _LOCK:
        if job_id not in _JOBS:
            return
        if "progress" in fields:
            fields["progress"] = max(0, min(100, int(fields["progress"])))
        _JOBS[job_id].update(fields)


def _run_reputation_job(job_id: str, force: bool) -> None:
    _update_job(
        job_id, status="running", stage="Arrancando motores", progress=2, started_at=_now_iso()
    )
    try:
        service = ReputationIngestService()

        def on_progress(stage: str, pct: int, meta: dict[str, Any] | None = None) -> None:
            _update_job(job_id, stage=stage, progress=pct, meta=meta or {})

        doc = service.run(force=force, progress=on_progress)
        warning = _extract_llm_warning(doc.stats.note)
        _update_job(
            job_id,
            status="success",
            stage="Ingesta completada",
            progress=100,
            finished_at=_now_iso(),
            meta={
                "items": doc.stats.count,
                "sources": len(doc.sources_enabled),
                "note": doc.stats.note,
                "warning": warning,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Reputation ingest failed")
        _update_job(
            job_id,
            status="error",
            stage="Error en ingesta",
            progress=100,
            finished_at=_now_iso(),
            error=str(exc),
        )


def _run_incidents_job(job_id: str) -> None:
    _update_job(
        job_id, status="running", stage="Preparando fuentes", progress=5, started_at=_now_iso()
    )
    try:
        repo = CacheRepo(settings.cache_path)
        ingest_service = IngestService(settings)
        consolidate_service = ConsolidateService()

        adapters = ingest_service.build_adapters()
        total = len(adapters)
        _update_job(job_id, stage="Leyendo fuentes", progress=10, meta={"sources": total})

        observations = []
        for idx, adapter in enumerate(adapters, start=1):
            observations.extend(adapter.read())
            pct = 10 + int(40 * (idx / max(total, 1)))
            _update_job(
                job_id,
                stage=f"Leyendo {adapter.source_id()}",
                progress=pct,
                meta={"sources": total, "observations": len(observations)},
            )

        _update_job(
            job_id,
            stage="Consolidando incidencias",
            progress=60,
            meta={"observations": len(observations)},
        )

        asset = str(Path(settings.assets_dir).resolve())
        sources = [
            RunSource(
                source_id=adapter.source_id(),
                asset=asset,
                fingerprint=None,
            )
            for adapter in adapters
        ]
        existing = repo.load()
        cache_doc = consolidate_service.consolidate_incremental(existing, observations, sources)

        _update_job(
            job_id,
            stage="Guardando cache",
            progress=85,
            meta={
                "observations": len(observations),
                "incidents": len(cache_doc.incidents),
                "sources": len(sources),
            },
        )
        repo.save(cache_doc)

        _update_job(
            job_id,
            status="success",
            stage="Ingesta completada",
            progress=100,
            finished_at=_now_iso(),
            meta={
                "observations": len(observations),
                "incidents": len(cache_doc.incidents),
                "sources": len(sources),
            },
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Incidents ingest failed")
        _update_job(
            job_id,
            status="error",
            stage="Error en ingesta",
            progress=100,
            finished_at=_now_iso(),
            error=str(exc),
        )


def start_reputation_ingest(force: bool) -> dict[str, Any]:
    active = _find_active("reputation")
    if active:
        return active
    job = _create_job("reputation")
    thread = threading.Thread(
        target=_run_reputation_job,
        args=(job["id"], force),
        daemon=True,
    )
    thread.start()
    return job


@router.post("/reputation", response_model=IngestJob)
def ingest_reputation(
    payload: IngestRequest | None = _INGEST_BODY,
) -> dict[str, Any]:
    payload = payload or IngestRequest()
    return start_reputation_ingest(payload.force)


@router.post("/incidents", response_model=IngestJob)
def ingest_incidents() -> dict[str, Any]:
    active = _find_active("incidents")
    if active:
        return active
    job = _create_job("incidents")
    thread = threading.Thread(
        target=_run_incidents_job,
        args=(job["id"],),
        daemon=True,
    )
    thread.start()
    return job


@router.get("/jobs/{job_id}", response_model=IngestJob)
def ingest_job(job_id: str) -> dict[str, Any]:
    job = _get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.get("/jobs", response_model=list[IngestJob])
def list_jobs() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(job) for job in _JOBS.values()]


def _extract_llm_warning(note: str | None) -> str | None:
    if not note:
        return None
    for chunk in note.split(";"):
        cleaned = chunk.strip()
        if cleaned.lower().startswith("llm:"):
            return cleaned
    return None
