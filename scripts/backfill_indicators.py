from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402
from sqlalchemy import text  # noqa: E402

from lib.pg_client import PostgresClient  # noqa: E402
from scripts.compute_indicators import (  # noqa: E402
    compute_indicators,
    indicator_rows_for_date,
    load_active_symbols,
    upsert_daily_indicators,
)

WARMUP_DAYS = 370
UPSERT_BATCH_SIZE = 1000

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - local fallback when tqdm is not installed.
    def tqdm(iterable: Any, **_: Any) -> Any:
        return iterable


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "INFO"), format="[{level}] {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill daily_indicators for a date range.")
    parser.add_argument("--start", required=True, help="Backfill start date, YYYY-MM-DD.")
    parser.add_argument("--end", required=True, help="Backfill end date, YYYY-MM-DD.")
    parser.add_argument(
        "--symbols",
        default="ALL",
        help="ALL or comma-separated symbols, e.g. NVDA,AAPL.",
    )
    return parser.parse_args()


def parse_symbols(value: str) -> list[str] | None:
    if value.strip().upper() == "ALL":
        return None
    symbols = sorted({item.strip().upper() for item in value.split(",") if item.strip()})
    if not symbols:
        raise ValueError("--symbols must be ALL or a comma-separated symbol list")
    return symbols


def load_backfill_quotes(
    pg: PostgresClient,
    start: date,
    end: date,
    symbols: list[str],
) -> pd.DataFrame:
    warmup_start = start - timedelta(days=WARMUP_DAYS)
    params: dict[str, Any] = {"start": warmup_start, "end": end}
    placeholders: list[str] = []
    for idx, symbol in enumerate(sorted(set(symbols + ["SPY"]))):
        key = f"symbol_{idx}"
        params[key] = symbol
        placeholders.append(f":{key}")
    sql = text(
        f"""
        SELECT symbol, trade_date, open, high, low, close, adj_close, volume
        FROM quotes_daily
        WHERE trade_date BETWEEN :start AND :end
          AND symbol IN ({", ".join(placeholders)})
        ORDER BY symbol, trade_date
        """
    )
    return pd.read_sql_query(sql, pg.engine, params=params)


def chunked(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[idx : idx + size] for idx in range(0, len(rows), size)]


def run_backfill(
    pg: PostgresClient,
    start: date,
    end: date,
    requested_symbols: list[str] | None = None,
) -> int:
    if start > end:
        raise ValueError("--start must be <= --end")
    symbols = requested_symbols or load_active_symbols(pg)
    logger.info(f"backfill_indicators symbols={len(symbols)}, range={start} to {end}")
    quotes = load_backfill_quotes(pg, start, end, symbols)
    indicators = compute_indicators(quotes)
    trading_dates = sorted(
        value
        for value in indicators["trade_date"].dropna().unique().tolist()
        if start <= value <= end
    )
    total_rows = 0
    for trade_date in tqdm(trading_dates, desc="daily_indicators"):
        rows = indicator_rows_for_date(indicators, trade_date, symbols)
        for batch in chunked(rows, UPSERT_BATCH_SIZE):
            upsert_daily_indicators(pg, batch)
        total_rows += len(rows)
        if len(rows) > 0:
            logger.info(f"backfilled {trade_date}: rows={len(rows)}")
    logger.info(f"backfill_indicators completed: backfilled_rows={total_rows}")
    return total_rows


def main() -> None:
    configure_logging()
    args = parse_args()
    started = time.monotonic()
    rows = run_backfill(
        PostgresClient(),
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        requested_symbols=parse_symbols(args.symbols),
    )
    logger.info(f"backfill_indicators finished in {time.monotonic() - started:.1f}s rows={rows}")


if __name__ == "__main__":
    main()
