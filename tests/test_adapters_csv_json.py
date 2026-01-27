"""Tests de adapters CSV y JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bbva_bugresolutionradar.adapters.csv_adapter import FilesystemCSVAdapter
from bbva_bugresolutionradar.adapters.json_adapter import FilesystemJSONAdapter
from bbva_bugresolutionradar.domain.enums import Severity, Status


def test_csv_adapter_parses_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "incidents.csv"
    csv_path.write_text(
        "source_key,title,status,severity,opened_at,closed_at,updated_at,clients_affected,product,feature\n"
        "INC-1,Login error,Abierto,Alta,2025-01-10,,2025-01-11,12,Mobile,Login\n"
        ",Missing id,Open,High,2025-01-10,,2025-01-11,1,Mobile,Login\n",
        encoding="utf-8",
    )

    adapter = FilesystemCSVAdapter("filesystem_csv", str(tmp_path))
    items = adapter.read()

    assert len(items) == 1
    item = items[0]
    assert item.source_id == "filesystem_csv"
    assert item.source_key == "INC-1"
    assert item.status == Status.OPEN
    assert item.severity == Severity.HIGH
    assert item.clients_affected == 12
    assert item.product == "Mobile"
    assert item.feature == "Login"


def test_json_adapter_parses_list(tmp_path: Path) -> None:
    json_path = tmp_path / "incidents.json"
    payload = [
        {
            "source_key": "INC-2",
            "title": "Pago lento",
            "status": "CLOSED",
            "severity": "MEDIUM",
            "opened_at": "2025-01-01",
            "closed_at": "2025-01-02",
            "clients_affected": "7",
        }
    ]
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    adapter = FilesystemJSONAdapter("filesystem_json", str(tmp_path))
    items = adapter.read()

    assert len(items) == 1
    item = items[0]
    assert item.source_id == "filesystem_json"
    assert item.source_key == "INC-2"
    assert item.status == Status.CLOSED
    assert item.severity == Severity.MEDIUM
    assert item.clients_affected == 7


def test_json_adapter_rejects_non_list(tmp_path: Path) -> None:
    json_path = tmp_path / "bad.json"
    json_path.write_text(json.dumps({"a": 1}), encoding="utf-8")

    adapter = FilesystemJSONAdapter("filesystem_json", str(tmp_path))

    with pytest.raises(ValueError, match="JSON asset must be a list"):
        adapter.read()
