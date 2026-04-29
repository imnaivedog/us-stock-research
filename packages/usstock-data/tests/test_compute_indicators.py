from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from usstock_data.derived.compute_indicators import compute_rows_for_symbols, prepare_quotes


def _quote_rows(symbol: str, start: date, closes: list[float]) -> list[dict[str, object]]:
    rows = []
    for idx, close in enumerate(closes):
        rows.append(
            {
                "symbol": symbol,
                "trade_date": start + timedelta(days=idx),
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "adj_close": close,
                "volume": 1000,
            }
        )
    return rows


def test_prepare_quotes_is_idempotent_for_double_call() -> None:
    quotes = pd.DataFrame(
        _quote_rows("SPY", date(2026, 1, 1), [100, 101, 102])
        + _quote_rows("AAPL", date(2026, 1, 1), [10, 11, 12])
    )
    once = prepare_quotes(quotes)
    twice = prepare_quotes(once)
    assert "spy_ret" in twice.columns
    assert "stock_ret" in twice.columns
    assert "spy_ret_x" not in twice.columns
    assert "spy_ret_y" not in twice.columns


def test_compute_rows_for_symbols_survives_prepared_quotes() -> None:
    start = date(2025, 8, 1)
    closes = [float(100 + idx) for idx in range(260)]
    quotes = pd.DataFrame(_quote_rows("SPY", start, closes) + _quote_rows("AAPL", start, closes))
    prepared = prepare_quotes(quotes)
    rows, failed = compute_rows_for_symbols(prepared, start + timedelta(days=259), ["AAPL"])
    assert failed == []
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"
