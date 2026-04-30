# principles

# us-stock-research 项目原则备忘录

> 事务原则 · codex 动手前读一遍 · 避免走偏。
> 

## 1. 项目身份

**个人美股波段 + 长线辅助决策系统** · 1 人维护 · 不替代真实交易。

**永不做**：实盘桥接 / Web Dashboard / 多用户 / 高频 / LLM 对 LLM 自动决策 / 过度可观测性。

## 2. 架构铁律

- **依赖单向**：reports → analytics → data
- **三层定位**：data 封存 / analytics 热改 / reports 不交互
- **smart data, dumb code** · 数据齐全则上层简单

## 3. 数据层铁律

- **现有 1.82M+ 行不动** · 任何 DROP 先 pg_dump
- **所有 schema 变更 idempotent** · ADD/CREATE IF NOT EXISTS
- **不重拉历史** · 缺字段从今日往前回填
- **表结构变更走 schema/ddl.sql + [migrate.py](http://migrate.py)** · 不在业务代码里 CREATE
- **a 池 SoT = config/a_pool.yaml** · DB 仅镜像 pool / is_active / thesis_added_at 三字段
- **themes SoT = config/themes.yaml** · a_pool.yaml.themes 必 ∈ themes.yaml.keys() · universe sync fail-fast
- **m_pool_overrides.yaml** · forced_in/forced_out · 一般留空

## 4. MCP 设计

- **返 raw structured data** · 不做 narrative 包装
- **MCP 是查询面标准化** · 不为某 client 定制
- **克制工具数** · 95% 用例够了 · 余用 SQL

## 5. 过度工程警戒线

- 单 package > 30 .py → 拆还是删？
- 单模块 > 500 行 → 真需要？
- 配置拆超 3 处 → 集中到 params.yaml
- 加表先问能不能复用
- **新功能入场考试**：3 个月后还有动力维护吗？

## 6. 调试与部署

- **不在 prod 上 hotfix 调试**
- **本地重写 · atomic deploy**
- **不分支 · trunk 直推**
- **一个 package 写完 push 一次**

## 7. 协作风格

- **用户**：验收 + 发部署指令 · 不改代码
- **codex**：写代码 · 本地跑通测试 · push trunk
- **竹蜓蜓**：结构化审查 · 文档归档 · 不代跳 codex 写代码
- **标记**：🪟 PowerShell / 🐧 LightOS bash · 勿混

## 8. 元原则

- **不空头承诺**：不说"我在做 X"但没调工具
- **不过度提议**：用户没要不提
- **修页前先 loadPage**
- **工具参数 JSON**·不是 Python literal

## 9. 已知技术坑

- `prepare_quotes` 必须 idempotent · 函数头 drop 旧 stock_ret/spy_ret
- `compute_indicators` 内部不重调 prepare_quotes
- `alert_log` / `events_calendar` 在 ddl.sql 里
- `symbol_universe` 加 `pool` 字段
- `quotes_daily` 加 `asset_class` 字段
- LightOS Postgres 17 · 5432 · 本地 dev 用 5433
- a_pool.yaml 语法错 → universe sync fail-fast 含行号
- a_pool.yaml.themes 未注册 → sync fail-fast
- A 池 shares_outstanding NULL → hold + alert WARN
- themes_score_daily 现产现耗 · 不向后填
- A 池 verdict_text 必骨架兑底 · LLM 失败不能让 daily 崩

## 10. V4→V5→V5.7 教训

- 代码散布 → monorepo 三 package
- schema 一次到位 · 勿拆二阶段
- 双池代码接口必须同步上 ADR 同时落地
- 回测依赖表一次补齐（corporate_actions / fundamentals / events_calendar）
- **schema 与算法紧耦合 · 下次设计先列算法菜单 · 从算法反推 schema** · 不预留二阶段

## 11. 起点问句表

- 这需求加东西还是减东西？加的话考试过吗？
- 现有表干不了吗？
- 本地能重现吗？不能为什么？
- MCP 返 raw 还是 narrative？
- basic infra 还是 algorithm？
- 有没有只说不做？