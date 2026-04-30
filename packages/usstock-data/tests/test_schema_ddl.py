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
    "themes_master",
    "themes_members",
    "themes_score_daily",
    "a_pool_calibration",
    "signals_a_pool_daily",
}


def test_schema_declares_expected_22_tables() -> None:
    ddl = DDL.read_text(encoding="utf-8").lower()
    declared = set(re.findall(r"create table if not exists\s+([a-z0-9_]+)", ddl))
    assert EXPECTED_TABLES <= declared


def test_schema_is_additive_only() -> None:
    ddl = DDL.read_text(encoding="utf-8").lower()
    assert "drop table" not in ddl
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
        "create table if not exists themes_master",
        "create table if not exists themes_members",
        "create table if not exists themes_score_daily",
        "create table if not exists a_pool_calibration",
        "create table if not exists signals_a_pool_daily",
        "alter table symbol_universe add column if not exists shares_outstanding",
        "alter table symbol_universe add column if not exists thesis_added_at",
        "hyg_lqd_spread",
        "gold_silver_ratio",
        "dgs10",
        "dgs2",
    ]:
        assert snippet in ddl


def test_schema_drops_target_cap_idempotently() -> None:
    ddl = DDL.read_text(encoding="utf-8").lower()
    assert "drop column if exists target_cap" in ddl
    assert "drop column if exists target_market_cap" in ddl


def test_schema_uses_three_phase_order() -> None:
    ddl = DDL.read_text(encoding="utf-8").lower()
    phase1 = ddl.index("phase 1: create table if not exists")
    phase2 = ddl.index("phase 2: alter table add/drop column if exists")
    phase3 = ddl.index("phase 3: create index if not exists")
    first_create_table = ddl.index("create table if not exists quotes_daily")
    first_alter = ddl.index("alter table")
    first_index = ddl.index("create index if not exists")

    assert phase1 < first_create_table < phase2 < first_alter < phase3 < first_index
    assert ddl.rindex("alter table") < first_index


def test_schema_indexes_after_backfill_columns() -> None:
    ddl = DDL.read_text(encoding="utf-8").lower()
    for alter_snippet, index_snippet in [
        (
            "alter table quotes_daily add column if not exists asset_class",
            "create index if not exists idx_quotes_asset_class",
        ),
        (
            "alter table symbol_universe add column if not exists pool",
            "create index if not exists idx_symbol_universe_pool",
        ),
        (
            "alter table alert_log add column if not exists category",
            "create index if not exists idx_alert_log_date",
        ),
    ]:
        assert ddl.index(alter_snippet) < ddl.index(index_snippet)
