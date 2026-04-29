from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.signals._params import load_params  # noqa: E402
from src.signals.themes import (  # noqa: E402
    compute_theme_signals,
    load_themes,
    top_theme_payload,
    volume_alert,
)


def stock_frame() -> pd.DataFrame:
    return pd.read_csv("tests/fixtures/sp_universe_1y.csv", parse_dates=["trade_date"])


def test_loads_eight_seed_themes() -> None:
    assert len(load_themes()) == 8


def test_volume_alert_sample_insufficient() -> None:
    assert volume_alert(2, 10, 100, load_params()) == "SAMPLE_INSUFFICIENT"


def test_volume_alert_red() -> None:
    assert volume_alert(18, 4, 99, load_params()) == "RED"


def test_theme_row_count() -> None:
    signals = compute_theme_signals(stock_frame(), load_themes(), load_params())
    assert len(signals) == 252 * 8


def test_ai_compute_is_frequent_top3() -> None:
    signals = compute_theme_signals(stock_frame(), load_themes(), load_params())
    assert sum(item.theme_id == "ai_compute" and item.rank <= 3 for item in signals) >= 120


def test_top_theme_payload_returns_three() -> None:
    signals = compute_theme_signals(stock_frame(), load_themes(), load_params())
    payload = top_theme_payload(signals, signals[-1].trade_date)
    assert len(payload) == 3
