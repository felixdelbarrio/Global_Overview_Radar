from __future__ import annotations

import hashlib
from typing import Any

from bbva_bugresolutionradar.domain.models import (
    IncidentCurrent,
    IncidentHistoryEvent,
    IncidentRecord,
    ObservedIncident,
    SourceRef,
)


def compute_global_id(source_id: str, source_key: str) -> str:
    raw = f"{source_id}:{source_key}".encode()
    return hashlib.sha256(raw).hexdigest()[:24]


def _diff_current(old: IncidentCurrent, new: IncidentCurrent) -> dict[str, Any]:
    diff: dict[str, Any] = {}

    # Compare a curated set of fields (safe and stable for KPIs)
    fields = [
        "title",
        "status",
        "severity",
        "opened_at",
        "closed_at",
        "updated_at",
        "clients_affected",
        "product",
        "feature",
        "resolution_type",
    ]
    for f in fields:
        old_v = getattr(old, f)
        new_v = getattr(new, f)
        if old_v != new_v:
            diff[f] = [old_v, new_v]
    return diff


def merge_observation(
    existing: IncidentRecord | None,
    obs: ObservedIncident,
    global_id: str,
    run_id: str,
) -> IncidentRecord:
    current = IncidentCurrent(
        title=obs.title,
        status=obs.status,
        severity=obs.severity,
        opened_at=obs.opened_at,
        closed_at=obs.closed_at,
        updated_at=obs.updated_at,
        clients_affected=obs.clients_affected,
        product=obs.product,
        feature=obs.feature,
        resolution_type=obs.resolution_type,
    )

    now = obs.observed_at

    if existing is None:
        prov = SourceRef(
            source_id=obs.source_id,
            source_key=obs.source_key,
            first_seen_at=now,
            last_seen_at=now,
        )
        return IncidentRecord(
            global_id=global_id,
            current=current,
            provenance=[prov],
            history=[
                IncidentHistoryEvent(
                    observed_at=now,
                    run_id=run_id,
                    source_id=obs.source_id,
                    diff={"_event": ["NONE", "CREATED"]},
                )
            ],
        )

    # update provenance for source
    updated_prov: list[SourceRef] = []
    found = False
    for p in existing.provenance:
        if p.source_id == obs.source_id and p.source_key == obs.source_key:
            updated_prov.append(
                SourceRef(
                    source_id=p.source_id,
                    source_key=p.source_key,
                    first_seen_at=p.first_seen_at,
                    last_seen_at=now,
                )
            )
            found = True
        else:
            updated_prov.append(p)
    if not found:
        updated_prov.append(
            SourceRef(
                source_id=obs.source_id,
                source_key=obs.source_key,
                first_seen_at=now,
                last_seen_at=now,
            )
        )

    diff = _diff_current(existing.current, current)
    history = list(existing.history)
    if diff:
        history.append(
            IncidentHistoryEvent(
                observed_at=now,
                run_id=run_id,
                source_id=obs.source_id,
                diff=diff,
            )
        )

    return IncidentRecord(
        global_id=existing.global_id,
        current=current,
        provenance=updated_prov,
        history=history,
    )
