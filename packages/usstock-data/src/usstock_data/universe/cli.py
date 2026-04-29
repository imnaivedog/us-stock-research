"""CLI entry point for universe management."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from typing import Any

from sqlalchemy import text

from usstock_data.db import create_postgres_engine
from usstock_data.etl.common import normalize_symbol
from usstock_data.universe import a_pool, m_pool
from usstock_data.universe.sync import sync_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-data universe")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List symbols in m_pool/a_pool.")
    list_parser.add_argument("--pool", choices=["m", "a", "all"], default="all")
    list_parser.add_argument("--format", choices=["table", "json", "csv"], default="table")

    show_parser = subparsers.add_parser("show", help="Show cross-pool symbol details.")
    show_parser.add_argument("symbol")

    sync_parser = subparsers.add_parser("sync", help="Sync m_pool and a_pool.")
    sync_parser.add_argument("--pool", choices=["m", "a", "all"], default="all")
    sync_parser.add_argument("--dry-run", action="store_true")

    add_parser = subparsers.add_parser("add", help="Add a symbol to a pool.")
    add_parser.add_argument("symbol")
    add_parser.add_argument("--pool", choices=["m", "a"], required=True)
    add_parser.add_argument("--source", default="manual")
    add_parser.add_argument("--thesis")
    add_parser.add_argument("--target-cap", type=float)

    remove_parser = subparsers.add_parser("remove", help="Remove a symbol from a pool.")
    remove_parser.add_argument("symbol")
    remove_parser.add_argument("--pool", choices=["m", "a"], required=True)
    remove_parser.add_argument("--reason")

    target_parser = subparsers.add_parser("set-target", help="Set a_pool target market cap.")
    target_parser.add_argument("symbol")
    target_parser.add_argument("--target-cap", type=float, required=True)

    a_pool_parser = subparsers.add_parser("a-pool", help="Manage A-pool YAML anchors.")
    a_pool_sub = a_pool_parser.add_subparsers(dest="a_pool_command", required=True)

    a_add = a_pool_sub.add_parser("add")
    a_add.add_argument("symbol")
    a_add.add_argument("--thesis-stop-mcap", type=float, required=True)
    a_add.add_argument("--target-mcap", type=float, required=True)
    a_add.add_argument("--themes", required=True)
    a_add.add_argument("--summary", required=True)
    a_add.add_argument("--status", choices=["active", "watching", "paused"], default="active")

    a_set_mcap = a_pool_sub.add_parser("set-mcap")
    a_set_mcap.add_argument("symbol")
    a_set_mcap.add_argument("--thesis-stop-mcap", type=float, required=True)
    a_set_mcap.add_argument("--target-mcap", type=float, required=True)

    a_set_themes = a_pool_sub.add_parser("set-themes")
    a_set_themes.add_argument("symbol")
    a_set_themes.add_argument("--themes", required=True)

    a_remove = a_pool_sub.add_parser("remove")
    a_remove.add_argument("symbol")

    a_pool_sub.add_parser("list")
    a_pool_sub.add_parser("sync")
    a_pool_sub.add_parser("validate")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    engine = create_postgres_engine()
    if args.command == "list":
        rows = list_rows(engine, args.pool)
        render_rows(rows, args.format)
        return 0
    if args.command == "show":
        row = show_symbol(engine, args.symbol)
        print(json.dumps(row, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "sync":
        result = asyncio.run(run_sync(args.pool, engine, args.dry_run))
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "a-pool":
        return run_a_pool_command(args, engine)
    if args.command == "add":
        if args.pool == "a":
            raise SystemExit("universe add --pool a is deprecated; use universe a-pool add")
        else:
            m_pool_row = manual_m_pool_row(args.symbol, args.source)
            from usstock_data.universe.core import audit_change, upsert_universe_symbols

            upsert_universe_symbols(engine, [m_pool_row])
            audit_change(engine, args.symbol, "forced_in", pool="m", reason=f"manual:{args.source}")
        return 0
    if args.command == "remove":
        if args.pool == "a":
            a_pool.remove(args.symbol, engine=engine, reason=args.reason)
        else:
            remove_m_pool_symbol(engine, args.symbol, args.reason)
        return 0
    if args.command == "set-target":
        raise SystemExit("set-target is deprecated; use universe a-pool set-mcap")
        return 0
    parser.error("unknown command")
    return 2


def list_rows(engine: Any, pool: str) -> list[dict[str, Any]]:
    where = "" if pool == "all" else "WHERE u.pool = :pool"
    with engine.begin() as conn:
        return [
            dict(row)
            for row in conn.execute(
                text(
                    f"""
                    SELECT
                        u.symbol,
                        u.pool,
                        u.is_active,
                        u.source,
                        u.market_cap,
                        u.adv_20d,
                        u.thesis_url,
                        u.thesis_added_at,
                        w.status AS watchlist_status
                    FROM symbol_universe u
                    LEFT JOIN watchlist w ON w.symbol = u.symbol
                    {where}
                    ORDER BY u.pool, u.symbol
                    """
                ),
                {"pool": pool},
            ).mappings()
        ]


def show_symbol(engine: Any, symbol: str) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    with engine.begin() as conn:
        universe = (
            conn.execute(
                text(
                    """
                SELECT u.*, w.status AS watchlist_status
                FROM symbol_universe u
                LEFT JOIN watchlist w ON w.symbol = u.symbol
                WHERE u.symbol = :symbol
                """
                ),
                {"symbol": symbol},
            )
            .mappings()
            .first()
        )
        quote = (
            conn.execute(
                text(
                    """
                SELECT trade_date, close, adj_close, volume, asset_class
                FROM quotes_daily
                WHERE symbol = :symbol
                ORDER BY trade_date DESC
                LIMIT 1
                """
                ),
                {"symbol": symbol},
            )
            .mappings()
            .first()
        )
    return {
        "symbol": symbol,
        "universe": dict(universe) if universe else None,
        "latest_quote": dict(quote) if quote else None,
    }


async def run_sync(pool: str, engine: Any, dry_run: bool) -> dict[str, Any]:
    if pool == "m":
        return {"m": await m_pool.sync(engine=engine, dry_run=dry_run)}
    if pool == "a":
        return {"a": {"synced": 0} if dry_run else a_pool.sync(engine=engine)}
    return await sync_all(engine=engine, dry_run=dry_run)


def render_rows(rows: list[dict[str, Any]], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return
    if output_format == "csv":
        if not rows:
            return
        writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        return
    columns = [
        "symbol",
        "pool",
        "is_active",
        "source",
        "market_cap",
        "thesis_url",
        "thesis_added_at",
    ]
    print(" | ".join(columns))
    print("-" * 96)
    for row in rows:
        print(
            " | ".join(
                "" if row.get(column) is None else str(row.get(column)) for column in columns
            )
        )


def manual_m_pool_row(symbol: str, source: str) -> dict[str, Any]:
    return {
        "symbol": normalize_symbol(symbol),
        "pool": "m",
        "source": source,
        "is_candidate": True,
        "is_active": True,
        "market_cap": None,
        "adv_20d": None,
        "ipo_date": None,
        "added_date": None,
        "as_of_date": None,
        "filter_reason": "m_pool_manual",
        "thesis_url": None,
    }


def remove_m_pool_symbol(engine: Any, symbol: str, reason: str | None) -> None:
    from usstock_data.universe.core import audit_change

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
                WHERE symbol = :symbol AND pool = 'm'
                """
            ),
            {"symbol": symbol},
        )
    audit_change(engine, symbol, "removed", pool="m", reason=reason or "m_pool_manual_remove")


def _themes_arg(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def run_a_pool_command(args: argparse.Namespace, engine: Any) -> int:
    command = args.a_pool_command
    if command == "add":
        a_pool.add_yaml_entry(
            args.symbol,
            thesis_stop_mcap_b=args.thesis_stop_mcap,
            target_mcap_b=args.target_mcap,
            themes=_themes_arg(args.themes),
            summary=args.summary,
            status=args.status,
        )
        return 0
    if command == "set-mcap":
        a_pool.set_mcap_yaml(args.symbol, args.thesis_stop_mcap, args.target_mcap)
        return 0
    if command == "set-themes":
        a_pool.set_themes_yaml(args.symbol, _themes_arg(args.themes))
        return 0
    if command == "remove":
        a_pool.remove_yaml_entry(args.symbol)
        a_pool.remove(args.symbol, engine=engine)
        return 0
    if command == "list":
        print(json.dumps(a_pool.load_entries(), ensure_ascii=False, indent=2, default=str))
        return 0
    if command == "sync":
        print(json.dumps(a_pool.sync(engine=engine), ensure_ascii=False, indent=2, default=str))
        return 0
    if command == "validate":
        a_pool.validate_entries(a_pool.load_entries())
        print("ok")
        return 0
    raise SystemExit(f"unknown a-pool command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
