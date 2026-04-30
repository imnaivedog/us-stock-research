# core-logic

# 核心逻辑 · us-stock-research V5.7

> 项目业务逻辑全貌 · codex 上手前理解这页 · 代码仅是这些逻辑的实现。
> 

> 
> 

> 完整设计文档原页：Notion 核心逻辑页（如需原文本请让用户 export）。
> 

## 1. 项目一句话

**个人美股波段 + 长线辅助决策系统** · 以双池（M · A）为载体 · 主题驱动 · 每日一轮 ETL+分析+推送 · 人在环决策。

## 2. 三层架构

```
reports/  →  analytics/  →  data/
  推送          计算          ETL
```

- **data**：stand-alone 资产 · 快照封存 · 半年才动
- **analytics**：实验场 · 热改 · experiment 输出 CSV 不污染 prod
- **reports**：推送 · 不交互 · Discord webhook

依赖单向：上层可 import 下层 · 下层不知道上层。

## 3. 双池设计

详见 `core/stock-pool.md`。一句话：

- **M 池**：未拥有 · ~1700 · 主题 β 信号 · SoT = etf_holdings + m_pool_overrides.yaml
- **A 池**：已拥有/却思考 · 5-15 · 个股 thesis 信号 + R:R · SoT = a_pool.yaml

## 4. 主题 SoT

- `config/themes.yaml` · 31 主题 · V5.7 新增·ADR-028
- a_pool.yaml.themes 未注册 → universe sync fail-fast

## 5. 三个 package·四套接口

```
usstock-data/         # ETL·出 CLI 主命令 usstock-data
usstock-analytics/    # 信号·评分·回测·experiment
usstock-reports/      # daily Discord·verdict.py·payload
usstock-mcp/          # 4 MCP 工具
schema/               # ddl.sql + migrate.py·独立
config/               # *.yaml SoT
```

## 6. ETL 数据流

```
FMP / FRED / Polygon / yfinance fallback
        ↓
ETL (data/etl.py)
        ↓
Postgres 17 · 22 表
        ↓
analytics 计算 (compute_indicators / themes_score / a_pool_signals)
        ↓
reports 推送 (daily Discord)
        ↓
Hermes 调 MCP 查询面
```

## 7. Daily 跳动顺序

```
22:30 UTC (06:30 CST 次日，周二-周六)
  → daily.sh · LightOS cron
      → usstock-data daily      # ETL·补齐 22 表
      → usstock-analytics       # 12 信号·三维评分·主题分
      → usstock-reports         # Discord payload 推送
  → 日志：~/logs/daily-YYYY-MM-DD.log
```

## 8. 12 类信号（A 池）

详见 `changes/2026-04-V5.7.md`。发信号点：B1-B5 买 · S1/S2a/S2b/S3 卖 · W1/W2 警告 hold · theme_oversold_entry 主题超卖入场。

## 9. 三维评分

弹性 35% / 性价比 30% / R:R 35% → A_Score ∈ [0,100]

主题加成：quintile=top +5 · quintile=bottom + theme_oversold_entry +3

## 10. Discord payload 结构

```
今日 dial（市场周期 / 风险偏好 / 主题热点）
ETF Top 3 主题
个股 Top 5（M+A 混合·按 A_Score）
A 池 highlights（近 thesis_stop / 近 target / hold 警告）
关键告警 ≤5（alert_log 不重复）
```

## 11. MCP

4 工具 · 详见 `core/architecture.md` §Hermes MCP 契约：

- `get_dial`
- `get_top_themes`
- `get_top_stocks(pool=m|a)`
- `query_signals`

## 12. 身份设定

- **用户** = Naive Dog · 单人维护 · 不代代码
- **codex** = 代码实施 · trunk 直推 · 不跳机部署
- **竹蜓蜓（Notion AI）** = 文档 · 审查 · Notion 侧

## 13. 安全红线

- 不接实盘 / 不接交易 API
- 不在 prod 上调试 · 本地重现后 atomic deploy
- 资金判断仅止于推送信号·人工交易

## 14. 当前状态 (2026-04-30)

- V5.7 任务书完整·部分代码已落
- LightOS Postgres 17 cutover Phase 0-3 完成·临时 ALTER 补齐·代码能跑
- daily ETL 有 corp/fund NoneType ERROR 海·源于 FMP free tier
- V5+1 任务书在 `handoff/04_V5_PLUS_1_TASKBOOK.md` · 6 patch 待交 codex