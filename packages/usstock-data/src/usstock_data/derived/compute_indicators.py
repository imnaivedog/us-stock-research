"""Compute daily technical indicators from quotes_daily."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from usstock_data.db import create_postgres_engine

LOOKBACK_ROWS = 252
JOB_NAME = "compute_indicators"
INDICATOR_COLUMNS = [
    "sma_5",
    "sma_10",
    "sma_20",
    "sma_50",
    "sma_200",
    "ema_12",
    "ema_26",
    "macd_line",
    "macd_signal",
    "macd_histogram",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "bb_width",
    "rsi_14",
    "obv",
    "vwap_20",
    "atr_14",
    "std_20",
    "std_60",
    "adx_14",
    "di_plus_14",
    "di_minus_14",
    "pct_to_52w_high",
    "pct_to_52w_low",
    "pct_to_200ma",
    "beta_60d",
    "ma200_slope_20d",
]
UPSERT_COLUMNS = ["symbol", "trade_date", *INDICATOR_COLUMNS]


@dataclass(frozen=True)
class IndicatorResult:
    as_of: date
    requested_symbols: int
    skipped_symbols: int
    computed_symbols: int
    rows_written: int
    dry_run: bool


def empty_quotes_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["symbol", "trade_date", "open", "high", "low", "close", "adj_close", "volume"]
    )


def prepare_quotes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return empty_quotes_frame()
    prepared = df.copy()
    prepared = prepared.drop(columns=["stock_ret", "spy_ret"], errors="ignore")
    prepared["symbol"] = prepared["symbol"].astype(str).str.upper()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"]).dt.date
    for column in ("open", "high", "low", "close", "adj_close", "volume"):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    prepared = prepared.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    prepared["stock_ret"] = prepared.groupby("symbol", sort=False)["close"].pct_change()
    spy_returns = (
        prepared.loc[prepared["symbol"] == "SPY", ["trade_date", "stock_ret"]]
        .rename(columns={"stock_ret": "spy_ret"})
        .drop_duplicates("trade_date", keep="last")
    )
    return prepared.merge(spy_returns, on="trade_date", how="left")


def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.where(avg_loss != 0, 100)


def true_range(high: pd.Series, low: pd.Series, previous_close: pd.Series) -> pd.Series:
    ranges = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    )
    return ranges.max(axis=1)


def compute_symbol_indicators(group: pd.DataFrame) -> pd.DataFrame:
    data = group.sort_values("trade_date").copy()
    high = data["high"]
    low = data["low"]
    close = data["close"]
    volume = data["volume"].fillna(0)

    data["sma_5"] = close.rolling(5).mean()
    data["sma_10"] = close.rolling(10).mean()
    data["sma_20"] = close.rolling(20).mean()
    data["sma_50"] = close.rolling(50).mean()
    data["sma_200"] = close.rolling(200).mean()
    data["ema_12"] = close.ewm(span=12, adjust=False).mean()
    data["ema_26"] = close.ewm(span=26, adjust=False).mean()
    data["macd_line"] = data["ema_12"] - data["ema_26"]
    data["macd_signal"] = data["macd_line"].ewm(span=9, adjust=False).mean()
    data["macd_histogram"] = data["macd_line"] - data["macd_signal"]

    bb_std = close.rolling(20).std()
    data["bb_middle"] = data["sma_20"]
    data["bb_upper"] = data["bb_middle"] + 2 * bb_std
    data["bb_lower"] = data["bb_middle"] - 2 * bb_std
    data["bb_width"] = (data["bb_upper"] - data["bb_lower"]) / data["bb_middle"]
    data["rsi_14"] = wilder_rsi(close)
    data["obv"] = (np.sign(close.diff()).fillna(0) * volume).cumsum()
    data["vwap_20"] = (close * volume).rolling(20).sum() / volume.rolling(20).sum()

    previous_close = close.shift(1)
    tr = true_range(high, low, previous_close)
    data["atr_14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    data["std_20"] = data["stock_ret"].rolling(20).std()
    data["std_60"] = data["stock_ret"].rolling(60).std()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=data.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=data.index
    )
    smoothed_tr = tr.ewm(alpha=1 / 14, adjust=False).mean().replace(0, np.nan)
    data["di_plus_14"] = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False).mean() / smoothed_tr
    data["di_minus_14"] = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False).mean() / smoothed_tr
    dx_denominator = (data["di_plus_14"] + data["di_minus_14"]).replace(0, np.nan)
    dx = 100 * (data["di_plus_14"] - data["di_minus_14"]).abs() / dx_denominator
    data["adx_14"] = dx.ewm(alpha=1 / 14, adjust=False).mean()

    high_52w = close.rolling(252).max()
    low_52w = close.rolling(252).min()
    data["pct_to_52w_high"] = (close - high_52w) / high_52w * 100
    data["pct_to_52w_low"] = (close - low_52w) / low_52w * 100
    data["pct_to_200ma"] = (close - data["sma_200"]) / data["sma_200"] * 100
    data["beta_60d"] = data["stock_ret"].rolling(60).cov(data["spy_ret"]) / data["spy_ret"].rolling(
        60
    ).var().replace(0, np.nan)
    data["ma200_slope_20d"] = (data["sma_200"] / data["sma_200"].shift(20) - 1) * 100
    return data


def compute_indicators(quotes: pd.DataFrame) -> pd.DataFrame:
    prepared = prepare_quotes(quotes)
    if prepared.empty:
        empty_columns = {column: pd.Series(dtype="float64") for column in INDICATOR_COLUMNS}
        return prepared.assign(**empty_columns)
    frames = [
        compute_symbol_indicators(group)
        for _, group in prepared.groupby("symbol", sort=False, group_keys=False)
    ]
    return pd.concat(frames, ignore_index=True)


def normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def indicator_rows_for_date(
    indicators: pd.DataFrame, as_of: date, symbols: list[str]
) -> list[dict[str, Any]]:
    if indicators.empty:
        return []
    wanted = set(symbols)
    rows = indicators[(indicators["trade_date"] == as_of) & (indicators["symbol"].isin(wanted))]
    payload: list[dict[str, Any]] = []
    for row in rows[UPSERT_COLUMNS].to_dict(orient="records"):
        item = {key: normalize_value(value) for key, value in row.items()}
        if item.get("obv") is not None:
            item["obv"] = int(item["obv"])
        payload.append(item)
    return payload


def load_active_symbols(engine: Engine) -> list[str]:
    with engine.begin() as conn:
        return [
            str(row[0]).upper()
            for row in conn.execute(
                text("SELECT symbol FROM symbol_universe WHERE is_active IS TRUE ORDER BY symbol")
            )
        ]


def load_existing_indicator_symbols(engine: Engine, as_of: date, symbols: list[str]) -> set[str]:
    if not symbols:
        return set()
    with engine.begin() as conn:
        return set(
            conn.execute(
                text(
                    """
                    SELECT symbol
                    FROM daily_indicators
                    WHERE trade_date = :as_of AND symbol IN :symbols
                    """
                ).bindparams(bindparam("symbols", expanding=True)),
                {"as_of": as_of, "symbols": symbols},
            ).scalars()
        )


def load_quote_history(
    engine: Engine, as_of: date, symbols: list[str], lookback_rows: int = LOOKBACK_ROWS
) -> pd.DataFrame:
    if not symbols:
        return empty_quotes_frame()
    params = {
        "as_of": as_of,
        "lookback_rows": lookback_rows,
        "symbols": sorted(set(symbols + ["SPY"])),
    }
    sql = text(
        """
        SELECT symbol, trade_date, open, high, low, close, adj_close, volume
        FROM (
            SELECT q.*,
                   row_number() OVER (PARTITION BY q.symbol ORDER BY q.trade_date DESC) AS rn
            FROM quotes_daily q
            WHERE q.trade_date <= :as_of
              AND q.symbol IN :symbols
        ) ranked
        WHERE rn <= :lookback_rows
        ORDER BY symbol, trade_date
        """
    ).bindparams(bindparam("symbols", expanding=True))
    return pd.read_sql_query(sql, engine, params=params)


def build_upsert_sql() -> str:
    columns = ", ".join(UPSERT_COLUMNS)
    values = ", ".join(f":{column}" for column in UPSERT_COLUMNS)
    update_cols = ", ".join(f"{column} = EXCLUDED.{column}" for column in INDICATOR_COLUMNS)
    return (
        f"INSERT INTO daily_indicators ({columns}) VALUES ({values}) "
        f"ON CONFLICT (symbol, trade_date) DO UPDATE SET {update_cols}, computed_at = now()"
    )


def upsert_daily_indicators(engine: Engine, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with engine.begin() as conn:
        conn.execute(text(build_upsert_sql()), rows)


def log_symbol_failure(engine: Engine, symbol: str, trade_date: date, message: str) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO alert_log (
                        job_name, symbol, trade_date, severity, message, created_at
                    )
                    VALUES (:job_name, :symbol, :trade_date, 'WARN', :message, now())
                    """
                ),
                {
                    "job_name": JOB_NAME,
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "message": message[:1000],
                },
            )
    except Exception as exc:  # pragma: no cover - alert_log is environment-owned.
        logger.warning("Could not write alert_log for {}: {}", symbol, exc)


def compute_rows_for_symbols(
    quotes: pd.DataFrame,
    as_of: date,
    symbols: list[str],
    engine: Engine | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    failed: list[str] = []
    prepared = prepare_quotes(quotes)
    if prepared.empty:
        return rows, symbols
    for symbol in symbols:
        try:
            symbol_quotes = prepared[(prepared["symbol"] == symbol) | (prepared["symbol"] == "SPY")]
            indicators = compute_indicators(symbol_quotes)
            symbol_rows = indicator_rows_for_date(indicators, as_of, [symbol])
            if symbol_rows:
                rows.extend(symbol_rows)
            else:
                failed.append(symbol)
        except Exception as exc:
            failed.append(symbol)
            logger.exception("Skipping {}", symbol)
            if engine is not None:
                log_symbol_failure(engine, symbol, as_of, str(exc))
    return rows, failed


def run_compute_indicators(
    engine: Engine | None = None,
    as_of: date | None = None,
    requested_symbols: list[str] | None = None,
    dry_run: bool = False,
) -> IndicatorResult:
    if as_of is None:
        raise ValueError("as_of is required")
    engine = engine or create_postgres_engine()
    symbols = requested_symbols or load_active_symbols(engine)
    existing = load_existing_indicator_symbols(engine, as_of, symbols)
    due_symbols = [symbol for symbol in symbols if symbol not in existing]
    logger.info(
        "compute_indicators as_of={}, requested={}, skipped_existing={}, due={}, dry_run={}",
        as_of,
        len(symbols),
        len(existing),
        len(due_symbols),
        dry_run,
    )
    if not due_symbols:
        return IndicatorResult(as_of, len(symbols), len(existing), 0, 0, dry_run)
    quotes = load_quote_history(engine, as_of, due_symbols)
    rows, failed = compute_rows_for_symbols(quotes, as_of, due_symbols, engine=engine)
    logger.info("compute_indicators computed_rows={}, failed_symbols={}", len(rows), len(failed))
    if not dry_run:
        upsert_daily_indicators(engine, rows)
    return IndicatorResult(
        as_of=as_of,
        requested_symbols=len(symbols),
        skipped_symbols=len(existing),
        computed_symbols=len(rows),
        rows_written=0 if dry_run else len(rows),
        dry_run=dry_run,
    )


def parse_symbols(value: str) -> list[str] | None:
    if value.strip().upper() == "ALL":
        return None
    symbols = sorted({item.strip().upper() for item in value.split(",") if item.strip()})
    if not symbols:
        raise ValueError("--symbols must be ALL or a comma-separated symbol list")
    return symbols


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute daily technical indicators.")
    parser.add_argument("--as-of", required=True, help="US Eastern trade date, YYYY-MM-DD.")
    parser.add_argument("--symbols", default="ALL")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_compute_indicators(
        as_of=date.fromisoformat(args.as_of),
        requested_symbols=parse_symbols(args.symbols),
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
