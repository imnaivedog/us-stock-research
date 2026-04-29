"""Top-level CLI for the analytics layer."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="usstock-analytics")
    parser.add_argument("command", choices=["signals", "backtest", "themes-score", "a-pool"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == "signals":
        from usstock_analytics.signals.m_pool.orchestrate import main as signals_main

        return signals_main(args.args)
    if args.command == "backtest":
        from usstock_analytics.backtest.cli import main as backtest_main

        return backtest_main(args.args)
    if args.command == "themes-score":
        from usstock_analytics.themes.score import main as themes_score_main

        return themes_score_main(args.args)
    if args.command == "a-pool":
        from usstock_analytics.a_pool.cli import main as a_pool_main

        return a_pool_main(args.args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
