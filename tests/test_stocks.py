from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.signals._params import load_params  # noqa: E402
from src.signals.sectors import compute_sector_signals  # noqa: E402
from src.signals.stocks import (  # noqa: E402
    compute_stock_signals,
    momentum_score,
    primary_theme,
    theme_bonus,
    trend_strength,
)
from src.signals.themes import compute_theme_signals, load_themes  # noqa: E402


def inputs():
    sectors = pd.read_csv("tests/fixtures/sectors_1y.csv", parse_dates=["trade_date"])
    stocks = pd.read_csv("tests/fixtures/sp_universe_1y.csv", parse_dates=["trade_date"])
    breadth = (
        stocks.groupby(["trade_date", "primary_sector"], as_index=False)["above_50ma"]
        .mean()
        .rename(columns={"primary_sector": "symbol", "above_50ma": "member_pct_above_50ma"})
    )
    breadth["member_pct_above_50ma"] *= 100
    params = load_params()
    themes = load_themes()
    sector_signals = compute_sector_signals(sectors, breadth, params)
    theme_signals = compute_theme_signals(stocks, themes, params)
    return stocks, sector_signals, themes, theme_signals, params


def test_trend_strength_five_levels() -> None:
    row = pd.Series({"close": 120, "sma_20": 110, "sma_50": 100, "sma_200": 90})
    assert trend_strength(row) == 100


def test_momentum_score_macd_and_rsi() -> None:
    assert momentum_score(pd.Series({"macd_histogram": 1, "rsi_14": 60})) == 100


def test_primary_theme_matches_core_symbol() -> None:
    assert primary_theme("NVDA", load_themes()) == "ai_compute"


def test_theme_bonus_top3() -> None:
    assert theme_bonus("NVDA", {"ai_compute": 1}, load_themes(), load_params()) == 80


def test_stock_row_count() -> None:
    signals = compute_stock_signals(*inputs())
    assert len(signals) == 252 * 30


def test_top5_count_per_day() -> None:
    signals = compute_stock_signals(*inputs())
    by_day = {}
    for item in signals:
        by_day.setdefault(item.trade_date, 0)
        by_day[item.trade_date] += int(item.is_top5)
    assert set(by_day.values()) == {5}


def test_nvda_frequent_top5() -> None:
    signals = compute_stock_signals(*inputs())
    assert sum(item.symbol == "NVDA" and item.is_top5 for item in signals) >= 120


def test_entry_pattern_is_optional_known_value() -> None:
    signals = compute_stock_signals(*inputs())
    assert {item.entry_pattern for item in signals} <= {None, "BREAKOUT", "PULLBACK"}
