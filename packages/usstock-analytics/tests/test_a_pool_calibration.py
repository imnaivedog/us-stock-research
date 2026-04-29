from __future__ import annotations

import pandas as pd
from usstock_analytics.a_pool.calibration import compute_calibration


def test_calibration_quantiles_handle_short_history_with_skip() -> None:
    history = pd.DataFrame(
        [
            {"trade_date": f"2026-01-{day:02d}", "close": day, "volume": 100, "rsi_14": 50}
            for day in range(1, 10)
        ]
    )
    spy = pd.DataFrame(
        [{"trade_date": f"2026-01-{day:02d}", "close": day} for day in range(1, 10)]
    )
    assert compute_calibration("NVDA", history, spy) is None
