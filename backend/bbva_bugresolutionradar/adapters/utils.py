from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def to_str(v: object) -> Optional[str]:
    """
    Convert any scalar value to a stripped string or None.
    Safe for Excel cells, numbers, dates, etc.
    """
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def to_int(v: object) -> Optional[int]:
    """
    Safely convert a value to int.
    Handles Excel numbers, numeric strings, floats, etc.
    """
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
            return int(float(s))
        except ValueError:
            return None
    return None


def to_date(v: object) -> Optional[date]:
    """
    Convert Excel / string values to date.
    Supports:
      - date
      - datetime
      - strings: YYYY-MM-DD, DD/MM/YYYY, YYYY/MM/DD
    """
    if v is None or v == "":
        return None

    if isinstance(v, date) and not isinstance(v, datetime):
        return v

    if isinstance(v, datetime):
        return v.date()

    if isinstance(v, str):
        s = v.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    return None
