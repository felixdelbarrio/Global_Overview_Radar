"""Tests del adapter XLSX."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import openpyxl  # type: ignore[import-untyped]

from bugresolutionradar.adapters.xlsx_adapter import XlsxAdapter
from bugresolutionradar.domain.enums import Severity, Status


def test_xlsx_adapter_reads_workbook(tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Reportes"
    ws.append(
        [
            "ID",
            "Fecha de incidente",
            "Estatus",
            "Criticidad",
            "Descripción",
            "Producto",
            "Funcionalidad",
        ]
    )
    ws.append(["INC-1", date(2025, 1, 10), "Resuelto", "Alta", "Fallo login", "App", "Login"])
    ws.append(["", date(2025, 1, 11), "", "Media", "Otro", "App", "Pagos"])

    path = tmp_path / "sample.xlsx"
    wb.save(path)

    adapter = XlsxAdapter("filesystem_xlsx", str(tmp_path))
    items = adapter.read()

    assert len(items) == 2
    first = items[0]
    second = items[1]

    assert first.source_key == "INC-1"
    assert first.status == Status.CLOSED
    assert first.severity == Severity.HIGH

    assert second.source_key.startswith("AUTO-")
    assert second.status == Status.OPEN
    assert second.severity == Severity.MEDIUM
