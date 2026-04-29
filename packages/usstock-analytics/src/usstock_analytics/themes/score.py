"""Daily theme momentum scoring."""

from __future__ import annotations

import argparse
from datetime import date
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_analytics.db import create_postgres_engine
from usstock_analytics.signals.m_pool.params import load_params
from usstock_analytics.themes.rank import assign_ranks

DEFAULT_WEIGHTS = {"ret_5d": 0.20, "ret_20d": 0.50, "ret_60d": 0.30}


def weighted_theme_score(
    returns: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    weights = weights or DEFAULT_WEIGHTS
    return sum(float(returns.get(key, 0.0)) * float(weight) for key, weight in weights.items())


def member_returns(prices: pd.DataFrame, trade_date: date) -> pd.DataFrame:
    df = prices.copy().sort_values(["symbol", "trade_date"])
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    rows = []
    for symbol, group in df.groupby("symbol", sort=True):
        group = group[group["trade_date"] <= trade_date].tail(61)
        if group.empty or group.iloc[-1]["trade_date"] != trade_date:
            continue
        latest = float(group.iloc[-1]["close"])
        payload: dict[str, Any] = {"symbol": symbol}
        for days, key in [(5, "ret_5d"), (20, "ret_20d"), (60, "ret_60d")]:
            if len(group) <= days:
                payload[key] = 0.0
            else:
                base = float(group.iloc[-days - 1]["close"])
                payload[key] = 0.0 if base == 0 else (latest / base - 1) * 100
        rows.append(payload)
    return pd.DataFrame(rows)


def score_theme(
    theme_id: str,
    members: list[str],
    returns: pd.DataFrame,
    weights: dict[str, float],
    min_members: int,
) -> dict[str, Any] | None:
    subset = returns[returns["symbol"].isin(members)]
    if len(subset) < min_members:
        logger.warning("Skipping theme {}: only {} members", theme_id, len(subset))
        return None
    averaged = {
        key: float(pd.to_numeric(subset[key], errors="coerce").mean())
        for key in ("ret_5d", "ret_20d", "ret_60d")
    }
    return {
        "theme_id": theme_id,
        "raw_score": round(weighted_theme_score(averaged, weights), 6),
        "member_count": len(subset),
    }


def load_theme_members(engine: Engine) -> dict[str, list[str]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT theme_id, symbol FROM themes_members ORDER BY theme_id, symbol")
        ).all()
    result: dict[str, list[str]] = {}
    for theme_id, symbol in rows:
        result.setdefault(str(theme_id), []).append(str(symbol))
    return result


def load_prices(engine: Engine, symbols: list[str], trade_date: date) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame(columns=["symbol", "trade_date", "close"])
    with engine.begin() as conn:
        return pd.read_sql_query(
            text(
                """
                SELECT symbol, trade_date, close
                FROM quotes_daily
                WHERE symbol = ANY(:symbols)
                  AND trade_date <= :trade_date
                  AND trade_date >= :trade_date - interval '90 days'
                ORDER BY symbol, trade_date
                """
            ),
            conn,
            params={"symbols": sorted(set(symbols)), "trade_date": trade_date},
        )


def compute_scores(
    engine: Engine,
    trade_date: date,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    members_by_theme = load_theme_members(engine)
    all_symbols = sorted({symbol for members in members_by_theme.values() for symbol in members})
    returns = member_returns(load_prices(engine, all_symbols, trade_date), trade_date)
    score_params = params.get("themes_score", {})
    weights = score_params.get("weights", DEFAULT_WEIGHTS)
    min_members = int(score_params.get("min_members", 5))
    rows = [
        row
        for theme_id, members in members_by_theme.items()
        if (row := score_theme(theme_id, members, returns, weights, min_members))
    ]
    ranked = assign_ranks(rows)
    return [{"date": trade_date, **row} for row in ranked]


def upsert_scores(engine: Engine, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO themes_score_daily (
                    date, theme_id, raw_score, rank, quintile, member_count
                )
                VALUES (:date, :theme_id, :raw_score, :rank, :quintile, :member_count)
                ON CONFLICT (date, theme_id) DO UPDATE SET
                    raw_score = EXCLUDED.raw_score,
                    rank = EXCLUDED.rank,
                    quintile = EXCLUDED.quintile,
                    member_count = EXCLUDED.member_count
                """
            ),
            rows,
        )
    return len(rows)


def run(engine: Engine | None = None, trade_date: date | None = None) -> int:
    if trade_date is None:
        raise ValueError("trade_date is required")
    engine = engine or create_postgres_engine()
    rows = compute_scores(engine, trade_date, load_params())
    return upsert_scores(engine, rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-analytics themes-score")
    parser.add_argument("--date", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    written = run(trade_date=date.fromisoformat(args.date))
    print({"written": written})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
