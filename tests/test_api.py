"""Tests de endpoints FastAPI."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from bbva_bugresolutionradar.api.main import create_app
from bbva_bugresolutionradar.domain.enums import Severity, Status
from bbva_bugresolutionradar.domain.models import CacheDocument, IncidentCurrent, IncidentRecord


class DummyRepo:
    def __init__(self, doc: CacheDocument) -> None:
        self._doc = doc

    def load(self) -> CacheDocument:
        return self._doc


def _record(
    gid: str,
    status: Status,
    severity: Severity,
    opened: date,
    closed: date | None = None,
) -> IncidentRecord:
    cur = IncidentCurrent(
        title=f"Incident {gid}",
        status=status,
        severity=severity,
        opened_at=opened,
        closed_at=closed,
        updated_at=opened,
        clients_affected=5,
        product="App",
        feature="Login",
        resolution_type=None,
    )
    return IncidentRecord(global_id=gid, current=cur, provenance=[], history=[])


def _build_app_with_data() -> TestClient:
    today = date.today()
    doc = CacheDocument(
        generated_at=datetime.now(timezone.utc),
        incidents={
            "src:1": _record("src:1", Status.OPEN, Severity.HIGH, today - timedelta(days=1)),
            "src:2": _record(
                "src:2",
                Status.CLOSED,
                Severity.MEDIUM,
                today - timedelta(days=2),
                closed=today - timedelta(days=1),
            ),
        },
    )
    app = create_app()
    app.state.cache_repo = DummyRepo(doc)
    return TestClient(app)


def test_health() -> None:
    client = _build_app_with_data()
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"


def test_kpis_endpoint() -> None:
    client = _build_app_with_data()
    res = client.get("/kpis")
    assert res.status_code == 200
    payload = res.json()
    assert payload["open_total"] == 1
    assert payload["open_by_severity"]["HIGH"] == 1


def test_incidents_list_filters() -> None:
    client = _build_app_with_data()
    res = client.get("/incidents", params={"only_open": True})
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["global_id"] == "src:1"

    res_q = client.get("/incidents", params={"q": "src:2"})
    assert res_q.status_code == 200
    assert res_q.json()["total"] == 1


def test_incident_detail_and_404() -> None:
    client = _build_app_with_data()
    ok = client.get("/incidents/src:1")
    assert ok.status_code == 200
    assert ok.json()["global_id"] == "src:1"

    missing = client.get("/incidents/does-not-exist")
    assert missing.status_code == 404


def test_evolution_series() -> None:
    client = _build_app_with_data()
    res = client.get("/evolution", params={"days": 3})
    assert res.status_code == 200
    data = res.json()
    assert data["days"] == 3
    assert len(data["series"]) == 3
    # The last day should still have the open incident
    assert data["series"][-1]["open"] >= 1
