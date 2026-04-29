from __future__ import annotations

from datetime import date

from usstock_data.etl.corporate_actions import dividend_rows, event_rows, split_rows
from usstock_data.etl.earnings_calendar import calendar_rows
from usstock_data.etl.fundamentals import fundamentals_rows
from usstock_data.etl.macro_daily import build_macro_rows
from usstock_data.etl.quotes_daily import quote_rows


def test_quote_rows_maps_fmp_history() -> None:
    rows = quote_rows(
        "AAPL",
        [
            {
                "date": "2026-04-29",
                "open": "1",
                "high": "2",
                "low": "0.5",
                "close": "1.5",
                "adjClose": "1.4",
                "volume": "10",
            }
        ],
    )
    assert rows == [
        {
            "symbol": "AAPL",
            "trade_date": date(2026, 4, 29),
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "adj_close": 1.4,
            "volume": 10,
            "asset_class": "equity",
        }
    ]


def test_macro_rows_compute_spreads_and_alias_yields() -> None:
    rows = build_macro_rows(
        [
            type(
                "SourceRows",
                (),
                {"key": "hyg", "rows": [{"trade_date": date(2026, 4, 29), "value": 80.0}]},
            ),
            type(
                "SourceRows",
                (),
                {"key": "lqd", "rows": [{"trade_date": date(2026, 4, 29), "value": 100.0}]},
            ),
            type(
                "SourceRows",
                (),
                {"key": "us10y", "rows": [{"trade_date": date(2026, 4, 29), "value": 4.5}]},
            ),
            type(
                "SourceRows",
                (),
                {"key": "us2y", "rows": [{"trade_date": date(2026, 4, 29), "value": 4.0}]},
            ),
        ]
    )
    assert rows[0]["hyg_lqd_spread"] == -20.0
    assert rows[0]["spread_10y_2y"] == 0.5
    assert rows[0]["dgs10"] == 4.5
    assert rows[0]["dgs2"] == 4.0


def test_corporate_actions_mirror_to_events() -> None:
    actions = split_rows("NVDA", [{"date": "2024-06-10", "numerator": 10}])
    actions += dividend_rows("NVDA", [{"date": "2024-07-01", "dividend": 0.01}])
    events = event_rows(actions)
    assert {event["event_type"] for event in events} == {"split", "dividend"}
    assert events[0]["symbol"] == "NVDA"


def test_fundamentals_merge_income_cash_flow_and_surprises() -> None:
    rows = fundamentals_rows(
        "MSFT",
        [{"date": "2026-03-31", "period": "Q3", "revenue": 1, "eps": 2, "netIncome": 3}],
        [{"date": "2026-03-31", "operatingCashFlow": 4, "freeCashFlow": 5}],
        [{"date": "2026-03-31", "actualEarningResult": 2.1, "estimatedEarning": 2.0}],
    )
    assert rows[0]["eps_actual"] == 2.1
    assert rows[0]["free_cash_flow"] == 5.0


def test_earnings_calendar_rows_use_events_calendar_shape() -> None:
    rows = calendar_rows([{"symbol": "aapl", "date": "2026-05-01", "epsEstimated": 1.2}])
    assert rows == [
        {
            "symbol": "AAPL",
            "event_date": date(2026, 5, 1),
            "event_type": "earnings",
            "details": {"symbol": "aapl", "date": "2026-05-01", "epsEstimated": 1.2},
        }
    ]
