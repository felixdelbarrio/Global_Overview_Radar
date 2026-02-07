"""CLI ligero para ejecutar solo la ingesta de reputación."""

from __future__ import annotations

import sys

from reputation.config import settings
from reputation.logging_utils import configure_logging, get_logger
from reputation.services.ingest_service import ReputationIngestService


def main() -> None:
    """Punto de entrada para la ingesta de reputación.

    Uso: brr-reputation [--force] [--all-sources]
    """
    configure_logging(force=True)
    logger = get_logger(__name__)

    force = False
    all_sources = False
    for arg in sys.argv[1:]:
        if arg in ("--force", "-f"):
            force = True
        elif arg in ("--all-sources", "--all"):
            all_sources = True

    service = ReputationIngestService()
    sources_override = settings.all_sources() if all_sources else None
    doc = service.run(force=force, sources_override=sources_override)

    logger.info("Reputation generated_at: %s", doc.generated_at.isoformat())
    logger.info("config_hash: %s", doc.config_hash)
    logger.info("items: %s", doc.stats.count)


if __name__ == "__main__":
    main()
