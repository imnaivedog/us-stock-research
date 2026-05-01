from __future__ import annotations

import time
from datetime import date, timedelta

import pandas as pd
from usstock_analytics.a_pool import orchestrator
from usstock_analytics.a_pool.orchestrator import (
    bottom_streak,
    build_daily_row,
    load_theme_history,
    run,
    snapshot_from_history,
)
from usstock_analytics.a_pool.signals.models import APoolSnapshot, Calibration
from usstock_analytics.a_pool.verdict import generate_verdict


class SlowClient:
    def generate_content(self, prompt: str) -> str:
        time.sleep(0.2)
        return prompt


class QuotaClient:
    def generate_content(self, prompt: str) -> str:
        raise RuntimeError("quota exceeded")


class SuccessClient:
    def generate_content(self, prompt: str) -> str:
        return (
            "NVDA A 池信号偏积极，主题仍在高位，"
            "回撤入场条件部分满足；继续观察止损锚和目标市值反推价格。"
        )


def snap(**kwargs) -> APoolSnapshot:
    base = {
        "symbol": "NVDA",
        "date": date(2026, 4, 30),
        "close": 100,
        "rsi14": 29,
        "drawdown_60d": -0.25,
        "trendline_5y": 120,
        "mean_20d": 120,
        "std_20d": 10,
        "ret_60d": 20,
        "shares_outstanding": 10_000_000_000,
        "thesis_stop_mcap_b": 800,
        "target_mcap_b": 1400,
        "theme_quintile": "top",
        "open": 98,
        "prev_close": 99,
        "volume": 2_000_000,
        "avg_volume_20d": 1_000_000,
        "sma_20": 100,
        "sma_50": 105,
        "sma_200": 90,
        "prev_sma_20": 106,
        "prev_sma_50": 105,
        "prev_sma_200": 110,
        "macd_line": 1.1,
        "macd_signal": 1.0,
        "prev_macd_line": 0.9,
        "prev_macd_signal": 1.0,
        "days_since_previous_macd_cross": 70,
        "rolling_high_60": 100,
        "rolling_low_20": 98,
        "rolling_low_60": 95,
        "max_rsi_60": 80,
        "rsi14_history": (81, 82, 83),
        "thesis_age_days": 365 * 4,
        "recent_b5_support": True,
    }
    base.update(kwargs)
    return APoolSnapshot(**base)


CAL = Calibration(rsi14_p20=30, rsi14_p80=70, drawdown_p10=-0.20)


def test_verdict_falls_back_to_skeleton_on_llm_timeout() -> None:
    result = generate_verdict(
        symbol="NVDA",
        signals={"b1": {"triggered": True, "strength": 0.5}},
        score=42,
        score_breakdown={},
        thesis_stop_price=80,
        target_price=140,
        client=SlowClient(),
        timeout_s=0.01,
    )
    assert result.source == "fallback"
    assert result.error == "llm_timeout"
    assert "【NVDA】A_Score=42.00" in result.text


def test_verdict_falls_back_on_quota_exceeded() -> None:
    result = generate_verdict(
        symbol="NVDA",
        signals={},
        score=10,
        score_breakdown={},
        client=QuotaClient(),
    )
    assert result.source == "fallback"
    assert result.error == "RuntimeError"


def test_orchestrator_writes_hold_on_null_shares_outstanding() -> None:
    row = build_daily_row(snapshot=snap(shares_outstanding=None), calibration=CAL)
    assert row["signals"]["hold"]["reason"] == "shares_outstanding_null"
    assert row["a_score"] == 0
    assert row["verdict_source"] == "fallback"


def test_orchestrator_full_pipeline_smoke() -> None:
    row = build_daily_row(snapshot=snap(), calibration=CAL, llm_client=SuccessClient())
    assert row["symbol"] == "NVDA"
    assert row["signals"]["b1"]["triggered"] is True
    assert row["a_score"] > 0
    assert row["verdict_source"] == "llm"
    assert row["thesis_stop_price"] == 80
    assert row["target_price"] == 140


class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, query, params):
        return self

    def all(self):
        return self.rows


class FakeEngine:
    def __init__(self, rows):
        self.conn = FakeConn(rows)

    def begin(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, traceback):
        return False


def history_frame(days: int = 61) -> pd.DataFrame:
    start = date(2026, 3, 1)
    return pd.DataFrame(
        {
            "symbol": ["NVDA"] * days,
            "trade_date": [start + timedelta(days=idx) for idx in range(days)],
            "open": [121.0] * (days - 1) + [98.0],
            "high": [122.0] * (days - 1) + [101.0],
            "low": [119.0] * (days - 1) + [98.0],
            "close": [120.0] * (days - 1) + [100.0],
            "volume": [1_000_000] * (days - 1) + [2_000_000],
            "rsi_14": [29.0] * days,
            "sma_20": [120.0] * days,
            "sma_50": [120.0] * days,
            "sma_200": [120.0] * days,
            "macd_line": [0.8] * (days - 1) + [1.1],
            "macd_signal": [1.0] * days,
        }
    )


def test_snapshot_from_theme_history_computes_quintile_prev_correctly() -> None:
    trade_date = date(2026, 4, 30)
    rows = [
        (trade_date, "theme_ai_compute", "top"),
        (trade_date - timedelta(days=1), "theme_ai_compute", "mid"),
    ]
    data = load_theme_history(
        FakeEngine(rows),
        trade_date,
        [{"symbol": "NVDA", "themes": ["theme_ai_compute"]}],
    )
    snapshot = snapshot_from_history(
        entry={"symbol": "NVDA", "thesis_stop_mcap_b": 800, "target_mcap_b": 1400},
        history=history_frame(),
        shares_outstanding=10_000_000_000,
        theme_quintile=data["NVDA"]["quintile"],
        theme_quintile_prev=data["NVDA"]["quintile_prev"],
    )
    assert snapshot.theme_quintile == "top"
    assert snapshot.theme_quintile_prev == "mid"


def test_snapshot_computes_bottom_days_consecutive() -> None:
    trade_date = date(2026, 4, 30)
    rows = [(trade_date - timedelta(days=idx), "bottom") for idx in range(22)]
    rows.append((trade_date - timedelta(days=22), "lower"))
    assert bottom_streak(rows) == 22


def test_b4_signal_triggered_on_fresh_macd_cross() -> None:
    row = build_daily_row(snapshot=snap(), calibration=CAL)
    assert row["signals"]["b4"]["triggered"] is True


def test_w1_triggered_on_three_day_rsi_overheat() -> None:
    row = build_daily_row(
        snapshot=snap(rsi14_history=(81, 82, 83), rsi14=83),
        calibration=CAL,
    )
    assert row["signals"]["w1"]["triggered"] is True


def test_w2_triggered_on_thesis_aging() -> None:
    row = build_daily_row(snapshot=snap(thesis_age_days=365 * 4, close=60), calibration=CAL)
    assert row["signals"]["w2"]["triggered"] is True


def test_s2b_triggered_on_slow_death_cross() -> None:
    row = build_daily_row(
        snapshot=snap(prev_sma_50=121, prev_sma_200=120, sma_50=119, sma_200=120),
        calibration=CAL,
    )
    assert row["signals"]["s2b"]["triggered"] is True


def test_orchestrator_end_to_end_4_signals_active(monkeypatch) -> None:
    written_rows = []

    monkeypatch.setattr(
        orchestrator,
        "load_a_pool_entries",
        lambda path, symbols: [
            {
                "symbol": "NVDA",
                "themes": ["theme_ai_compute"],
                "thesis_stop_mcap_b": 800,
                "target_mcap_b": 1400,
            }
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "load_symbol_metadata",
        lambda engine, symbols: {
                "NVDA": {
                    "shares_outstanding": 10_000_000_000,
                    "rsi14_p5": 30,
                    "rsi14_p20": 30,
                    "rsi14_p80": 70,
                    "rsi14_p95": 80,
                    "drawdown_p10": -0.2,
                }
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "load_history",
        lambda engine, symbols, trade_date: history_frame(),
    )
    monkeypatch.setattr(
        orchestrator,
        "load_theme_history",
        lambda engine, trade_date, entries: {
            "NVDA": {"quintile": "bottom", "quintile_prev": "top", "bottom_days": 21}
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "load_recent_earnings",
        lambda engine, symbols, trade_date: {"NVDA": {"days_since": 5, "drop_pct": -7}},
    )
    monkeypatch.setattr(
        orchestrator,
        "load_corporate_action_flags",
        lambda engine, symbols, trade_date: {"NVDA": ["split"]},
    )
    monkeypatch.setattr(orchestrator, "write_alert", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        orchestrator,
        "upsert_rows",
        lambda engine, rows: written_rows.extend(rows) or len(rows),
    )

    assert run(trade_date=date(2026, 4, 30), engine=object()) == 1
    signals = written_rows[0]["signals"]
    assert signals["b3"]["triggered"] is True
    assert signals["b5"]["triggered"] is True
    assert signals["w1"]["triggered"] is False
    assert signals["theme_oversold_entry"]["triggered"] is False
