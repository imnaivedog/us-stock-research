"""Top-level CLI for the reports layer."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="usstock-reports")
    parser.add_argument("command", choices=["daily"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    parser.parse_args(argv)
    parser.error("reports commands are not implemented yet")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
