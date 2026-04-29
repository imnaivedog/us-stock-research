"""Shared universe persistence helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import normalize_symbol


def engine_or_default(engine: Engine | None = None) -> Engine:
    return engine or create_postgres_engine()


def audit_change(
    engine: Engine,
    symbol: str,
    change_type: str,
    *,
    pool: str,
    reason: str | None = None,
    market_cap: float | None = None,
    thesis_url: str | None = None,
    target_market_cap: float | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO symbol_universe_changes (
                    symbol, change_type, reason, market_cap, pool, thesis_url, target_market_cap
                )
                VALUES (:symbol, :change_type, :reason, :market_cap, :pool, :thesis_url, :target_market_cap)
                """
            ),
            {
                "symbol": normalize_symbol(symbol),
                "change_type": change_type,
                "reason": reason,
                "market_cap": market_cap,
                "pool": pool,
                "thesis_url": thesis_url,
                "target_market_cap": target_market_cap,
            },
        )


def upsert_universe_symbols(engine: Engine, rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    normalized = [{**row, "symbol": normalize_symbol(row["symbol"])} for row in rows]
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO symbol_universe (
                    symbol, pool, source, is_candidate, is_active, market_cap, adv_20d,
                    ipo_date, added_date, as_of_date, filter_reason, thesis_url,
                    target_market_cap
                )
                VALUES (
                    :symbol, :pool, :source, :is_candidate, :is_active, :market_cap, :adv_20d,
                    :ipo_date, COALESCE(:added_date, CURRENT_DATE), :as_of_date, :filter_reason,
                    :thesis_url, :target_market_cap
                )
                ON CONFLICT (symbol) DO UPDATE SET
                    pool = EXCLUDED.pool,
                    source = COALESCE(EXCLUDED.source, symbol_universe.source),
                    is_candidate = EXCLUDED.is_candidate,
                    is_active = EXCLUDED.is_active,
                    market_cap = COALESCE(EXCLUDED.market_cap, symbol_universe.market_cap),
                    adv_20d = COALESCE(EXCLUDED.adv_20d, symbol_universe.adv_20d),
                    ipo_date = COALESCE(EXCLUDED.ipo_date, symbol_universe.ipo_date),
                    as_of_date = EXCLUDED.as_of_date,
                    filter_reason = EXCLUDED.filter_reason,
                    thesis_url = COALESCE(EXCLUDED.thesis_url, symbol_universe.thesis_url),
                    target_market_cap = COALESCE(
                        EXCLUDED.target_market_cap, symbol_universe.target_market_cap
                    ),
                    updated_at = now()
                """
            ),
            normalized,
        )
    return len(normalized)
