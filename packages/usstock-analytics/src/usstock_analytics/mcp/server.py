"""MCP server exposing raw analytics query tools."""

from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

from usstock_analytics.db import create_postgres_engine
from usstock_analytics.queries import core

mcp = FastMCP("usstock-analytics")


def _date(value: str) -> date:
    return date.fromisoformat(value)


@mcp.tool()
def get_dial(date: str) -> dict[str, Any]:
    """Return dial, macro, and breadth summary data for one date."""
    return core.get_dial(create_postgres_engine(), _date(date))


@mcp.tool()
def get_top_themes(date: str, n: int = 3) -> list[dict[str, Any]]:
    """Return top theme rows for one date."""
    return core.get_top_themes(create_postgres_engine(), _date(date), n=n)


@mcp.tool()
def get_top_stocks(date: str, n: int = 5, pool: str = "m") -> list[dict[str, Any]]:
    """Return top stock rows for one date and pool."""
    return core.get_top_stocks(create_postgres_engine(), _date(date), n=n, pool=pool)


@mcp.tool()
def query_signals(
    date_range: dict[str, str],
    filter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return raw signal rows for a date range."""
    start = _date(date_range["start"])
    end = _date(date_range["end"])
    return core.query_signals(create_postgres_engine(), start, end, filters=filter)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
