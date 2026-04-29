from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.signals._params import load_params  # noqa: E402
from src.signals.sectors import (  # noqa: E402
    absolute_cap,
    compute_sector_signals,
    conservative_quadrant,
    relative_quadrant,
    top_sector_payload,
    trend_score,
)


def sector_inputs():
    sectors = pd.read_csv("tests/fixtures/sectors_1y.csv", parse_dates=["trade_date"])
    stocks = pd.read_csv("tests/fixtures/sp_universe_1y.csv", parse_dates=["trade_date"])
    breadth = (
        stocks.groupby(["trade_date", "primary_sector"], as_index=False)["above_50ma"]
        .mean()
        .rename(columns={"primary_sector": "symbol", "above_50ma": "member_pct_above_50ma"})
    )
    breadth["member_pct_above_50ma"] *= 100
    return sectors, breadth


def test_trend_score_caps_at_100() -> None:
    row = pd.Series({"close": 120, "sma_20": 110, "sma_50": 100, "sma_200": 90})
    assert trend_score(row) == 100


def test_relative_quadrants() -> None:
    params = load_params()
    assert relative_quadrant(1, params) == "LEADING"
    assert relative_quadrant(5, params) == "NEUTRAL"
    assert relative_quadrant(11, params) == "LAGGING"


def test_absolute_cap() -> None:
    params = load_params()
    assert absolute_cap(75, params) == "LEADING"
    assert absolute_cap(20, params) == "WEAK"


def test_conservative_quadrant_takes_lower_track() -> None:
    params = load_params()
    assert conservative_quadrant(1, 20, params) == "WEAK"


def test_compute_sector_row_count() -> None:
    sectors, breadth = sector_inputs()
    signals = compute_sector_signals(sectors, breadth, load_params())
    assert len(signals) == 252 * 11


def test_xlk_has_leading_days() -> None:
    sectors, breadth = sector_inputs()
    signals = compute_sector_signals(sectors, breadth, load_params())
    assert sum(item.symbol == "XLK" and item.quadrant == "LEADING" for item in signals) >= 30


def test_xlu_has_lagging_days() -> None:
    sectors, breadth = sector_inputs()
    signals = compute_sector_signals(sectors, breadth, load_params())
    assert sum(item.symbol == "XLU" and item.quadrant == "LAGGING" for item in signals) >= 30


def test_top_sector_payload_returns_three() -> None:
    sectors, breadth = sector_inputs()
    signals = compute_sector_signals(sectors, breadth, load_params())
    top3, quadrant = top_sector_payload(signals, signals[-1].trade_date)
    assert len(top3) == 3
    assert "XLK" in quadrant
