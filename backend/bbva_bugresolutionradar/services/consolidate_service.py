from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from bbva_bugresolutionradar.domain.models import (
    CacheDocument,
    IncidentCurrent,
    IncidentHistoryEvent,
    IncidentRecord,
    ObservedIncident,
    RunInfo,
    RunSource,
    SourceRef,
)


class ConsolidateService:
    """
    Consolidación simple:
    - global_id = f"{source_id}:{source_key}" (por ahora)
    - si existe, actualiza current y añade evento de history si cambia algo relevante
    - provenance por source_id/source_key con first_seen_at/last_seen_at
    - añade RunInfo con run_id y sources
    """

    def __init__(self) -> None:
        pass

    def consolidate(
        self, observations: List[ObservedIncident], sources: List[RunSource]
    ) -> CacheDocument:
        now = datetime.now(timezone.utc).astimezone()
        run_id = now.strftime("%Y%m%dT%H%M%S%z")

        doc = CacheDocument(
            generated_at=now,
            runs=[],
            incidents={},
        )

        # registrar la ejecución
        doc.runs.append(
            RunInfo(
                run_id=run_id,
                started_at=now,
                sources=sources,
            )
        )

        # consolidar observaciones
        for obs in observations:
            global_id = f"{obs.source_id}:{obs.source_key}"

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

            if global_id not in doc.incidents:
                rec = IncidentRecord(
                    global_id=global_id,
                    current=current,
                    provenance=[
                        SourceRef(
                            source_id=obs.source_id,
                            source_key=obs.source_key,
                            first_seen_at=obs.observed_at,
                            last_seen_at=obs.observed_at,
                        )
                    ],
                    history=[],
                )
                doc.incidents[global_id] = rec
                continue

            rec = doc.incidents[global_id]

            # actualizar provenance
            _touch_provenance(rec, obs)

            # diff simple de campos clave
            diff: Dict[str, object] = {}
            if rec.current.status != current.status:
                diff["status"] = {"from": rec.current.status, "to": current.status}
            if rec.current.severity != current.severity:
                diff["severity"] = {"from": rec.current.severity, "to": current.severity}
            if rec.current.title != current.title and current.title:
                diff["title"] = {"from": rec.current.title, "to": current.title}
            if rec.current.opened_at != current.opened_at:
                diff["opened_at"] = {"from": rec.current.opened_at, "to": current.opened_at}
            if rec.current.closed_at != current.closed_at:
                diff["closed_at"] = {"from": rec.current.closed_at, "to": current.closed_at}
            if rec.current.updated_at != current.updated_at:
                diff["updated_at"] = {"from": rec.current.updated_at, "to": current.updated_at}

            # aplicar current (siempre)
            rec.current = current

            # registrar history si hubo cambios
            if diff:
                rec.history.append(
                    IncidentHistoryEvent(
                        observed_at=obs.observed_at,
                        run_id=run_id,
                        source_id=obs.source_id,
                        diff=diff,
                    )
                )

        return doc


def _touch_provenance(rec: IncidentRecord, obs: ObservedIncident) -> None:
    for p in rec.provenance:
        if p.source_id == obs.source_id and p.source_key == obs.source_key:
            p.last_seen_at = obs.observed_at
            return
    rec.provenance.append(
        SourceRef(
            source_id=obs.source_id,
            source_key=obs.source_key,
            first_seen_at=obs.observed_at,
            last_seen_at=obs.observed_at,
        )
    )
