"""Modelos canonicos del dominio (Pydantic)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field

from bugresolutionradar.domain.enums import Severity, Status


class SourceRef(BaseModel):
    """Referencia de procedencia de una incidencia."""

    source_id: str
    source_key: str
    first_seen_at: datetime
    last_seen_at: datetime


class IncidentCurrent(BaseModel):
    """Estado actual de una incidencia."""

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
        """Indica si la incidencia sigue abierta."""
        return self.status in {Status.OPEN, Status.IN_PROGRESS, Status.BLOCKED}

    def is_master(self, threshold: int) -> bool:
        """Indica si la incidencia supera el umbral de clientes afectados."""
        if self.clients_affected is None:
            return False
        return self.clients_affected > threshold


class IncidentHistoryEvent(BaseModel):
    """Evento historico con cambios relevantes detectados."""

    observed_at: datetime
    run_id: str
    source_id: str
    diff: Dict[str, Any] = Field(default_factory=dict)


class IncidentRecord(BaseModel):
    """Incidencia consolidada con estado actual, procedencia e historial."""

    global_id: str
    current: IncidentCurrent
    provenance: List[SourceRef] = Field(default_factory=lambda: cast(List[SourceRef], []))
    history: List[IncidentHistoryEvent] = Field(
        default_factory=lambda: cast(List[IncidentHistoryEvent], [])
    )


class RunSource(BaseModel):
    """Metadata de una fuente usada en una ejecucion de ingest."""

    source_id: str
    asset: str
    fingerprint: Optional[str] = None


class RunInfo(BaseModel):
    """Metadata global de una ejecucion de ingest/consolidacion."""

    run_id: str
    started_at: datetime
    sources: List[RunSource]


class CacheDocument(BaseModel):
    """Documento consolidado listo para consulta por la API."""

    schema_version: str = "1.0"
    generated_at: datetime
    runs: List[RunInfo] = Field(default_factory=lambda: cast(List[RunInfo], []))
    incidents: Dict[str, IncidentRecord] = Field(default_factory=dict)


class ObservedIncident(BaseModel):
    """Observacion canonica de un adapter (una fila/registro de una fuente).

    El global_id se calcula en servicios, pero los adapters deben aportar
    source_id y source_key.
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
