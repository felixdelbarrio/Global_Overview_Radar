from __future__ import annotations

from fastapi.testclient import TestClient

from reputation.api.main import create_app


def test_health_endpoint() -> None:
    client = TestClient(create_app())
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "date" in data
