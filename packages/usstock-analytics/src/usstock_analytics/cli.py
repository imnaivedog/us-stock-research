"""Top-level CLI for the analytics layer."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="usstock-analytics")
    parser.add_argument("command", choices=["signals", "backtest"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == "signals":
        from usstock_analytics.signals.m_pool.orchestrate import main as signals_main

        return signals_main(args.args)
    parser.error("backtest command is not implemented yet")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
