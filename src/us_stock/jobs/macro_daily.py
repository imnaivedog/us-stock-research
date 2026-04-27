from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from loguru import logger
from sqlalchemy import text

from lib.fmp_client import FMPClient
from lib.pg_client import PostgresClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
THRESHOLDS_PATH = PROJECT_ROOT / "config" / "thresholds.yaml"
TREASURY_RATE_PREFIX = "treasury_rates:"
ET_TZ = ZoneInfo("America/New_York")
NULL_MAX_LOOKBACK_DAYS = 10
MACRO_DB_COLUMNS = (
    "vix",
    "spy",
    "qqq",
    "tlt",
    "gld",
    "uup",
    "hyg",
    "lqd",
    "dxy",
    "wti",
    "btc",
    "ief",
    "us10y",
    "spread_10y_2y",
)


@dataclass(frozen=True)
class MacroSourceRows:
    key: str
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class MacroPlan:
    last_trade_date: date | None
    start_date: date
    end_date: date
    due_days: int


@dataclass(frozen=True)
class MacroResult:
    last_trade_date: date | None
    start_date: date
    end_date: date
    due_days: int
    rows_written: int
    source_successes: int
    source_failures: int
    dry_run: bool


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "INFO"), format="[{level}] {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Incrementally load macro_daily.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the macro load window without FMP calls or DB writes.",
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


def count_calendar_days(start: date, end: date) -> int:
    if start > end:
        return 0
    return (end - start).days + 1


def load_macro_symbols(path: Path = THRESHOLDS_PATH) -> dict[str, str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    macro_symbols = payload.get("macro_symbols")
    if not isinstance(macro_symbols, dict) or not macro_symbols:
        raise RuntimeError(f"macro_symbols missing from {path}")
    return {str(key): str(value) for key, value in macro_symbols.items()}


def load_last_trade_date(pg: PostgresClient) -> date | None:
    with pg.engine.begin() as conn:
        return conn.execute(text("SELECT MAX(trade_date) FROM macro_daily")).scalar_one()


def build_macro_plan(last_trade_date: date | None, today_et: date) -> MacroPlan:
    start_date = next_fetch_date(last_trade_date, today_et)
    return MacroPlan(
        last_trade_date=last_trade_date,
        start_date=start_date,
        end_date=today_et,
        due_days=count_calendar_days(start_date, today_et),
    )


def rows_from_history(key: str, history: list[dict[str, Any]]) -> MacroSourceRows:
    rows: list[dict[str, Any]] = []
    for item in history:
        trade_date = parse_date(item.get("date"))
        if not trade_date:
            continue
        rows.append(
            {
                "trade_date": trade_date,
                "value": parse_number(item.get("adjClose") or item.get("close")),
            }
        )
    return MacroSourceRows(key=key, rows=rows)


def rows_from_treasury_rates(
    key: str,
    treasury_rates: list[dict[str, Any]],
    field: str,
) -> MacroSourceRows:
    rows: list[dict[str, Any]] = []
    for item in treasury_rates:
        trade_date = parse_date(item.get("date"))
        if not trade_date:
            continue
        rows.append({"trade_date": trade_date, "value": parse_number(item.get(field))})
    return MacroSourceRows(key=key, rows=rows)


async def fetch_macro_source(
    client: FMPClient,
    key: str,
    source: str,
    start_date: date,
    end_date: date,
) -> MacroSourceRows:
    start = start_date.isoformat()
    end = end_date.isoformat()
    if source.startswith(TREASURY_RATE_PREFIX):
        field = source.removeprefix(TREASURY_RATE_PREFIX)
        treasury_rates = await client.get_treasury_rates(start, end)
        if not treasury_rates:
            logger.warning(f"{key} treasury rates returned no data; column will remain NULL")
        return rows_from_treasury_rates(key, treasury_rates, field)

    history = await client.get_historical(source, start, end)
    if not history:
        logger.warning(f"{key} macro symbol {source} returned no data; column will remain NULL")
    return rows_from_history(key, history)


async def fetch_all_macro_sources(
    macro_symbols: dict[str, str],
    start_date: date,
    end_date: date,
) -> tuple[list[MacroSourceRows], list[str]]:
    source_rows: list[MacroSourceRows] = []
    failed_sources: list[str] = []
    async with FMPClient() as client:
        results = await asyncio.gather(
            *(
                fetch_macro_source(client, key, source, start_date, end_date)
                for key, source in macro_symbols.items()
            ),
            return_exceptions=True,
        )
    for key, result in zip(macro_symbols, results, strict=True):
        if isinstance(result, Exception):
            failed_sources.append(key)
            logger.warning(f"Skipping macro source {key}: {result}")
            continue
        source_rows.append(result)
    if len(failed_sources) == len(macro_symbols):
        raise RuntimeError("all macro sources failed")
    return source_rows, failed_sources


def build_macro_upsert_rows(source_rows: list[MacroSourceRows]) -> list[dict[str, Any]]:
    by_date: dict[date, dict[str, float | None]] = defaultdict(dict)
    for source in source_rows:
        for row in source.rows:
            trade_date = row.get("trade_date")
            if isinstance(trade_date, date):
                by_date[trade_date][source.key] = row.get("value")

    macro_rows: list[dict[str, Any]] = []
    for trade_date, values in sorted(by_date.items()):
        row: dict[str, Any] = {"trade_date": trade_date}
        for column in MACRO_DB_COLUMNS:
            if column != "spread_10y_2y":
                row[column] = values.get(column)
        us10y = values.get("us10y")
        us2y = values.get("us2y")
        row["spread_10y_2y"] = None if us10y is None or us2y is None else us10y - us2y
        macro_rows.append(row)
    return macro_rows


def upsert_macro_rows(pg: PostgresClient, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    pg.upsert(
        "macro_daily",
        rows,
        conflict_cols=["trade_date"],
        update_cols=list(MACRO_DB_COLUMNS),
    )


async def run_macro_daily(pg: PostgresClient, dry_run: bool = False) -> MacroResult:
    today_et = datetime.now(ET_TZ).date()
    macro_symbols = load_macro_symbols()
    last_trade_date = load_last_trade_date(pg)
    plan = build_macro_plan(last_trade_date, today_et)
    logger.info(f"macro_daily last trade_date: {plan.last_trade_date}")
    logger.info(f"macro_daily fetch window: {plan.start_date} to {plan.end_date}")
    logger.info(f"macro_daily due calendar days: {plan.due_days}")
    logger.info(f"macro_daily source count: {len(macro_symbols)}")

    if dry_run or plan.due_days == 0:
        return MacroResult(
            last_trade_date=plan.last_trade_date,
            start_date=plan.start_date,
            end_date=plan.end_date,
            due_days=plan.due_days,
            rows_written=0,
            source_successes=0,
            source_failures=0,
            dry_run=dry_run,
        )

    source_rows, failed_sources = await fetch_all_macro_sources(
        macro_symbols,
        plan.start_date,
        plan.end_date,
    )
    success_count = sum(1 for source in source_rows if source.rows)
    if success_count == 0:
        raise RuntimeError("all macro sources returned no rows")
    rows = build_macro_upsert_rows(source_rows)
    upsert_macro_rows(pg, rows)
    logger.info(
        f"macro_daily completed: rows_written={len(rows)}, "
        f"source_successes={success_count}, source_failures={len(failed_sources)}"
    )
    return MacroResult(
        last_trade_date=plan.last_trade_date,
        start_date=plan.start_date,
        end_date=plan.end_date,
        due_days=plan.due_days,
        rows_written=len(rows),
        source_successes=success_count,
        source_failures=len(failed_sources),
        dry_run=False,
    )


async def async_main() -> None:
    configure_logging()
    args = parse_args()
    started = time.monotonic()
    result = await run_macro_daily(PostgresClient(), dry_run=args.dry_run)
    logger.info(
        f"macro_daily finished in {time.monotonic() - started:.1f}s "
        f"(dry_run={result.dry_run}, rows_written={result.rows_written})"
    )


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
