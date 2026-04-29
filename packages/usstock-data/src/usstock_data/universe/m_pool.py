"""M-pool automatic curation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from usstock_data.etl.common import normalize_symbol, parse_date, parse_number
from usstock_data.etl.fmp_client import FMPClient
from usstock_data.universe.core import audit_change, engine_or_default, upsert_universe_symbols


LOCAL_TZ = ZoneInfo("Asia/Shanghai")
MARKET_CAP_MIN = 1_000_000_000
ADV_20D_MIN = 10_000_000
IPO_DAYS_MIN = 90
ALLOWED_EXCHANGES = {"NASDAQ", "NYSE", "AMEX"}


def candidate_from_screener(item: dict[str, Any], today: date) -> dict[str, Any] | None:
    symbol = normalize_symbol(item.get("symbol"))
    if not symbol:
        return None
    exchange = str(item.get("exchangeShortName") or item.get("exchange") or "").upper()
    if exchange and exchange not in ALLOWED_EXCHANGES:
        return None
    market_cap = parse_number(item.get("marketCap"))
    price = parse_number(item.get("price"))
    volume = parse_number(item.get("volume") or item.get("avgVolume"))
    adv_20d = parse_number(item.get("avgVolume20d")) or (price * volume if price and volume else None)
    ipo_date = parse_date(item.get("ipoDate"))
    if market_cap is not None and market_cap < MARKET_CAP_MIN:
        return None
    if adv_20d is not None and adv_20d < ADV_20D_MIN:
        return None
    if ipo_date and (today - ipo_date).days < IPO_DAYS_MIN:
        return None
    return {
        "symbol": symbol,
        "pool": "m",
        "source": "fmp_screener",
        "is_candidate": True,
        "is_active": True,
        "market_cap": market_cap,
        "adv_20d": adv_20d,
        "ipo_date": ipo_date,
        "added_date": today,
        "as_of_date": today,
        "filter_reason": "m_pool_auto_curated",
        "thesis_url": None,
        "target_market_cap": None,
    }


async def fetch_candidates(today: date) -> list[dict[str, Any]]:
    async with FMPClient() as client:
        payload = await client.get_company_screener(
            {
                "marketCapMoreThan": MARKET_CAP_MIN,
                "isActivelyTrading": "true",
                "isEtf": "false",
                "isFund": "false",
                "country": "US",
                "exchangeShortName": ",".join(sorted(ALLOWED_EXCHANGES)),
                "limit": 10000,
            }
        )
    return [row for item in payload if (row := candidate_from_screener(item, today))]


async def sync(engine: Engine | None = None, today: date | None = None, dry_run: bool = False) -> dict[str, int]:
    engine = engine_or_default(engine)
    today = today or datetime.now(LOCAL_TZ).date()
    candidates = await fetch_candidates(today)
    candidate_symbols = {row["symbol"] for row in candidates}
    logger.info("m_pool candidates: {}", len(candidate_symbols))
    if dry_run:
        return {"candidates": len(candidate_symbols), "upserted": 0, "removed": 0}
    with engine.begin() as conn:
        current = set(
            conn.execute(
                text("SELECT symbol FROM symbol_universe WHERE pool = 'm' AND is_active IS TRUE")
            ).scalars()
        )
    upserted = upsert_universe_symbols(engine, candidates)
    to_remove = sorted(current - candidate_symbols)
    if to_remove:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE symbol_universe
                    SET is_active = false, removed_date = :today, last_seen = :today, updated_at = now()
                    WHERE pool = 'm' AND symbol IN :symbols
                    """
                ).bindparams(bindparam("symbols", expanding=True)),
                {"today": today, "symbols": to_remove},
            )
        for symbol in to_remove:
            audit_change(engine, symbol, "removed", pool="m", reason="m_pool_auto_curate_removed")
    for symbol in sorted(candidate_symbols - current):
        audit_change(engine, symbol, "added", pool="m", reason="m_pool_auto_curate_added")
    return {"candidates": len(candidate_symbols), "upserted": upserted, "removed": len(to_remove)}
