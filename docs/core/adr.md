# ADR 索引

canonical 编号以 `docs/_raw/adr-source.md` 为准。不要把 ADR ID 复用成 implementation notes。代码引入新的架构决策时，追加 ADR-034 之后的新编号，或显式标记旧 ADR 被 superseded。

## 状态词表

- **Accepted / 已采纳**：当前代码应遵守的设计约束。
- **Superseded / 已被替代**：被后续 ADR 或 V5.7 implementation delta 缩窄或替代。
- **Implementation Delta / 实现增量**：`_raw/v5.7-taskbook-source.md` 改变了实现形态，但没有创建新的 canonical ADR。
- **Deprecated / 已废弃**：明确不再采用。
- **Open / 待定**：预留问题。

## Canonical ADRs

ADR 条目格式：英文 keyword + 中文一句话决策。

| ADR | Decision |
| --- | --- |
| ADR-001 | **L1-L4 layers**：四层体系与层级语义；L3 只观察，L4 才执行。状态：Accepted。 |
| ADR-002 | **Universe source**：个股池原设计为 SP Composite 1500 + QQQ foreign/ADR + IPO/Hermes/manual 补充；实现上已被 ADR-022/023/025 与 V5.7 m_pool curation 细节缩窄。状态：Superseded in implementation。 |
| ADR-003 | **Macro regime**：宏观板块改名为宏观定调，并保留 8 个宏观场景。状态：Accepted。 |
| ADR-004 | **Risk dial**：档位 S/A/B/C/D，对应仓位 120/100/80/60/20。状态：Accepted。 |
| ADR-005 | **Staged entry**：50/30/20 三段建仓。状态：Accepted for local backtest。 |
| ADR-006 | **R-multiple take profit**：R 倍三段止盈。状态：Accepted for local backtest。 |
| ADR-007 | **Two simulated pools**：ETF 池与个股池双模拟账户；日报部分被 ADR-033 替代，本地 backtest 保留。状态：Superseded for daily reports。 |
| ADR-008 | **Percentile windows**：分位窗口按用途差异化，不一刀切 5Y。状态：Accepted。 |
| ADR-009 | **Theme volume control**：主题量能用 1Y 分位 + 绝对成交量双控。状态：Accepted。 |
| ADR-010 | **BTC macro confirmation**：BTC 作为 risk-on/off 确认指标，不新增独立宏观场景。状态：Accepted。 |
| ADR-011 | **Simulator daily simplification**：模拟交易日报段曾被简化；后续被 ADR-033 彻底从日报移除。状态：Superseded。 |
| ADR-012 | **Notion/Discord split**：Notion 完整版 + Discord 简版双输出；按 ADR-033 去掉 NAV/模拟盘段。状态：Accepted with ADR-033 constraint。 |
| ADR-013 | **Page split**：Notion 大页拆成多个专题页；repo docs 重构后仅作历史背景。状态：Superseded by repo docs。 |
| ADR-014 | **Backtest start**：模拟/回测起点改为 2025-01-01，适配 FMP Starter 5Y 窗口。状态：Accepted for backtest。 |
| ADR-015 | **S dial trigger**：S 档量化为 4 硬门槛 + 1 动能确认 + 连续 3 日。状态：Accepted。 |
| ADR-016 | **Sector quadrant**：L3 板块象限采用相对排名 + 绝对分位地板，取更保守结果。状态：Accepted。 |
| ADR-017 | **Signal/simulator isolation**：信号池单向流，算法不得读取 simulator state；live/backtest 物理隔离。状态：Accepted，V5.7 runtime 做实现适配。 |
| ADR-018 | **Idempotency/trade_id**：日报幂等与 `trade_id` 去重；云端交易追踪被 ADR-033 替代，本地 backtest/report 幂等仍保留。状态：Superseded for cloud trading。 |
| ADR-019 | **Exit trigger priority**：7 条出场触发链优先级固定，5D 最小持有只约束主动换仓。状态：Retained for local backtest。 |
| ADR-020 | **Dial cooldown**：档位防抖采用不对称冷却，降档即时、升档带冷却。状态：Accepted。 |
| ADR-021 | **Notion row/body persistence**：Notion row properties + page body 双层持久化；按 ADR-033 删除 NAV 字段和模拟盘段。状态：Accepted but simplified。 |
| ADR-022 | **M pool ETF holdings source**：M 池装载源走 FMP ETF holdings。状态：Accepted as source principle。 |
| ADR-023 | **M pool hard filters**：M 池硬过滤为市值 >= $1B、20D dollar volume >= $10M、`ipoDate >= 90d`、`actively_trading=true`。状态：Accepted。 |
| ADR-024 | **Notion output-only**：Notion 只做输出展示，配置和数据源单向流动。状态：Accepted。 |
| ADR-025 | **Dynamic member management**：成员管理走本地月度 diff、软退休、多源去重。状态：Accepted。 |
| ADR-026 | **Bootstrap/Curation/Operate**：部署层分为 bootstrap、curation、operate 三阶段；V5.7 当前 prod 在 LightOS 跑。状态：Accepted with implementation delta。 |
| ADR-027 | **Postgres data store**：Postgres 是主数据仓；V5.7 从 Cloud SQL 形态适配为 LightOS Postgres 17。状态：Implementation Delta。 |
| ADR-028 | **themes.yaml seed**：`themes.yaml` 由 ETF 反推草案 + 用户 review 形成。状态：Accepted。 |
| ADR-029 | **Watchlist side table**：watchlist 是 thesis/协作旁路概念；当前 A 池 thesis SoT 改为 `config/a_pool.yaml`，watchlist 不等于交易头寸。状态：Implementation Delta。 |
| ADR-030 | **A pool sidecar**：A 池长线 thesis 技术择时作为 M 主算法旁路；V5.7 把原 11 信号扩为 12 信号。状态：Accepted with implementation delta。 |
| ADR-031 | **daily_indicators**：建立 M/A 共用 `daily_indicators` 技术指标装载层。状态：Accepted。 |
| ADR-032 | **M pool signals**：M 池信号引擎按 L1-L4 + Macro 五模块实施。状态：Accepted。 |
| ADR-033 | **ETL/local BI split**：云端/生产只负责信号与输出，模拟盘从日报剥离，改成本地 CLI backtest。状态：Accepted and decisive。 |

## 已废弃提案

来自 `_raw/adr-source.md`：

| ID | Proposal |
| --- | --- |
| X-01 | **Position warning section**：本系统不做真实持仓破位预警板块。状态：Deprecated。 |
| X-02 | **No take-profit**：不采用“无止盈，只等破位出场”。状态：Deprecated by ADR-006。 |
| X-03 | **Position-monitoring phase**：不在本 repo 内扩成持仓监控系统。状态：Deprecated。 |
| X-04 | **Macro in algorithm**：宏观不直接入算法，只做上下文参考。状态：Deprecated。 |
| X-05 | **20MA breadth arrow**：不把 20MA 宽度方向箭头纳入主判断。状态：Deprecated。 |
| X-06 | **L3 direct stock operation**：L3 不下沉直接触发个股操作。状态：Deprecated by ADR-001。 |

## V5.7 Implementation Notes

以下来自 `_raw/v5.7-taskbook-source.md`，不是新的 ADR 编号：

- monorepo 包结构为 data / analytics / reports / MCP。
- `config/a_pool.yaml` 是 A 池 SoT；核心 thesis 字段不镜像进 DB。
- A 池 mcap anchor 为 `thesis_stop_mcap_b` 和 `target_mcap_b`，运行时用 `shares_outstanding` 反推价格。
- A 池信号为 12 类：B1-B5、S1/S2a/S2b/S3、W1/W2、`theme_oversold_entry`。
- A 池评分为弹性/性价比/R:R = 35/30/35，子权重见 `system.md`。
- MCP 工具克制为 4 个 read-only 工具：`get_dial`、`get_top_themes`、`get_top_stocks`、`query_signals`。
- `verdict_text` 必须有 deterministic fallback，LLM 失败不能让 daily 崩。

## Codex 规则

1. 动代码前先查本页和 `system.md`。
2. 代码变更依赖某条 ADR 时，在 commit 或交付说明里写清 ADR ID。
3. 如果实现会冲突 ADR，先问用户，再同 commit 追加或 supersede ADR。
4. 不要再创建“新的 ADR-018”这类局部编号；那会让历史漂移。
