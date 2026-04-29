"""M-pool L1 market dial."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from usstock_analytics.signals.m_pool.breadth import BreadthRow, percentile_rank
from usstock_analytics.signals.m_pool.hysteresis import apply_hysteresis, next_streak


@dataclass(frozen=True)
class MarketRow:
    trade_date: date
    spy_close: float
    sma_20: float
    sma_50: float
    sma_200: float
    vix_close: float
    vix_p5y: float
    vix_p95: float
    vix_10d_avg_p5y: float
    vix_jump_pct: float | None
    dist_to_monthly_high_pct: float
    has_blocking_event: bool


@dataclass(frozen=True)
class RegimeState:
    trade_date: date
    regime: str
    regime_prev: str | None
    regime_streak: int
    regime_changed: bool
    candidate_regime: str
    s_conditions_met: bool
    s_confirm_streak: int
    days_since_left_s: int


def market_row_for_date(
    spy_history: pd.DataFrame,
    vix_history: pd.DataFrame,
    events: pd.DataFrame,
    trade_date: date,
    params: dict[str, Any],
) -> MarketRow:
    spy = spy_history.copy().sort_values("trade_date")
    spy["trade_date"] = pd.to_datetime(spy["trade_date"]).dt.date
    vix = vix_history.copy().sort_values("trade_date")
    vix["trade_date"] = pd.to_datetime(vix["trade_date"]).dt.date
    spy_until = spy[spy["trade_date"] <= trade_date]
    vix_until = vix[vix["trade_date"] <= trade_date]
    if spy_until.empty or vix_until.empty:
        raise ValueError(f"Missing SPY or VIX history for {trade_date}")
    spy_row = spy_until.iloc[-1]
    vix_row = vix_until.iloc[-1]
    monthly_high = float(pd.to_numeric(spy_until.tail(21)["close"], errors="coerce").max())
    spy_close = float(spy_row["close"])
    dist_to_high = 0.0 if monthly_high == 0 else (monthly_high - spy_close) / monthly_high * 100
    vix_close = float(vix_row["vix"])
    vix_p5y = percentile_rank(vix_until["vix"], vix_close)
    vix_10d_avg = float(pd.to_numeric(vix_until.tail(10)["vix"], errors="coerce").mean())
    vix_10d_avg_p5y = percentile_rank(vix_until["vix"].rolling(10).mean(), vix_10d_avg)
    vix_p95 = float(vix_until["vix"].quantile(0.95))
    previous_vix = vix_until["vix"].shift(1).iloc[-1]
    vix_jump_pct = None
    if previous_vix and not pd.isna(previous_vix):
        vix_jump_pct = (vix_close / float(previous_vix) - 1) * 100
    return MarketRow(
        trade_date=trade_date,
        spy_close=spy_close,
        sma_20=float(spy_row["sma_20"]),
        sma_50=float(spy_row["sma_50"]),
        sma_200=float(spy_row["sma_200"]),
        vix_close=vix_close,
        vix_p5y=vix_p5y,
        vix_p95=vix_p95,
        vix_10d_avg_p5y=vix_10d_avg_p5y,
        vix_jump_pct=vix_jump_pct,
        dist_to_monthly_high_pct=dist_to_high,
        has_blocking_event=has_blocking_event(events, trade_date, params),
    )


def has_blocking_event(events: pd.DataFrame, trade_date: date, params: dict[str, Any]) -> bool:
    if events.empty:
        return False
    event_window_days = int(params["l1_regime"]["s_hard"]["h4_event_window_days"])
    blocking_types = set(params["events"]["blocking_types"])
    df = events.copy()
    df["event_date"] = pd.to_datetime(df["event_date"]).dt.date
    window_end = trade_date + timedelta(days=event_window_days)
    blocked = df[
        (df["event_date"] >= trade_date)
        & (df["event_date"] <= window_end)
        & (df["event_type"].isin(blocking_types))
    ]
    return not blocked.empty


def s_hard_conditions(
    market: MarketRow,
    breadth: BreadthRow,
    params: dict[str, Any],
) -> dict[str, bool]:
    hard = params["l1_regime"]["s_hard"]
    return {
        "h1_trend": market.dist_to_monthly_high_pct <= hard["h1_spy_dist_to_monthly_high_max_pct"],
        "h2_breadth": breadth.pct_above_200ma_p5y >= hard["h2_breadth_200ma_min_p5y"],
        "h3_vol": market.vix_p5y < hard["h3a_vix_max_p5y"]
        and market.vix_10d_avg_p5y < hard["h3b_vix_10d_avg_max_p5y"],
        "h4_event": not market.has_blocking_event,
    }


def s_soft_conditions(breadth: BreadthRow, params: dict[str, Any]) -> dict[str, bool]:
    soft = params["l1_regime"]["s_soft_any"]
    return {
        "s1_breadth_50ma": breadth.pct_above_50ma >= soft["s1_breadth_50ma_min_pct"],
        "s2_nh_nl": breadth.nh_nl_ratio >= soft["s2_nh_nl_min_ratio"],
        "s3_mcclellan": breadth.mcclellan >= soft["s3_mcclellan_min"],
    }


def s_conditions_met(market: MarketRow, breadth: BreadthRow, params: dict[str, Any]) -> bool:
    return all(s_hard_conditions(market, breadth, params).values()) and any(
        s_soft_conditions(breadth, params).values()
    )


def determine_base_regime(
    spy_close: float,
    sma_200: float,
    sma_50: float,
    vix_p5y: float,
    breadth_score: int,
) -> str:
    if vix_p5y >= 95 or breadth_score < 15:
        return "D"
    if spy_close < sma_200 or breadth_score < 30:
        return "C"
    if spy_close < sma_50 or breadth_score < 50:
        return "B"
    return "A"


def candidate_regime(
    market: MarketRow,
    breadth: BreadthRow,
    params: dict[str, Any],
    s_confirm_streak: int,
) -> tuple[str, bool, int]:
    s_ok = s_conditions_met(market, breadth, params)
    next_s_streak = s_confirm_streak + 1 if s_ok else 0
    if next_s_streak >= int(params["l1_regime"]["s_confirm_days"]):
        return "S", s_ok, next_s_streak
    base = determine_base_regime(
        market.spy_close,
        market.sma_200,
        market.sma_50,
        market.vix_p5y,
        breadth.score,
    )
    return base, s_ok, next_s_streak


def evaluate_regime(
    market: MarketRow,
    breadth: BreadthRow,
    params: dict[str, Any],
    prev_state: RegimeState | None = None,
) -> RegimeState:
    prev_regime = prev_state.regime if prev_state else None
    prev_streak = prev_state.regime_streak if prev_state else 0
    prev_s_confirm = prev_state.s_confirm_streak if prev_state else 0
    days_since_left_s = prev_state.days_since_left_s if prev_state else 999
    candidate, s_ok, next_s_confirm = candidate_regime(market, breadth, params, prev_s_confirm)
    regime = apply_hysteresis(
        prev_regime,
        prev_streak,
        candidate,
        days_since_left_s,
        market.vix_jump_pct,
        params,
    )
    if prev_regime == "S" and regime != "S":
        next_days_since_left_s = 0
    elif regime == "S":
        next_days_since_left_s = 999
    else:
        next_days_since_left_s = days_since_left_s + 1
    return RegimeState(
        trade_date=market.trade_date,
        regime=regime,
        regime_prev=prev_regime,
        regime_streak=next_streak(prev_regime, regime, prev_streak),
        regime_changed=prev_regime is not None and prev_regime != regime,
        candidate_regime=candidate,
        s_conditions_met=s_ok,
        s_confirm_streak=next_s_confirm,
        days_since_left_s=next_days_since_left_s,
    )
