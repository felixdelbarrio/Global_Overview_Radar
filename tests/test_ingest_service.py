"""Tests del servicio de ingest y construccion de adapters."""

from __future__ import annotations

import json
from pathlib import Path

from bbva_bugresolutionradar.config import Settings
from bbva_bugresolutionradar.services.ingest_service import IngestService


def test_ingest_service_combines_sources(tmp_path: Path) -> None:
    (tmp_path / "incidents.csv").write_text(
        "source_key,title,status,severity,opened_at\nINC-1,Login error,OPEN,HIGH,2025-01-10\n",
        encoding="utf-8",
    )
    (tmp_path / "incidents.json").write_text(
        json.dumps(
            [
                {
                    "source_key": "INC-2",
                    "title": "Pago lento",
                    "status": "CLOSED",
                    "severity": "LOW",
                    "opened_at": "2025-01-08",
                    "closed_at": "2025-01-09",
                }
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(
        ASSETS_DIR=str(tmp_path),
        SOURCES="filesystem_csv,filesystem_json",
    )

    service = IngestService(settings)
    items = service.ingest()

    assert len(items) == 2
    source_ids = sorted({i.source_id for i in items})
    assert source_ids == ["filesystem_csv", "filesystem_json"]


def test_build_adapters_respects_enabled_sources(tmp_path: Path) -> None:
    settings = Settings(
        ASSETS_DIR=str(tmp_path),
        SOURCES="filesystem_xlsx",
    )
    service = IngestService(settings)
    adapters = service.build_adapters()

    assert len(adapters) == 1
    assert adapters[0].source_id() == "filesystem_xlsx"
