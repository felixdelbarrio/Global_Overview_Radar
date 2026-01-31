"""Tests del merge de observaciones."""

from __future__ import annotations

from datetime import datetime, timezone

from bugresolutionradar.domain.enums import Severity, Status
from bugresolutionradar.domain.merge import compute_global_id, merge_observation
from bugresolutionradar.domain.models import IncidentRecord, ObservedIncident


def _obs(title: str, status: Status, severity: Severity) -> ObservedIncident:
    now = datetime(2025, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    return ObservedIncident(
        source_id="src",
        source_key="INC-1",
        observed_at=now,
        title=title,
        status=status,
        severity=severity,
        opened_at=now.date(),
        closed_at=None,
        updated_at=now.date(),
        clients_affected=5,
        product="App",
        feature="Login",
        resolution_type=None,
    )


def test_compute_global_id_is_deterministic() -> None:
    gid1 = compute_global_id("src", "INC-1")
    gid2 = compute_global_id("src", "INC-1")
    assert gid1 == gid2
    assert len(gid1) == 24


def test_merge_observation_creates_record() -> None:
    obs = _obs("Login error", Status.OPEN, Severity.HIGH)
    gid = compute_global_id(obs.source_id, obs.source_key)

    rec = merge_observation(None, obs, gid, "run-1")

    assert isinstance(rec, IncidentRecord)
    assert rec.global_id == gid
    assert rec.current.title == "Login error"
    assert rec.history
    assert rec.history[0].diff["_event"] == ["NONE", "CREATED"]


def test_merge_observation_updates_history_on_change() -> None:
    obs1 = _obs("Login error", Status.OPEN, Severity.HIGH)
    gid = compute_global_id(obs1.source_id, obs1.source_key)
    rec1 = merge_observation(None, obs1, gid, "run-1")

    obs2 = _obs("Login error 2", Status.CLOSED, Severity.CRITICAL)
    rec2 = merge_observation(rec1, obs2, gid, "run-2")

    assert rec2.current.status == Status.CLOSED
    assert rec2.current.severity == Severity.CRITICAL
    assert len(rec2.history) == 2
