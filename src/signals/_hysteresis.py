from __future__ import annotations

REGIME_ORDER = {"S": 4, "A": 3, "B": 2, "C": 1, "D": 0}


def is_adjacent(left: str | None, right: str | None) -> bool:
    if left not in REGIME_ORDER or right not in REGIME_ORDER:
        return False
    return abs(REGIME_ORDER[left] - REGIME_ORDER[right]) == 1


def apply_hysteresis(
    prev_regime: str | None,
    prev_streak: int,
    candidate_regime: str,
    days_since_left_s: int,
    vix_jump_pct: float | None,
    params: dict,
) -> str:
    if prev_regime is None or prev_regime == candidate_regime:
        return candidate_regime

    regime_params = params["l1_regime"]
    jump_threshold = regime_params["jump_exempt_vix_single_day_pct"]
    if vix_jump_pct is not None and vix_jump_pct >= jump_threshold:
        return candidate_regime

    if prev_regime == "S" and candidate_regime != "S":
        return candidate_regime

    if candidate_regime == "S" and prev_regime != "S":
        if days_since_left_s < regime_params["cooldown_a_to_s_days"]:
            return prev_regime

    if is_adjacent(prev_regime, candidate_regime):
        if prev_streak < regime_params["cooldown_adjacent_days"]:
            return prev_regime

    return candidate_regime


def next_streak(prev_regime: str | None, current_regime: str, prev_streak: int) -> int:
    if prev_regime == current_regime:
        return prev_streak + 1
    return 1
