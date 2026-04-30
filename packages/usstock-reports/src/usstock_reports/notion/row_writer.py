"""Write daily report row properties to Notion."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_reports.formatters.core import (
    dial_label,
    format_date,
    position_for_regime,
)
from usstock_reports.notion.client import RetryingNotionClient, daily_database_id


def rich_text(value: str) -> dict[str, list[dict[str, dict[str, str]]]]:
    return {"rich_text": [{"text": {"content": value[:2000]}}]} if value else {"rich_text": []}


def title(value: str) -> dict[str, list[dict[str, dict[str, str]]]]:
    return {"title": [{"text": {"content": value}}]}


def select(value: str | None) -> dict[str, dict[str, str] | None]:
    return {"select": {"name": value}} if value else {"select": None}


def number(value: Any) -> dict[str, float | int | None]:
    return {"number": None if value is None else float(value)}


def date_prop(value: date | str) -> dict[str, dict[str, str]]:
    return {"date": {"start": format_date(value)}}


def _names(items: list[dict[str, Any]], name_key: str = "symbol") -> str:
    return ", ".join(
        str(item.get(name_key) or item.get("theme_name") or "") for item in items if item
    )


def build_properties(report: dict[str, Any]) -> dict[str, Any]:
    daily = report.get("daily") or {}
    trade_date = daily.get("trade_date") or report["date"]
    regime = daily.get("regime")
    alerts = report.get("alerts") or []
    a_highlights = [
        row for row in report.get("a_pool") or [] if float(row.get("a_score") or 0) >= 70
    ]
    properties = {
        "Name": title(f"US Stock Research · {format_date(trade_date)}"),
        "Date": date_prop(trade_date),
        "Dial": select(dial_label(regime)),
        "Regime": select(regime),
        "Position": number(position_for_regime(regime)),
        "Breadth Score": number(daily.get("breadth_score")),
        "Macro State": select(daily.get("macro_state")),
        "Alerts": number(len(alerts)),
        "Top Sectors": rich_text(_names(report.get("sectors") or [])),
        "Top Themes": rich_text(_names(report.get("themes") or [], "theme_name")),
        "Top Stocks": rich_text(_names(report.get("stocks") or [])),
        "A Pool Highlights": number(len(a_highlights)),
    }
    return properties


def find_existing_page(
    client: RetryingNotionClient,
    database_id: str,
    trade_date: date | str,
) -> str | None:
    response = client.query_database(
        database_id=database_id,
        filter={"property": "Date", "date": {"equals": format_date(trade_date)}},
        page_size=1,
    )
    results = response.get("results", []) if isinstance(response, dict) else []
    if not results:
        return None
    return str(results[0]["id"])


def upsert_daily_row(
    client: RetryingNotionClient,
    report: dict[str, Any],
    database_id: str | None = None,
) -> str:
    database_id = database_id or daily_database_id()
    trade_date = report.get("date") or (report.get("daily") or {}).get("trade_date")
    properties = build_properties(report)
    page_id = find_existing_page(client, database_id, trade_date)
    if page_id:
        client.update_page(page_id=page_id, properties=properties)
        return page_id
    response = client.create_page(parent={"database_id": database_id}, properties=properties)
    return str(response["id"])


def write_alert_log(
    engine: Engine,
    *,
    trade_date: date,
    message: str,
    severity: str = "WARN",
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO alert_log (job_name, trade_date, severity, category, message)
                VALUES ('reports_notion', :trade_date, :severity, 'notion', :message)
                """
            ),
            {"trade_date": trade_date, "severity": severity, "message": message},
        )
