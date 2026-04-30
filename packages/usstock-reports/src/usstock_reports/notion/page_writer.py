"""Render and write the full Notion daily page body."""

from __future__ import annotations

import json
from typing import Any

from usstock_reports.formatters.core import (
    dial_label,
    format_date,
    format_number,
    format_price,
    triggered_signal_codes,
    truncate_verdict,
)
from usstock_reports.notion.client import RetryingNotionClient


def _json_loads(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def line_join(lines: list[str]) -> str:
    return "\n".join(line for line in lines if line is not None)


def render_dial(report: dict[str, Any]) -> str:
    daily = report.get("daily") or {}
    return line_join(
        [
            "## Dial",
            f"- 档位: {dial_label(daily.get('regime'))}",
            f"- 连续天数: {daily.get('regime_streak', 'N/A')}",
            f"- 是否切换: {daily.get('regime_changed', False)}",
        ]
    )


def render_breadth(report: dict[str, Any]) -> str:
    daily = report.get("daily") or {}
    alerts = report.get("alerts") or []
    lines = [
        "## Breadth",
        f"- Breadth Score: {format_number(daily.get('breadth_score'))}",
        f"- >200MA: {format_number(daily.get('breadth_pct_above_200ma'))}%",
        f"- >50MA: {format_number(daily.get('breadth_pct_above_50ma'))}%",
        f"- >20MA: {format_number(daily.get('breadth_pct_above_20ma'))}%",
        f"- NH/NL: {format_number(daily.get('breadth_nh_nl_ratio'))}",
        f"- McClellan: {format_number(daily.get('breadth_mcclellan'))}",
    ]
    if alerts:
        lines.append("- Alerts: " + ", ".join(str(item.get("alert_type")) for item in alerts))
    return line_join(lines)


def render_sector(report: dict[str, Any]) -> str:
    lines = ["## Sector"]
    for row in report.get("sectors") or []:
        lines.append(
            "- "
            f"{row.get('symbol')} · rank {row.get('rank_relative')} · "
            f"score {format_number(row.get('total_score'))} · {row.get('quadrant')}"
        )
    return line_join(lines)


def render_theme(report: dict[str, Any]) -> str:
    lines = ["## Theme"]
    for row in report.get("themes") or []:
        lines.append(
            "- "
            f"{row.get('theme_name') or row.get('theme_id')} · rank {row.get('rank')} · "
            f"score {format_number(row.get('total_score'))} · {row.get('state')}"
        )
    return line_join(lines)


def render_stock(report: dict[str, Any]) -> str:
    lines = ["## Stock"]
    for row in report.get("stocks") or []:
        lines.append(
            "- "
            f"{row.get('symbol')} · rank {row.get('rank')} · "
            f"score {format_number(row.get('total_score'))} · "
            f"{row.get('entry_pattern') or 'N/A'}"
        )
    return line_join(lines)


def _pool_metric(row: dict[str, Any], key: str) -> Any:
    breakdown = _json_loads(row.get("score_breakdown")) or {}
    return row.get(key) if row.get(key) is not None else breakdown.get(key)


def render_a_pool_highlights(report: dict[str, Any]) -> str:
    candidates = [
        row for row in report.get("a_pool") or [] if float(row.get("a_score") or 0) >= 70
    ]
    if not candidates:
        return ""
    lines = ["## A 池 Highlights"]
    for row in sorted(candidates, key=lambda item: float(item.get("a_score") or 0), reverse=True):
        signals = _json_loads(row.get("signals")) or {}
        codes = triggered_signal_codes(signals)
        theme_quintile = row.get("theme_quintile") or signals.get("theme_quintile")
        if not theme_quintile:
            theme_payload = signals.get("theme_oversold_entry")
            if isinstance(theme_payload, dict):
                theme_quintile = theme_payload.get("theme_quintile")
        lines.extend(
            [
                f"### 🎯 {row.get('symbol')} · A_Score {format_number(row.get('a_score'))}",
                f"> {truncate_verdict(row.get('verdict_text'))}",
                (
                    "- "
                    f"入场 (中) {format_price(_pool_metric(row, 'entry_moderate'))} · "
                    f"入场 (深) {format_price(_pool_metric(row, 'entry_conservative'))}"
                ),
                (
                    "- "
                    f"止损 (浅) {format_price(_pool_metric(row, 'stop_shallow'))} · "
                    f"止损 (深) {format_price(_pool_metric(row, 'stop_deep'))}"
                ),
                (
                    "- "
                    f"短目标 {format_price(_pool_metric(row, 'short_target'))} · "
                    f"战略 R:R {format_number(_pool_metric(row, 'strategic_rr'))}"
                ),
                (
                    "- 触发链 "
                    f"{', '.join(codes) if codes else 'none'}"
                    f"{f' · theme_quintile={theme_quintile}' if theme_quintile else ''}"
                ),
            ]
        )
    return line_join(lines)


def render_macro(report: dict[str, Any]) -> str:
    daily = report.get("daily") or {}
    return line_join(
        [
            "## Macro",
            f"- Macro State: {daily.get('macro_state') or 'N/A'}",
            f"- As Of: {format_date(daily.get('as_of_date') or report.get('date'))}",
        ]
    )


def safe_section(name: str, renderer: Any, report: dict[str, Any]) -> str:
    try:
        return renderer(report)
    except Exception as exc:  # noqa: BLE001 - report rendering should degrade by section
        return f"## {name}\n- section failed: {type(exc).__name__}: {exc}"


def render_daily_markdown(report: dict[str, Any]) -> str:
    sections = [
        safe_section("Dial", render_dial, report),
        safe_section("Breadth", render_breadth, report),
        safe_section("Sector", render_sector, report),
        safe_section("Theme", render_theme, report),
        safe_section("Stock", render_stock, report),
    ]
    a_pool = safe_section("A 池 Highlights", render_a_pool_highlights, report)
    if a_pool:
        sections.append(a_pool)
    sections.append(safe_section("Macro", render_macro, report))
    return "\n\n".join(sections)


def markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks = []
    for line in markdown.splitlines():
        if line.startswith("### "):
            blocks.append(
                {"object": "block", "type": "heading_3", "heading_3": _rich(line[4:])}
            )
        elif line.startswith("## "):
            blocks.append(
                {"object": "block", "type": "heading_2", "heading_2": _rich(line[3:])}
            )
        elif line.startswith("> "):
            blocks.append({"object": "block", "type": "quote", "quote": _rich(line[2:])})
        elif line.startswith("- "):
            blocks.append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": _rich(line[2:]),
                }
            )
        elif line.strip():
            blocks.append({"object": "block", "type": "paragraph", "paragraph": _rich(line)})
    return blocks


def _rich(content: str) -> dict[str, list[dict[str, dict[str, str]]]]:
    return {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]}


def write_page_body(
    client: RetryingNotionClient,
    page_id: str,
    report: dict[str, Any],
) -> str:
    markdown = render_daily_markdown(report)
    blocks = markdown_to_blocks(markdown)
    if blocks:
        client.append_blocks(block_id=page_id, children=blocks)
    return markdown
