from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import compute_indicators  # noqa: E402


def make_quotes_frame() -> pd.DataFrame:
    dates = pd.bdate_range("2025-04-29", periods=270)
    rows = []
    for idx, trade_date in enumerate(dates):
        spy_close = 420 + idx * 0.22 + (idx % 11) * 0.13
        nvda_close = 95 + idx * 0.48 + (idx % 13) * 0.41
        rows.extend(
            [
                {
                    "symbol": "SPY",
                    "trade_date": trade_date.date(),
                    "open": spy_close - 0.6,
                    "high": spy_close + 1.4,
                    "low": spy_close - 1.2,
                    "close": spy_close,
                    "adj_close": spy_close,
                    "volume": 50_000_000 + idx * 1000,
                },
                {
                    "symbol": "NVDA",
                    "trade_date": trade_date.date(),
                    "open": nvda_close - 0.8,
                    "high": nvda_close + 1.8,
                    "low": nvda_close - 1.5,
                    "close": nvda_close,
                    "adj_close": nvda_close,
                    "volume": 40_000_000 + idx * 2000,
                },
            ]
        )
    return pd.DataFrame(rows)


def reference_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return float((100 - (100 / (1 + rs))).where(avg_loss != 0, 100).iloc[-1])


def test_nvda_one_year_indicator_values_match_reference_formulas() -> None:
    quotes = make_quotes_frame()
    indicators = compute_indicators.compute_indicators(quotes)
    as_of = quotes["trade_date"].max()
    rows = compute_indicators.indicator_rows_for_date(indicators, as_of, ["NVDA"])
    assert len(rows) == 1
    row = rows[0]

    prepared = compute_indicators.prepare_quotes(quotes)
    nvda = prepared[prepared["symbol"] == "NVDA"].sort_values("trade_date")
    spy = prepared[prepared["symbol"] == "SPY"].sort_values("trade_date")
    close = nvda["close"]
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    nvda_ret = close.reset_index(drop=True).pct_change()
    spy_ret = spy["close"].reset_index(drop=True).pct_change()
    beta_60d = nvda_ret.rolling(60).cov(spy_ret) / spy_ret.rolling(60).var()

    assert row["sma_20"] == pytest.approx(float(close.tail(20).mean()), rel=0.01)
    assert row["rsi_14"] == pytest.approx(reference_rsi(close), rel=0.01)
    assert row["macd_line"] == pytest.approx(float(macd_line.iloc[-1]), rel=0.01)
    assert row["macd_signal"] == pytest.approx(float(macd_signal.iloc[-1]), rel=0.01)
    assert row["macd_histogram"] == pytest.approx(
        float((macd_line - macd_signal).iloc[-1]),
        rel=0.01,
    )
    assert row["beta_60d"] == pytest.approx(float(beta_60d.iloc[-1]), rel=0.01)


def test_daily_indicator_upsert_sql_is_idempotent() -> None:
    sql = compute_indicators.build_upsert_sql()

    assert "ON CONFLICT (symbol, trade_date) DO UPDATE SET" in sql
    assert "computed_at = now()" in sql
    assert sql.count("INSERT INTO daily_indicators") == 1


def test_indicator_rows_for_date_returns_only_requested_as_of_symbol() -> None:
    quotes = make_quotes_frame()
    indicators = compute_indicators.compute_indicators(quotes)
    as_of = quotes["trade_date"].max()

    rows = compute_indicators.indicator_rows_for_date(indicators, as_of, ["NVDA"])

    assert len(rows) == 1
    assert rows[0]["symbol"] == "NVDA"
    assert rows[0]["trade_date"] == as_of
    assert isinstance(rows[0]["obv"], int)
