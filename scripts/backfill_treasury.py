from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import bindparam, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.fmp_client import FMPClient  # noqa: E402
from lib.pg_client import PostgresClient  # noqa: E402
from src.us_stock.jobs.macro_daily import ET_TZ, parse_date, parse_number  # noqa: E402


@dataclass(frozen=True)
class BackfillReport:
    backfilled_rows: int
    updated_us10y: int
    updated_us2y: int
    cleaned_garbage_spread: int


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "INFO"), format="[{level}] {message}")


def treasury_rows(payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload:
        trade_date = parse_date(item.get("date"))
        if not trade_date:
            continue
        us10y = parse_number(item.get("year10"))
        us2y = parse_number(item.get("year2"))
        rows.append(
            {
                "trade_date": trade_date,
                "us10y": us10y,
                "us2y": us2y,
                "spread_10y_2y": None if us10y is None or us2y is None else us10y - us2y,
            }
        )
    return rows


def load_min_trade_date(pg: PostgresClient) -> str:
    with pg.engine.begin() as conn:
        value = conn.execute(text("SELECT MIN(trade_date) FROM macro_daily")).scalar_one()
    if value is None:
        raise RuntimeError("macro_daily has no rows to anchor treasury backfill")
    return value.isoformat()


def count_garbage_spreads(pg: PostgresClient, rows: list[dict[str, Any]]) -> int:
    dates = [row["trade_date"] for row in rows]
    if not dates:
        return 0
    sql = text(
        """
        SELECT COUNT(*)
        FROM macro_daily
        WHERE trade_date IN :dates
          AND spread_10y_2y IS NOT NULL
          AND (spread_10y_2y < -2 OR spread_10y_2y > 2)
        """
    ).bindparams(bindparam("dates", expanding=True))
    with pg.engine.begin() as conn:
        return int(conn.execute(sql, {"dates": dates}).scalar_one() or 0)


async def run_backfill() -> BackfillReport:
    pg = PostgresClient()
    from_date = load_min_trade_date(pg)
    to_date = datetime.now(ET_TZ).date().isoformat()
    logger.info(f"treasury backfill window: {from_date} to {to_date}")
    async with FMPClient() as client:
        payload = await client.get_treasury_rates(from_date, to_date)
    rows = treasury_rows(payload)
    cleaned_garbage_spread = count_garbage_spreads(pg, rows)
    pg.upsert(
        "macro_daily",
        rows,
        conflict_cols=["trade_date"],
        update_cols=["us10y", "us2y", "spread_10y_2y"],
    )
    report = BackfillReport(
        backfilled_rows=len(rows),
        updated_us10y=sum(1 for row in rows if row["us10y"] is not None),
        updated_us2y=sum(1 for row in rows if row["us2y"] is not None),
        cleaned_garbage_spread=cleaned_garbage_spread,
    )
    logger.info(
        "treasury backfill completed: "
        f"backfilled_rows={report.backfilled_rows}, "
        f"updated_us10y={report.updated_us10y}, "
        f"updated_us2y={report.updated_us2y}, "
        f"cleaned_garbage_spread={report.cleaned_garbage_spread}"
    )
    return report


def main() -> None:
    configure_logging()
    asyncio.run(run_backfill())


if __name__ == "__main__":
    main()
