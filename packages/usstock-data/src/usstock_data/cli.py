"""Top-level CLI for the data layer."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

from loguru import logger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily = subparsers.add_parser("daily", help="Run the data-layer daily pipeline.")
    daily.add_argument(
        "--as-of", dest="as_of", help="Trade date to process, defaults to latest quotes."
    )
    daily.add_argument("--dry-run", action="store_true", help="Print planned work without writes.")

    universe = subparsers.add_parser("universe", help="Manage m_pool and a_pool universes.")
    universe.add_argument("args", nargs=argparse.REMAINDER)

    themes = subparsers.add_parser("themes", help="Manage themes.yaml and theme tables.")
    themes.add_argument("args", nargs=argparse.REMAINDER)

    etl = subparsers.add_parser("etl", help="Run individual ETL jobs.")
    etl.add_argument("name", choices=["shares-outstanding"])
    etl.add_argument("args", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "daily":
        return asyncio.run(run_daily(as_of=parse_date_arg(args.as_of), dry_run=args.dry_run))
    if args.command == "universe":
        from usstock_data.universe.cli import main as universe_main

        return universe_main(args.args)
    if args.command == "themes":
        from usstock_data.themes.cli import main as themes_main

        return themes_main(args.args)
    if args.command == "etl":
        if args.name == "shares-outstanding":
            from usstock_data.etl.shares_outstanding import main as shares_main

            return shares_main(args.args)
    return 0


def parse_date_arg(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


async def run_daily(as_of: date | None = None, dry_run: bool = False) -> int:
    from usstock_data.etl import (
        corporate_actions,
        earnings_calendar,
        etf_holdings,
        fundamentals,
        macro_daily,
        quotes_daily,
        sp500_members,
    )

    steps = [
        ("quotes", quotes_daily.run),
        ("macro", macro_daily.run),
        ("corporate_actions", corporate_actions.run),
        ("fundamentals", fundamentals.run),
        ("earnings_calendar", earnings_calendar.run),
        ("sp500_members", sp500_members.run),
        ("etf_holdings", etf_holdings.run),
    ]
    for name, step in steps:
        logger.info("data daily step started: {}", name)
        written = await step(as_of=as_of, dry_run=dry_run)
        logger.info("data daily step finished: {} rows={}", name, written)
    from usstock_data.derived.compute_indicators import run_compute_indicators
    from usstock_data.universe.sync import sync_all

    logger.info("data daily step started: universe sync")
    sync_result = await sync_all(dry_run=dry_run)
    logger.info("data daily step finished: universe sync {}", sync_result)
    if as_of is None:
        logger.info("compute_indicators skipped because --as-of was not provided")
    else:
        logger.info("data daily step started: compute_indicators")
        result = run_compute_indicators(as_of=as_of, dry_run=dry_run)
        logger.info("data daily step finished: compute_indicators rows={}", result.rows_written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
