"""Top-level CLI for the analytics layer."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="usstock-analytics")
    parser.add_argument("command", choices=["signals", "backtest"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    parser.parse_args(argv)
    parser.error("analytics commands are not implemented yet")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
