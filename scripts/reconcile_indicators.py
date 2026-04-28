from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.pg_client import PostgresClient  # noqa: E402
from scripts.compute_indicators import INDICATOR_COLUMNS, compute_indicators  # noqa: E402

Status = Literal["pass", "fail", "no_data"]

TARGET_FIELDS = [
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

RELATIVE_TOLERANCES = {
    "sma_5": 0.001,
    "sma_10": 0.001,
    "sma_20": 0.001,
    "sma_50": 0.001,
    "sma_200": 0.001,
    "ema_12": 0.005,
    "ema_26": 0.005,
    "macd_line": 0.01,
    "macd_signal": 0.01,
    "macd_histogram": 0.01,
    "bb_upper": 0.001,
    "bb_middle": 0.001,
    "bb_lower": 0.001,
    "bb_width": 0.001,
    "vwap_20": 0.001,
    "atr_14": 0.02,
    "std_20": 0.01,
    "std_60": 0.01,
    "pct_to_52w_high": 0.005,
    "pct_to_52w_low": 0.005,
    "pct_to_200ma": 0.005,
    "ma200_slope_20d": 0.005,
}
POINT_TOLERANCES = {
    "rsi_14": 2.0,
    "adx_14": 3.0,
    "di_plus_14": 3.0,
    "di_minus_14": 3.0,
    "beta_60d": 0.05,
}
OBV_MIN_CORRELATION = 0.99
FORMULA_FIELDS = {"rsi_14", "atr_14", "adx_14", "di_plus_14", "di_minus_14"}


@dataclass(frozen=True)
class FieldResult:
    field: str
    symbol: str
    metric: float | None
    tolerance: float
    status: Status
    samples: int


@dataclass(frozen=True)
class ReconcileResult:
    results: list[FieldResult]
    samples: pd.DataFrame
    report_path: Path
    ours_source: str
    source_note: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile daily_indicators against yfinance/pandas-ta."
    )
    parser.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated symbols, e.g. NVDA,SPY,AAPL.",
    )
    parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD.")
    parser.add_argument(
        "--end",
        required=True,
        help="End date, YYYY-MM-DD. yfinance treats it as exclusive.",
    )
    parser.add_argument("--output", required=True, help="Markdown report output path.")
    parser.add_argument(
        "--ours-source",
        choices=["auto", "db", "compute"],
        default="auto",
        help=(
            "Read our values from Cloud SQL, compute locally from yfinance, "
            "or try DB then compute."
        ),
    )
    parser.add_argument(
        "--ours-csv",
        help="Optional local daily_indicators dump CSV. Columns must include symbol/trade_date.",
    )
    parser.add_argument(
        "--compare-tail",
        type=int,
        default=60,
        help="Compare the last N comparable rows per symbol to avoid warm-up noise.",
    )
    parser.add_argument(
        "--warmup-days",
        type=int,
        default=30,
        help="Extra calendar days to fetch before --start for rolling-window warm-up.",
    )
    return parser.parse_args()


def parse_symbols(value: str) -> list[str]:
    symbols = sorted({item.strip().upper() for item in value.split(",") if item.strip()})
    if not symbols:
        raise ValueError("--symbols must contain at least one ticker")
    return symbols


def require_external_modules() -> tuple[object, object]:
    try:
        if not hasattr(np, "NaN"):
            np.NaN = np.nan  # type: ignore[attr-defined]
        import pandas_ta as ta  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Missing or incompatible dependency pandas-ta. Install with `uv sync` after "
            "pyproject update."
        ) from exc
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency yfinance. Install with `uv sync` after pyproject update."
        ) from exc
    return ta, yf


def download_yfinance_quotes(
    yf: object,
    symbols: list[str],
    start: date,
    end: date,
) -> pd.DataFrame:
    wanted_symbols = sorted(set(symbols + ["SPY"]))
    try:
        raw = yf.download(  # type: ignore[attr-defined]
            tickers=" ".join(wanted_symbols),
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=True,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download yfinance OHLCV for {wanted_symbols}: {exc}"
        ) from exc
    if raw.empty:
        raise RuntimeError(f"yfinance returned no rows for {wanted_symbols} from {start} to {end}")
    frames: list[pd.DataFrame] = []
    if isinstance(raw.columns, pd.MultiIndex):
        for symbol in wanted_symbols:
            if symbol not in raw.columns.get_level_values(0):
                raise RuntimeError(f"yfinance response missing symbol {symbol}")
            frames.append(_normalize_yf_symbol(raw[symbol], symbol))
    else:
        if len(wanted_symbols) != 1:
            raise RuntimeError("Unexpected yfinance shape for multi-symbol download")
        frames.append(_normalize_yf_symbol(raw, wanted_symbols[0]))
    quotes = pd.concat(frames, ignore_index=True)
    missing = sorted(set(wanted_symbols) - set(quotes["symbol"].unique()))
    if missing:
        raise RuntimeError(f"yfinance returned no usable OHLCV rows for: {', '.join(missing)}")
    return quotes.sort_values(["symbol", "trade_date"]).reset_index(drop=True)


def _normalize_yf_symbol(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    column_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    }
    data = frame.rename(columns=column_map).copy()
    required = ["open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise RuntimeError(f"yfinance response for {symbol} missing columns: {missing}")
    if "adj_close" not in data.columns:
        data["adj_close"] = data["close"]
    data = data.reset_index().rename(columns={"Date": "trade_date"})
    if "trade_date" not in data.columns:
        data = data.rename(columns={data.columns[0]: "trade_date"})
    data["symbol"] = symbol
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.date
    numeric_columns = ["open", "high", "low", "close", "adj_close", "volume"]
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["open", "high", "low", "close", "volume"])
    return data[["symbol", "trade_date", *numeric_columns]]


def compute_pandas_ta_benchmark(ta: object, quotes: pd.DataFrame) -> pd.DataFrame:
    frames = []
    prepared = quotes.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"]).dt.date
    prepared["stock_ret"] = prepared.groupby("symbol", sort=False)["close"].pct_change()
    spy_returns = (
        prepared.loc[prepared["symbol"] == "SPY", ["trade_date", "stock_ret"]]
        .rename(columns={"stock_ret": "spy_ret"})
        .drop_duplicates("trade_date", keep="last")
    )
    prepared = prepared.merge(spy_returns, on="trade_date", how="left")
    for symbol, group in prepared.groupby("symbol", sort=False):
        data = group.sort_values("trade_date").copy()
        if symbol == "SPY" and symbol not in set(quotes["symbol"]):
            continue
        frames.append(_compute_symbol_pandas_ta(ta, data))
    return pd.concat(frames, ignore_index=True)


def _compute_symbol_pandas_ta(ta: object, data: pd.DataFrame) -> pd.DataFrame:
    high = data["high"]
    low = data["low"]
    close = data["close"]
    volume = data["volume"].fillna(0)
    out = data[["symbol", "trade_date"]].copy()
    for length in (5, 10, 20, 50, 200):
        out[f"sma_{length}"] = ta.sma(close, length=length)  # type: ignore[attr-defined]
    for length in (12, 26):
        out[f"ema_{length}"] = ta.ema(close, length=length)  # type: ignore[attr-defined]
    macd = ta.macd(close, fast=12, slow=26, signal=9)  # type: ignore[attr-defined]
    out["macd_line"] = _column(macd, "MACD_")
    out["macd_signal"] = _column(macd, "MACDs_")
    out["macd_histogram"] = _column(macd, "MACDh_")
    bbands = ta.bbands(close, length=20, std=2)  # type: ignore[attr-defined]
    out["bb_lower"] = _column(bbands, "BBL_")
    out["bb_middle"] = _column(bbands, "BBM_")
    out["bb_upper"] = _column(bbands, "BBU_")
    out["bb_width"] = _column(bbands, "BBB_") / 100
    out["rsi_14"] = ta.rsi(close, length=14)  # type: ignore[attr-defined]
    out["obv"] = ta.obv(close, volume)  # type: ignore[attr-defined]
    out["vwap_20"] = (close * volume).rolling(20).sum() / volume.rolling(20).sum()
    out["atr_14"] = ta.atr(high, low, close, length=14)  # type: ignore[attr-defined]
    out["std_20"] = data["stock_ret"].rolling(20).std()
    out["std_60"] = data["stock_ret"].rolling(60).std()
    adx = ta.adx(high, low, close, length=14)  # type: ignore[attr-defined]
    out["adx_14"] = _column(adx, "ADX_")
    out["di_plus_14"] = _column(adx, "DMP_")
    out["di_minus_14"] = _column(adx, "DMN_")
    high_52w = close.rolling(252).max()
    low_52w = close.rolling(252).min()
    out["pct_to_52w_high"] = (close - high_52w) / high_52w * 100
    out["pct_to_52w_low"] = (close - low_52w) / low_52w * 100
    out["pct_to_200ma"] = (close - out["sma_200"]) / out["sma_200"] * 100
    out["beta_60d"] = (
        data["stock_ret"].rolling(60).cov(data["spy_ret"])
        / data["spy_ret"].rolling(60).var().replace(0, np.nan)
    )
    out["ma200_slope_20d"] = (out["sma_200"] / out["sma_200"].shift(20) - 1) * 100
    return out


def _column(frame_or_series: pd.DataFrame | pd.Series | None, prefix: str) -> pd.Series:
    if frame_or_series is None:
        raise RuntimeError(f"pandas-ta returned no data for prefix {prefix}")
    if isinstance(frame_or_series, pd.Series):
        return frame_or_series
    for column in frame_or_series.columns:
        if str(column).startswith(prefix):
            return frame_or_series[column]
    raise RuntimeError(
        f"pandas-ta output missing column prefix {prefix}: {frame_or_series.columns}"
    )


def load_ours_from_db(symbols: list[str], start: date, end: date) -> pd.DataFrame:
    params: dict[str, object] = {"start": start, "end": end}
    placeholders = []
    for idx, symbol in enumerate(symbols):
        key = f"symbol_{idx}"
        params[key] = symbol
        placeholders.append(f":{key}")
    columns = ", ".join(["symbol", "trade_date", *INDICATOR_COLUMNS])
    sql = text(
        f"""
        SELECT {columns}
        FROM daily_indicators
        WHERE symbol IN ({", ".join(placeholders)})
          AND trade_date >= :start
          AND trade_date < :end
        ORDER BY symbol, trade_date
        """
    )
    return pd.read_sql_query(sql, PostgresClient().engine, params=params)


def load_ours_from_csv(path: Path, symbols: list[str], start: date, end: date) -> pd.DataFrame:
    data = pd.read_csv(path)
    data["symbol"] = data["symbol"].astype(str).str.upper()
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.date
    wanted = set(symbols)
    return data[
        data["symbol"].isin(wanted)
        & (data["trade_date"] >= start)
        & (data["trade_date"] < end)
    ].copy()


def choose_ours(
    symbols: list[str],
    start: date,
    end: date,
    quotes: pd.DataFrame,
    source: str,
    csv_path: str | None,
) -> tuple[pd.DataFrame, str, str | None]:
    if csv_path:
        return load_ours_from_csv(Path(csv_path), symbols, start, end), "csv", None
    if source == "compute":
        return compute_indicators(quotes), "compute", None
    try:
        ours = load_ours_from_db(symbols, start, end)
        if ours.empty:
            raise RuntimeError("daily_indicators query returned 0 rows")
        return ours, "db", None
    except Exception as exc:
        if source == "db":
            raise RuntimeError(f"Failed to load daily_indicators from DB: {exc}") from exc
        note = f"DB read unavailable ({exc}); report used local compute_indicators output as ours."
        return compute_indicators(quotes), "compute", note


def compare_all(
    ours: pd.DataFrame,
    theirs: pd.DataFrame,
    symbols: list[str],
    start: date,
    end: date,
    compare_tail: int,
) -> tuple[list[FieldResult], pd.DataFrame]:
    ours = normalize_indicator_frame(ours)
    theirs = normalize_indicator_frame(theirs)
    merged = ours.merge(theirs, on=["symbol", "trade_date"], suffixes=("_ours", "_their"))
    merged = merged[(merged["trade_date"] >= start) & (merged["trade_date"] < end)]
    results = []
    sample_rows = []
    for symbol in symbols:
        symbol_rows = merged[merged["symbol"] == symbol].sort_values("trade_date")
        symbol_rows = symbol_rows.tail(compare_tail)
        sample_dates = pick_sample_dates(symbol_rows["trade_date"], count=5)
        for field in TARGET_FIELDS:
            result = compare_field(symbol_rows, field, symbol)
            results.append(result)
            sample_rows.extend(build_samples(symbol_rows, symbol, field, sample_dates))
    return results, pd.DataFrame(sample_rows)


def normalize_indicator_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["symbol"] = data["symbol"].astype(str).str.upper()
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.date
    for column in TARGET_FIELDS:
        if column not in data.columns:
            data[column] = np.nan
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data[["symbol", "trade_date", *TARGET_FIELDS]]


def compare_field(rows: pd.DataFrame, field: str, symbol: str) -> FieldResult:
    ours = pd.to_numeric(rows[f"{field}_ours"], errors="coerce")
    theirs = pd.to_numeric(rows[f"{field}_their"], errors="coerce")
    valid = ours.notna() & theirs.notna()
    if valid.sum() == 0:
        return FieldResult(field, symbol, None, tolerance_for(field), "no_data", 0)
    if field == "obv":
        metric = obv_correlation(ours[valid], theirs[valid])
        status: Status = "pass" if metric >= OBV_MIN_CORRELATION else "fail"
        return FieldResult(field, symbol, metric, OBV_MIN_CORRELATION, status, int(valid.sum()))
    errors = error_series(ours[valid], theirs[valid], field)
    metric = float(errors.max())
    status = "pass" if metric <= tolerance_for(field) else "fail"
    return FieldResult(field, symbol, metric, tolerance_for(field), status, int(valid.sum()))


def error_series(ours: pd.Series, theirs: pd.Series, field: str) -> pd.Series:
    if field in POINT_TOLERANCES:
        return (ours - theirs).abs()
    return (ours - theirs).abs() / theirs.abs().clip(lower=1e-9)


def relative_error(ours: float, theirs: float) -> float:
    return abs(ours - theirs) / max(abs(theirs), 1e-9)


def tolerance_for(field: str) -> float:
    if field == "obv":
        return OBV_MIN_CORRELATION
    if field in POINT_TOLERANCES:
        return POINT_TOLERANCES[field]
    return RELATIVE_TOLERANCES[field]


def obv_correlation(ours: pd.Series, theirs: pd.Series) -> float:
    if len(ours) < 2:
        return 1.0 if float(ours.iloc[-1]) == float(theirs.iloc[-1]) else 0.0
    corr = ours.reset_index(drop=True).corr(theirs.reset_index(drop=True))
    if math.isnan(corr):
        return 0.0
    return float(corr)


def pick_sample_dates(dates: pd.Series, count: int = 5) -> list[date]:
    unique_dates = sorted(pd.Series(dates).dropna().unique())
    if len(unique_dates) <= count:
        return list(unique_dates)
    indexes = np.linspace(0, len(unique_dates) - 1, count).round().astype(int)
    return [unique_dates[int(idx)] for idx in indexes]


def build_samples(
    rows: pd.DataFrame,
    symbol: str,
    field: str,
    sample_dates: list[date],
) -> list[dict[str, object]]:
    samples = rows[rows["trade_date"].isin(sample_dates)]
    output = []
    for _, row in samples.iterrows():
        ours = row.get(f"{field}_ours")
        theirs = row.get(f"{field}_their")
        if pd.isna(ours) or pd.isna(theirs):
            err = np.nan
        elif field in POINT_TOLERANCES:
            err = abs(float(ours) - float(theirs))
        elif field == "obv":
            err = np.nan
        else:
            err = relative_error(float(ours), float(theirs))
        output.append(
            {
                "symbol": symbol,
                "date": row["trade_date"],
                "field": field,
                "ours": ours,
                "yfinance": theirs,
                "rel_err": err,
            }
        )
    return output


def write_report(
    output_path: Path,
    results: list[FieldResult],
    samples: pd.DataFrame,
    symbols: list[str],
    report_date: date,
    ours_source: str,
    source_note: str | None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    failed_fields = sorted({result.field for result in results if result.status != "pass"})
    passed = sum(1 for result in results if result.status == "pass")
    total = len(results)
    lines = [
        f"# daily_indicators 对账报告 · {report_date.isoformat()}",
        "",
        "## 摘要",
        f"- 通过字段:{passed} / {total}",
        f"- 超容差字段:{len(failed_fields)}",
        f"- ours 来源:{ours_source}",
    ]
    if source_note:
        lines.append(f"- 备注:{source_note}")
    if failed_fields:
        lines.append(f"- 建议修复:{', '.join(failed_fields)} · 详 §异常诊断")
    else:
        lines.append("- 建议修复:无")
    lines.extend(["", "## 全字段结果", field_results_table(results, symbols)])
    lines.extend(["", "## 抽样对比(5 个日期 · 每只票)", samples_table(samples)])
    lines.extend(["", "## 公式口径说明", formula_notes()])
    lines.extend(["", "## 异常诊断", diagnostics(failed_fields)])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def field_results_table(results: list[FieldResult], symbols: list[str]) -> str:
    by_field_symbol = {(result.field, result.symbol): result for result in results}
    rows = ["| 字段 | " + " | ".join(symbols) + " | 状态 |"]
    rows.append("|---|" + "|".join("---" for _ in symbols) + "|---|")
    for field in TARGET_FIELDS:
        cells = []
        statuses = []
        for symbol in symbols:
            result = by_field_symbol.get(
                (field, symbol),
                FieldResult(field, symbol, None, tolerance_for(field), "no_data", 0),
            )
            statuses.append(result.status)
            cells.append(format_result_cell(result))
        status = "通过" if all(item == "pass" for item in statuses) else "超容差"
        rows.append(f"| {field} | " + " | ".join(cells) + f" | {status} |")
    return "\n".join(rows)


def format_result_cell(result: FieldResult) -> str:
    if result.status == "no_data":
        return "无数据"
    marker = "PASS" if result.status == "pass" else "WARN"
    if result.field == "obv":
        metric = f"corr={result.metric:.4f}" if result.metric is not None else "corr=n/a"
    elif result.field in POINT_TOLERANCES:
        metric = f"max_abs={result.metric:.4f}" if result.metric is not None else "max_abs=n/a"
    else:
        metric = f"max_rel={result.metric:.4%}" if result.metric is not None else "max_rel=n/a"
    return f"{marker} {metric} n={result.samples}"


def samples_table(samples: pd.DataFrame) -> str:
    rows = ["| symbol | date | field | ours | yfinance | rel_err |", "|---|---|---|---:|---:|---:|"]
    if samples.empty:
        rows.append("| - | - | - | - | - | - |")
        return "\n".join(rows)
    sorted_samples = samples.sort_values(["symbol", "date", "field"])
    for _, row in sorted_samples.iterrows():
        rows.append(
            "| {symbol} | {date} | {field} | {ours} | {theirs} | {err} |".format(
                symbol=row["symbol"],
                date=row["date"],
                field=row["field"],
                ours=format_number(row["ours"]),
                theirs=format_number(row["yfinance"]),
                err=format_number(row["rel_err"]),
            )
        )
    return "\n".join(rows)


def format_number(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.6f}"


def formula_notes() -> str:
    return "\n".join(
        [
            "- 我方 RSI/ATR/ADX:Wilder 平滑，alpha = 1/N，pandas ewm(adjust=False)。",
            "- pandas-ta RSI/ATR/ADX:Wilder RMA 口径，主平滑系数 alpha = 1/N；",
            "  初始种子按库实现预热。",
            "- 业界主流:Wilder 原版、TradingView 默认 RMA、TA-Lib 默认均采用 Wilder 系列口径。",
            "- 判断建议:若仅初始化期有差异，不建议修 PR #9；",
            "  若尾部 RSI 超 2 点、ATR 超 2%、ADX/DI 超 3 点，",
            "  PR-OBS-2 应切换到主流 Wilder 初始化实现。",
        ]
    )


def diagnostics(failed_fields: list[str]) -> str:
    if not failed_fields:
        return "无异常字段。"
    blocks = []
    for field in failed_fields:
        if field in FORMULA_FIELDS:
            blocks.append(
                "\n".join(
                    [
                        f"### {field}",
                        "- 我方使用:Wilder alpha = 1/N = 0.0714，pandas ewm(adjust=False)。",
                        "- pandas-ta:Wilder RMA alpha = 1/N = 0.0714。",
                        "- 业界主流:Wilder 原版 / TradingView 默认 / TA-Lib 默认。",
                        "- 建议:若超容差发生在尾部稳定区，PR-OBS-2 对齐 "
                        "pandas-ta/TA-Lib 初始化规则；本 PR 不改主路径。",
                    ]
                )
            )
        else:
            blocks.append(
                "\n".join(
                    [
                        f"### {field}",
                        "- 诊断:该字段超出本 PR 配置容差。",
                        "- 建议:在 PR-OBS-2 检查输入价格源、rolling window、ddof、"
                        "EMA 初始化或 DB 历史预热长度。",
                    ]
                )
            )
    return "\n\n".join(blocks)


def run_reconcile(args: argparse.Namespace) -> ReconcileResult:
    ta, yf = require_external_modules()
    symbols = parse_symbols(args.symbols)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    fetch_start = start - timedelta(days=args.warmup_days)
    quotes = download_yfinance_quotes(yf, symbols, fetch_start, end)
    benchmark = compute_pandas_ta_benchmark(ta, quotes)
    ours, ours_source, source_note = choose_ours(
        symbols=symbols,
        start=start,
        end=end,
        quotes=quotes[quotes["symbol"].isin(set(symbols + ["SPY"]))],
        source=args.ours_source,
        csv_path=args.ours_csv,
    )
    results, samples = compare_all(ours, benchmark, symbols, start, end, args.compare_tail)
    output_path = Path(args.output)
    write_report(output_path, results, samples, symbols, end, ours_source, source_note)
    return ReconcileResult(results, samples, output_path, ours_source, source_note)


def main() -> None:
    try:
        result = run_reconcile(parse_args())
    except Exception as exc:
        print(f"reconcile_indicators failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    failures = [item for item in result.results if item.status != "pass"]
    print(f"wrote report: {result.report_path}")
    if failures:
        print(f"reconcile failed fields: {', '.join(sorted({item.field for item in failures}))}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
