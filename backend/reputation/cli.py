"""CLI ligero para ejecutar solo la ingesta de reputación."""

from __future__ import annotations

import sys

from reputation.services.ingest_service import ReputationIngestService


def main() -> None:
    """Punto de entrada para la ingesta de reputación.

    Uso: brr-reputation [--force]
    """
    force = False
    if len(sys.argv) > 1 and sys.argv[1] in ("--force", "-f"):
        force = True

    service = ReputationIngestService()
    doc = service.run(force=force)

    print(f">> Reputation generated_at: {doc.generated_at.isoformat()}")
    print(f">> config_hash: {doc.config_hash}")
    print(f">> items: {doc.stats.count}")


if __name__ == "__main__":
    main()
