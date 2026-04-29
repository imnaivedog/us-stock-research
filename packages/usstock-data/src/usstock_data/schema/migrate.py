"""Run additive, idempotent schema migrations for V5."""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from usstock_data.db import create_postgres_engine


DDL_PATH = Path(__file__).with_name("ddl.sql")


def run_migration(database_url: str | None = None, ddl_path: Path = DDL_PATH) -> None:
    ddl = ddl_path.read_text(encoding="utf-8")
    engine = create_postgres_engine(database_url)
    logger.info("Running schema migration from {}", ddl_path)
    with engine.begin() as conn:
        conn.exec_driver_sql(ddl)
    logger.info("Schema migration complete")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m usstock_data.schema.migrate")
    parser.add_argument("--database-url", help="Override DATABASE_URL/POSTGRES_* environment config.")
    parser.add_argument("--ddl", type=Path, default=DDL_PATH, help="DDL file to execute.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_migration(database_url=args.database_url, ddl_path=args.ddl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
