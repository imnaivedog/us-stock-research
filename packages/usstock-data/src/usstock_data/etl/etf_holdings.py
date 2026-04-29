"""Refresh etf_holdings_latest from FMP."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import CONFIG_DIR, load_yaml, normalize_symbol, parse_date, parse_number, run_many
from usstock_data.etl.fmp_client import FMPClient


LOCAL_TZ = ZoneInfo("Asia/Shanghai")
HOLDING_WEIGHT_KEYS = ("weight", "weightPercentage", "percentage", "weightPercentageOfNetAssets")


def load_etf_universe() -> list[str]:
    payload = load_yaml(CONFIG_DIR / "thresholds.yaml")
    return sorted({normalize_symbol(item) for item in payload.get("etf_universe", []) if normalize_symbol(item)})


def holding_symbol(row: dict[str, object]) -> str:
    for key in ("asset", "holdingSymbol", "ticker", "symbol"):
        if symbol := normalize_symbol(row.get(key)):
            return symbol
    return ""


def holding_weight(row: dict[str, object]) -> float | None:
    for key in HOLDING_WEIGHT_KEYS:
        value = parse_number(row.get(key))
        if value is not None:
            return value if key == "weight" else value / 100
    return None


def normalize_holding_rows(etf_code: str, raw_rows: list[dict[str, object]], as_of: date) -> list[dict[str, object]]:
    rows_by_symbol: dict[str, dict[str, object]] = {}
    for raw in raw_rows:
        symbol = holding_symbol(raw)
        weight = holding_weight(raw)
        if not symbol or weight is None or weight <= 0 or weight > 1.05:
            continue
        rows_by_symbol[symbol] = {
            "etf_code": etf_code,
            "symbol": symbol,
            "weight": weight,
            "as_of_date": parse_date(raw.get("date") or raw.get("asOfDate")) or as_of,
        }
    return list(rows_by_symbol.values())


async def run(engine: Engine | None = None, as_of: date | None = None, dry_run: bool = False) -> int:
    engine = engine or create_postgres_engine()
    as_of = as_of or datetime.now(LOCAL_TZ).date()
    etfs = load_etf_universe()
    logger.info("etf_holdings refresh ETF count: {}", len(etfs))
    if dry_run:
        return 0
    async with FMPClient() as client:
        results = await asyncio.gather(*(client.get_etf_holdings(etf) for etf in etfs), return_exceptions=True)
    total = 0
    with engine.begin() as conn:
        for etf, result in zip(etfs, results, strict=True):
            if isinstance(result, Exception):
                logger.exception("Skipping ETF holdings for {}", etf)
                continue
            rows = normalize_holding_rows(etf, result, as_of)
            conn.execute(text("DELETE FROM etf_holdings_latest WHERE etf_code = :etf_code"), {"etf_code": etf})
            total += run_many(
                conn,
                """
                INSERT INTO etf_holdings_latest (etf_code, symbol, weight, as_of_date)
                VALUES (:etf_code, :symbol, :weight, :as_of_date)
                """,
                rows,
            )
    return total
