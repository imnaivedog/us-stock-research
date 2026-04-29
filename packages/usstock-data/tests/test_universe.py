from __future__ import annotations

from datetime import date

import pytest
from usstock_data.universe import a_pool
from usstock_data.universe.cli import manual_m_pool_row
from usstock_data.universe.m_pool import candidate_from_screener


def test_m_pool_candidate_applies_hard_filters() -> None:
    today = date(2026, 4, 30)
    assert (
        candidate_from_screener(
            {
                "symbol": "good",
                "exchangeShortName": "NASDAQ",
                "marketCap": 2_000_000_000,
                "price": 100,
                "avgVolume": 200_000,
                "ipoDate": "2025-01-01",
            },
            today,
        )["symbol"]
        == "GOOD"
    )

    assert (
        candidate_from_screener(
            {"symbol": "tiny", "marketCap": 100_000_000, "price": 10, "avgVolume": 2_000_000},
            today,
        )
        is None
    )
    assert (
        candidate_from_screener(
            {
                "symbol": "new",
                "marketCap": 2_000_000_000,
                "price": 100,
                "avgVolume": 200_000,
                "ipoDate": "2026-04-01",
            },
            today,
        )
        is None
    )


def test_manual_m_pool_row_has_audit_ready_shape() -> None:
    row = manual_m_pool_row("brk.b", "manual")
    assert row["symbol"] == "BRK-B"
    assert row["pool"] == "m"
    assert row["is_active"] is True
    assert "target_market_cap" not in row


def test_a_pool_yaml_validates_themes_against_master(tmp_path) -> None:
    a_path = tmp_path / "a_pool.yaml"
    themes_path = tmp_path / "themes.yaml"
    a_path.write_text(
        """
- symbol: NVDA
  status: active
  added: 2025-09-02
  thesis_stop_mcap_b: 2000
  target_mcap_b: 6000
  thesis_summary: AI compute
  themes: [theme_missing]
""",
        encoding="utf-8",
    )
    themes_path.write_text(
        """
themes:
  - theme_id: theme_ai_compute
    name_cn: AI 算力
    name_en: AI Compute
""",
        encoding="utf-8",
    )
    with pytest.raises(a_pool.APoolValidationError, match="unknown theme_id 'theme_missing'"):
        a_pool.validate_entries(
            a_pool.load_entries(a_path),
            a_pool_path=a_path,
            themes_path=themes_path,
        )


def test_a_pool_set_mcap_writes_yaml_only_not_db(tmp_path) -> None:
    a_path = tmp_path / "a_pool.yaml"
    a_path.write_text(
        """
- symbol: NVDA
  status: active
  added: 2025-09-02
  thesis_stop_mcap_b: 2000
  target_mcap_b: 6000
  thesis_summary: AI compute
  themes: [theme_ai_compute]
""",
        encoding="utf-8",
    )
    entries = a_pool.set_mcap_yaml("NVDA", 1800, 6500, path=a_path)
    assert entries[0]["thesis_stop_mcap_b"] == 1800
    assert entries[0]["target_mcap_b"] == 6500
    assert "target_cap" not in a_path.read_text(encoding="utf-8")
