"""Weekly shares-outstanding refresh from Polygon."""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import normalize_symbol, parse_number

POLYGON_BASE_URL = "https://api.polygon.io"


@dataclass(frozen=True)
class SharesOutstandingRow:
    symbol: str
    shares_outstanding: float
    updated_at: datetime


def row_from_polygon_response(symbol: str, payload: dict[str, Any]) -> SharesOutstandingRow | None:
    result = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return None
    value = parse_number(result.get("share_class_shares_outstanding"))
    if value is None or value <= 0:
        return None
    return SharesOutstandingRow(
        symbol=normalize_symbol(symbol),
        shares_outstanding=value,
        updated_at=datetime.now(UTC),
    )


def warn_row(symbol: str, message: str) -> dict[str, Any]:
    return {
        "job_name": "shares_outstanding",
        "symbol": normalize_symbol(symbol),
        "trade_date": None,
        "severity": "WARN",
        "category": "shares_outstanding",
        "message": message,
    }


async def fetch_polygon_symbol(
    client: httpx.AsyncClient,
    symbol: str,
    api_key: str,
) -> SharesOutstandingRow | None:
    response = await client.get(f"/v3/reference/tickers/{symbol}", params={"apiKey": api_key})
    response.raise_for_status()
    return row_from_polygon_response(symbol, response.json())


def load_symbols(
    engine: Engine,
    symbols: list[str] | None = None,
    pool: str | None = None,
) -> list[str]:
    if symbols:
        return sorted({normalize_symbol(symbol) for symbol in symbols})
    with engine.begin() as conn:
        if pool:
            return [
                normalize_symbol(row[0])
                for row in conn.execute(
                    text(
                        """
                        SELECT symbol
                        FROM symbol_universe
                        WHERE pool = :pool AND is_active IS TRUE
                        ORDER BY market_cap DESC NULLS LAST, symbol
                        """
                    ),
                    {"pool": pool},
                )
            ]
        rows = conn.execute(
            text(
                """
                (
                  SELECT symbol
                  FROM symbol_universe
                  WHERE pool = 'a' AND is_active IS TRUE
                )
                UNION
                (
                  SELECT symbol
                  FROM symbol_universe
                  WHERE COALESCE(pool, 'm') = 'm' AND is_active IS TRUE
                  ORDER BY market_cap DESC NULLS LAST, symbol
                  LIMIT 200
                )
                ORDER BY symbol
                """
            )
        )
        return [normalize_symbol(row[0]) for row in rows]


def upsert_rows(engine: Engine, rows: list[SharesOutstandingRow]) -> int:
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE symbol_universe
                SET shares_outstanding = :shares_outstanding,
                    shares_outstanding_updated_at = :updated_at,
                    updated_at = now()
                WHERE symbol = :symbol
                """
            ),
            [row.__dict__ for row in rows],
        )
    return len(rows)


def write_alerts(engine: Engine, alerts: list[dict[str, Any]]) -> int:
    if not alerts:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO alert_log (job_name, symbol, trade_date, severity, category, message)
                VALUES (:job_name, :symbol, :trade_date, :severity, :category, :message)
                """
            ),
            alerts,
        )
    return len(alerts)


def stale_shares_alerts(engine: Engine) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT symbol
                FROM symbol_universe
                WHERE is_active IS TRUE
                  AND shares_outstanding_updated_at IS NOT NULL
                  AND shares_outstanding_updated_at < now() - interval '30 days'
                """
            )
        ).scalars()
        return [warn_row(str(symbol), "shares_outstanding older than 30 days") for symbol in rows]


async def run(
    engine: Engine | None = None,
    symbols: list[str] | None = None,
    pool: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    engine = engine or create_postgres_engine()
    selected = load_symbols(engine, symbols=symbols, pool=pool)
    logger.info("shares_outstanding selected symbols={}", len(selected))
    if dry_run:
        return {"selected": len(selected), "written": 0, "warned": 0}
    api_key = os.getenv("POLYGON_API_KEY", "")
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY is required")
    rows: list[SharesOutstandingRow] = []
    alerts: list[dict[str, Any]] = []
    async with httpx.AsyncClient(base_url=POLYGON_BASE_URL, timeout=30.0) as client:
        results = await asyncio.gather(
            *(fetch_polygon_symbol(client, symbol, api_key) for symbol in selected),
            return_exceptions=True,
        )
    for symbol, result in zip(selected, results, strict=True):
        if isinstance(result, Exception):
            alerts.append(warn_row(symbol, f"Polygon fetch failed: {result}"))
            continue
        if result is None:
            alerts.append(warn_row(symbol, "Polygon response missing shares outstanding"))
            continue
        rows.append(result)
    written = upsert_rows(engine, rows)
    warned = write_alerts(engine, alerts + stale_shares_alerts(engine))
    return {"selected": len(selected), "written": written, "warned": warned}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-data etl shares-outstanding")
    parser.add_argument("--symbols", help="Comma-separated symbols.")
    parser.add_argument("--pool", choices=["a", "m"])
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    symbols = [item.strip() for item in args.symbols.split(",")] if args.symbols else None
    result = asyncio.run(run(symbols=symbols, pool=args.pool, dry_run=args.dry_run))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
