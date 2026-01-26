from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from bbva_bugresolutionradar.domain.enums import Severity, Status

router = APIRouter()


def _matches_q(incident: Dict[str, Any], q: str) -> bool:
    qn = q.strip().lower()
    if not qn:
        return True
    title = str(incident.get("title", "")).lower()
    product = str(incident.get("product", "")).lower()
    feature = str(incident.get("feature", "")).lower()
    gid = str(incident.get("global_id", "")).lower()
    return qn in title or qn in product or qn in feature or qn in gid


@router.get("")
def list_incidents(
    request: Request,
    q: Optional[str] = None,
    status: Optional[Status] = None,
    severity: Optional[Severity] = None,
    opened_from: Optional[date] = None,
    opened_to: Optional[date] = None,
    only_open: bool = False,
    sort: str = Query("updated_desc", pattern=r"^(updated_desc|updated_asc|opened_desc|opened_asc|severity_desc)$"),
    limit: int = Query(200, ge=1, le=5000),
) -> Dict[str, Any]:
    repo = request.app.state.cache_repo
    doc = repo.load()

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

        if q and not _matches_q(row, q):
            continue

        items.append(row)

    def sev_rank(s: str) -> int:
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

    return {"total": total, "items": items}


@router.get("/{global_id}")
def get_incident(request: Request, global_id: str) -> Dict[str, Any]:
    repo = request.app.state.cache_repo
    doc = repo.load()
    rec = doc.incidents.get(global_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    cur = rec.current
    return {
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