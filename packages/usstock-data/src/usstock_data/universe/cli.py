"""CLI entry point for universe management."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-data universe")
    parser.add_argument("command", choices=["list", "show", "sync", "add", "remove", "set-target"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.error("universe commands are not implemented yet")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
