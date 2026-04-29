from __future__ import annotations

from usstock_analytics.mcp import server


def test_mcp_exposes_exactly_four_tools() -> None:
    tool_names = {
        "get_dial",
        "get_top_themes",
        "get_top_stocks",
        "query_signals",
    }
    registered = set(server.mcp._tool_manager._tools)
    assert tool_names <= registered
    assert "get_breadth" not in registered
    assert "list_alerts" not in registered
    assert "get_a_pool_thesis" not in registered
