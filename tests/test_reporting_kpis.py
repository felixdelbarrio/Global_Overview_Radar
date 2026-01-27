from __future__ import annotations

from datetime import date

from bbva_bugresolutionradar.domain.enums import Severity, Status
from bbva_bugresolutionradar.domain.kpis import compute_kpis
from bbva_bugresolutionradar.domain.models import IncidentCurrent, IncidentRecord


def _record(
    gid: str, status: Status, severity: Severity, opened: date, closed: date | None
) -> IncidentRecord:
    current = IncidentCurrent(
        title=f"Incident {gid}",
        status=status,
        severity=severity,
        opened_at=opened,
        closed_at=closed,
        updated_at=opened,
        clients_affected=10,
        product="App",
        feature="Login",
        resolution_type=None,
    )
    return IncidentRecord(global_id=gid, current=current, provenance=[], history=[])


def test_compute_kpis_basic_counts() -> None:
    today = date.today()
    incidents = [
        _record("A", Status.OPEN, Severity.CRITICAL, today, None),
        _record("B", Status.CLOSED, Severity.MEDIUM, today, today),
        _record("C", Status.OPEN, Severity.HIGH, today, None),
    ]

    result = compute_kpis(
        incidents=incidents,
        today=today,
        period_days=7,
        master_threshold_clients=5,
        stale_days_threshold=1,
    )

    assert result.open_total == 2
    assert result.new_total == 3
    assert result.closed_total == 1
    assert result.open_by_severity[Severity.CRITICAL] == 1
    assert result.open_by_severity[Severity.HIGH] == 1
    assert result.new_masters == 3
