# 01 · 项目上下文与环境快照

<aside>
🏗️

读完掌握：项目目标 / 架构 / 双池 / 关键概念 / LightOS 环境 / Win 本地 / GitHub 状态。

</aside>

## 项目目标

**日级双池股票研究系统**：每个交易日 ~UTC 22:30 自动跑 daily 流水线 · 把 m 池（量化 ~1784 大盘股）和 a 池（人工长线 thesis ~5 个 · 当前空骨架）的信号写到 Postgres + Notion daily DB + Discord webhook · 提供 4 工具 MCP server 给 Hermes（占位）查询。

## 架构 · 4 packages（uv workspace · monorepo）

| 包 | 职责 |
| --- | --- |
| `usstock-data` | ETL 拉数据（FMP/FRED/Polygon→Massive）+ schema migrate + universe sync + compute_indicators |
| `usstock-analytics` | themes-score + signals 引擎（m 池 12 类信号 / a 池长线 thesis）+ 三维评分 |
| `usstock-reports` | Notion row+page writer（含 a_pool highlights）+ Discord webhook |
| `usstock-mcp` | 4 工具 MCP server（get_dial / get_top_themes / get_top_stocks / query_signals） |

**数据库**：Postgres 17 · `usstock` database · 22 张表（13 现有 + 4 新增 + 3 themes + 2 A 池）

**输出**：Notion daily DB（每日 1 行 + 详情页含 a_pool highlights）· Discord webhook（dial + ETF Top 3 + 个股 Top 5 + a_pool highlights + ≤5 关键告警）

## 双池 SoT（Source of Truth · YAML）

- `config/a_pool.yaml` = `[]` 空骨架（cutover 完成后用户填 5 thesis：LITE/COHR/MRVL/WDC/SNDK）
- `config/m_pool_overrides.yaml` = `{forced_in: [], forced_out: []}`
- `config/themes.yaml` = 31 主题（头 8：theme_ai_compute / semiconductor / gpu / megacap_tech / enterprise_software / cybersecurity / cloud_infra / clean_energy）

## 12 类信号

- **M 池（量化）**：B1-B5 看涨 / S1/S2a/S2b/S3 看跌 / W1/W2 警告
- **A 池（长线）**：theme_oversold_entry（第 12 类 · A 池专属）

## 三维评分（§A.4）

- 弹性 35% / 性价比 30% / R:R 35%
- 主题加成（§A.5）：quintile='top' → +5 / 'bottom' + 第 12 类 → +3
- A 池 highlights 触发：a_score ≥ 70 · 渲染 H3 🎯 入场/止损/目标 + 触发链 + theme_quintile

## A 池 long-thesis mcap 反推

```python
thesis_stop_price = thesis_stop_mcap_b * 1e9 / shares_outstanding
target_price = target_mcap_b * 1e9 / shares_outstanding
strategic_rr = (target_price - close) / (close - thesis_stop_price)
```

## 关键 ADR

- ADR-022/023/024/025/026/027：M 池筛选 / mcap-anchor / themes 评分等
- **ADR-028 themes.yaml C 混合路径** ⭐：themes 用 yaml 定义 · etf_holdings 实拉成员
- **ADR-030 A 池长线 thesis** ⭐：双池架构 · A 池长线 thesis 与 M 池量化分离

## LightOS 环境（用户的远程跑环境 · 你不进）

- SSH：`ssh -p 2222 naivedog@<host>`（用户已登录）
- repo：`/home/naivedog/us-stock-research/`
- `.env`：`/home/naivedog/us-stock-research/.env`（547 bytes · 权限 600 · **不在 home 根目录**）
- 已注入 13 KEY：`DATABASE_URL` `DISCORD_WEBHOOK_URL` `FMP_API_KEY` `LOG_LEVEL` `NOTION_DAILY_DB_ID` `NOTION_TOKEN` `POSTGRES_*`(5) `PYTHONUNBUFFERED` `FRED_API_KEY` `POLYGON_API_KEY`
- ⚠️ `DATABASE_URL` 已被改为 `postgresql+psycopg://stock_user:...`（cutover 兜底 · V5+1 P2 修后可改回 `postgresql://`）
- 缺 `GOOGLE_APPLICATION_CREDENTIALS`（cutover 阶段 a 池为空 · 不需要 · V5+2 再补）
- uv：`/home/naivedog/.local/bin/uv` · venv `~/us-stock-research/.venv/`
- Postgres 17：[localhost:5432](http://localhost:5432) · `stock_user` / `ChangeMe2026Strong!` / database `usstock`
- 日志：`~/logs/daily-YYYY-MM-DD.log`
- 备份：`/lzcapp/document/usstock-backups/usstock-cutover-2026-04-30.sql.gz`（126MB · cutover 前完整备份 · 回滚源）
- 时区：系统 = UTC · cron 双版本（UTC 主 / Asia/Shanghai 备）
- git stash：`On master: lightos-pre-V57-cutover-2026-04-30`（V4 hotfix · cutover 完决定 drop）
- 残留文件：`scripts/compute_indicators.py.bak.20260430`（untracked · V5+1 P5 间接处理）
- preflight ALTER：`/tmp/preflight_alters.sql`（28 行 · 临时 · cutover 完可删）

## Win 本地环境（你工作的地方）

- 路径：`D:\Dev\us-stock-research\`
- Shell：PowerShell 7（**bash / WSL 不可用**）
- 行尾：`core.autocrlf=true`（CRLF 在 Win · LF 在 LightOS · 无害）
- pytest：可能有 `atexit PermissionError`（uv cache ACL 噪音 · 不影响测试结果 · 不要乱修）
- 字符集：UTF-8 · 不要写 BOM · 注意中文注释不要 mojibake

## GitHub

- repo：`https://github.com/imnaivedog/us-stock-research.git`
- 默认分支：**master**（不是 main · trunk 直推）
- HEAD：`4348cbc chore(deploy): readme troubleshooting + cron tz + alert_log category`
- 累计 20 commits（截止 cutover 起点）
- 你的 commit 加在 master HEAD 之后 · 不开 PR

## Postgres 数据规模（cutover 前 · 不能丢）

- symbol_universe：2358（含 V4 历史 inactive · 当前活跃 m 池 1784）
- quotes_daily：1.82M+
- macro_daily：1830
- daily_indicators：450K
- 任何 schema 变更必须 idempotent（CREATE/ALTER/DROP 全 IF NOT EXISTS）

## 起步

继续读 `02_STATUS.md`（cutover 卡在哪 · 你第一件事）。