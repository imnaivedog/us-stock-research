"""A-pool three-dimension scoring."""

from __future__ import annotations

from dataclasses import dataclass

from usstock_analytics.a_pool.signals.models import (
    APoolSnapshot,
    price_from_mcap_b,
)


@dataclass(frozen=True)
class ScoreResult:
    a_score: float
    score_breakdown: dict[str, float]
    thesis_stop_price: float | None
    target_price: float | None


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def elasticity_score(snapshot: APoolSnapshot) -> float:
    if snapshot.close <= 0:
        return 0.0
    volatility_pct = snapshot.std_20d / snapshot.close * 100
    trend_discount_pct = max(0.0, (snapshot.trendline_5y - snapshot.close) / snapshot.close * 100)
    return clamp(volatility_pct * 2.0 + trend_discount_pct)


def value_score(snapshot: APoolSnapshot) -> float:
    if snapshot.shares_outstanding is None or snapshot.target_mcap_b <= 0:
        return 0.0
    current_mcap_b = snapshot.close * snapshot.shares_outstanding / 1_000_000_000
    discount = 1 - current_mcap_b / snapshot.target_mcap_b
    return clamp(discount * 100)


def rr_score(snapshot: APoolSnapshot) -> tuple[float, float | None, float | None]:
    thesis_stop_price = price_from_mcap_b(snapshot.thesis_stop_mcap_b, snapshot.shares_outstanding)
    target_price = price_from_mcap_b(snapshot.target_mcap_b, snapshot.shares_outstanding)
    if thesis_stop_price is None or target_price is None:
        return 0.0, thesis_stop_price, target_price
    downside = snapshot.close - thesis_stop_price
    upside = target_price - snapshot.close
    if downside <= 0 or upside <= 0:
        return 0.0, thesis_stop_price, target_price
    return clamp((upside / downside) * 25), thesis_stop_price, target_price


def theme_bonus(snapshot: APoolSnapshot, signals: dict[str, dict[str, object]]) -> float:
    if snapshot.theme_quintile == "top":
        return 5.0
    theme_entry = signals.get("theme_oversold_entry", {})
    if snapshot.theme_quintile == "bottom" and theme_entry.get("triggered") is True:
        return 3.0
    return 0.0


def score_a_pool(snapshot: APoolSnapshot, signals: dict[str, dict[str, object]]) -> ScoreResult:
    if snapshot.shares_outstanding is None:
        return ScoreResult(
            a_score=0.0,
            score_breakdown={
                "elasticity": 0.0,
                "value": 0.0,
                "rr": 0.0,
                "theme_bonus": 0.0,
            },
            thesis_stop_price=None,
            target_price=None,
        )

    elasticity = elasticity_score(snapshot)
    value = value_score(snapshot)
    rr, thesis_stop_price, target_price = rr_score(snapshot)
    bonus = theme_bonus(snapshot, signals)
    total = elasticity * 0.35 + value * 0.30 + rr * 0.35 + bonus
    return ScoreResult(
        a_score=round(total, 2),
        score_breakdown={
            "elasticity": round(elasticity, 2),
            "value": round(value, 2),
            "rr": round(rr, 2),
            "theme_bonus": bonus,
        },
        thesis_stop_price=thesis_stop_price,
        target_price=target_price,
    )
