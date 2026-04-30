"""A-pool YAML management and DB mirroring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_data.etl.common import CONFIG_DIR, normalize_symbol
from usstock_data.universe.core import audit_change, engine_or_default, upsert_universe_symbols

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_A_POOL_PATH = CONFIG_DIR / "a_pool.yaml"
DEFAULT_THEMES_PATH = CONFIG_DIR / "themes.yaml"


@dataclass(frozen=True)
class APoolEntry:
    symbol: str
    status: str
    added: date
    thesis_stop_mcap_b: float
    target_mcap_b: float
    thesis_summary: str
    themes: list[str]

    def to_yaml(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "added": self.added.isoformat(),
            "thesis_stop_mcap_b": self.thesis_stop_mcap_b,
            "target_mcap_b": self.target_mcap_b,
            "thesis_summary": self.thesis_summary,
            "themes": self.themes,
        }


class APoolValidationError(ValueError):
    pass


def load_entries(path: Path = DEFAULT_A_POOL_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise APoolValidationError(f"{path}: root must be a list")
    return [dict(item) for item in payload]


def save_entries(entries: list[dict[str, Any]], path: Path = DEFAULT_A_POOL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(entries, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def registered_theme_ids(path: Path = DEFAULT_THEMES_PATH) -> set[str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    ids: set[str] = set()
    for item in payload.get("themes", []):
        theme_id = item.get("theme_id") or item.get("id")
        if theme_id:
            ids.add(str(theme_id))
    return ids


def yaml_line_for_symbol(path: Path, symbol: str) -> int:
    if not path.exists():
        return 1
    needle = f"symbol: {symbol}"
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            return idx
    return 1


def validate_entries(
    entries: list[dict[str, Any]],
    *,
    a_pool_path: Path = DEFAULT_A_POOL_PATH,
    themes_path: Path = DEFAULT_THEMES_PATH,
    master_theme_ids: set[str] | None = None,
) -> None:
    allowed = (
        master_theme_ids
        if master_theme_ids is not None
        else registered_theme_ids(themes_path)
    )
    for item in entries:
        symbol = normalize_symbol(item.get("symbol"))
        for theme_id in item.get("themes") or []:
            if theme_id not in allowed:
                line = yaml_line_for_symbol(a_pool_path, symbol)
                raise APoolValidationError(
                    f"{a_pool_path}:{line}: unknown theme_id '{theme_id}' for {symbol}"
                )


def add_yaml_entry(
    symbol: str,
    *,
    thesis_stop_mcap_b: float,
    target_mcap_b: float,
    themes: list[str],
    summary: str,
    status: str = "active",
    path: Path = DEFAULT_A_POOL_PATH,
    today: date | None = None,
) -> list[dict[str, Any]]:
    today = today or datetime.now(LOCAL_TZ).date()
    symbol = normalize_symbol(symbol)
    entries = [
        item for item in load_entries(path) if normalize_symbol(item.get("symbol")) != symbol
    ]
    entries.append(
        APoolEntry(
            symbol=symbol,
            status=status,
            added=today,
            thesis_stop_mcap_b=thesis_stop_mcap_b,
            target_mcap_b=target_mcap_b,
            thesis_summary=summary,
            themes=themes,
        ).to_yaml()
    )
    validate_entries(entries, a_pool_path=path)
    save_entries(sorted(entries, key=lambda item: item["symbol"]), path)
    return entries


def set_mcap_yaml(
    symbol: str,
    thesis_stop_mcap_b: float,
    target_mcap_b: float,
    *,
    path: Path = DEFAULT_A_POOL_PATH,
) -> list[dict[str, Any]]:
    symbol = normalize_symbol(symbol)
    entries = load_entries(path)
    for item in entries:
        if normalize_symbol(item.get("symbol")) == symbol:
            item["thesis_stop_mcap_b"] = thesis_stop_mcap_b
            item["target_mcap_b"] = target_mcap_b
            save_entries(entries, path)
            return entries
    raise KeyError(symbol)


def set_themes_yaml(
    symbol: str,
    themes: list[str],
    *,
    path: Path = DEFAULT_A_POOL_PATH,
) -> list[dict[str, Any]]:
    symbol = normalize_symbol(symbol)
    entries = load_entries(path)
    for item in entries:
        if normalize_symbol(item.get("symbol")) == symbol:
            item["themes"] = themes
            validate_entries(entries, a_pool_path=path)
            save_entries(entries, path)
            return entries
    raise KeyError(symbol)


def remove_yaml_entry(symbol: str, *, path: Path = DEFAULT_A_POOL_PATH) -> list[dict[str, Any]]:
    symbol = normalize_symbol(symbol)
    entries = [
        item for item in load_entries(path) if normalize_symbol(item.get("symbol")) != symbol
    ]
    save_entries(entries, path)
    return entries


def mirror_to_db(
    engine: Engine | None = None,
    path: Path = DEFAULT_A_POOL_PATH,
    master_theme_ids: set[str] | None = None,
) -> dict[str, int]:
    engine = engine_or_default(engine)
    entries = load_entries(path)
    validate_entries(entries, a_pool_path=path, master_theme_ids=master_theme_ids)
    active_rows = []
    for item in entries:
        symbol = normalize_symbol(item.get("symbol"))
        is_active = item.get("status", "active") == "active"
        active_rows.append(
            {
                "symbol": symbol,
                "pool": "a",
                "source": "a_pool_yaml",
                "is_candidate": True,
                "is_active": is_active,
                "market_cap": None,
                "adv_20d": None,
                "ipo_date": None,
                "added_date": item.get("added"),
                "as_of_date": None,
                "filter_reason": "a_pool_yaml",
                "thesis_url": None,
                "thesis_added_at": item.get("added"),
            }
        )
    upserted = upsert_universe_symbols(engine, active_rows)
    for row in active_rows:
        audit_change(engine, row["symbol"], "forced_in", pool="a", reason="a_pool_yaml_sync")
    return {"synced": upserted}


def remove(symbol: str, *, engine: Engine | None = None, reason: str | None = None) -> None:
    engine = engine_or_default(engine)
    symbol = normalize_symbol(symbol)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE symbol_universe
                SET is_active = false,
                    removed_date = CURRENT_DATE,
                    last_seen = CURRENT_DATE,
                    updated_at = now()
                WHERE symbol = :symbol AND pool = 'a'
                """
            ),
            {"symbol": symbol},
        )
    audit_change(engine, symbol, "removed", pool="a", reason=reason or "a_pool_yaml_remove")


def sync(
    engine: Engine | None = None,
    path: Path = DEFAULT_A_POOL_PATH,
    master_theme_ids: set[str] | None = None,
) -> dict[str, int]:
    return mirror_to_db(engine=engine, path=path, master_theme_ids=master_theme_ids)
