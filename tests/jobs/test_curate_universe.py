from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.us_stock.jobs import curate_universe as job  # noqa: E402


def member(symbol: str, market_cap: int = 2_000_000_000) -> job.UniverseMember:
    return job.UniverseMember(symbol=symbol, market_cap=job.parse_market_cap(market_cap))


def test_build_diff_three_sets_and_forced_in() -> None:
    snapshot = job.UniverseSnapshot(
        fmp_eligible={"AAA": member("AAA"), "BBB": member("BBB")},
        watchlist_symbols={"CCC"},
        current_active={"BBB", "DDD"},
        all_known={"BBB", "CCC", "DDD"},
    )

    diff = job.build_diff(snapshot)

    assert diff.should_be_active == {"AAA", "BBB", "CCC"}
    assert diff.to_add == {"AAA", "CCC"}
    assert diff.to_remove == {"DDD"}
    assert diff.forced_in == {"CCC"}
    assert diff.to_create == {"AAA"}


def test_watchlist_empty_uses_market_cap_only() -> None:
    snapshot = job.UniverseSnapshot(
        fmp_eligible={"AAA": member("AAA")},
        watchlist_symbols=set(),
        current_active={"OLD"},
        all_known={"OLD"},
    )

    diff = job.build_diff(snapshot)

    assert diff.should_be_active == {"AAA"}
    assert diff.to_add == {"AAA"}
    assert diff.to_remove == {"OLD"}
    assert diff.forced_in == set()


@dataclass
class _FakeFMP:
    payload: list[dict[str, Any]]

    async def __aenter__(self) -> _FakeFMP:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def _request(self, _path: str, params: dict[str, Any] | None = None) -> Any:
        return self.payload


@pytest.mark.parametrize("payload", [[], [{"symbol": "AAA"}] * 499])
def test_fmp_failure_floor_aborts(payload: list[dict[str, Any]]) -> None:
    job.MIN_FMP_ELIGIBLE_ROWS = 500

    async def run() -> None:
        await job.fetch_fmp_eligible(_FakeFMP(payload))

    with pytest.raises(RuntimeError):
        asyncio.run(run())


def test_fmp_screener_filters_etfs_and_funds() -> None:
    payload = [
        {
            "symbol": "AAPL",
            "companyName": "Apple Inc.",
            "sector": "Technology",
            "marketCap": 2_000_000_000,
            "country": "US",
            "exchangeShortName": "NASDAQ",
            "isEtf": False,
            "isFund": False,
        },
        {
            "symbol": "SPY",
            "companyName": "SPDR S&P 500 ETF Trust",
            "sector": "ETF",
            "marketCap": 2_000_000_000,
            "country": "US",
            "exchangeShortName": "AMEX",
            "isEtf": True,
            "isFund": False,
        },
        {
            "symbol": "AADEX",
            "companyName": "Mutual Fund",
            "sector": "Financial Services",
            "marketCap": 2_000_000_000,
            "country": "US",
            "exchangeShortName": "NASDAQ",
            "isEtf": False,
            "isFund": True,
        },
    ]
    old_floor = job.MIN_FMP_ELIGIBLE_ROWS
    job.MIN_FMP_ELIGIBLE_ROWS = 1
    try:
        members = asyncio.run(job.fetch_fmp_eligible(_FakeFMP(payload)))
    finally:
        job.MIN_FMP_ELIGIBLE_ROWS = old_floor

    assert set(members) == {"AAPL"}


def make_sqlite_conn():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    conn = engine.connect()
    conn.execute(
        text(
            """
            CREATE TABLE symbol_universe (
                symbol TEXT PRIMARY KEY,
                source TEXT,
                is_candidate BOOLEAN,
                is_active BOOLEAN,
                market_cap NUMERIC,
                added_date DATE,
                as_of_date DATE,
                filter_reason TEXT,
                first_seen DATE,
                last_seen DATE,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE symbol_universe_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                change_date DATE NOT NULL,
                change_type TEXT NOT NULL,
                reason TEXT,
                market_cap NUMERIC,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    return conn


def test_first_seen_is_not_overwritten_and_reentry_clears_last_seen() -> None:
    conn = make_sqlite_conn()
    conn.execute(
        text(
            """
            INSERT INTO symbol_universe (
                symbol, is_active, first_seen, last_seen
            ) VALUES ('AAA', false, '2024-01-01', '2024-06-01')
            """
        )
    )
    snapshot = job.UniverseSnapshot(
        fmp_eligible={"AAA": member("AAA")},
        watchlist_symbols=set(),
        current_active=set(),
        all_known={"AAA"},
    )
    diff = job.build_diff(snapshot)

    old_floor = job.MIN_FINAL_ACTIVE_ROWS
    job.MIN_FINAL_ACTIVE_ROWS = 1
    try:
        result = job.apply_diff(conn, snapshot, diff, date(2026, 4, 27))
    finally:
        job.MIN_FINAL_ACTIVE_ROWS = old_floor

    row = conn.execute(
        text("SELECT is_active, first_seen, last_seen FROM symbol_universe WHERE symbol='AAA'")
    ).one()
    assert bool(row.is_active) is True
    assert str(row.first_seen) == "2024-01-01"
    assert row.last_seen is None
    assert result.audit_rows == 1


def test_forced_in_priority_writes_forced_audit() -> None:
    rows = job.audit_rows_for_diff(
        job.UniverseDiff(
            should_be_active={"AAA"},
            to_add={"AAA"},
            to_remove=set(),
            forced_in={"AAA"},
            to_create=set(),
        ),
        {},
        date(2026, 4, 27),
    )

    assert rows == [
        {
            "symbol": "AAA",
            "change_date": date(2026, 4, 27),
            "change_type": "forced_in",
            "reason": "watchlist",
            "market_cap": None,
        }
    ]
