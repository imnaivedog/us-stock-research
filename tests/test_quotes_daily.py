from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.us_stock.jobs import quotes_daily  # noqa: E402


def test_incremental_next_fetch_date_uses_max_plus_one() -> None:
    assert quotes_daily.next_fetch_date(date(2026, 4, 24), date(2026, 4, 28)) == date(
        2026, 4, 25
    )


def test_write_rate_safety_floor_triggers() -> None:
    with pytest.raises(RuntimeError, match="write rate below safety floor"):
        quotes_daily.enforce_write_rate(written_symbols=89, active_total=100)
