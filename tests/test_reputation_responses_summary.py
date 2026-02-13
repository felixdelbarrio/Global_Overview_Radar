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
        "otros_actores_aliases": {"Beta Bank": ["Beta"]},
        "geografias": ["ES"],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_cache(path: Path, items: list[dict]) -> Path:
    doc = {
        "generated_at": datetime(2026, 2, 13, tzinfo=timezone.utc).isoformat(),
        "config_hash": "x",
        "sources_enabled": ["news", "appstore", "google_play"],
        "items": items,
        "stats": {"count": len(items)},
    }
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def _client(
    monkeypatch: pytest.MonkeyPatch, cache_path: Path, config_path: Path
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
    monkeypatch.setattr(rep_config.settings, "source_trustpilot", False)
    monkeypatch.setattr(rep_config.settings, "source_google_reviews", False)
    monkeypatch.setattr(rep_config.settings, "source_youtube", False)
    monkeypatch.setattr(rep_config.settings, "source_downdetector", False)

    app = create_app()
    app.dependency_overrides[reputation_router._refresh_settings] = lambda: None
    return TestClient(app)


def test_responses_summary_counts_and_repeated_templates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path / "profile.json")
    cache_path = _write_cache(
        tmp_path / "cache.json",
        [
            {
                "id": "i1",
                "source": "appstore",
                "geo": "ES",
                "actor": "Acme Bank",
                "author": "User 1",
                "title": "Buena experiencia",
                "text": "Todo bien",
                "published_at": "2026-02-10T10:00:00Z",
                "sentiment": "positive",
                "signals": {
                    "reply_text": "Gracias por tu comentario",
                    "reply_author": "Acme Bank",
                    "reply_at": "2026-02-10T11:00:00Z",
                },
            },
            {
                "id": "i2",
                "source": "google_play",
                "geo": "ES",
                "actor": "Acme Bank",
                "author": "User 2",
                "title": "Problema con login",
                "text": "No pude entrar",
                "published_at": "2026-02-11T10:00:00Z",
                "sentiment": "negative",
                "signals": {
                    "reply_text": "Lamentamos las molestias",
                    "reply_author": "Acme Support",
                },
            },
            {
                "id": "i3",
                "source": "appstore",
                "geo": "ES",
                "actor": "Beta Bank",
                "author": "User 3",
                "title": "Transferencia bloqueada",
                "text": "No funciona",
                "published_at": "2026-02-11T12:00:00Z",
                "sentiment": "negative",
                "signals": {
                    "reply_text": "Lamentamos las molestias",
                    "reply_author": "Beta Bank",
                },
            },
            {
                "id": "i4",
                "source": "google_play",
                "geo": "ES",
                "actor": "Acme Bank",
                "author": "User 4",
                "title": "Sin respuesta",
                "text": "Sigue igual",
                "published_at": "2026-02-12T10:00:00Z",
                "sentiment": "negative",
            },
            {
                "id": "i5",
                "source": "news",
                "geo": "ES",
                "actor": "Acme Bank",
                "author": "User 5",
                "title": "No entra en resumen de respuestas",
                "text": "Fuente no market",
                "published_at": "2026-02-12T11:00:00Z",
                "sentiment": "positive",
                "signals": {"reply_text": "Esto no debe contar"},
            },
        ],
    )
    client = _client(monkeypatch, cache_path, config_path)

    res = client.get("/reputation/responses/summary", params={"detail_limit": 2})
    assert res.status_code == 200
    body = res.json()

    assert body["totals"]["opinions_total"] == 4
    assert body["totals"]["answered_total"] == 3
    assert body["totals"]["answered_positive"] == 1
    assert body["totals"]["answered_negative"] == 2
    assert body["totals"]["unanswered_negative"] == 1

    repeated = body["repeated_replies"]
    assert repeated
    assert repeated[0]["count"] == 2
    assert "Lamentamos las molestias" in repeated[0]["reply_text"]

    actor_types = {(row["actor"], row["actor_type"]) for row in body["actor_breakdown"]}
    assert ("Acme Bank", "principal") in actor_types
    assert ("Beta Bank", "secondary") in actor_types

    assert len(body["answered_items"]) == 2


def test_responses_summary_can_filter_actor_principal_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path / "profile.json")
    cache_path = _write_cache(
        tmp_path / "cache.json",
        [
            {
                "id": "p1",
                "source": "appstore",
                "geo": "ES",
                "actor": "Acme Bank",
                "title": "Principal",
                "text": "Texto",
                "published_at": "2026-02-10T10:00:00Z",
                "sentiment": "negative",
                "signals": {"reply_text": "Recibido"},
            },
            {
                "id": "s1",
                "source": "google_play",
                "geo": "ES",
                "actor": "Beta Bank",
                "title": "Secundario",
                "text": "Texto",
                "published_at": "2026-02-10T10:00:00Z",
                "sentiment": "negative",
                "signals": {"reply_text": "Recibido"},
            },
        ],
    )
    client = _client(monkeypatch, cache_path, config_path)

    res = client.get(
        "/reputation/responses/summary", params={"entity": "actor_principal"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["totals"]["opinions_total"] == 1
    assert body["totals"]["answered_total"] == 1


def test_responses_summary_can_filter_other_actors_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path / "profile.json")
    cache_path = _write_cache(
        tmp_path / "cache.json",
        [
            {
                "id": "p1",
                "source": "appstore",
                "geo": "ES",
                "actor": "Acme Bank",
                "title": "Principal",
                "text": "Texto",
                "published_at": "2026-02-10T10:00:00Z",
                "sentiment": "negative",
                "signals": {"reply_text": "Recibido principal"},
            },
            {
                "id": "s1",
                "source": "google_play",
                "geo": "ES",
                "actor": "Beta Bank",
                "title": "Secundario",
                "text": "Texto",
                "published_at": "2026-02-10T10:00:00Z",
                "sentiment": "neutral",
                "signals": {"reply_text": "Recibido secundario"},
            },
        ],
    )
    client = _client(monkeypatch, cache_path, config_path)

    res = client.get("/reputation/responses/summary", params={"entity": "other_actors"})
    assert res.status_code == 200
    body = res.json()
    assert body["totals"]["opinions_total"] == 1
    assert body["totals"]["answered_total"] == 1
    assert body["totals"]["answered_neutral"] == 1
    assert body["answered_items"][0]["id"] == "s1"


def test_responses_summary_uses_reply_datetime_for_old_reviews(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path / "profile.json")
    cache_path = _write_cache(
        tmp_path / "cache.json",
        [
            {
                "id": "old-1",
                "source": "appstore",
                "geo": "ES",
                "actor": "Acme Bank",
                "author": "User old",
                "title": "Reseña antigua",
                "text": "Texto antiguo",
                "published_at": "2025-05-01T10:00:00Z",
                "sentiment": "negative",
                "signals": {
                    "has_reply": True,
                    "reply_author": "Acme Bank",
                    "reply_at": "2026-02-13T12:15:00Z",
                },
            }
        ],
    )
    client = _client(monkeypatch, cache_path, config_path)

    res = client.get(
        "/reputation/responses/summary",
        params={"from_date": "2026-02-13", "to_date": "2026-02-13"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["totals"]["opinions_total"] == 1
    assert body["totals"]["answered_total"] == 1
    assert body["answered_items"][0]["reply_author"] == "Acme Bank"
