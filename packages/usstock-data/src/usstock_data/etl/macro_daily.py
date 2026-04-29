"""Incremental macro_daily loader."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import CONFIG_DIR, load_yaml, parse_date, parse_number, upsert_rows
from usstock_data.etl.fmp_client import FMPClient

ET_TZ = ZoneInfo("America/New_York")
TREASURY_RATE_PREFIX = "treasury_rates:"
NULL_MAX_LOOKBACK_DAYS = 10
TREASURY_LOOKBACK_DAYS = 14
MACRO_COLUMNS = (
    "vix",
    "spy",
    "qqq",
    "tlt",
    "gld",
    "silver",
    "gold_silver_ratio",
    "uup",
    "hyg",
    "lqd",
    "hyg_lqd_spread",
    "dxy",
    "wti",
    "btc",
    "ief",
    "us10y",
    "us2y",
    "dgs10",
    "dgs2",
    "spread_10y_2y",
)


@dataclass(frozen=True)
class SourceRows:
    key: str
    rows: list[dict[str, object]]


def load_macro_symbols() -> dict[str, str]:
    path = CONFIG_DIR / "macro_symbols.yaml"
    if path.exists():
        return {str(key): str(value) for key, value in load_yaml(path).items()}
    payload = load_yaml(CONFIG_DIR / "thresholds.yaml")
    return {str(key): str(value) for key, value in payload.get("macro_symbols", {}).items()}


def rows_from_history(key: str, history: list[dict[str, object]]) -> SourceRows:
    return SourceRows(
        key,
        [
            {
                "trade_date": trade_date,
                "value": parse_number(item.get("adjClose") or item.get("close")),
            }
            for item in history
            if (trade_date := parse_date(item.get("date")))
        ],
    )


def rows_from_treasury_rates(key: str, rates: list[dict[str, object]], field: str) -> SourceRows:
    return SourceRows(
        key,
        [
            {"trade_date": trade_date, "value": parse_number(item.get(field))}
            for item in rates
            if (trade_date := parse_date(item.get("date")))
        ],
    )


async def fetch_source(
    client: FMPClient, key: str, source: str, start: date, end: date
) -> SourceRows:
    if source.startswith(TREASURY_RATE_PREFIX):
        field = source.removeprefix(TREASURY_RATE_PREFIX)
        rates = await client.get_treasury_rates(
            (end - timedelta(days=TREASURY_LOOKBACK_DAYS)).isoformat(), end.isoformat()
        )
        return rows_from_treasury_rates(key, rates, field)
    history = await client.get_historical(source, start.isoformat(), end.isoformat())
    return rows_from_history(key, history)


def build_macro_rows(source_rows: list[SourceRows]) -> list[dict[str, object]]:
    by_date: dict[date, dict[str, float | None]] = defaultdict(dict)
    for source in source_rows:
        for row in source.rows:
            by_date[row["trade_date"]][source.key] = row["value"]
    rows: list[dict[str, object]] = []
    for trade_date, values in sorted(by_date.items()):
        row: dict[str, object] = {"trade_date": trade_date}
        for column in MACRO_COLUMNS:
            row[column] = values.get(column)
        us10y = values.get("us10y") or values.get("dgs10")
        us2y = values.get("us2y") or values.get("dgs2")
        row["dgs10"] = values.get("dgs10") or us10y
        row["dgs2"] = values.get("dgs2") or us2y
        row["spread_10y_2y"] = None if us10y is None or us2y is None else us10y - us2y
        if values.get("hyg") is not None and values.get("lqd") is not None:
            row["hyg_lqd_spread"] = values["hyg"] - values["lqd"]
        if values.get("gld") is not None and values.get("silver") is not None:
            row["gold_silver_ratio"] = values["gld"] / values["silver"]
        if any(row.get(column) is not None for column in MACRO_COLUMNS):
            rows.append(row)
    return rows


def last_trade_date(engine: Engine) -> date | None:
    with engine.begin() as conn:
        return conn.execute(text("SELECT MAX(trade_date) FROM macro_daily")).scalar_one()


async def run(
    engine: Engine | None = None, as_of: date | None = None, dry_run: bool = False
) -> int:
    engine = engine or create_postgres_engine()
    end = as_of or datetime.now(ET_TZ).date()
    last = last_trade_date(engine)
    start = (
        end - timedelta(days=NULL_MAX_LOOKBACK_DAYS) if last is None else last + timedelta(days=1)
    )
    symbols = load_macro_symbols()
    logger.info("macro_daily fetch window: {} to {}; sources={}", start, end, len(symbols))
    if dry_run:
        return 0
    async with FMPClient() as client:
        results = await asyncio.gather(
            *(fetch_source(client, key, source, start, end) for key, source in symbols.items()),
            return_exceptions=True,
        )
    source_rows: list[SourceRows] = []
    for key, result in zip(symbols, results, strict=True):
        if isinstance(result, Exception):
            logger.exception("Skipping macro source {}", key)
            continue
        source_rows.append(result)
    rows = build_macro_rows(source_rows)
    return upsert_rows(
        engine, "macro_daily", rows, conflict_cols=["trade_date"], update_cols=MACRO_COLUMNS
    )
