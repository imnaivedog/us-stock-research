from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.signals._params import load_params  # noqa: E402
from src.signals.breadth import (  # noqa: E402
    detect_alerts,
    enrich_breadth_history,
    mcclellan_normalized,
    nh_nl_normalized,
    percentile_rank,
    row_for_date,
)


def load_fixture_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv("tests/fixtures/breadth_1y.csv", parse_dates=["trade_date"]),
        pd.read_csv("tests/fixtures/spy_1y.csv", parse_dates=["trade_date"]),
    )


def test_percentile_rank_uses_observed_history() -> None:
    assert percentile_rank(pd.Series([10, 20, 30, 40]), 30) == 75


def test_nh_nl_normalized_maps_one_to_midpoint() -> None:
    assert nh_nl_normalized(1.0) == 50
    assert nh_nl_normalized(5.0) > 90


def test_mcclellan_normalized_clamps_to_range() -> None:
    assert mcclellan_normalized(0) == 50
    assert mcclellan_normalized(200) == 100
    assert mcclellan_normalized(-200) == 0


def test_enrich_breadth_history_adds_percentiles_and_score() -> None:
    breadth, _ = load_fixture_frames()
    enriched = enrich_breadth_history(breadth, load_params())
    row = row_for_date(enriched, date.fromisoformat("2025-09-02"))
    assert 0 <= row.pct_above_200ma_p5y <= 100
    assert 0 <= row.pct_above_50ma_p2y <= 100
    assert 0 <= row.score <= 100


def test_detects_nh_nl_and_mcclellan_extremes() -> None:
    breadth, spy = load_fixture_frames()
    params = load_params()
    enriched = enrich_breadth_history(breadth, params)
    alerts = detect_alerts(enriched, spy, date.fromisoformat("2025-09-02"), params)
    alert_types = {alert.alert_type for alert in alerts}
    assert "NH_NL_EXTREME" in alert_types
    assert "MCCLELLAN_EXTREME" in alert_types


def test_detects_50ma_extreme_red() -> None:
    breadth, spy = load_fixture_frames()
    params = load_params()
    enriched = enrich_breadth_history(breadth, params)
    alerts = detect_alerts(enriched, spy, date.fromisoformat("2025-09-10"), params)
    assert any(
        alert.alert_type == "BREADTH_50MA_EXTREME" and alert.severity == "RED"
        for alert in alerts
    )


def test_detects_200ma_low_red_in_selloff() -> None:
    breadth, spy = load_fixture_frames()
    params = load_params()
    enriched = enrich_breadth_history(breadth, params)
    alerts = detect_alerts(enriched, spy, date.fromisoformat("2025-12-01"), params)
    assert any(
        alert.alert_type == "BREADTH_200MA_LOW" and alert.severity == "RED"
        for alert in alerts
    )


def test_fixture_does_not_trigger_zweig() -> None:
    breadth, spy = load_fixture_frames()
    params = load_params()
    enriched = enrich_breadth_history(breadth, params)
    all_alerts = []
    for trade_date in pd.to_datetime(enriched["trade_date"]).dt.date:
        all_alerts.extend(detect_alerts(enriched, spy, trade_date, params))
    assert not any(alert.alert_type == "ZWEIG_BREADTH_THRUST" for alert in all_alerts)
