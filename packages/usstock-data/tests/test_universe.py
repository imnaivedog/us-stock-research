from __future__ import annotations

import asyncio
from datetime import date

import pytest
from usstock_data.universe import a_pool
from usstock_data.universe import sync as universe_sync
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


def test_sync_fails_fast_on_unknown_theme_with_yaml_line_number(tmp_path) -> None:
    a_path = tmp_path / "a_pool.yaml"
    a_path.write_text(
        """
- symbol: NVDA
  status: active
  added: 2025-09-02
  thesis_stop_mcap_b: 2000
  target_mcap_b: 6000
  thesis_summary: AI compute
  themes: [theme_made_up]
""",
        encoding="utf-8",
    )

    with pytest.raises(universe_sync.UnknownThemeError) as exc:
        universe_sync.validate_a_pool_themes(a_path, {"theme_ai_compute"})
    message = str(exc.value)
    assert "a_pool.yaml line 2" in message
    assert "symbol NVDA" in message
    assert "theme_made_up" in message


def test_sync_passes_when_all_themes_registered(tmp_path, monkeypatch) -> None:
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

    async def fake_m_sync(**kwargs):
        return {"synced": 1}

    monkeypatch.setattr(
        universe_sync,
        "load_themes_master",
        lambda *args, **kwargs: {"theme_ai_compute"},
    )
    monkeypatch.setattr(universe_sync.m_pool, "sync", fake_m_sync)

    result = asyncio.run(universe_sync.sync_all(engine=object(), dry_run=True, a_pool_path=a_path))
    assert result == {"m": {"synced": 1}, "a": {"synced": 0}}


def test_sync_raises_when_themes_master_empty(tmp_path) -> None:
    with pytest.raises(universe_sync.ThemesMasterEmptyError):
        universe_sync.load_themes_master(object(), fallback_yaml=tmp_path / "missing.yaml")


def test_a_pool_sync_is_awaited_when_async(tmp_path, monkeypatch) -> None:
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

    async def fake_m_sync(**kwargs):
        return {"synced": 2}

    async def fake_a_sync(**kwargs):
        return {"synced": 3}

    monkeypatch.setattr(
        universe_sync,
        "load_themes_master",
        lambda *args, **kwargs: {"theme_ai_compute"},
    )
    monkeypatch.setattr(universe_sync.m_pool, "sync", fake_m_sync)
    monkeypatch.setattr(universe_sync.a_pool, "sync", fake_a_sync)

    result = asyncio.run(universe_sync.sync_all(engine=object(), a_pool_path=a_path))
    assert result == {"m": {"synced": 2}, "a": {"synced": 3}}
