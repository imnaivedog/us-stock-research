from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

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
    assert rows[0]["us2y"] == 3.75
    assert rows[0]["spread_10y_2y"] == pytest.approx(0.5)


def test_treasury_window_uses_independent_lookback() -> None:
    incremental_start = date(2026, 4, 28)
    end_date = date(2026, 4, 28)

    assert macro_daily.source_start_date("SPY", incremental_start, end_date) == date(
        2026,
        4,
        28,
    )
    assert macro_daily.source_start_date(
        "treasury_rates:year10",
        incremental_start,
        end_date,
    ) == date(2026, 4, 14)

    rows = macro_daily.build_macro_upsert_rows(
        [
            macro_daily.MacroSourceRows(
                key="us10y",
                rows=[
                    {"trade_date": date(2026, 4, 14), "value": 4.2},
                    {"trade_date": date(2026, 4, 24), "value": 4.3},
                ],
            )
        ]
    )
    assert [row["trade_date"] for row in rows] == [date(2026, 4, 14), date(2026, 4, 24)]


def test_spread_is_null_when_either_treasury_leg_is_null() -> None:
    rows = macro_daily.build_macro_upsert_rows(
        [
            macro_daily.MacroSourceRows(
                key="us10y",
                rows=[
                    {"trade_date": date(2026, 4, 24), "value": 4.31},
                    {"trade_date": date(2026, 4, 25), "value": 4.30},
                ],
            ),
            macro_daily.MacroSourceRows(
                key="us2y",
                rows=[{"trade_date": date(2026, 4, 24), "value": 3.81}],
            ),
        ]
    )

    assert rows[0]["spread_10y_2y"] == pytest.approx(0.5)
    assert rows[1]["spread_10y_2y"] is None


def test_all_null_macro_rows_are_not_written() -> None:
    rows = macro_daily.build_macro_upsert_rows(
        [
            macro_daily.MacroSourceRows(
                key="spy",
                rows=[{"trade_date": date(2026, 4, 26), "value": None}],
            ),
            macro_daily.MacroSourceRows(
                key="us10y",
                rows=[{"trade_date": date(2026, 4, 26), "value": None}],
            ),
        ]
    )

    assert rows == []
