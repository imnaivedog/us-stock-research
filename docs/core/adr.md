# adr

# ADR · 架构决策记录集

> 本页为 ADR 索引·各条主题与状态。原始完整决议文（背景 / 选项对比 / 代价）请从 Notion ADR 页 export（本仓留主题 + 关键决策）。
> 

> 
> 

> codex 需在代码中恢复某条 ADR 上下文时·在 PR description 里引用该 ADR ID + 关键决策。
> 

## ADR 状态定义

- **Accepted**：已落地·代码应符合
- **Superseded**：被后者取代·表明取代的 ADR ID
- **Proposed**：在审
- **Deprecated**：不再适用·但代码可能还有残留

## V5 前 ADR-001 ~ ADR-017

这些是 V4 / V5 前期决议。现阶段大多已 Accepted 或 Superseded。如 codex 需某条详情·请让用户从 Notion ADR 页提供。

关键几条列举（记住主题即可）：

- **ADR-013**：三层架构 reports/analytics/data
- **ADR-014**：依赖单向·不跨层反向依赖
- **ADR-015**：双池雏形·本阶段实现后 V5.7 调整 (superseded by ADR-022)
- **ADR-016**：Postgres 为唯一 prod 仓·本地 dev 可 SQLite
- **ADR-017**：analytics experiment CSV 输出·不污染 prod 表

## V5.7 新增 ADR-018 ~ ADR-033

### ADR-018 · schema/ddl.sql 集中·[migrate.py](http://migrate.py) 幂等

- **决策**：所有表结构变更走 schema/ddl.sql + scripts/[migrate.py](http://migrate.py)·业务代码不 CREATE·跑两遍不出错
- **状态**：Accepted

### ADR-019 · corporate_actions 表·拆股增发复权

- **决策**：新增 corporate_actions 表·记 stock_split / stock_dividend / cash_dividend · 回测复权依赖
- **状态**：Accepted·codex V5+1 需修 FMP free tier fallback

### ADR-020 · fundamentals 表·季度财务

- **决策**：fundamentals 表记季度 income/balance/cashflow·供财务画像与拐点信号使用
- **状态**：Accepted·codex V5+1 需修 FMP free tier fallback

### ADR-021 · events_calendar 表·catalyst 临近信号

- **决策**：events_calendar 表记财报/分拆/FOMC/产品发布·驱动 B2 / S2a 信号
- **状态**：Accepted

### ADR-022 · 双池 SoT 走 yaml

- **决策**：a 池 SoT = config/a_pool.yaml·m 池 override = config/m_pool_overrides.yaml·DB 仅镜像 3 字段·仅 yaml 为人/Codex/Hermes 共同入口
- **状态**：Accepted·取代 ADR-015 实现细节

### ADR-023 · 价格锁 → 市值锁

- **决策**：a_pool.yaml 用 thesis_stop_mcap_b / target_mcap_b·价格运行时反推 mcap*1e9/shares_outstanding·拆股增发免疫
- **状态**：Accepted

### ADR-024 · shares_outstanding NULL 走 hold + alert

- **决策**：ETL 拉取失败不静默·该标的今日信号走 hold + alert_log WARN
- **状态**：Accepted

### ADR-025 · alert_log · 告警不重复推送

- **决策**：alert_log 表记已推送告警·category 区分·daily report 取未推送的·避免骚扰
- **状态**：Accepted

### ADR-026 · watchlist 表·独立概念

- **决策**：watchlist 表同 watchlist·跨双池·记 target_market_cap / thesis_url / updated_at·不作为交易头寸
- **状态**：Accepted

### ADR-027 · themes_score_daily · 现产现耗

- **决策**：主题评分仅走今日·不向后填·某日某主题缺→该主题代表股一律 hold
- **状态**：Accepted

### ADR-028 · themes SoT = themes.yaml

- **决策**：config/themes.yaml 为主题词典唯一源·codex 从 etf_holdings 反推草案·用户 review PR merge·a_pool.yaml.themes 必 ∈ themes.yaml.keys()·universe sync fail-fast
- **状态**：Accepted·V5.7 新增

### ADR-029 · 三维评分

- **决策**：弹性 35% / 性价比 30% / R:R 35% → A_Score ∈ [0,100]·主题加成走 §A.5·不走连乘
- **状态**：Accepted·codex V5+1 需实现

### ADR-030 · 12 类 A 池信号

- **决策**：B1-B5 买 · S1/S2a/S2b/S3 卖 · W1/W2 警告 hold · theme_oversold_entry 主题超卖入场·不加 13 类·克制
- **状态**：Accepted·codex V5+1 需实现

### ADR-031 · MCP 工具 8 → 4

- **决策**：get_dial / get_top_themes / get_top_stocks(pool=m|a) / query_signals·Hermes 95% 用例够了·余走 SQL·返 raw structured·不 narrative 包装
- **状态**：Accepted

### ADR-032 · verdict_text 骨架兑底

- **决策**：[verdict.py](http://verdict.py) LLM 全路径 fallback·LLM 失败/GCP 超限/key 过期 任一·verdict_text 走骨架 【代码】A_Score=X · top_signal · 入场 Y / 止损 Z · daily 不崩
- **状态**：Accepted·codex V5+1 需实现

### ADR-033 · trunk 直推 · 不分支

- **决策**：个人项目不开 PR 分支·codex 本地跑通测试后直推 origin master·push 频率 = 1 commit / package·master→main 重命名留给用户决定时机
- **状态**：Accepted

## codex 使用须知

1. 动代码前·查是否有相关 ADR·遵其决策·不走偏
2. PR description 里引用 ADR ID·例：`per ADR-022, a-pool reads from a_pool.yaml not DB`
3. 不同意某 ADR · 不要静默走偏 · 提出辩论·让用户决是否补一条 superseded ADR
4. ADR 本页唯读·codex 不修·只加·加走 PR 同 commit