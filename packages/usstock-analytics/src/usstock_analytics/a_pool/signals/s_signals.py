"""A-pool exit signals S1-S3."""

from __future__ import annotations

from usstock_analytics.a_pool.signals.models import (
    APoolSnapshot,
    Calibration,
    current_mcap_b,
    price_from_mcap_b,
    signal,
)


def s1_target_price(snapshot: APoolSnapshot) -> dict[str, object]:
    target_price = price_from_mcap_b(snapshot.target_mcap_b, snapshot.shares_outstanding)
    triggered = target_price is not None and snapshot.close >= target_price
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        close=snapshot.close,
        target_price=target_price,
    )


def s2a_thesis_break_mcap(snapshot: APoolSnapshot) -> dict[str, object]:
    current = current_mcap_b(snapshot)
    triggered = current is not None and current > snapshot.thesis_stop_mcap_b
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        current_mcap_b=current,
        thesis_stop_mcap_b=snapshot.thesis_stop_mcap_b,
    )


def s2b_theme_break(snapshot: APoolSnapshot) -> dict[str, object]:
    triggered = snapshot.theme_quintile == "bottom" and snapshot.theme_bottom_days > 20
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        theme_quintile=snapshot.theme_quintile,
        theme_bottom_days=snapshot.theme_bottom_days,
    )


def s3_overheated(snapshot: APoolSnapshot, calibration: Calibration) -> dict[str, object]:
    triggered = snapshot.rsi14 > calibration.rsi14_p80 and snapshot.ret_60d > 50
    return signal(
        triggered,
        min(1.0, (snapshot.rsi14 - calibration.rsi14_p80) / 20) if triggered else 0.0,
        rsi14=snapshot.rsi14,
        threshold=calibration.rsi14_p80,
        ret_60d=snapshot.ret_60d,
    )
