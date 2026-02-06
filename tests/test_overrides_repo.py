from __future__ import annotations

import json
from pathlib import Path

from reputation.repositories.overrides_repo import ReputationOverridesRepo


def test_overrides_repo_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    repo = ReputationOverridesRepo(path)

    assert repo.load() == {}

    payload = {
        "a1": {"geo": "ES", "sentiment": "neutral"},
        "a2": {"geo": "US", "sentiment": "positive"},
    }
    repo.save(payload)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert "updated_at" in data
    assert data["items"] == payload

    loaded = repo.load()
    assert loaded == payload


def test_overrides_repo_loads_flat_map(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    path.write_text(
        json.dumps({"a1": {"sentiment": "negative"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    repo = ReputationOverridesRepo(path)
    loaded = repo.load()
    assert loaded == {"a1": {"sentiment": "negative"}}


def test_overrides_repo_invalid_payload(tmp_path: Path) -> None:
    path = tmp_path / "overrides.json"
    path.write_text("{", encoding="utf-8")
    repo = ReputationOverridesRepo(path)
    assert repo.load() == {}

    path.write_text("[]", encoding="utf-8")
    assert repo.load() == {}
