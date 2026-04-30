from __future__ import annotations

from usstock_reports.notion.page_writer import render_a_pool_highlights, render_daily_markdown

EXPECTED_MARKDOWN = """## Dial
- 档位: A · Risk-on
- 连续天数: 3
- 是否切换: False

## Breadth
- Breadth Score: 76
- >200MA: 58.20%
- >50MA: 63.10%
- >20MA: 61.40%
- NH/NL: 1.80
- McClellan: 42.50
- Alerts: ZWEIG_BREADTH_THRUST

## Sector
- XLK · rank 1 · score 91.20 · LEADING
- XLF · rank 2 · score 84.40 · STRONG

## Theme
- AI Compute · rank 1 · score 88.50 · ACCELERATING
- Semiconductors · rank 2 · score 82.10 · LAUNCHING

## Stock
- NVDA · rank 1 · score 94 · PULLBACK
- MSFT · rank 2 · score 89.50 · BREAKOUT

## A 池 Highlights
### 🎯 NVDA · A_Score 85
> 英伟达 A 池信号积极，算力主题仍在 top 分位，适合继续观察分批入场。
- 入场 (中) $95.00 · 入场 (深) $88.00
- 止损 (浅) $82.00 · 止损 (深) $76.00
- 短目标 $125.00 · 战略 R:R 3.25
- 触发链 b1, b5, theme_oversold_entry · theme_quintile=top
### 🎯 AMD · A_Score 72
> AMD 回撤后性价比改善，但相对强度仍弱于 NVDA，适合小仓观察。
- 入场 (中) $105.00 · 入场 (深) $98.00
- 止损 (浅) $91.00 · 止损 (深) $86.00
- 短目标 $132.00 · 战略 R:R 2.40
- 触发链 b1

## Macro
- Macro State: risk_on
- As Of: 2026-04-30"""


def test_page_writer_snapshot_includes_a_pool_highlights(sample_report) -> None:
    assert render_daily_markdown(sample_report) == EXPECTED_MARKDOWN


def test_a_pool_highlights_hidden_when_no_score_ge_70(sample_report) -> None:
    report = {
        **sample_report,
        "a_pool": [{**row, "a_score": 69} for row in sample_report["a_pool"]],
    }
    assert render_a_pool_highlights(report) == ""
    assert "A 池 Highlights" not in render_daily_markdown(report)


def test_a_pool_highlights_three_rows_sorted_desc(sample_report) -> None:
    report = {**sample_report}
    report["a_pool"] = [
        {**sample_report["a_pool"][0], "a_score": 85},
        {**sample_report["a_pool"][1], "a_score": 72},
        {**sample_report["a_pool"][2], "a_score": 95},
    ]
    markdown = render_a_pool_highlights(report)
    first = markdown.index("### 🎯 SNOW · A_Score 95")
    second = markdown.index("### 🎯 NVDA · A_Score 85")
    third = markdown.index("### 🎯 AMD · A_Score 72")
    assert first < second < third


def test_a_pool_highlights_preserves_chinese_utf8(sample_report) -> None:
    markdown = render_a_pool_highlights(sample_report)
    assert "英伟达 A 池信号积极" in markdown
    assert "相对强度仍弱于 NVDA" in markdown
