"""A-pool theme-driven entry signals."""

from __future__ import annotations

from usstock_analytics.a_pool.signals.models import APoolSnapshot, price_from_mcap_b, signal


def theme_oversold_entry(snapshot: APoolSnapshot) -> dict[str, object]:
    thesis_stop_price = price_from_mcap_b(snapshot.thesis_stop_mcap_b, snapshot.shares_outstanding)
    above_stop_buffer = (
        thesis_stop_price is not None and snapshot.close > thesis_stop_price * 1.3
    )
    triggered = (
        snapshot.theme_quintile == "bottom"
        and snapshot.theme_bottom_days >= 20
        and above_stop_buffer
        and snapshot.recent_b5_support
    )
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        theme_quintile=snapshot.theme_quintile,
        theme_bottom_days=snapshot.theme_bottom_days,
        thesis_stop_price=thesis_stop_price,
        recent_b5_support=snapshot.recent_b5_support,
    )
