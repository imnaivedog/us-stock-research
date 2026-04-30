"""Universe sync orchestration."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.universe import a_pool, m_pool

DEFAULT_A_POOL_PATH = a_pool.DEFAULT_A_POOL_PATH
DEFAULT_THEMES_YAML = a_pool.DEFAULT_THEMES_PATH


class UnknownThemeError(ValueError):
    def __init__(
        self,
        yaml_path: Path,
        line_number: int,
        symbol: str,
        unknown_theme_id: str,
        valid_themes_count: int,
    ) -> None:
        self.yaml_path = yaml_path
        self.line_number = line_number
        self.symbol = symbol
        self.unknown_theme_id = unknown_theme_id
        self.valid_themes_count = valid_themes_count
        super().__init__(
            f"{yaml_path.name} line {line_number}: symbol {symbol} references "
            f"unregistered theme '{unknown_theme_id}'. Valid themes: {valid_themes_count} "
            "in themes.yaml. Add theme via 'usstock-data themes generate' first."
        )


class ThemesMasterEmptyError(ValueError):
    pass


def _yaml_symbol_lines(yaml_path: Path) -> dict[str, int]:
    lines: dict[str, int] = {}
    if not yaml_path.exists():
        return lines
    for idx, line in enumerate(yaml_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("- symbol:"):
            symbol = stripped.split(":", 1)[1].strip().strip("\"'")
        elif stripped.startswith("symbol:"):
            symbol = stripped.split(":", 1)[1].strip().strip("\"'")
        else:
            symbol = ""
        if symbol:
            lines[a_pool.normalize_symbol(symbol)] = idx
    return lines


def _theme_ids_from_yaml(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        str(item.get("theme_id") or item.get("id"))
        for item in payload.get("themes", [])
        if item.get("theme_id") or item.get("id")
    }


def load_themes_master(
    engine: Engine,
    fallback_yaml: Path = DEFAULT_THEMES_YAML,
) -> set[str]:
    db_ids: set[str] = set()
    try:
        with engine.begin() as conn:
            rows = conn.execute(text("SELECT theme_id FROM themes_master")).all()
        db_ids = {str(row[0]) for row in rows if row[0]}
    except Exception:
        db_ids = set()
    if db_ids:
        return db_ids

    yaml_ids = _theme_ids_from_yaml(fallback_yaml)
    if yaml_ids:
        return yaml_ids
    raise ThemesMasterEmptyError(
        "themes_master is empty and config/themes.yaml has no themes; "
        "run 'usstock-data themes sync' first."
    )


def validate_a_pool_themes(yaml_path: Path, master_theme_ids: set[str]) -> None:
    entries = a_pool.load_entries(yaml_path)
    symbol_lines = _yaml_symbol_lines(yaml_path)
    for entry in entries:
        symbol = a_pool.normalize_symbol(entry.get("symbol"))
        line_number = symbol_lines.get(symbol, 1)
        for theme_id in entry.get("themes") or []:
            if theme_id not in master_theme_ids:
                raise UnknownThemeError(
                    yaml_path,
                    line_number,
                    symbol,
                    str(theme_id),
                    len(master_theme_ids),
                )


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def sync_all(
    engine: Engine | None = None,
    dry_run: bool = False,
    a_pool_path: Path = DEFAULT_A_POOL_PATH,
) -> dict[str, dict[str, int]]:
    engine = engine or create_postgres_engine()
    master_theme_ids = load_themes_master(engine, fallback_yaml=DEFAULT_THEMES_YAML)
    validate_a_pool_themes(a_pool_path, master_theme_ids)
    m_result = await m_pool.sync(engine=engine, dry_run=dry_run)
    a_result = (
        {"synced": 0}
        if dry_run
        else await _maybe_await(
            a_pool.sync(
                engine=engine,
                path=a_pool_path,
                master_theme_ids=master_theme_ids,
            )
        )
    )
    return {"m": m_result, "a": a_result}
