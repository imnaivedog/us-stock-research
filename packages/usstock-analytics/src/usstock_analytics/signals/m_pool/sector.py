"""M-pool L3 sector signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from usstock_analytics.signals.m_pool.breadth import clamp, percentile_rank

QUADRANT_ORDER = ["LAGGING", "WEAK", "NEUTRAL", "STRONG", "LEADING"]


@dataclass(frozen=True)
class SectorSignal:
    trade_date: date
    symbol: str
    score_trend: float
    score_rs: float
    score_breadth: float
    score_money_flow: float
    score_volatility: float
    total_score: float
    rank_relative: int
    pct_5y: float
    quadrant: str
    multiplier: float
    as_of_date: date


def trend_score(row: pd.Series) -> float:
    close = float(row["close"])
    score = 0.0
    if close > float(row["sma_200"]):
        score += 40
    if close > float(row["sma_50"]):
        score += 30
    if close > float(row["sma_20"]):
        score += 30
    if float(row["sma_20"]) > float(row["sma_50"]) > float(row["sma_200"]):
        score += 10
    return clamp(score)


def relative_quadrant(rank: int, params: dict[str, Any]) -> str:
    rel = params["l3_sectors"]["relative"]
    if rank <= rel["leading_top"]:
        return "LEADING"
    if rank <= rel["strong_top"]:
        return "STRONG"
    if rank <= rel["neutral_top"]:
        return "NEUTRAL"
    if rank <= rel["weak_top"]:
        return "WEAK"
    return "LAGGING"


def absolute_cap(pct_5y: float, params: dict[str, Any]) -> str:
    floor = params["l3_sectors"]["absolute_floor"]
    if pct_5y >= floor["leading_min_p5y"]:
        return "LEADING"
    if pct_5y >= floor["strong_min_p5y"]:
        return "STRONG"
    if pct_5y >= floor["neutral_min_p5y"]:
        return "NEUTRAL"
    return "WEAK"


def conservative_quadrant(rank: int, pct_5y: float, params: dict[str, Any]) -> str:
    rel = relative_quadrant(rank, params)
    cap = absolute_cap(pct_5y, params)
    return QUADRANT_ORDER[min(QUADRANT_ORDER.index(rel), QUADRANT_ORDER.index(cap))]


def compute_sector_signals(
    sectors: pd.DataFrame,
    member_breadth: pd.DataFrame,
    params: dict[str, Any],
) -> list[SectorSignal]:
    df = sectors.copy().sort_values(["trade_date", "symbol"])
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    for column in ("close", "sma_20", "sma_50", "sma_200"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    for column in ("ret_60d", "obv_20d_chg", "std_60"):
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
    breadth = member_breadth.copy()
    breadth["trade_date"] = pd.to_datetime(breadth["trade_date"]).dt.date
    df = df.merge(breadth, on=["trade_date", "symbol"], how="left")
    df["member_pct_above_50ma"] = pd.to_numeric(
        df["member_pct_above_50ma"], errors="coerce"
    ).fillna(50)
    df["score_trend"] = df.apply(trend_score, axis=1)
    outputs: list[SectorSignal] = []
    weights = params["l3_sectors"]["score_weights"]
    multipliers = params["l3_sectors"]["multipliers"]
    history_scores: dict[str, list[float]] = {}
    for trade_date, day in df.groupby("trade_date", sort=True):
        day = day.copy()
        day["score_rs"] = day["ret_60d"].rank(pct=True).fillna(0.5) * 100
        day["score_money_flow"] = day["obv_20d_chg"].rank(pct=True).fillna(0.5) * 100
        day["score_volatility"] = (1 - day["std_60"].rank(pct=True).fillna(0.5)) * 100
        day["score_breadth"] = day["member_pct_above_50ma"]
        day["total_score"] = (
            day["score_trend"] * weights["trend"]
            + day["score_rs"] * weights["rs"]
            + day["score_breadth"] * weights["breadth"]
            + day["score_money_flow"] * weights["money_flow"]
            + day["score_volatility"] * weights["volatility"]
        )
        day["total_score"] = day["total_score"].fillna(0)
        day["rank_relative"] = day["total_score"].rank(ascending=False, method="first").astype(int)
        for _, row in day.iterrows():
            symbol = str(row["symbol"])
            scores = history_scores.setdefault(symbol, [])
            scores.append(float(row["total_score"]))
            pct_5y = percentile_rank(pd.Series(scores), float(row["total_score"]))
            quadrant = conservative_quadrant(int(row["rank_relative"]), pct_5y, params)
            outputs.append(
                SectorSignal(
                    trade_date=trade_date,
                    symbol=symbol,
                    score_trend=round(float(row["score_trend"]), 2),
                    score_rs=round(float(row["score_rs"]), 2),
                    score_breadth=round(float(row["score_breadth"]), 2),
                    score_money_flow=round(float(row["score_money_flow"]), 2),
                    score_volatility=round(float(row["score_volatility"]), 2),
                    total_score=round(float(row["total_score"]), 2),
                    rank_relative=int(row["rank_relative"]),
                    pct_5y=round(pct_5y, 2),
                    quadrant=quadrant,
                    multiplier=float(multipliers[quadrant]),
                    as_of_date=trade_date,
                )
            )
    return outputs


def top_sector_payload(signals: list[SectorSignal], trade_date: date) -> tuple[list[dict], dict]:
    rows = [item for item in signals if item.trade_date == trade_date]
    top3 = sorted(rows, key=lambda item: item.total_score, reverse=True)[:3]
    quadrant = {item.symbol: item.quadrant for item in rows}
    return (
        [
            {"symbol": item.symbol, "score": item.total_score, "quadrant": item.quadrant}
            for item in top3
        ],
        quadrant,
    )
