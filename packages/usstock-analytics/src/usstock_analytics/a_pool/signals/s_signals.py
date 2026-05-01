"""A-pool exit signals S1-S3."""

from __future__ import annotations

from usstock_analytics.a_pool.signals.models import (
    APoolSnapshot,
    Calibration,
    signal,
)


def s1_support_breach(snapshot: APoolSnapshot) -> dict[str, object]:
    support = snapshot.rolling_low_20 or snapshot.rolling_low_60 or snapshot.mean_20d
    breach_level = support * 0.98
    triggered = support > 0 and snapshot.close < breach_level
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        close=snapshot.close,
        support=support,
        breach_level=breach_level,
    )


def s2a_fast_death_cross(snapshot: APoolSnapshot) -> dict[str, object]:
    triggered = (
        snapshot.prev_sma_20 is not None
        and snapshot.prev_sma_50 is not None
        and snapshot.sma_20 is not None
        and snapshot.sma_50 is not None
        and snapshot.prev_sma_20 >= snapshot.prev_sma_50
        and snapshot.sma_20 < snapshot.sma_50
    )
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        sma_20=snapshot.sma_20,
        sma_50=snapshot.sma_50,
        prev_sma_20=snapshot.prev_sma_20,
        prev_sma_50=snapshot.prev_sma_50,
    )


def s2b_slow_death_cross(snapshot: APoolSnapshot) -> dict[str, object]:
    triggered = (
        snapshot.prev_sma_50 is not None
        and snapshot.prev_sma_200 is not None
        and snapshot.sma_50 is not None
        and snapshot.sma_200 is not None
        and snapshot.prev_sma_50 >= snapshot.prev_sma_200
        and snapshot.sma_50 < snapshot.sma_200
    )
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        sma_50=snapshot.sma_50,
        sma_200=snapshot.sma_200,
        prev_sma_50=snapshot.prev_sma_50,
        prev_sma_200=snapshot.prev_sma_200,
    )


def s3_price_volume_divergence(
    snapshot: APoolSnapshot,
    calibration: Calibration,
) -> dict[str, object]:
    high_60 = snapshot.rolling_high_60 or snapshot.close
    max_rsi = snapshot.max_rsi_60 or snapshot.rsi14
    avg_volume = snapshot.avg_volume_20d or 0
    volume = snapshot.volume or 0
    at_high = snapshot.close >= high_60
    rsi_diverged = max_rsi - snapshot.rsi14 >= 5 and snapshot.rsi14 < calibration.rsi14_p80
    volume_diverged = avg_volume > 0 and volume < avg_volume * 0.8
    triggered = at_high and (rsi_diverged or volume_diverged)
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        close=snapshot.close,
        high_60=high_60,
        rsi14=snapshot.rsi14,
        max_rsi_60=max_rsi,
        volume=volume,
        avg_volume_20d=avg_volume,
    )
