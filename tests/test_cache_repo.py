from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from reputation.models import ReputationCacheDocument, ReputationItem
from reputation.repositories.cache_repo import ReputationCacheRepo


def _doc() -> ReputationCacheDocument:
    return ReputationCacheDocument(
        generated_at=datetime.now(timezone.utc),
        config_hash="x",
        sources_enabled=[],
        items=[],
        market_ratings=[],
    )


def test_cache_repo_load_missing(tmp_path: Path) -> None:
    repo = ReputationCacheRepo(tmp_path / "missing.json")
    assert repo.load() is None
    assert repo.is_fresh(ttl_hours=1) is False


def test_cache_repo_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    repo = ReputationCacheRepo(path)

    doc = _doc()
    repo.save(doc)

    loaded = repo.load()
    assert loaded is not None
    assert loaded.config_hash == "x"
    assert loaded.items == []


def test_cache_repo_is_fresh(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    repo = ReputationCacheRepo(path)

    doc = _doc()
    doc.generated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    repo.save(doc)

    assert repo.is_fresh(ttl_hours=2)
    assert not repo.is_fresh(ttl_hours=0)


def test_cache_repo_applies_aliases(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config_file = repo_root / "data" / "reputation" / "config.json"
    original = None
    if config_file.exists():
        original = config_file.read_text(encoding="utf-8")
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        '{"otros_actores_aliases": {"Acme Bank": ["Acme"]}}',
        encoding="utf-8",
    )

    try:
        path = tmp_path / "cache.json"
        repo = ReputationCacheRepo(path)
        doc = ReputationCacheDocument(
            generated_at=datetime.now(timezone.utc),
            config_hash="x",
            sources_enabled=[],
            items=[
                ReputationItem(
                    id="a1",
                    source="news",
                    geo="ES",
                    actor="Acme",
                    title="t",
                    text="x",
                    published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                )
            ],
            market_ratings=[],
        )
        repo.save(doc)
        loaded = repo.load()
        assert loaded is not None
        assert loaded.items[0].actor == "Acme Bank"
    finally:
        if original is None:
            config_file.unlink(missing_ok=True)
        else:
            config_file.write_text(original, encoding="utf-8")


def test_cache_repo_ignores_invalid_config(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config_file = repo_root / "data" / "reputation" / "config.json"
    original = None
    if config_file.exists():
        original = config_file.read_text(encoding="utf-8")
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("{", encoding="utf-8")

    try:
        path = tmp_path / "cache.json"
        repo = ReputationCacheRepo(path)
        doc = ReputationCacheDocument(
            generated_at=datetime.now(timezone.utc),
            config_hash="x",
            sources_enabled=[],
            items=[
                ReputationItem(
                    id="a1",
                    source="news",
                    geo="ES",
                    actor="Acme",
                    title="t",
                    text="x",
                    published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                )
            ],
            market_ratings=[],
        )
        repo.save(doc)
        loaded = repo.load()
        assert loaded is not None
        assert loaded.items[0].actor == "Acme"
    finally:
        if original is None:
            config_file.unlink(missing_ok=True)
        else:
            config_file.write_text(original, encoding="utf-8")
