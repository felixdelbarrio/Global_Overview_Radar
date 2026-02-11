from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reputation.api.main import create_app

_ADMIN_KEY = "32chars-minimum-admin-key-12345678"


def _write_cache(tmp_path: Path, items: list[dict]) -> Path:
    doc = {
        "generated_at": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        "config_hash": "x",
        "sources_enabled": [],
        "items": items,
        "stats": {"count": len(items)},
    }
    cache_file = tmp_path / "rep_cache.json"
    cache_file.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return cache_file


def _make_item(item_id: str, geo: str, sentiment: str) -> dict:
    return {
        "id": item_id,
        "source": "news",
        "geo": geo,
        "actor": "Acme",
        "title": f"Title {item_id}",
        "text": f"Text {item_id}",
        "published_at": "2025-01-01T00:00:00Z",
        "sentiment": sentiment,
    }


def _client(
    monkeypatch: pytest.MonkeyPatch, cache_path: Path, overrides_path: Path
) -> TestClient:
    import reputation.config as rep_config
    from reputation.api.routers import reputation as reputation_router

    monkeypatch.setattr(rep_config.settings, "cache_path", cache_path)
    monkeypatch.setattr(rep_config.settings, "overrides_path", overrides_path)
    # Asegura determinismo: estos tests usan items con source="news"
    monkeypatch.setattr(rep_config.settings, "source_news", True)
    monkeypatch.setattr(rep_config.settings, "google_cloud_login_requested", False)
    monkeypatch.setattr(rep_config.settings, "auth_bypass_allow_mutations", True)
    monkeypatch.setattr(rep_config.settings, "auth_bypass_mutation_key", _ADMIN_KEY)
    app = create_app()
    app.dependency_overrides[reputation_router._refresh_settings] = lambda: None
    return TestClient(app)


def test_override_endpoint_updates_items(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    items = [
        _make_item("a1", "ES", "neutral"),
        _make_item("a2", "FR", "positive"),
    ]
    cache_path = _write_cache(tmp_path, items)
    overrides_path = tmp_path / "rep_overrides.json"
    client = _client(monkeypatch, cache_path, overrides_path)

    res = client.post(
        "/reputation/items/override",
        json={"ids": ["a1"], "geo": "USA", "sentiment": "negative"},
        headers={"x-gor-admin-key": _ADMIN_KEY},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["updated"] == 1
    assert body["ids"] == ["a1"]
    assert body["updated_at"]

    res = client.get("/reputation/items")
    assert res.status_code == 200
    data = res.json()

    items_by_id = {it["id"]: it for it in data["items"]}
    assert items_by_id["a1"]["geo"] == "USA"
    assert items_by_id["a1"]["sentiment"] == "negative"
    override = items_by_id["a1"].get("manual_override")
    assert override
    assert override["geo"] == "USA"
    assert override["sentiment"] == "negative"
    assert override["updated_at"]

    assert items_by_id["a2"]["geo"] == "FR"
    assert items_by_id["a2"]["sentiment"] == "positive"
    assert not items_by_id["a2"].get("manual_override")


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({"ids": [], "geo": "ES"}, "ids is required"),
        ({"ids": ["a1"]}, "geo or sentiment is required"),
        ({"ids": ["a1"], "sentiment": "bad"}, "invalid sentiment value"),
        ({"ids": ["a1"], "geo": "  "}, "geo cannot be empty"),
    ],
)
def test_override_endpoint_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: dict,
    detail: str,
) -> None:
    cache_path = _write_cache(tmp_path, [_make_item("a1", "ES", "neutral")])
    overrides_path = tmp_path / "rep_overrides.json"
    client = _client(monkeypatch, cache_path, overrides_path)

    res = client.post(
        "/reputation/items/override",
        json=payload,
        headers={"x-gor-admin-key": _ADMIN_KEY},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == detail


def test_compare_uses_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    items = [
        _make_item("a1", "ES", "positive"),
        _make_item("a2", "FR", "negative"),
    ]
    cache_path = _write_cache(tmp_path, items)
    overrides_path = tmp_path / "rep_overrides.json"
    overrides_path.write_text(
        json.dumps(
            {
                "updated_at": "2025-01-02T10:00:00+00:00",
                "items": {
                    "a1": {
                        "geo": "US",
                        "sentiment": "negative",
                        "updated_at": "2025-01-02T10:00:00+00:00",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(monkeypatch, cache_path, overrides_path)

    res = client.post(
        "/reputation/items/compare",
        json=[{"geo": "US", "sentiment": "negative"}],
    )
    assert res.status_code == 200
    body = res.json()

    group_items = body["groups"][0]["items"]
    assert len(group_items) == 1
    assert group_items[0]["id"] == "a1"
