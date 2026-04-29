from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.signals._params import load_params  # noqa: E402
from src.signals.breadth import enrich_breadth_history, row_for_date  # noqa: E402
from src.signals.regime import (  # noqa: E402
    candidate_regime,
    determine_base_regime,
    evaluate_regime,
    market_row_for_date,
    s_conditions_met,
    s_hard_conditions,
    s_soft_conditions,
)


def frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv("tests/fixtures/spy_1y.csv", parse_dates=["trade_date"]),
        pd.read_csv("tests/fixtures/breadth_1y.csv", parse_dates=["trade_date"]),
        pd.read_csv("tests/fixtures/vix_1y.csv", parse_dates=["trade_date"]),
        pd.read_csv("tests/fixtures/events_calendar.csv", parse_dates=["event_date"]),
    )


def market_and_breadth(day: str):
    spy, breadth, vix, events = frames()
    params = load_params()
    enriched = enrich_breadth_history(breadth, params)
    trade_date = date.fromisoformat(day)
    return (
        market_row_for_date(spy, vix, events, trade_date, params),
        row_for_date(enriched, trade_date),
        params,
    )


def test_determine_base_regime_d_for_extreme_vix_percentile() -> None:
    assert determine_base_regime(500, 450, 480, 96, 80) == "D"


def test_determine_base_regime_c_when_spy_below_200ma() -> None:
    assert determine_base_regime(440, 450, 460, 50, 60) == "C"


def test_determine_base_regime_b_when_below_50ma() -> None:
    assert determine_base_regime(470, 450, 480, 50, 60) == "B"


def test_determine_base_regime_a_when_healthy() -> None:
    assert determine_base_regime(500, 450, 480, 50, 60) == "A"


def test_s_hard_conditions_are_true_in_strong_fixture_period() -> None:
    market, breadth, params = market_and_breadth("2025-09-01")
    hard = s_hard_conditions(market, breadth, params)
    assert all(hard.values())


def test_s_soft_conditions_have_any_true_in_strong_fixture_period() -> None:
    _, breadth, params = market_and_breadth("2025-09-01")
    soft = s_soft_conditions(breadth, params)
    assert any(soft.values())


def test_candidate_regime_requires_three_s_confirm_days() -> None:
    market, breadth, params = market_and_breadth("2025-09-01")
    assert s_conditions_met(market, breadth, params)
    assert candidate_regime(market, breadth, params, s_confirm_streak=1)[0] == "A"
    assert candidate_regime(market, breadth, params, s_confirm_streak=2)[0] == "S"


def test_evaluate_regime_demotes_s_immediately_when_hard_breaks() -> None:
    market, breadth, params = market_and_breadth("2025-09-01")
    state = evaluate_regime(market, breadth, params, None)
    state = evaluate_regime(market, breadth, params, state)
    state = evaluate_regime(market, breadth, params, state)
    assert state.regime == "S"
    weak_market, weak_breadth, _ = market_and_breadth("2026-01-05")
    next_state = evaluate_regime(weak_market, weak_breadth, params, state)
    assert next_state.regime != "S"
    assert next_state.regime_changed


def test_event_window_blocks_s_conditions() -> None:
    market, breadth, params = market_and_breadth("2025-06-27")
    assert market.has_blocking_event
    assert not s_conditions_met(market, breadth, params)
