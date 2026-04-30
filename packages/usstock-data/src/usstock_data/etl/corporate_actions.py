"""Load splits and dividends, and mirror them into events_calendar."""

from __future__ import annotations

import asyncio
from datetime import date

from loguru import logger
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import (
    fetch_symbols_in_pool,
    normalize_symbol,
    parse_date,
    parse_number,
    run_many,
    upsert_rows,
)
from usstock_data.etl.fmp_client import FMPClient, FMPTransientError


def split_rows(symbol: str, payload: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for item in payload:
        ex_date = parse_date(item.get("date"))
        if ex_date:
            rows.append(
                {
                    "symbol": symbol,
                    "ex_date": ex_date,
                    "action_type": "split",
                    "ratio": parse_number(item.get("numerator"))
                    or parse_number(item.get("splitRatio"))
                    or parse_number(item.get("ratio")),
                    "cash_amount": None,
                    "details": item,
                }
            )
    return rows


def dividend_rows(symbol: str, payload: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for item in payload:
        ex_date = parse_date(item.get("date") or item.get("exDate"))
        if ex_date:
            rows.append(
                {
                    "symbol": symbol,
                    "ex_date": ex_date,
                    "action_type": "dividend",
                    "ratio": None,
                    "cash_amount": parse_number(item.get("dividend") or item.get("adjDividend")),
                    "details": item,
                }
            )
    return rows


def event_rows(action_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "symbol": row["symbol"],
            "event_date": row["ex_date"],
            "event_type": row["action_type"],
            "details": row["details"],
        }
        for row in action_rows
    ]


async def fetch_symbol_actions(client: FMPClient, symbol: str) -> list[dict[str, object]]:
    splits, dividends = await asyncio.gather(
        client.get_splits(symbol), client.get_dividends(symbol)
    )
    return split_rows(symbol, splits) + dividend_rows(symbol, dividends)


def collect_action_results(
    symbols: list[str], results: list[list[dict[str, object]] | BaseException | None]
) -> tuple[list[dict[str, object]], int, int]:
    rows: list[dict[str, object]] = []
    success_count = 0
    skip_count = 0
    total = len(symbols)
    for symbol, result in zip(symbols, results, strict=True):
        normalized_symbol = normalize_symbol(symbol)
        if result is None:
            skip_count += 1
            logger.debug("corporate_actions skip {}: empty response", normalized_symbol)
        elif isinstance(result, FMPTransientError):
            skip_count += 1
            logger.opt(exception=result).error("corporate_actions failed for {}", normalized_symbol)
        elif isinstance(result, Exception):
            skip_count += 1
            logger.opt(exception=result).debug("corporate_actions skip {}", normalized_symbol)
        else:
            success_count += 1
            rows.extend(result)

        if skip_count and skip_count % 200 == 0:
            logger.info(
                "corporate_actions: skipped {}/{}, success {}",
                skip_count,
                total,
                success_count,
            )
    logger.info(
        "corporate_actions done: {} success / {} skipped / {} total",
        success_count,
        skip_count,
        total,
    )
    return rows, success_count, skip_count


async def run(
    engine: Engine | None = None, as_of: date | None = None, dry_run: bool = False
) -> int:
    del as_of
    engine = engine or create_postgres_engine()
    with engine.begin() as conn:
        symbols = fetch_symbols_in_pool(conn, "all")
    logger.info("corporate_actions fetch symbols: {}", len(symbols))
    if dry_run:
        return 0
    rows: list[dict[str, object]] = []
    async with FMPClient() as client:
        results = await asyncio.gather(
            *(fetch_symbol_actions(client, symbol) for symbol in symbols), return_exceptions=True
        )
    rows, _success_count, _skip_count = collect_action_results(symbols, results)
    written = upsert_rows(
        engine,
        "corporate_actions",
        rows,
        conflict_cols=["symbol", "ex_date", "action_type"],
        update_cols=["ratio", "cash_amount", "details"],
    )
    with engine.begin() as conn:
        run_many(
            conn,
            """
            INSERT INTO events_calendar (symbol, event_date, event_type, details)
            VALUES (:symbol, :event_date, :event_type, :details)
            ON CONFLICT (symbol, event_date, event_type)
            DO UPDATE SET details = EXCLUDED.details
            """,
            event_rows(rows),
        )
    return written
