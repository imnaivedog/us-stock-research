"""Evaluate all 12 A-pool signal types."""

from __future__ import annotations

from usstock_analytics.a_pool.signals.b_signals import (
    b1_rsi_oversold,
    b2_drawdown_extreme,
    b3_below_trendline,
    b4_post_earnings_pullback,
    b5_mean_reversion,
)
from usstock_analytics.a_pool.signals.models import APoolSnapshot, Calibration
from usstock_analytics.a_pool.signals.s_signals import (
    s1_target_price,
    s2a_thesis_break_mcap,
    s2b_theme_break,
    s3_overheated,
)
from usstock_analytics.a_pool.signals.theme_signals import theme_oversold_entry
from usstock_analytics.a_pool.signals.w_signals import (
    w1_theme_downgrade,
    w2_corporate_action_abnormal,
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
        "b1": b1_rsi_oversold(snapshot, calibration),
        "b2": b2_drawdown_extreme(snapshot, calibration),
        "b3": b3_below_trendline(snapshot),
        "b4": b4_post_earnings_pullback(snapshot),
        "b5": b5_mean_reversion(snapshot),
        "s1": s1_target_price(snapshot),
        "s2a": s2a_thesis_break_mcap(snapshot),
        "s2b": s2b_theme_break(snapshot),
        "s3": s3_overheated(snapshot, calibration),
        "w1": w1_theme_downgrade(snapshot),
        "w2": w2_corporate_action_abnormal(snapshot),
        "theme_oversold_entry": theme_oversold_entry(snapshot),
    }
