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
        rsi14_p20=float(row.get("rsi14_p20") or 30.0),
        rsi14_p80=float(row.get("rsi14_p80") or 70.0),
        drawdown_p10=float(row.get("drawdown_p10") or -0.20),
    )


def snapshot_from_history(
    *,
    entry: dict[str, Any],
    history: pd.DataFrame,
    shares_outstanding: float | None,
    theme_quintile: str = "mid",
    theme_quintile_prev: str = "mid",
) -> APoolSnapshot:
    df = history.sort_values("trade_date").copy()
    latest = df.iloc[-1]
    close = float(latest["close"])
    rolling_high = float(pd.to_numeric(df["close"], errors="coerce").tail(60).max())
    mean_20d = float(pd.to_numeric(df["close"], errors="coerce").tail(20).mean())
    std_20d = float(pd.to_numeric(df["close"], errors="coerce").tail(20).std() or 0.0)
    if len(df) > 60:
        ret_60d = (close / float(df.iloc[-61]["close"]) - 1) * 100
    else:
        ret_60d = 0.0
    return APoolSnapshot(
        symbol=str(entry["symbol"]),
        date=pd.to_datetime(latest["trade_date"]).date(),
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
                SELECT q.symbol, q.trade_date, q.close, di.rsi_14, di.sma_200
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
                       c.rsi14_p20, c.rsi14_p80, c.drawdown_p10
                FROM symbol_universe su
                LEFT JOIN a_pool_calibration c ON c.symbol = su.symbol
                WHERE su.symbol = ANY(:symbols)
                """
            ),
            {"symbols": symbols},
        ).mappings()
        return {str(row["symbol"]): dict(row) for row in rows}


def load_theme_quintiles(
    engine: Engine,
    trade_date: date,
    entries: list[dict[str, Any]],
) -> dict[str, str]:
    theme_ids = sorted({theme for item in entries for theme in item.get("themes", [])})
    if not theme_ids:
        return {}
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT theme_id, quintile
                FROM themes_score_daily
                WHERE date = :trade_date AND theme_id = ANY(:theme_ids)
                """
            ),
            {"trade_date": trade_date, "theme_ids": theme_ids},
        ).all()
    quintile_by_theme = {str(theme_id): str(quintile) for theme_id, quintile in rows}
    result = {}
    for item in entries:
        for theme_id in item.get("themes", []):
            if theme_id in quintile_by_theme:
                result[str(item["symbol"])] = quintile_by_theme[theme_id]
                break
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
    theme_quintiles = load_theme_quintiles(engine, trade_date, entries)
    rows = []
    for entry in entries:
        symbol = entry["symbol"]
        meta = metadata.get(symbol, {})
        symbol_history = history[history["symbol"] == symbol]
        if symbol_history.empty:
            logger.warning("Skipping {}: missing quote history for {}", symbol, trade_date)
            continue
        snapshot = snapshot_from_history(
            entry=entry,
            history=symbol_history,
            shares_outstanding=meta.get("shares_outstanding"),
            theme_quintile=theme_quintiles.get(symbol, "mid"),
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
