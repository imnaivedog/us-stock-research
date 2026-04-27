from __future__ import annotations

import argparse
import asyncio
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Connection

from lib.fmp_client import FMPClient
from lib.pg_client import PostgresClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
THRESHOLDS_PATH = PROJECT_ROOT / "config" / "thresholds.yaml"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
MIN_WRITE_RATE = 0.9
HOLDING_WEIGHT_MAX = 1.05
HOLDING_WEIGHT_KEYS = (
    "weight",
    "weightPercentage",
    "percentage",
    "weightPercentageOfNetAssets",
)
API_KEY_RE = re.compile(r"apikey=[^&'\"]+")


@dataclass(frozen=True)
class ETFHoldingsFetch:
    etf_code: str
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class ETFHoldingsResult:
    total_etfs: int
    written_etfs: int
    failed_etfs: int
    total_holdings_rows: int
    write_rate: float
    dry_run: bool


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "INFO"), format="[{level}] {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh etf_holdings_latest monthly.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print ETF count and current holdings row count without FMP calls or DB writes.",
    )
    return parser.parse_args()


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(".", "-")


def parse_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def parse_date(value: Any) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date().isoformat()
    except ValueError:
        return None


def load_etf_universe(path: Path = THRESHOLDS_PATH) -> list[str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_etfs = payload.get("etf_universe")
    if not isinstance(raw_etfs, list) or not raw_etfs:
        raise RuntimeError(f"etf_universe missing from {path}")
    return sorted({normalize_symbol(item) for item in raw_etfs if normalize_symbol(item)})


def current_holdings_count(pg: PostgresClient) -> int:
    with pg.engine.begin() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM etf_holdings_latest")).scalar_one() or 0)


def holding_symbol(row: dict[str, Any]) -> str:
    for key in ("asset", "holdingSymbol", "ticker", "symbol"):
        symbol = normalize_symbol(row.get(key))
        if symbol:
            return symbol
    return ""


def holding_weight(row: dict[str, Any]) -> float | None:
    for key in HOLDING_WEIGHT_KEYS:
        value = parse_number(row.get(key))
        if value is not None:
            return value if key == "weight" else value / 100
    return None


def holding_as_of_date(row: dict[str, Any], fallback: str) -> str:
    for key in ("date", "asOfDate", "as_of_date", "reportedDate", "updatedAt"):
        parsed = parse_date(row.get(key))
        if parsed:
            return parsed
    return fallback


def redact_secrets(value: object) -> str:
    return API_KEY_RE.sub("apikey=<redacted>", str(value))


def normalize_holding_rows(
    etf_code: str,
    raw_rows: list[dict[str, Any]],
    as_of_date: str,
) -> list[dict[str, Any]]:
    rows_by_symbol: dict[str, dict[str, Any]] = {}
    for raw in raw_rows:
        symbol = holding_symbol(raw)
        if not symbol:
            continue
        weight = holding_weight(raw)
        if weight is None or weight <= 0 or weight > HOLDING_WEIGHT_MAX:
            continue
        rows_by_symbol[symbol] = {
            "etf_code": etf_code,
            "symbol": symbol,
            "weight": weight,
            "as_of_date": holding_as_of_date(raw, as_of_date),
        }
    return list(rows_by_symbol.values())


async def fetch_etf_holdings(
    client: FMPClient,
    etf_code: str,
    as_of_date: str,
) -> ETFHoldingsFetch:
    raw_rows = await client.get_etf_holdings(etf_code)
    return ETFHoldingsFetch(
        etf_code=etf_code,
        rows=normalize_holding_rows(etf_code, raw_rows, as_of_date),
    )


async def fetch_all_holdings(
    etf_codes: list[str],
    as_of_date: str,
) -> tuple[list[ETFHoldingsFetch], list[str]]:
    fetched: list[ETFHoldingsFetch] = []
    failed: list[str] = []
    async with FMPClient() as client:
        results = await asyncio.gather(
            *(fetch_etf_holdings(client, etf_code, as_of_date) for etf_code in etf_codes),
            return_exceptions=True,
        )
    for etf_code, result in zip(etf_codes, results, strict=True):
        if isinstance(result, Exception):
            failed.append(etf_code)
            logger.warning(f"Skipping ETF {etf_code}: {redact_secrets(result)}")
            continue
        fetched.append(result)
    return fetched, failed


def enforce_write_rate(written_etfs: int, total_etfs: int) -> float:
    write_rate = 1.0 if total_etfs == 0 else written_etfs / total_etfs
    if write_rate < MIN_WRITE_RATE:
        raise RuntimeError(
            "etf_holdings write rate below safety floor: "
            f"{written_etfs}/{total_etfs}={write_rate:.3f}"
        )
    return write_rate


def replace_etf_holdings(conn: Connection, etf_code: str, rows: list[dict[str, Any]]) -> int:
    conn.execute(
        text("DELETE FROM etf_holdings_latest WHERE etf_code = :etf_code"),
        {"etf_code": etf_code},
    )
    if not rows:
        return 0
    conn.execute(
        text(
            """
            INSERT INTO etf_holdings_latest (etf_code, symbol, weight, as_of_date)
            VALUES (:etf_code, :symbol, :weight, :as_of_date)
            """
        ),
        rows,
    )
    return len(rows)


def replace_all_holdings(pg: PostgresClient, fetched: list[ETFHoldingsFetch]) -> int:
    total_rows = 0
    with pg.engine.begin() as conn:
        for item in fetched:
            total_rows += replace_etf_holdings(conn, item.etf_code, item.rows)
    return total_rows


async def run_etf_holdings_monthly(pg: PostgresClient, dry_run: bool = False) -> ETFHoldingsResult:
    started_at = datetime.now(LOCAL_TZ).date().isoformat()
    etf_codes = load_etf_universe()
    current_rows = current_holdings_count(pg)
    logger.info(f"etf_holdings_monthly ETF count: {len(etf_codes)}")
    logger.info(f"etf_holdings_latest current rows: {current_rows}")
    if dry_run:
        return ETFHoldingsResult(
            total_etfs=len(etf_codes),
            written_etfs=0,
            failed_etfs=0,
            total_holdings_rows=0,
            write_rate=0.0,
            dry_run=True,
        )

    fetched, failed = await fetch_all_holdings(etf_codes, started_at)
    written_etfs = sum(1 for item in fetched if item.rows)
    write_rate = enforce_write_rate(written_etfs, len(etf_codes))
    total_rows = replace_all_holdings(pg, fetched)
    logger.info(
        f"etf_holdings_monthly completed: written_etfs={written_etfs}, "
        f"failed_etfs={len(failed)}, total_holdings_rows={total_rows}, "
        f"write_rate={write_rate:.3f}"
    )
    return ETFHoldingsResult(
        total_etfs=len(etf_codes),
        written_etfs=written_etfs,
        failed_etfs=len(failed),
        total_holdings_rows=total_rows,
        write_rate=write_rate,
        dry_run=False,
    )


async def async_main() -> None:
    configure_logging()
    args = parse_args()
    started = time.monotonic()
    result = await run_etf_holdings_monthly(PostgresClient(), dry_run=args.dry_run)
    logger.info(
        f"etf_holdings_monthly finished in {time.monotonic() - started:.1f}s "
        f"(dry_run={result.dry_run}, total_holdings_rows={result.total_holdings_rows})"
    )


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
