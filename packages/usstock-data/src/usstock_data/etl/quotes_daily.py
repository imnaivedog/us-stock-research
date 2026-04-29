"""Incremental quotes_daily loader."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import parse_date, parse_number, upsert_rows
from usstock_data.etl.fmp_client import FMPClient


ET_TZ = ZoneInfo("America/New_York")
NULL_MAX_LOOKBACK_DAYS = 10
FETCH_BATCH_SIZE = 50


@dataclass(frozen=True)
class QuoteState:
    symbol: str
    max_trade_date: date | None


def quote_rows(symbol: str, history: list[dict[str, object]], asset_class: str = "equity") -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
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
                "adj_close": parse_number(item.get("adjClose") or item.get("adj_close") or item.get("close")),
                "volume": int(parse_number(item.get("volume")) or 0),
                "asset_class": asset_class,
            }
        )
    return rows


def next_fetch_date(max_trade_date: date | None, today: date) -> date:
    return today - timedelta(days=NULL_MAX_LOOKBACK_DAYS) if max_trade_date is None else max_trade_date + timedelta(days=1)


def load_quote_states(engine: Engine) -> list[QuoteState]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT u.symbol, MAX(q.trade_date) AS max_trade_date
                FROM symbol_universe u
                LEFT JOIN quotes_daily q ON q.symbol = u.symbol
                WHERE u.is_active IS TRUE
                GROUP BY u.symbol
                ORDER BY u.symbol
                """
            )
        ).mappings()
        return [QuoteState(str(row["symbol"]), row["max_trade_date"]) for row in rows]


async def fetch_due_quotes(states: list[QuoteState], today: date) -> list[dict[str, object]]:
    all_rows: list[dict[str, object]] = []
    async with FMPClient() as client:
        for idx in range(0, len(states), FETCH_BATCH_SIZE):
            batch = states[idx : idx + FETCH_BATCH_SIZE]
            results = await asyncio.gather(
                *(
                    client.get_historical(
                        state.symbol,
                        next_fetch_date(state.max_trade_date, today).isoformat(),
                        today.isoformat(),
                    )
                    for state in batch
                ),
                return_exceptions=True,
            )
            for state, result in zip(batch, results, strict=True):
                if isinstance(result, Exception):
                    logger.exception("Skipping quote fetch for {}", state.symbol)
                    continue
                all_rows.extend(quote_rows(state.symbol, result))
            logger.info("quote fetch progress: {}/{}", min(idx + len(batch), len(states)), len(states))
    return all_rows


async def run(engine: Engine | None = None, as_of: date | None = None, dry_run: bool = False) -> int:
    engine = engine or create_postgres_engine()
    today = as_of or datetime.now(ET_TZ).date()
    due = [state for state in load_quote_states(engine) if next_fetch_date(state.max_trade_date, today) <= today]
    logger.info("quotes_daily due symbols: {}", len(due))
    if dry_run:
        return 0
    rows = await fetch_due_quotes(due, today)
    return upsert_rows(
        engine,
        "quotes_daily",
        rows,
        conflict_cols=["symbol", "trade_date"],
        update_cols=["open", "high", "low", "close", "adj_close", "volume", "asset_class"],
    )
