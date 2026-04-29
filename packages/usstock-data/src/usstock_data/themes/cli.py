"""CLI for theme dictionary tooling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from usstock_data.themes.generate import generate
from usstock_data.themes.sync import sync
from usstock_data.themes.validate import THEMES_PATH, load_theme_payload, validate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-data themes")
    sub = parser.add_subparsers(dest="command", required=True)
    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--output", type=Path, default=THEMES_PATH)
    sub.add_parser("sync")
    sub.add_parser("validate")
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--theme")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        payload = generate(args.output)
        print(json.dumps({"themes": len(payload.get("themes", []))}, ensure_ascii=False))
        return 0
    if args.command == "sync":
        print(json.dumps(sync(), ensure_ascii=False))
        return 0
    if args.command == "validate":
        validate()
        print("ok")
        return 0
    if args.command == "list":
        payload = load_theme_payload()
        themes = payload.get("themes", [])
        if args.theme:
            themes = [theme for theme in themes if theme.get("theme_id") == args.theme]
        print(json.dumps(themes, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
