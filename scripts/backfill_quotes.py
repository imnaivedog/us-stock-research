from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.pg_client import PostgresClient  # noqa: E402

DEFAULT_SYMBOLS_FILE = PROJECT_ROOT / "diagnostic_2026-04-25" / "missing_quotes_symbols.txt"
DEFAULT_QUOTES_DIR = PROJECT_ROOT / "data" / "snapshots" / "bootstrap_2026-04-25" / "quotes"
QUOTE_COLUMNS = ["symbol", "trade_date", "open", "high", "low", "close", "adj_close", "volume"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill quotes_daily from local parquet snapshots."
    )
    parser.add_argument("--symbols-file", type=Path, default=DEFAULT_SYMBOLS_FILE)
    parser.add_argument("--quotes-dir", type=Path, default=DEFAULT_QUOTES_DIR)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate parquet files but skip DB writes.",
    )
    return parser.parse_args()


def read_symbols(path: Path) -> list[str]:
    return [
        line.strip().upper()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def none_if_missing(value: Any) -> Any:
    return None if pd.isna(value) else value


def normalize_rows(symbol: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    missing_cols = sorted(set(QUOTE_COLUMNS) - set(frame.columns))
    if missing_cols:
        raise ValueError(f"{symbol} parquet missing columns: {missing_cols}")

    rows: list[dict[str, Any]] = []
    for item in frame[QUOTE_COLUMNS].to_dict("records"):
        trade_date = none_if_missing(item["trade_date"])
        if hasattr(trade_date, "date"):
            trade_date = trade_date.date()
        rows.append(
            {
                "symbol": symbol,
                "trade_date": str(trade_date),
                "open": none_if_missing(item["open"]),
                "high": none_if_missing(item["high"]),
                "low": none_if_missing(item["low"]),
                "close": none_if_missing(item["close"]),
                "adj_close": none_if_missing(item["adj_close"]),
                "volume": int(item["volume"]) if not pd.isna(item["volume"]) else None,
            }
        )
    return rows


def existing_quote_symbols(pg: PostgresClient, symbols: list[str]) -> set[str]:
    if not symbols:
        return set()
    placeholders = ", ".join(f":s{idx}" for idx, _ in enumerate(symbols))
    params = {f"s{idx}": symbol for idx, symbol in enumerate(symbols)}
    sql = f"SELECT DISTINCT symbol FROM quotes_daily WHERE symbol IN ({placeholders})"
    with pg.engine.begin() as conn:
        return {row[0] for row in conn.execute(text(sql), params)}


def main() -> None:
    os.chdir(PROJECT_ROOT)
    args = parse_args()
    symbols = read_symbols(args.symbols_file)
    pg = PostgresClient()
    already_present = existing_quote_symbols(pg, symbols)

    success_symbols = 0
    skipped_symbols = sorted(already_present)
    all_rows: list[dict[str, Any]] = []
    failures: dict[str, str] = {}

    for symbol in symbols:
        if symbol in already_present:
            continue
        parquet_path = args.quotes_dir / f"{symbol}.parquet"
        if not parquet_path.exists():
            failures[symbol] = "parquet_missing"
            continue
        if parquet_path.stat().st_size == 0:
            failures[symbol] = "parquet_empty"
            continue

        try:
            frame = pd.read_parquet(parquet_path)
            if frame.empty:
                failures[symbol] = "parquet_zero_rows"
                continue
            rows = normalize_rows(symbol, frame)
            all_rows.extend(rows)
            success_symbols += 1
        except Exception as exc:  # noqa: BLE001 - one-shot diagnostic script should report all failures
            failures[symbol] = f"{type(exc).__name__}: {exc}"

    if not args.dry_run and all_rows:
        pg.upsert(
            "quotes_daily",
            all_rows,
            conflict_cols=["symbol", "trade_date"],
            update_cols=["open", "high", "low", "close", "adj_close", "volume"],
            batch_size=5000,
        )

    print(
        json.dumps(
            {
                "symbols_requested": len(symbols),
                "symbols_skipped_already_present": len(skipped_symbols),
                "symbols_backfilled": success_symbols,
                "rows_backfilled": len(all_rows),
                "symbols_failed": len(failures),
                "failures": failures,
                "dry_run": args.dry_run,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
