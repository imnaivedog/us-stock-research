"""M-pool L2 breadth signals."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BreadthRow:
    trade_date: date
    pct_above_200ma: float
    pct_above_50ma: float
    pct_above_20ma: float | None
    nh_nl_ratio: float
    mcclellan: float
    pct_above_200ma_p5y: float
    pct_above_50ma_p5y: float
    pct_above_50ma_p2y: float
    score: int


@dataclass(frozen=True)
class Alert:
    trade_date: date
    alert_type: str
    severity: str
    detail: dict[str, Any]
    as_of_date: date


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def percentile_rank(series: pd.Series, value: float) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty or pd.isna(value):
        return 0.0
    return float((clean <= value).mean() * 100)


def nh_nl_normalized(ratio: float) -> float:
    if ratio <= 0 or math.isnan(ratio):
        return 0.0
    return clamp(100 / (1 + math.exp(-1.8 * math.log(ratio))))


def mcclellan_normalized(value: float) -> float:
    return clamp((value + 100) / 2)


def breadth_score(row: pd.Series, params: dict[str, Any]) -> int:
    weights = params["l2_breadth"]["score_weights"]
    score = (
        float(row["breadth_pct_above_200ma_p5y"]) * weights["pct_above_200ma_p5y"]
        + float(row["breadth_pct_above_50ma_p5y"]) * weights["pct_above_50ma_p5y"]
        + nh_nl_normalized(float(row["breadth_nh_nl_ratio"])) * weights["nh_nl_normalized"]
        + mcclellan_normalized(float(row["breadth_mcclellan"])) * weights["mcclellan_normalized"]
    )
    return int(round(clamp(score)))


def enrich_breadth_history(history: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    if history.empty:
        return history.copy()
    df = history.copy().sort_values("trade_date").reset_index(drop=True)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["breadth_pct_above_200ma_p5y"] = [
        percentile_rank(df.loc[:idx, "breadth_pct_above_200ma"], value)
        for idx, value in enumerate(df["breadth_pct_above_200ma"])
    ]
    df["breadth_pct_above_50ma_p5y"] = [
        percentile_rank(df.loc[:idx, "breadth_pct_above_50ma"], value)
        for idx, value in enumerate(df["breadth_pct_above_50ma"])
    ]
    two_year_window = 504
    df["breadth_pct_above_50ma_p2y"] = [
        percentile_rank(
            df.loc[max(0, idx - two_year_window + 1) : idx, "breadth_pct_above_50ma"],
            value,
        )
        for idx, value in enumerate(df["breadth_pct_above_50ma"])
    ]
    df["breadth_score"] = df.apply(lambda row: breadth_score(row, params), axis=1)
    return df


def row_for_date(enriched: pd.DataFrame, trade_date: date) -> BreadthRow:
    match = enriched[enriched["trade_date"] == trade_date]
    if match.empty:
        raise ValueError(f"Missing breadth row for {trade_date}")
    row = match.iloc[-1]
    pct_above_20ma = row.get("breadth_pct_above_20ma")
    return BreadthRow(
        trade_date=trade_date,
        pct_above_200ma=float(row["breadth_pct_above_200ma"]),
        pct_above_50ma=float(row["breadth_pct_above_50ma"]),
        pct_above_20ma=None if pd.isna(pct_above_20ma) else float(pct_above_20ma),
        nh_nl_ratio=float(row["breadth_nh_nl_ratio"]),
        mcclellan=float(row["breadth_mcclellan"]),
        pct_above_200ma_p5y=float(row["breadth_pct_above_200ma_p5y"]),
        pct_above_50ma_p5y=float(row["breadth_pct_above_50ma_p5y"]),
        pct_above_50ma_p2y=float(row["breadth_pct_above_50ma_p2y"]),
        score=int(row["breadth_score"]),
    )


def detail(rule_id: str, threshold: Any, actual: Any, window: str, **extra: Any) -> dict[str, Any]:
    payload = {"rule_id": rule_id, "threshold": threshold, "actual": actual, "window": window}
    payload.update(extra)
    return payload


def detect_alerts(
    enriched: pd.DataFrame,
    spy_history: pd.DataFrame,
    trade_date: date,
    params: dict[str, Any],
    as_of_date: date | None = None,
) -> list[Alert]:
    as_of = as_of_date or trade_date
    row = row_for_date(enriched, trade_date)
    alerts: list[Alert] = []
    breadth_params = params["l2_breadth"]
    nh_nl = breadth_params["nh_nl"]
    if row.nh_nl_ratio >= nh_nl["extreme_red"] or row.nh_nl_ratio <= nh_nl["extreme_bottom"]:
        threshold = (
            f">={nh_nl['extreme_red']}"
            if row.nh_nl_ratio >= nh_nl["extreme_red"]
            else f"<={nh_nl['extreme_bottom']}"
        )
        alerts.append(
            Alert(
                trade_date,
                "NH_NL_EXTREME",
                "RED",
                detail("nh_nl_extreme", threshold, row.nh_nl_ratio, "1d"),
                as_of,
            )
        )
    mcclellan = breadth_params["mcclellan"]
    if row.mcclellan >= mcclellan["extreme_red"] or row.mcclellan <= mcclellan["extreme_bottom"]:
        threshold = (
            f">={mcclellan['extreme_red']}"
            if row.mcclellan >= mcclellan["extreme_red"]
            else f"<={mcclellan['extreme_bottom']}"
        )
        alerts.append(
            Alert(
                trade_date,
                "MCCLELLAN_EXTREME",
                "RED",
                detail("mcclellan_extreme", threshold, row.mcclellan, "1d"),
                as_of,
            )
        )
    alerts.extend(detect_50ma_alerts(enriched, trade_date, row, breadth_params, as_of))
    alerts.extend(detect_200ma_low_alerts(trade_date, row, breadth_params, as_of))
    if is_zweig_thrust(enriched, trade_date, breadth_params):
        zweig = breadth_params["zweig"]
        alerts.append(
            Alert(
                trade_date,
                "ZWEIG_BREADTH_THRUST",
                "RED",
                detail(
                    "zweig_breadth_thrust",
                    f"{zweig['from_threshold']}->{zweig['to_threshold']}",
                    row.pct_above_50ma,
                    f"{zweig['window_days']}d",
                ),
                as_of,
            )
        )
    if is_top_divergence(enriched, spy_history, trade_date, breadth_params):
        divergence = breadth_params["top_divergence"]
        alerts.append(
            Alert(
                trade_date,
                "BREADTH_TOP_DIVERGENCE",
                "YELLOW",
                detail(
                    "breadth_top_divergence",
                    f">{divergence['breadth_lag_min_pct']}",
                    row.pct_above_50ma,
                    f"{divergence['window_days']}d",
                ),
                as_of,
            )
        )
    return alerts


def detect_50ma_alerts(
    enriched: pd.DataFrame,
    trade_date: date,
    row: BreadthRow,
    breadth_params: dict[str, Any],
    as_of: date,
) -> list[Alert]:
    alerts: list[Alert] = []
    extreme = breadth_params["pct_above_50ma_extreme"]
    severity: str | None = None
    mode: str | None = None
    threshold: str | None = None
    actual = row.pct_above_50ma_p5y
    if actual >= extreme["red_p5y"]:
        severity, mode, threshold = "RED", "top_extreme", f">={extreme['red_p5y']}"
    elif actual >= extreme["yellow_p5y"]:
        severity, mode, threshold = "YELLOW", "top_extreme", f">={extreme['yellow_p5y']}"
    elif actual <= extreme["bottom_red_p5y"]:
        severity, mode, threshold = "RED", "bottom_extreme", f"<={extreme['bottom_red_p5y']}"
    elif actual <= extreme["bottom_yellow_p5y"]:
        severity, mode, threshold = "YELLOW", "bottom_extreme", f"<={extreme['bottom_yellow_p5y']}"
    if severity and threshold and mode:
        alerts.append(
            Alert(
                trade_date,
                "BREADTH_50MA_EXTREME",
                severity,
                detail("breadth_50ma_extreme", threshold, actual, "5y", mode=mode),
                as_of,
            )
        )
    dull = breadth_params["pct_above_50ma_dull"]
    recent = enriched[enriched["trade_date"] <= trade_date].tail(int(dull["consec_days"]))
    if (
        len(recent) >= int(dull["consec_days"])
        and (recent["breadth_pct_above_50ma_p2y"] >= float(dull["threshold_p2y"])).all()
    ):
        alerts.append(
            Alert(
                trade_date,
                "BREADTH_50MA_EXTREME",
                "RED",
                detail(
                    "breadth_50ma_dull",
                    f">={dull['threshold_p2y']}",
                    row.pct_above_50ma_p2y,
                    f"{dull['consec_days']}d",
                    mode="dull",
                ),
                as_of,
            )
        )
    return alerts


def detect_200ma_low_alerts(
    trade_date: date,
    row: BreadthRow,
    breadth_params: dict[str, Any],
    as_of: date,
) -> list[Alert]:
    weak_max = breadth_params["pct_above_200ma"]["weak_max_p5y"]
    if row.pct_above_200ma_p5y <= 10:
        return [
            Alert(
                trade_date,
                "BREADTH_200MA_LOW",
                "RED",
                detail("breadth_200ma_low", "<=10", row.pct_above_200ma_p5y, "5y"),
                as_of,
            )
        ]
    if row.pct_above_200ma_p5y <= weak_max:
        return [
            Alert(
                trade_date,
                "BREADTH_200MA_LOW",
                "YELLOW",
                detail("breadth_200ma_low", f"<={weak_max}", row.pct_above_200ma_p5y, "5y"),
                as_of,
            )
        ]
    return []


def is_zweig_thrust(
    enriched: pd.DataFrame, trade_date: date, breadth_params: dict[str, Any]
) -> bool:
    zweig = breadth_params["zweig"]
    recent = enriched[enriched["trade_date"] <= trade_date].tail(int(zweig["window_days"]))
    if recent.empty:
        return False
    return recent["breadth_pct_above_50ma"].min() <= float(zweig["from_threshold"]) and recent[
        "breadth_pct_above_50ma"
    ].iloc[-1] >= float(zweig["to_threshold"])


def is_top_divergence(
    enriched: pd.DataFrame,
    spy_history: pd.DataFrame,
    trade_date: date,
    breadth_params: dict[str, Any],
) -> bool:
    divergence = breadth_params["top_divergence"]
    window_days = int(divergence["window_days"])
    spy = spy_history.copy().sort_values("trade_date")
    spy["trade_date"] = pd.to_datetime(spy["trade_date"]).dt.date
    spy_window = spy[spy["trade_date"] <= trade_date].tail(window_days)
    breadth_window = enriched[enriched["trade_date"] <= trade_date].tail(window_days)
    if len(spy_window) < window_days or len(breadth_window) < window_days:
        return False
    close = pd.to_numeric(spy_window["close"], errors="coerce")
    current_close = close.iloc[-1]
    if current_close < close.max():
        return False
    current_breadth = float(breadth_window["breadth_pct_above_50ma"].iloc[-1])
    recent_breadth_high = float(breadth_window["breadth_pct_above_50ma"].max())
    return recent_breadth_high - current_breadth > float(divergence["breadth_lag_min_pct"])
