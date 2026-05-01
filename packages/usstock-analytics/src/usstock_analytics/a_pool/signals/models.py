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
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: float | None = None
    avg_volume_20d: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    prev_sma_20: float | None = None
    prev_sma_50: float | None = None
    prev_sma_200: float | None = None
    macd_line: float | None = None
    macd_signal: float | None = None
    prev_macd_line: float | None = None
    prev_macd_signal: float | None = None
    days_since_previous_macd_cross: int | None = None
    rolling_high_60: float | None = None
    rolling_low_20: float | None = None
    rolling_low_60: float | None = None
    max_rsi_60: float | None = None
    max_volume_60: float | None = None
    rsi14_history: tuple[float, ...] = ()
    thesis_age_days: int | None = None
    recent_b5_support: bool = False
    days_since_earnings: int | None = None
    post_earnings_drop_pct: float = 0.0
    corporate_action_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Calibration:
    rsi14_p20: float
    rsi14_p80: float
    drawdown_p10: float
    rsi14_p5: float | None = None
    rsi14_p95: float | None = None


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
