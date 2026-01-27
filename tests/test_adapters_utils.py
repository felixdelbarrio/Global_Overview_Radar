from __future__ import annotations

from datetime import date, datetime

from bbva_bugresolutionradar.adapters.utils import to_date, to_int, to_str


def test_to_str_handles_none_and_whitespace() -> None:
    assert to_str(None) is None
    assert to_str("") is None
    assert to_str("  abc  ") == "abc"


def test_to_int_handles_various_inputs() -> None:
    assert to_int(None) is None
    assert to_int("") is None
    assert to_int(True) is None
    assert to_int(12) == 12
    assert to_int(12.9) == 12
    assert to_int("  45 ") == 45
    assert to_int("3.14") == 3
    assert to_int("nope") is None


def test_to_date_parses_supported_formats() -> None:
    assert to_date(date(2025, 1, 1)) == date(2025, 1, 1)
    assert to_date(datetime(2025, 1, 2, 12, 0, 0)) == date(2025, 1, 2)
    assert to_date("2025-01-03") == date(2025, 1, 3)
    assert to_date("04/01/2025") == date(2025, 1, 4)
    assert to_date("2025/01/05") == date(2025, 1, 5)
    assert to_date("bad") is None
