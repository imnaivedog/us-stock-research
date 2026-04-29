"""Top-level CLI for the data layer."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    daily = subparsers.add_parser("daily", help="Run the data-layer daily pipeline.")
    daily.add_argument("--as-of", dest="as_of", help="Trade date to process, defaults to latest quotes.")

    universe = subparsers.add_parser("universe", help="Manage m_pool and a_pool universes.")
    universe.add_argument("args", nargs=argparse.REMAINDER)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "daily":
        parser.error("daily pipeline is not implemented yet")
    if args.command == "universe":
        from usstock_data.universe.cli import main as universe_main

        return universe_main(args.args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
