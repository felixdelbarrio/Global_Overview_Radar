"""Tests del repositorio de cache JSON."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bbva_bugresolutionradar.domain.models import CacheDocument
from bbva_bugresolutionradar.repositories.cache_repo import CacheRepo


def test_cache_repo_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    repo = CacheRepo(str(path))

    doc = CacheDocument(generated_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    repo.save(doc)

    loaded = repo.load()
    assert loaded.generated_at.date().isoformat() == "2025-01-01"
    assert loaded.incidents == {}


def test_cache_repo_missing_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    repo = CacheRepo(str(path))
    loaded = repo.load()

    assert loaded.incidents == {}
