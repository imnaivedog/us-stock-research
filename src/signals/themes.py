from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.signals.breadth import percentile_rank


@dataclass(frozen=True)
class ThemeConfig:
    id: str
    name: str
    core: list[str]
    diffusion: list[str]
    concept: list[str]
    inception_date: date


@dataclass(frozen=True)
class ThemeSignal:
    trade_date: date
    theme_id: str
    theme_name: str
    state: str
    rank: int
    total_score: float
    volume_ratio_3m: float
    volume_pct_1y: float
    volume_alert: str
    core_avg_change_pct: float
    diffusion_avg_change_pct: float
    as_of_date: date


def load_themes(path: Path | str = Path("config/themes.yaml")) -> list[ThemeConfig]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    themes = []
    for item in payload.get("themes", []):
        themes.append(
            ThemeConfig(
                id=str(item["id"]),
                name=str(item["name"]),
                core=[str(symbol) for symbol in item.get("core", [])],
                diffusion=[str(symbol) for symbol in item.get("diffusion", [])],
                concept=[str(symbol) for symbol in item.get("concept", [])],
                inception_date=date.fromisoformat(str(item["inception_date"])),
            )
        )
    return themes


def avg_change(stocks: pd.DataFrame, symbols: list[str]) -> float:
    subset = stocks[stocks["symbol"].isin(symbols)]
    if subset.empty:
        return 0.0
    value = pd.to_numeric(subset["chg_pct"], errors="coerce").mean()
    return 0.0 if pd.isna(value) else float(value)


def volume_ratio(stocks: pd.DataFrame, symbols: list[str]) -> float:
    subset = stocks[stocks["symbol"].isin(symbols)]
    if subset.empty:
        return 0.0
    value = pd.to_numeric(subset["volume_ratio_20d_3m"], errors="coerce").mean()
    return 0.0 if pd.isna(value) else float(value)


def volume_alert(age_months: int, ratio: float, pct_1y: float, params: dict[str, Any]) -> str:
    config = params["l4_themes"]["volume_alert"]
    if age_months < int(config["min_theme_age_months"]):
        return "SAMPLE_INSUFFICIENT"
    if pct_1y >= config["red_pct_1y"] and ratio >= config["red_volume_ratio"]:
        return "RED"
    if pct_1y >= config["yellow_pct_1y"] and ratio >= config["yellow_volume_ratio"]:
        return "YELLOW"
    return "NONE"


def state_for_theme(rank: int, volume_flag: str, core_above_50ma_pct: float) -> str:
    if rank <= 3 and core_above_50ma_pct >= 80:
        return "ACCELERATING"
    if volume_flag in {"YELLOW", "RED"}:
        return "LAUNCHING"
    if core_above_50ma_pct < 50:
        return "DECAYING"
    return "INCUBATING"


def compute_theme_signals(
    stocks: pd.DataFrame,
    themes: list[ThemeConfig],
    params: dict[str, Any],
) -> list[ThemeSignal]:
    df = stocks.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    for column in ("chg_pct", "volume_ratio_20d_3m", "above_50ma"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    weights = params["l4_themes"]["basket_weights"]
    history: dict[str, list[float]] = {theme.id: [] for theme in themes}
    outputs: list[ThemeSignal] = []
    for trade_date, day in df.groupby("trade_date", sort=True):
        rows = []
        for theme in themes:
            core_change = avg_change(day, theme.core)
            diffusion_change = avg_change(day, theme.diffusion)
            total_score = core_change * weights["core"] + diffusion_change * weights["diffusion"]
            ratio = volume_ratio(day, [*theme.core, *theme.diffusion, *theme.concept])
            history[theme.id].append(ratio)
            volume_pct = percentile_rank(pd.Series(history[theme.id]), ratio)
            age_months = max(0, (trade_date - theme.inception_date).days // 30)
            core = day[day["symbol"].isin(theme.core)]
            core_above_raw = core["above_50ma"].mean() if not core.empty else 0.0
            core_above = 0.0 if pd.isna(core_above_raw) else float(core_above_raw * 100)
            rows.append(
                {
                    "theme": theme,
                    "core_change": core_change,
                    "diffusion_change": diffusion_change,
                    "total_score": total_score,
                    "ratio": ratio,
                    "volume_pct": volume_pct,
                    "core_above": core_above,
                    "volume_alert": volume_alert(age_months, ratio, volume_pct, params),
                }
            )
        ranked = sorted(rows, key=lambda row: row["total_score"], reverse=True)
        for rank, row in enumerate(ranked, start=1):
            theme = row["theme"]
            state = state_for_theme(rank, row["volume_alert"], row["core_above"])
            outputs.append(
                ThemeSignal(
                    trade_date=trade_date,
                    theme_id=theme.id,
                    theme_name=theme.name,
                    state=state,
                    rank=rank,
                    total_score=round(float(row["total_score"]), 2),
                    volume_ratio_3m=round(float(row["ratio"]), 2),
                    volume_pct_1y=round(float(row["volume_pct"]), 2),
                    volume_alert=row["volume_alert"],
                    core_avg_change_pct=round(float(row["core_change"]), 2),
                    diffusion_avg_change_pct=round(float(row["diffusion_change"]), 2),
                    as_of_date=trade_date,
                )
            )
    return outputs


def top_theme_payload(signals: list[ThemeSignal], trade_date: date) -> list[dict[str, Any]]:
    rows = [item for item in signals if item.trade_date == trade_date]
    top3 = sorted(rows, key=lambda item: item.rank)[:3]
    return [
        {"theme_id": item.theme_id, "theme_name": item.theme_name, "score": item.total_score}
        for item in top3
    ]
