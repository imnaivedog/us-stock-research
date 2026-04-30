"""Shared report formatting helpers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

DIAL_LABELS = {
    "S": "S · Strong risk-on",
    "A": "A · Risk-on",
    "B": "B · Neutral",
    "C": "C · Defensive",
    "D": "D · Risk-off",
}

POSITION_MAP = {"S": 1.0, "A": 0.8, "B": 0.5, "C": 0.25, "D": 0.0}


def decimal_to_float(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def format_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def format_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    number = float(decimal_to_float(value))
    if number.is_integer():
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def format_price(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"${float(decimal_to_float(value)):,.2f}"


def dial_label(regime: str | None) -> str:
    if not regime:
        return "N/A"
    return DIAL_LABELS.get(regime, str(regime))


def position_for_regime(regime: str | None) -> float | None:
    if not regime:
        return None
    return POSITION_MAP.get(regime)


def truncate_verdict(text: str | None, limit: int = 220) -> str:
    if not text:
        return ""
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 1]}…"


def triggered_signal_codes(signals: dict[str, Any] | None) -> list[str]:
    if not signals:
        return []
    return [
        key
        for key, payload in signals.items()
        if isinstance(payload, dict) and payload.get("triggered") is True
    ]
