"""CLI para ejecutar ingest y consolidacion desde terminal."""

from __future__ import annotations

import sys
from pathlib import Path

from bugresolutionradar.config import settings
from bugresolutionradar.domain.models import RunSource
from bugresolutionradar.logging_utils import configure_logging, get_logger
from bugresolutionradar.repositories import CacheRepo
from bugresolutionradar.services import ConsolidateService, IngestService


def main() -> None:
    """Punto de entrada CLI (soporta comandos 'ingest' y 'reputation-ingest')."""
    configure_logging(force=True)
    logger = get_logger(__name__)

    if len(sys.argv) < 2:
        logger.error("Usage: brr ingest | brr reputation-ingest")
        sys.exit(1)

    cmd = sys.argv[1]

    # ------------------------------------------------------------------
    # INGEST ACTUAL (incidencias / cuadros de mando)
    # ------------------------------------------------------------------
    if cmd == "ingest":
        logger.info("Running incidents dashboard ingest...")

        repo = CacheRepo(settings.cache_path)
        ingest_service = IngestService(settings)
        consolidate_service = ConsolidateService()

        observations = ingest_service.ingest()
        logger.info("Observations read: %s", len(observations))

        asset = str(Path(settings.assets_dir).resolve())
        sources = [
            RunSource(
                source_id=adapter.source_id(),
                asset=asset,
                fingerprint=None,
            )
            for adapter in ingest_service.build_adapters()
        ]

        existing = repo.load()
        cache_doc = consolidate_service.consolidate_incremental(existing, observations, sources)

        repo.save(cache_doc)
        print(f"Incidents: {len(cache_doc.incidents)}")
        print(f"Observations: {len(observations)}")
        print(f"Sources: {len(sources)}")
        logger.info("Cache written to %s", settings.cache_path)

    # ------------------------------------------------------------------
    # REPUTATION INGEST (Paso 1: plumbing + cache vacía)
    # ------------------------------------------------------------------
    elif cmd == "reputation-ingest":
        logger.info("Running reputation ingest...")

        # Import lazy para no romper 'ingest' si reputación no está montado
        from reputation.services import ReputationIngestService

        service = ReputationIngestService()
        doc = service.run()

        print(f"Reputation items: {doc.stats.count}")
        logger.info("Reputation generated_at: %s", doc.generated_at.isoformat())
        logger.info("config_hash: %s", doc.config_hash)
        logger.info("items: %s", doc.stats.count)

        if doc.sources_enabled:
            logger.info("sources_enabled: %s", ", ".join(doc.sources_enabled))
        else:
            logger.info("sources_enabled: (none)")

        if doc.stats.note:
            logger.info("note: %s", doc.stats.note)

    # ------------------------------------------------------------------
    # COMANDO DESCONOCIDO
    # ------------------------------------------------------------------
    else:
        logger.error("Unknown command: %s", cmd)
        logger.error("Usage: brr ingest | brr reputation-ingest")
        sys.exit(1)


if __name__ == "__main__":
    main()
