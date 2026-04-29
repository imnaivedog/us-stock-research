from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.signals.macro import compute_macro_state, vote_macro_state  # noqa: E402


def test_macro_vote_risk_on() -> None:
    assert vote_macro_state({"SPY": 1, "HYG": 1, "LQD": 1, "TLT": -1}) == "risk_on"


def test_macro_vote_risk_off() -> None:
    assert vote_macro_state({"TLT": 1, "GLD": 1, "UUP": 1, "SPY": -1}) == "risk_off"


def test_macro_vote_neutral() -> None:
    assert vote_macro_state({"SPY": 1, "TLT": 1}) == "neutral"


def test_compute_macro_state_uses_close_vs_ma20() -> None:
    trade_date = date(2026, 4, 20)
    rows = []
    for symbol, prices in {
        "SPY": [10] * 19 + [12],
        "HYG": [10] * 19 + [12],
        "LQD": [10] * 19 + [12],
        "TLT": [10] * 19 + [8],
    }.items():
        for idx, close in enumerate(prices):
            rows.append({"symbol": symbol, "trade_date": date(2026, 4, 1 + idx), "close": close})
    result = compute_macro_state(pd.DataFrame(rows), trade_date)
    assert result.macro_state == "risk_on"
    assert result.symbol_states["SPY"] == 1
