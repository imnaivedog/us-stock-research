from __future__ import annotations

import re
from pathlib import Path

DDL = Path(__file__).parents[1] / "src" / "usstock_data" / "schema" / "ddl.sql"

EXPECTED_TABLES = {
    "quotes_daily",
    "macro_daily",
    "sp500_members_daily",
    "etf_holdings_latest",
    "symbol_universe",
    "symbol_universe_changes",
    "watchlist",
    "daily_indicators",
    "signals_daily",
    "signals_alerts",
    "signals_sectors_daily",
    "signals_themes_daily",
    "signals_stocks_daily",
    "alert_log",
    "events_calendar",
    "corporate_actions",
    "fundamentals_quarterly",
}


def test_schema_declares_expected_17_tables() -> None:
    ddl = DDL.read_text(encoding="utf-8").lower()
    declared = set(re.findall(r"create table if not exists\s+([a-z0-9_]+)", ddl))
    assert EXPECTED_TABLES <= declared


def test_schema_is_additive_only() -> None:
    ddl = DDL.read_text(encoding="utf-8").lower()
    assert "drop table" not in ddl
    assert "drop column" not in ddl
    assert "truncate " not in ddl
    assert "delete from" not in ddl


def test_schema_has_v5_alignment_columns_and_tables() -> None:
    ddl = DDL.read_text(encoding="utf-8").lower()
    for snippet in [
        "alter table symbol_universe add column if not exists pool",
        "alter table quotes_daily add column if not exists asset_class",
        "create table if not exists alert_log",
        "create table if not exists events_calendar",
        "create table if not exists corporate_actions",
        "create table if not exists fundamentals_quarterly",
        "hyg_lqd_spread",
        "gold_silver_ratio",
        "dgs10",
        "dgs2",
    ]:
        assert snippet in ddl
