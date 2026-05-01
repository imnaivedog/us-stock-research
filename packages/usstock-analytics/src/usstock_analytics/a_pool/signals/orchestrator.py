"""Evaluate all 12 A-pool signal types."""

from __future__ import annotations

from usstock_analytics.a_pool.signals.b_signals import (
    b1_pullback_confirmed,
    b2_breakout_volume,
    b3_rsi_oversold_reversal,
    b4_macd_golden_cross_fresh,
    b5_support_bounce,
)
from usstock_analytics.a_pool.signals.models import APoolSnapshot, Calibration
from usstock_analytics.a_pool.signals.s_signals import (
    s1_support_breach,
    s2a_fast_death_cross,
    s2b_slow_death_cross,
    s3_price_volume_divergence,
)
from usstock_analytics.a_pool.signals.theme_signals import theme_oversold_entry
from usstock_analytics.a_pool.signals.w_signals import (
    w1_rsi_overheated,
    w2_thesis_aging,
)


def evaluate_signals(
    snapshot: APoolSnapshot,
    calibration: Calibration,
) -> dict[str, dict[str, object]]:
    if snapshot.shares_outstanding is None:
        return {
            "hold": {
                "triggered": True,
                "reason": "shares_outstanding_null",
                "strength": 1.0,
            }
        }
    return {
        "b1": b1_pullback_confirmed(snapshot, calibration),
        "b2": b2_breakout_volume(snapshot),
        "b3": b3_rsi_oversold_reversal(snapshot, calibration),
        "b4": b4_macd_golden_cross_fresh(snapshot),
        "b5": b5_support_bounce(snapshot),
        "s1": s1_support_breach(snapshot),
        "s2a": s2a_fast_death_cross(snapshot),
        "s2b": s2b_slow_death_cross(snapshot),
        "s3": s3_price_volume_divergence(snapshot, calibration),
        "w1": w1_rsi_overheated(snapshot, calibration),
        "w2": w2_thesis_aging(snapshot),
        "theme_oversold_entry": theme_oversold_entry(snapshot),
    }
