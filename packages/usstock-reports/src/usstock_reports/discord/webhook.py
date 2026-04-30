"""Discord webhook delivery for the mobile daily digest."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from datetime import date
from typing import Any

import requests
from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_reports.formatters.core import (
    decimal_to_float,
    format_date,
    format_percent,
    position_for_regime,
    truncate_verdict,
)

DISCORD_LIMIT = 2000
SAFE_CHUNK_LIMIT = 1900


def _json_loads(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _score(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(decimal_to_float(value)):.0f}"


def _vix(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(decimal_to_float(value)):.1f}"


def _alert_text(alert: dict[str, Any]) -> str:
    detail = _json_loads(alert.get("detail")) if alert.get("detail") is not None else None
    message = alert.get("message") or alert.get("alert_type") or "alert"
    if isinstance(detail, dict) and detail.get("message"):
        message = detail["message"]
    return f"{alert.get('severity')} · {message}"


def build_webhook_message(report: dict[str, Any]) -> str:
    daily = report.get("daily") or {}
    trade_date = report.get("date") or daily.get("trade_date")
    regime = daily.get("regime") or "N/A"
    position = position_for_regime(regime)
    lines = [
        (
            f"📊 {format_date(trade_date)} · Dial {regime} · "
            f"仓位 {format_percent(position)} · VIX {_vix(daily.get('vix'))}"
        )
    ]

    lines.append("")
    lines.append("ETF Top 3")
    for idx, row in enumerate((report.get("sectors") or [])[:3], start=1):
        rank = row.get("rank_relative") or idx
        ticker = row.get("symbol") or row.get("ticker") or "N/A"
        lines.append(f"{rank}. {ticker} · 综合分 {_score(row.get('total_score'))}")

    lines.append("")
    lines.append("个股 Top 5")
    for idx, row in enumerate((report.get("stocks") or [])[:5], start=1):
        rank = row.get("rank") or idx
        sector = row.get("primary_sector") or "N/A"
        top_signal = row.get("top_signal") or row.get("entry_pattern") or "N/A"
        lines.append(f"{rank}. {row.get('symbol')} · {sector} · 触发 {top_signal}")

    highlights = [
        row for row in report.get("a_pool") or [] if float(row.get("a_score") or 0) >= 70
    ]
    if highlights:
        lines.append("")
        lines.append("A 池 highlights")
        sorted_highlights = sorted(
            highlights,
            key=lambda item: float(item.get("a_score") or 0),
            reverse=True,
        )
        for row in sorted_highlights:
            verdict = truncate_verdict(row.get("verdict_text"), limit=83)
            lines.append(f"🎯 {row.get('symbol')} A{_score(row.get('a_score'))} · {verdict}")

    alerts = [
        row for row in report.get("alerts") or [] if row.get("severity") in {"ERROR", "WARN"}
    ][:5]
    if alerts:
        lines.append("")
        lines.append("关键告警")
        for alert in alerts:
            lines.append(f"- {_alert_text(alert)}")

    return "\n".join(lines)


def split_message(message: str, limit: int = DISCORD_LIMIT) -> list[str]:
    if len(message) <= limit:
        return [message]

    chunks: list[str] = []
    current = ""
    for line in message.splitlines():
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= SAFE_CHUNK_LIMIT:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(line) > SAFE_CHUNK_LIMIT:
            chunks.append(line[:SAFE_CHUNK_LIMIT])
            line = line[SAFE_CHUNK_LIMIT:]
        current = line
    if current:
        chunks.append(current)

    if len(chunks) <= 1:
        return chunks
    continuation_count = len(chunks) - 1
    return [
        chunks[0],
        *[
            f"续 {idx}/{continuation_count}\n{chunk}"
            for idx, chunk in enumerate(chunks[1:], start=1)
        ],
    ]


def write_alert_log(
    engine: Engine | None,
    *,
    trade_date: date | str | None,
    severity: str,
    message: str,
) -> None:
    if engine is None:
        logger.warning("Discord alert_log skipped without engine: {}", message)
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO alert_log (job_name, trade_date, severity, category, message)
                VALUES ('reports.discord', :trade_date, :severity, 'discord', :message)
                """
            ),
            {"trade_date": trade_date, "severity": severity, "message": message},
        )


def _post_with_retry(
    url: str,
    content: str,
    *,
    post: Callable[..., Any],
    sleep: Callable[[float], None],
) -> bool:
    delays = [1, 2, 4]
    for attempt, delay in enumerate(delays, start=1):
        response = post(url, json={"content": content}, timeout=10)
        if 200 <= int(response.status_code) < 300:
            return True
        if attempt < len(delays):
            sleep(delay)
    return False


def send_discord_report(
    report: dict[str, Any],
    *,
    engine: Engine | None = None,
    webhook_url: str | None = None,
    post: Callable[..., Any] = requests.post,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    trade_date = report.get("date") or (report.get("daily") or {}).get("trade_date")
    webhook_url = webhook_url if webhook_url is not None else os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        write_alert_log(
            engine,
            trade_date=trade_date,
            severity="INFO",
            message="DISCORD_WEBHOOK_URL missing; Discord push skipped",
        )
        return 0

    for part in split_message(build_webhook_message(report)):
        if not _post_with_retry(webhook_url, part, post=post, sleep=sleep):
            write_alert_log(
                engine,
                trade_date=trade_date,
                severity="ERROR",
                message="Discord webhook failed after 3 attempts",
            )
            return 1
    return 0
