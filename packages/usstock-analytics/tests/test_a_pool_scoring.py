from __future__ import annotations

from datetime import date

from usstock_analytics.a_pool.scoring import score_a_pool
from usstock_analytics.a_pool.signals.models import APoolSnapshot


def snap(**kwargs) -> APoolSnapshot:
    base = {
        "symbol": "NVDA",
        "date": date(2026, 4, 30),
        "close": 100,
        "rsi14": 45,
        "drawdown_60d": -0.10,
        "trendline_5y": 110,
        "mean_20d": 105,
        "std_20d": 5,
        "ret_60d": 20,
        "shares_outstanding": 10_000_000_000,
        "thesis_stop_mcap_b": 800,
        "target_mcap_b": 1400,
        "theme_quintile": "mid",
    }
    base.update(kwargs)
    return APoolSnapshot(**base)


def test_scoring_three_dimensions_sum_to_100() -> None:
    result = score_a_pool(snap(close=100, trendline_5y=100, std_20d=0), {})
    expected = (
        result.score_breakdown["elasticity"] * 0.35
        + result.score_breakdown["value"] * 0.30
        + result.score_breakdown["rr"] * 0.35
        + result.score_breakdown["theme_bonus"]
    )
    assert result.a_score == round(expected, 2)


def test_scoring_uses_mcap_reverse_for_rr_not_price_target() -> None:
    result = score_a_pool(snap(thesis_stop_mcap_b=900, target_mcap_b=1300), {})
    assert result.thesis_stop_price == 90
    assert result.target_price == 130
    assert result.score_breakdown["rr"] == 75


def test_theme_bonus_top_quintile_adds_5() -> None:
    base = score_a_pool(snap(theme_quintile="mid"), {})
    boosted = score_a_pool(snap(theme_quintile="top"), {})
    assert boosted.score_breakdown["theme_bonus"] == 5
    assert boosted.a_score == base.a_score + 5


def test_theme_bonus_bottom_oversold_adds_3() -> None:
    signals = {"theme_oversold_entry": {"triggered": True}}
    result = score_a_pool(snap(theme_quintile="bottom"), signals)
    assert result.score_breakdown["theme_bonus"] == 3
