from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import bootstrap_history  # noqa: E402


class _HoldingsClient:
    def __init__(self, row: dict[str, object]):
        self.row = row

    async def get_etf_holdings(self, _etf: str) -> list[dict[str, object]]:
        return [self.row]


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ({"asset": "NAN", "weightPercentage": math.nan}, "nan_weight"),
        ({"asset": "ZERO", "weightPercentage": 0}, "nonpositive_weight"),
        ({"asset": "OVER", "weight": 1.06}, "weight_overflow"),
    ],
)
def test_bad_weight_rows_are_quarantined(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    row: dict[str, object],
    reason: str,
) -> None:
    uploaded: list[tuple[Path, str]] = []
    monkeypatch.setattr(bootstrap_history, "BAD_ROWS_DIR", tmp_path / "bad_rows")
    monkeypatch.setattr(
        bootstrap_history,
        "upload_file",
        lambda local_path, gcs_uri: uploaded.append((Path(local_path), gcs_uri)) or gcs_uri,
    )

    stats = asyncio.run(
        bootstrap_history.process_all_etf_holdings(
            _HoldingsClient(row),
            None,
            tmp_path / "run",
            ["ETF"],
            "2026-04-27",
            {"etf_holdings_latest": []},
            tmp_path / "run" / "_checkpoint.json",
            True,
        )
    )

    assert stats.input_rows == 1
    assert stats.skipped_rows == 1
    assert stats.db_rows == 0
    assert uploaded == [
        (
            tmp_path / "bad_rows" / "etf_holdings" / "2026-04-27.csv",
            "gs://naive-usstock-data/bad_rows/etf_holdings/2026-04-27.csv",
        )
    ]
    assert reason in uploaded[0][0].read_text(encoding="utf-8")
