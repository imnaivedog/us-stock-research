"""A-pool manual thesis management and optional Notion sync."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from notion_client import Client
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_data.etl.common import normalize_symbol
from usstock_data.universe.core import audit_change, engine_or_default, upsert_universe_symbols


LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def add(
    symbol: str,
    *,
    engine: Engine | None = None,
    thesis_url: str | None = None,
    target_market_cap: float | None = None,
    source: str = "manual",
    today: date | None = None,
) -> None:
    engine = engine_or_default(engine)
    today = today or datetime.now(LOCAL_TZ).date()
    symbol = normalize_symbol(symbol)
    upsert_universe_symbols(
        engine,
        [
            {
                "symbol": symbol,
                "pool": "a",
                "source": source,
                "is_candidate": True,
                "is_active": True,
                "market_cap": None,
                "adv_20d": None,
                "ipo_date": None,
                "added_date": today,
                "as_of_date": today,
                "filter_reason": "a_pool_manual",
                "thesis_url": thesis_url,
                "target_market_cap": target_market_cap,
            }
        ],
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO watchlist (
                    symbol, source, added_date, target_market_cap, status, thesis_url, updated_at
                )
                VALUES (:symbol, :source, :added_date, :target_market_cap, 'watching', :thesis_url, now())
                ON CONFLICT (symbol) DO UPDATE SET
                    source = EXCLUDED.source,
                    target_market_cap = EXCLUDED.target_market_cap,
                    thesis_url = EXCLUDED.thesis_url,
                    updated_at = now()
                """
            ),
            {
                "symbol": symbol,
                "source": source,
                "added_date": today,
                "target_market_cap": target_market_cap,
                "thesis_url": thesis_url,
            },
        )
    audit_change(
        engine,
        symbol,
        "forced_in",
        pool="a",
        reason="a_pool_manual_add",
        thesis_url=thesis_url,
        target_market_cap=target_market_cap,
    )


def remove(symbol: str, *, engine: Engine | None = None, reason: str | None = None) -> None:
    engine = engine_or_default(engine)
    symbol = normalize_symbol(symbol)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE symbol_universe
                SET is_active = false, removed_date = CURRENT_DATE, last_seen = CURRENT_DATE, updated_at = now()
                WHERE symbol = :symbol AND pool = 'a'
                """
            ),
            {"symbol": symbol},
        )
        conn.execute(text("UPDATE watchlist SET status = 'exited', updated_at = now() WHERE symbol = :symbol"), {"symbol": symbol})
    audit_change(engine, symbol, "removed", pool="a", reason=reason or "a_pool_manual_remove")


def set_target(symbol: str, target_market_cap: float, *, engine: Engine | None = None) -> None:
    engine = engine_or_default(engine)
    symbol = normalize_symbol(symbol)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE symbol_universe
                SET target_market_cap = :target_market_cap, updated_at = now()
                WHERE symbol = :symbol AND pool = 'a'
                """
            ),
            {"symbol": symbol, "target_market_cap": target_market_cap},
        )
        conn.execute(
            text("UPDATE watchlist SET target_market_cap = :target_market_cap, updated_at = now() WHERE symbol = :symbol"),
            {"symbol": symbol, "target_market_cap": target_market_cap},
        )
    audit_change(
        engine,
        symbol,
        "forced_in",
        pool="a",
        reason="a_pool_target_updated",
        target_market_cap=target_market_cap,
    )


def _plain_text(prop: dict[str, Any]) -> str:
    parts = prop.get("title") or prop.get("rich_text") or []
    return "".join(part.get("plain_text", "") for part in parts).strip()


def _url(prop: dict[str, Any]) -> str | None:
    return prop.get("url") or _plain_text(prop) or None


def _number(prop: dict[str, Any]) -> float | None:
    value = prop.get("number")
    return float(value) if value is not None else None


def rows_from_notion() -> list[dict[str, Any]]:
    token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_A_POOL_DB_ID")
    if not token or not database_id:
        logger.info("NOTION_TOKEN/NOTION_A_POOL_DB_ID not set; a_pool notion sync skipped")
        return []
    client = Client(auth=token)
    response = client.databases.query(database_id=database_id)
    rows = []
    for page in response.get("results", []):
        props = page.get("properties", {})
        symbol = normalize_symbol(
            _plain_text(props.get("Symbol", {}))
            or _plain_text(props.get("Name", {}))
            or _plain_text(props.get("Ticker", {}))
        )
        if not symbol:
            continue
        rows.append(
            {
                "symbol": symbol,
                "thesis_url": _url(props.get("Thesis", {})) or page.get("url"),
                "target_market_cap": _number(props.get("Target Cap", {})),
            }
        )
    return rows


def sync(engine: Engine | None = None) -> dict[str, int]:
    rows = rows_from_notion()
    for row in rows:
        add(
            row["symbol"],
            engine=engine,
            thesis_url=row.get("thesis_url"),
            target_market_cap=row.get("target_market_cap"),
            source="notion",
        )
    return {"synced": len(rows)}
