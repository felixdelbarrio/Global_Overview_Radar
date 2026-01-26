from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from typing import Optional


def to_str(v: object) -> Optional[str]:
    """Convert any scalar to stripped string or None."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def to_int(v: object) -> Optional[int]:
    """Safely convert to int or return None."""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None
    return None


def to_date(v: object) -> Optional[Date]:
    """Parse YYYY-MM-DD strings into date, else None."""
    if v is None or v == "":
        return None
    if isinstance(v, Date):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return datetime.strptime(v, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None
