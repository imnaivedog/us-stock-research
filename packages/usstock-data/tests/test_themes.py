from __future__ import annotations

import pandas as pd
import pytest
from usstock_data.themes.generate import generate_from_holdings
from usstock_data.themes.sync import sync_preview
from usstock_data.themes.validate import ThemeValidationError, validate_a_pool_references


def test_themes_generate_from_etf_holdings_dedupes_members() -> None:
    payload = generate_from_holdings(
        pd.DataFrame(
            [
                {"etf_code": "SMH", "symbol": "NVDA", "weight": 0.2},
                {"etf_code": "SOXX", "symbol": "NVDA", "weight": 0.1},
            ]
        )
    )
    ai = next(theme for theme in payload["themes"] if theme["theme_id"] == "theme_ai_compute")
    assert ai["members"] == [{"symbol": "NVDA", "weight": 0.15, "source_etfs": ["SMH", "SOXX"]}]


def test_themes_sync_is_idempotent(tmp_path) -> None:
    themes = tmp_path / "themes.yaml"
    themes.write_text(
        """
themes:
  - theme_id: theme_ai_compute
    name_cn: AI 算力
    name_en: AI Compute
    members:
      - {symbol: NVDA, weight: 0.18}
""",
        encoding="utf-8",
    )
    assert sync_preview(themes) == sync_preview(themes)


def test_themes_validate_fails_on_unknown_theme_in_a_pool(tmp_path) -> None:
    themes = tmp_path / "themes.yaml"
    a_pool = tmp_path / "a_pool.yaml"
    themes.write_text(
        "themes:\n  - {theme_id: theme_ai_compute, name_cn: AI, name_en: AI}\n",
        encoding="utf-8",
    )
    a_pool.write_text(
        "- {symbol: NVDA, themes: [theme_missing]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ThemeValidationError, match="theme_missing"):
        validate_a_pool_references(a_pool, themes)
