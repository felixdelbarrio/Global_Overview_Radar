"""Adapter JSON: lee ficheros JSON y genera ObservedIncident."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, cast

from bugresolutionradar.adapters.filesystem import FilesystemAdapter
from bugresolutionradar.adapters.utils import to_date, to_int, to_str
from bugresolutionradar.domain.enums import Severity, Status
from bugresolutionradar.domain.models import ObservedIncident


def _parse_status(raw: Optional[str]) -> Status:
    """Normaliza el campo de estado desde texto."""
    if raw is None:
        return Status.UNKNOWN
    try:
        return Status(raw.upper())
    except ValueError:
        return Status.UNKNOWN


def _parse_severity(raw: Optional[str]) -> Severity:
    """Normaliza el campo de severidad desde texto."""
    if raw is None:
        return Severity.UNKNOWN
    try:
        return Severity(raw.upper())
    except ValueError:
        return Severity.UNKNOWN


class FilesystemJSONAdapter(FilesystemAdapter):
    """Lee todos los JSON dentro de assets_dir.

    Formato esperado: lista de objetos con al menos:
    - source_key
    - title
    - status
    - severity

    Opcionales: opened_at, closed_at, updated_at (YYYY-MM-DD), clients_affected,
    product, feature, resolution_type.
    """

    def read(self) -> List[ObservedIncident]:
        """Lee todos los JSON y devuelve observaciones."""
        incidents: List[ObservedIncident] = []
        for path in sorted(self.assets_dir().glob("*.json")):
            incidents.extend(self._read_file(path))
        return incidents

    def _read_file(self, path: Path) -> List[ObservedIncident]:
        """Parsea un JSON y devuelve observaciones."""
        observed_at = datetime.now().astimezone()
        raw = path.read_text(encoding="utf-8")
        loaded: Any = json.loads(raw)

        if not isinstance(loaded, list):
            raise ValueError(f"JSON asset must be a list: {path}")

        # Help Pyright/Pylance: force a concrete element type instead of Unknown
        data: List[object] = cast(List[object], loaded)

        out: List[ObservedIncident] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            row = cast(Mapping[str, Any], item)

            source_key_raw = row.get("source_key") or row.get("id") or ""
            source_key = str(source_key_raw).strip()
            if not source_key:
                continue

            status_raw = to_str(row.get("status"))
            severity_raw = to_str(row.get("severity"))

            out.append(
                ObservedIncident(
                    source_id=self.source_id(),
                    source_key=source_key,
                    observed_at=observed_at,
                    title=str(row.get("title") or ""),
                    status=_parse_status(status_raw),
                    severity=_parse_severity(severity_raw),
                    opened_at=to_date(row.get("opened_at")),
                    closed_at=to_date(row.get("closed_at")),
                    updated_at=to_date(row.get("updated_at")),
                    clients_affected=to_int(row.get("clients_affected")),
                    product=to_str(row.get("product")),
                    feature=to_str(row.get("feature")),
                    resolution_type=to_str(row.get("resolution_type")),
                )
            )

        return out
