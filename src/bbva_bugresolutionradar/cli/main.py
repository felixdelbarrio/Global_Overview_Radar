from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime

import uvicorn

from bbva_bugresolutionradar.config import settings
from bbva_bugresolutionradar.domain.models import RunSource
from bbva_bugresolutionradar.repositories import CacheRepo
from bbva_bugresolutionradar.services import ConsolidateService, IngestService


@dataclass(frozen=True)
class Exit:
    code: int = 0


def cmd_ingest() -> Exit:
    ingest = IngestService(settings)
    observations = ingest.ingest()

    sources = [
        RunSource(source_id=s, asset=settings.assets_dir, fingerprint=None)
        for s in settings.enabled_sources()
    ]

    repo = CacheRepo(settings.cache_path)
    doc = repo.load()

    consolidator = ConsolidateService()
    updated = consolidator.consolidate(existing=doc, observations=observations, sources=sources)
    repo.save(updated)

    print(
        f"[OK] Consolidated {len(observations)} observations into {len(updated.incidents)} incidents"
    )
    print(f"[OK] Cache: {settings.cache_path}")
    print(f"[OK] Generated at: {updated.generated_at.isoformat()}")
    return Exit(0)


def cmd_serve(host: str, port: int) -> Exit:
    # FastAPI app import path
    uvicorn.run("bbva_bugresolutionradar.api.main:app", host=host, port=port, reload=True)
    return Exit(0)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="brr", description="BBVA BugResolutionRadar CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ingest", help="Ingest assets and consolidate into cache.json")

    sp = sub.add_parser("serve", help="Serve FastAPI")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)

    return p


def app() -> None:
    parser = build_parser()
    args = parser.parse_args()

    started = datetime.now().astimezone()
    print(f"[INFO] {settings.app_name} - {started.isoformat()}")

    if args.cmd == "ingest":
        raise SystemExit(cmd_ingest().code)
    if args.cmd == "serve":
        raise SystemExit(cmd_serve(args.host, args.port).code)

    raise SystemExit(2)
