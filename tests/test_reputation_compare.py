from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from bugresolutionradar.api.main import create_app


def _make_item(gid: str, actor: str | None, geo: str) -> dict:
    return {
        "id": gid,
        "source": "news",
        "geo": geo,
        "actor": actor,
        "title": f"Title {gid}",
        "text": f"Text {gid}",
        "published_at": "2025-01-01T00:00:00Z",
    }


def test_compare_endpoint_normalizes_and_combines(monkeypatch, tmp_path: Path) -> None:
    # build a minimal cache doc with various actor variants and write to tmp file
    items = [
        _make_item("a1", "Banco Santander", "España"),
        _make_item("a2", "Santander", "España"),
        _make_item("b1", "BBVA Empresas", "España"),
        _make_item("b2", None, "España"),
    ]

    doc_dict = {
        "generated_at": datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        "config_hash": "x",
        "sources_enabled": [],
        "items": items,
        "stats": {"count": len(items)},
    }

    cache_file = tmp_path / "rep_cache.json"
    import json

    cache_file.write_text(json.dumps(doc_dict, ensure_ascii=False), encoding="utf-8")

    # point the reputation settings cache_path to our temp file so the real
    # ReputationCacheRepo.load() (which performs normalization) is used.
    import reputation.config as rep_config

    monkeypatch.setattr(rep_config.settings, "cache_path", cache_file)

    app = create_app()
    client = TestClient(app)

    payload = [
        {
            "entity": "bbva",
            "geo": "España",
            "from_date": "2024-01-01",
            "to_date": "2026-01-01",
        },
        {
            "actor": "Santander",
            "geo": "España",
            "from_date": "2024-01-01",
            "to_date": "2026-01-01",
        },
    ]

    res = client.post("/reputation/items/compare", json=payload)
    assert res.status_code == 200
    body = res.json()

    # two groups
    assert len(body.get("groups", [])) == 2
    # group counts: BBVA group should include b1 (normalized) and b2 (title contains BBVA?); at least 1
    assert body["groups"][0]["stats"]["count"] >= 1
    assert body["groups"][1]["stats"]["count"] >= 1
    # combined should include all unique ids
    combined_ids = {it["id"] for it in body["combined"]["items"]}
    # b2 has no explicit BBVA mention in title/text, so it may be excluded.
    assert {"a1", "a2", "b1"}.issubset(combined_ids)
