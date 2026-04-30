from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


class MockNotionClient:
    def __init__(self, existing_page_id: str | None = None) -> None:
        self.existing_page_id = existing_page_id
        self.queries: list[dict[str, Any]] = []
        self.created_pages: list[dict[str, Any]] = []
        self.updated_pages: list[dict[str, Any]] = []
        self.appended_blocks: list[dict[str, Any]] = []

    def query_database(self, **kwargs: Any) -> dict[str, Any]:
        self.queries.append(kwargs)
        if self.existing_page_id:
            return {"results": [{"id": self.existing_page_id}]}
        return {"results": []}

    def create_page(self, **kwargs: Any) -> dict[str, Any]:
        self.created_pages.append(kwargs)
        return {"id": "new-page-id"}

    def update_page(self, **kwargs: Any) -> dict[str, Any]:
        self.updated_pages.append(kwargs)
        return {"id": kwargs["page_id"]}

    def append_blocks(self, **kwargs: Any) -> dict[str, Any]:
        self.appended_blocks.append(kwargs)
        return {"results": kwargs.get("children", [])}


@pytest.fixture
def mock_notion_client() -> MockNotionClient:
    return MockNotionClient()


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_report(fixtures_dir: Path) -> dict[str, Any]:
    m_pool = json.loads((fixtures_dir / "signals_m_pool_sample.json").read_text(encoding="utf-8"))
    a_pool = json.loads((fixtures_dir / "signals_a_pool_sample.json").read_text(encoding="utf-8"))
    return {**m_pool, "a_pool": a_pool}
