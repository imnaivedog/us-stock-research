from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from src.signals.breadth import clamp
from src.signals.sectors import SectorSignal
from src.signals.themes import ThemeConfig, ThemeSignal


@dataclass(frozen=True)
class StockSignal:
    trade_date: date
    symbol: str
    total_score: float
    technical_score: float
    fundamental_score: float
    theme_bonus: float
    sector_multiplier: float
    rank: int
    is_top5: bool
    entry_pattern: str | None
    primary_sector: str | None
    primary_theme: str | None
    as_of_date: date


def trend_strength(row: pd.Series) -> float:
    close = float(row["close"])
    above = sum(
        [
            close > float(row["sma_200"]),
            close > float(row["sma_50"]),
            close > float(row["sma_20"]),
            float(row["sma_20"]) > float(row["sma_50"]) > float(row["sma_200"]),
        ]
    )
    return [0, 30, 60, 90, 100][above]


def momentum_score(row: pd.Series) -> float:
    macd = 50 if float(row["macd_histogram"]) > 0 else 0
    rsi = float(row["rsi_14"])
    return macd + (50 if 50 <= rsi <= 70 else 0)


def primary_theme(symbol: str, themes: list[ThemeConfig]) -> str | None:
    for theme in themes:
        if symbol in {*theme.core, *theme.diffusion, *theme.concept}:
            return theme.id
    return None


def theme_bonus(
    symbol: str,
    theme_ranks: dict[str, int],
    themes: list[ThemeConfig],
    params: dict[str, Any],
) -> float:
    theme_id = primary_theme(symbol, themes)
    bonus_map = params["l4_stocks"]["theme_bonus_map"]
    if theme_id is None:
        return float(bonus_map["not_in_themes"])
    rank = theme_ranks.get(theme_id, 999)
    if rank <= 3:
        return float(bonus_map["in_top3"])
    if rank <= 8:
        return float(bonus_map["in_top4_to_8"])
    return float(bonus_map["not_in_themes"])


def entry_pattern(row: pd.Series, params: dict[str, Any]) -> str | None:
    entry = params["l4_stocks"]["entry"]
    if bool(row.get("is_breakout_20d")) and float(row["volume_ratio_20d"]) >= float(
        entry["breakout_volume_multiplier"]
    ):
        return "BREAKOUT"
    close = float(row["close"])
    near_50 = abs(close - float(row["sma_50"])) / float(row["sma_50"]) * 100
    near_20 = abs(close - float(row["sma_20"])) / float(row["sma_20"]) * 100
    if (
        near_50 <= float(entry["pullback_to_ma50_tolerance_pct"])
        or near_20 <= float(entry["pullback_to_ma20_tolerance_pct"])
    ) and bool(row.get("macd_hist_cross_up")):
        return "PULLBACK"
    return None


def compute_stock_signals(
    stocks: pd.DataFrame,
    sectors: list[SectorSignal],
    themes: list[ThemeConfig],
    theme_signals: list[ThemeSignal],
    params: dict[str, Any],
) -> list[StockSignal]:
    df = stocks.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    numeric_columns = [
        "close",
        "sma_20",
        "sma_50",
        "sma_200",
        "macd_histogram",
        "rsi_14",
        "ret_60d",
        "obv_5d_slope",
        "volume_ratio_20d",
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    sector_multiplier = {(item.trade_date, item.symbol): item.multiplier for item in sectors}
    outputs: list[StockSignal] = []
    weights = params["l4_stocks"]["technical_weights"]
    total_weights = params["l4_stocks"]["total_score_weights"]
    top_n = int(params["l4_stocks"]["top_n"])
    fundamental = float(params["l4_stocks"]["fundamental_score_placeholder"])
    for trade_date, day in df.groupby("trade_date", sort=True):
        day = day.copy()
        day["trend_strength"] = day.apply(trend_strength, axis=1)
        day["momentum"] = day.apply(momentum_score, axis=1)
        day["relative_strength"] = day["ret_60d"].rank(pct=True) * 100
        day["volume_trend"] = day["obv_5d_slope"].rank(pct=True) * 100
        theme_ranks = {
            item.theme_id: item.rank for item in theme_signals if item.trade_date == trade_date
        }
        scores = []
        for _, row in day.iterrows():
            symbol = str(row["symbol"])
            sector = str(row.get("primary_sector") or "")
            technical = (
                float(row["trend_strength"]) * weights["trend_strength"]
                + float(row["momentum"]) * weights["momentum"]
                + float(row["relative_strength"]) * weights["relative_strength"]
                + float(row["volume_trend"]) * weights["volume_trend"]
            )
            bonus = theme_bonus(symbol, theme_ranks, themes, params)
            multiplier = float(sector_multiplier.get((trade_date, sector), 1.0))
            total = (
                technical * total_weights["technical"]
                + fundamental * total_weights["fundamental"]
                + bonus * total_weights["theme_bonus"]
            ) * multiplier
            scores.append(
                {
                    "symbol": symbol,
                    "total": clamp(total),
                    "technical": clamp(technical),
                    "bonus": bonus,
                    "multiplier": multiplier,
                    "sector": sector or None,
                    "theme": primary_theme(symbol, themes),
                    "entry": entry_pattern(row, params),
                }
            )
        ranked = sorted(scores, key=lambda row: row["total"], reverse=True)
        for rank, row in enumerate(ranked, start=1):
            outputs.append(
                StockSignal(
                    trade_date=trade_date,
                    symbol=row["symbol"],
                    total_score=round(row["total"], 2),
                    technical_score=round(row["technical"], 2),
                    fundamental_score=fundamental,
                    theme_bonus=round(row["bonus"], 2),
                    sector_multiplier=round(row["multiplier"], 3),
                    rank=rank,
                    is_top5=rank <= top_n,
                    entry_pattern=row["entry"],
                    primary_sector=row["sector"],
                    primary_theme=row["theme"],
                    as_of_date=trade_date,
                )
            )
    return outputs
