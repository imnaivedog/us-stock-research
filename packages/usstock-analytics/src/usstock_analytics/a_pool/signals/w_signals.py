"""A-pool warning signals W1-W2."""

from __future__ import annotations

from usstock_analytics.a_pool.signals.models import (
    APoolSnapshot,
    Calibration,
    price_from_mcap_b,
    signal,
)


def w1_rsi_overheated(snapshot: APoolSnapshot, calibration: Calibration) -> dict[str, object]:
    threshold = calibration.rsi14_p95 or calibration.rsi14_p80
    history = snapshot.rsi14_history or (snapshot.rsi14,)
    last_three = history[-3:]
    triggered = len(last_three) == 3 and all(value > threshold for value in last_three)
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        rsi14=snapshot.rsi14,
        threshold=threshold,
        rsi14_history=last_three,
    )


def w2_thesis_aging(snapshot: APoolSnapshot) -> dict[str, object]:
    target_price = price_from_mcap_b(snapshot.target_mcap_b, snapshot.shares_outstanding)
    triggered = (
        snapshot.thesis_age_days is not None
        and snapshot.thesis_age_days > 365 * 3
        and target_price is not None
        and snapshot.close < target_price * 0.5
    )
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        thesis_age_days=snapshot.thesis_age_days,
        close=snapshot.close,
        target_price=target_price,
    )
