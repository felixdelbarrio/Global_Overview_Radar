from __future__ import annotations

import sys
from pathlib import Path

from bbva_bugresolutionradar.config import settings
from bbva_bugresolutionradar.domain.models import RunSource
from bbva_bugresolutionradar.repositories import CacheRepo
from bbva_bugresolutionradar.services import ConsolidateService, IngestService


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: brr ingest")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "ingest":
        print(">> Running ingest pipeline...")

        repo = CacheRepo(settings.cache_path)
        ingest_service = IngestService(settings)
        consolidate_service = ConsolidateService()

        observations = ingest_service.ingest()
        print(f">> Observations read: {len(observations)}")

        asset = str(Path(settings.assets_dir).resolve())
        sources = [RunSource(source_id=a.source_id(), asset=asset, fingerprint=None) for a in ingest_service.build_adapters()]

        cache_doc = consolidate_service.consolidate(observations, sources)

        repo.save(cache_doc)
        print(f">> Cache written to {settings.cache_path}")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()