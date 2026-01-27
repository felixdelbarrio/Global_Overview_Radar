"""Endpoints de KPIs ejecutivos."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
def get_kpis(request: Request, period_days: Optional[int] = None) -> Dict[str, Any]:
    """Devuelve KPIs agregados a partir del cache consolidado."""
    cache_repo = request.app.state.cache_repo
    reporting = request.app.state.reporting

    doc = cache_repo.load()
    result = reporting.kpis(doc=doc, today=date.today(), period_days=period_days)

    return {
        "open_total": result.open_total,
        "open_by_severity": {k.value: v for k, v in result.open_by_severity.items()},
        "new_total": result.new_total,
        "new_by_severity": {k.value: v for k, v in result.new_by_severity.items()},
        "new_masters": result.new_masters,
        "closed_total": result.closed_total,
        "closed_by_severity": {k.value: v for k, v in result.closed_by_severity.items()},
        "mean_resolution_days_overall": result.mean_resolution_days_overall,
        "mean_resolution_days_by_severity": {
            k.value: v for k, v in result.mean_resolution_days_by_severity.items()
        },
        "open_over_threshold_pct": result.open_over_threshold_pct,
        "open_over_threshold_list": result.open_over_threshold_list,
    }
