from __future__ import annotations

import sys
from argparse import Namespace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import reconcile_indicators  # noqa: E402


def test_relative_error_uses_epsilon_denominator_for_zero_reference() -> None:
    assert reconcile_indicators.relative_error(1.0, 0.0) == pytest.approx(1_000_000_000.0)


def test_rsi_uses_point_tolerance_not_relative_tolerance() -> None:
    rows = pd.DataFrame(
        {
            "symbol": ["NVDA", "NVDA"],
            "trade_date": [date(2026, 4, 28), date(2026, 4, 29)],
            "rsi_14_ours": [50.0, 51.5],
            "rsi_14_their": [49.0, 50.0],
        }
    )

    result = reconcile_indicators.compare_field(rows, "rsi_14", "NVDA")

    assert result.status == "pass"
    assert result.metric == pytest.approx(1.5)
    assert result.tolerance == pytest.approx(2.0)


def test_atr_uses_relative_tolerance_and_fails_above_two_percent() -> None:
    rows = pd.DataFrame(
        {
            "symbol": ["NVDA"],
            "trade_date": [date(2026, 4, 29)],
            "atr_14_ours": [10.3],
            "atr_14_their": [10.0],
        }
    )

    result = reconcile_indicators.compare_field(rows, "atr_14", "NVDA")

    assert result.status == "fail"
    assert result.metric == pytest.approx(0.03)


def test_obv_passes_on_high_correlation_even_when_scale_differs() -> None:
    rows = pd.DataFrame(
        {
            "symbol": ["NVDA", "NVDA", "NVDA"],
            "trade_date": [date(2026, 4, 27), date(2026, 4, 28), date(2026, 4, 29)],
            "obv_ours": [10, 20, 30],
            "obv_their": [100, 200, 300],
        }
    )

    result = reconcile_indicators.compare_field(rows, "obv", "NVDA")

    assert result.status == "pass"
    assert result.metric == pytest.approx(1.0)


def test_pick_sample_dates_returns_five_evenly_spaced_dates() -> None:
    dates = pd.Series(pd.date_range("2026-04-01", periods=9).date)

    samples = reconcile_indicators.pick_sample_dates(dates, count=5)

    assert samples == [
        date(2026, 4, 1),
        date(2026, 4, 3),
        date(2026, 4, 5),
        date(2026, 4, 7),
        date(2026, 4, 9),
    ]


def test_report_writes_formula_diagnostics_for_wilder_fields(tmp_path: Path) -> None:
    output = tmp_path / "reconcile.md"
    results = [
        reconcile_indicators.FieldResult(
            field="rsi_14",
            symbol="NVDA",
            metric=3.0,
            tolerance=2.0,
            status="fail",
            samples=5,
        )
    ]

    reconcile_indicators.write_report(
        output_path=output,
        results=results,
        samples=pd.DataFrame(),
        symbols=["NVDA"],
        report_date=date(2026, 4, 29),
        ours_source="compute",
        source_note=None,
    )

    report = output.read_text(encoding="utf-8")
    assert "### rsi_14" in report
    assert "Wilder alpha = 1/N" in report
    assert "TradingView 默认" in report


def test_run_reconcile_returns_nonpassing_result_with_compute_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    quotes = pd.DataFrame(
        {
            "symbol": ["NVDA", "SPY"],
            "trade_date": [date(2026, 4, 29), date(2026, 4, 29)],
            "open": [10.0, 20.0],
            "high": [11.0, 21.0],
            "low": [9.0, 19.0],
            "close": [10.0, 20.0],
            "adj_close": [10.0, 20.0],
            "volume": [1000, 2000],
        }
    )
    ours = pd.DataFrame(
        {
            "symbol": ["NVDA"],
            "trade_date": [date(2026, 4, 29)],
            "sma_5": [10.0],
        }
    )
    benchmark = pd.DataFrame(
        {
            "symbol": ["NVDA"],
            "trade_date": [date(2026, 4, 29)],
            "sma_5": [11.0],
        }
    )
    monkeypatch.setattr(
        reconcile_indicators,
        "require_external_modules",
        lambda: (object(), object()),
    )
    monkeypatch.setattr(reconcile_indicators, "download_yfinance_quotes", lambda *_args: quotes)
    monkeypatch.setattr(
        reconcile_indicators,
        "compute_pandas_ta_benchmark",
        lambda *_args: benchmark,
    )
    monkeypatch.setattr(reconcile_indicators, "compute_indicators", lambda *_args: ours)

    result = reconcile_indicators.run_reconcile(
        Namespace(
            symbols="NVDA",
            start="2026-04-28",
            end="2026-04-30",
            output=str(tmp_path / "report.md"),
            ours_source="compute",
            ours_csv=None,
            compare_tail=60,
            warmup_days=30,
        )
    )

    assert result.report_path.exists()
    assert any(item.field == "sma_5" and item.status == "fail" for item in result.results)
