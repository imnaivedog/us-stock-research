"""Top-level CLI for the reports layer."""

from __future__ import annotations

import argparse
from datetime import date

from usstock_reports.daily import run_daily


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="usstock-reports")
    parser.add_argument("command", choices=["daily"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == "daily":
        daily_parser = argparse.ArgumentParser(prog="usstock-reports daily")
        daily_parser.add_argument("--date", required=True)
        daily_parser.add_argument("--no-notion", action="store_true")
        daily_parser.add_argument("--no-discord", action="store_true")
        daily_args = daily_parser.parse_args(args.args)
        result = run_daily(
            trade_date=date.fromisoformat(daily_args.date),
            no_notion=daily_args.no_notion,
            no_discord=daily_args.no_discord,
        )
        print(result)
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
