from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from loguru import logger

from lib.pg_client import PostgresClient
from scripts.run_signals import (
    load_db_context,
    load_fixture_context,
    run_signal_engine,
    upsert_alerts,
    upsert_detail_rows,
    upsert_signals_daily,
)
from src.signals._params import load_params
from src.signals.macro import compute_macro_state, run_macro, upsert_macro_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orchestrate daily M-pool signal stages.")
    parser.add_argument("--date", help="Single trade date, YYYY-MM-DD. Defaults to today UTC.")
    parser.add_argument("--start", help="Backtest start date, YYYY-MM-DD.")
    parser.add_argument("--end", help="Backtest end date, YYYY-MM-DD.")
    parser.add_argument("--fixture-dir", help="Optional deterministic fixture directory.")
    return parser.parse_args()


def date_range(args: argparse.Namespace) -> tuple[date, date]:
    if args.date:
        day = date.fromisoformat(args.date)
        return day, day
    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
        if start > end:
            raise ValueError("--start must be <= --end")
        return start, end
    today = datetime.now(UTC).date()
    return today, today


def load_fixture_macro_quotes(fixture_dir: Path) -> pd.DataFrame:
    path = fixture_dir / "macro_1y.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["trade_date"])
    spy = pd.read_csv(fixture_dir / "spy_1y.csv", parse_dates=["trade_date"])
    rows = []
    factors = {
        "SPY": 1.00,
        "TLT": 0.75,
        "IEF": 0.80,
        "HYG": 0.95,
        "LQD": 0.88,
        "UUP": 0.55,
        "GLD": 0.70,
        "SLV": 0.60,
        "DBC": 0.65,
        "VIXY": 0.45,
    }
    for symbol, factor in factors.items():
        symbol_frame = spy[["trade_date", "close"]].copy()
        symbol_frame["symbol"] = symbol
        symbol_frame["close"] = symbol_frame["close"] * factor
        rows.append(symbol_frame)
    return pd.concat(rows, ignore_index=True)


def run_pipeline(start: date, end: date, fixture_dir: Path | None = None) -> None:
    params = load_params()
    pg = PostgresClient()
    if fixture_dir:
        spy, breadth, vix, events, sectors, stocks = load_fixture_context(fixture_dir)
    else:
        spy, breadth, vix, events, sectors, stocks = load_db_context(pg, start, end)
    logger.info("stage=dial,breadth,sector,theme,stock started")
    daily_rows, alerts, sector_rows, theme_rows, stock_rows = run_signal_engine(
        spy, breadth, vix, events, start, end, params, sectors=sectors, stocks=stocks
    )
    upsert_signals_daily(pg, daily_rows)
    upsert_alerts(pg, alerts)
    upsert_detail_rows(pg, "signals_sectors_daily", [item.__dict__ for item in sector_rows])
    upsert_detail_rows(pg, "signals_themes_daily", [item.__dict__ for item in theme_rows])
    upsert_detail_rows(pg, "signals_stocks_daily", [item.__dict__ for item in stock_rows])
    logger.info(
        "stage=dial,breadth,sector,theme,stock wrote "
        f"daily={len(daily_rows)} alerts={len(alerts)} sectors={len(sector_rows)} "
        f"themes={len(theme_rows)} stocks={len(stock_rows)}"
    )
    logger.info("stage=macro started")
    macro_quotes = load_fixture_macro_quotes(fixture_dir) if fixture_dir else None
    for row in daily_rows:
        trade_date = row["trade_date"]
        if macro_quotes is None:
            result = run_macro(pg, trade_date)
        else:
            result = compute_macro_state(macro_quotes, trade_date)
            upsert_macro_state(pg, result)
        logger.info(f"stage=macro trade_date={trade_date} macro_state={result.macro_state}")


def main() -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="[{level}] {message}")
    args = parse_args()
    try:
        start, end = date_range(args)
        run_pipeline(start, end, Path(args.fixture_dir) if args.fixture_dir else None)
    except Exception:
        logger.exception("signals orchestration failed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
