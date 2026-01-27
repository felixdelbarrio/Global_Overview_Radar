from __future__ import annotations

from datetime import datetime, timezone

from reputation.config import (
    compute_config_hash,
    effective_ttl_hours,
    load_business_config,
    settings,
)
from reputation.models import ReputationCacheDocument, ReputationCacheStats
from reputation.repositories.cache_repo import ReputationCacheRepo


class ReputationIngestService:
    """Paso 1: plumbing + cache vacía, sin collectors todavía."""

    def __init__(self) -> None:
        self._settings = settings
        self._repo = ReputationCacheRepo(self._settings.cache_path)

    def run(self, force: bool = False) -> ReputationCacheDocument:
        cfg = load_business_config()
        cfg_hash = compute_config_hash(cfg)
        ttl_hours = effective_ttl_hours(cfg)
        sources_enabled = self._settings.enabled_sources()

        # Feature apagada: devolvemos doc vacío, no escribimos
        if not self._settings.reputation_enabled:
            return self._build_empty_doc(
                cfg_hash=cfg_hash,
                sources_enabled=sources_enabled,
                note="REPUTATION_ENABLED=false",
            )

        # Reutiliza cache si aplica
        if self._settings.cache_enabled and not force:
            existing = self._repo.load()
            if existing and existing.config_hash == cfg_hash and self._repo.is_fresh(ttl_hours):
                return existing

        # Paso 1: sin collectors => items=[]
        doc = self._build_empty_doc(
            cfg_hash=cfg_hash,
            sources_enabled=sources_enabled,
            note="Paso 1: sin collectors (cache vacía)",
        )

        if self._settings.cache_enabled:
            self._repo.save(doc)

        return doc

    @staticmethod
    def _build_empty_doc(
        cfg_hash: str,
        sources_enabled: list[str],
        note: str | None = None,
    ) -> ReputationCacheDocument:
        return ReputationCacheDocument(
            generated_at=datetime.now(timezone.utc),
            config_hash=cfg_hash,
            sources_enabled=sources_enabled,
            items=[],
            stats=ReputationCacheStats(count=0, note=note),
        )
