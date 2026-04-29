"""Generate a themes.yaml draft from ETF holdings."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import normalize_symbol

ETF_THEME_MAP = {
    "SOXX": ["theme_semiconductor", "theme_ai_compute"],
    "SMH": ["theme_semiconductor", "theme_ai_compute", "theme_gpu"],
    "QQQ": ["theme_megacap_tech"],
    "XLK": ["theme_megacap_tech"],
    "XLE": ["theme_energy_traditional"],
    "ICLN": ["theme_clean_energy"],
    "XLF": ["theme_financials"],
    "FINX": ["theme_fintech"],
    "IBB": ["theme_biotech"],
    "XBI": ["theme_biotech"],
    "ITA": ["theme_defense"],
    "XAR": ["theme_defense"],
    "PAVE": ["theme_infrastructure"],
    "XLI": ["theme_industrials"],
    "XHB": ["theme_housing"],
    "CIBR": ["theme_cybersecurity"],
    "HACK": ["theme_cybersecurity"],
    "SKYY": ["theme_cloud_infra"],
    "WCLD": ["theme_cloud_infra"],
    "BLOK": ["theme_crypto"],
    "IBIT": ["theme_crypto"],
}


def generate_from_holdings(holdings: pd.DataFrame) -> dict[str, Any]:
    buckets: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(lambda: defaultdict(list))
    for row in holdings.itertuples(index=False):
        etf = normalize_symbol(row.etf_code)
        symbol = normalize_symbol(row.symbol)
        weight = float(row.weight or 0)
        for theme_id in ETF_THEME_MAP.get(etf, []):
            buckets[theme_id][symbol].append((etf, weight))
    themes = []
    for theme_id, members in sorted(buckets.items()):
        source_etfs = sorted({etf for rows in members.values() for etf, _ in rows})
        themes.append(
            {
                "theme_id": theme_id,
                "name_cn": theme_id.removeprefix("theme_"),
                "name_en": theme_id.removeprefix("theme_").replace("_", " ").title(),
                "description": None,
                "source_etfs": source_etfs,
                "members": [
                    {
                        "symbol": symbol,
                        "weight": round(sum(weight for _, weight in rows) / len(rows), 6),
                        "source_etfs": sorted({etf for etf, _ in rows}),
                    }
                    for symbol, rows in sorted(members.items())
                ],
            }
        )
    return {"themes": themes}


def load_holdings(engine: Engine) -> pd.DataFrame:
    return pd.read_sql_query(
        text("SELECT etf_code, symbol, weight FROM etf_holdings_latest"),
        engine,
    )


def generate(output: Path, engine: Engine | None = None) -> dict[str, Any]:
    engine = engine or create_postgres_engine()
    payload = generate_from_holdings(load_holdings(engine))
    output.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return payload
