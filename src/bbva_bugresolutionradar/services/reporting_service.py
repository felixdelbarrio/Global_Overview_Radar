from __future__ import annotations

from datetime import date
from typing import Optional

from bbva_bugresolutionradar.config import Settings
from bbva_bugresolutionradar.domain.kpis import KPIResult, compute_kpis
from bbva_bugresolutionradar.domain.models import CacheDocument


class ReportingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def kpis(self, doc: CacheDocument, today: date, period_days: Optional[int] = None) -> KPIResult:
        pd = period_days if period_days is not None else self._settings.period_days_default
        incidents = list(doc.incidents.values())
        return compute_kpis(
            incidents=incidents,
            today=today,
            period_days=pd,
            master_threshold_clients=self._settings.master_threshold_clients,
            stale_days_threshold=self._settings.stale_days_threshold,
        )
