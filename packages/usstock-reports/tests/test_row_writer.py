from __future__ import annotations

from usstock_reports.notion.row_writer import build_properties, upsert_daily_row


def test_row_writer_builds_complete_typed_properties(sample_report) -> None:
    properties = build_properties(sample_report)

    assert properties["Name"]["title"][0]["text"]["content"] == "US Stock Research · 2026-04-30"
    assert properties["Date"] == {"date": {"start": "2026-04-30"}}
    assert properties["Dial"] == {"select": {"name": "A · Risk-on"}}
    assert properties["Regime"] == {"select": {"name": "A"}}
    assert properties["Position"] == {"number": 0.8}
    assert properties["Breadth Score"] == {"number": 76.0}
    assert properties["Macro State"] == {"select": {"name": "risk_on"}}
    assert properties["Alerts"] == {"number": 1.0}
    assert properties["A Pool Highlights"] == {"number": 2.0}
    assert properties["Top Sectors"]["rich_text"][0]["text"]["content"] == "XLK, XLF"
    assert properties["Top Themes"]["rich_text"][0]["text"]["content"] == (
        "AI Compute, Semiconductors"
    )
    assert properties["Top Stocks"]["rich_text"][0]["text"]["content"] == "NVDA, MSFT"


def test_row_writer_upserts_existing_page(sample_report, mock_notion_client) -> None:
    mock_notion_client.existing_page_id = "existing-page"
    page_id = upsert_daily_row(mock_notion_client, sample_report, database_id="daily-db")

    assert page_id == "existing-page"
    assert not mock_notion_client.created_pages
    assert mock_notion_client.updated_pages[0]["page_id"] == "existing-page"
    assert mock_notion_client.updated_pages[0]["properties"]["Date"]["date"]["start"] == (
        "2026-04-30"
    )


def test_row_writer_creates_missing_page(sample_report, mock_notion_client) -> None:
    page_id = upsert_daily_row(mock_notion_client, sample_report, database_id="daily-db")

    assert page_id == "new-page-id"
    assert mock_notion_client.created_pages[0]["parent"] == {"database_id": "daily-db"}
