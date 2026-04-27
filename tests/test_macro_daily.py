from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.us_stock.jobs import macro_daily  # noqa: E402


def test_incremental_next_fetch_date_uses_max_plus_one() -> None:
    assert macro_daily.next_fetch_date(date(2026, 4, 24), date(2026, 4, 28)) == date(
        2026,
        4,
        25,
    )


def test_single_source_null_tolerance_and_spread_calculation() -> None:
    rows = macro_daily.build_macro_upsert_rows(
        [
            macro_daily.MacroSourceRows(
                key="spy",
                rows=[{"trade_date": date(2026, 4, 27), "value": 599.25}],
            ),
            macro_daily.MacroSourceRows(
                key="us10y",
                rows=[{"trade_date": date(2026, 4, 27), "value": 4.25}],
            ),
            macro_daily.MacroSourceRows(
                key="us2y",
                rows=[{"trade_date": date(2026, 4, 27), "value": 3.75}],
            ),
        ]
    )

    assert len(rows) == 1
    assert rows[0]["spy"] == 599.25
    assert rows[0]["vix"] is None
    assert rows[0]["spread_10y_2y"] == 0.5
