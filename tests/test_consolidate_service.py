from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bbva_bugresolutionradar.domain.enums import Severity, Status
from bbva_bugresolutionradar.domain.models import ObservedIncident, RunSource
from bbva_bugresolutionradar.services.consolidate_service import ConsolidateService


def test_consolidate_creates_history_on_change() -> None:
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    later = now + timedelta(hours=1)

    obs1 = ObservedIncident(
        source_id="src",
        source_key="INC-1",
        observed_at=now,
        title="Login error",
        status=Status.OPEN,
        severity=Severity.LOW,
        opened_at=now.date(),
        closed_at=None,
        updated_at=now.date(),
        clients_affected=2,
        product="Mobile",
        feature="Login",
        resolution_type=None,
    )
    obs2 = ObservedIncident(
        source_id="src",
        source_key="INC-1",
        observed_at=later,
        title="Login error",
        status=Status.CLOSED,
        severity=Severity.HIGH,
        opened_at=now.date(),
        closed_at=later.date(),
        updated_at=later.date(),
        clients_affected=2,
        product="Mobile",
        feature="Login",
        resolution_type=None,
    )

    service = ConsolidateService()
    doc = service.consolidate(
        observations=[obs1, obs2],
        sources=[RunSource(source_id="src", asset="file.csv")],
    )

    rec = doc.incidents["src:INC-1"]
    assert rec.current.status == Status.CLOSED
    assert rec.current.severity == Severity.HIGH
    assert len(rec.history) == 1
    assert "status" in rec.history[0].diff
    assert "severity" in rec.history[0].diff
