# architecture

# Architecture · 架构总览 + Hermes MCP 契约

> 当前态系统架构 · codex 改架构同 PR 改这里 · 这是 SoT
> 

## 1. 4 Packages 单 repo monorepo

```
us-stock-research/  (uv workspace)
├── packages/
│   ├── usstock-data/        # 数据层 · etl + universe + derived + schema
│   ├── usstock-analytics/   # 分析层 · signals/m_pool + signals/a_pool + themes + backtest + queries + mcp
│   ├── usstock-reports/     # 输出层 · notion + discord + formatters
│   └── usstock-mcp/         # MCP server · 暴露 Hermes 工具
├── config/                  # YAML SoT (a_pool / m_pool_overrides / themes)
├── deploy/                  # daily.sh / weekly_backup.sh
├── scripts/                 # 一次性脚本
└── docs/                    # 本目录树
```

依赖单向：reports → analytics → data · 下层不知道上层存在。

## 2. 22 表清单（V5.7 final）

**数据层 (13 现有 + 9 新增 = 22)**

| 类 | 表 | 关键 |
| --- | --- | --- |
| 行情 | `quotes_daily` | 含 `asset_class` (equity/crypto) |
| 行情 | `quotes_intraday` | 暂未用 |
| 宏观 | `macro_daily` | 含 dgs10/dgs2/ten_minus_two/dxy/wti/ief_close/hyg_lqd_spread/gold_silver_ratio |
| 成员 | `sp500_members_daily` | PIT 历史 |
| ETF | `etf_holdings_latest` / `etf_holdings_snapshot` |  |
| Universe | `symbol_universe` | 含 `pool` (m/a) / `is_active` / `thesis_added_at` / `shares_outstanding` |
| Universe | `symbol_universe_changes` | 审计 |
| 公司 | `corporate_actions` | splits + dividends 历史 |
| 公司 | `fundamentals_quarterly` | 季报关键科目 |
| 公司 | `events_calendar` | 财报日 + 拆股 |
| 派生 | `daily_indicators` | 30 字段技术指标（M+A 共用 SoT） |
| 主题 | `themes_master` / `themes_members` / `themes_score_daily` | V5.7 新增 |
| A 池 | `a_pool_calibration` | per-symbol 5Y 画像 · 周更 |
| 信号 | `signals_daily` (M 池) / `signals_stock_daily` / `signals_alerts` / `signals_macro` |  |
| 信号 | `signals_a_pool_daily` | A 池信号物理隔离 |
| 运维 | `alert_log` | INFO/WARN/ERROR |

## 3. 双池语义（核心）

- **M 池 (短线 · m_pool)**: 自动准入 ~1784 只 · 纯技术动量波段
- **A 池 (长线 · a_pool)**: 用户 thesis 跟踪 5-20 只 · YAML SoT 不入 DB 核心字段
- **物理隔离 ADR-030**: M 信号引擎 SELECT 不访问 A 表 · A 引擎 SELECT 不写 M 表
- **共享**: M2 数据流水线 (`quotes_daily` / `daily_indicators` / `macro_daily` / `themes_score_daily`)

### A 池 mcap 反推（V5.7 关键）

YAML 锚 `thesis_stop_mcap_b` / `target_mcap_b` (单位 B 美元) → 运行时反推：

```python
thesis_stop_price = thesis_stop_mcap_b * 1e9 / shares_outstanding
target_price = target_mcap_b * 1e9 / shares_outstanding
strategic_rr = (target_price - close) / (close - thesis_stop_price)
```

好处：拆股/增发免疫 · 跨标的可比 · 基本面方法天然出市值。

## 4. A 池 12 类信号（§A.3）

**入场 B 类 5 个**: B1 回踩确认 / B2 突破阻力 (B2a 警告 + B2b 入场) / B3 超卖反转 / B4 均线金叉 / B5 强支撑反弹

**出场 S 类 4 个**: S1 跌破支撑 / S2a 死叉警告 (20/50) / S2b 深度死叉 (50/200) / S3 量价背离

**警示 W 类 2 个**: W1 过热区 / W2 thesis 时间老化

**主题加成 1 类**: theme_oversold_entry (主题 quintile=bottom + 个股超卖)

## 5. A 池三维评分（§A.4）

```
A_Score = 弹性 × 0.35 + 性价比 × 0.30 + R:R × 0.35
```

- **弹性 35%**: ATR% 横向分位 40% + β 分段 30% + 20D σ 横向分位 30%
- **性价比 30%**: 价值原始分 (距 52W 低 30% + 距 200MA 30% + 回撤深度 40%) × 趋势健康系数 (0.50-1.00)
- **R:R 35%**: 战略 R:R 仅过滤 (<2 禁加仓) · 战术 R:R 真打分
- 信号加成: ≥2 个 B 信号 → +5
- 一致性扣: 任一维 <50 → A_Score -10

**主题加成**: a_pool 标的的 themes[] 主题分数 quintile='top' → +5 · 'bottom' + 触发第 12 类信号 → +3

## 6. M 池档位（§3 五档 · ADR-020）

S=120% / A=100% / B=80% / C=60% / D=20% · 不对称冷却 (A→S 5 日 · 相邻 2 日 · 降档即时)

## 7. Hermes MCP 接口契约（重要）

**usstock-mcp 包暴露 4 个 MCP 工具**：

| Tool | 签名 | 返回 |
| --- | --- | --- |
| `get_dial` | `(as_of?: date)` | `{regime, regime_streak, position_pct, breadth_*, vix, vix_pctl_5y}` |
| `get_top_themes` | `(as_of?: date, limit?: int=10)` | `[{theme_id, name, momentum_score, quintile, rank}]` |
| `get_top_stocks` | `(pool: 'm'\ | 'a', as_of?: date, limit?: int=20)` |
| `query_signals` | `(symbol: str, days?: int=30)` | `[{trade_date, ...signals}]` |

**契约规则**：

1. **返回 raw structured data** · 不做 narrative 包装（原则备忘录 §4）
2. **Hermes 是 MCP 客户端 · 上游团队/项目维护接入** · 本 repo 不管 Hermes 端
3. **签名稳定** · 加新工具 OK · 改老工具签名需写 ADR
4. **同步更新 [architecture.md](http://architecture.md) 第 7 节** · 任何工具变化
5. **不直接执行交易/写库** · MCP server 仅查询（read-only）

## 8. 数据流

```
FMP/FRED/Polygon API
  ↓ etl
quotes_daily / macro_daily / corporate_actions / fundamentals / events_calendar / shares_outstanding
  ↓ universe sync (m curate + a YAML 加载 + themes 校验)
symbol_universe (双池标记)
  ↓ compute_indicators
daily_indicators (30 字段 · M+A 共用)
  ↓ themes_score_daily (主题动量榜)
  ↓ signals (M 池: dial→breadth→sector→theme→stock→macro · A 池: calibration→signals→scoring→verdict)
signals_daily / signals_stock_daily / signals_a_pool_daily / signals_alerts
  ↓ reports
Notion daily DB row + page · Discord webhook
```

## 9. 调度（cron 双版本）

| Job | UTC | Asia/Shanghai |
| --- | --- | --- |
| [daily.sh](http://daily.sh) | 22:30 周一-五 | 06:30 周二-六 |
| weekly_[backup.sh](http://backup.sh) | 20:00 周六 | 04:00 周日 |
| calibrate-a-pool (周更) | TBD 周一 17:00 UTC | 周一 01:00 |

## 10. 关键 ADR 锚

- ADR-017 信号池隔离
- ADR-022/023/025 M 池装载源 + 硬过滤 + 多源去重
- ADR-024 Notion 输出-only · 数据单向流
- ADR-026 三阶段架构 (Bootstrap/Curation/Operate)
- ADR-027 Cloud SQL Postgres (V5.7 已迁 LightOS Postgres)
- ADR-028 themes.yaml C 混合
- ADR-029 watchlist 旁路表 (V5.7 已合并到 a_pool)
- ADR-030 A 池长线 thesis 平行旁路
- ADR-031 daily_indicators 装载层
- ADR-032 M 池信号引擎 5 子模块
- ADR-033 云端 ETL + 本地 BI 分层

详见 `core/adr.md`。