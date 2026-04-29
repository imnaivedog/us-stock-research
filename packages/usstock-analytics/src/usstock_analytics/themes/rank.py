"""Theme rank and quintile helpers."""

from __future__ import annotations

from typing import Any

QUINTILES = ["top", "upper", "mid", "lower", "bottom"]


def assign_ranks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: (-float(row["raw_score"]), str(row["theme_id"])))
    total = len(ranked)
    output = []
    for idx, row in enumerate(ranked, start=1):
        bucket = min(4, int((idx - 1) * 5 / max(total, 1)))
        output.append({**row, "rank": idx, "quintile": QUINTILES[bucket]})
    return output
