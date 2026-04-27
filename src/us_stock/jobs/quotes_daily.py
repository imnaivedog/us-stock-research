from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import text

from lib.fmp_client import FMPClient
from lib.pg_client import PostgresClient

ET_TZ = ZoneInfo("America/New_York")
MIN_WRITE_RATE = 0.9
NULL_MAX_LOOKBACK_DAYS = 10
FETCH_BATCH_SIZE = 50


@dataclass(frozen=True)
class SymbolQuoteState:
    symbol: str
    max_trade_date: date | None


@dataclass(frozen=True)
class QuotesPlan:
    active_total: int
    due_symbols: list[SymbolQuoteState]
    max_date_distribution: dict[str, int]
    estimated_rows: int
    today_et: date


@dataclass(frozen=True)
class QuotesResult:
    active_total: int
    due_symbols: int
    written_symbols: int
    rows_written: int
    write_rate: float
    dry_run: bool


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "INFO"), format="[{level}] {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Incrementally load quotes_daily for active symbols."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print due-symbol stats without FMP or DB writes.",
    )
    return parser.parse_args()


def parse_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def next_fetch_date(max_trade_date: date | None, today_et: date) -> date:
    if max_trade_date is None:
        return today_et - timedelta(days=NULL_MAX_LOOKBACK_DAYS)
    return max_trade_date + timedelta(days=1)


def estimate_business_days(start: date, end: date) -> int:
    if start > end:
        return 0
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def quote_rows(symbol: str, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history:
        trade_date = parse_date(item.get("date"))
        if not trade_date:
            continue
        rows.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "open": parse_number(item.get("open")),
                "high": parse_number(item.get("high")),
                "low": parse_number(item.get("low")),
                "close": parse_number(item.get("close")),
                "adj_close": parse_number(
                    item.get("adjClose") or item.get("adj_close") or item.get("close")
                ),
                "volume": int(parse_number(item.get("volume")) or 0),
            }
        )
    return rows


def build_quotes_plan(states: list[SymbolQuoteState], today_et: date) -> QuotesPlan:
    distribution = Counter(
        state.max_trade_date.isoformat() if state.max_trade_date else "NULL" for state in states
    )
    due = [
        state
        for state in states
        if next_fetch_date(state.max_trade_date, today_et) <= today_et
    ]
    estimated_rows = sum(
        estimate_business_days(next_fetch_date(state.max_trade_date, today_et), today_et)
        for state in due
    )
    return QuotesPlan(
        active_total=len(states),
        due_symbols=due,
        max_date_distribution=dict(sorted(distribution.items())),
        estimated_rows=estimated_rows,
        today_et=today_et,
    )


def load_symbol_states(pg: PostgresClient) -> list[SymbolQuoteState]:
    sql = text(
        """
        SELECT u.symbol, MAX(q.trade_date) AS max_trade_date
        FROM symbol_universe u
        LEFT JOIN quotes_daily q ON q.symbol = u.symbol
        WHERE u.is_active IS TRUE
        GROUP BY u.symbol
        ORDER BY u.symbol
        """
    )
    with pg.engine.begin() as conn:
        rows = conn.execute(sql).mappings().all()
    return [
        SymbolQuoteState(symbol=str(row["symbol"]), max_trade_date=row["max_trade_date"])
        for row in rows
    ]


async def fetch_symbol_rows(
    client: FMPClient,
    state: SymbolQuoteState,
    today_et: date,
) -> tuple[str, list[dict[str, Any]]]:
    start_date = next_fetch_date(state.max_trade_date, today_et)
    history = await client.get_historical(
        state.symbol,
        start_date.isoformat(),
        today_et.isoformat(),
    )
    return state.symbol, quote_rows(state.symbol, history)


async def fetch_due_quotes(
    states: list[SymbolQuoteState],
    today_et: date,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    fetched: dict[str, list[dict[str, Any]]] = {}
    failed: list[str] = []
    async with FMPClient() as client:
        for idx in range(0, len(states), FETCH_BATCH_SIZE):
            batch = states[idx : idx + FETCH_BATCH_SIZE]
            results = await asyncio.gather(
                *(fetch_symbol_rows(client, state, today_et) for state in batch),
                return_exceptions=True,
            )
            for state, result in zip(batch, results, strict=True):
                if isinstance(result, Exception):
                    failed.append(state.symbol)
                    logger.warning(f"Skipping {state.symbol}: {result}")
                    continue
                symbol, rows = result
                fetched[symbol] = rows
            logger.info(f"quote fetch progress: {min(idx + len(batch), len(states))}/{len(states)}")
    return fetched, failed


def upsert_quote_rows(pg: PostgresClient, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    pg.upsert(
        "quotes_daily",
        rows,
        conflict_cols=["symbol", "trade_date"],
        update_cols=["open", "high", "low", "close", "adj_close", "volume"],
    )


def enforce_write_rate(written_symbols: int, active_total: int) -> float:
    write_rate = 1.0 if active_total == 0 else written_symbols / active_total
    if write_rate < MIN_WRITE_RATE:
        raise RuntimeError(
            "quotes_daily write rate below safety floor: "
            f"{written_symbols}/{active_total}={write_rate:.3f}"
        )
    return write_rate


async def run_quotes_daily(pg: PostgresClient, dry_run: bool = False) -> QuotesResult:
    today_et = datetime.now(ET_TZ).date()
    states = load_symbol_states(pg)
    plan = build_quotes_plan(states, today_et)
    logger.info(f"quotes_daily active symbols: {plan.active_total}")
    logger.info(f"quotes_daily due symbols: {len(plan.due_symbols)}")
    logger.info(f"quotes_daily estimated rows: {plan.estimated_rows}")
    logger.info(f"quotes_daily max trade_date distribution: {plan.max_date_distribution}")
    if dry_run:
        return QuotesResult(
            active_total=plan.active_total,
            due_symbols=len(plan.due_symbols),
            written_symbols=0,
            rows_written=0,
            write_rate=0.0,
            dry_run=True,
        )

    fetched, failed = await fetch_due_quotes(plan.due_symbols, today_et)
    rows = [row for symbol_rows in fetched.values() for row in symbol_rows]
    written_symbols = sum(1 for symbol_rows in fetched.values() if symbol_rows)
    write_rate = enforce_write_rate(written_symbols, plan.active_total)
    upsert_quote_rows(pg, rows)
    logger.info(
        f"quotes_daily completed: written_symbols={written_symbols}, "
        f"failed_symbols={len(failed)}, rows_written={len(rows)}, write_rate={write_rate:.3f}"
    )
    return QuotesResult(
        active_total=plan.active_total,
        due_symbols=len(plan.due_symbols),
        written_symbols=written_symbols,
        rows_written=len(rows),
        write_rate=write_rate,
        dry_run=False,
    )


async def async_main() -> None:
    configure_logging()
    args = parse_args()
    started = time.monotonic()
    result = await run_quotes_daily(PostgresClient(), dry_run=args.dry_run)
    logger.info(
        f"quotes_daily finished in {time.monotonic() - started:.1f}s "
        f"(dry_run={result.dry_run}, rows_written={result.rows_written})"
    )


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
