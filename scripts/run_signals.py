from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
from loguru import logger  # noqa: E402
from sqlalchemy import text  # noqa: E402

from lib.pg_client import PostgresClient  # noqa: E402
from src.signals._params import load_params  # noqa: E402
from src.signals.breadth import (  # noqa: E402
    Alert,
    detect_alerts,
    enrich_breadth_history,
    row_for_date,
)
from src.signals.regime import RegimeState, evaluate_regime, market_row_for_date  # noqa: E402


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "INFO"), format="[{level}] {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run L1/L2 signals for one date or a date range.")
    parser.add_argument("--date", help="Single trade date, YYYY-MM-DD.")
    parser.add_argument("--start", help="Range start date, YYYY-MM-DD.")
    parser.add_argument("--end", help="Range end date, YYYY-MM-DD.")
    parser.add_argument(
        "--fixture-dir",
        help="Optional directory with spy_1y.csv, breadth_1y.csv, vix_1y.csv, events_calendar.csv.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute without database writes.")
    return parser.parse_args()


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def requested_dates(args: argparse.Namespace) -> tuple[date, date]:
    if args.date:
        day = parse_date(args.date)
        return day, day
    if not args.start or not args.end:
        raise ValueError("Use either --date or --start/--end")
    start = parse_date(args.start)
    end = parse_date(args.end)
    if start > end:
        raise ValueError("--start must be <= --end")
    return start, end


def load_fixture_context(
    fixture_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    spy = pd.read_csv(fixture_dir / "spy_1y.csv", parse_dates=["trade_date"])
    breadth = pd.read_csv(fixture_dir / "breadth_1y.csv", parse_dates=["trade_date"])
    vix = pd.read_csv(fixture_dir / "vix_1y.csv", parse_dates=["trade_date"])
    events = pd.read_csv(fixture_dir / "events_calendar.csv", parse_dates=["event_date"])
    return spy, breadth, vix, events


def load_db_context(
    pg: PostgresClient,
    start: date,
    end: date,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
        pg.engine,
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
              GREATEST(
                SUM(CASE WHEN pct_to_52w_high >= -1 THEN 1 ELSE 0 END)::numeric,
                1
              ) / GREATEST(
                SUM(CASE WHEN pct_to_52w_low <= 1 THEN 1 ELSE 0 END)::numeric,
                1
              ) AS breadth_nh_nl_ratio,
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
        pg.engine,
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
        pg.engine,
        params={"lookback_start": lookback_start, "end": end},
    )
    events = load_events_calendar(pg, start, end)
    return spy, breadth, vix, events


def load_events_calendar(pg: PostgresClient, start: date, end: date) -> pd.DataFrame:
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
            pg.engine,
            params={"start": start, "end": end + timedelta(days=10)},
        )
    except Exception:
        logger.warning("events_calendar table unavailable; treating event window as empty")
        return pd.DataFrame(columns=["event_date", "event_type"])


def signal_dates(breadth: pd.DataFrame, start: date, end: date) -> list[date]:
    df = breadth.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return [
        value
        for value in df["trade_date"].tolist()
        if start <= value <= end
    ]


def run_signal_engine(
    spy: pd.DataFrame,
    breadth_history: pd.DataFrame,
    vix: pd.DataFrame,
    events: pd.DataFrame,
    start: date,
    end: date,
    params: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Alert]]:
    enriched = enrich_breadth_history(breadth_history, params)
    daily_rows: list[dict[str, Any]] = []
    all_alerts: list[Alert] = []
    state: RegimeState | None = None
    for trade_date in signal_dates(enriched, start, end):
        breadth_row = row_for_date(enriched, trade_date)
        market = market_row_for_date(spy, vix, events, trade_date, params)
        state = evaluate_regime(market, breadth_row, params, state)
        alerts = detect_alerts(enriched, spy, trade_date, params, as_of_date=trade_date)
        all_alerts.extend(alerts)
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
                "sectors_top3": None,
                "sectors_quadrant": None,
                "themes_top3": None,
                "as_of_date": trade_date,
            }
        )
    return daily_rows, all_alerts


def upsert_signals_daily(pg: PostgresClient, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
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
    with pg.engine.begin() as conn:
        conn.execute(sql, [_serialize_json_columns(row) for row in rows])


def upsert_alerts(pg: PostgresClient, alerts: list[Alert]) -> None:
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
    with pg.engine.begin() as conn:
        conn.execute(sql, rows)


def _serialize_json_columns(row: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(row)
    for column in ("sectors_top3", "sectors_quadrant", "themes_top3"):
        if serialized[column] is not None:
            serialized[column] = json.dumps(serialized[column], sort_keys=True)
    return serialized


def run(args: argparse.Namespace) -> tuple[int, int]:
    params = load_params()
    start, end = requested_dates(args)
    pg: PostgresClient | None = None
    if args.fixture_dir:
        spy, breadth, vix, events = load_fixture_context(Path(args.fixture_dir))
    else:
        pg = PostgresClient()
        spy, breadth, vix, events = load_db_context(pg, start, end)
    if spy.empty or breadth.empty or vix.empty:
        raise ValueError("Missing input data for signal computation")
    daily_rows, alerts = run_signal_engine(spy, breadth, vix, events, start, end, params)
    logger.info(f"signals_daily rows={len(daily_rows)}, signals_alerts rows={len(alerts)}")
    if pg is not None and not args.dry_run:
        upsert_signals_daily(pg, daily_rows)
        upsert_alerts(pg, alerts)
    return len(daily_rows), len(alerts)


def main() -> None:
    configure_logging()
    args = parse_args()
    try:
        run(args)
    except ValueError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc
    except Exception as exc:
        logger.error(str(exc))
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
