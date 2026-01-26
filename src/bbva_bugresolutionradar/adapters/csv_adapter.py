from __future__ import annotations

import csv
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, cast

from bbva_bugresolutionradar.adapters.filesystem import FilesystemAdapter
from bbva_bugresolutionradar.adapters.utils import to_date, to_int, to_str
from bbva_bugresolutionradar.domain.enums import Severity, Status
from bbva_bugresolutionradar.domain.models import ObservedIncident


def _parse_status(raw: Optional[str]) -> Status:
    if raw is None:
        return Status.UNKNOWN
    try:
        return Status(raw.upper())
    except ValueError:
        return Status.UNKNOWN


def _parse_severity(raw: Optional[str]) -> Severity:
    if raw is None:
        return Severity.UNKNOWN
    try:
        return Severity(raw.upper())
    except ValueError:
        return Severity.UNKNOWN


class FilesystemCSVAdapter(FilesystemAdapter):
    """
    Reads CSV files under assets_dir.
    Expected header containing at least: source_key,title,status,severity
    """

    def read(self) -> List[ObservedIncident]:
        incidents: List[ObservedIncident] = []
        for path in sorted(self.assets_dir().glob("*.csv")):
            incidents.extend(self._read_file(path))
        return incidents

    def _read_file(self, path: Path) -> List[ObservedIncident]:
        observed_at = datetime.now().astimezone()
        out: List[ObservedIncident] = []

        with path.open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for raw_row in reader:
                row = cast(Mapping[str, Any], raw_row)

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
