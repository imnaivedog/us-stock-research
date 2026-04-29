"""Orchestrate the M-pool signal engine."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_analytics.db import create_postgres_engine
from usstock_analytics.signals.m_pool.breadth import (
    Alert,
    detect_alerts,
    enrich_breadth_history,
    row_for_date,
)
from usstock_analytics.signals.m_pool.dial import RegimeState, evaluate_regime, market_row_for_date
from usstock_analytics.signals.m_pool.macro import (
    compute_macro_state,
    run_macro,
    upsert_macro_state,
)
from usstock_analytics.signals.m_pool.params import load_params
from usstock_analytics.signals.m_pool.sector import (
    SectorSignal,
    compute_sector_signals,
    top_sector_payload,
)
from usstock_analytics.signals.m_pool.stock import StockSignal, compute_stock_signals
from usstock_analytics.signals.m_pool.theme import (
    ThemeSignal,
    compute_theme_signals,
    load_themes,
    top_theme_payload,
)


def max_quotes_trade_date(engine: Engine) -> date:
    with engine.begin() as conn:
        value = conn.execute(text("SELECT MAX(trade_date) FROM quotes_daily")).scalar_one()
    if value is None:
        raise ValueError("quotes_daily has no trade_date rows; cannot resolve target_date")
    return value


def resolve_date_range(args: argparse.Namespace, engine: Engine) -> tuple[date, date, str]:
    as_of = args.as_of or args.date
    if as_of:
        day = date.fromisoformat(as_of)
        return day, day, "arg"
    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
        if start > end:
            raise ValueError("--start must be <= --end")
        return start, end, "arg"
    if args.start or args.end:
        raise ValueError("--start and --end must be provided together")
    target_date = max_quotes_trade_date(engine)
    return target_date, target_date, "max_quotes"


def load_fixture_context(
    fixture_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spy = pd.read_csv(fixture_dir / "spy_1y.csv", parse_dates=["trade_date"])
    breadth = pd.read_csv(fixture_dir / "breadth_1y.csv", parse_dates=["trade_date"])
    vix = pd.read_csv(fixture_dir / "vix_1y.csv", parse_dates=["trade_date"])
    events = pd.read_csv(fixture_dir / "events_calendar.csv", parse_dates=["event_date"])
    sectors = pd.read_csv(fixture_dir / "sectors_1y.csv", parse_dates=["trade_date"])
    stocks = pd.read_csv(fixture_dir / "sp_universe_1y.csv", parse_dates=["trade_date"])
    return spy, breadth, vix, events, sectors, stocks


def load_db_context(
    engine: Engine,
    start: date,
    end: date,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    params = load_params()
    sector_symbols = params["l3_sectors"]["symbols"]
    lookback_start = start - timedelta(days=370)
    spy = pd.read_sql_query(
        text(
            """
            SELECT q.trade_date, q.close, di.sma_20, di.sma_50, di.sma_200
            FROM quotes_daily q
            JOIN daily_indicators di
              ON di.symbol = q.symbol AND di.trade_date = q.trade_date
            WHERE q.symbol = 'SPY'
              AND q.trade_date BETWEEN :lookback_start AND :end
            ORDER BY q.trade_date
            """
        ),
        engine,
        params={"lookback_start": lookback_start, "end": end},
    )
    breadth = pd.read_sql_query(
        text(
            """
            SELECT
              trade_date,
              AVG(CASE WHEN pct_to_200ma > 0 THEN 100.0 ELSE 0.0 END)
                AS breadth_pct_above_200ma,
              AVG(CASE WHEN close_proxy > sma_50 THEN 100.0 ELSE 0.0 END)
                AS breadth_pct_above_50ma,
              AVG(CASE WHEN close_proxy > sma_20 THEN 100.0 ELSE 0.0 END)
                AS breadth_pct_above_20ma,
              GREATEST(SUM(CASE WHEN pct_to_52w_high >= -1 THEN 1 ELSE 0 END)::numeric, 1)
                / GREATEST(SUM(CASE WHEN pct_to_52w_low <= 1 THEN 1 ELSE 0 END)::numeric, 1)
                AS breadth_nh_nl_ratio,
              (AVG(CASE WHEN pct_to_200ma > 0 THEN 100.0 ELSE 0.0 END) - 50.0) * 2.0
                AS breadth_mcclellan
            FROM (
              SELECT
                trade_date,
                pct_to_200ma,
                pct_to_52w_high,
                pct_to_52w_low,
                sma_20,
                sma_50,
                CASE
                  WHEN pct_to_200ma IS NULL OR sma_200 IS NULL THEN NULL
                  ELSE sma_200 * (1 + pct_to_200ma / 100.0)
                END AS close_proxy
              FROM daily_indicators
              WHERE trade_date BETWEEN :lookback_start AND :end
            ) di
            GROUP BY trade_date
            ORDER BY trade_date
            """
        ),
        engine,
        params={"lookback_start": lookback_start, "end": end},
    )
    vix = pd.read_sql_query(
        text(
            """
            SELECT trade_date, vix
            FROM macro_daily
            WHERE trade_date BETWEEN :lookback_start AND :end
            ORDER BY trade_date
            """
        ),
        engine,
        params={"lookback_start": lookback_start, "end": end},
    )
    events = load_events_calendar(engine, start, end)
    sectors = pd.read_sql_query(
        text(
            """
            SELECT q.symbol, q.trade_date, q.open, q.high, q.low, q.close, q.volume,
                   di.sma_20, di.sma_50, di.sma_200, di.std_60, di.obv
            FROM quotes_daily q
            JOIN daily_indicators di
              ON di.symbol = q.symbol AND di.trade_date = q.trade_date
            WHERE q.symbol = ANY(:symbols)
              AND q.trade_date BETWEEN :lookback_start AND :end
            ORDER BY q.symbol, q.trade_date
            """
        ),
        engine,
        params={"symbols": sector_symbols, "lookback_start": lookback_start, "end": end},
    )
    stocks = pd.read_sql_query(
        text(
            """
            SELECT q.symbol, q.trade_date, q.close, q.high, q.volume,
                   di.sma_20, di.sma_50, di.sma_200, di.macd_histogram,
                   di.rsi_14, di.obv, ps.primary_sector
            FROM quotes_daily q
            JOIN daily_indicators di
              ON di.symbol = q.symbol AND di.trade_date = q.trade_date
            JOIN symbol_universe su
              ON su.symbol = q.symbol AND su.is_active = true
            LEFT JOIN (
              SELECT DISTINCT ON (symbol) symbol, etf_code AS primary_sector
              FROM etf_holdings_latest
              WHERE etf_code = ANY(:symbols)
              ORDER BY symbol, weight DESC NULLS LAST, etf_code
            ) ps ON ps.symbol = q.symbol
            WHERE q.trade_date BETWEEN :lookback_start AND :end
            ORDER BY q.symbol, q.trade_date
            """
        ),
        engine,
        params={"symbols": sector_symbols, "lookback_start": lookback_start, "end": end},
    )
    return spy, breadth, vix, events, _enrich_sector_frame(sectors), _enrich_stock_frame(stocks)


def _enrich_sector_frame(sectors: pd.DataFrame) -> pd.DataFrame:
    if sectors.empty:
        return sectors
    df = sectors.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values(["symbol", "trade_date"])
    for column in ("close", "obv"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    grouped = df.groupby("symbol", group_keys=False)
    df["ret_60d"] = grouped["close"].pct_change(60).fillna(0) * 100
    df["obv_20d_chg"] = grouped["obv"].diff(20).fillna(0)
    return df.drop(columns=["obv"])


def _enrich_stock_frame(stocks: pd.DataFrame) -> pd.DataFrame:
    if stocks.empty:
        return stocks
    df = stocks.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values(["symbol", "trade_date"])
    numeric_columns = [
        "close",
        "high",
        "volume",
        "sma_20",
        "sma_50",
        "sma_200",
        "macd_histogram",
        "rsi_14",
        "obv",
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    grouped = df.groupby("symbol", group_keys=False)
    volume_20d = grouped["volume"].transform(lambda item: item.rolling(20, min_periods=1).mean())
    volume_3m = grouped["volume"].transform(lambda item: item.rolling(63, min_periods=1).mean())
    prior_20d_high = grouped["high"].transform(
        lambda item: item.rolling(20, min_periods=1).max().shift(1)
    )
    prev_macd = grouped["macd_histogram"].shift(1)
    df["chg_pct"] = grouped["close"].pct_change().fillna(0) * 100
    df["ret_60d"] = grouped["close"].pct_change(60).fillna(0) * 100
    df["obv_5d_slope"] = grouped["obv"].diff(5).fillna(0)
    df["volume_ratio_20d"] = (df["volume"] / volume_20d).fillna(1)
    df["volume_ratio_20d_3m"] = (volume_20d / volume_3m).fillna(1)
    df["above_50ma"] = df["close"] > df["sma_50"]
    df["is_breakout_20d"] = df["close"] > prior_20d_high.fillna(df["high"])
    df["macd_hist_cross_up"] = (df["macd_histogram"] > 0) & (prev_macd <= 0)
    return df.drop(columns=["high", "obv"])


def load_events_calendar(engine: Engine, start: date, end: date) -> pd.DataFrame:
    try:
        return pd.read_sql_query(
            text(
                """
                SELECT event_date, event_type
                FROM events_calendar
                WHERE event_date BETWEEN :start AND :end
                ORDER BY event_date
                """
            ),
            engine,
            params={"start": start, "end": end + timedelta(days=10)},
        )
    except Exception:
        logger.warning("events_calendar table unavailable; treating event window as empty")
        return pd.DataFrame(columns=["event_date", "event_type"])


def signal_dates(breadth: pd.DataFrame, start: date, end: date) -> list[date]:
    df = breadth.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return [value for value in df["trade_date"].tolist() if start <= value <= end]


def run_signal_engine(
    spy: pd.DataFrame,
    breadth_history: pd.DataFrame,
    vix: pd.DataFrame,
    events: pd.DataFrame,
    start: date,
    end: date,
    params: dict[str, Any],
    sectors: pd.DataFrame | None = None,
    stocks: pd.DataFrame | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[Alert],
    list[SectorSignal],
    list[ThemeSignal],
    list[StockSignal],
]:
    enriched = enrich_breadth_history(breadth_history, params)
    themes = load_themes()
    sector_rows: list[SectorSignal] = []
    theme_rows: list[ThemeSignal] = []
    stock_rows: list[StockSignal] = []
    if sectors is not None and not sectors.empty and stocks is not None and not stocks.empty:
        member_breadth = (
            stocks.assign(trade_date=lambda df: pd.to_datetime(df["trade_date"]).dt.date)
            .groupby(["trade_date", "primary_sector"], as_index=False)["above_50ma"]
            .mean()
            .rename(columns={"primary_sector": "symbol", "above_50ma": "member_pct_above_50ma"})
        )
        member_breadth["member_pct_above_50ma"] *= 100
        sector_rows = compute_sector_signals(sectors, member_breadth, params)
        theme_rows = compute_theme_signals(stocks, themes, params)
        stock_rows = compute_stock_signals(stocks, sector_rows, themes, theme_rows, params)
    daily_rows: list[dict[str, Any]] = []
    all_alerts: list[Alert] = []
    state: RegimeState | None = None
    for trade_date in signal_dates(enriched, start, end):
        breadth_row = row_for_date(enriched, trade_date)
        market = market_row_for_date(spy, vix, events, trade_date, params)
        state = evaluate_regime(market, breadth_row, params, state)
        alerts = detect_alerts(enriched, spy, trade_date, params, as_of_date=trade_date)
        all_alerts.extend(alerts)
        sector_top3, sector_quadrant = (
            top_sector_payload(sector_rows, trade_date) if sector_rows else (None, None)
        )
        daily_rows.append(
            {
                "trade_date": trade_date,
                "regime": state.regime,
                "regime_streak": state.regime_streak,
                "regime_prev": state.regime_prev,
                "regime_changed": state.regime_changed,
                "breadth_pct_above_200ma": breadth_row.pct_above_200ma,
                "breadth_pct_above_50ma": breadth_row.pct_above_50ma,
                "breadth_pct_above_20ma": breadth_row.pct_above_20ma,
                "breadth_nh_nl_ratio": breadth_row.nh_nl_ratio,
                "breadth_mcclellan": breadth_row.mcclellan,
                "breadth_pct_above_200ma_p5y": breadth_row.pct_above_200ma_p5y,
                "breadth_pct_above_50ma_p5y": breadth_row.pct_above_50ma_p5y,
                "breadth_pct_above_50ma_p2y": breadth_row.pct_above_50ma_p2y,
                "breadth_score": breadth_row.score,
                "sectors_top3": sector_top3,
                "sectors_quadrant": sector_quadrant,
                "themes_top3": top_theme_payload(theme_rows, trade_date) if theme_rows else None,
                "as_of_date": trade_date,
            }
        )
    return daily_rows, all_alerts, sector_rows, theme_rows, stock_rows


def upsert_signals_daily(engine: Engine, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0])
    values = ", ".join(f":{column}" for column in columns)
    updates = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in columns if column != "trade_date"
    )
    sql = text(
        f"""
        INSERT INTO signals_daily ({", ".join(columns)})
        VALUES ({values})
        ON CONFLICT (trade_date) DO UPDATE SET {updates}
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, [_serialize_json_columns(row) for row in rows])


def upsert_alerts(engine: Engine, alerts: list[Alert]) -> None:
    if not alerts:
        return
    rows = [
        {
            "trade_date": item.trade_date,
            "alert_type": item.alert_type,
            "severity": item.severity,
            "detail": json.dumps(item.detail, sort_keys=True),
            "as_of_date": item.as_of_date,
        }
        for item in alerts
    ]
    sql = text(
        """
        INSERT INTO signals_alerts (trade_date, alert_type, severity, detail, as_of_date)
        VALUES (:trade_date, :alert_type, :severity, CAST(:detail AS JSONB), :as_of_date)
        ON CONFLICT (trade_date, alert_type, severity)
        DO UPDATE SET detail = EXCLUDED.detail, as_of_date = EXCLUDED.as_of_date
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, rows)


def upsert_detail_rows(engine: Engine, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0])
    values = ", ".join(f":{column}" for column in columns)
    key_columns = {"trade_date", "symbol", "theme_id"}
    updates = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in columns if column not in key_columns
    )
    conflict = "(trade_date, theme_id)" if "theme_id" in columns else "(trade_date, symbol)"
    sql = text(
        f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({values})
        ON CONFLICT {conflict} DO UPDATE SET {updates}
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, rows)


def _serialize_json_columns(row: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(row)
    for column in ("sectors_top3", "sectors_quadrant", "themes_top3"):
        if serialized[column] is not None:
            serialized[column] = json.dumps(serialized[column], sort_keys=True)
    return serialized


def load_fixture_macro_quotes(fixture_dir: Path) -> pd.DataFrame:
    path = fixture_dir / "macro_1y.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["trade_date"])
    spy = pd.read_csv(fixture_dir / "spy_1y.csv", parse_dates=["trade_date"])
    rows = []
    factors = {
        "SPY": 1.00,
        "TLT": 0.75,
        "IEF": 0.80,
        "HYG": 0.95,
        "LQD": 0.88,
        "UUP": 0.55,
        "GLD": 0.70,
        "SLV": 0.60,
        "DBC": 0.65,
        "VIXY": 0.45,
    }
    for symbol, factor in factors.items():
        symbol_frame = spy[["trade_date", "close"]].copy()
        symbol_frame["symbol"] = symbol
        symbol_frame["close"] = symbol_frame["close"] * factor
        rows.append(symbol_frame)
    return pd.concat(rows, ignore_index=True)


def run_pipeline(
    start: date,
    end: date,
    fixture_dir: Path | None = None,
    engine: Engine | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    params = load_params()
    engine = engine or create_postgres_engine()
    if fixture_dir:
        spy, breadth, vix, events, sectors, stocks = load_fixture_context(fixture_dir)
    else:
        spy, breadth, vix, events, sectors, stocks = load_db_context(engine, start, end)
    daily_rows, alerts, sector_rows, theme_rows, stock_rows = run_signal_engine(
        spy, breadth, vix, events, start, end, params, sectors=sectors, stocks=stocks
    )
    if not dry_run:
        upsert_signals_daily(engine, daily_rows)
        upsert_alerts(engine, alerts)
        upsert_detail_rows(engine, "signals_sectors_daily", [item.__dict__ for item in sector_rows])
        upsert_detail_rows(engine, "signals_themes_daily", [item.__dict__ for item in theme_rows])
        upsert_detail_rows(engine, "signals_stocks_daily", [item.__dict__ for item in stock_rows])
        macro_quotes = load_fixture_macro_quotes(fixture_dir) if fixture_dir else None
        for row in daily_rows:
            trade_date = row["trade_date"]
            if macro_quotes is None:
                run_macro(engine, trade_date)
            else:
                result = compute_macro_state(macro_quotes, trade_date)
                upsert_macro_state(engine, result)
    return {
        "signals_daily": len(daily_rows),
        "signals_alerts": len(alerts),
        "signals_sectors_daily": len(sector_rows),
        "signals_themes_daily": len(theme_rows),
        "signals_stocks_daily": len(stock_rows),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Orchestrate daily M-pool signal stages.")
    parser.add_argument("--as-of", help="Single trade date, YYYY-MM-DD.")
    parser.add_argument("--date", help="Deprecated alias for --as-of, YYYY-MM-DD.")
    parser.add_argument("--start", help="Backtest start date, YYYY-MM-DD.")
    parser.add_argument("--end", help="Backtest end date, YYYY-MM-DD.")
    parser.add_argument("--fixture-dir", help="Optional deterministic fixture directory.")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = create_postgres_engine()
    start, end, source = resolve_date_range(args, engine)
    logger.info("orchestrate target_date={}..{} source={}", start, end, source)
    result = run_pipeline(
        start,
        end,
        Path(args.fixture_dir) if args.fixture_dir else None,
        engine=engine,
        dry_run=args.dry_run,
    )
    logger.info("orchestrate wrote {}", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
