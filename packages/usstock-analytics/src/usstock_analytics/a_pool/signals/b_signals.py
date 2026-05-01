"""A-pool buy-entry signals B1-B5."""

from __future__ import annotations

from usstock_analytics.a_pool.signals.models import APoolSnapshot, Calibration, signal


def b1_pullback_confirmed(snapshot: APoolSnapshot, calibration: Calibration) -> dict[str, object]:
    """Pullback is near calibrated range while price remains above 200MA."""
    sma_200 = snapshot.sma_200 or snapshot.trendline_5y
    triggered = snapshot.close > sma_200 and snapshot.drawdown_60d <= calibration.drawdown_p10
    gap = max(0.0, calibration.drawdown_p10 - snapshot.drawdown_60d)
    return signal(
        triggered,
        min(1.0, gap / 0.25) if triggered else 0.0,
        close=snapshot.close,
        sma_200=sma_200,
        drawdown_60d=snapshot.drawdown_60d,
        threshold=calibration.drawdown_p10,
    )


def b2_breakout_volume(snapshot: APoolSnapshot) -> dict[str, object]:
    high_60 = snapshot.rolling_high_60 or snapshot.close
    avg_volume = snapshot.avg_volume_20d or 0
    volume = snapshot.volume or 0
    triggered = snapshot.close >= high_60 and avg_volume > 0 and volume > avg_volume * 1.5
    return signal(
        triggered,
        min(1.0, volume / (avg_volume * 1.5) - 1) if triggered else 0.0,
        close=snapshot.close,
        high_60=high_60,
        volume=volume,
        avg_volume_20d=avg_volume,
    )


def b3_rsi_oversold_reversal(
    snapshot: APoolSnapshot,
    calibration: Calibration,
) -> dict[str, object]:
    threshold = calibration.rsi14_p5 or calibration.rsi14_p20
    triggered = snapshot.rsi14 < threshold
    gap = max(0.0, threshold - snapshot.rsi14)
    return signal(
        triggered,
        min(1.0, gap / 20) if triggered else 0.0,
        rsi14=snapshot.rsi14,
        threshold=threshold,
    )


def b4_macd_golden_cross_fresh(snapshot: APoolSnapshot) -> dict[str, object]:
    has_cross = (
        snapshot.prev_macd_line is not None
        and snapshot.prev_macd_signal is not None
        and snapshot.macd_line is not None
        and snapshot.macd_signal is not None
        and snapshot.prev_macd_line <= snapshot.prev_macd_signal
        and snapshot.macd_line > snapshot.macd_signal
    )
    old_enough = (
        snapshot.days_since_previous_macd_cross is None
        or snapshot.days_since_previous_macd_cross >= 60
    )
    triggered = has_cross and old_enough
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        macd_line=snapshot.macd_line,
        macd_signal=snapshot.macd_signal,
        days_since_previous_cross=snapshot.days_since_previous_macd_cross,
    )


def b5_support_bounce(snapshot: APoolSnapshot) -> dict[str, object]:
    support = snapshot.rolling_low_20 or snapshot.rolling_low_60 or snapshot.mean_20d
    near_support = support > 0 and snapshot.close <= support * 1.03
    bullish_close = (
        (snapshot.open is not None and snapshot.close > snapshot.open)
        or (snapshot.prev_close is not None and snapshot.close > snapshot.prev_close)
    )
    triggered = near_support and bullish_close
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        close=snapshot.close,
        support=support,
        bullish_close=bullish_close,
    )
