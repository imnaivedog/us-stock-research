"""Validate theme dictionary and A-pool references."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from usstock_data.etl.common import CONFIG_DIR, normalize_symbol

THEMES_PATH = CONFIG_DIR / "themes.yaml"
A_POOL_PATH = CONFIG_DIR / "a_pool.yaml"


class ThemeValidationError(ValueError):
    pass


def load_theme_payload(path: Path = THEMES_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {"themes": []}


def theme_ids(path: Path = THEMES_PATH) -> set[str]:
    payload = load_theme_payload(path)
    return {str(item.get("theme_id") or item.get("id")) for item in payload.get("themes", [])}


def member_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for theme in payload.get("themes", []):
        theme_id = str(theme["theme_id"])
        source_etfs = theme.get("source_etfs") or []
        for member in theme.get("members", []):
            rows.append(
                {
                    "theme_id": theme_id,
                    "symbol": normalize_symbol(member["symbol"]),
                    "weight": member.get("weight"),
                    "source_etfs": member.get("source_etfs") or source_etfs,
                }
            )
    return rows


def validate_theme_payload(payload: dict[str, Any]) -> None:
    seen: set[str] = set()
    for theme in payload.get("themes", []):
        theme_id = str(theme.get("theme_id") or "")
        if not theme_id:
            raise ThemeValidationError("theme_id is required")
        if theme_id in seen:
            raise ThemeValidationError(f"duplicate theme_id: {theme_id}")
        seen.add(theme_id)
        if not theme.get("name_cn") or not theme.get("name_en"):
            raise ThemeValidationError(f"{theme_id}: name_cn/name_en are required")


def validate_a_pool_references(
    a_pool_path: Path = A_POOL_PATH,
    themes_path: Path = THEMES_PATH,
) -> None:
    allowed = theme_ids(themes_path)
    a_pool = yaml.safe_load(a_pool_path.read_text(encoding="utf-8")) or []
    for item in a_pool:
        symbol = normalize_symbol(item.get("symbol"))
        for theme_id in item.get("themes") or []:
            if theme_id not in allowed:
                raise ThemeValidationError(f"{symbol}: unknown theme_id {theme_id}")


def validate(themes_path: Path = THEMES_PATH, a_pool_path: Path = A_POOL_PATH) -> None:
    payload = load_theme_payload(themes_path)
    validate_theme_payload(payload)
    validate_a_pool_references(a_pool_path, themes_path)
