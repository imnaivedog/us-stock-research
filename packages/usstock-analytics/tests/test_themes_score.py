from __future__ import annotations

import pandas as pd
from usstock_analytics.themes.rank import assign_ranks
from usstock_analytics.themes.score import member_returns, score_theme, weighted_theme_score


def test_theme_score_weights_5d_20d_60d_correctly() -> None:
    assert weighted_theme_score({"ret_5d": 10, "ret_20d": 20, "ret_60d": 30}) == 21


def test_theme_quintile_split_handles_ties_deterministically() -> None:
    rows = [{"theme_id": f"t{i}", "raw_score": 1, "member_count": 5} for i in range(10)]
    ranked = assign_ranks(rows)
    assert [row["theme_id"] for row in ranked[:3]] == ["t0", "t1", "t2"]
    assert ranked[0]["quintile"] == "top"
    assert ranked[-1]["quintile"] == "bottom"


def test_theme_score_skips_themes_with_lt_5_members_with_warn() -> None:
    returns = pd.DataFrame(
        [
            {"symbol": "A", "ret_5d": 1, "ret_20d": 1, "ret_60d": 1},
            {"symbol": "B", "ret_5d": 1, "ret_20d": 1, "ret_60d": 1},
        ]
    )
    assert score_theme("theme_small", ["A", "B"], returns, {}, 5) is None


def test_member_returns_computes_windows() -> None:
    prices = pd.DataFrame(
        [{"symbol": "A", "trade_date": f"2026-01-{day:02d}", "close": day} for day in range(1, 31)]
    )
    returns = member_returns(prices, pd.Timestamp("2026-01-30").date())
    assert round(float(returns.iloc[0]["ret_5d"]), 2) == 20.0
