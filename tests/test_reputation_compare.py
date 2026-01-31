from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from bugresolutionradar.api.main import create_app
from reputation.actors import primary_actor_info
from reputation.config import load_business_config


def _make_item(gid: str, actor: str | None, geo: str, title: str | None = None) -> dict:
    return {
        "id": gid,
        "source": "news",
        "geo": geo,
        "actor": actor,
        "title": title or f"Title {gid}",
        "text": f"Text {gid}",
        "published_at": "2025-01-01T00:00:00Z",
    }


def test_compare_endpoint_normalizes_and_combines(monkeypatch, tmp_path: Path) -> None:
    cfg = load_business_config()
    principal = primary_actor_info(cfg)
    assert principal is not None
    principal_canonical = str(principal.get("canonical") or "").strip()
    principal_aliases = list(principal.get("aliases") or principal.get("names") or [])
    if not principal_aliases:
        principal_aliases = [principal_canonical]
    principal_alias = principal_aliases[0]

    other_aliases = cfg.get("otros_actores_aliases") or {}
    assert isinstance(other_aliases, dict)
    assert other_aliases
    other_canonical = next(iter(other_aliases.keys()))
    other_alias_values = other_aliases.get(other_canonical) or []
    if isinstance(other_alias_values, list) and other_alias_values:
        other_alias = other_alias_values[0]
    else:
        other_alias = other_canonical

    geos = cfg.get("geografias") or []
    geo = geos[0] if isinstance(geos, list) and geos else "Global"

    # build a minimal cache doc with various actor variants and write to tmp file
    items = [
        _make_item("a1", other_alias, geo),
        _make_item("a2", other_canonical, geo),
        _make_item("p1", principal_alias, geo),
        _make_item("p2", None, geo, title=f"{principal_alias} novedades"),
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
            "entity": "actor_principal",
            "geo": geo,
            "from_date": "2024-01-01",
            "to_date": "2026-01-01",
        },
        {
            "actor": other_canonical,
            "geo": geo,
            "from_date": "2024-01-01",
            "to_date": "2026-01-01",
        },
    ]

    res = client.post("/reputation/items/compare", json=payload)
    assert res.status_code == 200
    body = res.json()

    # two groups
    assert len(body.get("groups", [])) == 2
    # group counts: actor principal group should include p1 (normalized) and p2 (title contains alias); at least 1
    assert body["groups"][0]["stats"]["count"] >= 1
    assert body["groups"][1]["stats"]["count"] >= 1
    # combined should include all unique ids
    combined_ids = {it["id"] for it in body["combined"]["items"]}
    assert {"a1", "a2", "p1"}.issubset(combined_ids)
