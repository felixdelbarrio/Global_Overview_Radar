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
        "actor_principal_aliases": {"Acme Bank": ["Acme App"]},
        "geografias": ["ES", "MX"],
        "segment_terms": ["login", "transferencias", "notificaciones", "tarjeta"],
        "keywords": ["fallo login", "error transferencia", "app movil"],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_cache(path: Path, items: list[dict[str, object]]) -> Path:
    doc = {
        "generated_at": datetime(2025, 1, 31, tzinfo=timezone.utc).isoformat(),
        "config_hash": "x",
        "sources_enabled": ["news", "appstore"],
        "items": items,
        "stats": {"count": len(items)},
    }
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def _item(
    item_id: str,
    *,
    actor: str,
    source: str,
    geo: str,
    author: str | None,
    sentiment: str,
    published_at: str,
    title: str,
    text: str,
    aspects: list[str] | None = None,
    signals: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": item_id,
        "source": source,
        "geo": geo,
        "actor": actor,
        "author": author,
        "title": title,
        "text": text,
        "sentiment": sentiment,
        "published_at": published_at,
    }
    if aspects:
        payload["aspects"] = aspects
    if signals:
        payload["signals"] = signals
    return payload


def _client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cache_path: Path,
    config_path: Path,
) -> TestClient:
    import reputation.config as rep_config
    from reputation.api.routers import reputation as reputation_router

    monkeypatch.setattr(rep_config.settings, "cache_path", cache_path)
    monkeypatch.setattr(rep_config.settings, "config_path", config_path)
    monkeypatch.setattr(rep_config.settings, "profiles", "")
    monkeypatch.setattr(rep_config.settings, "source_news", True)
    monkeypatch.setattr(rep_config.settings, "source_appstore", True)
    monkeypatch.setattr(rep_config.settings, "source_google_play", True)
    monkeypatch.setattr(rep_config.settings, "source_reddit", False)
    monkeypatch.setattr(rep_config.settings, "source_twitter", False)
    monkeypatch.setattr(rep_config.settings, "source_newsapi", False)
    monkeypatch.setattr(rep_config.settings, "source_gdelt", False)
    monkeypatch.setattr(rep_config.settings, "source_guardian", False)
    monkeypatch.setattr(rep_config.settings, "source_forums", False)
    monkeypatch.setattr(rep_config.settings, "source_blogs", False)
    monkeypatch.setattr(rep_config.settings, "source_trustpilot", True)
    monkeypatch.setattr(rep_config.settings, "source_google_reviews", False)
    monkeypatch.setattr(rep_config.settings, "source_youtube", False)
    monkeypatch.setattr(rep_config.settings, "source_downdetector", False)

    app = create_app()
    app.dependency_overrides[reputation_router._refresh_settings] = lambda: None
    return TestClient(app)


def test_markets_insights_builds_recurring_authors_features_and_newsletter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path / "profile.json")
    cache_path = _write_cache(
        tmp_path / "cache.json",
        [
            _item(
                "a1",
                actor="Acme Bank",
                source="appstore",
                geo="ES",
                author="Ana",
                sentiment="negative",
                published_at="2025-01-10T10:00:00Z",
                title="No puedo entrar",
                text="El login falla cada dia y la app se bloquea",
                aspects=["login"],
                signals={
                    "reply_text": "Gracias por reportarlo",
                    "reply_author": "Acme Bank",
                },
            ),
            _item(
                "a2",
                actor="Acme Bank",
                source="google_play",
                geo="ES",
                author="Ana",
                sentiment="negative",
                published_at="2025-01-12T10:00:00Z",
                title="Transferencia fallida",
                text="Las transferencias no funcionan desde ayer",
                aspects=["transferencias"],
                signals={
                    "reply_text": "Gracias por reportarlo",
                    "reply_author": "Acme Bank",
                },
            ),
            _item(
                "a3",
                actor="Acme Bank",
                source="trustpilot",
                geo="ES",
                author="Luis",
                sentiment="positive",
                published_at="2025-01-15T10:00:00Z",
                title="Mejoras visibles",
                text="La app va mejor y las notificaciones llegan",
            ),
            _item(
                "a4",
                actor="Acme Bank",
                source="appstore",
                geo="MX",
                author="Caro",
                sentiment="negative",
                published_at="2025-01-18T10:00:00Z",
                title="Fallo de token",
                text="Token y acceso tardan demasiado",
            ),
            _item(
                "b1",
                actor="Beta Bank",
                source="google_play",
                geo="ES",
                author="Pepe",
                sentiment="negative",
                published_at="2025-01-20T10:00:00Z",
                title="Caso competidor",
                text="Texto de competidor que no debe incluirse",
            ),
        ],
    )
    client = _client(monkeypatch, cache_path=cache_path, config_path=config_path)

    res = client.get(
        "/reputation/markets/insights",
        params={"geo": "ES", "from_date": "2025-01-01", "to_date": "2025-01-31"},
    )
    assert res.status_code == 200
    body = res.json()

    assert body["comparisons_enabled"] is False
    assert body["principal_actor"] == "Acme Bank"
    assert body["filters"]["geo"] == "ES"
    assert body["kpis"]["total_mentions"] == 2
    assert body["kpis"]["negative_mentions"] == 2
    assert body["kpis"]["recurring_authors"] == 1

    recurring = body["recurring_authors"]
    assert recurring
    assert recurring[0]["author"] == "Ana"
    assert recurring[0]["opinions_count"] == 2
    assert len(recurring[0]["opinions"]) == 2

    top_features = body["top_penalized_features"]
    assert top_features
    feature_names = {entry["feature"].lower() for entry in top_features}
    assert "login" in feature_names or "transferencias" in feature_names

    newsletters = body["newsletter_by_geo"]
    assert newsletters
    assert newsletters[0]["geo"] == "ES"
    assert "Newsletter reputacional · ES" in newsletters[0]["markdown"]
    assert newsletters[0]["subject"].startswith("[GOR] Radar reputacional ES")
    assert body["responses"]["totals"]["answered_total"] == 2
    assert body["responses"]["repeated_replies"][0]["count"] == 2


def test_markets_insights_without_geo_returns_multiple_editions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path / "profile.json")
    cache_path = _write_cache(
        tmp_path / "cache.json",
        [
            _item(
                "es-1",
                actor="Acme Bank",
                source="google_play",
                geo="ES",
                author="Ana",
                sentiment="negative",
                published_at="2025-01-10T10:00:00Z",
                title="Error en login",
                text="No me deja entrar",
            ),
            _item(
                "mx-1",
                actor="Acme Bank",
                source="appstore",
                geo="MX",
                author="Pablo",
                sentiment="negative",
                published_at="2025-01-11T10:00:00Z",
                title="No va transferencia",
                text="No puedo transferir dinero",
            ),
        ],
    )
    client = _client(monkeypatch, cache_path=cache_path, config_path=config_path)

    res = client.get("/reputation/markets/insights")
    assert res.status_code == 200
    body = res.json()

    editions = body["newsletter_by_geo"]
    assert editions
    edition_geos = {entry["geo"] for entry in editions}
    assert {"ES", "MX"}.issubset(edition_geos)


def test_markets_insights_responses_include_replies_to_old_reviews(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path / "profile.json")
    cache_path = _write_cache(
        tmp_path / "cache.json",
        [
            _item(
                "old-r1",
                actor="Acme Bank",
                source="appstore",
                geo="ES",
                author="Ana",
                sentiment="negative",
                published_at="2025-01-10T10:00:00Z",
                title="Reseña antigua",
                text="Texto antiguo",
                signals={
                    "has_reply": True,
                    "reply_author": "Acme Bank",
                    "reply_at": "2026-02-13T11:45:00Z",
                },
            )
        ],
    )
    client = _client(monkeypatch, cache_path=cache_path, config_path=config_path)

    res = client.get(
        "/reputation/markets/insights",
        params={"geo": "ES", "from_date": "2026-02-13", "to_date": "2026-02-13"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["kpis"]["total_mentions"] == 0
    assert body["responses"]["totals"]["opinions_total"] == 1
    assert body["responses"]["totals"]["answered_total"] == 1
