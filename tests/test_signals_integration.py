from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from scripts.run_signals import load_fixture_context, run_signal_engine  # noqa: E402
from src.signals import orchestrate  # noqa: E402
from src.signals._params import load_params  # noqa: E402

FIXTURE_DIR = Path("tests/fixtures")


def test_fixture_backfill_produces_expected_regime_and_alert_profile() -> None:
    spy, breadth, vix, events, sectors, stocks = load_fixture_context(FIXTURE_DIR)
    rows, alerts, sector_rows, theme_rows, stock_rows = run_signal_engine(
        spy,
        breadth,
        vix,
        events,
        date.fromisoformat("2025-04-29"),
        date.fromisoformat("2026-04-15"),
        load_params(),
        sectors=sectors,
        stocks=stocks,
    )
    signals = pd.DataFrame(rows)
    assert len(signals) == 252
    assert 0.05 <= (signals["regime"] == "S").mean() <= 0.25
    assert (signals["regime"] == "D").sum() > 0
    assert sum(
        alert.alert_type == "BREADTH_50MA_EXTREME" and alert.severity == "RED"
        for alert in alerts
    ) >= 3
    assert any(alert.alert_type == "NH_NL_EXTREME" for alert in alerts)
    assert not any(alert.alert_type == "ZWEIG_BREADTH_THRUST" for alert in alerts)
    assert len(sector_rows) == 252 * 11
    assert len(theme_rows) == 252 * 8
    assert len(stock_rows) == 252 * 30
    assert sum(item.quadrant == "LEADING" for item in sector_rows) >= 30
    assert sum(item.quadrant == "LAGGING" for item in sector_rows) >= 30
    assert sum(item.theme_id == "ai_compute" and item.rank <= 3 for item in theme_rows) >= 120
    assert sum(item.symbol == "NVDA" and item.is_top5 for item in stock_rows) >= 120


def test_no_forbidden_table_access() -> None:
    forbidden = [
        "nav_daily",
        "positions_current",
        "trades_log",
        "signals_a_pool_daily",
        "a_pool_calibration",
    ]
    for path in Path("src/signals").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for table in forbidden:
            assert table not in text, f"{path} must not reference {table}"


def test_orchestrate_fixture_writes_all_signal_outputs(monkeypatch) -> None:
    tables: dict[str, list] = {
        "signals_daily": [],
        "signals_alerts": [],
        "signals_sectors_daily": [],
        "signals_themes_daily": [],
        "signals_stocks_daily": [],
    }

    monkeypatch.setattr(orchestrate, "PostgresClient", lambda: object())
    monkeypatch.setattr(
        orchestrate,
        "upsert_signals_daily",
        lambda _pg, rows: tables["signals_daily"].extend(rows),
    )
    monkeypatch.setattr(
        orchestrate,
        "upsert_alerts",
        lambda _pg, rows: tables["signals_alerts"].extend(rows),
    )
    monkeypatch.setattr(
        orchestrate,
        "upsert_detail_rows",
        lambda _pg, table, rows: tables[table].extend(rows),
    )

    def fake_macro_update(_pg, result):
        for row in tables["signals_daily"]:
            if row["trade_date"] == result.trade_date:
                row["macro_state"] = result.macro_state

    monkeypatch.setattr(orchestrate, "upsert_macro_state", fake_macro_update)
    orchestrate.run_pipeline(
        date.fromisoformat("2025-04-29"),
        date.fromisoformat("2026-04-15"),
        FIXTURE_DIR,
    )
    assert all(tables[name] for name in tables)
    daily = [
        row for row in tables["signals_daily"] if row["trade_date"].isoformat() == "2026-04-15"
    ]
    assert len(daily) == 1
    assert daily[0]["macro_state"] in {"risk_on", "risk_off", "neutral"}
