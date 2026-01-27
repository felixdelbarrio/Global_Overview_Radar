from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from bbva_bugresolutionradar.adapters.filesystem import FilesystemAdapter
from bbva_bugresolutionradar.adapters.utils import to_date, to_int, to_str
from bbva_bugresolutionradar.domain.enums import Severity, Status
from bbva_bugresolutionradar.domain.models import ObservedIncident


def _parse_status(raw: str | None) -> Status:
    if raw is None:
        return Status.UNKNOWN
    v = raw.strip().upper()
    try:
        return Status(v)
    except ValueError:
        # heurística básica
        if "OPEN" in v or "ABIERT" in v:
            return Status.OPEN
        if "CLOSED" in v or "CERR" in v:
            return Status.CLOSED
        return Status.UNKNOWN


def _parse_severity(raw: str | None) -> Severity:
    if raw is None:
        return Severity.UNKNOWN
    v = raw.strip().upper()
    try:
        return Severity(v)
    except ValueError:
        if "CRIT" in v:
            return Severity.CRITICAL
        if "HIGH" in v or "ALTA" in v:
            return Severity.HIGH
        if "MED" in v or "MEDIA" in v:
            return Severity.MEDIUM
        if "LOW" in v or "BAJA" in v:
            return Severity.LOW
        return Severity.UNKNOWN


class FilesystemCSVAdapter(FilesystemAdapter):
    """
    Reads all *.csv files under assets_dir.
    Expected header fields (flexible): source_key/id, title, status, severity, opened_at, closed_at, updated_at, etc.
    """

    def read(self) -> list[ObservedIncident]:
        incidents: list[ObservedIncident] = []
        for path in sorted(self.assets_dir().glob("*.csv")):
            incidents.extend(self._read_file(path))
        return incidents

    def _read_file(self, path: Path) -> list[ObservedIncident]:
        observed_at = datetime.now().astimezone()
        out: list[ObservedIncident] = []

        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row_any in reader:
                row: dict[str, Any] = cast(dict[str, Any], row_any)

                source_key = to_str(row.get("source_key")) or to_str(row.get("id")) or ""
                if not source_key:
                    continue

                out.append(
                    ObservedIncident(
                        source_id=self.source_id(),
                        source_key=source_key,
                        observed_at=observed_at,
                        title=to_str(row.get("title")) or "",
                        status=_parse_status(to_str(row.get("status"))),
                        severity=_parse_severity(to_str(row.get("severity"))),
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
