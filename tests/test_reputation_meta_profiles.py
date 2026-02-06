from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reputation.api.main import create_app


def _write_config(path: Path) -> Path:
    payload = {
        "actor_principal": {"Acme Bank": ["Acme"]},
        "otros_actores_globales": ["Beta Bank"],
        "otros_actores_por_geografia": {"ES": ["Beta Bank"]},
        "geografias": ["Global", "ES"],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_cache(
    path: Path, items: list[dict], sources: list[str] | None = None
) -> Path:
    doc = {
        "generated_at": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        "config_hash": "x",
        "sources_enabled": sources or [],
        "items": items,
        "stats": {"count": len(items)},
    }
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def _client(
    monkeypatch: pytest.MonkeyPatch,
    cache_path: Path,
    config_path: Path,
    profiles: str = "",
) -> TestClient:
    import reputation.config as rep_config
    from reputation.api.routers import reputation as reputation_router

    monkeypatch.setattr(rep_config.settings, "cache_path", cache_path)
    monkeypatch.setattr(rep_config.settings, "config_path", config_path)
    monkeypatch.setattr(rep_config.settings, "profiles", profiles)
    monkeypatch.setattr(rep_config.settings, "source_news", True)
    app = create_app()
    app.dependency_overrides[reputation_router._refresh_settings] = lambda: None
    return TestClient(app)


def test_meta_reports_cache_and_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = _write_config(tmp_path / "profile.json")
    cache_path = _write_cache(
        tmp_path / "cache.json",
        [
            {
                "id": "n1",
                "source": "news",
                "geo": "ES",
                "actor": "Acme Bank",
                "title": "Titulo",
                "text": "Texto",
                "published_at": "2025-01-01T00:00:00Z",
                "sentiment": "positive",
            }
        ],
        sources=["news"],
    )

    client = _client(monkeypatch, cache_path, config_path)
    res = client.get("/reputation/meta")
    assert res.status_code == 200
    body = res.json()
    assert body["cache_available"] is True
    assert body["sources_enabled"] == ["news"]
    assert body["source_counts"]["news"] == 1
    assert "Global" in body["geos"]
    assert body["actor_principal"]["canonical"] == "Acme Bank"


def test_profiles_lists_default_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    alpha = tmp_path / "alpha.json"
    beta = tmp_path / "beta.json"
    alpha.write_text("{}", encoding="utf-8")
    beta.write_text("{}", encoding="utf-8")
    cache_path = _write_cache(tmp_path / "cache.json", [])

    client = _client(monkeypatch, cache_path, tmp_path, profiles="alpha")
    res = client.get("/reputation/profiles")
    assert res.status_code == 200
    body = res.json()
    assert "alpha" in body["active"]["profiles"]
    assert "banking_bbva_retail" in body["options"]["default"]


def test_items_filters_by_geo_sentiment_and_date(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = _write_config(tmp_path / "profile.json")
    cache_path = _write_cache(
        tmp_path / "cache.json",
        [
            {
                "id": "p1",
                "source": "news",
                "geo": "ES",
                "actor": "Acme Bank",
                "title": "Bueno",
                "text": "Texto bueno",
                "published_at": "2025-01-10T00:00:00Z",
                "sentiment": "positive",
            },
            {
                "id": "n1",
                "source": "news",
                "geo": "FR",
                "actor": "Acme Bank",
                "title": "Malo",
                "text": "Texto malo",
                "published_at": "2025-01-10T00:00:00Z",
                "sentiment": "negative",
            },
        ],
        sources=["news"],
    )

    client = _client(monkeypatch, cache_path, config_path)
    res = client.get(
        "/reputation/items",
        params={
            "geo": "ES",
            "sentiment": "positive",
            "sources": "news",
            "from_date": "2024-01-01",
            "to_date": "2026-01-01",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["stats"]["count"] == 1
    assert body["items"][0]["id"] == "p1"
