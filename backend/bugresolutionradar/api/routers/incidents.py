"""Endpoints de consulta de incidencias."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel

from bugresolutionradar.config import settings
from bugresolutionradar.domain.enums import Severity, Status
from bugresolutionradar.repositories.incidents_overrides_repo import IncidentsOverridesRepo
from bugresolutionradar.user_settings import (
    get_user_settings_snapshot,
    reset_user_settings_to_example,
    update_user_settings,
)
from bugresolutionradar.utils.jira_cookie import JiraCookieError, extract_domain, read_browser_cookie

router = APIRouter()
SETTINGS_BODY = Body(..., description="Actualización de settings para conectores de Bugs")


def _matches_q(incident: Dict[str, Any], q: str) -> bool:
    """Aplica filtro de texto libre sobre campos principales."""
    qn = q.strip().lower()
    if not qn:
        return True
    title = str(incident.get("title", "")).lower()
    product = str(incident.get("product", "")).lower()
    feature = str(incident.get("feature", "")).lower()
    gid = str(incident.get("global_id", "")).lower()
    return qn in title or qn in product or qn in feature or qn in gid


class SettingsUpdate(BaseModel):
    values: dict[str, Any]


class CookieRefreshRequest(BaseModel):
    browser: str | None = None


@router.get("/settings")
def incidents_settings_get() -> dict[str, Any]:
    return get_user_settings_snapshot()


@router.post("/settings")
def incidents_settings_update(payload: SettingsUpdate = SETTINGS_BODY) -> dict[str, Any]:
    try:
        return update_user_settings(payload.values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/settings/reset")
def incidents_settings_reset() -> dict[str, Any]:
    return reset_user_settings_to_example()


@router.post("/settings/jira-cookie/refresh")
def incidents_settings_jira_cookie_refresh(
    payload: CookieRefreshRequest = Body(default=CookieRefreshRequest())
) -> dict[str, Any]:
    try:
        domain = extract_domain(settings.jira_base_url)
        cookie = read_browser_cookie(domain, payload.browser)
        updates = {"jira.session_cookie": cookie, "jira.auth_mode": "cookie"}
        return update_user_settings(updates)
    except JiraCookieError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_incidents(
    request: Request,
    q: Optional[str] = None,
    status: Optional[Status] = None,
    severity: Optional[Severity] = None,
    opened_from: Optional[date] = None,
    opened_to: Optional[date] = None,
    only_open: bool = False,
    sort: str = Query(
        "updated_desc", pattern=r"^(updated_desc|updated_asc|opened_desc|opened_asc|severity_desc)$"
    ),
    limit: int = Query(200, ge=1, le=5000),
) -> Dict[str, Any]:
    """Lista incidencias con filtros, orden y limite."""
    repo = request.app.state.cache_repo
    doc = repo.load()
    overrides = _load_overrides()
    latest_run_at = _latest_run_at(doc)

    items: List[Dict[str, Any]] = []
    for gid, rec in doc.incidents.items():
        cur = rec.current

        if only_open and not cur.is_open:
            continue
        if status is not None and cur.status != status:
            continue
        if severity is not None and cur.severity != severity:
            continue
        if opened_from is not None and (cur.opened_at is None or cur.opened_at < opened_from):
            continue
        if opened_to is not None and (cur.opened_at is None or cur.opened_at > opened_to):
            continue

        row: Dict[str, Any] = {
            "global_id": gid,
            "title": cur.title,
            "status": cur.status.value,
            "severity": cur.severity.value,
            "opened_at": cur.opened_at.isoformat() if cur.opened_at else None,
            "updated_at": cur.updated_at.isoformat() if cur.updated_at else None,
            "closed_at": cur.closed_at.isoformat() if cur.closed_at else None,
            "clients_affected": cur.clients_affected,
            "product": cur.product,
            "feature": cur.feature,
            "resolution_type": cur.resolution_type,
            "sources": len(rec.provenance),
            "history_events": len(rec.history),
        }

        last_seen_at = _last_seen_at(rec)
        if last_seen_at:
            row["last_seen_at"] = last_seen_at.isoformat()
        if latest_run_at:
            row["missing_in_last_ingest"] = bool(last_seen_at and last_seen_at < latest_run_at)

        override = overrides.get(gid)
        if override:
            _apply_override_to_row(row, override)

        if q and not _matches_q(row, q):
            continue

        items.append(row)

    def sev_rank(s: str) -> int:
        """Devuelve el indice de severidad para ordenar."""
        order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
        try:
            return order.index(s)
        except ValueError:
            return len(order)

    if sort == "updated_desc":
        items.sort(key=lambda x: (x["updated_at"] is None, x["updated_at"]), reverse=True)
    elif sort == "updated_asc":
        items.sort(key=lambda x: (x["updated_at"] is None, x["updated_at"]))
    elif sort == "opened_desc":
        items.sort(key=lambda x: (x["opened_at"] is None, x["opened_at"]), reverse=True)
    elif sort == "opened_asc":
        items.sort(key=lambda x: (x["opened_at"] is None, x["opened_at"]))
    elif sort == "severity_desc":
        items.sort(key=lambda x: sev_rank(str(x["severity"])))

    total = len(items)
    items = items[:limit]

    return {
        "generated_at": doc.generated_at.isoformat(),
        "total": total,
        "items": items,
    }


@router.get("/{global_id}")
def get_incident(request: Request, global_id: str) -> Dict[str, Any]:
    """Devuelve detalle completo de una incidencia por global_id."""
    repo = request.app.state.cache_repo
    doc = repo.load()
    rec = doc.incidents.get(global_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    overrides = _load_overrides()
    override = overrides.get(global_id)
    latest_run_at = _latest_run_at(doc)
    last_seen_at = _last_seen_at(rec)

    cur = rec.current
    payload: Dict[str, Any] = {
        "global_id": rec.global_id,
        "current": {
            "title": cur.title,
            "status": cur.status.value,
            "severity": cur.severity.value,
            "opened_at": cur.opened_at.isoformat() if cur.opened_at else None,
            "updated_at": cur.updated_at.isoformat() if cur.updated_at else None,
            "closed_at": cur.closed_at.isoformat() if cur.closed_at else None,
            "clients_affected": cur.clients_affected,
            "product": cur.product,
            "feature": cur.feature,
            "resolution_type": cur.resolution_type,
        },
        "provenance": [
            {
                "source_id": p.source_id,
                "source_key": p.source_key,
                "first_seen_at": p.first_seen_at.isoformat(),
                "last_seen_at": p.last_seen_at.isoformat(),
            }
            for p in rec.provenance
        ],
        "history": [
            {
                "observed_at": h.observed_at.isoformat(),
                "run_id": h.run_id,
                "source_id": h.source_id,
                "diff": h.diff,
            }
            for h in rec.history
        ],
    }
    if last_seen_at:
        payload["last_seen_at"] = last_seen_at.isoformat()
    if latest_run_at:
        payload["missing_in_last_ingest"] = bool(last_seen_at and last_seen_at < latest_run_at)
    if override:
        _apply_override_to_detail(payload, override)
    return payload


class IncidentOverrideRequest(BaseModel):
    ids: List[str]
    status: Status | None = None
    severity: Severity | None = None
    note: str | None = None


@router.post("/override")
def incident_override(payload: IncidentOverrideRequest) -> Dict[str, Any]:
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids is required")
    if payload.status is None and payload.severity is None and payload.note is None:
        raise HTTPException(status_code=400, detail="status, severity or note is required")

    repo = IncidentsOverridesRepo(Path(settings.incidents_overrides_path))
    overrides = repo.load()
    now = datetime.now(timezone.utc).isoformat()

    for incident_id in payload.ids:
        entry: Dict[str, Any] = overrides.get(incident_id, {})
        if payload.status is not None:
            entry["status"] = payload.status.value
        if payload.severity is not None:
            entry["severity"] = payload.severity.value
        if payload.note is not None:
            entry["note"] = payload.note
        entry["updated_at"] = now
        overrides[incident_id] = entry

    repo.save(overrides)
    return {"updated": len(payload.ids)}


def _load_overrides() -> Dict[str, Dict[str, Any]]:
    repo = IncidentsOverridesRepo(Path(settings.incidents_overrides_path))
    return repo.load()


def _apply_override_to_row(row: Dict[str, Any], override: Dict[str, Any]) -> None:
    status = override.get("status")
    severity = override.get("severity")
    if isinstance(status, str) and status:
        row["status"] = status
    if isinstance(severity, str) and severity:
        row["severity"] = severity
    row["manual_override"] = override


def _apply_override_to_detail(payload: Dict[str, Any], override: Dict[str, Any]) -> None:
    current = payload.get("current")
    if isinstance(current, dict):
        status = override.get("status")
        severity = override.get("severity")
        if isinstance(status, str) and status:
            current["status"] = status
        if isinstance(severity, str) and severity:
            current["severity"] = severity
    payload["manual_override"] = override


def _latest_run_at(doc: Any) -> datetime | None:
    runs = getattr(doc, "runs", None)
    if not runs:
        return None
    latest: datetime | None = None
    for run in runs:
        ts = getattr(run, "started_at", None)
        if ts and (latest is None or ts > latest):
            latest = ts
    return latest


def _last_seen_at(rec: Any) -> datetime | None:
    provenance = getattr(rec, "provenance", None)
    if not provenance:
        return None
    latest: datetime | None = None
    for ref in provenance:
        ts = getattr(ref, "last_seen_at", None)
        if ts and (latest is None or ts > latest):
            latest = ts
    return latest
