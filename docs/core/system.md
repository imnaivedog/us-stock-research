# System

Codex 面向的系统参考页。它合并了旧的 core logic、architecture、stock pool、principles。完整设计历史仍保留在 `_raw/`。

## 项目定位

个人美股研究助手，用于日级 swing-trading 信号和 long-thesis 技术择时。它不交易、不管理真实资金、不服务多用户、不做 intraday / high-frequency。

核心原则：smart data, dumb code。数据尽量完整可查；analytics 便于热改；output 保持朴素。

## Package 层级

依赖方向单向：

```text
reports -> analytics -> data
```

| Layer | Package | 职责 |
| --- | --- | --- |
| Data | `usstock-data` | ETL、universe sync、`daily_indicators`、schema migration helpers |
| Analytics | `usstock-analytics` | M 池 signals、A 池 signals、themes、scoring、backtest、queries |
| Reports | `usstock-reports` | Notion row/page、Discord webhook、daily formatting |
| Query | `usstock-mcp` | 给 Hermes 和其它 client 的 read-only MCP tools |

规则：

- 下层永远不 import 上层。
- schema 变更走 DDL / migration，不写进业务代码。
- `ddl.sql` 顺序固定为 CREATE TABLE -> ALTER TABLE ADD/DROP COLUMN -> CREATE INDEX，保证旧表先补列再建索引。
- 生产历史数据受保护；destructive migration 必须先得到用户明确批准并备份。
- MCP 返回 raw structured data，不做 narrative 包装。
- data / analytics / reports 三层 CLI 都会通过各自 DB helper 自动读取 repo root `.env`；显式 shell env 优先，不被覆盖。
- data / analytics / reports 的 `DATABASE_URL` 可写 `postgres://` / `postgresql://`；运行时统一 normalize 为 `postgresql+psycopg://`。
- 如果 `DATABASE_URL` 只有 username 但缺 password，且 `POSTGRES_PASSWORD` 存在，三层 DB helper 会补 password 后再建 engine。
- `corporate_actions` / `fundamentals` / `earnings_calendar` 是 best-effort ETL；provider tier 或 endpoint unavailable 类 skip 不阻塞 daily，transient/provider outage 仍保留 ERROR。

## 数据流

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

daily output 遵守 ADR-033：不含 NAV block、不含模拟盘仓位 block、不含云端模拟交易段。backtest 仅作为本地 CLI。

## 数据表

实现 SoT 以 repo schema 为准。V5.7 概念上使用：

| 范围 | Tables |
| --- | --- |
| 行情与宏观 | `quotes_daily`, `quotes_intraday`, `macro_daily` |
| Universe | `symbol_universe`, `symbol_universe_changes`, `sp500_members_daily`, `etf_holdings_latest`, `etf_holdings_snapshot` |
| Derived | `daily_indicators` |
| Themes | `themes_master`, `themes_members`, `themes_score_daily` |
| Company events | `corporate_actions`, `fundamentals_quarterly`, `events_calendar` |
| M signals | `signals_daily`, `signals_stock_daily`, `signals_alerts`, `signals_macro` |
| A signals | `a_pool_calibration`, `signals_a_pool_daily` |
| Ops | `alert_log` |

`daily_indicators` 是 M/A 共享表。backtest 类场景读取时必须带 `trade_date <= :as_of_date`，避免 look-ahead bias。

## 字段契约

`daily_indicators` 是共享技术特征表。V1 字段分组：

| 分组 | Fields |
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

M signal 输出：

| Table | Contract |
| --- | --- |
| `signals_daily` | 每日一行：`regime`, `regime_streak`, breadth fields, `sectors_top3`, `themes_top3`, `alert_count`, `macro_scenario`, `macro_btc_status` |
| `signals_stock_daily` | 每 symbol / day 一行：`technical_score`, `sector_bonus`, `theme_bonus`, `final_score`, `rank`, `regime`, `entry_signal`, `exit_signal`, `warning_signal` |
| `signals_alerts` | L2 breadth / risk alerts 与相关 daily warnings |
| `signals_macro` | 8 个 macro scenarios + BTC risk-on/off confirmation |

## M 池

M 池是短线动量池。

Universe 来源与过滤：

- 来源：IVV + IJH + IJR + QQQ foreign members + Renaissance IPO ETF + Hermes/manual additions。
- 硬过滤：market cap >= $1B，20D average dollar volume >= $10M，`ipoDate >= 90d`，`actively_trading = true`。
- 去重优先级：IVV > IJH > IJR > QQQ_intl > IPO > Hermes > manual。
- override SoT：`config/m_pool_overrides.yaml`。

Signal engine modules：

| Module | Output |
| --- | --- |
| L1 regime | `signals_daily.regime`, `regime_streak` |
| L2 breadth | `signals_alerts`, `signals_daily.breadth_*` |
| L3 sectors | `signals_daily.sectors_top3`, sector quadrant fields |
| L4 themes + stocks | `signals_daily.themes_top3`, `signals_stock_daily` |
| Macro | `signals_macro`, daily macro scenario |

## L1 Regime

五档 risk dial：

| Dial | Position | 含义 |
| --- | --- | --- |
| S | 120% | 进攻 |
| A | 100% | 标准 |
| B | 80% | 打折 |
| C | 60% | 防守 |
| D | 20% | 试水，不是 full cash |

S 档触发：

- 4 个 hard gates 全部满足：
  - SPY 当日新高，或距月线新高 <= 3%。
  - 200MA breadth >= 5Y P85。
  - VIX < P20 且 10-day average < P30。
  - 未来 7 日无 FOMC / CPI / NFP / election。
- 至少 1 个 momentum confirmation：
  - 50MA breadth >= 70%。
  - NH/NL >= 3。
  - McClellan Oscillator >= +50。
- 时间确认：hard gates + 任一 momentum condition 连续 3 个交易日成立。

Cooldown：

- A -> S：距上次离开 S 至少 5 个交易日。
- A/B/C/D 相邻同向切换：至少间隔 2 个交易日。
- S -> A：任一 hard gate 破坏时立即降档。
- VIX 单日 +30% 等 extreme events 可绕过相邻 cooldown。

## L2 Breadth

关键阈值：

- 200MA breadth：5Y P80 / P50 / P20。
- 50MA extreme：5Y P95 / P5。
- 50MA warning bands：P90-P95 yellow，P95+ red。
- 50MA dulling：2Y P75+ 连续多日。
- Acceleration：50MA breadth 的 5-day change。
- Confirmation ladder：1 日观察，2 日 warning，3 日进入 dial input，5 日视为 structural。
- Top divergence：指数创 20-day high，但 breadth 未创新高且差 >5%。
- Bottom reversal：VIX 从 P95+ 回落到 P80 以下，同时 breadth 从 P5 反转到 P20+。
- McClellan 是辅助指标，不单独触发 dial。

## L3 Sectors

11 个 SPDR sectors 按五维评分：price trend、relative strength、breadth、flow、volatility。

象限映射使用双轨，并取更保守结果：

| 11 个 sector 内相对排名 | Candidate quadrant |
| --- | --- |
| 1-2 | Leading |
| 3-4 | Strong |
| 5-7 | Neutral |
| 8-9 | Weak |
| 10-11 | Lagging |

| sector 自身 5Y percentile | 允许最高象限 |
| --- | --- |
| >= P70 | Leading |
| P50-P70 | Strong |
| P30-P50 | Neutral |
| < P30 | Weak |

L3 只观察。它可以给 L4 sector bonus，但不能单独产生 buy signal。

## L4 Themes And Stocks

Theme SoT 是 `config/themes.yaml`。

Theme basket segments：

- V4/V5.7 launch weights：core 70%，diffusion 30%，concept 0%。
- V5 target weights：core 60%，diffusion 30%，concept 10%。

Theme state thresholds：

- Embryonic -> start：core RS > P70，theme volume share > 5%，至少 3 个 core names 同步 breakout。
- Start -> accelerate：theme score top 3，core 50MA bullish alignment > 80%。
- Volume yellow：1Y P80 且 20D average volume >= 3-month average x 2。
- Volume red：1Y P95 且 20D average volume >= 3-month average x 3，并且放量后次日收阴。
- 成立 6-12 个月的 themes 用 age-to-date window，并标记样本不足；不足 6 个月则跳过 volume warning。
- Accelerate -> decay：red volume control + 3 日不创新高，或 core RS 集体跌破 P50。

M stock score contract：

```text
final_score = technical_score + sector_bonus + theme_bonus
```

持久化行包含 `symbol`, `as_of_date`, `technical_score`, `sector_bonus`, `theme_bonus`, `final_score`, `rank`, `regime`, `entry_signal`, `exit_signal`, `warning_signal`。

## A 池

A 池是 long-thesis timing，不是 position management。它给用户 thesis 提供技术择时和 R:R 上下文。

SoT：

- `config/a_pool.yaml` 是 thesis 字段唯一来源。
- DB 仅镜像 `pool`、`is_active`、`thesis_added_at`。
- 不把 `thesis_stop_mcap_b`、`target_mcap_b`、`themes`、`thesis_summary` 镜像到 SQL。

YAML 字段语义：

| Field | 含义 |
| --- | --- |
| `symbol` | 大写 ticker |
| `status` | `active`, `watching`, `removed`；只有 `active` 会评分 |
| `added` | `YYYY-MM-DD`，用于 thesis aging |
| `thesis_stop_mcap_b` | thesis 失效市值，单位 USD billions；`active` 必填 |
| `target_mcap_b` | 3-5Y thesis 目标市值，单位 USD billions；`active` 必填 |
| `themes` | 必须全部存在于 `config/themes.yaml`；sync fail-fast 并给出 line/theme detail |
| `thesis_summary` | 人读 / LLM context；业务文字由用户维护 |

runtime mcap conversion：

```python
thesis_stop_price = thesis_stop_mcap_b * 1e9 / shares_outstanding
target_price = target_mcap_b * 1e9 / shares_outstanding
strategic_rr = (target_price - close) / (close - thesis_stop_price)
```

如果 `shares_outstanding` 为 null，该 symbol 当日走 hold，并写 `alert_log` WARN。

## A 池 Signals

V5.7 把 ADR-030 原 11-signal design 扩为 12 signals，新增 `theme_oversold_entry`。

| ID | 含义 |
| --- | --- |
| B1 | 回踩确认：pullback 接近画像 typical range，且 close > 200MA |
| B2 | 突破：close 创 60D high，且 volume > 1.5 x 20D average |
| B3 | 超卖反转：RSI14 低于 per-symbol RSI P5 |
| B4 | MACD golden cross，且足够新鲜，并距上次 cross 至少 60D |
| B5 | 强支撑反弹：close 接近 calibrated support 且收阳 |
| S1 | 跌破支撑：跌破最近 strong support 且 breach >2% |
| S2a | fast death cross：MA20 下穿 MA50 |
| S2b | slow death cross：MA50 下穿 MA200 |
| S3 | 价量背离：60D high 伴随 RSI / volume divergence |
| W1 | 过热：RSI14 > per-symbol P95 连续 3D |
| W2 | thesis aging：added >3y 且 close < target_price x 0.5 |
| theme_oversold_entry | 关联 theme 连续 4W bottom-quintile，price > thesis_stop_price x 1.3，且近期触发 B5 support |

每个 signal 在可用时都需要 human explanation 和 historical reference。

## A 池 Scoring

```text
A_Score = elasticity * 0.35 + value * 0.30 + rr * 0.35
```

Elasticity：

- ATR% cross-sectional percentile：40%。
- Beta segment：30%。
- 20D sigma cross-sectional percentile：30%。

Value：

- 距 52W low：30%。
- 距 200MA：30%。
- Drawdown depth：40%。
- 再乘 trend-health coefficient 0.50-1.00，基于 200MA 20D slope。

R:R：

- Strategic R:R 只过滤加仓；若 <2，不加仓。
- Tactical R:R 真正参与打分，使用 next resistance 与 tactical stop。
- tactical stop = max(50MA x 0.95, entry x 0.92, recent 20D support)。
- Score tiers：>=3.0 => 85-100；2.0-3.0 => 60-85；1.5-2.0 => 30-60；<1.5 => 0。

Adjustments：

- >=2 个 B signals：+5。
- 任一维度 <50：-10。
- Theme quintile top：+5。
- Theme bottom + `theme_oversold_entry`：+3。
- 最终 clamp 到 [0, 100]。

## Reports

Notion daily：

- Row properties 使用固定字段名：`Name`, `Date`, `Dial`, `Regime`, `Position`, `Breadth Score`, `Macro State`, `Alerts`, `Top Sectors`, `Top Themes`, `Top Stocks`, `A Pool Highlights`。
- Page body：header、macro、L1、L2、L3、ETF top、stock top、A pool highlights、risk notes。
- 按 ADR-033 排除 simulated NAV 和 simulated positions。

Discord daily：

- 一行 dial。
- ETF Top 3。
- M 池 Stock Top 5。
- A pool highlights（若有）。
- 最多 5 条 key alerts。

## MCP Contract

read-only MCP tools：

| Tool | Contract |
| --- | --- |
| `get_dial` | `(as_of?: date)` -> regime, streak, position, breadth, VIX |
| `get_top_themes` | `(as_of?: date, limit?: int)` -> ranked theme rows |
| `get_top_stocks` | `(pool: "m"|"a", as_of?: date, limit?: int)` -> ranked stock/signal rows |
| `query_signals` | `(symbol: str, days?: int)` -> raw signal history |

没有新 ADR 和用户批准，不增加 write tools。

## 维护原则

- 少加东西。过不了“3 个月后还愿不愿意维护？”测试，就不要加。
- 加表前优先想能不能复用现有表。
- CLI 行为保持 idempotent、可重跑。
- 不把 LightOS 当 dev shell。本地复现，用户再部署。
- 用户负责 credentials、LightOS ops、A 池 thesis numbers、Notion/Hermes 侧 setup。
