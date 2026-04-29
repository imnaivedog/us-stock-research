from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from lib.pg_client import PostgresClient

BENCHMARK_SYMBOL = "SPY"
DEFENSIVE = {"TLT", "GLD", "UUP", "VIXY"}
OFFENSIVE = {BENCHMARK_SYMBOL, "HYG", "LQD"}


@dataclass(frozen=True)
class MacroResult:
    trade_date: date
    macro_state: str
    symbol_states: dict[str, int]


def load_macro_symbols(path: Path | str = Path("config/etf_universe.csv")) -> list[str]:
    symbols: list[str] = []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("algo_role") == "macro_hedge" and row.get("code"):
                symbols.append(row["code"].strip().upper())
    merged = [*symbols, BENCHMARK_SYMBOL]
    return sorted({symbol for symbol in merged if symbol})


def compute_symbol_states(snapshot: pd.DataFrame) -> dict[str, int]:
    states: dict[str, int] = {}
    for row in snapshot.itertuples(index=False):
        close = float(row.close)
        sma_20 = float(row.sma_20)
        states[str(row.symbol)] = 1 if close > sma_20 else -1 if close < sma_20 else 0
    return states


def vote_macro_state(symbol_states: dict[str, int]) -> str:
    defensive_votes = sum(1 for symbol in DEFENSIVE if symbol_states.get(symbol) == 1)
    offensive_votes = sum(1 for symbol in OFFENSIVE if symbol_states.get(symbol) == 1)
    if defensive_votes > offensive_votes:
        return "risk_off"
    if offensive_votes > defensive_votes:
        return "risk_on"
    return "neutral"


def compute_macro_state(quotes: pd.DataFrame, trade_date: date) -> MacroResult:
    df = quotes.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["close"]).sort_values(["symbol", "trade_date"])
    df["sma_20"] = df.groupby("symbol")["close"].transform(
        lambda item: item.rolling(20, min_periods=1).mean()
    )
    snapshot = df[df["trade_date"] == trade_date]
    states = compute_symbol_states(snapshot)
    return MacroResult(
        trade_date=trade_date,
        macro_state=vote_macro_state(states),
        symbol_states=states,
    )


def load_macro_quotes(pg: PostgresClient, trade_date: date) -> pd.DataFrame:
    symbols = load_macro_symbols()
    start = trade_date - timedelta(days=45)
    return pd.read_sql_query(
        text(
            """
            SELECT symbol, trade_date, close
            FROM quotes_daily
            WHERE symbol = ANY(:symbols)
              AND trade_date BETWEEN :start AND :trade_date
            ORDER BY symbol, trade_date
            """
        ),
        pg.engine,
        params={"symbols": symbols, "start": start, "trade_date": trade_date},
    )


def upsert_macro_state(pg: PostgresClient, result: MacroResult) -> None:
    sql = text(
        """
        UPDATE signals_daily
        SET macro_state = :macro_state
        WHERE trade_date = :trade_date
        """
    )
    with pg.engine.begin() as conn:
        updated = conn.execute(
            sql, {"macro_state": result.macro_state, "trade_date": result.trade_date}
        ).rowcount
    if updated != 1:
        raise RuntimeError(f"signals_daily missing row for {result.trade_date}")


def run_macro(pg: PostgresClient, trade_date: date) -> MacroResult:
    result = compute_macro_state(load_macro_quotes(pg, trade_date), trade_date)
    upsert_macro_state(pg, result)
    return result
