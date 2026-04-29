from __future__ import annotations

from datetime import date

from usstock_analytics.a_pool.signals.models import APoolSnapshot, Calibration
from usstock_analytics.a_pool.signals.orchestrator import evaluate_signals
from usstock_analytics.a_pool.signals.s_signals import s2a_thesis_break_mcap
from usstock_analytics.a_pool.signals.theme_signals import theme_oversold_entry


CAL = Calibration(rsi14_p20=30, rsi14_p80=70, drawdown_p10=-0.20)


def snap(**kwargs) -> APoolSnapshot:
    base = {
        "symbol": "NVDA",
        "date": date(2026, 4, 30),
        "close": 100,
        "rsi14": 25,
        "drawdown_60d": -0.25,
        "trendline_5y": 120,
        "mean_20d": 120,
        "std_20d": 10,
        "ret_60d": 60,
        "shares_outstanding": 10_000_000_000,
        "thesis_stop_mcap_b": 900,
        "target_mcap_b": 1000,
        "theme_quintile": "top",
        "theme_quintile_prev": "top",
        "theme_bottom_days": 0,
        "days_since_earnings": 5,
        "post_earnings_drop_pct": -6,
        "corporate_action_flags": ["split"],
    }
    base.update(kwargs)
    return APoolSnapshot(**base)


def test_b1_triggers_on_rsi_below_per_symbol_p20() -> None:
    assert evaluate_signals(snap(rsi14=29), CAL)["b1"]["triggered"] is True
    assert evaluate_signals(snap(rsi14=31), CAL)["b1"]["triggered"] is False


def test_s2a_uses_mcap_anchor_not_price() -> None:
    result = s2a_thesis_break_mcap(snap(close=100, thesis_stop_mcap_b=900))
    assert result["triggered"] is True
    assert result["current_mcap_b"] == 1000


def test_theme_oversold_entry_requires_top_quintile_and_rsi_below_50() -> None:
    assert theme_oversold_entry(snap(theme_quintile="top", rsi14=49))["triggered"] is True
    assert theme_oversold_entry(snap(theme_quintile="upper", rsi14=49))["triggered"] is False
    assert theme_oversold_entry(snap(theme_quintile="top", rsi14=51))["triggered"] is False


def test_signals_skip_with_hold_when_shares_outstanding_null() -> None:
    result = evaluate_signals(snap(shares_outstanding=None), CAL)
    assert result == {
        "hold": {"triggered": True, "reason": "shares_outstanding_null", "strength": 1.0}
    }


def test_all_12_signal_keys_present() -> None:
    result = evaluate_signals(snap(), CAL)
    assert set(result) == {
        "b1",
        "b2",
        "b3",
        "b4",
        "b5",
        "s1",
        "s2a",
        "s2b",
        "s3",
        "w1",
        "w2",
        "theme_oversold_entry",
    }
