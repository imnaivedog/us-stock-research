from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.signals._hysteresis import apply_hysteresis, is_adjacent, next_streak  # noqa: E402
from src.signals._params import load_params  # noqa: E402


def test_adjacent_regime_detection() -> None:
    assert is_adjacent("A", "B")
    assert is_adjacent("C", "D")
    assert not is_adjacent("A", "C")


def test_a_to_s_cooldown_blocks_early_reentry() -> None:
    params = load_params()
    assert (
        apply_hysteresis("A", 10, "S", days_since_left_s=2, vix_jump_pct=0, params=params)
        == "A"
    )


def test_vix_jump_exempts_cooldown() -> None:
    params = load_params()
    assert (
        apply_hysteresis("B", 1, "D", days_since_left_s=999, vix_jump_pct=35, params=params)
        == "D"
    )


def test_next_streak_resets_on_regime_change() -> None:
    assert next_streak("A", "A", 4) == 5
    assert next_streak("A", "B", 4) == 1
