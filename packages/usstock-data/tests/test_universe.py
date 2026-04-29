from __future__ import annotations

from datetime import date

from usstock_data.universe.cli import manual_m_pool_row
from usstock_data.universe.m_pool import candidate_from_screener


def test_m_pool_candidate_applies_hard_filters() -> None:
    today = date(2026, 4, 30)
    assert candidate_from_screener(
        {
            "symbol": "good",
            "exchangeShortName": "NASDAQ",
            "marketCap": 2_000_000_000,
            "price": 100,
            "avgVolume": 200_000,
            "ipoDate": "2025-01-01",
        },
        today,
    )["symbol"] == "GOOD"

    assert candidate_from_screener(
        {"symbol": "tiny", "marketCap": 100_000_000, "price": 10, "avgVolume": 2_000_000},
        today,
    ) is None
    assert candidate_from_screener(
        {
            "symbol": "new",
            "marketCap": 2_000_000_000,
            "price": 100,
            "avgVolume": 200_000,
            "ipoDate": "2026-04-01",
        },
        today,
    ) is None


def test_manual_m_pool_row_has_audit_ready_shape() -> None:
    row = manual_m_pool_row("brk.b", "manual")
    assert row["symbol"] == "BRK-B"
    assert row["pool"] == "m"
    assert row["is_active"] is True
