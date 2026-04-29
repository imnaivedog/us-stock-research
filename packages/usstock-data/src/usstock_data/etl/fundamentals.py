"""Load quarterly fundamentals needed by stock scoring."""

from __future__ import annotations

import asyncio
from datetime import date

from loguru import logger
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import fetch_symbols_in_pool, parse_date, parse_number, upsert_rows
from usstock_data.etl.fmp_client import FMPClient


def fundamentals_rows(
    symbol: str,
    income: list[dict[str, object]],
    cash_flow: list[dict[str, object]],
    surprises: list[dict[str, object]],
) -> list[dict[str, object]]:
    cash_by_period = {
        parse_date(row.get("date") or row.get("period_end")): row for row in cash_flow
    }
    surprise_by_period = {
        parse_date(row.get("date") or row.get("period_end")): row for row in surprises
    }
    rows: list[dict[str, object]] = []
    for item in income:
        period_end = parse_date(item.get("date") or item.get("period_end"))
        if not period_end:
            continue
        cash = cash_by_period.get(period_end, {})
        surprise = surprise_by_period.get(period_end, {})
        rows.append(
            {
                "symbol": symbol,
                "period_end": period_end,
                "fiscal_period": str(
                    item.get("period") or item.get("fiscal_period") or "Q"
                ).upper(),
                "reported_at": item.get("reportedCurrencyDate")
                or item.get("fillingDate")
                or surprise.get("date"),
                "revenue": parse_number(item.get("revenue")),
                "eps_actual": parse_number(surprise.get("actualEarningResult") or item.get("eps")),
                "eps_estimate": parse_number(surprise.get("estimatedEarning")),
                "net_income": parse_number(item.get("netIncome")),
                "operating_cash_flow": parse_number(cash.get("operatingCashFlow")),
                "free_cash_flow": parse_number(cash.get("freeCashFlow")),
                "guidance": None,
            }
        )
    return rows


async def fetch_symbol_fundamentals(client: FMPClient, symbol: str) -> list[dict[str, object]]:
    income, cash_flow, surprises = await asyncio.gather(
        client.get_income_statement(symbol),
        client.get_cash_flow_statement(symbol),
        client.get_earnings_surprises(symbol),
    )
    return fundamentals_rows(symbol, income, cash_flow, surprises)


async def run(
    engine: Engine | None = None, as_of: date | None = None, dry_run: bool = False
) -> int:
    del as_of
    engine = engine or create_postgres_engine()
    with engine.begin() as conn:
        symbols = fetch_symbols_in_pool(conn, "all")
    logger.info("fundamentals fetch symbols: {}", len(symbols))
    if dry_run:
        return 0
    rows: list[dict[str, object]] = []
    async with FMPClient() as client:
        results = await asyncio.gather(
            *(fetch_symbol_fundamentals(client, symbol) for symbol in symbols),
            return_exceptions=True,
        )
    for symbol, result in zip(symbols, results, strict=True):
        if isinstance(result, Exception):
            logger.exception("Skipping fundamentals for {}", symbol)
            continue
        rows.extend(result)
    return upsert_rows(
        engine,
        "fundamentals_quarterly",
        rows,
        conflict_cols=["symbol", "period_end"],
        update_cols=[
            "fiscal_period",
            "reported_at",
            "revenue",
            "eps_actual",
            "eps_estimate",
            "net_income",
            "operating_cash_flow",
            "free_cash_flow",
            "guidance",
        ],
    )
