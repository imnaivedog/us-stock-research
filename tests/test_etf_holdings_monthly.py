from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.us_stock.jobs import etf_holdings_monthly as job  # noqa: E402


def _sqlite_conn():
    engine = create_engine("sqlite:///:memory:", future=True)
    conn = engine.connect()
    conn.execute(
        text(
            """
            CREATE TABLE etf_holdings_latest (
                etf_code TEXT NOT NULL,
                symbol TEXT NOT NULL,
                weight NUMERIC,
                as_of_date DATE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (etf_code, symbol)
            )
            """
        )
    )
    return conn


def test_replace_etf_holdings_deletes_old_and_inserts_new() -> None:
    conn = _sqlite_conn()
    conn.execute(
        text(
            """
            INSERT INTO etf_holdings_latest (etf_code, symbol, weight, as_of_date)
            VALUES ('SPY', 'OLD', 0.5, '2026-04-01')
            """
        )
    )

    rows = job.normalize_holding_rows(
        "SPY",
        [{"asset": "AAPL", "weightPercentage": 7.5}],
        "2026-04-28",
    )
    assert job.replace_etf_holdings(conn, "SPY", rows) == 1

    result = conn.execute(
        text("SELECT etf_code, symbol, weight, as_of_date FROM etf_holdings_latest")
    ).all()
    assert result == [("SPY", "AAPL", 0.075, "2026-04-28")]


def test_single_etf_failure_skips_without_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def get_etf_holdings(self, etf_code: str) -> list[dict[str, object]]:
            if etf_code == "BAD":
                raise RuntimeError("boom")
            return [{"asset": "AAPL", "weight": 0.1}]

    monkeypatch.setattr(job, "FMPClient", FakeClient)

    fetched, failed = asyncio.run(job.fetch_all_holdings(["SPY", "BAD"], "2026-04-28"))

    assert [item.etf_code for item in fetched] == ["SPY"]
    assert fetched[0].rows[0]["symbol"] == "AAPL"
    assert failed == ["BAD"]


def test_write_rate_safety_floor_triggers() -> None:
    with pytest.raises(RuntimeError, match="write rate below safety floor"):
        job.enforce_write_rate(written_etfs=89, total_etfs=100)
