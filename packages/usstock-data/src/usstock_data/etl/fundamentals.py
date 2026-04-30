"""Load quarterly fundamentals needed by stock scoring."""

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
    upsert_rows,
)
from usstock_data.etl.fmp_client import FMPClient, FMPTransientError


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


def collect_fundamental_results(
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
            logger.debug("fundamentals skip {}: empty response", normalized_symbol)
        elif isinstance(result, FMPTransientError):
            skip_count += 1
            logger.opt(exception=result).error("fundamentals failed for {}", normalized_symbol)
        elif isinstance(result, Exception):
            skip_count += 1
            logger.opt(exception=result).debug("fundamentals skip {}", normalized_symbol)
        else:
            success_count += 1
            rows.extend(result)

        if skip_count and skip_count % 200 == 0:
            logger.info(
                "fundamentals: skipped {}/{}, success {}",
                skip_count,
                total,
                success_count,
            )
    logger.info(
        "fundamentals done: {} success / {} skipped / {} total",
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
    logger.info("fundamentals fetch symbols: {}", len(symbols))
    if dry_run:
        return 0
    rows: list[dict[str, object]] = []
    async with FMPClient() as client:
        results = await asyncio.gather(
            *(fetch_symbol_fundamentals(client, symbol) for symbol in symbols),
            return_exceptions=True,
        )
    rows, _success_count, _skip_count = collect_fundamental_results(symbols, results)
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
