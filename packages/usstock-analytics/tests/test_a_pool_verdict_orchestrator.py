from __future__ import annotations

import time
from datetime import date

from usstock_analytics.a_pool.orchestrator import build_daily_row
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
        return "NVDA A 池信号偏积极，主题仍在高位，回撤入场条件部分满足；继续观察止损锚和目标市值反推价格。"


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
