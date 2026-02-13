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
    # Asegura determinismo: los tests en este módulo usan items con source="news".
    # Fuerza todos los toggles de fuentes a false salvo news.
    monkeypatch.setattr(rep_config.settings, "source_reddit", False)
    monkeypatch.setattr(rep_config.settings, "source_twitter", False)
    monkeypatch.setattr(rep_config.settings, "source_news", True)
    monkeypatch.setattr(rep_config.settings, "source_newsapi", False)
    monkeypatch.setattr(rep_config.settings, "source_gdelt", False)
    monkeypatch.setattr(rep_config.settings, "source_guardian", False)
    monkeypatch.setattr(rep_config.settings, "source_forums", False)
    monkeypatch.setattr(rep_config.settings, "source_blogs", False)
    monkeypatch.setattr(rep_config.settings, "source_appstore", False)
    monkeypatch.setattr(rep_config.settings, "source_trustpilot", False)
    monkeypatch.setattr(rep_config.settings, "source_google_reviews", False)
    monkeypatch.setattr(rep_config.settings, "source_google_play", False)
    monkeypatch.setattr(rep_config.settings, "source_youtube", False)
    monkeypatch.setattr(rep_config.settings, "source_downdetector", False)
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
    assert any(
        option.startswith("banking_bbva_") for option in body["options"]["default"]
    )


def test_profiles_update_samples_applies_templates_to_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import reputation.config as rep_config
    from reputation.api.routers import reputation as reputation_router

    cache_path = _write_cache(tmp_path / "cache.json", [])
    monkeypatch.setattr(rep_config.settings, "cache_path", cache_path)
    monkeypatch.setattr(rep_config.settings, "config_path", tmp_path / "profile.json")
    monkeypatch.setattr(rep_config.settings, "profiles", "")

    called: dict[str, object] = {}

    def _fake_apply_sample_profiles_to_default(
        profiles: list[str] | None,
    ) -> dict[str, object]:
        called["profiles"] = profiles
        return {
            "active": {
                "source": "default",
                "profiles": ["banking_bbva_retail"],
                "profile_key": "banking_bbva_retail",
            },
            "copied": {"config": ["banking_bbva_retail.json"], "llm": []},
            "removed": {"config": [], "llm": []},
            "missing": {"llm": []},
        }

    monkeypatch.setattr(
        reputation_router,
        "apply_sample_profiles_to_default",
        _fake_apply_sample_profiles_to_default,
    )

    app = create_app()
    app.dependency_overrides[reputation_router._refresh_settings] = lambda: None
    app.dependency_overrides[reputation_router.require_google_user] = lambda: None
    app.dependency_overrides[reputation_router.require_mutation_access] = lambda: None
    client = TestClient(app)

    res = client.post(
        "/reputation/profiles",
        json={"source": "samples", "profiles": ["banking_bbva_retail"]},
    )

    assert res.status_code == 200
    body = res.json()
    assert called["profiles"] == ["banking_bbva_retail"]
    assert body["active"]["source"] == "default"
    assert body["active"]["profiles"] == ["banking_bbva_retail"]
    assert body["copied"]["config"] == ["banking_bbva_retail.json"]
    assert body["auto_ingest"]["started"] is False


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


def test_items_returns_empty_when_cache_document_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path / "profile.json")
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "generated_at": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
                "config_hash": "x",
                "sources_enabled": ["news"],
                "items": [{"id": "bad-item-no-source"}],
                "stats": {"count": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    client = _client(monkeypatch, cache_path, config_path)
    res = client.get(
        "/reputation/items",
        params={"from_date": "2026-01-15", "to_date": "2026-02-13", "geo": "España"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["stats"]["count"] == 0
    assert body["items"] == []
