"""Load forward earnings dates into events_calendar."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from loguru import logger
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import normalize_symbol, parse_date, run_many
from usstock_data.etl.fmp_client import FMPClient

ET_TZ = ZoneInfo("America/New_York")


def calendar_rows(payload: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for item in payload:
        symbol = normalize_symbol(item.get("symbol"))
        event_date = parse_date(item.get("date"))
        if symbol and event_date:
            rows.append(
                {
                    "symbol": symbol,
                    "event_date": event_date,
                    "event_type": "earnings",
                    "details": item,
                }
            )
    return rows


async def run(
    engine: Engine | None = None, as_of: date | None = None, dry_run: bool = False
) -> int:
    engine = engine or create_postgres_engine()
    start = as_of or datetime.now(ET_TZ).date()
    end = start + timedelta(days=90)
    if dry_run:
        return 0
    async with FMPClient() as client:
        try:
            payload = await client.get_earnings_calendar(start.isoformat(), end.isoformat())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.info(
                    "earnings_calendar skipped: FMP endpoint unavailable status=404"
                )
                return 0
            raise
    with engine.begin() as conn:
        return run_many(
            conn,
            """
            INSERT INTO events_calendar (symbol, event_date, event_type, details)
            VALUES (:symbol, :event_date, :event_type, :details)
            ON CONFLICT (symbol, event_date, event_type)
            DO UPDATE SET details = EXCLUDED.details
            """,
            calendar_rows(payload),
        )
