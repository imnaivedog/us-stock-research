"""A-pool signal input models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class APoolSnapshot:
    symbol: str
    date: date
    close: float
    rsi14: float
    drawdown_60d: float
    trendline_5y: float
    mean_20d: float
    std_20d: float
    ret_60d: float
    shares_outstanding: float | None
    thesis_stop_mcap_b: float
    target_mcap_b: float
    theme_quintile: str = "mid"
    theme_quintile_prev: str = "mid"
    theme_bottom_days: int = 0
    days_since_earnings: int | None = None
    post_earnings_drop_pct: float = 0.0
    corporate_action_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Calibration:
    rsi14_p20: float
    rsi14_p80: float
    drawdown_p10: float


def current_mcap_b(snapshot: APoolSnapshot) -> float | None:
    if snapshot.shares_outstanding is None:
        return None
    return snapshot.close * snapshot.shares_outstanding / 1_000_000_000


def price_from_mcap_b(mcap_b: float, shares_outstanding: float | None) -> float | None:
    if shares_outstanding is None or shares_outstanding <= 0:
        return None
    return mcap_b * 1_000_000_000 / shares_outstanding


def signal(triggered: bool, strength: float = 0.0, **payload: object) -> dict[str, object]:
    return {"triggered": triggered, "strength": strength, **payload}
