from __future__ import annotations

import csv
import os
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger
from notion_client import Client
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "config" / "etf_universe.csv"


class NotionSettings(BaseSettings):
    notion_token: str
    notion_etf_audit_db_id: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def _plain_text(items: list[dict[str, Any]]) -> str:
    return "".join(item.get("plain_text", "") for item in items or []).strip()


def _property_text(properties: dict[str, Any], name: str) -> str:
    prop = properties.get(name, {})
    prop_type = prop.get("type")
    if prop_type == "title":
        return _plain_text(prop.get("title", []))
    if prop_type == "rich_text":
        return _plain_text(prop.get("rich_text", []))
    if prop_type == "select":
        selected = prop.get("select")
        return selected.get("name", "") if selected else ""
    if prop_type == "status":
        selected = prop.get("status")
        return selected.get("name", "") if selected else ""
    if prop_type == "number":
        value = prop.get("number")
        return "" if value is None else str(value)
    if prop_type == "formula":
        formula = prop.get("formula", {})
        return str(formula.get(formula.get("type"), "") or "")
    return ""


def _property_number(properties: dict[str, Any], name: str) -> str:
    prop = properties.get(name, {})
    if prop.get("type") == "number":
        value = prop.get("number")
        return "" if value is None else str(value)
    text = _property_text(properties, name)
    return text


def _property_checkbox(properties: dict[str, Any], name: str) -> bool:
    prop = properties.get(name, {})
    if prop.get("type") == "checkbox":
        return bool(prop.get("checkbox"))
    return False


def _property_multi_select(properties: dict[str, Any], name: str) -> str:
    prop = properties.get(name, {})
    if prop.get("type") != "multi_select":
        return ""
    return "|".join(item.get("name", "") for item in prop.get("multi_select", []) if item.get("name"))


def derive_algo_role(theme: str) -> str:
    if theme == "GICS板块":
        return "L3_sector"
    if "装载源" in theme:
        return "universe_loader"
    if theme == "大盘基准":
        return "benchmark"
    if theme == "宏观对冲":
        return "macro_hedge"
    if theme in {"中国股", "中概", "日本", "印度", "新兴市场"}:
        return "region"
    if theme in {"成长style", "价值style", "高股息", "股息贵族", "股息增长"}:
        return "style"
    return "L3_theme"


def _query_all_pages(client: Client, database_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        response = client.databases.query(database_id=database_id, start_cursor=cursor)
        rows.extend(response.get("results", []))
        if not response.get("has_more"):
            return rows
        cursor = response.get("next_cursor")


def main() -> None:
    settings = NotionSettings()
    client = Client(auth=settings.notion_token)
    pages = _query_all_pages(client, settings.notion_etf_audit_db_id)

    today = date.today().isoformat()
    output_rows: list[dict[str, Any]] = []
    for page in pages:
        properties = page.get("properties", {})
        theme = _property_text(properties, "Theme")
        current_primary = _property_checkbox(properties, "Current_Primary")
        output_rows.append(
            {
                "code": _property_text(properties, "Code").upper(),
                "name": _property_text(properties, "Name"),
                "market": _property_text(properties, "Market"),
                "theme": theme,
                "gics_sector": _property_multi_select(properties, "GICS_Sector"),
                "is_candidate": str(current_primary).lower(),
                "algo_role": derive_algo_role(theme),
                "source_discovered": "manual_seed",
                "aum_billion": _property_number(properties, "AUM_Billion"),
                "expense_ratio_pct": _property_number(properties, "Expense_Ratio_Pct"),
                "added_date": today,
                "note": "",
            }
        )

    output_rows.sort(key=lambda row: row["code"])
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "code",
                "name",
                "market",
                "theme",
                "gics_sector",
                "is_candidate",
                "algo_role",
                "source_discovered",
                "aum_billion",
                "expense_ratio_pct",
                "added_date",
                "note",
            ],
        )
        writer.writeheader()
        writer.writerows(output_rows)

    missing_roles = sum(1 for row in output_rows if not row["algo_role"])
    logger.info(
        "exported ETF audit CSV",
        path=str(OUTPUT_PATH),
        rows=len(output_rows),
        missing_roles=missing_roles,
    )


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    main()
