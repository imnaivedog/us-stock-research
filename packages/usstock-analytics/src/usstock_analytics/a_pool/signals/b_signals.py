"""A-pool buy-entry signals B1-B5."""

from __future__ import annotations

from usstock_analytics.a_pool.signals.models import APoolSnapshot, Calibration, signal


def b1_rsi_oversold(snapshot: APoolSnapshot, calibration: Calibration) -> dict[str, object]:
    triggered = snapshot.rsi14 < calibration.rsi14_p20
    gap = max(0.0, calibration.rsi14_p20 - snapshot.rsi14)
    return signal(
        triggered,
        min(1.0, gap / 20),
        rsi14=snapshot.rsi14,
        threshold=calibration.rsi14_p20,
    )


def b2_drawdown_extreme(snapshot: APoolSnapshot, calibration: Calibration) -> dict[str, object]:
    triggered = snapshot.drawdown_60d < calibration.drawdown_p10
    gap = max(0.0, calibration.drawdown_p10 - snapshot.drawdown_60d)
    return signal(
        triggered,
        min(1.0, gap / 0.25),
        drawdown_60d=snapshot.drawdown_60d,
        threshold=calibration.drawdown_p10,
    )


def b3_below_trendline(snapshot: APoolSnapshot) -> dict[str, object]:
    threshold = snapshot.trendline_5y * 0.90
    triggered = snapshot.close <= threshold
    return signal(triggered, 1.0 if triggered else 0.0, close=snapshot.close, threshold=threshold)


def b4_post_earnings_pullback(snapshot: APoolSnapshot) -> dict[str, object]:
    in_window = snapshot.days_since_earnings is not None and 0 <= snapshot.days_since_earnings <= 10
    triggered = in_window and snapshot.post_earnings_drop_pct <= -5
    return signal(
        triggered,
        min(1.0, abs(snapshot.post_earnings_drop_pct) / 15) if triggered else 0.0,
        days_since_earnings=snapshot.days_since_earnings,
        post_earnings_drop_pct=snapshot.post_earnings_drop_pct,
    )


def b5_mean_reversion(snapshot: APoolSnapshot) -> dict[str, object]:
    threshold = snapshot.mean_20d - 1.5 * snapshot.std_20d
    triggered = snapshot.close < threshold
    return signal(triggered, 1.0 if triggered else 0.0, close=snapshot.close, threshold=threshold)
