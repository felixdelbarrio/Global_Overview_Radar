"""Fixtures compartidas para tests del backend."""

from __future__ import annotations

import importlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, TYPE_CHECKING

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

# Ensure the backend package is importable without installing.
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_enums = importlib.import_module("bugresolutionradar.domain.enums")
Severity = _enums.Severity
Status = _enums.Status
_models = importlib.import_module("bugresolutionradar.domain.models")
CacheDocument = _models.CacheDocument
IncidentCurrent = _models.IncidentCurrent
IncidentHistoryEvent = _models.IncidentHistoryEvent
IncidentRecord = _models.IncidentRecord
SourceRef = _models.SourceRef

if TYPE_CHECKING:
    from bugresolutionradar.domain.enums import Severity as _Severity, Status as _Status
    from bugresolutionradar.domain.models import (
        CacheDocument as _CacheDocument,
        IncidentRecord as _IncidentRecord,
    )


def _make_record(
    *,
    global_id: str,
    status: "_Status",
    severity: "_Severity",
    opened_at: date | None,
    closed_at: date | None = None,
    updated_at: date | None = None,
    title: str = "",
    clients_affected: int | None = None,
    product: str | None = None,
    feature: str | None = None,
) -> "_IncidentRecord":
    now = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    current = IncidentCurrent(
        title=title,
        status=status,
        severity=severity,
        opened_at=opened_at,
        closed_at=closed_at,
        updated_at=updated_at,
        clients_affected=clients_affected,
        product=product,
        feature=feature,
        resolution_type=None,
    )
    return IncidentRecord(
        global_id=global_id,
        current=current,
        provenance=[
            SourceRef(
                source_id="src",
                source_key=global_id,
                first_seen_at=now,
                last_seen_at=now,
            )
        ],
        history=[
            IncidentHistoryEvent(
                observed_at=now,
                run_id="run-1",
                source_id="src",
                diff={"status": {"from": "OPEN", "to": status}},
            )
        ],
    )


@pytest.fixture()
def sample_doc() -> "_CacheDocument":
    today = date.today()
    incidents: Dict[str, "_IncidentRecord"] = {
        "src:1": _make_record(
            global_id="src:1",
            status=Status.OPEN,
            severity=Severity.HIGH,
            opened_at=today,
            updated_at=today,
            title="Login fails",
            clients_affected=12,
            product="Mobile",
            feature="Login",
        ),
        "src:2": _make_record(
            global_id="src:2",
            status=Status.CLOSED,
            severity=Severity.MEDIUM,
            opened_at=today,
            closed_at=today,
            updated_at=today,
            title="Slow payments",
            clients_affected=3,
            product="Payments",
            feature="Transfer",
        ),
    }

    return CacheDocument(
        generated_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        runs=[],
        incidents=incidents,
    )
