"""A-pool daily signal orchestration."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

from usstock_analytics.a_pool.scoring import ScoreResult, score_a_pool
from usstock_analytics.a_pool.signals.models import APoolSnapshot, Calibration
from usstock_analytics.a_pool.signals.orchestrator import evaluate_signals
from usstock_analytics.a_pool.verdict import VerdictClient, generate_verdict
from usstock_analytics.db import create_postgres_engine

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_A_POOL_PATH = REPO_ROOT / "config" / "a_pool.yaml"


def load_a_pool_entries(
    path: Path = DEFAULT_A_POOL_PATH,
    symbols: list[str] | None = None,
) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else []
    entries = payload or []
    wanted = {symbol.upper() for symbol in symbols or []}
    result = []
    for item in entries:
        symbol = str(item.get("symbol", "")).upper()
        if not symbol or item.get("status", "active") != "active":
            continue
        if wanted and symbol not in wanted:
            continue
        result.append({**item, "symbol": symbol})
    return result


def calibration_from_mapping(row: dict[str, Any]) -> Calibration:
    return Calibration(
        rsi14_p5=float(row.get("rsi14_p5") or 25.0),
        rsi14_p20=float(row.get("rsi14_p20") or 30.0),
        rsi14_p80=float(row.get("rsi14_p80") or 70.0),
        rsi14_p95=float(row.get("rsi14_p95") or 80.0),
        drawdown_p10=float(row.get("drawdown_p10") or -0.20),
    )


def _float_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _entry_age_days(entry: dict[str, Any], trade_date: date) -> int | None:
    added = entry.get("added")
    if added is None:
        return None
    if isinstance(added, date):
        added_date = added
    else:
        added_date = date.fromisoformat(str(added))
    return (trade_date - added_date).days


def _days_since_previous_macd_cross(df: pd.DataFrame) -> int | None:
    crosses: list[date] = []
    for idx in range(1, len(df)):
        prev = df.iloc[idx - 1]
        current = df.iloc[idx]
        if any(
            pd.isna(value)
            for value in (
                prev.get("macd_line"),
                prev.get("macd_signal"),
                current.get("macd_line"),
                current.get("macd_signal"),
            )
        ):
            continue
        crossed_up = (
            prev["macd_line"] <= prev["macd_signal"]
            and current["macd_line"] > current["macd_signal"]
        )
        if crossed_up:
            crosses.append(pd.to_datetime(current["trade_date"]).date())
    if not crosses:
        return None
    latest_date = pd.to_datetime(df.iloc[-1]["trade_date"]).date()
    earlier = [cross_date for cross_date in crosses if cross_date < latest_date]
    if not earlier:
        return None
    return (latest_date - earlier[-1]).days


def snapshot_from_history(
    *,
    entry: dict[str, Any],
    history: pd.DataFrame,
    shares_outstanding: float | None,
    theme_quintile: str = "mid",
    theme_quintile_prev: str = "mid",
    theme_bottom_days: int = 0,
    days_since_earnings: int | None = None,
    post_earnings_drop_pct: float | None = None,
    corporate_action_flags: list[str] | None = None,
) -> APoolSnapshot:
    df = history.sort_values("trade_date").copy()
    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) >= 2 else latest
    close = float(latest["close"])
    rolling_high = float(pd.to_numeric(df["close"], errors="coerce").tail(60).max())
    rolling_low_20 = float(pd.to_numeric(df["low"], errors="coerce").tail(20).min())
    rolling_low_60 = float(pd.to_numeric(df["low"], errors="coerce").tail(60).min())
    mean_20d = float(pd.to_numeric(df["close"], errors="coerce").tail(20).mean())
    std_20d = float(pd.to_numeric(df["close"], errors="coerce").tail(20).std() or 0.0)
    avg_volume_20d = float(pd.to_numeric(df["volume"], errors="coerce").tail(20).mean() or 0.0)
    rsi_series = pd.to_numeric(df["rsi_14"], errors="coerce").dropna()
    latest_trade_date = pd.to_datetime(latest["trade_date"]).date()
    if len(df) > 60:
        ret_60d = (close / float(df.iloc[-61]["close"]) - 1) * 100
    else:
        ret_60d = 0.0
    recent_b5_support = (
        rolling_low_20 > 0
        and close <= rolling_low_20 * 1.03
        and (
            (_float_or_none(latest.get("open")) is not None and close > float(latest["open"]))
            or close > float(previous["close"])
        )
    )
    return APoolSnapshot(
        symbol=str(entry["symbol"]),
        date=latest_trade_date,
        close=close,
        rsi14=float(latest.get("rsi_14") or 50.0),
        drawdown_60d=0.0 if rolling_high <= 0 else close / rolling_high - 1,
        trendline_5y=float(latest.get("sma_200") or close),
        mean_20d=mean_20d,
        std_20d=std_20d,
        ret_60d=ret_60d,
        shares_outstanding=shares_outstanding,
        thesis_stop_mcap_b=float(entry["thesis_stop_mcap_b"]),
        target_mcap_b=float(entry["target_mcap_b"]),
        theme_quintile=theme_quintile,
        theme_quintile_prev=theme_quintile_prev,
        theme_bottom_days=theme_bottom_days,
        open=_float_or_none(latest.get("open")),
        high=_float_or_none(latest.get("high")),
        low=_float_or_none(latest.get("low")),
        prev_close=_float_or_none(previous.get("close")),
        volume=_float_or_none(latest.get("volume")),
        avg_volume_20d=avg_volume_20d,
        sma_20=_float_or_none(latest.get("sma_20")),
        sma_50=_float_or_none(latest.get("sma_50")),
        sma_200=_float_or_none(latest.get("sma_200")),
        prev_sma_20=_float_or_none(previous.get("sma_20")),
        prev_sma_50=_float_or_none(previous.get("sma_50")),
        prev_sma_200=_float_or_none(previous.get("sma_200")),
        macd_line=_float_or_none(latest.get("macd_line")),
        macd_signal=_float_or_none(latest.get("macd_signal")),
        prev_macd_line=_float_or_none(previous.get("macd_line")),
        prev_macd_signal=_float_or_none(previous.get("macd_signal")),
        days_since_previous_macd_cross=_days_since_previous_macd_cross(df),
        rolling_high_60=rolling_high,
        rolling_low_20=rolling_low_20,
        rolling_low_60=rolling_low_60,
        max_rsi_60=float(rsi_series.tail(60).max()) if not rsi_series.empty else None,
        max_volume_60=float(pd.to_numeric(df["volume"], errors="coerce").tail(60).max() or 0.0),
        rsi14_history=tuple(float(value) for value in rsi_series.tail(3)),
        thesis_age_days=_entry_age_days(entry, latest_trade_date),
        recent_b5_support=recent_b5_support,
        days_since_earnings=days_since_earnings,
        post_earnings_drop_pct=post_earnings_drop_pct or 0.0,
        corporate_action_flags=corporate_action_flags or [],
    )


def build_daily_row(
    *,
    snapshot: APoolSnapshot,
    calibration: Calibration,
    llm_client: VerdictClient | None = None,
    profile: dict[str, object] | None = None,
) -> dict[str, Any]:
    signals = evaluate_signals(snapshot, calibration)
    score: ScoreResult = score_a_pool(snapshot, signals)
    verdict = generate_verdict(
        symbol=snapshot.symbol,
        signals=signals,
        score=score.a_score,
        score_breakdown=score.score_breakdown,
        profile=profile or {},
        ohlc={"date": snapshot.date.isoformat(), "close": snapshot.close},
        thesis_stop_price=score.thesis_stop_price,
        target_price=score.target_price,
        client=llm_client,
    )
    return {
        "date": snapshot.date,
        "symbol": snapshot.symbol,
        "signals": signals,
        "a_score": score.a_score,
        "score_breakdown": score.score_breakdown,
        "verdict_text": verdict.text,
        "verdict_source": verdict.source,
        "verdict_error": verdict.error,
        "thesis_stop_price": score.thesis_stop_price,
        "target_price": score.target_price,
    }


def load_history(engine: Engine, symbols: list[str], trade_date: date) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    with engine.begin() as conn:
        return pd.read_sql_query(
            text(
                """
                SELECT q.symbol, q.trade_date, q.open, q.high, q.low, q.close, q.volume,
                       di.rsi_14, di.sma_20, di.sma_50, di.sma_200,
                       di.macd_line, di.macd_signal
                FROM quotes_daily q
                LEFT JOIN daily_indicators di
                  ON di.symbol = q.symbol AND di.trade_date = q.trade_date
                WHERE q.symbol = ANY(:symbols)
                  AND q.trade_date <= :trade_date
                  AND q.trade_date >= :trade_date - interval '120 days'
                ORDER BY q.symbol, q.trade_date
                """
            ),
            conn,
            params={"symbols": symbols, "trade_date": trade_date},
        )


def load_symbol_metadata(engine: Engine, symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT su.symbol, su.shares_outstanding,
                       c.rsi14_p5, c.rsi14_p20, c.rsi14_p80, c.rsi14_p95,
                       c.drawdown_p10
                FROM symbol_universe su
                LEFT JOIN a_pool_calibration c ON c.symbol = su.symbol
                WHERE su.symbol = ANY(:symbols)
                """
            ),
            {"symbols": symbols},
        ).mappings()
        return {str(row["symbol"]): dict(row) for row in rows}


def _row_value(row: Any, key: str, index: int) -> Any:
    if hasattr(row, "_mapping"):
        return row._mapping[key]
    if isinstance(row, dict):
        return row[key]
    return row[index]


def primary_theme_by_symbol(entries: list[dict[str, Any]]) -> dict[str, str]:
    result = {}
    for item in entries:
        themes = item.get("themes") or []
        if themes:
            result[str(item["symbol"])] = str(themes[0])
    return result


def bottom_streak(rows: list[tuple[date, str]]) -> int:
    count = 0
    for _row_date, quintile in sorted(rows, key=lambda item: item[0], reverse=True):
        if quintile != "bottom":
            break
        count += 1
    return count


def load_theme_history(
    engine: Engine,
    trade_date: date,
    entries: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Returns {symbol: {quintile, quintile_prev, bottom_days}}."""
    theme_ids = sorted({theme for item in entries for theme in item.get("themes", [])})
    if not theme_ids:
        return {}
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT date, theme_id, quintile
                FROM themes_score_daily
                WHERE theme_id = ANY(:theme_ids)
                  AND date <= :trade_date
                  AND date >= :trade_date - interval '30 days'
                ORDER BY theme_id, date DESC
                """
            ),
            {"trade_date": trade_date, "theme_ids": theme_ids},
        ).all()
    rows_by_theme: dict[str, list[tuple[date, str]]] = {}
    for row in rows:
        row_date = _row_value(row, "date", 0)
        theme_id = str(_row_value(row, "theme_id", 1))
        quintile = str(_row_value(row, "quintile", 2))
        rows_by_theme.setdefault(theme_id, []).append((row_date, quintile))

    primary_themes = primary_theme_by_symbol(entries)
    result = {}
    for symbol, theme_id in primary_themes.items():
        series = sorted(rows_by_theme.get(theme_id, []), key=lambda item: item[0], reverse=True)
        if not series:
            continue
        today = next((item for item in series if item[0] == trade_date), series[0])
        prev = next((item for item in series if item[0] < trade_date), today)
        result[symbol] = {
            "quintile": today[1],
            "quintile_prev": prev[1],
            "bottom_days": bottom_streak(series),
        }
    return result


def load_recent_earnings(
    engine: Engine,
    symbols: list[str],
    trade_date: date,
) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT ec.symbol, ec.event_date,
                       q_event.close AS event_close,
                       q_now.close AS current_close
                FROM events_calendar ec
                JOIN quotes_daily q_event
                  ON q_event.symbol = ec.symbol AND q_event.trade_date = ec.event_date
                JOIN quotes_daily q_now
                  ON q_now.symbol = ec.symbol AND q_now.trade_date = :trade_date
                WHERE ec.symbol = ANY(:symbols)
                  AND ec.event_type = 'earnings'
                  AND ec.event_date <= :trade_date
                  AND ec.event_date >= :trade_date - interval '30 days'
                ORDER BY ec.symbol, ec.event_date DESC
                """
            ),
            {"symbols": symbols, "trade_date": trade_date},
        ).all()
    result = {}
    for row in rows:
        symbol = str(_row_value(row, "symbol", 0))
        if symbol in result:
            continue
        event_date = _row_value(row, "event_date", 1)
        event_close = float(_row_value(row, "event_close", 2) or 0)
        current_close = float(_row_value(row, "current_close", 3) or 0)
        drop_pct = 0.0 if event_close <= 0 else (current_close / event_close - 1) * 100
        result[symbol] = {
            "days_since": (trade_date - event_date).days,
            "drop_pct": drop_pct,
        }
    return result


def load_corporate_action_flags(
    engine: Engine,
    symbols: list[str],
    trade_date: date,
) -> dict[str, list[str]]:
    if not symbols:
        return {}
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT symbol, action_type
                FROM corporate_actions
                WHERE symbol = ANY(:symbols)
                  AND ex_date <= :trade_date
                  AND ex_date >= :trade_date - interval '30 days'
                ORDER BY symbol, ex_date DESC
                """
            ),
            {"symbols": symbols, "trade_date": trade_date},
        ).all()
    mapping = {
        "split": "split",
        "secondary_offering": "large_dilution",
        "dilution": "large_dilution",
        "dividend_cut": "dividend_cut",
    }
    result: dict[str, list[str]] = {}
    for row in rows:
        symbol = str(_row_value(row, "symbol", 0))
        action_type = str(_row_value(row, "action_type", 1))
        flag = mapping.get(action_type, action_type)
        if flag not in result.setdefault(symbol, []):
            result[symbol].append(flag)
    return result


def write_alert(
    engine: Engine,
    *,
    job_name: str,
    symbol: str,
    trade_date: date,
    severity: str,
    message: str,
    category: str,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO alert_log (job_name, symbol, trade_date, severity, message, category)
                VALUES (:job_name, :symbol, :trade_date, :severity, :message, :category)
                """
            ),
            {
                "job_name": job_name,
                "symbol": symbol,
                "trade_date": trade_date,
                "severity": severity,
                "message": message,
                "category": category,
            },
        )


def upsert_rows(engine: Engine, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    prepared = [
        {
            **row,
            "signals": json.dumps(row["signals"], ensure_ascii=False),
            "score_breakdown": json.dumps(row["score_breakdown"], ensure_ascii=False),
        }
        for row in rows
    ]
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO signals_a_pool_daily (
                    date, symbol, signals, a_score, score_breakdown, verdict_text,
                    verdict_source, thesis_stop_price, target_price
                )
                VALUES (
                    :date, :symbol, CAST(:signals AS JSONB), :a_score,
                    CAST(:score_breakdown AS JSONB), :verdict_text, :verdict_source,
                    :thesis_stop_price, :target_price
                )
                ON CONFLICT (date, symbol) DO UPDATE SET
                    signals = EXCLUDED.signals,
                    a_score = EXCLUDED.a_score,
                    score_breakdown = EXCLUDED.score_breakdown,
                    verdict_text = EXCLUDED.verdict_text,
                    verdict_source = EXCLUDED.verdict_source,
                    thesis_stop_price = EXCLUDED.thesis_stop_price,
                    target_price = EXCLUDED.target_price
                """
            ),
            prepared,
        )
    return len(rows)


def run(
    *,
    trade_date: date,
    engine: Engine | None = None,
    symbols: list[str] | None = None,
    a_pool_path: Path = DEFAULT_A_POOL_PATH,
    llm_client: VerdictClient | None = None,
) -> int:
    engine = engine or create_postgres_engine()
    entries = load_a_pool_entries(a_pool_path, symbols)
    active_symbols = [item["symbol"] for item in entries]
    metadata = load_symbol_metadata(engine, active_symbols)
    history = load_history(engine, active_symbols, trade_date)
    theme_data = load_theme_history(engine, trade_date, entries)
    earnings = load_recent_earnings(engine, active_symbols, trade_date)
    ca_flags = load_corporate_action_flags(engine, active_symbols, trade_date)
    rows = []
    for entry in entries:
        symbol = entry["symbol"]
        meta = metadata.get(symbol, {})
        symbol_history = history[history["symbol"] == symbol]
        if symbol_history.empty:
            logger.warning("Skipping {}: missing quote history for {}", symbol, trade_date)
            continue
        td = theme_data.get(symbol, {})
        ev = earnings.get(symbol, {})
        snapshot = snapshot_from_history(
            entry=entry,
            history=symbol_history,
            shares_outstanding=meta.get("shares_outstanding"),
            theme_quintile=td.get("quintile", "mid"),
            theme_quintile_prev=td.get("quintile_prev", "mid"),
            theme_bottom_days=td.get("bottom_days", 0),
            days_since_earnings=ev.get("days_since"),
            post_earnings_drop_pct=ev.get("drop_pct"),
            corporate_action_flags=ca_flags.get(symbol, []),
        )
        calibration = calibration_from_mapping(meta)
        row = build_daily_row(
            snapshot=snapshot,
            calibration=calibration,
            llm_client=llm_client,
            profile=meta,
        )
        if snapshot.shares_outstanding is None:
            write_alert(
                engine,
                job_name="a_pool_signals",
                symbol=symbol,
                trade_date=trade_date,
                severity="WARN",
                message="shares_outstanding is NULL; writing hold verdict",
                category="shares_outstanding",
            )
        if row["verdict_error"]:
            write_alert(
                engine,
                job_name="a_pool_signals",
                symbol=symbol,
                trade_date=trade_date,
                severity="WARN",
                message=str(row["verdict_error"]),
                category="llm_verdict",
            )
        rows.append(row)
    return upsert_rows(engine, rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="usstock-analytics a-pool signals")
    parser.add_argument("--date", required=True)
    parser.add_argument("--symbols")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    symbols = [item.strip().upper() for item in args.symbols.split(",")] if args.symbols else None
    written = run(trade_date=date.fromisoformat(args.date), symbols=symbols)
    print({"written": written})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
