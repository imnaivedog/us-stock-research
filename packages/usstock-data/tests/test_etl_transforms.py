from __future__ import annotations

from datetime import date

from loguru import logger
from usstock_data.etl.corporate_actions import (
    collect_action_results,
    dividend_rows,
    event_rows,
    split_rows,
)
from usstock_data.etl.earnings_calendar import calendar_rows
from usstock_data.etl.fmp_client import FMPTransientError
from usstock_data.etl.fundamentals import collect_fundamental_results, fundamentals_rows
from usstock_data.etl.macro_daily import build_macro_rows
from usstock_data.etl.quotes_daily import quote_rows
from usstock_data.etl.shares_outstanding import row_from_polygon_response, warn_row


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


def test_shares_outstanding_rows_maps_polygon_response() -> None:
    row = row_from_polygon_response(
        "nvda",
        {"results": {"share_class_shares_outstanding": 24_000_000_000}},
    )
    assert row is not None
    assert row.symbol == "NVDA"
    assert row.shares_outstanding == 24_000_000_000


def test_shares_outstanding_etl_skips_null_response_with_warn() -> None:
    assert row_from_polygon_response("NVDA", {"results": {}}) is None
    alert = warn_row("nvda", "missing")
    assert alert["severity"] == "WARN"
    assert alert["category"] == "shares_outstanding"


def test_corporate_actions_skip_expected_exception_without_error_log() -> None:
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="DEBUG", format="{level}:{message}")
    try:
        rows, success_count, skip_count = collect_action_results(
            ["AAPL", "MSFT"], [[{"symbol": "AAPL"}], RuntimeError("tier unsupported")]
        )
    finally:
        logger.remove(sink_id)

    assert rows == [{"symbol": "AAPL"}]
    assert success_count == 1
    assert skip_count == 1
    text = "\n".join(messages)
    assert "ERROR:" not in text
    assert "DEBUG:corporate_actions skip MSFT" in text
    assert "INFO:corporate_actions done: 1 success / 1 skipped / 2 total" in text


def test_fundamentals_skip_expected_exception_without_error_log() -> None:
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="DEBUG", format="{level}:{message}")
    try:
        rows, success_count, skip_count = collect_fundamental_results(
            ["AAPL", "MSFT"], [[{"symbol": "AAPL"}], RuntimeError("tier unsupported")]
        )
    finally:
        logger.remove(sink_id)

    assert rows == [{"symbol": "AAPL"}]
    assert success_count == 1
    assert skip_count == 1
    text = "\n".join(messages)
    assert "ERROR:" not in text
    assert "DEBUG:fundamentals skip MSFT" in text
    assert "INFO:fundamentals done: 1 success / 1 skipped / 2 total" in text


def test_fundamentals_transient_exception_still_logs_error() -> None:
    messages: list[str] = []
    sink_id = logger.add(messages.append, level="DEBUG", format="{level}:{message}")
    try:
        rows, success_count, skip_count = collect_fundamental_results(
            ["AAPL"], [FMPTransientError("FMP transient status 429")]
        )
    finally:
        logger.remove(sink_id)

    assert rows == []
    assert success_count == 0
    assert skip_count == 1
    assert "ERROR:fundamentals failed for AAPL" in "\n".join(messages)
