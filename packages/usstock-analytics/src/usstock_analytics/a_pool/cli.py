"""A-pool analytics CLI."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-analytics a-pool")
    sub = parser.add_subparsers(dest="command", required=True)
    calibrate = sub.add_parser("calibrate")
    calibrate.add_argument("--symbols")
    calibrate.add_argument("--all", action="store_true")
    signals = sub.add_parser("signals")
    signals.add_argument("--date", required=True)
    signals.add_argument("--symbols")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "calibrate":
        from usstock_analytics.a_pool.calibration import main as calibrate_main

        forwarded = []
        if args.symbols:
            forwarded.extend(["--symbols", args.symbols])
        if args.all:
            forwarded.append("--all")
        return calibrate_main(forwarded)
    if args.command == "signals":
        from usstock_analytics.a_pool.orchestrator import main as signals_main

        forwarded = ["--date", args.date]
        if args.symbols:
            forwarded.extend(["--symbols", args.symbols])
        return signals_main(forwarded)
    return 2
