from __future__ import annotations

import csv
from datetime import date

from usstock_analytics.backtest.cli import create_run, parse_params, write_placeholder_report
from usstock_analytics.signals.a_pool.placeholder import available_signals


def test_backtest_scaffold_writes_isolated_csv(tmp_path) -> None:
    run = create_run(date(2025, 1, 1), date(2025, 1, 3), {"risk": 1}, tmp_path)
    write_placeholder_report(run)
    with run.output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["status"] == "scaffold"
    assert rows[0]["params_json"] == '{"risk": 1}'


def test_a_pool_scaffold_is_empty() -> None:
    assert available_signals() == []


def test_parse_params_requires_object() -> None:
    assert parse_params('{"a": 1}') == {"a": 1}
