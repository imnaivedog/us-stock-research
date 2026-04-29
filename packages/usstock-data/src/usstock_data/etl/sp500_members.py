"""Refresh sp500_members_daily from FMP."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import normalize_symbol, upsert_rows
from usstock_data.etl.fmp_client import FMPClient

ET_TZ = ZoneInfo("America/New_York")


def member_rows(payload: list[dict[str, object]], as_of: date) -> list[dict[str, object]]:
    rows = []
    for item in payload:
        symbol = normalize_symbol(item.get("symbol"))
        if symbol:
            rows.append({"as_of_date": as_of, "symbol": symbol, "index_name": "S&P 500"})
    return rows


async def run(
    engine: Engine | None = None, as_of: date | None = None, dry_run: bool = False
) -> int:
    engine = engine or create_postgres_engine()
    as_of = as_of or datetime.now(ET_TZ).date()
    if dry_run:
        return 0
    async with FMPClient() as client:
        payload = await client.get_sp500_constituents()
    return upsert_rows(
        engine,
        "sp500_members_daily",
        member_rows(payload, as_of),
        conflict_cols=["as_of_date", "symbol", "index_name"],
        update_cols=["index_name"],
    )
