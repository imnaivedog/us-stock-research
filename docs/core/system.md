# System

Codex-facing system reference for `us-stock-research`. This file merges the old logic, architecture, stock-pool, and principles pages. Full design history remains in `_raw/`.

## Project Shape

Personal US stock research assistant for daily swing-trading signals and long-thesis timing. It does not trade, manage real cash, serve multiple users, or run intraday/high-frequency strategies.

Core principle: smart data, dumb code. Keep data complete and inspectable; keep analytics easy to change; keep output boring.

## Package Layers

Dependency direction is one-way:

```text
reports -> analytics -> data
```

| Layer | Package | Role |
| --- | --- | --- |
| Data | `usstock-data` | ETL, universe sync, `daily_indicators`, schema migration helpers |
| Analytics | `usstock-analytics` | M pool signals, A pool signals, themes, scoring, backtest, queries |
| Reports | `usstock-reports` | Notion row/page, Discord webhook, daily formatting |
| Query | `usstock-mcp` | Read-only MCP tools for Hermes and other clients |

Rules:

- Lower layers never import upper layers.
- Schema changes go through schema DDL/migration, not business code.
- Existing production data is protected; destructive migrations require explicit user approval and backup.
- MCP returns raw structured data, never narrative wrapping.

## Data Flow

```text
FMP / FRED / Polygon or Massive / yfinance fallback
  -> quotes_daily / macro_daily / corporate_actions / fundamentals / events_calendar
  -> universe sync: m_pool auto-curation + a_pool YAML mirror + themes validation
  -> daily_indicators: 30 shared technical fields
  -> themes_score_daily
  -> signals:
       M pool: L1 -> L2 -> L3 -> L4 -> macro
       A pool: calibration -> signals -> scoring -> verdict
  -> reports: Notion daily row/page + Discord webhook
  -> MCP: read-only query surface
```

Daily output follows ADR-033: no NAV block, no simulated-pool position block, no cloud-run simulated trading section. Backtest is local CLI only.

## Tables

The implementation SoT is the repo schema. Conceptually V5.7 uses:

| Area | Tables |
| --- | --- |
| Prices and macro | `quotes_daily`, `quotes_intraday`, `macro_daily` |
| Universe | `symbol_universe`, `symbol_universe_changes`, `sp500_members_daily`, `etf_holdings_latest`, `etf_holdings_snapshot` |
| Derived | `daily_indicators` |
| Themes | `themes_master`, `themes_members`, `themes_score_daily` |
| Company events | `corporate_actions`, `fundamentals_quarterly`, `events_calendar` |
| M signals | `signals_daily`, `signals_stock_daily`, `signals_alerts`, `signals_macro` |
| A signals | `a_pool_calibration`, `signals_a_pool_daily` |
| Ops | `alert_log` |

`daily_indicators` is M/A shared and must be read with `trade_date <= :as_of_date` in backtest-like contexts to avoid look-ahead bias.

## Field Contracts

`daily_indicators` is the shared technical feature table. V1 fields are grouped as:

| Group | Fields |
| --- | --- |
| Identity | `symbol`, `trade_date`, `computed_at` |
| Moving averages | `sma_5`, `sma_10`, `sma_20`, `sma_50`, `sma_200`, `ema_12`, `ema_26` |
| MACD | `macd_line`, `macd_signal`, `macd_histogram` |
| Bollinger | `bb_upper`, `bb_middle`, `bb_lower`, `bb_width` |
| Momentum | `rsi_14` |
| Volume | `obv`, `vwap_20` |
| Volatility | `atr_14`, `std_20`, `std_60` |
| Trend strength | `adx_14`, `di_plus_14`, `di_minus_14` |
| Position | `pct_to_52w_high`, `pct_to_52w_low`, `pct_to_200ma` |
| Relative / slope | `beta_60d`, `ma200_slope_20d` |

M signal outputs:

| Table | Contract |
| --- | --- |
| `signals_daily` | One row per day: `regime`, `regime_streak`, breadth fields, `sectors_top3`, `themes_top3`, `alert_count`, `macro_scenario`, `macro_btc_status` |
| `signals_stock_daily` | One row per symbol/day: `technical_score`, `sector_bonus`, `theme_bonus`, `final_score`, `rank`, `regime`, `entry_signal`, `exit_signal`, `warning_signal` |
| `signals_alerts` | Breadth/risk alerts from L2 and related daily warnings |
| `signals_macro` | 8 macro scenarios plus BTC risk-on/off confirmation |

## M Pool

M pool is the short-term momentum pool.

Universe source and filters:

- Sources: IVV + IJH + IJR + QQQ foreign members + Renaissance IPO ETF + Hermes/manual additions.
- Hard filters: market cap >= $1B, 20D average dollar volume >= $10M, `ipoDate >= 90d`, `actively_trading = true`.
- Dedup priority: IVV > IJH > IJR > QQQ_intl > IPO > Hermes > manual.
- Override SoT: `config/m_pool_overrides.yaml`.

Signal engine modules:

| Module | Output |
| --- | --- |
| L1 regime | `signals_daily.regime`, `regime_streak` |
| L2 breadth | `signals_alerts`, `signals_daily.breadth_*` |
| L3 sectors | `signals_daily.sectors_top3`, sector quadrant fields |
| L4 themes + stocks | `signals_daily.themes_top3`, `signals_stock_daily` |
| Macro | `signals_macro`, daily macro scenario |

## L1 Regime

Five risk dials:

| Dial | Position | Meaning |
| --- | --- | --- |
| S | 120% | Offensive |
| A | 100% | Standard |
| B | 80% | Discounted |
| C | 60% | Defensive |
| D | 20% | Trial exposure, not full cash |

S dial trigger:

- All 4 hard gates:
  - SPY at new high or <= 3% from monthly high.
  - 200MA breadth >= P85 over 5 years.
  - VIX < P20 and 10-day average < P30.
  - No FOMC / CPI / NFP / election in the next 7 days.
- At least 1 momentum confirmation:
  - 50MA breadth >= 70%.
  - NH/NL >= 3.
  - McClellan Oscillator >= +50.
- Confirmation: all gates + one momentum condition for 3 consecutive trading days.

Cooldown:

- A -> S requires at least 5 trading days since leaving S.
- Adjacent A/B/C/D same-direction changes require at least 2 trading days.
- S -> A is immediate when any hard gate breaks.
- Extreme events such as VIX +30% day can bypass adjacent cooldown.

## L2 Breadth

Key thresholds:

- 200MA breadth: 5-year P80 / P50 / P20.
- 50MA extreme: 5-year P95 / P5.
- 50MA warning bands: P90-P95 yellow, P95+ red.
- 50MA dulling: 2-year P75+ for consecutive days.
- Acceleration: 5-day change in 50MA breadth.
- Confirmation ladder: 1 day observe, 2 days warning, 3 days dial input, 5 days structural.
- Top divergence: index makes 20-day high while breadth fails to make high by >5%.
- Bottom reversal: VIX falls from P95+ to below P80 and breadth rebounds from P5 to P20+.
- McClellan is auxiliary, not a standalone dial trigger.

## L3 Sectors

11 SPDR sectors score on five dimensions: price trend, relative strength, breadth, flow, volatility.

Quadrant mapping uses two tracks and takes the more conservative result:

| Relative rank among 11 | Candidate quadrant |
| --- | --- |
| 1-2 | Leading |
| 3-4 | Strong |
| 5-7 | Neutral |
| 8-9 | Weak |
| 10-11 | Lagging |

| Sector own 5-year percentile | Highest allowed quadrant |
| --- | --- |
| >= P70 | Leading |
| P50-P70 | Strong |
| P30-P50 | Neutral |
| < P30 | Weak |

L3 is observational. It can add a sector bonus to L4 but cannot by itself create a buy signal.

## L4 Themes And Stocks

Theme SoT is `config/themes.yaml`.

Theme basket segments:

- V4/V5.7 launch weights: core 70%, diffusion 30%, concept 0%.
- V5 target weights: core 60%, diffusion 30%, concept 10%.

Theme state thresholds:

- Embryonic -> start: core RS > P70, theme volume share > 5%, at least 3 core names break out together.
- Start -> accelerate: theme score top 3, core 50MA bullish alignment > 80%.
- Volume yellow: 1-year P80 and 20D average volume >= 3-month average x 2.
- Volume red: 1-year P95 and 20D average volume >= 3-month average x 3 plus bearish next-day candle after volume expansion.
- Themes aged 6-12 months use age-to-date window and mark sample-insufficient; themes under 6 months skip volume warning.
- Accelerate -> decay: red volume control plus 3 days without new high, or core RS falls below P50 together.

M stock score contract:

```text
final_score = technical_score + sector_bonus + theme_bonus
```

The persisted row includes `symbol`, `as_of_date`, `technical_score`, `sector_bonus`, `theme_bonus`, `final_score`, `rank`, `regime`, `entry_signal`, `exit_signal`, and `warning_signal`.

## A Pool

A pool is long-thesis timing, not position management. It gives technical timing and R:R context for user-owned theses.

SoT:

- `config/a_pool.yaml` is the only source for thesis fields.
- DB mirrors only `pool`, `is_active`, and `thesis_added_at`.
- Do not mirror `thesis_stop_mcap_b`, `target_mcap_b`, `themes`, or `thesis_summary` into SQL.

YAML field semantics:

| Field | Meaning |
| --- | --- |
| `symbol` | Uppercase ticker |
| `status` | `active`, `watching`, or `removed`; only `active` is scored |
| `added` | `YYYY-MM-DD`, used for thesis aging |
| `thesis_stop_mcap_b` | Thesis invalidation market cap in USD billions; required for `active` |
| `target_mcap_b` | 3-5 year thesis target market cap in USD billions; required for `active` |
| `themes` | Must all exist in `config/themes.yaml`; sync fails fast with line/theme detail |
| `thesis_summary` | Human/LLM context; user-owned business text |

Runtime mcap conversion:

```python
thesis_stop_price = thesis_stop_mcap_b * 1e9 / shares_outstanding
target_price = target_mcap_b * 1e9 / shares_outstanding
strategic_rr = (target_price - close) / (close - thesis_stop_price)
```

If `shares_outstanding` is null, the symbol goes hold and writes `alert_log` WARN.

## A Pool Signals

V5.7 extends ADR-030's original 11-signal design to 12 signals by adding `theme_oversold_entry`.

| ID | Meaning |
| --- | --- |
| B1 | Pullback confirmation: pullback near typical profile range and close > 200MA |
| B2 | Breakout: close makes 60D high and volume > 1.5 x 20D average |
| B3 | Oversold reversal: RSI14 below per-symbol RSI P5 |
| B4 | MACD golden cross, fresh enough and at least 60D from previous cross |
| B5 | Strong support rebound: close near a calibrated support and closes green |
| S1 | Breaks support: below nearest strong support and >2% breach |
| S2a | Fast death cross: MA20 below MA50 |
| S2b | Slow death cross: MA50 below MA200 |
| S3 | Price/volume divergence: 60D high with RSI/volume divergence |
| W1 | Overheated: RSI14 > per-symbol P95 for 3D |
| W2 | Thesis aging: added >3y and close < target_price x 0.5 |
| theme_oversold_entry | A linked theme is bottom-quintile for 4W, price is > thesis_stop_price x 1.3, and recent B5 support fires |

Every signal needs a human explanation and a historical reference when available.

## A Pool Scoring

```text
A_Score = elasticity * 0.35 + value * 0.30 + rr * 0.35
```

Elasticity:

- ATR% cross-sectional percentile: 40%.
- Beta segment: 30%.
- 20D sigma cross-sectional percentile: 30%.

Value:

- Distance from 52W low: 30%.
- Distance from 200MA: 30%.
- Drawdown depth: 40%.
- Multiply by trend-health coefficient 0.50-1.00 based on 200MA 20D slope.

R:R:

- Strategic R:R filters add attempts; if <2, do not add.
- Tactical R:R is scored using next resistance and tactical stop.
- Tactical stop = max(50MA x 0.95, entry x 0.92, recent 20D support).
- Score tiers: >=3.0 => 85-100; 2.0-3.0 => 60-85; 1.5-2.0 => 30-60; <1.5 => 0.

Adjustments:

- >=2 B signals: +5.
- Any dimension <50: -10.
- Theme quintile top: +5.
- Theme bottom plus `theme_oversold_entry`: +3.
- Final range clamps to [0, 100].

## Reports

Notion daily:

- Row properties: date, regime, regime streak, SPY/VIX/macro summary, top themes/stocks, alert count.
- Page body: header, macro, L1, L2, L3, ETF top, stock top, A pool highlights, risk notes.
- Excludes simulated NAV and simulated positions per ADR-033.

Discord daily:

- One-line dial.
- ETF Top 3.
- M pool stock Top 5.
- A pool highlights when present.
- Up to 5 key alerts.

## MCP Contract

The read-only MCP tools are:

| Tool | Contract |
| --- | --- |
| `get_dial` | `(as_of?: date)` -> regime, streak, position, breadth, VIX |
| `get_top_themes` | `(as_of?: date, limit?: int)` -> ranked theme rows |
| `get_top_stocks` | `(pool: "m"|"a", as_of?: date, limit?: int)` -> ranked stock/signal rows |
| `query_signals` | `(symbol: str, days?: int)` -> raw signal history |

Do not add write tools without a new ADR and user approval.

## Maintenance Principles

- Add less than you think. If a feature fails the "will I maintain this in 3 months?" test, do not add it.
- Prefer reusing current tables before adding tables.
- Keep CLI behavior idempotent and rerunnable.
- Do not use LightOS as a development shell. Reproduce locally, then let the user deploy.
- User owns credentials, LightOS operations, A-pool thesis numbers, and Notion/Hermes side setup.
