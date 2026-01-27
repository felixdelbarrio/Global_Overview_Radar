from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
def evolution(request: Request, days: int = 90) -> Dict[str, Any]:
    """
    Serie temporal diaria:
    - abiertas
    - nuevas
    - cerradas
    """
    repo = request.app.state.cache_repo
    doc = repo.load()

    today = date.today()
    start = today - timedelta(days=days - 1)

    opened_map: Dict[date, int] = {}
    closed_map: Dict[date, int] = []
    intervals: List[tuple[date, date | None]] = []

    for rec in doc.incidents.values():
        cur = rec.current
        if cur.opened_at:
            opened_map[cur.opened_at] = opened_map.get(cur.opened_at, 0) + 1
            intervals.append((cur.opened_at, cur.closed_at))
        if cur.closed_at:
            closed_map.append(cur.closed_at)

    series: List[Dict[str, Any]] = []

    for i in range(days):
        d = start + timedelta(days=i)
        new_count = opened_map.get(d, 0)
        closed_count = sum(1 for c in closed_map if c == d)
        open_count = sum(
            1 for o, c in intervals if o <= d and (c is None or c > d)
        )

        series.append(
            {
                "date": d.isoformat(),
                "open": open_count,
                "new": new_count,
                "closed": closed_count,
            }
        )

    return {"days": days, "series": series}