from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

from bbva_bugresolutionradar.domain.enums import Severity
from bbva_bugresolutionradar.domain.models import IncidentRecord


@dataclass(frozen=True)
class KPIResult:
    open_total: int
    open_by_severity: Dict[Severity, int]

    new_total: int
    new_by_severity: Dict[Severity, int]
    new_masters: int

    closed_total: int
    closed_by_severity: Dict[Severity, int]

    mean_resolution_days_overall: Optional[float]
    mean_resolution_days_by_severity: Dict[Severity, float]

    open_over_threshold_pct: float
    open_over_threshold_list: List[str]


def _severity_counter_to_dict(counter: Counter[Severity]) -> Dict[Severity, int]:
    return {sev: int(counter.get(sev, 0)) for sev in Severity}


def compute_kpis(
    incidents: List[IncidentRecord],
    today: date,
    period_days: int,
    master_threshold_clients: int,
    stale_days_threshold: int,
) -> KPIResult:
    period_start = today - timedelta(days=period_days)

    open_items = [i for i in incidents if i.current.is_open]
    open_by_sev: Counter[Severity] = Counter([i.current.severity for i in open_items])

    new_items = [
        i
        for i in incidents
        if i.current.opened_at is not None and period_start <= i.current.opened_at <= today
    ]
    new_by_sev: Counter[Severity] = Counter([i.current.severity for i in new_items])
    new_masters = sum(1 for i in new_items if i.current.is_master(master_threshold_clients))

    closed_items = [
        i
        for i in incidents
        if i.current.closed_at is not None and period_start <= i.current.closed_at <= today
    ]
    closed_by_sev: Counter[Severity] = Counter([i.current.severity for i in closed_items])

    resolution_days: List[int] = []
    resolution_days_by_sev: Dict[Severity, List[int]] = {sev: [] for sev in Severity}

    for i in incidents:
        if i.current.opened_at is None or i.current.closed_at is None:
            continue
        d = (i.current.closed_at - i.current.opened_at).days
        if d < 0:
            continue
        resolution_days.append(d)
        resolution_days_by_sev[i.current.severity].append(d)

    mean_overall: Optional[float] = None
    if resolution_days:
        mean_overall = sum(resolution_days) / len(resolution_days)

    mean_by_sev: Dict[Severity, float] = {}
    for sev, values in resolution_days_by_sev.items():
        if values:
            mean_by_sev[sev] = sum(values) / len(values)

    over: List[str] = []
    for i in open_items:
        if i.current.opened_at is None:
            continue
        if (today - i.current.opened_at).days > stale_days_threshold:
            over.append(i.global_id)

    over_pct = 0.0
    if open_items:
        over_pct = (len(over) / len(open_items)) * 100.0

    return KPIResult(
        open_total=len(open_items),
        open_by_severity=_severity_counter_to_dict(open_by_sev),
        new_total=len(new_items),
        new_by_severity=_severity_counter_to_dict(new_by_sev),
        new_masters=new_masters,
        closed_total=len(closed_items),
        closed_by_severity=_severity_counter_to_dict(closed_by_sev),
        mean_resolution_days_overall=mean_overall,
        mean_resolution_days_by_severity=mean_by_sev,
        open_over_threshold_pct=over_pct,
        open_over_threshold_list=over,
    )
