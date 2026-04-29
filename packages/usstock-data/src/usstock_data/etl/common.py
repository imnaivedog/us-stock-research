"""Shared helpers for data-layer ETL jobs."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection, Engine


PROJECT_ROOT = Path(__file__).resolve().parents[5]
CONFIG_DIR = PROJECT_ROOT / "config"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(".", "-")


def parse_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def quote_identifier(identifier: str) -> str:
    if not _IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier}")
    return f'"{identifier}"'


def run_many(conn: Connection, sql: str, rows: Sequence[dict[str, Any]]) -> int:
    if not rows:
        return 0
    conn.execute(text(sql), list(rows))
    return len(rows)


def upsert_rows(
    engine: Engine,
    table: str,
    rows: Sequence[dict[str, Any]],
    conflict_cols: Sequence[str],
    update_cols: Sequence[str],
) -> int:
    if not rows:
        return 0
    columns = list(rows[0])
    quoted_table = quote_identifier(table)
    quoted_columns = ", ".join(quote_identifier(col) for col in columns)
    values = ", ".join(f":{col}" for col in columns)
    conflict = ", ".join(quote_identifier(col) for col in conflict_cols)
    update_targets = [col for col in update_cols if col not in conflict_cols]
    set_clause = ", ".join(
        f"{quote_identifier(col)} = EXCLUDED.{quote_identifier(col)}" for col in update_targets
    )
    if "updated_at" not in update_targets:
        set_clause = f"{set_clause}, updated_at = now()" if set_clause else "updated_at = now()"
    sql = (
        f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({values}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}"
    )
    with engine.begin() as conn:
        conn.execute(text(sql), list(rows))
    return len(rows)


def fetch_symbols_in_pool(conn: Connection, pool: str = "m") -> list[str]:
    if pool == "all":
        result = conn.execute(
            text("SELECT symbol FROM symbol_universe WHERE is_active IS TRUE ORDER BY symbol")
        )
    else:
        result = conn.execute(
            text(
                """
                SELECT symbol
                FROM symbol_universe
                WHERE is_active IS TRUE AND pool = :pool
                ORDER BY symbol
                """
            ),
            {"pool": pool},
        )
    return [normalize_symbol(symbol) for symbol in result.scalars().all()]


def rows_for_symbols(conn: Connection, symbols: Sequence[str], sql: str) -> list[dict[str, Any]]:
    if not symbols:
        return []
    result = conn.execute(
        text(sql).bindparams(bindparam("symbols", expanding=True)),
        {"symbols": list(symbols)},
    )
    return [dict(row) for row in result.mappings().all()]


def as_iso_date(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else None
