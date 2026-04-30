"""Daily report loading and delivery orchestration."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_reports.db import create_postgres_engine
from usstock_reports.notion.client import RetryingNotionClient
from usstock_reports.notion.page_writer import write_page_body
from usstock_reports.notion.row_writer import upsert_daily_row, write_alert_log


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return frame.to_dict(orient="records")


def load_daily_report(engine: Engine, trade_date: date) -> dict[str, Any]:
    """Load report inputs from the six signal tables only."""
    with engine.begin() as conn:
        daily = pd.read_sql_query(
            text("SELECT * FROM signals_daily WHERE trade_date = :trade_date"),
            conn,
            params={"trade_date": trade_date},
        )
        alerts = pd.read_sql_query(
            text(
                """
                SELECT *
                FROM signals_alerts
                WHERE trade_date = :trade_date
                ORDER BY severity DESC, alert_type
                """
            ),
            conn,
            params={"trade_date": trade_date},
        )
        sectors = pd.read_sql_query(
            text(
                """
                SELECT *
                FROM signals_sectors_daily
                WHERE trade_date = :trade_date
                ORDER BY rank_relative NULLS LAST, total_score DESC
                LIMIT 5
                """
            ),
            conn,
            params={"trade_date": trade_date},
        )
        themes = pd.read_sql_query(
            text(
                """
                SELECT *
                FROM signals_themes_daily
                WHERE trade_date = :trade_date
                ORDER BY rank NULLS LAST, total_score DESC
                LIMIT 5
                """
            ),
            conn,
            params={"trade_date": trade_date},
        )
        stocks = pd.read_sql_query(
            text(
                """
                SELECT *
                FROM signals_stocks_daily
                WHERE trade_date = :trade_date
                ORDER BY is_top5 DESC, rank NULLS LAST, total_score DESC
                LIMIT 10
                """
            ),
            conn,
            params={"trade_date": trade_date},
        )
        a_pool = pd.read_sql_query(
            text(
                """
                SELECT *
                FROM signals_a_pool_daily
                WHERE date = :trade_date
                ORDER BY a_score DESC NULLS LAST, symbol
                """
            ),
            conn,
            params={"trade_date": trade_date},
        )

    daily_row = {} if daily.empty else daily.iloc[0].to_dict()
    return {
        "date": trade_date,
        "daily": daily_row,
        "alerts": _records(alerts),
        "sectors": _records(sectors),
        "themes": _records(themes),
        "stocks": _records(stocks),
        "a_pool": _records(a_pool),
    }


def write_notion_report(
    report: dict[str, Any],
    *,
    engine: Engine,
    client: RetryingNotionClient | None = None,
) -> str | None:
    client = client or RetryingNotionClient.from_env()
    trade_date = report["date"]
    page_id = None
    try:
        page_id = upsert_daily_row(client, report)
    except Exception as exc:  # noqa: BLE001 - Notion failures should be observable
        logger.exception("Failed to write Notion daily row for {}", trade_date)
        write_alert_log(engine, trade_date=trade_date, message=f"row_writer: {exc}")

    if not page_id:
        return None

    try:
        write_page_body(client, page_id, report)
    except Exception as exc:  # noqa: BLE001 - body failure should not hide row write
        logger.exception("Failed to write Notion page body for {}", trade_date)
        write_alert_log(engine, trade_date=trade_date, message=f"page_writer: {exc}")
    return page_id


def run_daily(
    *,
    trade_date: date,
    no_notion: bool = False,
    no_discord: bool = False,
    engine: Engine | None = None,
    notion_client: RetryingNotionClient | None = None,
) -> dict[str, Any]:
    engine = engine or create_postgres_engine()
    report = load_daily_report(engine, trade_date)
    result = {"date": trade_date.isoformat(), "notion_page_id": None, "discord": "skipped"}
    if not no_notion:
        result["notion_page_id"] = write_notion_report(
            report,
            engine=engine,
            client=notion_client,
        )
    if no_discord:
        result["discord"] = "skipped"
    return result
