from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from loguru import logger
from sqlalchemy import bindparam, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.fmp_client import FMPClient  # noqa: E402
from lib.pg_client import PostgresClient  # noqa: E402
from scripts.backfill_indicators import run_backfill  # noqa: E402
from src.us_stock.jobs.quotes_daily import quote_rows  # noqa: E402

THRESHOLDS_PATH = PROJECT_ROOT / "config" / "thresholds.yaml"
ET_TZ = ZoneInfo("America/New_York")

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - local fallback when tqdm is not installed.
    def tqdm(iterable: Any, **_: Any) -> Any:
        return iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap ETF universe quotes and indicators.")
    parser.add_argument("--years", type=int, default=5, help="History window in years.")
    return parser.parse_args()


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="[{level}] {message}")


def load_etf_universe(path: Path = THRESHOLDS_PATH) -> list[str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    symbols = {str(symbol).strip().upper() for symbol in payload.get("etf_universe", []) if symbol}
    return sorted(symbols)


def year_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(date(cursor.year, 12, 31), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def symbol_universe_columns(pg: PostgresClient) -> set[str]:
    sql = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'symbol_universe'
        """
    )
    with pg.engine.begin() as conn:
        return {str(value) for value in conn.execute(sql).scalars().all()}


def upsert_etf_symbols(pg: PostgresClient, symbols: list[str], today: date) -> None:
    columns = symbol_universe_columns(pg)
    base_columns = [
        "symbol",
        "source",
        "is_candidate",
        "is_active",
        "market_cap",
        "added_date",
        "as_of_date",
        "filter_reason",
    ]
    optional_columns = [column for column in ("sector", "name") if column in columns]
    insert_columns = base_columns + optional_columns
    rows = []
    for symbol in symbols:
        row = {
            "symbol": symbol,
            "source": "etf_universe",
            "is_candidate": True,
            "is_active": True,
            "market_cap": None,
            "added_date": today,
            "as_of_date": today,
            "filter_reason": "etf_universe_bootstrap",
            "sector": "ETF",
            "name": symbol,
        }
        rows.append({column: row[column] for column in insert_columns})
    update_targets = [
        "is_active = TRUE",
        "as_of_date = EXCLUDED.as_of_date",
        "source = EXCLUDED.source",
        "filter_reason = EXCLUDED.filter_reason",
    ]
    if "last_seen" in columns:
        update_targets.append("last_seen = NULL")
    if "sector" in optional_columns:
        update_targets.append("sector = COALESCE(symbol_universe.sector, EXCLUDED.sector)")
    if "name" in optional_columns:
        update_targets.append("name = COALESCE(symbol_universe.name, EXCLUDED.name)")
    sql = text(
        f"""
        INSERT INTO symbol_universe ({", ".join(insert_columns)})
        VALUES ({", ".join(f":{column}" for column in insert_columns)})
        ON CONFLICT (symbol) DO UPDATE SET {", ".join(update_targets)}
        """
    )
    with pg.engine.begin() as conn:
        conn.execute(sql, rows)
    logger.info(f"symbol_universe ETF upserted: symbols={len(symbols)}")


async def fetch_etf_quote_rows(symbol: str, start: date, end: date) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, date], dict[str, Any]] = {}
    async with FMPClient() as client:
        for window_start, window_end in year_windows(start, end):
            history = await client.get_historical(
                symbol,
                window_start.isoformat(),
                window_end.isoformat(),
            )
            for row in quote_rows(symbol, history):
                by_key[(row["symbol"], row["trade_date"])] = row
    return [by_key[key] for key in sorted(by_key, key=lambda item: item[1])]


async def fetch_all_quotes(symbols: list[str], start: date, end: date) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    for symbol in tqdm(symbols, desc="etf_quotes"):
        rows = await fetch_etf_quote_rows(symbol, start, end)
        all_rows.extend(rows)
        logger.info(f"{symbol}: quote rows={len(rows)}")
    return all_rows


def verify_quotes(pg: PostgresClient, symbols: list[str]) -> None:
    sql = text(
        """
        SELECT symbol, COUNT(*) AS rows, MIN(trade_date), MAX(trade_date)
        FROM quotes_daily
        WHERE symbol IN :symbols
        GROUP BY symbol
        ORDER BY symbol
        """
    ).bindparams(bindparam("symbols", expanding=True))
    with pg.engine.begin() as conn:
        rows = conn.execute(sql, {"symbols": symbols}).mappings().all()
    for row in rows:
        logger.info(
            f"quotes_daily ETF verify: symbol={row['symbol']} rows={row['rows']} "
            f"min={row['min']} max={row['max']}"
        )
    logger.info(f"quotes_daily ETF verify rows={len(rows)}/{len(symbols)}")


async def run_bootstrap(years: int) -> None:
    if years <= 0:
        raise ValueError("--years must be positive")
    pg = PostgresClient()
    symbols = load_etf_universe()
    today = datetime.now(ET_TZ).date()
    start = today - timedelta(days=years * 365)
    logger.info(f"bootstrap_etf_quotes symbols={len(symbols)} range={start} to {today}")
    upsert_etf_symbols(pg, symbols, today)
    rows = await fetch_all_quotes(symbols, start, today)
    pg.upsert(
        "quotes_daily",
        rows,
        conflict_cols=["symbol", "trade_date"],
        update_cols=["open", "high", "low", "close", "adj_close", "volume"],
    )
    logger.info(f"quotes_daily ETF upserted rows={len(rows)}")
    run_backfill(pg, start=start, end=today, requested_symbols=symbols)
    verify_quotes(pg, symbols)


def main() -> None:
    configure_logging()
    args = parse_args()
    started = time.monotonic()
    asyncio.run(run_bootstrap(args.years))
    logger.info(f"bootstrap_etf_quotes completed in {time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    main()
