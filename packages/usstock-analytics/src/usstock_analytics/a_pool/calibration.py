"""A-pool per-symbol 5Y calibration."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_analytics.db import create_postgres_engine

MIN_HISTORY_ROWS = 120


@dataclass(frozen=True)
class CalibrationRow:
    symbol: str
    rsi14_p20: float
    rsi14_p80: float
    drawdown_p10: float
    vol_avg_60d: float
    beta_120d: float


def compute_calibration(
    symbol: str,
    history: pd.DataFrame,
    spy_history: pd.DataFrame,
) -> CalibrationRow | None:
    df = history.copy().sort_values("trade_date")
    if len(df) < MIN_HISTORY_ROWS:
        logger.warning("Skipping calibration for {}: short history {}", symbol, len(df))
        return None
    df["rsi_14"] = pd.to_numeric(df["rsi_14"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["ret"] = df["close"].pct_change()
    df["drawdown_60d"] = df["close"] / df["close"].rolling(60).max() - 1
    spy = spy_history.copy().sort_values("trade_date")
    spy["spy_ret"] = pd.to_numeric(spy["close"], errors="coerce").pct_change()
    merged = df[["trade_date", "ret"]].merge(spy[["trade_date", "spy_ret"]], on="trade_date")
    beta = (
        merged["ret"].tail(120).cov(merged["spy_ret"].tail(120))
        / merged["spy_ret"].tail(120).var()
    )
    return CalibrationRow(
        symbol=symbol,
        rsi14_p20=float(df["rsi_14"].quantile(0.20)),
        rsi14_p80=float(df["rsi_14"].quantile(0.80)),
        drawdown_p10=float(df["drawdown_60d"].quantile(0.10)),
        vol_avg_60d=float((df["close"] * df["volume"]).tail(60).mean()),
        beta_120d=0.0 if pd.isna(beta) else float(beta),
    )


def load_symbols(engine: Engine, symbols: list[str] | None = None) -> list[str]:
    if symbols:
        return sorted({symbol.upper() for symbol in symbols})
    with engine.begin() as conn:
        return [
            str(row[0])
            for row in conn.execute(
                text("SELECT symbol FROM symbol_universe WHERE pool = 'a' AND is_active IS TRUE")
            )
        ]


def load_history(engine: Engine, symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not symbols:
        empty = pd.DataFrame(columns=["symbol", "trade_date", "close", "volume", "rsi_14"])
        return empty, empty
    with engine.begin() as conn:
        history = pd.read_sql_query(
            text(
                """
                SELECT q.symbol, q.trade_date, q.close, q.volume, di.rsi_14
                FROM quotes_daily q
                JOIN daily_indicators di
                  ON di.symbol = q.symbol AND di.trade_date = q.trade_date
                WHERE q.symbol = ANY(:symbols)
                ORDER BY q.symbol, q.trade_date
                """
            ),
            conn,
            params={"symbols": symbols},
        )
        spy = pd.read_sql_query(
            text(
                """
                SELECT symbol, trade_date, close
                FROM quotes_daily
                WHERE symbol = 'SPY'
                ORDER BY trade_date
                """
            ),
            conn,
        )
    return history, spy


def upsert_calibrations(engine: Engine, rows: list[CalibrationRow]) -> int:
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO a_pool_calibration (
                    symbol, rsi14_p20, rsi14_p80, drawdown_p10,
                    vol_avg_60d, beta_120d, calibrated_at
                )
                VALUES (
                    :symbol, :rsi14_p20, :rsi14_p80, :drawdown_p10,
                    :vol_avg_60d, :beta_120d, now()
                )
                ON CONFLICT (symbol) DO UPDATE SET
                    rsi14_p20 = EXCLUDED.rsi14_p20,
                    rsi14_p80 = EXCLUDED.rsi14_p80,
                    drawdown_p10 = EXCLUDED.drawdown_p10,
                    vol_avg_60d = EXCLUDED.vol_avg_60d,
                    beta_120d = EXCLUDED.beta_120d,
                    calibrated_at = now()
                """
            ),
            [row.__dict__ for row in rows],
        )
    return len(rows)


def run(engine: Engine | None = None, symbols: list[str] | None = None) -> int:
    engine = engine or create_postgres_engine()
    selected = load_symbols(engine, symbols)
    history, spy = load_history(engine, selected)
    rows = [
        row
        for symbol, group in history.groupby("symbol")
        if (row := compute_calibration(str(symbol), group, spy)) is not None
    ]
    return upsert_calibrations(engine, rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-analytics a-pool calibrate")
    parser.add_argument("--symbols", help="Comma-separated symbols.")
    parser.add_argument("--all", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    symbols = [item.strip() for item in args.symbols.split(",")] if args.symbols else None
    written = run(symbols=symbols)
    print({"written": written})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
