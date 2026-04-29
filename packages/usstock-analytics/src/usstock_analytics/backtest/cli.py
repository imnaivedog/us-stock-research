"""Local backtest CLI scaffold.

Backtest output is intentionally isolated from prod tables per ADR-017.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BacktestRun:
    run_id: str
    start: date
    end: date
    params: dict[str, Any]
    output_path: Path


def parse_params(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("--params must be a JSON object")
    return parsed


def build_run_id(start: date, end: date) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"bt_{start.isoformat()}_{end.isoformat()}_{stamp}"


def write_placeholder_report(run: BacktestRun) -> None:
    run.output_path.parent.mkdir(parents=True, exist_ok=True)
    with run.output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["run_id", "start", "end", "status", "params_json"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "run_id": run.run_id,
                "start": run.start.isoformat(),
                "end": run.end.isoformat(),
                "status": "scaffold",
                "params_json": json.dumps(run.params, sort_keys=True),
            }
        )


def create_run(start: date, end: date, params: dict[str, Any], output_dir: Path) -> BacktestRun:
    if start > end:
        raise ValueError("--start must be <= --end")
    run_id = build_run_id(start, end)
    return BacktestRun(run_id, start, end, params, output_dir / f"{run_id}.csv")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-analytics backtest")
    parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD.")
    parser.add_argument("--end", required=True, help="End date, YYYY-MM-DD.")
    parser.add_argument("--params", help="JSON object with local experiment params.")
    parser.add_argument("--output-dir", default="bt_reports")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run = create_run(
        date.fromisoformat(args.start),
        date.fromisoformat(args.end),
        parse_params(args.params),
        Path(args.output_dir),
    )
    write_placeholder_report(run)
    print(json.dumps({**asdict(run), "output_path": str(run.output_path)}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
