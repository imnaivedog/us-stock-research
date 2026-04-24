from __future__ import annotations

import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from lib.fmp_client import FMPClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS_PATH = PROJECT_ROOT / "config" / "thresholds.yaml"


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = value.replace("_", "").replace(",", "")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _load_thresholds() -> dict[str, Any]:
    with THRESHOLDS_PATH.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    return config.get("universe_filter", {})


def _historical_adv_20d(history: list[dict[str, Any]]) -> float | None:
    values: list[float] = []
    for row in history:
        close = _number(row.get("adjClose") or row.get("close"))
        volume = _number(row.get("volume"))
        if close is not None and volume is not None:
            values.append(close * volume)
        if len(values) >= 20:
            break
    if not values:
        return None
    return sum(values) / len(values)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


async def _filter_one(client: FMPClient, symbol: str, thresholds: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    today = date.today()
    profile = await client.get_profile(symbol)
    history = await client.get_historical(
        symbol,
        from_date=(today - timedelta(days=30)).isoformat(),
        to_date=today.isoformat(),
    )

    market_cap = _number(profile.get("mktCap") or profile.get("marketCap"))
    adv_20d = _historical_adv_20d(history)
    ipo_date = _parse_date(profile.get("ipoDate"))
    is_actively_trading = _bool(profile.get("isActivelyTrading"))

    market_cap_min = _number(thresholds.get("market_cap_min_usd")) or 1_000_000_000
    adv_min = _number(thresholds.get("avg_dollar_volume_20d_min_usd")) or 10_000_000
    ipo_days_min = int(_number(thresholds.get("ipo_days_min")) or 90)
    must_be_active = _bool(thresholds.get("must_be_actively_trading", True))

    failures: list[str] = []
    if market_cap is None or market_cap < market_cap_min:
        failures.append("market_cap<$1B")
    if adv_20d is None or adv_20d < adv_min:
        failures.append("adv_20d<$10M")
    if ipo_date is None:
        failures.append("ipo_date_missing")
    elif (today - ipo_date).days < ipo_days_min:
        failures.append("ipoDate<90d")
    if must_be_active and not is_actively_trading:
        failures.append("not_actively_trading")

    return symbol, {
        "is_active": not failures,
        "reason": "pass" if not failures else ",".join(failures),
        "market_cap": market_cap,
        "adv_20d": adv_20d,
        "ipo_date": ipo_date.isoformat() if ipo_date else None,
    }


async def _filter_many(symbols: list[str]) -> dict[str, dict[str, Any]]:
    thresholds = _load_thresholds()
    async with FMPClient() as client:
        tasks = [_filter_one(client, symbol, thresholds) for symbol in symbols]
        results = await asyncio.gather(*tasks)
    return dict(results)


async def async_filter_universe(symbols: list[str]) -> dict[str, dict[str, Any]]:
    cleaned = sorted({symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()})
    if not cleaned:
        return {}
    return await _filter_many(cleaned)


def filter_universe(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Apply ADR-023 hard filter to symbols via FMP profile and recent prices."""

    return asyncio.run(async_filter_universe(symbols))
