"""Thin Notion client wrapper with bounded retry."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from notion_client import APIResponseError, Client


class NotionConfigError(RuntimeError):
    pass


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise NotionConfigError(f"{name} is required")
    return value


class RetryingNotionClient:
    def __init__(self, client: Client, max_attempts: int = 3, base_sleep_s: float = 0.5) -> None:
        self._client = client
        self.max_attempts = max_attempts
        self.base_sleep_s = base_sleep_s

    @classmethod
    def from_env(cls) -> RetryingNotionClient:
        return cls(Client(auth=require_env("NOTION_TOKEN")))

    def _call(self, fn: Callable[..., Any], **kwargs: Any) -> Any:
        attempt = 0
        while True:
            attempt += 1
            try:
                return fn(**kwargs)
            except APIResponseError as exc:
                status = getattr(exc, "status", 0) or 0
                if status < 500 or attempt >= self.max_attempts:
                    raise
                time.sleep(self.base_sleep_s * (2 ** (attempt - 1)))

    def query_database(self, **kwargs: Any) -> Any:
        return self._call(self._client.databases.query, **kwargs)

    def create_page(self, **kwargs: Any) -> Any:
        return self._call(self._client.pages.create, **kwargs)

    def update_page(self, **kwargs: Any) -> Any:
        return self._call(self._client.pages.update, **kwargs)

    def append_blocks(self, **kwargs: Any) -> Any:
        return self._call(self._client.blocks.children.append, **kwargs)


def daily_database_id() -> str:
    return require_env("NOTION_DAILY_DB_ID")
