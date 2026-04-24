from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.universe_filter import async_filter_universe  # noqa: E402
from lib.fmp_client import FMPClient  # noqa: E402
from lib.gcs_client import upload_dir  # noqa: E402
from lib.pg_client import PostgresClient  # noqa: E402


ETF_UNIVERSE_PATH = PROJECT_ROOT / "config" / "etf_universe.csv"
THRESHOLDS_PATH = PROJECT_ROOT / "config" / "thresholds.yaml"
SNAPSHOTS_DIR = PROJECT_ROOT / "data" / "snapshots"
LOADER_PRIORITY = ["IVV", "IJH", "IJR", "QQQ", "IPO"]
SOURCE_LABEL = {"QQQ": "QQQ_intl"}
MACRO_COLUMN_MAP = {
    "vix": "vix",
    "spy": "spy_close",
    "qqq": "qqq_close",
    "tlt": "tlt_close",
    "gld": "gld_close",
    "uup": "uup_close",
    "hyg": "hyg_close",
    "lqd": "lqd_close",
    "dxy": "dxy",
    "wti": "wti",
    "btc": "btc_close",
    "ief": "ief_close",
}


class BootstrapSettings(BaseSettings):
    gcs_bootstrap_bucket: str = "naive-usstock-data"
    gcs_bootstrap_prefix: str = "bootstrap/"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"), serialize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M1 one-shot 5-year historical bootstrap.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true", help="Reuse the newest existing checkpoint.")
    mode.add_argument("--fresh", action="store_true", help="Wipe today's bootstrap snapshot and restart.")
    parser.add_argument("--dry-run", action="store_true", help="Skip DB writes.")
    parser.add_argument("--start-date", help="Override default start date of today minus 5 years.")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "loader_etfs": [],
            "filter_completed": False,
            "quotes": [],
            "macro": [],
            "etf_holdings_latest": [],
            "sp500_completed": False,
            "gcs_upload_completed": False,
        }
    with path.open("r", encoding="utf-8") as handle:
        checkpoint = json.load(handle)
    checkpoint.setdefault("loader_etfs", [])
    checkpoint.setdefault("filter_completed", False)
    checkpoint.setdefault("quotes", [])
    checkpoint.setdefault("macro", [])
    checkpoint.setdefault("etf_holdings_latest", [])
    checkpoint.setdefault("sp500_completed", False)
    checkpoint.setdefault("gcs_upload_completed", False)
    return checkpoint


def save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(checkpoint, handle, indent=2, sort_keys=True)
    temp_path.replace(path)


def resolve_run_dir(args: argparse.Namespace, today: date) -> Path:
    if args.resume:
        checkpoints = sorted(SNAPSHOTS_DIR.glob("bootstrap_*/_checkpoint.json"))
        if checkpoints:
            return checkpoints[-1].parent
    run_dir = SNAPSHOTS_DIR / f"bootstrap_{today.isoformat()}"
    if args.fresh and run_dir.exists():
        shutil.rmtree(run_dir)
    return run_dir


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(".", "-")


def parse_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = value.replace("%", "").replace(",", "").replace("_", "").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_date(value: Any) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def holding_symbol(row: dict[str, Any]) -> str:
    for key in ("asset", "holdingSymbol", "ticker", "symbol"):
        symbol = normalize_symbol(row.get(key))
        if symbol:
            return symbol
    return ""


def holding_weight(row: dict[str, Any]) -> float | None:
    for key in ("weight", "weightPercentage", "percentage", "weightPercentageOfNetAssets"):
        value = parse_number(row.get(key))
        if value is not None:
            return value
    return None


def holding_as_of_date(row: dict[str, Any], fallback: str) -> str:
    for key in ("date", "asOfDate", "as_of_date", "reportedDate", "updatedAt"):
        parsed = parse_date(row.get(key))
        if parsed:
            return parsed
    return fallback


def load_etf_universe() -> pd.DataFrame:
    if not ETF_UNIVERSE_PATH.exists():
        raise FileNotFoundError("Run scripts/export_etf_audit.py before bootstrap_history.py")
    df = pd.read_csv(ETF_UNIVERSE_PATH, keep_default_na=False)
    required = {"code", "algo_role", "is_candidate"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"config/etf_universe.csv missing columns: {sorted(missing)}")
    return df


def _csv_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def get_loader_etfs(df: pd.DataFrame) -> list[str]:
    loader_mask = (df["algo_role"].astype(str).str.strip() == "L1_loader") & df["is_candidate"].map(
        _csv_bool
    )
    codes = [normalize_symbol(code) for code in df.loc[loader_mask, "code"]]
    ordered = [code for code in LOADER_PRIORITY if code in codes]
    if ordered != LOADER_PRIORITY:
        raise ValueError(f"Loader ETF set differs from expected: found {ordered}, expected {LOADER_PRIORITY}")
    return ordered


def holdings_parquet_path(run_dir: Path, etf: str) -> Path:
    return run_dir / "holdings" / f"{etf}.parquet"


async def get_or_load_holdings(
    client: FMPClient,
    etf: str,
    run_dir: Path,
    checkpoint: dict[str, Any],
    checkpoint_key: str,
    checkpoint_path: Path,
) -> list[dict[str, Any]]:
    path = holdings_parquet_path(run_dir, etf)
    if path.exists():
        if etf not in checkpoint[checkpoint_key]:
            checkpoint[checkpoint_key].append(etf)
            save_checkpoint(checkpoint_path, checkpoint)
        return pd.read_parquet(path).to_dict("records")

    rows = await client.get_etf_holdings(etf)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    if etf not in checkpoint[checkpoint_key]:
        checkpoint[checkpoint_key].append(etf)
        save_checkpoint(checkpoint_path, checkpoint)
    return rows


async def build_symbol_universe(
    client: FMPClient,
    loader_etfs: list[str],
    run_dir: Path,
    as_of_date: str,
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    universe: dict[str, dict[str, Any]] = {}
    holdings_by_etf: dict[str, list[dict[str, Any]]] = {}
    for etf in loader_etfs:
        rows = await get_or_load_holdings(
            client,
            etf,
            run_dir,
            checkpoint,
            "loader_etfs",
            checkpoint_path,
        )
        holdings_by_etf[etf] = rows
        source = SOURCE_LABEL.get(etf, etf)
        for row in rows:
            symbol = holding_symbol(row)
            if not symbol:
                continue
            if symbol not in universe:
                universe[symbol] = {
                    "symbol": symbol,
                    "source": source,
                    "source_secondary": [],
                    "is_candidate": True,
                    "added_date": as_of_date,
                    "last_seen_date": as_of_date,
                    "as_of_date": as_of_date,
                }
            elif source != universe[symbol]["source"] and source not in universe[symbol]["source_secondary"]:
                universe[symbol]["source_secondary"].append(source)
    return universe, holdings_by_etf


def upsert_symbol_universe(
    pg: PostgresClient | None,
    rows: list[dict[str, Any]],
    dry_run: bool,
) -> None:
    if dry_run or not pg or not rows:
        return
    pg.upsert(
        "symbol_universe",
        rows,
        conflict_cols=["symbol"],
        update_cols=[
            "source",
            "source_secondary",
            "is_candidate",
            "is_active",
            "market_cap",
            "adv_20d",
            "ipo_date",
            "added_date",
            "last_seen_date",
            "removed_date",
            "as_of_date",
            "filter_reason",
        ],
    )


def base_symbol_rows(universe: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in universe.values():
        rows.append({**item, "source_secondary": Jsonb(item["source_secondary"])})
    return rows


def write_filter_results(path: Path, results: dict[str, dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, sort_keys=True)


def read_filter_results(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def enrich_symbol_rows(
    universe: dict[str, dict[str, Any]],
    filter_results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol, item in universe.items():
        result = filter_results.get(symbol, {})
        rows.append(
            {
                **item,
                "source_secondary": Jsonb(item["source_secondary"]),
                "is_active": bool(result.get("is_active")),
                "market_cap": result.get("market_cap"),
                "adv_20d": result.get("adv_20d"),
                "ipo_date": result.get("ipo_date"),
                "filter_reason": result.get("reason"),
            }
        )
    return rows


def quote_rows(symbol: str, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history:
        trade_date = parse_date(item.get("date"))
        if not trade_date:
            continue
        rows.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "open": parse_number(item.get("open")),
                "high": parse_number(item.get("high")),
                "low": parse_number(item.get("low")),
                "close": parse_number(item.get("close")),
                "adj_close": parse_number(item.get("adjClose") or item.get("adj_close")),
                "volume": int(parse_number(item.get("volume")) or 0),
            }
        )
    return rows


def write_quotes_parquet(run_dir: Path, symbol: str, rows: list[dict[str, Any]]) -> None:
    path = run_dir / "quotes" / f"{symbol}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


async def fetch_history_batch(
    client: FMPClient,
    symbols: list[str],
    start_date: str,
    end_date: str,
) -> list[tuple[str, list[dict[str, Any]]]]:
    async def fetch(symbol: str) -> tuple[str, list[dict[str, Any]]]:
        return symbol, await client.get_historical(symbol, start_date, end_date)

    return await asyncio.gather(*(fetch(symbol) for symbol in symbols))


async def process_quotes(
    client: FMPClient,
    pg: PostgresClient | None,
    run_dir: Path,
    active_symbols: list[str],
    start_date: str,
    end_date: str,
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
    dry_run: bool,
) -> int:
    completed = set(checkpoint["quotes"])
    pending = [symbol for symbol in active_symbols if symbol not in completed]
    total_rows = 0
    for idx in range(0, len(pending), 50):
        batch_symbols = pending[idx : idx + 50]
        histories = await fetch_history_batch(client, batch_symbols, start_date, end_date)
        for symbol, history in histories:
            rows = quote_rows(symbol, history)
            write_quotes_parquet(run_dir, symbol, rows)
            if not dry_run and pg and rows:
                pg.upsert(
                    "quotes_daily",
                    rows,
                    conflict_cols=["symbol", "trade_date"],
                    update_cols=["open", "high", "low", "close", "adj_close", "volume"],
                )
            total_rows += len(rows)
            checkpoint["quotes"].append(symbol)
        save_checkpoint(checkpoint_path, checkpoint)
        logger.info(
            "quote progress",
            completed=len(checkpoint["quotes"]),
            total=len(active_symbols),
            latest_batch=len(batch_symbols),
        )
    return total_rows


def macro_rows_from_history(code: str, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in history:
        trade_date = parse_date(item.get("date"))
        if not trade_date:
            continue
        rows.append({"code": code, "trade_date": trade_date, "close": parse_number(item.get("adjClose") or item.get("close"))})
    return rows


def write_macro_parquet(run_dir: Path, code: str, rows: list[dict[str, Any]]) -> None:
    safe_code = code.replace("^", "").replace("/", "_")
    path = run_dir / "macro" / f"{safe_code}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def read_macro_parquets(run_dir: Path) -> dict[str, dict[str, float | None]]:
    by_date: dict[str, dict[str, float | None]] = defaultdict(dict)
    for path in (run_dir / "macro").glob("*.parquet"):
        df = pd.read_parquet(path)
        for row in df.to_dict("records"):
            by_date[str(row["trade_date"])][str(row["code"])] = row.get("close")
    return by_date


async def process_macro(
    client: FMPClient,
    pg: PostgresClient | None,
    run_dir: Path,
    macro_symbols: dict[str, str],
    start_date: str,
    end_date: str,
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
    dry_run: bool,
) -> int:
    for key, symbol in macro_symbols.items():
        if key in checkpoint["macro"]:
            continue
        history = await client.get_historical(symbol, start_date, end_date)
        if key == "wti" and not history:
            logger.warning("macro symbol returned no data; falling back to USO", key=key, symbol=symbol)
            history = await client.get_historical("USO", start_date, end_date)
        if not history:
            logger.warning("macro symbol returned no data; macro column will remain NULL", key=key, symbol=symbol)
        rows = macro_rows_from_history(key, history)
        write_macro_parquet(run_dir, key, rows)
        checkpoint["macro"].append(key)
        save_checkpoint(checkpoint_path, checkpoint)

    by_date = read_macro_parquets(run_dir)
    macro_rows: list[dict[str, Any]] = []
    for trade_date, values in sorted(by_date.items()):
        row: dict[str, Any] = {"trade_date": trade_date}
        for key, column in MACRO_COLUMN_MAP.items():
            row[column] = values.get(key)
        us10y = values.get("us10y")
        us2y = values.get("us2y")
        row["spread_10y_2y"] = None if us10y is None or us2y is None else us10y - us2y
        macro_rows.append(row)

    if not dry_run and pg and macro_rows:
        pg.upsert(
            "macro_daily",
            macro_rows,
            conflict_cols=["trade_date"],
            update_cols=[
                "vix",
                "spy_close",
                "qqq_close",
                "tlt_close",
                "gld_close",
                "uup_close",
                "hyg_close",
                "lqd_close",
                "dxy",
                "wti",
                "btc_close",
                "ief_close",
                "spread_10y_2y",
            ],
        )
    return len(macro_rows)


async def process_all_etf_holdings(
    client: FMPClient,
    pg: PostgresClient | None,
    run_dir: Path,
    etf_codes: list[str],
    as_of_date: str,
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
    dry_run: bool,
) -> int:
    total_rows = 0
    for etf in etf_codes:
        rows = await get_or_load_holdings(
            client,
            etf,
            run_dir,
            checkpoint,
            "etf_holdings_latest",
            checkpoint_path,
        )
        db_rows = [
            {
                "etf_code": etf,
                "symbol": holding_symbol(row),
                "weight": holding_weight(row),
                "as_of_date": holding_as_of_date(row, as_of_date),
            }
            for row in rows
            if holding_symbol(row)
        ]
        if not dry_run and pg and db_rows:
            pg.upsert(
                "etf_holdings_latest",
                db_rows,
                conflict_cols=["etf_code", "symbol"],
                update_cols=["weight", "as_of_date"],
            )
        total_rows += len(db_rows)
    return total_rows


def process_sp500_members(
    pg: PostgresClient | None,
    ivv_holdings: list[dict[str, Any]],
    as_of_date: str,
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
    dry_run: bool,
) -> int:
    if checkpoint["sp500_completed"]:
        return 0
    rows = [
        {"as_of_date": as_of_date, "symbol": holding_symbol(row), "index_name": "SP500"}
        for row in ivv_holdings
        if holding_symbol(row)
    ]
    if not dry_run and pg and rows:
        pg.upsert(
            "sp500_members_daily",
            rows,
            conflict_cols=["as_of_date", "symbol", "index_name"],
            update_cols=[],
        )
    checkpoint["sp500_completed"] = True
    save_checkpoint(checkpoint_path, checkpoint)
    return len(rows)


def table_counts(pg: PostgresClient | None, dry_run: bool) -> dict[str, int | None]:
    tables = [
        "quotes_daily",
        "macro_daily",
        "sp500_members_daily",
        "etf_holdings_latest",
        "symbol_universe",
    ]
    if dry_run or not pg:
        return {table: None for table in tables}
    return {table: int(pg.fetch_scalar(f"SELECT count(*) FROM {table}") or 0) for table in tables}


async def async_main() -> None:
    configure_logging()
    args = parse_args()
    started = time.monotonic()
    today = date.today()
    as_of_date = today.isoformat()
    start_date = args.start_date or (today - timedelta(days=365 * 5)).isoformat()
    end_date = as_of_date
    run_dir = resolve_run_dir(args, today)
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / "_checkpoint.json"
    checkpoint = load_checkpoint(checkpoint_path)
    save_checkpoint(checkpoint_path, checkpoint)

    etf_df = load_etf_universe()
    loader_etfs = get_loader_etfs(etf_df)
    all_etfs = sorted({normalize_symbol(code) for code in etf_df["code"] if normalize_symbol(code)})
    settings = BootstrapSettings()
    pg = None if args.dry_run else PostgresClient()

    async with FMPClient() as fmp:
        universe, holdings_by_etf = await build_symbol_universe(
            fmp,
            loader_etfs,
            run_dir,
            as_of_date,
            checkpoint,
            checkpoint_path,
        )
        upsert_symbol_universe(pg, base_symbol_rows(universe), args.dry_run)

        filter_results_path = run_dir / "symbol_universe_filter.json"
        if checkpoint["filter_completed"] and filter_results_path.exists():
            filter_results = read_filter_results(filter_results_path)
        else:
            filter_results = await async_filter_universe(sorted(universe))
            write_filter_results(filter_results_path, filter_results)
            checkpoint["filter_completed"] = True
            save_checkpoint(checkpoint_path, checkpoint)

        enriched_rows = enrich_symbol_rows(universe, filter_results)
        upsert_symbol_universe(pg, enriched_rows, args.dry_run)
        active_symbols = sorted(row["symbol"] for row in enriched_rows if row["is_active"])

        quote_rows_written = await process_quotes(
            fmp,
            pg,
            run_dir,
            active_symbols,
            start_date,
            end_date,
            checkpoint,
            checkpoint_path,
            args.dry_run,
        )

        thresholds = load_yaml(THRESHOLDS_PATH)
        macro_rows_written = await process_macro(
            fmp,
            pg,
            run_dir,
            thresholds.get("macro_symbols", {}),
            start_date,
            end_date,
            checkpoint,
            checkpoint_path,
            args.dry_run,
        )

        etf_holdings_rows = await process_all_etf_holdings(
            fmp,
            pg,
            run_dir,
            all_etfs,
            as_of_date,
            checkpoint,
            checkpoint_path,
            args.dry_run,
        )

        ivv_holdings = holdings_by_etf.get("IVV")
        if not ivv_holdings and holdings_parquet_path(run_dir, "IVV").exists():
            ivv_holdings = pd.read_parquet(holdings_parquet_path(run_dir, "IVV")).to_dict("records")
        sp500_rows = process_sp500_members(
            pg,
            ivv_holdings or [],
            as_of_date,
            checkpoint,
            checkpoint_path,
            args.dry_run,
        )

    prefix = settings.gcs_bootstrap_prefix
    if not prefix.endswith("/"):
        prefix += "/"
    gcs_uri = f"gs://{settings.gcs_bootstrap_bucket}/{prefix}{as_of_date}/"
    if not checkpoint["gcs_upload_completed"]:
        upload_dir(run_dir, gcs_uri)
        checkpoint["gcs_upload_completed"] = True
        save_checkpoint(checkpoint_path, checkpoint)

    inactive_count = len(enriched_rows) - len(active_symbols)
    counts = table_counts(pg, args.dry_run)
    elapsed = time.monotonic() - started
    summary = {
        "total_symbols": len(enriched_rows),
        "active_symbols": len(active_symbols),
        "inactive_symbols": inactive_count,
        "quote_rows_written_this_run": quote_rows_written,
        "macro_rows": macro_rows_written,
        "etf_holdings_rows": etf_holdings_rows,
        "sp500_rows": sp500_rows,
        "table_counts": counts,
        "elapsed_seconds": round(elapsed, 2),
        "gcs_uri": gcs_uri,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    asyncio.run(async_main())
