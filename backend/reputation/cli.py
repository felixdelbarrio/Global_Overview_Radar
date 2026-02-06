"""CLI ligero para ejecutar solo la ingesta de reputación."""

from __future__ import annotations

import sys

from reputation.logging_utils import configure_logging, get_logger
from reputation.services.ingest_service import ReputationIngestService


def main() -> None:
    """Punto de entrada para la ingesta de reputación.

    Uso: reputation [--force]
    """
    configure_logging(force=True)
    logger = get_logger(__name__)

    force = False
    if len(sys.argv) > 1 and sys.argv[1] in ("--force", "-f"):
        force = True

    service = ReputationIngestService()
    doc = service.run(force=force)

    logger.info("Reputation generated_at: %s", doc.generated_at.isoformat())
    logger.info("config_hash: %s", doc.config_hash)
    logger.info("items: %s", doc.stats.count)


if __name__ == "__main__":
    main()
