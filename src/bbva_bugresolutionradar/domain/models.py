from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from bbva_bugresolutionradar.domain.enums import Severity, Status


class SourceRef(BaseModel):
    source_id: str
    source_key: str
    first_seen_at: datetime
    last_seen_at: datetime


class IncidentCurrent(BaseModel):
    title: str
    status: Status
    severity: Severity

    opened_at: Optional[date] = None
    closed_at: Optional[date] = None
    updated_at: Optional[date] = None

    clients_affected: Optional[int] = None
    product: Optional[str] = None
    feature: Optional[str] = None
    resolution_type: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.status in {Status.OPEN, Status.IN_PROGRESS, Status.BLOCKED}

    def is_master(self, threshold: int) -> bool:
        if self.clients_affected is None:
            return False
        return self.clients_affected > threshold


class IncidentHistoryEvent(BaseModel):
    observed_at: datetime
    run_id: str
    source_id: str
    diff: Dict[str, Any] = Field(default_factory=dict)


class IncidentRecord(BaseModel):
    global_id: str
    current: IncidentCurrent
    provenance: List[SourceRef] = Field(default_factory=lambda: cast(List[SourceRef], []))
    history: List[IncidentHistoryEvent] = Field(
        default_factory=lambda: cast(List[IncidentHistoryEvent], [])
    )


class RunSource(BaseModel):
    source_id: str
    asset: str
    fingerprint: Optional[str] = None


class RunInfo(BaseModel):
    run_id: str
    started_at: datetime
    sources: List[RunSource]


class CacheDocument(BaseModel):
    schema_version: str = "1.0"
    generated_at: datetime
    runs: List[RunInfo] = Field(default_factory=lambda: cast(List[RunInfo], []))
    incidents: Dict[str, IncidentRecord] = Field(default_factory=dict)


class ObservedIncident(BaseModel):
    """
    Canonical observation from an adapter: one record from one source.
    global_id is computed by services, but adapters must provide source_id/source_key.
    """

    source_id: str
    source_key: str
    observed_at: datetime

    title: str
    status: Status
    severity: Severity

    opened_at: Optional[date] = None
    closed_at: Optional[date] = None
    updated_at: Optional[date] = None

    clients_affected: Optional[int] = None
    product: Optional[str] = None
    feature: Optional[str] = None
    resolution_type: Optional[str] = None
