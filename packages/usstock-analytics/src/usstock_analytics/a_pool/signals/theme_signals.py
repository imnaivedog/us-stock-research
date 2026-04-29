"""A-pool theme-driven entry signals."""

from __future__ import annotations

from usstock_analytics.a_pool.signals.models import APoolSnapshot, signal


def theme_oversold_entry(snapshot: APoolSnapshot) -> dict[str, object]:
    triggered = snapshot.theme_quintile == "top" and snapshot.rsi14 < 50
    return signal(
        triggered,
        min(1.0, (50 - snapshot.rsi14) / 25) if triggered else 0.0,
        theme_quintile=snapshot.theme_quintile,
        rsi14=snapshot.rsi14,
    )
