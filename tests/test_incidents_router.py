"""Tests adicionales para endpoints de incidencias."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bugresolutionradar.api.main import create_app
from bugresolutionradar.domain.enums import Severity, Status
from bugresolutionradar.domain.models import (
    CacheDocument,
    IncidentCurrent,
    IncidentHistoryEvent,
    IncidentRecord,
    RunInfo,
    RunSource,
    SourceRef,
)


class DummyRepo:
    def __init__(self, doc: CacheDocument) -> None:
        self._doc = doc

    def load(self) -> CacheDocument:
        return self._doc


def _record(
    gid: str,
    status: Status,
    severity: Severity,
    opened_at: date,
    title: str,
    product: str,
    feature: str,
) -> IncidentRecord:
    now = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
    current = IncidentCurrent(
        title=title,
        status=status,
        severity=severity,
        opened_at=opened_at,
        closed_at=None,
        updated_at=opened_at,
        clients_affected=10,
        product=product,
        feature=feature,
        resolution_type=None,
    )
    return IncidentRecord(
        global_id=gid,
        current=current,
        provenance=[
            SourceRef(
                source_id="src",
                source_key=gid,
                first_seen_at=now,
                last_seen_at=now,
            )
        ],
        history=[
            IncidentHistoryEvent(
                observed_at=now,
                run_id="run-1",
                source_id="src",
                diff={"status": {"from": "OPEN", "to": status.value}},
            )
        ],
    )


def _build_client() -> TestClient:
    today = date(2025, 1, 1)
    doc = CacheDocument(
        generated_at=datetime(2025, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
        incidents={
            "src:1": _record(
                "src:1",
                Status.OPEN,
                Severity.HIGH,
                today - timedelta(days=2),
                "Login fails",
                "Mobile",
                "Login",
            ),
            "src:2": _record(
                "src:2",
                Status.CLOSED,
                Severity.MEDIUM,
                today - timedelta(days=5),
                "Slow payments",
                "Payments",
                "Transfer",
            ),
        },
        runs=[
            RunInfo(
                run_id="run-latest",
                started_at=datetime(2025, 1, 3, 8, 0, 0, tzinfo=timezone.utc),
                sources=[RunSource(source_id="src", asset="/tmp", fingerprint=None)],
            )
        ],
    )
    app = create_app()
    app.state.cache_repo = DummyRepo(doc)
    return TestClient(app)


def test_incidents_sorting_and_filters() -> None:
    client = _build_client()

    res = client.get("/incidents", params={"sort": "severity_desc"})
    assert res.status_code == 200
    payload = res.json()
    assert payload["items"][0]["severity"] == "HIGH"

    res_open = client.get("/incidents", params={"status": "OPEN"})
    assert res_open.status_code == 200
    assert res_open.json()["total"] == 1

    res_window = client.get(
        "/incidents",
        params={
            "opened_from": "2024-12-30",
            "opened_to": "2025-01-02",
        },
    )
    assert res_window.status_code == 200
    assert res_window.json()["total"] == 1


def test_incidents_query_and_limit() -> None:
    client = _build_client()

    res_q = client.get("/incidents", params={"q": "payments"})
    assert res_q.status_code == 200
    assert res_q.json()["total"] == 1

    res_limit = client.get("/incidents", params={"limit": 1})
    assert res_limit.status_code == 200
    assert len(res_limit.json()["items"]) == 1


def test_incidents_override_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    overrides_path = tmp_path / "overrides.json"
    monkeypatch.setattr(
        "bugresolutionradar.api.routers.incidents.settings.incidents_overrides_path",
        str(overrides_path),
    )

    client = _build_client()

    res_empty = client.post("/incidents/override", json={"ids": []})
    assert res_empty.status_code == 400

    res_missing = client.post("/incidents/override", json={"ids": ["src:1"]})
    assert res_missing.status_code == 400

    res_ok = client.post(
        "/incidents/override",
        json={"ids": ["src:1"], "status": "BLOCKED", "note": "Manual"},
    )
    assert res_ok.status_code == 200

    res_list = client.get("/incidents")
    assert res_list.status_code == 200
    row = next(
        item for item in res_list.json()["items"] if item["global_id"] == "src:1"
    )
    assert row["manual_override"]["status"] == "BLOCKED"

    res_detail = client.get("/incidents/src:1")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["manual_override"]["note"] == "Manual"
    assert detail["current"]["status"] == "BLOCKED"
