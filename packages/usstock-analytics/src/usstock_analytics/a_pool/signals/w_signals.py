"""A-pool warning signals W1-W2."""

from __future__ import annotations

from usstock_analytics.a_pool.signals.models import APoolSnapshot, signal

QUINTILE_ORDER = {"top": 4, "upper": 3, "mid": 2, "lower": 1, "bottom": 0}


def w1_theme_downgrade(snapshot: APoolSnapshot) -> dict[str, object]:
    prev = QUINTILE_ORDER.get(snapshot.theme_quintile_prev, 2)
    current = QUINTILE_ORDER.get(snapshot.theme_quintile, 2)
    triggered = prev - current >= 2
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        previous=snapshot.theme_quintile_prev,
        current=snapshot.theme_quintile,
    )


def w2_corporate_action_abnormal(snapshot: APoolSnapshot) -> dict[str, object]:
    triggered = bool(snapshot.corporate_action_flags)
    return signal(
        triggered,
        1.0 if triggered else 0.0,
        flags=snapshot.corporate_action_flags,
    )
