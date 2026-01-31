"""CLI para ejecutar ingest y consolidacion desde terminal."""

from __future__ import annotations

import sys
from pathlib import Path

from bugresolutionradar.config import settings
from bugresolutionradar.domain.models import RunSource
from bugresolutionradar.repositories import CacheRepo
from bugresolutionradar.services import ConsolidateService, IngestService


def main() -> None:
    """Punto de entrada CLI (soporta comandos 'ingest' y 'reputation-ingest')."""
    if len(sys.argv) < 2:
        print("Usage: brr ingest | brr reputation-ingest")
        sys.exit(1)

    cmd = sys.argv[1]

    # ------------------------------------------------------------------
    # INGEST ACTUAL (incidencias / bugs)
    # ------------------------------------------------------------------
    if cmd == "ingest":
        print(">> Running ingest pipeline...")

        repo = CacheRepo(settings.cache_path)
        ingest_service = IngestService(settings)
        consolidate_service = ConsolidateService()

        observations = ingest_service.ingest()
        print(f">> Observations read: {len(observations)}")

        asset = str(Path(settings.assets_dir).resolve())
        sources = [
            RunSource(
                source_id=adapter.source_id(),
                asset=asset,
                fingerprint=None,
            )
            for adapter in ingest_service.build_adapters()
        ]

        cache_doc = consolidate_service.consolidate(observations, sources)

        repo.save(cache_doc)
        print(f">> Cache written to {settings.cache_path}")

    # ------------------------------------------------------------------
    # REPUTATION INGEST (Paso 1: plumbing + cache vacía)
    # ------------------------------------------------------------------
    elif cmd == "reputation-ingest":
        print(">> Running reputation ingest (Paso 1)...")

        # Import lazy para no romper 'ingest' si reputación no está montado
        from reputation.services import ReputationIngestService

        service = ReputationIngestService()
        doc = service.run()

        print(f">> Reputation generated_at: {doc.generated_at.isoformat()}")
        print(f">> config_hash: {doc.config_hash}")
        print(f">> items: {doc.stats.count}")

        if doc.sources_enabled:
            print(f">> sources_enabled: {', '.join(doc.sources_enabled)}")
        else:
            print(">> sources_enabled: (none)")

        if doc.stats.note:
            print(f">> note: {doc.stats.note}")

    # ------------------------------------------------------------------
    # COMANDO DESCONOCIDO
    # ------------------------------------------------------------------
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: brr ingest | brr reputation-ingest")
        sys.exit(1)


if __name__ == "__main__":
    main()
