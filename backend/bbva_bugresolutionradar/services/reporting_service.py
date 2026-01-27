"""Servicio de reporting: calculo de KPIs sobre el cache consolidado."""

from __future__ import annotations

from datetime import date
from typing import Optional

from bbva_bugresolutionradar.config import Settings
from bbva_bugresolutionradar.domain.kpis import KPIResult, compute_kpis
from bbva_bugresolutionradar.domain.models import CacheDocument


class ReportingService:
    """Capa de servicio para exponer KPIs con defaults de configuracion."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def kpis(self, doc: CacheDocument, today: date, period_days: Optional[int] = None) -> KPIResult:
        """Calcula KPIs usando el periodo por defecto si no se provee."""
        pd = period_days if period_days is not None else self._settings.period_days_default
        incidents = list(doc.incidents.values())
        return compute_kpis(
            incidents=incidents,
            today=today,
            period_days=pd,
            master_threshold_clients=self._settings.master_threshold_clients,
            stale_days_threshold=self._settings.stale_days_threshold,
        )
