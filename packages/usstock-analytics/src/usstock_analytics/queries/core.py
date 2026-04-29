"""Raw structured query helpers shared by CLI and MCP."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _to_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def get_dial(engine: Engine, trade_date: date) -> dict[str, Any]:
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    """
                SELECT trade_date, regime, regime_streak, regime_prev, regime_changed,
                       macro_state, breadth_pct_above_200ma, breadth_pct_above_50ma,
                       breadth_pct_above_20ma, breadth_nh_nl_ratio, breadth_mcclellan,
                       breadth_score, sectors_top3, themes_top3
                FROM signals_daily
                WHERE trade_date = :trade_date
                """
                ),
                {"trade_date": trade_date},
            )
            .mappings()
            .first()
        )
    return _to_dict(row)


def get_top_themes(engine: Engine, trade_date: date, n: int = 3) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = (
            conn.execute(
                text(
                    """
                SELECT trade_date, theme_id, theme_name, state, rank, total_score,
                       volume_ratio_3m, volume_pct_1y, volume_alert,
                       core_avg_change_pct, diffusion_avg_change_pct
                FROM signals_themes_daily
                WHERE trade_date = :trade_date
                ORDER BY rank ASC, total_score DESC
                LIMIT :limit
                """
                ),
                {"trade_date": trade_date, "limit": n},
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def get_top_stocks(
    engine: Engine,
    trade_date: date,
    n: int = 5,
    pool: str = "m",
) -> list[dict[str, Any]]:
    pool_filter = "" if pool == "all" else "AND COALESCE(u.pool, 'm') = :pool"
    with engine.begin() as conn:
        rows = (
            conn.execute(
                text(
                    f"""
                SELECT s.trade_date, s.symbol, s.total_score, s.technical_score,
                       s.fundamental_score, s.theme_bonus, s.sector_multiplier,
                       s.rank, s.is_top5, s.entry_pattern, s.primary_sector,
                       s.primary_theme, COALESCE(u.pool, 'm') AS pool
                FROM signals_stocks_daily s
                LEFT JOIN symbol_universe u ON u.symbol = s.symbol
                WHERE s.trade_date = :trade_date
                  {pool_filter}
                ORDER BY s.rank ASC, s.total_score DESC
                LIMIT :limit
                """
                ),
                {"trade_date": trade_date, "limit": n, "pool": pool},
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def query_signals(
    engine: Engine,
    start: date,
    end: date,
    filters: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    filters = filters or {}
    include = set(filters.get("tables") or ["daily", "alerts", "sectors", "themes", "stocks"])
    result: dict[str, list[dict[str, Any]]] = {}
    with engine.begin() as conn:
        if "daily" in include:
            result["daily"] = [
                dict(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT *
                        FROM signals_daily
                        WHERE trade_date BETWEEN :start AND :end
                        ORDER BY trade_date
                        """
                    ),
                    {"start": start, "end": end},
                ).mappings()
            ]
        if "alerts" in include:
            result["alerts"] = [
                dict(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT *
                        FROM signals_alerts
                        WHERE trade_date BETWEEN :start AND :end
                        ORDER BY trade_date, alert_type, severity
                        """
                    ),
                    {"start": start, "end": end},
                ).mappings()
            ]
        if "sectors" in include:
            result["sectors"] = [
                dict(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT *
                        FROM signals_sectors_daily
                        WHERE trade_date BETWEEN :start AND :end
                        ORDER BY trade_date, rank_relative
                        """
                    ),
                    {"start": start, "end": end},
                ).mappings()
            ]
        if "themes" in include:
            result["themes"] = [
                dict(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT *
                        FROM signals_themes_daily
                        WHERE trade_date BETWEEN :start AND :end
                        ORDER BY trade_date, rank
                        """
                    ),
                    {"start": start, "end": end},
                ).mappings()
            ]
        if "stocks" in include:
            result["stocks"] = [
                dict(row)
                for row in conn.execute(
                    text(
                        """
                        SELECT *
                        FROM signals_stocks_daily
                        WHERE trade_date BETWEEN :start AND :end
                        ORDER BY trade_date, rank
                        """
                    ),
                    {"start": start, "end": end},
                ).mappings()
            ]
    return result
