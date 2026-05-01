from __future__ import annotations

from datetime import date

from usstock_analytics.a_pool.signals.models import APoolSnapshot, Calibration
from usstock_analytics.a_pool.signals.orchestrator import evaluate_signals
from usstock_analytics.a_pool.signals.s_signals import s2a_fast_death_cross
from usstock_analytics.a_pool.signals.theme_signals import theme_oversold_entry

CAL = Calibration(rsi14_p20=30, rsi14_p80=70, drawdown_p10=-0.20, rsi14_p5=25, rsi14_p95=80)


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
        "open": 98,
        "prev_close": 99,
        "volume": 2_000_000,
        "avg_volume_20d": 1_000_000,
        "sma_20": 100,
        "sma_50": 105,
        "sma_200": 90,
        "prev_sma_20": 106,
        "prev_sma_50": 105,
        "prev_sma_200": 110,
        "macd_line": 1.1,
        "macd_signal": 1.0,
        "prev_macd_line": 0.9,
        "prev_macd_signal": 1.0,
        "days_since_previous_macd_cross": 70,
        "rolling_high_60": 100,
        "rolling_low_20": 98,
        "rolling_low_60": 95,
        "max_rsi_60": 90,
        "max_volume_60": 2_000_000,
        "rsi14_history": (81, 82, 83),
        "thesis_age_days": 365 * 4,
        "recent_b5_support": True,
        "days_since_earnings": 5,
        "post_earnings_drop_pct": -6,
        "corporate_action_flags": ["split"],
    }
    base.update(kwargs)
    return APoolSnapshot(**base)


def test_b1_triggers_on_pullback_above_200ma() -> None:
    assert evaluate_signals(snap(close=100, sma_200=90, drawdown_60d=-0.25), CAL)["b1"][
        "triggered"
    ] is True
    assert evaluate_signals(snap(close=80, sma_200=90, drawdown_60d=-0.25), CAL)["b1"][
        "triggered"
    ] is False


def test_s2a_triggers_on_fast_death_cross() -> None:
    result = s2a_fast_death_cross(
        snap(prev_sma_20=101, prev_sma_50=100, sma_20=99, sma_50=100)
    )
    assert result["triggered"] is True
    assert result["sma_20"] == 99


def test_theme_oversold_entry_requires_bottom_quintile_stop_buffer_and_b5() -> None:
    assert theme_oversold_entry(
        snap(
            theme_quintile="bottom",
            theme_bottom_days=20,
            close=100,
            thesis_stop_mcap_b=700,
            recent_b5_support=True,
        )
    )["triggered"] is True
    assert theme_oversold_entry(
        snap(
            theme_quintile="top",
            theme_bottom_days=20,
            close=100,
            thesis_stop_mcap_b=700,
            recent_b5_support=True,
        )
    )["triggered"] is False
    assert theme_oversold_entry(
        snap(
            theme_quintile="bottom",
            theme_bottom_days=20,
            close=70,
            thesis_stop_mcap_b=700,
            recent_b5_support=True,
        )
    )["triggered"] is False


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
