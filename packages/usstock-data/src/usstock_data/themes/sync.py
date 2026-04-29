"""Sync themes.yaml into themes_master and themes_members."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.themes.validate import THEMES_PATH, load_theme_payload, member_rows_from_payload


def master_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for theme in payload.get("themes", []):
        rows.append(
            {
                "theme_id": theme["theme_id"],
                "name_cn": theme["name_cn"],
                "name_en": theme["name_en"],
                "description": theme.get("description"),
                "source_etfs": theme.get("source_etfs") or [],
            }
        )
    return rows


def sync(path: Path = THEMES_PATH, engine: Engine | None = None) -> dict[str, int]:
    engine = engine or create_postgres_engine()
    payload = load_theme_payload(path)
    masters = master_rows(payload)
    members = member_rows_from_payload(payload)
    with engine.begin() as conn:
        if masters:
            conn.execute(
                text(
                    """
                    INSERT INTO themes_master (
                        theme_id, name_cn, name_en, description, source_etfs, updated_at
                    )
                    VALUES (
                        :theme_id, :name_cn, :name_en, :description,
                        CAST(:source_etfs AS TEXT[]), now()
                    )
                    ON CONFLICT (theme_id) DO UPDATE SET
                        name_cn = EXCLUDED.name_cn,
                        name_en = EXCLUDED.name_en,
                        description = EXCLUDED.description,
                        source_etfs = EXCLUDED.source_etfs,
                        updated_at = now()
                    """
                ),
                [{**row, "source_etfs": row["source_etfs"]} for row in masters],
            )
        if members:
            conn.execute(
                text(
                    """
                    INSERT INTO themes_members (theme_id, symbol, weight, source_etfs)
                    VALUES (
                        :theme_id, :symbol, :weight, CAST(:source_etfs AS TEXT[])
                    )
                    ON CONFLICT (theme_id, symbol) DO UPDATE SET
                        weight = EXCLUDED.weight,
                        source_etfs = EXCLUDED.source_etfs
                    """
                ),
                members,
            )
    return {"themes": len(masters), "members": len(members)}


def sync_preview(path: Path = THEMES_PATH) -> str:
    payload = load_theme_payload(path)
    return json.dumps(
        {"themes": len(master_rows(payload)), "members": len(member_rows_from_payload(payload))},
        ensure_ascii=False,
        sort_keys=True,
    )
